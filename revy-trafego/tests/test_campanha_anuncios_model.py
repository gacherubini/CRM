from app.db import Base, engine, SessionLocal
from app.models import Campanha, CampanhaAnuncio, novo_id


def _setup():
    Base.metadata.create_all(bind=engine)


def test_campanha_tem_anuncios():
    _setup()
    db = SessionLocal()
    try:
        c = Campanha(
            id=novo_id(), loja_slug="moto-center", nome="MT03 CAUA",
            utm_campaign="mt03", utm_campaign_norm="mt03", criada_por_email="a@b.com",
        )
        db.add(c)
        db.flush()
        db.add(CampanhaAnuncio(id=novo_id(), loja_slug="moto-center",
                               campanha_id=c.id, ad_id="120252470707220341"))
        db.commit()
        db.refresh(c)
        assert [a.ad_id for a in c.anuncios] == ["120252470707220341"]
    finally:
        db.close()
