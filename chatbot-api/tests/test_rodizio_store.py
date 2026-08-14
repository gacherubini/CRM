import pytest

from app.models_db import FilaVendedor, OfertaLead, RodizioPonteiro
from app.rodizio import abrir_oferta


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


def _fila(db, loja_id, quantos):
    # IDs por loja: o SQLite de teste é compartilhado (StaticPool) e não
    # é limpo entre testes — "f0" colide com o teste anterior.
    ids = []
    for i in range(quantos):
        vid = f"{loja_id[:8]}-f{i}"
        db.add(FilaVendedor(
            id=vid, loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
        ids.append(vid)
    db.commit()
    return ids


def test_primeira_oferta_vai_para_o_primeiro(db, loja_a):
    ids = _fila(db, loja_a["loja_id"], 3)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    assert oferta is not None
    assert oferta.vendedor_id == ids[0]
    assert oferta.estado == "aberta"
    assert oferta.prazo_em is not None


def test_segundo_lead_vai_para_o_segundo(db, loja_a):
    ids = _fila(db, loja_a["loja_id"], 3)
    abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    segunda = abrir_oferta(db, loja_a["loja_id"], "5511977776666")
    assert segunda.vendedor_id == ids[1]


def test_fila_vazia_devolve_none(db, loja_a):
    assert abrir_oferta(db, loja_a["loja_id"], "5511988887777") is None


def test_vendedor_inativo_e_pulado(db, loja_a):
    ids = _fila(db, loja_a["loja_id"], 2)
    db.query(FilaVendedor).filter(FilaVendedor.id == ids[0]).update({"ativo": False})
    db.commit()
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    assert oferta.vendedor_id == ids[1]
