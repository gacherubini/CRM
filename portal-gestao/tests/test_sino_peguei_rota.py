from dataclasses import replace

from conftest import criar_usuario, csrf_da_resposta, login

from app.config import settings as portal_settings
from app.loja.copiloto.sinais_store import criar_sinal_direcionado
from app.main import app, get_chatbot_client
from app.models import AtendimentoAtribuicao, Usuario


class _ChatbotFake:
    def __init__(self, ganhou=True, telefone="5511988887777"):
        self.ganhou = ganhou
        self.telefone = telefone
        self.chamadas = []

    def assumir_oferta(self, oferta_id):
        self.chamadas.append(oferta_id)
        return {
            "ganhou": self.ganhou,
            "telefone_cliente": self.telefone if self.ganhou else "",
        }


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    enabled = replace(portal_settings, revy_loja_atendimento_enabled=True)
    monkeypatch.setattr("app.config.settings", enabled)
    monkeypatch.setattr("app.main.settings", enabled)
    monkeypatch.setattr("app.loja.routes.settings", enabled)


def _usuario(db, email):
    return db.query(Usuario).filter(Usuario.email == email).one()


def _sinal(db, destinatario_id, entidade="of-1"):
    return criar_sinal_direcionado(
        db,
        "loja-teste",
        regra="oferta_lead",
        destinatario_usuario_id=destinatario_id,
        entidade_ref=entidade,
        titulo="Lead novo para Ana",
        detalhe="Toque em Peguei para assumir o atendimento.",
    )


def _override(fake):
    app.dependency_overrides[get_chatbot_client] = lambda: fake


def teardown_function():
    app.dependency_overrides.pop(get_chatbot_client, None)


def test_peguei_ganhou_registra_handoff_e_resolve(client, db, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="ana@loja.test")
    usuario = _usuario(db, "ana@loja.test")
    sinal = _sinal(db, usuario.id)
    fake = _ChatbotFake(ganhou=True)
    _override(fake)

    pagina = client.get("/login")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal.id}/peguei",
        data={"csrf": csrf_da_resposta(pagina)},
    )

    assert r.status_code == 200
    corpo = r.json()
    assert corpo["ganhou"] is True
    assert fake.chamadas == ["of-1"]
    db.expire_all()
    assert db.get(type(sinal), sinal.id).estado == "resolvido"
    assert db.query(AtendimentoAtribuicao).filter(
        AtendimentoAtribuicao.ativa.is_(True)
    ).count() == 1


def test_peguei_perdeu_nao_faz_handoff(client, db, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="bruno@loja.test")
    usuario = _usuario(db, "bruno@loja.test")
    sinal = _sinal(db, usuario.id, entidade="of-2")
    _override(_ChatbotFake(ganhou=False))

    pagina = client.get("/login")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal.id}/peguei",
        data={"csrf": csrf_da_resposta(pagina)},
    )

    assert r.status_code == 200
    assert r.json()["ganhou"] is False
    assert "pego" in r.json()["mensagem"].lower()
    assert db.query(AtendimentoAtribuicao).count() == 0


def test_peguei_sinal_alheio_e_403(client, db, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="carla@loja.test")
    criar_usuario(papel="vendedor", email="outro@loja.test")
    from app.db import SessionLocal

    with SessionLocal() as s:
        outro_id = s.query(Usuario).filter(Usuario.email == "outro@loja.test").one().id
    sinal = _sinal(db, outro_id, entidade="of-3")

    pagina = client.get("/login")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal.id}/peguei",
        data={"csrf": csrf_da_resposta(pagina)},
    )

    assert r.status_code == 403
    assert db.query(AtendimentoAtribuicao).count() == 0
