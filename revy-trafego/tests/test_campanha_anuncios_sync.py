from app.db import Base, engine, SessionLocal
from app.models import Campanha, CampanhaAnuncio, novo_id
from app.campanha_anuncios import sincronizar_anuncios


def _camp(db):
    c = Campanha(id=novo_id(), loja_slug="moto-center", nome="c",
                 utm_campaign="mt03", utm_campaign_norm="mt03", criada_por_email="a@b.com")
    db.add(c); db.flush(); return c


def test_sync_insere_e_remove():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        c = _camp(db)
        sincronizar_anuncios(db, c, "120252470707220341\n120252470799120341\n")
        db.commit()
        assert {a.ad_id for a in db.query(CampanhaAnuncio).all()} == {
            "120252470707220341", "120252470799120341"}
        # reeditar removendo um e adicionando lixo (deve normalizar/ignorar)
        sincronizar_anuncios(db, c, " 120252470707220341 \nabc\n")
        db.commit()
        assert {a.ad_id for a in db.query(CampanhaAnuncio).filter_by(campanha_id=c.id)} == {
            "120252470707220341"}
    finally:
        db.close()
