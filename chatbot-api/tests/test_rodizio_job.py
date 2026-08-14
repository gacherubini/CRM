from datetime import datetime, timedelta, timezone

import pytest

from app.models_db import FilaVendedor, OfertaLead
from app.rodizio import abrir_oferta
from app.rodizio_job import RodizioWorker


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


def _vencer(db, oferta):
    oferta.prazo_em = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()


def test_oferta_vencida_passa_para_o_proximo(db, loja_a):
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db)

    assert resultado["expiradas"] == 1
    assert resultado["reofertadas"] == 1
    nova = (
        db.query(OfertaLead)
        .filter(OfertaLead.estado == "aberta", OfertaLead.loja_id == loja_a["loja_id"])
        .one()
    )
    assert nova.vendedor_id != oferta.vendedor_id


def test_volta_completa_esgota(db, loja_a):
    _fila(db, loja_a["loja_id"], 1)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db)

    assert resultado["esgotadas"] == 1
    assert (
        db.query(OfertaLead)
        .filter(OfertaLead.estado == "aberta", OfertaLead.loja_id == loja_a["loja_id"])
        .count()
        == 0
    )


def test_oferta_travada_nao_expira(db, loja_a):
    """Pegou e não ligou: fica travado, não volta para a fila (spec §5.3)."""
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    oferta.estado = "travada"
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db)

    assert resultado["expiradas"] == 0
