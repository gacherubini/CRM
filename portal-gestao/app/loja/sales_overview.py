"""SalesOverview — read model único da Visão geral de Vendas (Fase 3).

Compõe módulos existentes sem duplicar regras de negócio:
- app.financeiro_calc (receita, margem, metas, funil auditável)
- app.funil_eventos (resumo de coorte / SLA)
- app.resultados_dono + app.roi_calc (aquisição / ROAS)
- padrões do painel do vendedor em app.main

Estados de bloco: ok | vazio | parcial | erro | indisponivel.
Aquisição nunca inventa investimento zero nem ROAS infinito.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Mapping
from sqlalchemy.orm import Session

from app.config import settings
from app.financeiro_calc import (
    FUSO_PORTAL,
    _data,
    calcular_metricas_vendas,
    funil_periodo,
    lucro_bruto_venda,
    metas_view_periodo,
    periodo_padrao,
)
from app.funil_eventos import resumo_funil
from app.models import Meta, Venda
from app.resultados_dono import resumo_from_api, resumo_periodo
from app.roi_calc import calcular_roi_loja, totais_roi

CENTAVOS = Decimal("0.01")

# Papéis com visão comercial completa da loja.
PAPEIS_VISAO_COMPLETA = frozenset({"dono", "gerente", "admin_plataforma"})
PAPEIS_VENDEDOR = frozenset({"vendedor"})
PAPEIS_AUTORIZADOS = PAPEIS_VISAO_COMPLETA | PAPEIS_VENDEDOR


@dataclass(frozen=True)
class PendenciaAcao:
    codigo: str
    texto: str
    href: str
    quantidade: int = 1


@dataclass(frozen=True)
class AquisicaoResumo:
    """Resumo comercial de aquisição (Meta/local; Google fica indisponível até Control 4)."""

    status: str  # ok | parcial | indisponivel
    investimento: Decimal | None = None
    investimento_disponivel: bool = False
    cac: Decimal | None = None
    cac_disponivel: bool = False
    roas: Decimal | None = None
    roas_disponivel: bool = False
    leads: int | None = None
    vendas_atribuidas: int | None = None
    faturamento_atribuido: Decimal | None = None
    google_status: str = "indisponivel"
    fonte: str | None = None  # api | local | None
    mensagem: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "investimento": _dec_str(self.investimento) if self.investimento_disponivel else None,
            "investimento_disponivel": self.investimento_disponivel,
            "cac": _dec_str(self.cac) if self.cac_disponivel else None,
            "cac_disponivel": self.cac_disponivel,
            "roas": _dec_str(self.roas) if self.roas_disponivel else None,
            "roas_disponivel": self.roas_disponivel,
            "leads": self.leads,
            "vendas_atribuidas": self.vendas_atribuidas,
            "faturamento_atribuido": (
                _dec_str(self.faturamento_atribuido)
                if self.faturamento_atribuido is not None
                else None
            ),
            "google_status": self.google_status,
            "fonte": self.fonte,
            "mensagem": self.mensagem,
        }


@dataclass
class SalesOverview:
    """Interface única de leitura da Visão geral de Vendas."""

    status: str  # ok | vazio | parcial | erro
    periodo_inicio: date
    periodo_fim: date
    timezone: str
    escopo: str  # loja | vendedor
    vendedor_email: str | None = None

    # Vendas / financeiro
    receita: Decimal | None = None
    margem: Decimal | None = None
    margem_completa: bool = True
    vendas_lucro_incompleto: int = 0
    qtd_vendas: int = 0
    vendas_status: str = "vazio"  # ok | vazio | parcial | erro

    # Metas
    metas: list[dict[str, Any]] = field(default_factory=list)
    metas_status: str = "vazio"

    # Leads / funil
    leads_count: int | None = None
    funil: dict[str, Any] | None = None
    funil_status: str = "indisponivel"

    # Aquisição (Control / Revy Tráfego / cálculo local)
    aquisicao: AquisicaoResumo | None = None
    aquisicao_status: str = "indisponivel"
    # Detalhe por campanha/canal — só quando vem da API, que é quem sabe o gasto.
    # O fallback local não tem número confiável por campanha; fica vazio.
    aquisicao_campanhas: list[dict[str, Any]] = field(default_factory=list)
    aquisicao_canais: list[dict[str, Any]] = field(default_factory=list)

    # Pendências acionáveis derivadas dos dados atuais
    pendencias: list[PendenciaAcao] = field(default_factory=list)

    # Mensagem global opcional
    mensagem: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "periodo": {
                "inicio": self.periodo_inicio.isoformat(),
                "fim": self.periodo_fim.isoformat(),
                "timezone": self.timezone,
            },
            "escopo": self.escopo,
            "vendedor_email": self.vendedor_email,
            "receita": _dec_str(self.receita) if self.receita is not None else None,
            "margem": _dec_str(self.margem) if self.margem is not None else None,
            "margem_completa": self.margem_completa,
            "vendas_lucro_incompleto": self.vendas_lucro_incompleto,
            "qtd_vendas": self.qtd_vendas,
            "vendas_status": self.vendas_status,
            "metas": _serializar_metas(self.metas),
            "metas_status": self.metas_status,
            "leads_count": self.leads_count,
            "funil": self.funil,
            "funil_status": self.funil_status,
            "aquisicao": self.aquisicao.to_dict() if self.aquisicao else None,
            "aquisicao_status": self.aquisicao_status,
            "aquisicao_campanhas": _serializar_linhas_midia(self.aquisicao_campanhas),
            "aquisicao_canais": _serializar_linhas_midia(self.aquisicao_canais),
            "pendencias": [asdict(p) for p in self.pendencias],
            "mensagem": self.mensagem,
        }


def _dec_str(valor: Decimal | None) -> str | None:
    if valor is None:
        return None
    return str(valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP))


def _serializar_linhas_midia(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saida = []
    for linha in linhas:
        item = {
            chave: (_dec_str(valor) if isinstance(valor, Decimal) else valor)
            for chave, valor in linha.items()
        }
        saida.append(item)
    return saida


def _dec_ou_none(valor: Any) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (ArithmeticError, TypeError, ValueError):
        return None


def _linhas_midia_da_api(payload: Mapping[str, Any] | None) -> tuple[list, list]:
    """Campanhas e canais do payload da API, com Decimal já convertido.

    Ordena campanha por gasto (maior primeiro): quem gasta mais é o que o dono
    precisa olhar antes.
    """
    if not payload:
        return [], []

    def _linha(bruto: Mapping[str, Any], campos_decimais: tuple[str, ...]) -> dict:
        item = dict(bruto)
        for campo in campos_decimais:
            if campo in item:
                item[campo] = _dec_ou_none(item[campo])
        return item

    campanhas = [
        _linha(c, ("gasto", "faturamento", "cpl", "cpa", "roas"))
        for c in (payload.get("campanhas") or [])
    ]
    campanhas.sort(key=lambda c: c.get("gasto") or Decimal("0"), reverse=True)
    canais = [
        _linha(c, ("gasto", "faturamento", "roas"))
        for c in (payload.get("canais") or [])
    ]
    return campanhas, canais


def _serializar_metas(metas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saida = []
    for m in metas:
        item = dict(m)
        for chave in ("alvo", "realizado"):
            if chave in item and isinstance(item[chave], Decimal):
                item[chave] = _dec_str(item[chave])
        saida.append(item)
    return saida


def _periodo_datetime(d_inicio: date, d_fim: date) -> tuple[datetime, datetime]:
    fuso = FUSO_PORTAL
    inicio_dt = datetime.combine(d_inicio, datetime.min.time(), tzinfo=fuso)
    fim_dt = datetime.combine(
        d_fim + timedelta(days=1),
        datetime.min.time(),
        tzinfo=fuso,
    ) - timedelta(microseconds=1)
    return inicio_dt, fim_dt


def _metricas_vendedor(
    db: Session,
    loja_slug: str,
    vendedor_email: str,
    d_inicio: date,
    d_fim: date,
) -> dict[str, Any]:
    """Mesma semântica de calcular_metricas_vendas, filtrada ao vendedor."""
    confirmadas = [
        v
        for v in db.query(Venda)
        .filter(
            Venda.loja_slug == loja_slug,
            Venda.vendedor_email == vendedor_email,
            Venda.status == "confirmada",
        )
        .all()
        if d_inicio <= _data(v.criada_em) <= d_fim
    ]
    faturamento = sum((v.preco_venda for v in confirmadas), Decimal("0"))
    lucros_conhecidos = [
        valor for venda in confirmadas if (valor := lucro_bruto_venda(venda)) is not None
    ]
    lucro = sum(lucros_conhecidos, Decimal("0"))
    vendas_lucro_incompleto = len(confirmadas) - len(lucros_conhecidos)
    return {
        "confirmadas": confirmadas,
        "quantidade": len(confirmadas),
        "faturamento": faturamento,
        "lucro_bruto": lucro,
        "lucro_completo": vendas_lucro_incompleto == 0,
        "vendas_lucro_incompleto": vendas_lucro_incompleto,
    }


def _metas_vendedor(
    db: Session,
    loja_slug: str,
    vendedor_email: str,
    d_inicio: date,
    d_fim: date,
    realizado_por_tipo: dict[str, Decimal],
    lucro_completo: bool,
    *,
    pode_ver_margem: bool,
) -> list[dict[str, Any]]:
    metas_view: list[dict[str, Any]] = []
    metas = (
        db.query(Meta)
        .filter(
            Meta.loja_slug == loja_slug,
            Meta.escopo == "vendedor",
            Meta.vendedor_email == vendedor_email,
            Meta.ativa.is_(True),
        )
        .all()
    )
    for meta in metas:
        if meta.tipo == "lucro_bruto" and not pode_ver_margem:
            continue
        if meta.tipo not in realizado_por_tipo or not (
            meta.periodo_inicio <= d_fim and meta.periodo_fim >= d_inicio
        ):
            continue
        realizado = realizado_por_tipo[meta.tipo]
        indisponivel = meta.tipo == "lucro_bruto" and not lucro_completo
        pct = (
            round(float(realizado / meta.valor_alvo * 100), 1)
            if meta.valor_alvo and not indisponivel
            else 0.0
        )
        metas_view.append(
            {
                "tipo": meta.tipo,
                "alvo": meta.valor_alvo,
                "realizado": realizado,
                "pct": pct,
                "pct_barra": min(pct, 100),
                "quantidade": meta.tipo == "quantidade",
                "indisponivel": indisponivel,
            }
        )
    return metas_view


def _aquisicao_de_totais(
    totais: Mapping[str, Any],
    *,
    fonte: str,
    chatbot_offline: bool = False,
    api_falhou: bool = False,
) -> AquisicaoResumo:
    """Normaliza totais de ROI/API em resumo comercial seguro.

    - gasto ausente ou <= 0 → investimento e ROAS indisponíveis (nunca infinito).
    - não força investimento 0 quando a fonte falhou.
    """
    gasto_raw = totais.get("gasto")
    try:
        gasto = Decimal(str(gasto_raw)) if gasto_raw is not None else None
    except Exception:
        gasto = None

    leads = totais.get("leads")
    try:
        leads_n = int(leads) if leads is not None else None
    except (TypeError, ValueError):
        leads_n = None

    vendas = totais.get("vendas")
    try:
        vendas_n = int(vendas) if vendas is not None else None
    except (TypeError, ValueError):
        vendas_n = None

    fat_raw = totais.get("faturamento")
    try:
        faturamento = Decimal(str(fat_raw)) if fat_raw is not None else None
    except Exception:
        faturamento = None

    invest_ok = gasto is not None and gasto > 0
    # CPA/CAC: só com investimento real e vendas > 0
    cac: Decimal | None = None
    cac_ok = False
    if invest_ok and vendas_n and vendas_n > 0:
        cac_raw = totais.get("cpa")
        if cac_raw is not None:
            try:
                cac = Decimal(str(cac_raw)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
                cac_ok = True
            except Exception:
                cac = (gasto / Decimal(vendas_n)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
                cac_ok = True
        else:
            cac = (gasto / Decimal(vendas_n)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
            cac_ok = True

    roas: Decimal | None = None
    roas_ok = False
    if invest_ok and faturamento is not None:
        roas_raw = totais.get("roas")
        if roas_raw is not None:
            try:
                roas = Decimal(str(roas_raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                roas_ok = True
            except Exception:
                roas = (faturamento / gasto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                roas_ok = True
        else:
            roas = (faturamento / gasto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            roas_ok = True

    if api_falhou:
        status = "parcial"
        mensagem = "Aquisição parcial: fonte de mídia indisponível no momento."
    elif not invest_ok:
        status = "indisponivel" if gasto is None else "parcial"
        mensagem = (
            "Investimento e ROAS indisponíveis sem gasto de mídia no período."
            if not invest_ok
            else None
        )
        if gasto is not None and gasto <= 0:
            status = "indisponivel"
            mensagem = "Sem investimento no período — ROAS indisponível."
    elif chatbot_offline:
        status = "parcial"
        mensagem = "Contagem de leads de mídia pode estar incompleta."
    else:
        status = "ok"
        mensagem = None

    return AquisicaoResumo(
        status=status,
        investimento=gasto if invest_ok else None,
        investimento_disponivel=invest_ok,
        cac=cac if cac_ok else None,
        cac_disponivel=cac_ok,
        roas=roas if roas_ok else None,
        roas_disponivel=roas_ok,
        leads=leads_n if not chatbot_offline else None,
        vendas_atribuidas=vendas_n,
        faturamento_atribuido=faturamento,
        google_status="indisponivel",
        fonte=fonte,
        mensagem=mensagem,
    )


def _carregar_aquisicao(
    db: Session,
    *,
    loja_slug: str,
    d_inicio: date,
    d_fim: date,
    confirmadas: list[Venda],
    chatbot: Any | None,
    fetch_resultados_api: Callable[..., dict | None] | None,
    revy_trafego_resultados_enabled: bool,
) -> tuple[AquisicaoResumo, list[dict], list[dict]]:
    """Tenta API (Control/Revy Tráfego); fallback local; nunca zera gasto ausente.

    Devolve também o detalhe por campanha e por canal quando a API responde — é
    ela que conhece o gasto real por campanha.
    """
    chatbot_offline = False
    api_payload = None
    if revy_trafego_resultados_enabled and fetch_resultados_api is not None:
        try:
            # Janela explícita: gasto e receita têm que sair do MESMO período, senão
            # o ROAS divide receita filtrada por gasto de outra janela.
            api_payload = fetch_resultados_api(
                loja_slug=loja_slug,
                inicio=d_inicio.isoformat(),
                fim=d_fim.isoformat(),
                modo="last",
            )
        except Exception:
            api_payload = None

    if api_payload is not None:
        resumo = resumo_from_api(api_payload)
        periodo_api = api_payload.get("periodo") or {}
        chatbot_offline = bool(periodo_api.get("chatbot_offline"))
        # Do payload cru: resumo_from_api monta só os totais e os canais, e
        # descarta a lista de campanhas — que é justamente o detalhe procurado.
        campanhas, canais = _linhas_midia_da_api(api_payload)
        return (
            _aquisicao_de_totais(
                resumo.get("totais") or {},
                fonte="api",
                chatbot_offline=chatbot_offline,
            ),
            campanhas,
            canais,
        )

    if revy_trafego_resultados_enabled and fetch_resultados_api is not None:
        # Flag ligada mas API falhou → parcial; ainda tenta local como fallback de números.
        api_falhou = True
    else:
        api_falhou = False

    from app.models import Campanha, CampanhaGasto

    campanhas = db.query(Campanha).filter(Campanha.loja_slug == loja_slug).all()
    gastos = db.query(CampanhaGasto).filter(CampanhaGasto.loja_slug == loja_slug).all()
    leads: list[dict] = []
    if chatbot is not None:
        try:
            leads = chatbot.listar_leads()
        except Exception:
            chatbot_offline = True
    linhas = calcular_roi_loja(
        campanhas=campanhas,
        gastos=gastos,
        leads=leads,
        vendas_confirmadas=confirmadas,
        d_inicio=d_inicio,
        d_fim=d_fim,
        modo_atribuicao="last",
    )
    if not any(l.campanha_id is not None for l in linhas):
        if api_falhou:
            return (
                AquisicaoResumo(
                    status="parcial",
                    google_status="indisponivel",
                    fonte=None,
                    mensagem="Aquisição parcial: fonte de mídia indisponível e sem campanhas locais.",
                ),
                [],
                [],
            )
        return (
            AquisicaoResumo(
                status="indisponivel",
                google_status="indisponivel",
                fonte=None,
                mensagem="Sem dados de aquisição no período.",
            ),
            [],
            [],
        )

    totais = totais_roi(linhas)
    # resumo_periodo é usado só para garantir paridade com dashboard; totais_roi é a fonte.
    _ = resumo_periodo(linhas)
    # Fallback local não publica detalhe por campanha: sem o gasto que a API
    # conhece, a linha por campanha enganaria mais do que informaria.
    return (
        _aquisicao_de_totais(
            totais,
            fonte="local",
            chatbot_offline=chatbot_offline,
            api_falhou=api_falhou,
        ),
        [],
        [],
    )


def pendencias_bancos_nao_configurados(
    nomes_faltando: list[str] | tuple[str, ...] | None,
) -> list[PendenciaAcao]:
    """Pendência operacional: bancos sem credencial (F5). Não bloqueia Vendas."""
    if not nomes_faltando:
        return []
    nomes = [str(n).strip() for n in nomes_faltando if str(n).strip()]
    if not nomes:
        return []
    n = len(nomes)
    if n == 1:
        texto = f"Banco {nomes[0]} ainda não configurado"
    elif n <= 3:
        texto = f"Bancos sem acesso: {', '.join(nomes)}"
    else:
        texto = f"{n} bancos ainda sem acesso configurado"
    return [
        PendenciaAcao(
            codigo="bancos_nao_configurados",
            texto=texto,
            href="/app/financeiras",
            quantidade=n,
        )
    ]


def _pendencias(
    db: Session,
    *,
    loja_slug: str,
    d_inicio: date,
    d_fim: date,
    vendedor_email: str | None,
    chatbot: Any | None,
    escopo: str,
    bancos_nao_configurados: list[str] | None = None,
) -> list[PendenciaAcao]:
    itens: list[PendenciaAcao] = []

    q_vendas = db.query(Venda).filter(
        Venda.loja_slug == loja_slug,
        Venda.status == "registrada",
    )
    if vendedor_email:
        q_vendas = q_vendas.filter(Venda.vendedor_email == vendedor_email)
    rascunhos = [
        v for v in q_vendas.all() if d_inicio <= _data(v.criada_em) <= d_fim
    ]
    if rascunhos:
        href = "/app/vendas" if escopo == "loja" else "/app/vendedor"
        n = len(rascunhos)
        itens.append(
            PendenciaAcao(
                codigo="vendas_registradas",
                texto=(
                    f"{n} venda{'s' if n != 1 else ''} registrada"
                    f"{'s' if n != 1 else ''} aguardando confirmação"
                ),
                href=href,
                quantidade=n,
            )
        )

    if escopo == "loja" and bancos_nao_configurados:
        itens.extend(pendencias_bancos_nao_configurados(bancos_nao_configurados))

    if chatbot is None:
        return itens[:8]

    try:
        leads = chatbot.listar_leads()
    except Exception:
        return itens[:8]

    sem_etapa = [
        lead
        for lead in leads
        if not str(lead.get("etapa") or "").strip()
    ]
    if escopo == "loja" and sem_etapa:
        n = len(sem_etapa)
        itens.append(
            PendenciaAcao(
                codigo="leads_sem_etapa",
                texto=f"{n} lead{'s' if n != 1 else ''} sem etapa no funil",
                href="/app/leads",
                quantidade=n,
            )
        )

    novos = [lead for lead in leads if str(lead.get("etapa") or "").casefold() == "novo"]
    if novos and escopo == "loja":
        n = len(novos)
        itens.append(
            PendenciaAcao(
                codigo="leads_novos",
                texto=f"{n} lead{'s' if n != 1 else ''} novo{'s' if n != 1 else ''} aguardando atendimento",
                href="/app/leads",
                quantidade=n,
            )
        )

    return itens[:8]


def build_sales_overview(
    db: Session,
    *,
    loja_slug: str,
    papel: str,
    vendedor_email: str | None = None,
    inicio: str | date | None = None,
    fim: str | date | None = None,
    chatbot: Any | None = None,
    fetch_resultados_api: Callable[..., dict | None] | None = None,
    revy_trafego_resultados_enabled: bool | None = None,
    pode_ver_margem: bool | None = None,
    bancos_nao_configurados: list[str] | None = None,
) -> SalesOverview:
    """Monta o read model da Visão geral de Vendas.

    ``papel`` controla escopo: dono/gerente veem a loja; vendedor só as próprias métricas.
    Integrações externas (chatbot, API de aquisição) degradam blocos sem derrubar vendas.
    """
    papel_n = (papel or "").strip().casefold()
    if papel_n not in PAPEIS_AUTORIZADOS:
        return SalesOverview(
            status="erro",
            periodo_inicio=periodo_padrao(None, None)[0],
            periodo_fim=periodo_padrao(None, None)[1],
            timezone=settings.timezone,
            escopo="loja",
            mensagem="Papel não autorizado para a visão comercial.",
        )

    ini_s = inicio.isoformat() if isinstance(inicio, date) else inicio
    fim_s = fim.isoformat() if isinstance(fim, date) else fim
    d_inicio, d_fim = periodo_padrao(ini_s, fim_s)
    tz_nome = settings.timezone
    escopo = "vendedor" if papel_n in PAPEIS_VENDEDOR else "loja"
    email_filtro = (vendedor_email or "").strip().lower() or None
    if escopo == "vendedor" and not email_filtro:
        return SalesOverview(
            status="erro",
            periodo_inicio=d_inicio,
            periodo_fim=d_fim,
            timezone=tz_nome,
            escopo="vendedor",
            mensagem="Vendedor sem e-mail de sessão.",
        )

    ver_margem = (
        pode_ver_margem
        if pode_ver_margem is not None
        else papel_n in PAPEIS_VISAO_COMPLETA
    )
    flag_api = (
        settings.revy_trafego_resultados_enabled
        if revy_trafego_resultados_enabled is None
        else revy_trafego_resultados_enabled
    )

    # --- Vendas ---
    if escopo == "vendedor":
        resultado = _metricas_vendedor(db, loja_slug, email_filtro, d_inicio, d_fim)
    else:
        resultado = calcular_metricas_vendas(db, loja_slug, d_inicio, d_fim)

    confirmadas = resultado["confirmadas"]
    qtd = resultado["quantidade"]
    receita = resultado["faturamento"]
    margem = resultado["lucro_bruto"] if ver_margem else None
    margem_completa = resultado["lucro_completo"]
    vendas_lucro_incompleto = resultado["vendas_lucro_incompleto"]

    if qtd == 0:
        vendas_status = "vazio"
    elif ver_margem and not margem_completa:
        vendas_status = "parcial"
    else:
        vendas_status = "ok"

    realizado_por_tipo = {
        "quantidade": Decimal(qtd),
        "faturamento": receita,
        "lucro_bruto": resultado["lucro_bruto"],
    }

    # --- Metas ---
    if escopo == "vendedor":
        metas = _metas_vendedor(
            db,
            loja_slug,
            email_filtro,
            d_inicio,
            d_fim,
            realizado_por_tipo,
            margem_completa,
            pode_ver_margem=ver_margem,
        )
    else:
        metas = metas_view_periodo(
            db, loja_slug, d_inicio, d_fim, realizado_por_tipo, margem_completa
        )
    metas_status = "ok" if metas else "vazio"

    # --- Funil / leads ---
    funil_view: dict[str, Any] | None = None
    funil_status = "indisponivel"
    leads_count: int | None = None

    if escopo == "loja":
        inicio_dt, fim_dt = _periodo_datetime(d_inicio, d_fim)
        try:
            funil_eventos = resumo_funil(
                db, loja_slug=loja_slug, inicio=inicio_dt, fim=fim_dt
            )
            leads_count = funil_eventos.get("total_leads")
            funil_view = {
                "total_leads": funil_eventos.get("total_leads"),
                "etapas": funil_eventos.get("etapas"),
                "taxa_resposta_pct": (
                    str(funil_eventos["taxa_resposta_pct"])
                    if funil_eventos.get("taxa_resposta_pct") is not None
                    else None
                ),
                "taxa_conversao_pct": (
                    str(funil_eventos["taxa_conversao_pct"])
                    if funil_eventos.get("taxa_conversao_pct") is not None
                    else None
                ),
                "tempo_mediano_primeira_resposta_segundos": funil_eventos.get(
                    "tempo_mediano_primeira_resposta_segundos"
                ),
            }
            funil_status = "ok" if (leads_count or 0) > 0 else "vazio"
        except Exception:
            funil_status = "erro"
            funil_view = None

        # Funil auditável (leads elegíveis → atendidos → vendas) via chatbot
        if chatbot is not None:
            try:
                funil_audit, _, _ = funil_periodo(
                    chatbot,
                    db,
                    loja_slug,
                    d_inicio,
                    d_fim,
                    None,
                    None,
                    confirmadas,
                )
                if funil_view is None:
                    funil_view = {}
                funil_view["auditavel"] = funil_audit
                if funil_audit.get("disponivel") and leads_count is None:
                    leads_count = funil_audit.get("elegiveis")
                if funil_status == "erro" and funil_audit.get("disponivel"):
                    funil_status = "parcial"
            except Exception:
                if funil_status == "ok":
                    funil_status = "parcial"
    else:
        # Vendedor: leads atribuídos (se chatbot disponível)
        if chatbot is not None:
            try:
                from app.financeiro_calc import identidade_telefone
                from app.models import AtendimentoAtribuicao

                atribuicoes = (
                    db.query(AtendimentoAtribuicao)
                    .filter(
                        AtendimentoAtribuicao.loja_slug == loja_slug,
                        AtendimentoAtribuicao.vendedor_email == email_filtro,
                        AtendimentoAtribuicao.ativa.is_(True),
                    )
                    .all()
                )
                hashes = {a.telefone_hmac for a in atribuicoes}
                leads = chatbot.listar_leads()
                meus = [
                    lead
                    for lead in leads
                    if identidade_telefone(lead.get("telefone")) in hashes
                ]
                leads_count = len(meus)
                funil_status = "ok" if leads_count else "vazio"
                funil_view = {"leads_atribuidos": leads_count}
            except Exception:
                funil_status = "parcial"
                funil_view = None

    # --- Aquisição (somente visão completa) ---
    aquisicao: AquisicaoResumo | None = None
    aquisicao_status = "indisponivel"
    aquisicao_campanhas: list[dict[str, Any]] = []
    aquisicao_canais: list[dict[str, Any]] = []
    if escopo == "loja":
        try:
            aquisicao, aquisicao_campanhas, aquisicao_canais = _carregar_aquisicao(
                db,
                loja_slug=loja_slug,
                d_inicio=d_inicio,
                d_fim=d_fim,
                confirmadas=confirmadas,
                chatbot=chatbot,
                fetch_resultados_api=fetch_resultados_api,
                revy_trafego_resultados_enabled=flag_api,
            )
            aquisicao_status = aquisicao.status
        except Exception:
            aquisicao = AquisicaoResumo(
                status="parcial",
                google_status="indisponivel",
                mensagem="Não foi possível carregar aquisição.",
            )
            aquisicao_status = "parcial"
            aquisicao_campanhas = []
            aquisicao_canais = []

    # --- Pendências ---
    pendencias = _pendencias(
        db,
        loja_slug=loja_slug,
        d_inicio=d_inicio,
        d_fim=d_fim,
        vendedor_email=email_filtro if escopo == "vendedor" else None,
        chatbot=chatbot,
        escopo=escopo,
        bancos_nao_configurados=(
            bancos_nao_configurados if escopo == "loja" else None
        ),
    )

    # --- Status global ---
    blocos = [vendas_status, metas_status, funil_status]
    if escopo == "loja":
        blocos.append(aquisicao_status)

    if vendas_status == "erro":
        status = "erro"
    elif all(b in {"vazio", "indisponivel"} for b in blocos):
        status = "vazio"
    elif any(b in {"parcial", "erro"} for b in blocos) or aquisicao_status == "parcial":
        status = "parcial" if vendas_status in {"ok", "parcial", "vazio"} else "erro"
    elif qtd == 0 and funil_status in {"vazio", "indisponivel"}:
        status = "vazio"
    else:
        status = "ok"

    # Se vendas ok mas aquisição parcial, overview fica parcial (sem derrubar vendas).
    if vendas_status in {"ok", "vazio"} and aquisicao_status == "parcial":
        status = "parcial" if qtd > 0 or funil_status == "ok" else status

    return SalesOverview(
        status=status,
        periodo_inicio=d_inicio,
        periodo_fim=d_fim,
        timezone=tz_nome,
        escopo=escopo,
        vendedor_email=email_filtro if escopo == "vendedor" else None,
        receita=receita,
        margem=margem,
        margem_completa=margem_completa if ver_margem else True,
        vendas_lucro_incompleto=vendas_lucro_incompleto if ver_margem else 0,
        qtd_vendas=qtd,
        vendas_status=vendas_status,
        metas=metas,
        metas_status=metas_status,
        leads_count=leads_count,
        funil=funil_view,
        funil_status=funil_status,
        aquisicao=aquisicao,
        aquisicao_status=aquisicao_status,
        aquisicao_campanhas=aquisicao_campanhas,
        aquisicao_canais=aquisicao_canais,
        pendencias=pendencias,
    )


def aquisicao_sem_investimento(
    faturamento: Decimal = Decimal("0"),
    gasto: Decimal | None = None,
) -> AquisicaoResumo:
    """Helper de teste/contrato: ROAS sem investimento → indisponível."""
    return _aquisicao_de_totais(
        {
            "gasto": gasto if gasto is not None else None,
            "faturamento": faturamento,
            "leads": 0,
            "vendas": 0,
            "cpa": None,
            "roas": None,
        },
        fonte="local",
    )
