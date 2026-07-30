"""F3: loja suspensa interrompe jobs sem apagar filas/histórico."""
from datetime import date
from decimal import Decimal

from app.control.stores import store_blocks_traffic_jobs
from app.control.types import StoreStatus
from app.cripto import cifrar
from app.db import SessionLocal
from app.meta_ads_spend import (
    listar_lojas_para_sync,
    sincronizar_gastos_meta,
    sincronizar_todas_lojas,
)
from app.meta_capi import (
    processar_outbox_automatico,
    processar_outbox_pendentes,
    tentar_enviar_outbox,
)
from app.models import (
    Campanha,
    CampanhaGasto,
    Loja,
    MetaAdsConfig,
    MetaCapiOutbox,
    agora,
    novo_id,
)


def _seed_loja(*, slug: str, status: str) -> Loja:
    with SessionLocal() as db:
        loja = Loja(nome=f"Loja {slug}", slug=slug, status=status)
        db.add(loja)
        db.commit()
        db.refresh(loja)
        return loja


def _ads_config(loja: Loja) -> None:
    with SessionLocal() as db:
        db.add(
            MetaAdsConfig(
                loja_slug=loja.slug,
                loja_id=loja.id,
                ad_account_id="act_1",
                token_ciphertext=cifrar("token-ads"),
                sync_enabled=True,
                atualizada_em=agora(),
            )
        )
        db.add(
            Campanha(
                id=novo_id(),
                loja_slug=loja.slug,
                loja_id=loja.id,
                nome="Camp Suspend",
                canal="meta",
                status="ativa",
                utm_campaign=f"camp-{loja.slug}",
                utm_campaign_norm=f"camp-{loja.slug}",
                meta_campaign_id="111",
                criada_por_email="gestor@revy.local",
            )
        )
        db.commit()


def _pending_outbox(loja: Loja, event_id: str) -> str:
    with SessionLocal() as db:
        row = MetaCapiOutbox(
            loja_slug=loja.slug,
            loja_id=loja.id,
            event_id=event_id,
            event_name="Purchase",
            payload_json='{"data":[{"event_name":"Purchase","event_id":"'
            + event_id
            + '"}]}',
            status="pending",
            attempts=0,
        )
        db.add(row)
        db.commit()
        return row.id


def test_store_blocks_traffic_jobs_apenas_suspensa_ou_encerrada():
    active = _seed_loja(slug="job-ativa", status=StoreStatus.ACTIVE.value)
    suspended = _seed_loja(slug="job-suspensa", status=StoreStatus.SUSPENDED.value)
    closed = _seed_loja(slug="job-encerrada", status=StoreStatus.CLOSED.value)
    draft = _seed_loja(slug="job-rascunho", status=StoreStatus.DRAFT.value)

    with SessionLocal() as db:
        assert store_blocks_traffic_jobs(db, loja_id=active.id) is False
        assert store_blocks_traffic_jobs(db, loja_slug=active.slug) is False
        assert store_blocks_traffic_jobs(db, loja_id=suspended.id) is True
        assert store_blocks_traffic_jobs(db, loja_slug=suspended.slug) is True
        assert store_blocks_traffic_jobs(db, loja_id=closed.id) is True
        assert store_blocks_traffic_jobs(db, loja_slug=draft.slug) is False
        # Legado sem cadastro Control: não bloqueia.
        assert store_blocks_traffic_jobs(db, loja_slug="slug-inexistente") is False


def test_spend_sync_pula_loja_suspensa_sem_apagar_historico():
    active = _seed_loja(slug="spend-ativa", status=StoreStatus.ACTIVE.value)
    suspended = _seed_loja(slug="spend-suspensa", status=StoreStatus.SUSPENDED.value)
    _ads_config(active)
    _ads_config(suspended)

    with SessionLocal() as db:
        campanha = (
            db.query(Campanha)
            .filter(Campanha.loja_slug == suspended.slug)
            .one()
        )
        historico = CampanhaGasto(
            id=novo_id(),
            campanha_id=campanha.id,
            loja_slug=suspended.slug,
            valor=Decimal("25.00"),
            referencia=date(2026, 7, 10),
            origem="meta_api",
            external_key=f"meta:{suspended.slug}:111:2026-07-10",
            criada_por="meta_api",
        )
        db.add(historico)
        db.commit()
        historico_id = historico.id

    def fake_fetch(**kwargs):
        return [
            {
                "campaign_id": "111",
                "spend": "99.00",
                "date_start": "2026-07-20",
                "date_stop": "2026-07-20",
            }
        ]

    with SessionLocal() as db:
        assert suspended.slug not in listar_lojas_para_sync(db)
        assert active.slug in listar_lojas_para_sync(db)

    with SessionLocal() as db:
        skipped = sincronizar_gastos_meta(
            db,
            suspended.slug,
            since=date(2026, 7, 20),
            until=date(2026, 7, 20),
            fetch=fake_fetch,
        )
        assert skipped.status == "skipped"
        assert skipped.imported == 0
        assert "suspensa" in skipped.errors[0].lower() or "encerrada" in skipped.errors[
            0
        ].lower()

    agg = sincronizar_todas_lojas(SessionLocal, janela_dias=1, fetch=fake_fetch)
    assert active.slug in {d["loja_slug"] for d in agg.details}
    assert suspended.slug not in {d["loja_slug"] for d in agg.details}
    assert agg.imported >= 1

    with SessionLocal() as db:
        # Histórico da suspensa permanece; nenhum gasto novo importado.
        assert db.get(CampanhaGasto, historico_id) is not None
        novos = (
            db.query(CampanhaGasto)
            .filter(
                CampanhaGasto.loja_slug == suspended.slug,
                CampanhaGasto.id != historico_id,
            )
            .count()
        )
        assert novos == 0
        assert (
            db.query(CampanhaGasto)
            .filter(CampanhaGasto.loja_slug == active.slug)
            .count()
            >= 1
        )


def test_capi_outbox_estaciona_quando_loja_suspensa_sem_apagar_fila(monkeypatch):
    suspended = _seed_loja(slug="capi-suspensa", status=StoreStatus.SUSPENDED.value)
    active = _seed_loja(slug="capi-ativa", status=StoreStatus.ACTIVE.value)
    outbox_suspensa_id = _pending_outbox(suspended, "purchase-suspensa")
    outbox_ativa_id = _pending_outbox(active, "purchase-ativa")

    chamadas: list[str] = []

    def fake_enviar(*args, **kwargs):
        raise AssertionError("Meta CAPI não deve ser chamado para loja suspensa")

    def fake_tentar(db, item, config=None):
        chamadas.append(item.event_id)
        if item.loja_slug == suspended.slug:
            raise AssertionError("tentar_enviar não deve processar loja suspensa")
        item.status = "delivered"
        db.commit()
        return True

    monkeypatch.setattr("app.meta_capi.enviar_eventos_capi", fake_enviar)
    monkeypatch.setattr("app.meta_capi.tentar_enviar_outbox", fake_tentar)

    with SessionLocal() as db:
        pendentes = processar_outbox_pendentes(db, suspended.slug)
        assert pendentes["processados"] == 0
        assert pendentes["suspensas"] == 1
        row = db.get(MetaCapiOutbox, outbox_suspensa_id)
        assert row is not None
        assert row.status == "pending"
        assert row.attempts == 0

    auto = processar_outbox_automatico(SessionLocal, limite=50)
    assert auto["suspensas"] >= 1
    assert "purchase-suspensa" not in chamadas
    assert "purchase-ativa" in chamadas

    with SessionLocal() as db:
        suspensa = db.get(MetaCapiOutbox, outbox_suspensa_id)
        ativa = db.get(MetaCapiOutbox, outbox_ativa_id)
        assert suspensa is not None
        assert suspensa.status == "pending"
        assert suspensa.attempts == 0
        assert ativa is not None
        assert ativa.status == "delivered"


def test_tentar_enviar_outbox_respeita_suspensao_sem_mudar_status():
    suspended = _seed_loja(slug="capi-tentar-suspensa", status=StoreStatus.SUSPENDED.value)
    outbox_id = _pending_outbox(suspended, "purchase-tentar-suspensa")

    with SessionLocal() as db:
        row = db.get(MetaCapiOutbox, outbox_id)
        ok = tentar_enviar_outbox(db, row)
        assert ok is False
        db.refresh(row)
        assert row.status == "pending"
        assert row.attempts == 0
        assert row.last_error is None
