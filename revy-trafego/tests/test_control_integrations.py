"""Central de Integrações Meta — Control Fase 3 lean."""

from dataclasses import replace

from app.auth import hash_senha
from app.config import settings
from app.control.audit import AuditTrail
from app.control.integrations import (
    IntegrationKind,
    IntegrationStatus,
    IntegrationsControl,
    UpsertPixel,
)
from app.control.portfolio import PortfolioControl
from app.control.readiness import StoreReadiness
from app.control.stores import StoreControl
from app.control.types import (
    AccessDenied,
    Actor,
    AuditQuery,
    CreateStore,
    StoreRef,
)
from app.cripto import cifrar
from app.db import SessionLocal
from app.models import (
    AuditoriaEvento,
    GestorRevy,
    Loja,
    MetaPixelConfig,
    ModuloRevy,
    VinculoTrafego,
)
from app.web import control as control_mod


def _enable_control(monkeypatch) -> None:
    monkeypatch.setattr(
        control_mod,
        "settings",
        replace(settings, revy_control_enabled=True),
    )


def _login(client, email: str, password: str) -> None:
    response = client.post(
        "/login",
        data={"email": email, "senha": password},
        follow_redirects=False,
    )
    assert response.status_code == 303


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(
            id=admin.id,
            email=admin.email,
            name=admin.nome,
            role=admin.papel,
        )


def _seed_catalog() -> None:
    with SessionLocal() as db:
        if db.query(ModuloRevy).count() == 0:
            db.add_all(
                [
                    ModuloRevy(id="vendas", codigo="vendas", nome="Vendas"),
                    ModuloRevy(id="estoque", codigo="estoque", nome="Estoque"),
                    ModuloRevy(id="copiloto", codigo="copiloto", nome="Copiloto de Vendas"),
                ]
            )
            db.commit()


def _create_store_with_links() -> dict[str, str]:
    """Cria loja + responsável + colaborador. Retorna ids/emails."""
    with SessionLocal() as db:
        store = Loja(nome="Loja Integrações", slug="loja-integracoes")
        responsible = GestorRevy(
            email="responsavel.int@revy.local",
            nome="Responsável Integrações",
            senha_hash=hash_senha("senha-responsavel"),
            papel="gestor",
            ativo=True,
        )
        collaborator = GestorRevy(
            email="colaborador.int@revy.local",
            nome="Colaborador Integrações",
            senha_hash=hash_senha("senha-colaborador"),
            papel="gestor",
            ativo=True,
        )
        db.add_all([store, responsible, collaborator])
        db.flush()
        db.add_all(
            [
                VinculoTrafego(
                    loja_id=store.id,
                    gestor_id=responsible.id,
                    tipo="responsavel",
                ),
                VinculoTrafego(
                    loja_id=store.id,
                    gestor_id=collaborator.id,
                    tipo="colaborador",
                ),
            ]
        )
        db.commit()
        return {
            "store_id": store.id,
            "store_slug": store.slug,
            "responsible_id": responsible.id,
            "collaborator_id": collaborator.id,
        }


def _seed_pixel(store_slug: str, store_id: str, *, token: str = "EAAG-secret-token") -> None:
    with SessionLocal() as db:
        db.add(
            MetaPixelConfig(
                loja_slug=store_slug,
                loja_id=store_id,
                pixel_id="123456789012345",
                token_ciphertext=cifrar(token),
                enviar_page_view=True,
                enviar_lead=True,
                enviar_purchase=True,
            )
        )
        db.commit()


def test_colaborador_nao_pode_desconectar_pixel(client, monkeypatch):
    _enable_control(monkeypatch)
    ids = _create_store_with_links()
    _seed_pixel(ids["store_slug"], ids["store_id"])

    control = IntegrationsControl(SessionLocal)
    collaborator = Actor(
        id=ids["collaborator_id"],
        email="colaborador.int@revy.local",
        name="Colaborador Integrações",
        role="gestor",
    )

    try:
        control.disconnect_pixel(collaborator, StoreRef(id=ids["store_id"]))
        raised = False
    except AccessDenied:
        raised = True
    assert raised is True

    _login(client, "colaborador.int@revy.local", "senha-colaborador")
    response = client.post(
        f"/control/v1/lojas/{ids['store_id']}/integracoes/pixel/desconectar",
        json={"motivo": "tentativa colaborador"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "access_denied"

    with SessionLocal() as db:
        config = (
            db.query(MetaPixelConfig)
            .filter(MetaPixelConfig.loja_slug == ids["store_slug"])
            .one()
        )
        assert config.token_ciphertext is not None
        assert config.pixel_id == "123456789012345"


def test_admin_lista_sem_token_cru_no_json(client, monkeypatch):
    _enable_control(monkeypatch)
    ids = _create_store_with_links()
    secret = "EAAG-super-secret-token-xyz"
    _seed_pixel(ids["store_slug"], ids["store_id"], token=secret)

    _login(client, "trafego@revy.local", "secret-teste")
    response = client.get(f"/control/v1/lojas/{ids['store_id']}/integracoes")

    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    kinds = {item["tipo"] for item in body["items"]}
    assert kinds == {"pixel", "capi", "meta_ads"}

    raw = response.text
    assert secret not in raw
    assert "token_ciphertext" not in raw
    assert "EAAG" not in raw

    pixel = next(item for item in body["items"] if item["tipo"] == "pixel")
    assert pixel["status"] == "connected"
    assert pixel["campos"]["token_configured"] is True
    assert pixel["campos"]["token_masked"] == "••••••••"
    assert pixel["campos"]["pixel_id"] == "123456789012345"
    assert secret not in str(pixel["campos"])

    capi = next(item for item in body["items"] if item["tipo"] == "capi")
    assert capi["status"] == "connected"
    assert capi["campos"]["token_configured"] is True

    ads = next(item for item in body["items"] if item["tipo"] == "meta_ads")
    assert ads["status"] == "missing"


def test_disconnect_limpa_tokens_e_audita(client, monkeypatch):
    _enable_control(monkeypatch)
    ids = _create_store_with_links()
    secret = "EAAG-to-be-cleared"
    _seed_pixel(ids["store_slug"], ids["store_id"], token=secret)

    admin = _admin_actor()
    control = IntegrationsControl(SessionLocal)
    view = control.disconnect_pixel(
        admin,
        StoreRef(id=ids["store_id"]),
        reason="rotação de credencial",
    )

    assert view.kind is IntegrationKind.PIXEL
    assert view.status is IntegrationStatus.MISSING
    assert view.fields["token_configured"] is False
    assert view.fields["token_masked"] is None

    with SessionLocal() as db:
        config = (
            db.query(MetaPixelConfig)
            .filter(MetaPixelConfig.loja_slug == ids["store_slug"])
            .one()
        )
        assert config.token_ciphertext is None
        assert config.pixel_id == ""
        events = (
            db.query(AuditoriaEvento)
            .filter(
                AuditoriaEvento.loja_id == ids["store_id"],
                AuditoriaEvento.acao == "integration.pixel.disconnected",
            )
            .all()
        )
        assert len(events) == 1
        assert events[0].motivo == "rotação de credencial"
        assert secret not in (events[0].antes_json or "")
        assert secret not in (events[0].depois_json or "")

    trail = AuditTrail(SessionLocal).list(
        admin,
        AuditQuery(store_id=ids["store_id"], limit=50),
    )
    actions = [event.action for event in trail.items]
    assert "integration.pixel.disconnected" in actions


def test_responsavel_pode_upsert_e_desconectar_via_http(client, monkeypatch):
    _enable_control(monkeypatch)
    ids = _create_store_with_links()

    _login(client, "responsavel.int@revy.local", "senha-responsavel")
    created = client.put(
        f"/control/v1/lojas/{ids['store_id']}/integracoes/pixel",
        json={
            "pixel_id": "987654321098765",
            "token": "EAAG-responsavel-token",
            "enviar_purchase": True,
        },
    )
    assert created.status_code == 200
    assert created.json()["status"] == "connected"
    assert "EAAG-responsavel-token" not in created.text
    assert created.json()["campos"]["token_masked"] == "••••••••"

    listed = client.get(f"/control/v1/lojas/{ids['store_id']}/integracoes")
    assert listed.status_code == 200
    assert "EAAG-responsavel-token" not in listed.text

    disconnected = client.post(
        f"/control/v1/lojas/{ids['store_id']}/integracoes/pixel/desconectar",
        json={"motivo": "troca de conta"},
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["status"] == "missing"
    assert disconnected.json()["campos"]["token_configured"] is False


def test_readiness_alerta_pixel_quando_vendas_ativo_sem_config():
    _seed_catalog()
    admin = _admin_actor()
    store = StoreControl(SessionLocal).create(
        admin,
        CreateStore(name="Loja Pixel Alerta", slug="loja-pixel-alerta"),
    )
    PortfolioControl(SessionLocal).configure(
        admin,
        StoreRef(id=store.id),
        {"vendas"},
    )

    report = StoreReadiness(SessionLocal).evaluate(admin, StoreRef(id=store.id))
    by_code = {check.code: check for check in report.checks}

    assert "meta_pixel" in by_code
    assert by_code["meta_pixel"].ok is False
    assert by_code["meta_pixel"].severity == "alert"
    # Alerta não impede prontidão por si só (requireds ainda falham sem dono).
    assert report.ready is False

    IntegrationsControl(SessionLocal).upsert_pixel(
        admin,
        UpsertPixel(
            store=StoreRef(id=store.id),
            pixel_id="111222333444555",
            token="EAAG-ready-token",
        ),
    )
    after = StoreReadiness(SessionLocal).evaluate(admin, StoreRef(id=store.id))
    assert {c.code: c for c in after.checks}["meta_pixel"].ok is True
