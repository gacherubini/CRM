from types import SimpleNamespace
from app.campanhas import lead_casa_campanha


def _camp(ad_ids):
    return SimpleNamespace(
        utm_campaign="mt03", utm_content=None, meta_campaign_id=None,
        codigo_ctwa=None, anuncios=[SimpleNamespace(ad_id=a) for a in ad_ids],
    )


def test_casa_por_ad_id_last():
    camp = _camp(["120252470707220341"])
    lead = {"meta_ad_id": "120252470707220341"}
    assert lead_casa_campanha(lead, camp, modo="last") is True


def test_nao_casa_ad_id_fora_da_lista():
    camp = _camp(["120252470707220341"])
    lead = {"meta_ad_id": "999999999999999999"}
    assert lead_casa_campanha(lead, camp, modo="last") is False


def test_casa_por_ad_id_first():
    camp = _camp(["120252470707220341"])
    lead = {"meta_ad_id_first": "120252470707220341", "meta_ad_id": "outro"}
    assert lead_casa_campanha(lead, camp, modo="first") is True
