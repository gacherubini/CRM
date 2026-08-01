"""Task 2 do plano de status de integrações: probe da Graph API + check_meta.

Não usa `httpx` de verdade — `FakeGraphProbe` local garante que o teste nunca
bate na rede. As fixtures/factories seguem o padrão já usado em
`tests/test_control_integrations.py` (não há fixtures pytest `db`/`loja`/
`actor_admin` neste repositório; loja e ator admin são criados via
`SessionLocal()` direto, como no restante da suíte do Control).
"""

from __future__ import annotations

from app.control.integrations import IntegrationsControl, UpsertPixel
from app.control.integrations_health import (
    GroupHealth,
    HealthStatus,
    ItemHealth,
    check_meta,
)
from app.control.types import Actor, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, Loja


class FakeGraphProbe:
    def __init__(self, ok: bool = True, motivo: str | None = None) -> None:
        self.ok = ok
        self.motivo = motivo
        self.chamadas = 0

    def validar_token(self, token: str, pixel_id: str) -> tuple[bool, str | None]:
        self.chamadas += 1
        return (self.ok, None if self.ok else (self.motivo or "token inválido"))


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def _create_store(slug: str) -> str:
    with SessionLocal() as db:
        store = Loja(nome="Loja Health Meta", slug=slug)
        db.add(store)
        db.commit()
        db.refresh(store)
        return store.id


def _load_store(store_id: str, db) -> Loja:
    return db.query(Loja).filter(Loja.id == store_id).one()


def test_check_meta_missing_sem_config():
    store_id = _create_store("loja-health-meta-missing")
    with SessionLocal() as db:
        grupo = check_meta(db, _load_store(store_id, db), FakeGraphProbe())

    assert isinstance(grupo, GroupHealth)
    assert grupo.status is HealthStatus.MISSING
    assert all(item.status is HealthStatus.MISSING for item in grupo.itens)
    kinds = {item.kind for item in grupo.itens}
    assert kinds == {"pixel", "capi", "meta_ads"}


def test_check_meta_connected_com_pixel_e_token_valido():
    store_id = _create_store("loja-health-meta-connected")
    actor_admin = _admin_actor()
    IntegrationsControl(SessionLocal).upsert_pixel(
        actor_admin,
        UpsertPixel(store=StoreRef(id=store_id), pixel_id="123456789012345", token="tok-abc"),
    )
    probe = FakeGraphProbe(ok=True)

    with SessionLocal() as db:
        grupo = check_meta(db, _load_store(store_id, db), probe)

    assert grupo.status is HealthStatus.CONNECTED
    assert probe.chamadas >= 1
    pixel_item = next(i for i in grupo.itens if i.kind == "pixel")
    capi_item = next(i for i in grupo.itens if i.kind == "capi")
    ads_item = next(i for i in grupo.itens if i.kind == "meta_ads")
    assert pixel_item.status is HealthStatus.CONNECTED
    assert capi_item.status is HealthStatus.CONNECTED
    assert ads_item.status is HealthStatus.MISSING


def test_check_meta_error_quando_token_invalido():
    store_id = _create_store("loja-health-meta-error")
    actor_admin = _admin_actor()
    IntegrationsControl(SessionLocal).upsert_pixel(
        actor_admin,
        UpsertPixel(store=StoreRef(id=store_id), pixel_id="123456789012345", token="tok-abc"),
    )
    probe = FakeGraphProbe(ok=False, motivo="OAuthException")

    with SessionLocal() as db:
        grupo = check_meta(db, _load_store(store_id, db), probe)

    assert grupo.status is HealthStatus.ERROR
    assert any(
        item.status is HealthStatus.ERROR and item.message for item in grupo.itens
    )
    # o token cru nunca deve vazar na mensagem de erro
    assert all("tok-abc" not in (item.message or "") for item in grupo.itens)


def test_itemhealth_e_grouphealth_sao_dataclasses_congelados():
    item = ItemHealth(kind="pixel", status=HealthStatus.MISSING, message=None)
    try:
        item.kind = "outro"  # type: ignore[misc]
        congelado = False
    except Exception:
        congelado = True
    assert congelado is True
