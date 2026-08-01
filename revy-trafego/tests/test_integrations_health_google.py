"""Task 3 do plano de status de integrações: check_google ao vivo.

Segue o mesmo padrão de `tests/test_integrations_health_meta.py`: não há
fixtures pytest `db`/`loja`/`google_conn_factory` neste repositório — Loja e
GoogleAdsConnection são criadas via `SessionLocal()` direto, como no restante
da suíte do Control. `google_conn_factory` local cifra o refresh token com
`app.cripto.cifrar` para refletir o storage real.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.control.integrations_health import (
    GroupHealth,
    HealthStatus,
    check_google,
)
from app.cripto import cifrar
from app.db import SessionLocal
from app.models import GoogleAdsConnection, Loja, novo_id

CONNECTION_STATUS_CONNECTED = "conectado"


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
        store = Loja(nome="Loja Health Google", slug=slug)
        db.add(store)
        db.commit()
        db.refresh(store)
        return store.id


def _load_store(store_id: str, db) -> Loja:
    return db.query(Loja).filter(Loja.id == store_id).one()


def google_conn_factory(store_id: str, refresh_token: str) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(
            GoogleAdsConnection(
                id=novo_id(),
                loja_id=store_id,
                status=CONNECTION_STATUS_CONNECTED,
                customer_id=None,
                login_customer_id=None,
                refresh_token_ciphertext=cifrar(refresh_token),
                scopes="https://www.googleapis.com/auth/adwords",
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()


def test_check_google_missing_sem_conexao():
    store_id = _create_store("loja-health-google-missing")
    with SessionLocal() as db:
        grupo = check_google(db, _load_store(store_id, db), FakeExchanger())

    assert isinstance(grupo, GroupHealth)
    assert grupo.status is HealthStatus.MISSING
    assert len(grupo.itens) == 1
    assert grupo.itens[0].kind == "google_ads"
    assert grupo.itens[0].status is HealthStatus.MISSING


def test_check_google_connected():
    store_id = _create_store("loja-health-google-connected")
    google_conn_factory(store_id, refresh_token="rt-abc")
    probe = FakeExchanger(ok=True)

    with SessionLocal() as db:
        grupo = check_google(db, _load_store(store_id, db), probe)

    assert grupo.status is HealthStatus.CONNECTED
    assert probe.chamadas == 1
    assert grupo.itens[0].status is HealthStatus.CONNECTED


def test_check_google_error_quando_refresh_invalido():
    store_id = _create_store("loja-health-google-error")
    google_conn_factory(store_id, refresh_token="rt-ruim")
    probe = FakeExchanger(ok=False)

    with SessionLocal() as db:
        grupo = check_google(db, _load_store(store_id, db), probe)

    assert grupo.status is HealthStatus.ERROR
    assert grupo.itens[0].status is HealthStatus.ERROR
    # o token cru nunca deve vazar na mensagem de erro
    assert "rt-ruim" not in (grupo.itens[0].message or "")
    assert grupo.itens[0].message == "falha ao renovar access token do Google Ads"
