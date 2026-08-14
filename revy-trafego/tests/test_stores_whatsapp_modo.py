import pytest

from app.control.stores import StoreControl
from app.control.types import Actor, SetWhatsappMode, StoreRef
from app.db import SessionLocal
from app.models import GestorRevy, Loja


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def _loja() -> tuple[str, int]:
    with SessionLocal() as db:
        loja = Loja(slug="loja-modo", nome="Loja Modo", status="ativa", versao=1)
        db.add(loja)
        db.commit()
        return loja.id, loja.versao


def test_troca_para_modo_2_incrementa_a_versao(monkeypatch):
    monkeypatch.setattr("app.control.stores.config.WHATSAPP_MODO2_ENABLED", True)
    loja_id, versao_antes = _loja()

    view = StoreControl(SessionLocal).set_whatsapp_mode(
        _admin_actor(), SetWhatsappMode(store=StoreRef(id=loja_id), mode=2)
    )

    assert view.whatsapp_mode == 2
    # Sem bump, a projeção monotônica do chatbot descarta o evento.
    assert view.version > versao_antes


def test_flag_off_recusa_modo_2(monkeypatch):
    monkeypatch.setattr("app.control.stores.config.WHATSAPP_MODO2_ENABLED", False)
    loja_id, _ = _loja()

    with pytest.raises(ValueError):
        StoreControl(SessionLocal).set_whatsapp_mode(
            _admin_actor(), SetWhatsappMode(store=StoreRef(id=loja_id), mode=2)
        )

    with SessionLocal() as db:
        assert db.get(Loja, loja_id).whatsapp_modo == 1


def test_modo_invalido_e_recusado(monkeypatch):
    monkeypatch.setattr("app.control.stores.config.WHATSAPP_MODO2_ENABLED", True)
    loja_id, _ = _loja()
    with pytest.raises(ValueError):
        StoreControl(SessionLocal).set_whatsapp_mode(
            _admin_actor(), SetWhatsappMode(store=StoreRef(id=loja_id), mode=3)
        )


def test_voltar_para_modo_1_bumpa_a_versao_de_novo(monkeypatch):
    """Ida e volta. Cada troca é um evento novo para a projeção do chatbot.

    Sem o segundo bump, o chatbot ficaria no modo 2 para sempre: a projeção é
    monotônica e descartaria a volta com a mesma versão.
    """
    monkeypatch.setattr("app.control.stores.config.WHATSAPP_MODO2_ENABLED", True)
    loja_id, versao_inicial = _loja()
    controle = StoreControl(SessionLocal)
    ator = _admin_actor()

    no_modo_2 = controle.set_whatsapp_mode(
        ator, SetWhatsappMode(store=StoreRef(id=loja_id), mode=2)
    )
    de_volta = controle.set_whatsapp_mode(
        ator, SetWhatsappMode(store=StoreRef(id=loja_id), mode=1)
    )

    assert de_volta.whatsapp_mode == 1
    assert no_modo_2.version > versao_inicial
    assert de_volta.version > no_modo_2.version
