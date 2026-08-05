from app.db import Base, engine, SessionLocal
from app.models import MetaAdCampanha, novo_id


def test_cache_grava_resolucao():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(
            MetaAdCampanha(
                id=novo_id(),
                loja_slug="moto-center",
                ad_id="120252470707220341",
                meta_campaign_id="120249613359800224",
                meta_campaign_nome="MT03 CAUA",
                tentativas=1,
            )
        )
        db.commit()
        row = db.query(MetaAdCampanha).filter_by(ad_id="120252470707220341").one()
        assert row.meta_campaign_id == "120249613359800224"
        assert row.meta_campaign_nome == "MT03 CAUA"
        assert row.loja_slug == "moto-center"
    finally:
        db.close()
