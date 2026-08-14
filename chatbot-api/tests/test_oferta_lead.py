from app.models_db import FilaVendedor, OfertaLead, RodizioPonteiro


def test_oferta_nasce_aberta(db, loja_a):
    """Commit obrigatório: antes do flush o estado é ``None``, não o default."""
    vid = f"{loja_a['loja_id'][:8]}-f1"
    db.add(FilaVendedor(
        id=vid, loja_id=loja_a["loja_id"], nome="V", telefone="5511999990000", ordem=0,
    ))
    db.commit()
    o = OfertaLead(
        id=f"{loja_a['loja_id'][:8]}-o1", loja_id=loja_a["loja_id"],
        telefone_cliente="5511988887777",
        vendedor_id=vid, posicao_inicial=0,
    )
    db.add(o)
    db.commit()
    assert o.estado == "aberta"
    assert o.travada_em is None


def test_ponteiro_comeca_em_zero(db, loja_a):
    """Loja nova começa no topo da fila — o default é parte do contrato."""
    p = RodizioPonteiro(loja_id=loja_a["loja_id"])
    db.add(p)
    db.commit()
    assert p.posicao == 0
