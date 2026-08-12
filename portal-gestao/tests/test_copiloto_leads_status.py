from datetime import date, datetime, timedelta, timezone

from app.clients.chatbot import ChatbotIndisponivel
from app.loja.copiloto.consultas_leads import escopo_chatbot_confiavel, leads_status
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


class ChatbotQuebrado:
    """Payload malformado: nem ChatbotIndisponivel, nem sucesso — bug real."""

    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        raise KeyError("ultima_mensagem")


def test_excecao_inesperada_no_chatbot_degrada_e_loga_warning(caplog):
    with caplog.at_level("WARNING", logger="app.loja.copiloto.consultas_leads"):
        r = leads_status(_overview(), ChatbotQuebrado(), ctx=_ctx(), agora=AGORA)

    # Degrada exatamente como o caso "esperado" (nunca zero inventado)...
    assert r.sem_resposta is None
    assert r.sem_resposta_status == "indisponivel"
    # ...mas, ao contrário do offline conhecido, o defeito real não fica mudo.
    avisos = [rec for rec in caplog.records if rec.levelname == "WARNING"]
    assert len(avisos) == 1
    assert "loja-teste" in avisos[0].getMessage()


def test_funil_com_erro_nao_vira_zero_leads():
    r = leads_status(
        _overview(funil=None, funil_status="erro"),
        ChatbotStub([]),
        ctx=_ctx(),
        agora=AGORA,
    )
    assert r.total_leads is None
    assert r.status in {"parcial", "erro"}


def test_funil_vazio_com_fontes_ok_vira_status_vazio():
    """Zero leads de verdade (funil_status='vazio') não é a mesma coisa que
    "está tudo bem" — mas também não é degradação. Mesmo vocabulário das
    outras consultas (estoque_parado, vendas_resumo): vazio é vazio."""
    r = leads_status(
        _overview(
            funil={
                "total_leads": 0,
                "taxa_resposta_pct": None,
                "tempo_mediano_primeira_resposta_segundos": None,
            },
            funil_status="vazio",
        ),
        ChatbotStub([]),
        ctx=_ctx(),
        agora=AGORA,
    )
    assert r.total_leads == 0
    assert r.status == "vazio"


def test_funil_parcial_com_chatbot_saudavel_vira_status_parcial():
    """I1: funil_status="parcial" é INPUT para um modelo instruído (REGRAS[7])
    a avisar quando um dado vier parcial. Devolver STATUS_OK aqui faria um
    modelo bem-comportado não qualificar um número que devia vir com
    ressalva — mesmo com o chatbot saudável."""
    r = leads_status(
        _overview(
            funil={
                "total_leads": 40,
                "taxa_resposta_pct": "62.0",
                "tempo_mediano_primeira_resposta_segundos": 300,
            },
            funil_status="parcial",
        ),
        ChatbotStub([]),
        ctx=_ctx(),
        agora=AGORA,
    )
    assert r.status == "parcial"
    # Os dados continuam repassados — "parcial" é status, não apagão de dado.
    assert r.total_leads == 40


# --- I5: leads_status é a única consulta sem escopo de loja. ChatbotClient
# não tem hook de escopo (nem parâmetro de loja em listar_conversas, nem
# endpoint de identidade como EstoqueClient.obter_loja()) — ver docstring de
# consultas_leads.py. O guard compara a sessão contra uma declaração opt-in
# de config (settings.chatbot_loja_slug / CHATBOT_API_LOJA_SLUG).


def test_escopo_confiavel_por_padrao_sem_declaracao():
    """Hoje (deploy de uma loja só): ninguém configura CHATBOT_API_LOJA_SLUG,
    então o guard confia — comportamento idêntico ao pré-fix."""
    assert escopo_chatbot_confiavel(_ctx(), loja_declarada="") is True
    assert escopo_chatbot_confiavel(_ctx(), loja_declarada=None) is True


def test_escopo_confiavel_quando_declaracao_bate_com_sessao():
    assert escopo_chatbot_confiavel(_ctx(), loja_declarada="loja-teste") is True
    assert escopo_chatbot_confiavel(_ctx(), loja_declarada="LOJA-TESTE") is True


def test_escopo_nao_confiavel_quando_declaracao_diverge():
    """O dia em que duas lojas compartilharem um deploy do chatbot: a
    declaração aponta para outra loja que não a da sessão."""
    assert escopo_chatbot_confiavel(_ctx(), loja_declarada="loja-outra") is False


class ChatbotEspiao:
    """Devolveria a contagem de uma loja ESTRANHA — prova que o guard barra
    ANTES de chamar o chatbot, não descarta o resultado depois de já ter
    vazado o dado para o processo."""

    def __init__(self):
        self.chamado = False

    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        self.chamado = True
        return [_conversa(bot_ativo=False, direcao="entrada", horas=99)]


def test_leads_status_degrada_sem_chamar_chatbot_quando_declaracao_diverge():
    espiao = ChatbotEspiao()

    r = leads_status(
        _overview(), espiao, ctx=_ctx(), agora=AGORA, chatbot_loja_slug="loja-outra"
    )

    assert espiao.chamado is False
    assert r.sem_resposta is None
    assert r.sem_resposta_status == "indisponivel"


def test_leads_status_deploy_de_uma_loja_so_continua_igual():
    """Constraint dura do fix: CHATBOT_API_LOJA_SLUG não configurado (o
    default, hoje) não pode virar "indisponivel" permanente — o dado real
    tem que continuar fluindo exatamente como antes do fix."""
    conversas = [_conversa(bot_ativo=False, direcao="entrada", horas=6)]

    r = leads_status(
        _overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA,
        chatbot_loja_slug="",
    )

    assert r.sem_resposta == 1
    assert r.sem_resposta_status == "ok"


def test_leads_status_usa_settings_quando_chatbot_loja_slug_nao_e_passado():
    """Sem injetar o parâmetro (o caminho real de produção), o guard lê de
    settings.chatbot_loja_slug — que é "" por padrão (dev/test), então o
    comportamento é o mesmo de hoje."""
    conversas = [_conversa(bot_ativo=False, direcao="entrada", horas=6)]

    r = leads_status(_overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA)

    assert r.sem_resposta == 1
    assert r.sem_resposta_status == "ok"


def test_funil_e_sem_resposta_indisponiveis_vira_status_indisponivel():
    """As duas fontes fora do ar ao mesmo tempo: nada de "parcial" — não há
    nenhum dado confiável para mostrar, então o status tem que dizer isso."""
    r = leads_status(
        _overview(funil=None, funil_status="indisponivel"),
        ChatbotStub([], indisponivel=True),
        ctx=_ctx(),
        agora=AGORA,
    )
    assert r.sem_resposta is None
    assert r.sem_resposta_status == "indisponivel"
    assert r.status == "indisponivel"
