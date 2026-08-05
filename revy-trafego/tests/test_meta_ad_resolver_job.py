from datetime import datetime, timedelta, timezone

from app.db import Base, engine, SessionLocal
from app.meta_ad_resolver_job import mapa_ad_campaign_loja, resolver_ads_pendentes
from app.models import MetaAdCampanha, novo_id


def fake_resolver(ad_id, token, **kw):
    if ad_id == "120252470707220341":
        return ("120249613359800224", "MT03 CAUA")
    return (None, None)


def _db():
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_resolve_e_cacheia():
    db = _db()
    try:
        batch = resolver_ads_pendentes(
            db,
            "moto-center",
            ["120252470707220341", "999"],
            resolver=fake_resolver,
            token="T",
            sleep_entre_calls=0,
            cooldown_seconds=0,
        )
        db.commit()
        assert batch.resolvidos == 1
        assert batch.chamadas == 2  # ok + falha do 999
        assert batch.falhas == 1
        row = db.query(MetaAdCampanha).filter_by(ad_id="120252470707220341").one()
        assert row.meta_campaign_id == "120249613359800224"
        assert row.meta_campaign_nome == "MT03 CAUA"
        assert row.ultima_tentativa_em is not None
        # não re-resolve o que já está cacheado
        batch2 = resolver_ads_pendentes(
            db,
            "moto-center",
            ["120252470707220341"],
            resolver=fake_resolver,
            token="T",
            sleep_entre_calls=0,
        )
        assert batch2.resolvidos == 0
        assert batch2.chamadas == 0
        assert batch2.skipped_ok == 1
        mapa = mapa_ad_campaign_loja(db, "moto-center")
        assert mapa == {"120252470707220341": "120249613359800224"}
    finally:
        db.close()


def test_sem_token_retorna_zero():
    db = _db()
    try:
        batch = resolver_ads_pendentes(
            db, "x", ["120252470707220341"], token="", resolver=fake_resolver
        )
        assert batch.resolvidos == 0
        assert batch.chamadas == 0
    finally:
        db.close()


def test_cooldown_pula_falha_recente():
    db = _db()
    agora = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    try:
        db.add(
            MetaAdCampanha(
                id=novo_id(),
                loja_slug="moto-center",
                ad_id="120252470707220341",
                erro="nao_resolvido",
                tentativas=1,
                ultima_tentativa_em=agora - timedelta(hours=1),
            )
        )
        db.commit()
        calls = []

        def tracking(ad_id, token, **kw):
            calls.append(ad_id)
            return ("1", "x")

        batch = resolver_ads_pendentes(
            db,
            "moto-center",
            ["120252470707220341"],
            token="T",
            resolver=tracking,
            cooldown_seconds=86400,
            sleep_entre_calls=0,
            agora=agora,
        )
        assert batch.chamadas == 0
        assert batch.skipped_cooldown == 1
        assert calls == []
    finally:
        db.close()


def test_cooldown_expirado_retenta():
    db = _db()
    agora = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    try:
        db.add(
            MetaAdCampanha(
                id=novo_id(),
                loja_slug="moto-center",
                ad_id="120252470707220341",
                erro="nao_resolvido",
                tentativas=1,
                ultima_tentativa_em=agora - timedelta(hours=25),
            )
        )
        db.commit()
        batch = resolver_ads_pendentes(
            db,
            "moto-center",
            ["120252470707220341"],
            token="T",
            resolver=fake_resolver,
            cooldown_seconds=86400,
            sleep_entre_calls=0,
            agora=agora,
        )
        assert batch.chamadas == 1
        assert batch.resolvidos == 1
        row = db.query(MetaAdCampanha).filter_by(ad_id="120252470707220341").one()
        assert row.meta_campaign_id == "120249613359800224"
        assert row.erro is None
        assert row.tentativas == 2
    finally:
        db.close()


def test_max_tentativas_nao_chama_graph():
    db = _db()
    try:
        db.add(
            MetaAdCampanha(
                id=novo_id(),
                loja_slug="moto-center",
                ad_id="120252470707220341",
                erro="nao_resolvido",
                tentativas=5,
                ultima_tentativa_em=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
        )
        db.commit()
        calls = []

        def tracking(ad_id, token, **kw):
            calls.append(ad_id)
            return ("1", "x")

        batch = resolver_ads_pendentes(
            db,
            "moto-center",
            ["120252470707220341"],
            token="T",
            resolver=tracking,
            max_tentativas=5,
            cooldown_seconds=0,
            sleep_entre_calls=0,
        )
        assert batch.chamadas == 0
        assert batch.skipped_max_tentativas == 1
        assert calls == []
    finally:
        db.close()


def test_teto_por_ciclo():
    db = _db()
    try:
        calls = []

        def tracking(ad_id, token, **kw):
            calls.append(ad_id)
            return (ad_id, "nome")

        ads = [f"10000000000000000{i}" for i in range(5)]
        batch = resolver_ads_pendentes(
            db,
            "moto-center",
            ads,
            token="T",
            resolver=tracking,
            max_por_ciclo=2,
            sleep_entre_calls=0,
            cooldown_seconds=0,
        )
        assert batch.chamadas == 2
        assert batch.resolvidos == 2
        assert batch.skipped_teto == 3
        assert len(calls) == 2
    finally:
        db.close()


def test_sleep_entre_calls_injetavel():
    db = _db()
    try:
        sleeps: list[float] = []

        def always_ok(ad_id, token, **kw):
            return ("1", "n")

        batch = resolver_ads_pendentes(
            db,
            "moto-center",
            ["111", "222", "333"],
            token="T",
            resolver=always_ok,
            max_por_ciclo=10,
            sleep_entre_calls=0.05,
            sleeper=sleeps.append,
            cooldown_seconds=0,
        )
        assert batch.chamadas == 3
        # sleep entre calls: 2 sleeps (antes da 2ª e da 3ª)
        assert sleeps == [0.05, 0.05]
    finally:
        db.close()
