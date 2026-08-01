"""Task 6 do plano de status de integrações: invalidação de cache em
connect/disconnect.

`integrations_health.invalidar(store_id)` já existe (Task 4). Este teste
cobre que os pontos de escrita de Pixel/Meta Ads (`IntegrationsControl`) e
de conexão Google Ads (`GoogleAdsConnectionControl`) chamam `invalidar`
automaticamente após o commit, sem esperar o TTL de 10min.

Segue o mesmo padrão de `tests/test_integrations_health_agg.py`: não há
fixtures pytest `db`/`loja` neste repositório — Loja é criada via
`SessionLocal()` direto. `FakeGraphProbe`/`FakeExchanger` são redefinidos
localmente para não acoplar este teste aos módulos vizinhos.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.control.google_ads import (
    FakeGoogleAdsTokenExchanger,
    GOOGLE_ADS_SCOPES,
    GoogleAdsConnectionControl,
    OAuthTokenBundle,
)
from app.control.integrations import IntegrationsControl, UpsertPixel
from app.control.integrations_health import HealthStatus, health_da_loja
from app.control.types import Actor, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, Loja
from tests.test_integrations_health_whatsapp import FakeWppPort


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


class FakeGraphProbe:
    def __init__(self, ok: bool = True, motivo: str | None = None) -> None:
        self.ok = ok
        self.motivo = motivo
        self.chamadas = 0

    def validar_token(self, token: str, pixel_id: str) -> tuple[bool, str | None]:
        self.chamadas += 1
        return (self.ok, None if self.ok else (self.motivo or "token inválido"))


class FakeExchanger:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.chamadas = 0

    def obter_access_token(self, refresh_token: str) -> str:
        self.chamadas += 1
        if not self.ok:
            raise RuntimeError("invalid_grant")
        return "access-xyz"


def _create_store(slug: str) -> str:
    with SessionLocal() as db:
        store = Loja(nome="Loja Health Invalidacao", slug=slug)
        db.add(store)
        db.commit()
        db.refresh(store)
        return store.id


def _load_store(store_id: str, db) -> Loja:
    return db.query(Loja).filter(Loja.id == store_id).one()


def _wpp() -> FakeWppPort:
    # WhatsApp não é o alvo deste teste (invalidação de Meta/Google): fica
    # sempre MISSING, sem afetar as asserções em `out["meta"]`/`out["google"]`.
    return FakeWppPort(indisponivel=True)


def test_upsert_pixel_invalida_cache_de_health():
    store_id = _create_store("loja-health-inv-upsert-pixel")
    actor = _admin_actor()
    control = IntegrationsControl(SessionLocal)

    control.upsert_pixel(
        actor,
        UpsertPixel(store=StoreRef(id=store_id), pixel_id="123456789012345", token="tok-1"),
    )

    probe = FakeGraphProbe()
    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=_wpp())
        n1 = probe.chamadas
        assert n1 > 0

        health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert probe.chamadas == n1  # cache hit, ainda não invalidado

    # Reconecta com token novo: deve invalidar o cache da loja.
    control.upsert_pixel(
        actor,
        UpsertPixel(store=StoreRef(id=store_id), pixel_id="123456789012345", token="tok-2"),
    )

    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert probe.chamadas > n1  # invalidado pelo upsert, rechecou de fato


def test_disconnect_pixel_invalida_cache_de_health():
    store_id = _create_store("loja-health-inv-disconnect-pixel")
    actor = _admin_actor()
    control = IntegrationsControl(SessionLocal)

    control.upsert_pixel(
        actor,
        UpsertPixel(store=StoreRef(id=store_id), pixel_id="123456789012345", token="tok-1"),
    )

    probe = FakeGraphProbe(ok=True)
    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        out1 = health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert out1["meta"]["status"] == HealthStatus.CONNECTED.value

        out2 = health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert out2["meta"]["status"] == HealthStatus.CONNECTED.value  # cache hit

    control.disconnect_pixel(actor, StoreRef(id=store_id))

    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        out3 = health_da_loja(db, loja, probe=probe, exchanger=FakeExchanger(), whatsapp_port=_wpp())
        # Sem a invalidação, o resultado CONNECTED antigo ficaria em cache até o
        # TTL expirar; com a invalidação, a rechecagem reflete o estado real
        # (pixel desconectado) imediatamente.
        assert out3["meta"]["status"] == HealthStatus.MISSING.value


def test_google_ads_connect_e_disconnect_invalidam_cache_de_health():
    store_id = _create_store("loja-health-inv-google")
    actor = _admin_actor()
    control = GoogleAdsConnectionControl(
        SessionLocal,
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="https://control.revy.test/control/v1/google-ads/oauth/callback",
        token_exchanger=FakeGoogleAdsTokenExchanger(
            default_bundle=OAuthTokenBundle(
                refresh_token="rt-secret-value",
                access_token="at-value",
                scopes=GOOGLE_ADS_SCOPES,
            )
        ),
        now=lambda: datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
    )

    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        out1 = health_da_loja(db, loja, probe=FakeGraphProbe(), exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert out1["google"]["status"] == HealthStatus.MISSING.value

        out2 = health_da_loja(db, loja, probe=FakeGraphProbe(), exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert out2["google"]["status"] == HealthStatus.MISSING.value  # cache hit

    # Conecta: deve invalidar o cache imediatamente.
    started = control.start_oauth(actor, StoreRef(id=store_id))
    control.complete_oauth(state=started.state, code="c1")

    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        out3 = health_da_loja(db, loja, probe=FakeGraphProbe(), exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert out3["google"]["status"] == HealthStatus.CONNECTED.value

        out4 = health_da_loja(db, loja, probe=FakeGraphProbe(), exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert out4["google"]["status"] == HealthStatus.CONNECTED.value  # cache hit

    # Desconecta: deve invalidar o cache imediatamente.
    control.disconnect(actor, StoreRef(id=store_id))

    with SessionLocal() as db:
        loja = _load_store(store_id, db)
        out5 = health_da_loja(db, loja, probe=FakeGraphProbe(), exchanger=FakeExchanger(), whatsapp_port=_wpp())
        assert out5["google"]["status"] == HealthStatus.MISSING.value
