from datetime import date, datetime, timedelta, timezone

from app.clients.chatbot import ChatbotIndisponivel
from app.loja.copiloto.consultas_leads import leads_status
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.sales_overview import SalesOverview

AGORA = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


def _overview(funil=None, funil_status="ok"):
    return SalesOverview(
        status="ok",
        periodo_inicio=date(2026, 8, 1),
        periodo_fim=date(2026, 8, 31),
        timezone="America/Sao_Paulo",
        escopo="loja",
        funil=funil,
        funil_status=funil_status,
    )


class ChatbotStub:
    def __init__(self, conversas, indisponivel=False):
        self.conversas = conversas
        self.indisponivel = indisponivel

    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("chatbot fora")
        return list(self.conversas)


def _conversa(*, bot_ativo, direcao, horas):
    return {
        "telefone": "5511987654321",
        "bot_ativo": bot_ativo,
        "status": "aberta" if bot_ativo else "handoff",
        "ultima_mensagem": {
            "texto": "e aí, tem?",
            "direcao": direcao,
            "criada_em": (AGORA - timedelta(hours=horas)).isoformat(),
        },
    }


def test_repassa_metricas_do_funil():
    overview = _overview(
        funil={
            "total_leads": 40,
            "taxa_resposta_pct": "82.5",
            "tempo_mediano_primeira_resposta_segundos": 320,
        }
    )
    r = leads_status(overview, ChatbotStub([]), ctx=_ctx(), agora=AGORA)
    assert r.status == "ok"
    assert r.total_leads == 40
    assert r.taxa_resposta_pct == "82.5"
    assert r.tempo_mediano_primeira_resposta_segundos == 320


def test_conta_conversa_em_handoff_esperando_ha_horas():
    conversas = [
        _conversa(bot_ativo=False, direcao="entrada", horas=6),
        _conversa(bot_ativo=False, direcao="entrada", horas=1),
    ]
    r = leads_status(
        _overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA,
        horas_sem_resposta=4,
    )
    assert r.sem_resposta == 1
    assert r.sem_resposta_status == "ok"


def test_bot_ligado_nao_e_lead_abandonado():
    conversas = [_conversa(bot_ativo=True, direcao="entrada", horas=10)]
    r = leads_status(_overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA)
    assert r.sem_resposta == 0


def test_ultima_mensagem_da_loja_nao_conta():
    conversas = [_conversa(bot_ativo=False, direcao="saida", horas=10)]
    r = leads_status(_overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA)
    assert r.sem_resposta == 0


def test_conversa_sem_ultima_mensagem_nao_conta():
    conversas = [{"telefone": "5511999", "bot_ativo": False, "ultima_mensagem": None}]
    r = leads_status(_overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA)
    assert r.sem_resposta == 0


def test_chatbot_fora_do_ar_marca_indisponivel_nao_zero():
    r = leads_status(
        _overview(), ChatbotStub([], indisponivel=True), ctx=_ctx(), agora=AGORA
    )
    assert r.sem_resposta is None
    assert r.sem_resposta_status == "indisponivel"


def test_funil_com_erro_nao_vira_zero_leads():
    r = leads_status(
        _overview(funil=None, funil_status="erro"),
        ChatbotStub([]),
        ctx=_ctx(),
        agora=AGORA,
    )
    assert r.total_leads is None
    assert r.status in {"parcial", "erro"}
