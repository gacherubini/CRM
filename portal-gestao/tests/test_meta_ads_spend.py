from datetime import date
from decimal import Decimal

from conftest import csrf_da_resposta, login
from app.cripto import cifrar
from app.db import SessionLocal
from app.meta_ads_spend import (
    external_key_meta,
    normalizar_ad_account_id,
    parse_spend,
    sincronizar_gastos_meta,
)
from app.models import Campanha, CampanhaGasto, MetaAdsConfig, agora, novo_id


def test_normalizar_ad_account_e_spend():
    assert normalizar_ad_account_id("123456") == "act_123456"
    assert normalizar_ad_account_id("act_99") == "act_99"
    assert parse_spend("12.50") == Decimal("12.50")
    assert parse_spend("-1") is None


def test_sincronizar_importa_atualiza_e_orfa(client):
    login(client)
    db = SessionLocal()
    campanha = Campanha(
        id=novo_id(),
        loja_slug="loja-teste",
        nome="Meta Sync",
        canal="meta",
        status="ativa",
        utm_campaign="sync-test",
        utm_campaign_norm="sync-test",
        meta_campaign_id="111",
        criada_por_email="dono@teste.local",
    )
    db.add(campanha)
    db.add(
        MetaAdsConfig(
            loja_slug="loja-teste",
            ad_account_id="act_1",
            token_ciphertext=cifrar("token-ads"),
            sync_enabled=True,
            atualizada_em=agora(),
        )
    )
    db.commit()
    campanha_id = campanha.id
    db.close()

    rows = [
        {
            "campaign_id": "111",
            "spend": "100.00",
            "date_start": "2026-07-20",
            "date_stop": "2026-07-20",
        },
        {
            "campaign_id": "999",
            "spend": "50.00",
            "date_start": "2026-07-20",
            "date_stop": "2026-07-20",
        },
    ]

    def fake_fetch(**kwargs):
        return rows

    db = SessionLocal()
    r1 = sincronizar_gastos_meta(
        db,
        "loja-teste",
        since=date(2026, 7, 20),
        until=date(2026, 7, 20),
        fetch=fake_fetch,
    )
    assert r1.imported == 1
    assert r1.orphans == 1
    assert r1.status in {"ok", "partial"}
    gastos = db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == campanha_id).all()
    assert len(gastos) == 1
    assert gastos[0].origem == "meta_api"
    assert gastos[0].valor == Decimal("100.00")
    assert gastos[0].external_key == external_key_meta("loja-teste", "111", date(2026, 7, 20))
    db.close()

    rows[0]["spend"] = "120.50"
    db = SessionLocal()
    r2 = sincronizar_gastos_meta(
        db,
        "loja-teste",
        since=date(2026, 7, 20),
        until=date(2026, 7, 20),
        fetch=fake_fetch,
    )
    assert r2.imported == 0
    assert r2.updated == 1
    g = db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == campanha_id).one()
    assert g.valor == Decimal("120.50")
    db.close()


def test_nao_sobrescreve_gasto_manual_mesmo_dia(client):
    login(client)
    db = SessionLocal()
    campanha = Campanha(
        id=novo_id(),
        loja_slug="loja-teste",
        nome="Manual Protect",
        canal="meta",
        status="ativa",
        utm_campaign="manual-protect",
        utm_campaign_norm="manual-protect",
        meta_campaign_id="222",
        criada_por_email="dono@teste.local",
    )
    db.add(campanha)
    db.add(
        CampanhaGasto(
            id=novo_id(),
            campanha_id=campanha.id,
            loja_slug="loja-teste",
            valor=Decimal("10.00"),
            referencia=date(2026, 7, 21),
            origem="manual",
            criada_por="dono@teste.local",
        )
    )
    db.add(
        MetaAdsConfig(
            loja_slug="loja-teste",
            ad_account_id="act_1",
            token_ciphertext=cifrar("token-ads"),
            sync_enabled=True,
            atualizada_em=agora(),
        )
    )
    db.commit()
    cid = campanha.id
    db.close()

    def fake_fetch(**kwargs):
        return [
            {
                "campaign_id": "222",
                "spend": "99.00",
                "date_start": "2026-07-21",
                "date_stop": "2026-07-21",
            }
        ]

    db = SessionLocal()
    r = sincronizar_gastos_meta(
        db,
        "loja-teste",
        since=date(2026, 7, 21),
        until=date(2026, 7, 21),
        fetch=fake_fetch,
    )
    assert r.skipped_manual == 1
    assert r.imported == 0
    g = db.query(CampanhaGasto).filter(CampanhaGasto.campanha_id == cid).one()
    assert g.valor == Decimal("10.00")
    assert g.origem == "manual"
    db.close()


def test_ui_salva_ads_e_sincroniza(client, monkeypatch):
    login(client)
    pagina = client.get("/app/trafego")
    assert "Gasto automático" in pagina.text
    csrf = csrf_da_resposta(pagina)
    r = client.post(
        "/app/trafego/ads/salvar",
        data={
            "csrf": csrf,
            "ad_account_id": "act_555",
            "ads_token": "tok-xyz",
            "ads_sync_enabled": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "ads-salvo" in r.headers["location"]

    db = SessionLocal()
    cfg = db.query(MetaAdsConfig).filter(MetaAdsConfig.loja_slug == "loja-teste").one()
    assert cfg.ad_account_id == "act_555"
    assert cfg.token_ciphertext
    db.close()

    called = {}

    def fake_sync(db, loja_slug, **kwargs):
        from app.meta_ads_spend import SyncResult

        called["loja"] = loja_slug
        return SyncResult(imported=2, status="ok")

    monkeypatch.setattr("app.main.sincronizar_gastos_meta", fake_sync)
    pagina2 = client.get("/app/trafego")
    r2 = client.post(
        "/app/trafego/ads/sincronizar",
        data={"csrf": csrf_da_resposta(pagina2)},
        follow_redirects=False,
    )
    assert r2.status_code == 303
    assert "sync-ok" in r2.headers["location"]
    assert called["loja"] == "loja-teste"


def test_campanha_form_aceita_meta_campaign_id(client):
    login(client)
    p = client.get("/app/campanhas/nova")
    r = client.post(
        "/app/campanhas/nova",
        data={
            "csrf": csrf_da_resposta(p),
            "nome": "Com Meta ID",
            "canal": "meta",
            "utm_campaign": "com-meta-id",
            "meta_campaign_id": "12033999888777",
            "status": "ativa",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    c = db.query(Campanha).filter(Campanha.utm_campaign_norm == "com-meta-id").one()
    assert c.meta_campaign_id == "12033999888777"
    db.close()


def test_sincronizar_todas_lojas_e_job_endpoint(client, monkeypatch):
    from app.meta_ads_spend import SyncResult, sincronizar_todas_lojas
    from app import meta_ads_spend_job

    db = SessionLocal()
    db.add(
        MetaAdsConfig(
            loja_slug="loja-teste",
            ad_account_id="act_1",
            token_ciphertext=cifrar("tok"),
            sync_enabled=True,
            atualizada_em=agora(),
        )
    )
    db.add(
        Campanha(
            id=novo_id(),
            loja_slug="loja-teste",
            nome="Job Camp",
            canal="meta",
            status="ativa",
            utm_campaign="job-camp",
            utm_campaign_norm="job-camp",
            meta_campaign_id="333",
            criada_por_email="dono@loja.test",
        )
    )
    db.commit()
    db.close()

    def fake_fetch(**kwargs):
        return [
            {
                "campaign_id": "333",
                "spend": "15.00",
                "date_start": "2026-07-22",
                "date_stop": "2026-07-22",
            }
        ]

    agg = sincronizar_todas_lojas(SessionLocal, janela_dias=1, fetch=fake_fetch)
    assert agg.lojas == 1
    assert agg.imported == 1

    # endpoint sem secret configurado
    monkeypatch.delenv("PORTAL_META_SPEND_JOB_SECRET", raising=False)
    r = client.post("/internal/jobs/meta-spend-sync")
    assert r.status_code == 503

    monkeypatch.setenv("PORTAL_META_SPEND_JOB_SECRET", "segredo-job")
    r401 = client.post(
        "/internal/jobs/meta-spend-sync",
        headers={"X-Job-Token": "errado"},
    )
    assert r401.status_code == 401

    class FakeWorker:
        def run_once(self):
            return {"ok": True, "lojas": 1, "resumo": "ok"}

    monkeypatch.setattr(meta_ads_spend_job, "get_worker", lambda: FakeWorker())
    r_ok = client.post(
        "/internal/jobs/meta-spend-sync",
        headers={"X-Job-Token": "segredo-job"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["ok"] is True


def test_worker_respeita_enabled_false():
    from app.meta_ads_spend_job import MetaSpendSyncWorker

    w = MetaSpendSyncWorker(
        db_factory=SessionLocal,
        enabled=False,
        interval_seconds=1,
        initial_delay_seconds=0,
    )
    w.start()
    assert w._thread is None
    w.stop()
