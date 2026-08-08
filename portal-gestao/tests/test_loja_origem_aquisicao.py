"""Task 9 — "Por onde as pessoas chegam" no painel de aquisição da Loja.

Agrupa por `ctwa_source_type` (dado cru da Meta, correto) e não por `origem`
(errada em 10 leads e sem backfill). O bloco tem guard próprio: a fonte dele é
o lead do Chatbot, não o gasto da Meta.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from conftest import login
from app.db import SessionLocal
from app.loja.sales_overview import (
    build_sales_overview,
    classificar_origem_lead,
    resumir_origens,
)

JANELA = (date(2026, 8, 1), date(2026, 8, 31))


def _lead(**campos):
    base = {"id": campos.pop("id", "l1"), "criada_em": "2026-08-05T12:00:00+00:00"}
    base.update(campos)
    return base


class ChatbotStub:
    def __init__(self, leads=None, indisponivel=False):
        self.leads = leads if leads is not None else []
        self.indisponivel = indisponivel

    def listar_leads(self, etapa=None):
        if self.indisponivel:
            from app.clients.chatbot import ChatbotIndisponivel

            raise ChatbotIndisponivel("chatbot offline")
        return self.leads


# ---------------------------------------------------------------------------
# classificar_origem_lead
# ---------------------------------------------------------------------------


def test_classifica_fb_ads_como_anuncio():
    """O valor real em produção é `FB_Ads`; comparação sensível a caixa erra 205 leads."""
    for source in ("FB_Ads", "fb_ads", "ctwa_ad", "ad"):
        chave, _ = classificar_origem_lead(_lead(ctwa_source_type=source))
        assert chave == "anuncio", source


def test_link_direto_e_busca_nao_entram_em_anuncio():
    for source in ("click_to_chat_link", "message_short_link"):
        chave, rotulo = classificar_origem_lead(_lead(ctwa_source_type=source))
        assert chave == "link_direto", source
        assert rotulo == "Link direto"

    chave, rotulo = classificar_origem_lead(
        _lead(ctwa_source_type="global_search_new_chat")
    )
    assert chave == "busca_whatsapp"
    assert rotulo == "Procurou no WhatsApp"


def test_source_type_desconhecido_vai_para_outro():
    chave, rotulo = classificar_origem_lead(_lead(ctwa_source_type="algo_novo_da_meta"))
    assert chave == "outro"
    assert rotulo == "Outro (WhatsApp)"


def test_sem_source_type_usa_origem():
    assert classificar_origem_lead(_lead(origem="catalogo"))[0] == "catalogo"
    # origem=meta_ctwa sem source_type veio de identificador de anúncio: é anúncio.
    assert classificar_origem_lead(_lead(origem="meta_ctwa"))[0] == "anuncio"


def test_sem_nada_e_nao_identificado():
    chave, rotulo = classificar_origem_lead(_lead())
    assert chave == "nao_identificado"
    assert rotulo == "Não identificado"


def test_source_type_vence_origem_errada():
    """Os 10 leads carimbados meta_ctwa por engano caem no balde certo."""
    lead = _lead(ctwa_source_type="global_search_new_chat", origem="meta_ctwa")
    assert classificar_origem_lead(lead)[0] == "busca_whatsapp"


# ---------------------------------------------------------------------------
# resumir_origens
# ---------------------------------------------------------------------------


def test_lead_fora_do_periodo_nao_conta():
    linhas = resumir_origens(
        [
            _lead(id="dentro", ctwa_source_type="FB_Ads"),
            _lead(id="fora", ctwa_source_type="FB_Ads", criada_em="2026-07-05T12:00:00+00:00"),
        ],
        *JANELA,
    )
    assert [l["chave"] for l in linhas] == ["anuncio"]
    assert linhas[0]["leads"] == 1


def test_lead_sem_criada_em_fica_de_fora():
    """Não pode virar "Não identificado": o balde incharia com lead antigo."""
    linhas = resumir_origens(
        [
            _lead(id="ok", ctwa_source_type="FB_Ads"),
            {"id": "sem-data", "ctwa_source_type": "click_to_chat_link"},
        ],
        *JANELA,
    )
    assert [l["chave"] for l in linhas] == ["anuncio"]
    assert sum(l["leads"] for l in linhas) == 1


def test_nota_conta_anuncios_sem_identificacao():
    """Explica na tela por que a soma das campanhas não bate com "Anúncio"."""
    linhas = resumir_origens(
        [
            _lead(id="a", ctwa_source_type="FB_Ads", meta_ad_id="1202496"),
            _lead(id="b", ctwa_source_type="FB_Ads", ctwa_clid="ARAclick"),
            _lead(id="c", ctwa_source_type="ctwa_ad"),  # cego: nenhum identificador
        ],
        *JANELA,
    )
    anuncio = next(l for l in linhas if l["chave"] == "anuncio")
    assert anuncio["leads"] == 3
    assert anuncio["nota"] == "1 sem identificação de campanha"

    outros = [l for l in linhas if l["chave"] != "anuncio"]
    assert all(l["nota"] is None for l in outros)


def test_nota_ausente_quando_todos_tem_identificacao():
    linhas = resumir_origens(
        [_lead(id="a", ctwa_source_type="FB_Ads", meta_campaign_id="1202496")], *JANELA
    )
    assert linhas[0]["nota"] is None


def test_share_soma_100_no_periodo():
    leads = [
        _lead(id="a", ctwa_source_type="FB_Ads"),
        _lead(id="b", ctwa_source_type="click_to_chat_link"),
        _lead(id="c", ctwa_source_type="global_search_new_chat"),
    ]
    linhas = resumir_origens(leads, *JANELA)
    assert sum(l["share"] for l in linhas) == Decimal("100.0")
    assert all(l["leads"] == 1 for l in linhas)


def test_ordena_por_volume_decrescente():
    leads = [
        _lead(id="a", ctwa_source_type="click_to_chat_link"),
        _lead(id="b", ctwa_source_type="FB_Ads"),
        _lead(id="c", ctwa_source_type="FB_Ads"),
        _lead(id="d", ctwa_source_type="FB_Ads"),
    ]
    linhas = resumir_origens(leads, *JANELA)
    assert [l["chave"] for l in linhas] == ["anuncio", "link_direto"]
    assert linhas[0]["leads"] == 3
    assert linhas[0]["share"] == Decimal("75.0")


def test_sem_leads_devolve_lista_vazia():
    assert resumir_origens([], *JANELA) == []


# ---------------------------------------------------------------------------
# Integração com o overview
# ---------------------------------------------------------------------------


def test_overview_publica_origens_sem_depender_da_api_de_midia():
    """Guard próprio: sem fonte de mídia o bloco continua respondível."""
    overview = build_sales_overview(
        SessionLocal(),
        loja_slug="loja-teste",
        papel="dono",
        inicio="2026-08-01",
        fim="2026-08-31",
        chatbot=ChatbotStub(
            [
                _lead(id="a", ctwa_source_type="FB_Ads", meta_ad_id="1202496"),
                _lead(id="b", ctwa_source_type="click_to_chat_link"),
            ]
        ),
        revy_trafego_resultados_enabled=False,
    )
    assert overview.aquisicao_campanhas == []
    assert [l["chave"] for l in overview.aquisicao_origens] == ["anuncio", "link_direto"]
    assert overview.to_dict()["aquisicao_origens"][0]["share"] == "50.0"


def test_chatbot_offline_devolve_lista_vazia():
    overview = build_sales_overview(
        SessionLocal(),
        loja_slug="loja-teste",
        papel="dono",
        inicio="2026-08-01",
        fim="2026-08-31",
        chatbot=ChatbotStub(indisponivel=True),
        revy_trafego_resultados_enabled=False,
    )
    assert overview.aquisicao_origens == []


def test_tela_renderiza_o_bloco_sem_fonte_de_midia(client, chatbot_fake, monkeypatch):
    """Render real com a API de mídia DESLIGADA: o guard próprio é o que se prova.

    Sem ele o bloco herdaria `{% if overview.aquisicao_campanhas %}` e sumiria
    exatamente quando o lojista mais quer saber por onde entrou gente.
    """
    from datetime import datetime, timezone

    from app.config import settings

    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    object.__setattr__(settings, "revy_loja_shell_enabled", True)
    object.__setattr__(settings, "revy_trafego_resultados_enabled", False)
    hoje = datetime.now(timezone.utc).isoformat()
    chatbot_fake.leads = [
        {"id": "a", "etapa": "novo", "criada_em": hoje, "ctwa_source_type": "FB_Ads"},
        {"id": "b", "etapa": "novo", "criada_em": hoje, "ctwa_source_type": "FB_Ads",
         "meta_ad_id": "1202496"},
        {"id": "c", "etapa": "novo", "criada_em": hoje,
         "ctwa_source_type": "global_search_new_chat"},
    ]
    login(client)
    pagina = client.get("/app/loja/vendas")

    assert pagina.status_code == 200
    assert "Por onde as pessoas chegam" in pagina.text
    assert "Anúncio" in pagina.text
    assert "Procurou no WhatsApp" in pagina.text
    assert "1 sem identificação de campanha" in pagina.text
    # Enum cru não chega na tela.
    assert "global_search_new_chat" not in pagina.text
    assert "FB_Ads" not in pagina.text


def test_vendedor_nao_recebe_origens():
    overview = build_sales_overview(
        SessionLocal(),
        loja_slug="loja-teste",
        papel="vendedor",
        vendedor_email="v@loja.test",
        inicio="2026-08-01",
        fim="2026-08-31",
        chatbot=ChatbotStub([_lead(id="a", ctwa_source_type="FB_Ads")]),
        revy_trafego_resultados_enabled=False,
    )
    assert overview.aquisicao_origens == []
