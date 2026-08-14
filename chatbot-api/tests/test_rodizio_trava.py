import pytest

from app.models_db import FilaVendedor, OfertaLead
from app.rodizio import abrir_oferta, assumir_oferta


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


def _fila(db, loja_id, quantos):
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


def test_primeiro_clique_trava(db, loja_a):
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    ganhou, travada = assumir_oferta(db, oferta.id)
    assert ganhou is True
    assert travada.estado == "travada"
    assert travada.travada_em is not None


def test_segundo_clique_nao_muda_nada(db, loja_a):
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    assumir_oferta(db, oferta.id)
    ganhou, travada = assumir_oferta(db, oferta.id)
    assert ganhou is False
    assert travada.vendedor_id == oferta.vendedor_id


def test_clique_atrasado_do_primeiro_vence_o_segundo(db, loja_a):
    """Spec §5.3: botão velho vale até o lead travar."""
    _fila(db, loja_a["loja_id"], 2)
    primeira = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    segunda = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    assert segunda.vendedor_id != primeira.vendedor_id

    ganhou_velho, _ = assumir_oferta(db, primeira.id)
    ganhou_novo, _ = assumir_oferta(db, segunda.id)

    assert ganhou_velho is True
    assert ganhou_novo is False


def test_oferta_inexistente(db):
    assert assumir_oferta(db, "nao-existe") == (False, None)
