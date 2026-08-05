"""Worker: resolve ad_id → meta_campaign_id via Graph e grava cache.

Usa o mesmo token ``ads_read`` de ``meta_ads_config`` (gasto automático).
Sobe sempre com o processo (lifespan); testes usam ``REVY_TRAFEGO_SKIP_INIT=1``.

Proteções de volume:

- não re-resolve cache com campaign_id;
- max tentativas por ad;
- cooldown após falha;
- teto de chamadas Graph por ciclo/loja;
- cliente Graph com backoff em 429/5xx.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from app.clients.meta_graph import ResolveResult, resolver_campanha_do_anuncio
from app.cripto import decifrar
from app.meta_ads_spend import normalizar_meta_campaign_id
from app.models import MetaAdCampanha, MetaAdsConfig, novo_id

logger = logging.getLogger(__name__)

# Defaults de proteção (sobrescrevíveis por env)
DEFAULT_MAX_TENTATIVAS = 5
DEFAULT_COOLDOWN_SECONDS = 86400.0  # 24h
DEFAULT_MAX_POR_CICLO = 20
DEFAULT_SLEEP_ENTRE_CALLS = 0.05


def env_float(nome: str, default: float) -> float:
    try:
        return float(os.getenv(nome, str(default)))
    except (TypeError, ValueError):
        return default


def env_int(nome: str, default: int) -> int:
    try:
        return int(os.getenv(nome, str(default)))
    except (TypeError, ValueError):
        return default


def _limites_from_env() -> tuple[int, float, int, float]:
    return (
        max(1, env_int("REVY_TRAFEGO_AD_RESOLVER_MAX_TENTATIVAS", DEFAULT_MAX_TENTATIVAS)),
        max(0.0, env_float("REVY_TRAFEGO_AD_RESOLVER_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS)),
        max(1, env_int("REVY_TRAFEGO_AD_RESOLVER_MAX_POR_CICLO", DEFAULT_MAX_POR_CICLO)),
        max(0.0, env_float("REVY_TRAFEGO_AD_RESOLVER_SLEEP_ENTRE_CALLS", DEFAULT_SLEEP_ENTRE_CALLS)),
    )


def mapa_ad_campaign_loja(db: Session, loja_slug: str) -> dict[str, str]:
    """Mapa ``ad_id → meta_campaign_id`` resolvido (cache Graph) da loja."""
    rows = (
        db.query(MetaAdCampanha)
        .filter(
            MetaAdCampanha.loja_slug == loja_slug,
            MetaAdCampanha.meta_campaign_id.isnot(None),
        )
        .all()
    )
    out: dict[str, str] = {}
    for r in rows:
        if r.ad_id and r.meta_campaign_id:
            out[r.ad_id] = r.meta_campaign_id
    return out


@dataclass
class ResolveBatchResult:
    resolvidos: int = 0
    chamadas: int = 0
    skipped_ok: int = 0
    skipped_cooldown: int = 0
    skipped_max_tentativas: int = 0
    skipped_teto: int = 0
    falhas: int = 0
    detalhes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "resolvidos": self.resolvidos,
            "chamadas": self.chamadas,
            "skipped_ok": self.skipped_ok,
            "skipped_cooldown": self.skipped_cooldown,
            "skipped_max_tentativas": self.skipped_max_tentativas,
            "skipped_teto": self.skipped_teto,
            "falhas": self.falhas,
        }


def _normalize_resolver_result(raw) -> ResolveResult:
    """Aceita ResolveResult ou tupla legada ``(cid, nome)``."""
    if isinstance(raw, ResolveResult):
        return raw
    if isinstance(raw, tuple) and len(raw) >= 2:
        cid, nome = raw[0], raw[1]
        if cid:
            return ResolveResult(
                campaign_id=str(cid),
                campaign_nome=str(nome) if nome else None,
            )
        return ResolveResult(erro="nao_resolvido")
    return ResolveResult(erro="nao_resolvido")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _deve_pular(
    row: MetaAdCampanha | None,
    *,
    agora: datetime,
    max_tentativas: int,
    cooldown_seconds: float,
    result: ResolveBatchResult,
) -> bool:
    """True se não deve chamar a Graph para este ad."""
    if row is None:
        return False
    if row.meta_campaign_id:
        result.skipped_ok += 1
        return True
    if (row.tentativas or 0) >= max_tentativas:
        result.skipped_max_tentativas += 1
        return True
    if cooldown_seconds > 0 and row.erro and row.ultima_tentativa_em:
        ultima = _aware(row.ultima_tentativa_em)
        if ultima and agora < ultima + timedelta(seconds=cooldown_seconds):
            result.skipped_cooldown += 1
            return True
    return False


def resolver_ads_pendentes(
    db: Session,
    loja_slug: str,
    ad_ids: Iterable[str],
    *,
    token: str,
    resolver=resolver_campanha_do_anuncio,
    max_tentativas: int | None = None,
    cooldown_seconds: float | None = None,
    max_por_ciclo: int | None = None,
    sleep_entre_calls: float | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    agora: datetime | None = None,
) -> ResolveBatchResult:
    """Upsert no cache dos ``ad_ids`` elegíveis. Nunca lança.

    Não re-resolve entradas com ``meta_campaign_id``.
    Respeita max tentativas, cooldown de falha e teto de chamadas por ciclo.
    """
    result = ResolveBatchResult()
    if not token:
        return result

    env_max_t, env_cd, env_teto, env_sleep = _limites_from_env()
    max_tentativas = max_tentativas if max_tentativas is not None else env_max_t
    cooldown_seconds = (
        cooldown_seconds if cooldown_seconds is not None else env_cd
    )
    max_por_ciclo = max_por_ciclo if max_por_ciclo is not None else env_teto
    sleep_entre_calls = (
        sleep_entre_calls if sleep_entre_calls is not None else env_sleep
    )
    now = agora or datetime.now(timezone.utc)

    # Pré-carrega rows da loja para os ad_ids normalizados
    normalizados: list[str] = []
    vistos: set[str] = set()
    for raw in ad_ids:
        ad_id = normalizar_meta_campaign_id(raw)
        if ad_id and ad_id not in vistos:
            vistos.add(ad_id)
            normalizados.append(ad_id)

    if not normalizados:
        return result

    existentes = {
        r.ad_id: r
        for r in db.query(MetaAdCampanha)
        .filter(
            MetaAdCampanha.loja_slug == loja_slug,
            MetaAdCampanha.ad_id.in_(normalizados),
        )
        .all()
    }

    for ad_id in normalizados:
        row = existentes.get(ad_id)
        if _deve_pular(
            row,
            agora=now,
            max_tentativas=max_tentativas,
            cooldown_seconds=cooldown_seconds,
            result=result,
        ):
            continue

        if result.chamadas >= max_por_ciclo:
            result.skipped_teto += 1
            continue

        if result.chamadas > 0 and sleep_entre_calls > 0:
            try:
                sleeper(sleep_entre_calls)
            except Exception:
                pass

        try:
            raw = resolver(ad_id, token)
            resolved = _normalize_resolver_result(raw)
        except Exception:
            logger.warning(
                "meta_ad_resolver: resolver falhou loja=%s ad=%s",
                loja_slug,
                ad_id,
            )
            resolved = ResolveResult(erro="excecao", retryable=True)

        result.chamadas += 1
        if row is None:
            row = MetaAdCampanha(id=novo_id(), loja_slug=loja_slug, ad_id=ad_id)
            db.add(row)
            existentes[ad_id] = row

        row.tentativas = (row.tentativas or 0) + 1
        row.ultima_tentativa_em = now

        if resolved.campaign_id:
            row.meta_campaign_id = normalizar_meta_campaign_id(resolved.campaign_id)
            row.meta_campaign_nome = (
                (resolved.campaign_nome or None)
                and str(resolved.campaign_nome)[:200]
            )
            row.resolvido_em = now
            row.erro = None
            result.resolvidos += 1
        else:
            erro = (resolved.erro or "nao_resolvido")[:300]
            row.erro = erro
            result.falhas += 1

    return result


def _extrair_ad_ids_leads(leads: list[dict]) -> list[str]:
    vistos: list[str] = []
    for lead in leads or []:
        for key in ("meta_ad_id", "meta_ad_id_first"):
            n = normalizar_meta_campaign_id(lead.get(key))
            if n and n not in vistos:
                vistos.append(n)
    return vistos


def processar_loja(
    db: Session,
    loja_slug: str,
    *,
    listar_leads: Callable[[], list[dict]] | None = None,
    resolver=resolver_campanha_do_anuncio,
    sleeper: Callable[[float], None] = time.sleep,
    **limites,
) -> ResolveBatchResult:
    """Resolve ads pendentes de uma loja. Nunca lança."""
    vazio = ResolveBatchResult()
    try:
        from app.control.stores import store_blocks_traffic_jobs

        if store_blocks_traffic_jobs(db, loja_slug=loja_slug):
            return vazio
    except Exception:
        pass

    config = (
        db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == loja_slug).first()
    )
    if config is None or not config.token_ciphertext:
        return vazio
    try:
        token = decifrar(config.token_ciphertext)
    except Exception:
        logger.warning("meta_ad_resolver: token inválido loja=%s", loja_slug)
        return vazio
    if not token:
        return vazio

    leads: list[dict] = []
    if listar_leads is not None:
        try:
            leads = listar_leads() or []
        except Exception as exc:
            logger.warning(
                "meta_ad_resolver: falha ao listar leads loja=%s tipo=%s",
                loja_slug,
                type(exc).__name__,
            )
            return vazio
    ad_ids = _extrair_ad_ids_leads(leads)
    if not ad_ids:
        return vazio
    batch = resolver_ads_pendentes(
        db,
        loja_slug,
        ad_ids,
        token=token,
        resolver=resolver,
        sleeper=sleeper,
        **limites,
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("meta_ad_resolver: commit falhou loja=%s", loja_slug)
        return vazio
    return batch


def processar_todas_lojas(
    db_factory: Callable[[], Session],
    *,
    chatbot_factory: Callable[[str], object] | None = None,
    resolver=resolver_campanha_do_anuncio,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Varre lojas com token Meta e resolve ads. Nunca lança."""
    resumo = {
        "lojas": 0,
        "resolvidos": 0,
        "chamadas": 0,
        "falhas": 0,
        "skipped_cooldown": 0,
        "skipped_max_tentativas": 0,
        "skipped_teto": 0,
        "erros": 0,
    }
    db = db_factory()
    try:
        slugs = [
            r[0]
            for r in db.query(MetaAdsConfig.loja_slug)
            .filter(MetaAdsConfig.token_ciphertext.isnot(None))
            .all()
        ]
    finally:
        db.close()

    for slug in slugs:
        db = db_factory()
        try:
            listar = None
            if chatbot_factory is not None:
                client = chatbot_factory(slug)

                def _listar(c=client):
                    return c.listar_leads()

                listar = _listar
            batch = processar_loja(
                db, slug, listar_leads=listar, resolver=resolver, sleeper=sleeper
            )
            resumo["lojas"] += 1
            resumo["resolvidos"] += batch.resolvidos
            resumo["chamadas"] += batch.chamadas
            resumo["falhas"] += batch.falhas
            resumo["skipped_cooldown"] += batch.skipped_cooldown
            resumo["skipped_max_tentativas"] += batch.skipped_max_tentativas
            resumo["skipped_teto"] += batch.skipped_teto
        except Exception:
            resumo["erros"] += 1
            logger.warning("meta_ad_resolver: falha loja=%s", slug)
        finally:
            db.close()
    return resumo


class MetaAdResolverWorker:
    """Thread daemon que resolve ad_id→campaign em intervalo fixo."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        chatbot_factory: Callable[[str], object] | None = None,
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        enabled: bool | None = None,
    ):
        self.db_factory = db_factory
        self.chatbot_factory = chatbot_factory
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else env_float("REVY_TRAFEGO_AD_RESOLVER_INTERVAL_SECONDS", 3600.0)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else env_float("REVY_TRAFEGO_AD_RESOLVER_INITIAL_DELAY_SECONDS", 90.0)
        )
        # Sempre ligado no runtime; só desliga se o chamador passar enabled=False (testes).
        self.enabled = True if enabled is None else bool(enabled)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict | None = None

    def start(self) -> None:
        if not self.enabled:
            logger.info("meta_ad_resolver: desligado (enabled=False)")
            return
        if self.interval <= 0:
            logger.info("meta_ad_resolver: intervalo inválido, não inicia")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="meta-ad-resolver",
            daemon=True,
        )
        self._thread.start()
        max_t, cd, teto, sleep_c = _limites_from_env()
        logger.info(
            "meta_ad_resolver: iniciado interval=%ss delay=%ss "
            "max_tentativas=%s cooldown=%ss max_por_ciclo=%s sleep=%ss",
            self.interval,
            self.initial_delay,
            max_t,
            cd,
            teto,
            sleep_c,
        )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def run_once(self) -> dict:
        try:
            result = processar_todas_lojas(
                self.db_factory,
                chatbot_factory=self.chatbot_factory,
            )
            payload = {"ok": True, **result}
            self.last_result = payload
            logger.info(
                "meta_ad_resolver: lojas=%s resolvidos=%s chamadas=%s falhas=%s "
                "skip_cd=%s skip_max=%s skip_teto=%s erros=%s",
                result.get("lojas"),
                result.get("resolvidos"),
                result.get("chamadas"),
                result.get("falhas"),
                result.get("skipped_cooldown"),
                result.get("skipped_max_tentativas"),
                result.get("skipped_teto"),
                result.get("erros"),
            )
            return payload
        except Exception as exc:
            logger.warning(
                "meta_ad_resolver: falha tipo=%s", type(exc).__name__
            )
            payload = {"ok": False, "erro": type(exc).__name__}
            self.last_result = payload
            return payload

    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval):
                break


_worker: MetaAdResolverWorker | None = None


def get_worker() -> MetaAdResolverWorker | None:
    return _worker


def start_worker(
    db_factory: Callable[[], Session],
    *,
    chatbot_factory: Callable[[str], object] | None = None,
) -> MetaAdResolverWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = MetaAdResolverWorker(
        db_factory=db_factory,
        chatbot_factory=chatbot_factory,
    )
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
