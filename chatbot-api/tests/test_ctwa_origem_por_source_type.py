"""`origem = meta_ctwa` so para quem veio de anuncio.

`ctwa_source_type` diz POR ONDE a pessoa entrou, nao QUAL campanha pagou. O
balde CTWA carrega link direto (`click_to_chat_link`, `message_short_link`) e
busca dentro do WhatsApp (`global_search_new_chat`) — em producao, 10 leads
assim estavam carimbados como lead de anuncio da Meta.

O sinal continua sendo gravado sempre; o que passa a ter guarda e so o carimbo
de origem.
"""
from app.models_db import Lead
from app.servico import aplicar_touch_ctwa


def _lead() -> Lead:
    """Lead cru, sem passar pelo banco: aplicar_touch_ctwa e pura sobre o objeto."""
    return Lead(loja_id="loja-1", telefone="5511900001111")


def test_fb_ads_sozinho_carimba_origem():
    """O valor real em producao vem com maiusculas."""
    lead = _lead()
    aplicar_touch_ctwa(lead, ctwa_source_type="FB_Ads")
    assert lead.origem == "meta_ctwa"
    assert lead.origem_first == "meta_ctwa"
    assert lead.origem_last == "meta_ctwa"
    assert lead.ctwa_atribuido_em is not None


def test_ctwa_ad_e_ad_tambem_sao_anuncio():
    for source in ("ctwa_ad", "ad", "AD"):
        lead = _lead()
        aplicar_touch_ctwa(lead, ctwa_source_type=source)
        assert lead.origem == "meta_ctwa", source


def test_link_direto_nao_carimba_origem_mas_grava_source_type():
    for source in ("click_to_chat_link", "message_short_link"):
        lead = _lead()
        aplicar_touch_ctwa(lead, ctwa_source_type=source)
        assert lead.origem is None, source
        assert lead.origem_first is None, source
        assert lead.origem_last is None, source
        assert lead.ctwa_atribuido_em is None, source
        assert lead.ctwa_source_type == source, "o sinal cru nao pode se perder"


def test_busca_no_whatsapp_nao_carimba_origem():
    lead = _lead()
    aplicar_touch_ctwa(lead, ctwa_source_type="global_search_new_chat")
    assert lead.origem is None
    assert lead.ctwa_source_type == "global_search_new_chat"


def test_identificador_vence_source_type_nao_anuncio():
    """clid/ad_id sao prova de anuncio, independentemente do source_type."""
    lead = _lead()
    aplicar_touch_ctwa(
        lead, ctwa_source_type="global_search_new_chat", ctwa_clid="ARActwaClick123"
    )
    assert lead.origem == "meta_ctwa"

    outro = _lead()
    aplicar_touch_ctwa(
        outro, ctwa_source_type="click_to_chat_link", meta_ad_id="120249613359810224"
    )
    assert outro.origem == "meta_ctwa"


def test_codigo_na_mensagem_vence_source_type_nao_anuncio():
    """Rota da Task 4: codigo na mensagem pre-preenchida do anuncio."""
    lead = _lead()
    aplicar_touch_ctwa(
        lead,
        ctwa_source_type="click_to_chat_link",
        texto="Quero saber da MT-03 — Cód: CAUA08",
    )
    assert lead.ctwa_codigo == "CAUA08"
    assert lead.origem == "meta_ctwa"


def test_source_type_desconhecido_nao_carimba():
    """Falso negativo aqui e barato; falso positivo e o defeito que se conserta."""
    lead = _lead()
    aplicar_touch_ctwa(lead, ctwa_source_type="algo_novo_da_meta")
    assert lead.origem is None
    assert lead.ctwa_source_type == "algo_novo_da_meta"


def test_canal_whatsapp_vale_para_qualquer_sinal():
    """Quem chegou por link direto tambem chegou pelo WhatsApp."""
    lead = _lead()
    aplicar_touch_ctwa(lead, ctwa_source_type="click_to_chat_link")
    assert lead.canal == "whatsapp"
    assert lead.canal_first == "whatsapp"
    assert lead.canal_last == "whatsapp"


def test_origem_de_anuncio_nao_e_rebaixada():
    """O guard decide se ESCREVE, nunca apaga o que ja foi atribuido."""
    lead = _lead()
    aplicar_touch_ctwa(lead, ctwa_source_type="FB_Ads")
    atribuido_em = lead.ctwa_atribuido_em
    aplicar_touch_ctwa(lead, ctwa_source_type="click_to_chat_link")

    assert lead.origem == "meta_ctwa"
    assert lead.origem_last == "meta_ctwa"
    assert lead.ctwa_atribuido_em == atribuido_em
    assert lead.ctwa_source_type == "click_to_chat_link", "o sinal cru segue o ultimo touch"


def test_sem_sinal_nenhum_e_no_op():
    lead = _lead()
    assert aplicar_touch_ctwa(lead) is False
    assert lead.origem is None
    assert lead.canal is None
