"""Importa gasto de campanhas via Meta Marketing API (Insights).

Token com ``ads_read`` — distinto do token CAPI de conversões.
Falha de rede/API nunca deve quebrar o fluxo de venda.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from app.cripto import decifrar
from app.models import Campanha, CampanhaGasto, MetaAdsConfig, agora, novo_id

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
CENTAVOS = Decimal("0.01")
ORIGEM_META = "meta_api"
ORIGEM_MANUAL = "manual"
DEFAULT_TIMEOUT = 30.0
MAX_INSIGHTS_PAGES = 100
NOTA_META = "Meta API (gasto automático)"


@dataclass
class SyncResult:
    imported: int = 0
    updated: int = 0
    skipped_manual: int = 0
    orphans: int = 0
    orphan_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | partial | erro

    def resumo(self) -> str:
        partes = [
            f"{self.imported} novo(s)",
            f"{self.updated} atualizado(s)",
            f"{self.orphans} sem campanha no Revy",
        ]
        if self.skipped_manual:
            partes.append(f"{self.skipped_manual} manual preservado(s)")
        if self.errors:
            partes.append(f"{len(self.errors)} erro(s)")
        return " · ".join(partes)[:240]


def normalizar_ad_account_id(valor: str | None) -> str:
    raw = (valor or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    return f"act_{digits}"


def normalizar_meta_campaign_id(valor: str | None) -> str | None:
    raw = (valor or "").strip()
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits or None


def external_key_meta(loja_slug: str, meta_campaign_id: str, referencia: date) -> str:
    return f"meta:{loja_slug}:{meta_campaign_id}:{referencia.isoformat()}"


def parse_spend(valor: Any) -> Decimal | None:
    if valor is None:
        return None
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    if d < 0:
        return None
    return d.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def erro_api_sanitizado(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return f"Meta Insights respondeu HTTP {exc.response.status_code}."
    if isinstance(exc, httpx.RequestError):
        return "Falha de rede ao contatar a Meta Insights."
    return "Falha interna ao sincronizar gastos da Meta."


def fetch_campaign_insights(
    *,
    ad_account_id: str,
    access_token: str,
    since: date,
    until: date,
    timeout: float = DEFAULT_TIMEOUT,
    client: httpx.Client | None = None,
    max_pages: int = MAX_INSIGHTS_PAGES,
) -> list[dict[str, Any]]:
    """Busca spend diário por campanha no ad account."""
    account = normalizar_ad_account_id(ad_account_id)
    if not account:
        raise ValueError("ad_account_id inválido")
    if until < since:
        raise ValueError("período inválido")
    if max_pages < 1:
        raise ValueError("max_pages inválido")

    params = {
        "level": "campaign",
        "fields": "campaign_id,campaign_name,spend,date_start,date_stop",
        "time_increment": 1,
        "time_range": f'{{"since":"{since.isoformat()}","until":"{until.isoformat()}"}}',
        "limit": 500,
        "access_token": access_token,
    }
    url: str | None = f"{GRAPH_BASE}/{account}/insights"
    rows: list[dict[str, Any]] = []
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout)
    visitadas: set[str] = set()
    try:
        while url:
            if url in visitadas:
                raise RuntimeError("Meta Insights retornou paginação cíclica")
            if len(visitadas) >= max_pages:
                raise RuntimeError("Meta Insights excedeu o limite de páginas")
            visitadas.add(url)
            if url.startswith("http"):
                response = http.get(url, params=params if "access_token" not in url else None)
            else:
                response = http.get(url, params=params)
            response.raise_for_status()
            body = response.json()
            rows.extend(body.get("data") or [])
            next_url = (body.get("paging") or {}).get("next")
            url = next_url
            params = {}  # next já carrega query string
    finally:
        if owns_client:
            http.close()
    return rows


def _config_loja(db: Session, loja_slug: str) -> MetaAdsConfig | None:
    return db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == loja_slug).first()


@dataclass
class _LinhaBatch:
    """Rastreia o que já foi decidido para uma ``external_key`` neste batch.

    ``SessionLocal`` usa ``autoflush=False``: um ``db.add()`` continua pendente
    e a query de dedupe não o enxerga. Sem esta memória em processo, duas linhas
    da Meta para a mesma campanha+dia (paginação sobreposta, linha corrigida)
    virariam dois INSERTs e o commit estouraria ``UNIQUE(external_key)``.
    """

    gasto: CampanhaGasto | None  # None = linha ignorada (gasto manual do dia)
    novo: bool = False
    atualizado: bool = False


def sincronizar_gastos_meta(
    db: Session,
    loja_slug: str,
    *,
    since: date | None = None,
    until: date | None = None,
    janela_dias: int = 7,
    fetch: Callable[..., list[dict[str, Any]]] | None = None,
) -> SyncResult:
    """Importa spend e grava CampanhaGasto com origem meta_api."""
    result = SyncResult()
    config = _config_loja(db, loja_slug)
    if config is None or not config.token_ciphertext or not config.ad_account_id:
        result.status = "erro"
        result.errors.append("Configure a conta de anúncios Meta (Ad Account + token) em Tráfego.")
        return result
    if not config.sync_enabled:
        result.status = "erro"
        result.errors.append("Sincronização de gastos Meta está desligada para esta loja.")
        return result

    fim = until or date.today()
    inicio = since or (fim - timedelta(days=max(janela_dias - 1, 0)))
    try:
        token = decifrar(config.token_ciphertext)
    except Exception:
        result.status = "erro"
        result.errors.append("Não foi possível ler o token da conta de anúncios.")
        _persistir_status(config, result)
        db.commit()
        return result

    fetcher = fetch or fetch_campaign_insights
    try:
        rows = fetcher(
            ad_account_id=config.ad_account_id,
            access_token=token,
            since=inicio,
            until=fim,
        )
    except Exception as exc:
        result.status = "erro"
        result.errors.append(erro_api_sanitizado(exc))
        logger.warning(
            "meta_ads_spend: falha loja=%s tipo=%s",
            loja_slug,
            type(exc).__name__,
        )
        _persistir_status(config, result)
        db.commit()
        return result

    try:
        _aplicar_rows(db, loja_slug, rows, result)
        _definir_status(result)
        _persistir_status(config, result)
        db.commit()
    except Exception as exc:
        # Contrato do módulo: falha aqui nunca pode escapar e quebrar o fluxo
        # do chamador (UI vira 500, job perde o batch da loja).
        _tratar_falha_persistencia(db, loja_slug, result, exc)
    return result


def _aplicar_rows(
    db: Session,
    loja_slug: str,
    rows: list[dict[str, Any]],
    result: SyncResult,
) -> None:
    campanhas = (
        db.query(Campanha)
        .filter(
            Campanha.loja_slug == loja_slug,
            Campanha.meta_campaign_id.isnot(None),
        )
        .all()
    )
    por_meta_id = {
        c.meta_campaign_id: c
        for c in campanhas
        if c.meta_campaign_id
    }

    # Dedupe intra-batch: external_key -> decisão já tomada nesta rodada.
    processados: dict[str, _LinhaBatch] = {}

    for row in rows:
        meta_id = normalizar_meta_campaign_id(row.get("campaign_id"))
        if not meta_id:
            continue
        spend = parse_spend(row.get("spend"))
        if spend is None:
            continue
        if spend == 0:
            # Zero spend: ainda assim podemos registrar/atualizar se quiser; MVP ignora 0
            continue
        try:
            ref = date.fromisoformat(str(row.get("date_start") or "")[:10])
        except ValueError:
            continue

        campanha = por_meta_id.get(meta_id)
        if campanha is None:
            result.orphans += 1
            if meta_id not in result.orphan_ids and len(result.orphan_ids) < 20:
                result.orphan_ids.append(meta_id)
            continue

        key = external_key_meta(loja_slug, meta_id, ref)

        anterior = processados.get(key)
        if anterior is not None:
            # Mesma campanha+dia repetida no batch: a ÚLTIMA linha prevalece.
            # Somar inflaria o gasto (a Meta já manda o total do dia) e
            # distorceria o ROI.
            if anterior.gasto is None:
                continue  # manual preservado, já contabilizado
            if anterior.gasto.valor != spend:
                anterior.gasto.valor = spend
                anterior.gasto.nota = NOTA_META
                if not anterior.novo and not anterior.atualizado:
                    result.updated += 1
                    anterior.atualizado = True
            continue

        existente = (
            db.query(CampanhaGasto)
            .filter(CampanhaGasto.external_key == key)
            .first()
        )
        if existente is None:
            # Evita sobrescrever lançamento manual do mesmo dia sem external_key
            manual = (
                db.query(CampanhaGasto)
                .filter(
                    CampanhaGasto.campanha_id == campanha.id,
                    CampanhaGasto.referencia == ref,
                    CampanhaGasto.origem == ORIGEM_MANUAL,
                )
                .first()
            )
            if manual is not None:
                result.skipped_manual += 1
                processados[key] = _LinhaBatch(gasto=None)
                continue
            gasto = CampanhaGasto(
                id=novo_id(),
                campanha_id=campanha.id,
                loja_slug=loja_slug,
                valor=spend,
                referencia=ref,
                nota=NOTA_META,
                origem=ORIGEM_META,
                external_key=key,
                criada_por="meta_api",
            )
            db.add(gasto)
            result.imported += 1
            processados[key] = _LinhaBatch(gasto=gasto, novo=True)
            continue

        if existente.origem == ORIGEM_MANUAL:
            result.skipped_manual += 1
            processados[key] = _LinhaBatch(gasto=None)
            continue
        registro = _LinhaBatch(gasto=existente)
        if existente.valor != spend:
            existente.valor = spend
            existente.nota = NOTA_META
            result.updated += 1
            registro.atualizado = True
        # se igual, no-op silencioso
        processados[key] = registro


def _definir_status(result: SyncResult) -> None:
    if result.errors:
        result.status = "partial" if (result.imported or result.updated) else "erro"
    elif result.orphans and not (result.imported or result.updated):
        result.status = "partial"
    else:
        result.status = "ok"


def _tratar_falha_persistencia(
    db: Session,
    loja_slug: str,
    result: SyncResult,
    exc: Exception,
) -> None:
    """Rollback + status ``erro``; nada escapa para o chamador."""
    logger.warning(
        "meta_ads_spend: falha ao gravar loja=%s tipo=%s",
        loja_slug,
        type(exc).__name__,
    )
    try:
        db.rollback()
    except Exception:  # pragma: no cover - sessão já inutilizável
        pass
    # Nada foi persistido: não contabilize o que voltou atrás.
    result.imported = 0
    result.updated = 0
    result.skipped_manual = 0
    result.status = "erro"
    result.errors.append("Falha ao gravar os gastos importados da Meta.")
    try:
        config = _config_loja(db, loja_slug)
        if config is not None:
            _persistir_status(config, result)
            db.commit()
    except Exception:  # pragma: no cover - best effort
        try:
            db.rollback()
        except Exception:
            pass


def _persistir_status(config: MetaAdsConfig, result: SyncResult) -> None:
    config.ultima_sync_em = agora()
    config.ultima_sync_status = result.status
    config.ultima_sync_erro = (result.errors[0][:500] if result.errors else None)
    config.ultima_sync_resumo = result.resumo()
    config.atualizada_em = agora()


@dataclass
class SyncAllResult:
    lojas: int = 0
    ok: int = 0
    partial: int = 0
    erro: int = 0
    imported: int = 0
    updated: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def resumo(self) -> str:
        return (
            f"{self.lojas} loja(s) · {self.ok} ok · {self.partial} parcial · "
            f"{self.erro} erro · +{self.imported}/~{self.updated} gastos"
        )[:240]


def listar_lojas_para_sync(db: Session) -> list[str]:
    rows = (
        db.query(MetaAdsConfig.loja_slug)
        .filter(
            MetaAdsConfig.sync_enabled.is_(True),
            MetaAdsConfig.token_ciphertext.isnot(None),
            MetaAdsConfig.ad_account_id != "",
        )
        .all()
    )
    return [r[0] for r in rows]


def sincronizar_todas_lojas(
    db_factory: Callable[[], Session],
    *,
    janela_dias: int = 3,
    fetch: Callable[..., list[dict[str, Any]]] | None = None,
) -> SyncAllResult:
    """Roda sync por loja em sessões separadas (falha de uma não aborta as demais)."""
    aggregate = SyncAllResult()
    db = db_factory()
    try:
        lojas = listar_lojas_para_sync(db)
    finally:
        db.close()

    for loja_slug in lojas:
        aggregate.lojas += 1
        session = db_factory()
        try:
            result = sincronizar_gastos_meta(
                session,
                loja_slug,
                janela_dias=janela_dias,
                fetch=fetch,
            )
            if result.status == "ok":
                aggregate.ok += 1
            elif result.status == "partial":
                aggregate.partial += 1
            else:
                aggregate.erro += 1
            aggregate.imported += result.imported
            aggregate.updated += result.updated
            aggregate.details.append(
                {
                    "loja_slug": loja_slug,
                    "status": result.status,
                    "resumo": result.resumo(),
                }
            )
        except Exception as exc:
            aggregate.erro += 1
            logger.warning(
                "meta_ads_spend: job loja=%s falhou tipo=%s",
                loja_slug,
                type(exc).__name__,
            )
            aggregate.details.append(
                {
                    "loja_slug": loja_slug,
                    "status": "erro",
                    "resumo": erro_api_sanitizado(exc),
                }
            )
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
    return aggregate
