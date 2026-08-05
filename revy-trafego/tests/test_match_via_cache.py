from types import SimpleNamespace

from app.campanhas import lead_casa_campanha


def test_casa_via_cache_ad_para_campaign():
    camp = SimpleNamespace(
        utm_campaign="mt03",
        utm_content=None,
        meta_campaign_id="120249613359800224",
        codigo_ctwa=None,
        anuncios=[],
    )
    lead = {"meta_ad_id": "120252470707220341"}
    mapa = {"120252470707220341": "120249613359800224"}
    assert (
        lead_casa_campanha(lead, camp, modo="last", mapa_ad_campaign=mapa) is True
    )
    assert (
        lead_casa_campanha(lead, camp, modo="last", mapa_ad_campaign={}) is False
    )


def test_cache_nao_casa_se_campanha_sem_meta_id():
    camp = SimpleNamespace(
        utm_campaign="mt03",
        utm_content=None,
        meta_campaign_id=None,
        codigo_ctwa=None,
        anuncios=[],
    )
    lead = {"meta_ad_id": "120252470707220341"}
    mapa = {"120252470707220341": "120249613359800224"}
    assert (
        lead_casa_campanha(lead, camp, modo="last", mapa_ad_campaign=mapa) is False
    )
