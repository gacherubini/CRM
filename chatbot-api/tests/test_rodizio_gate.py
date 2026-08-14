from app.models_db import FilaVendedor, LojaOperacionalProjecao
from app.rodizio import abrir_oferta, loja_opera_modo2


def _fila(db, loja_id):
    db.add(FilaVendedor(
        id=f"{loja_id[:8]}-f0", loja_id=loja_id, nome="V0",
        telefone="5511999990000", ordem=0, ativo=True,
    ))
    db.commit()


def test_flag_off_nao_oferece(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", False)
    _fila(db, loja_a["loja_id"])
    assert abrir_oferta(db, loja_a["loja_id"], "5511988887777") is None


def test_loja_suspensa_nao_opera(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    projecao = db.get(LojaOperacionalProjecao, (loja_a["loja_id"], "loja"))
    projecao.state = "suspensa"
    db.commit()
    _fila(db, loja_a["loja_id"])

    assert loja_opera_modo2(db, loja_a["loja_id"]) is False
    assert abrir_oferta(db, loja_a["loja_id"], "5511988887777") is None


def test_loja_sem_projecao_nao_opera(db, loja_sem_projecao, monkeypatch):
    """Fail-closed: sem projeção do Control, não opera (allows_processing)."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_sem_projecao["loja_id"])
    assert loja_opera_modo2(db, loja_sem_projecao["loja_id"]) is False


def test_loja_ativa_com_flag_on_opera(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo(db, loja_a["loja_id"], "2")
    _fila(db, loja_a["loja_id"])
    assert loja_opera_modo2(db, loja_a["loja_id"]) is True
    assert abrir_oferta(db, loja_a["loja_id"], "5511988887777") is not None


def _projetar_modo(db, loja_id, modo: str):
    db.add(LojaOperacionalProjecao(
        loja_id=loja_id, aggregate="whatsapp_modo", version=1,
        state=modo, event_id=f"e-modo-{modo}",
    ))
    db.commit()


def test_loja_no_modo_1_nao_opera_o_rodizio(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo(db, loja_a["loja_id"], "1")
    assert loja_opera_modo2(db, loja_a["loja_id"]) is False


def test_loja_no_modo_2_opera(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo(db, loja_a["loja_id"], "2")
    assert loja_opera_modo2(db, loja_a["loja_id"]) is True


def test_sem_projecao_de_modo_nao_opera(db, loja_a, monkeypatch):
    """Fail-closed: sem o Control ter dito o modo, não entra no rodízio."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    assert loja_opera_modo2(db, loja_a["loja_id"]) is False
