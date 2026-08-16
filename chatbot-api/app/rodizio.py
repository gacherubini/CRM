"""Decisão do rodízio (spec §5.3), sem banco.

Separado do store de propósito: é aqui que mora a regra que erra fácil
(ponteiro circular, pular ocupado, saber que a volta fechou), e sem I/O
cada caso vira um teste de duas linhas.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import config
from app.models_db import FilaVendedor, LojaOperacionalProjecao, OfertaLead, RodizioPonteiro
from app.provisioning import allows_processing


def escolher_proximo(
    ordem_ids: list[str],
    *,
    ponteiro: int,
    pendentes: set[str],
    ja_ofertados: set[str],
    posicao_inicial: int | None,
) -> tuple[str | None, int, bool]:
    """Devolve ``(vendedor_id, nova_posicao, volta_fechou)``.

    - ``None`` + ``volta_fechou=True``: acabou (fila vazia ou todo mundo já
      recebeu). O lead vira ``aguardando``.
    - ``None`` + ``volta_fechou=False``: todos estão com oferta aberta agora.
      O lead espera uma vaga; não é fim de fila.
    """
    total = len(ordem_ids)
    if total == 0:
        return None, ponteiro, True

    if posicao_inicial is not None and len(ja_ofertados) >= total:
        return None, ponteiro, True

    inicio = ponteiro % total
    for salto in range(total):
        indice = (inicio + salto) % total
        candidato = ordem_ids[indice]
        if candidato in pendentes or candidato in ja_ofertados:
            continue
        return candidato, (indice + 1) % total, False

    # Ninguém elegível. Distinguir "todos ocupados agora" de "todos já
    # receberam" é o que separa esperar de encerrar.
    livres = [v for v in ordem_ids if v not in ja_ofertados]
    return None, ponteiro, not livres


def loja_opera_modo2(db: Session, loja_id: str) -> bool:
    """Gate único do Modo 2 (spec §6.3 e §5.8).

    Três condições, todas fail-closed:

    1. flag de rollout ligada (invariante do projeto: default OFF);
    2. loja operacional — ``allows_processing`` já cobre suspensa e sem projeção;
    3. o Control projetou ``whatsapp_modo == "2"`` para esta loja.

    A terceira é o que impede uma loja Modo 1 de cair no rodízio quando a flag
    é ligada no ambiente: sem central Cloud, os vendedores dela nunca receberiam
    a oferta e o lead ficaria preso em ``aguardando``.
    """
    if not config.MODO2_ENABLED:
        return False
    if not allows_processing(db, loja_id):
        return False
    modo = db.get(LojaOperacionalProjecao, (loja_id, "whatsapp_modo"))
    return modo is not None and modo.state == "2"


def _fila_ordenada(db: Session, loja_id: str) -> list[FilaVendedor]:
    return (
        db.query(FilaVendedor)
        .filter(FilaVendedor.loja_id == loja_id, FilaVendedor.ativo.is_(True))
        .order_by(FilaVendedor.ordem, FilaVendedor.criado_em)
        .all()
    )


def abrir_oferta(
    db: Session,
    loja_id: str,
    telefone_cliente: str,
    *,
    prazo_minutos: int = 10,
) -> OfertaLead | None:
    """Oferece o lead ao vendedor da vez. ``None`` = ninguém para oferecer."""
    if not loja_opera_modo2(db, loja_id):
        return None
    fila = _fila_ordenada(db, loja_id)
    ordem_ids = [v.id for v in fila]

    ponteiro = db.get(RodizioPonteiro, loja_id)
    if ponteiro is None:
        ponteiro = RodizioPonteiro(loja_id=loja_id, posicao=0)
        db.add(ponteiro)
        db.flush()

    abertas = (
        db.query(OfertaLead)
        .filter(OfertaLead.loja_id == loja_id, OfertaLead.estado == "aberta")
        .all()
    )
    pendentes = {o.vendedor_id for o in abertas}

    deste_lead = [o for o in abertas if o.telefone_cliente == telefone_cliente]
    ja_ofertados = {o.vendedor_id for o in db.query(OfertaLead).filter(
        OfertaLead.loja_id == loja_id,
        OfertaLead.telefone_cliente == telefone_cliente,
    ).all()}
    posicao_inicial = deste_lead[0].posicao_inicial if deste_lead else None

    vendedor_id, nova_posicao, _fechou = escolher_proximo(
        ordem_ids,
        ponteiro=ponteiro.posicao,
        pendentes=pendentes - ja_ofertados,
        ja_ofertados=ja_ofertados,
        posicao_inicial=posicao_inicial,
    )
    if vendedor_id is None:
        return None

    oferta = OfertaLead(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        telefone_cliente=telefone_cliente,
        vendedor_id=vendedor_id,
        estado="aberta",
        posicao_inicial=posicao_inicial if posicao_inicial is not None else ponteiro.posicao,
        prazo_em=datetime.now(timezone.utc) + timedelta(minutes=prazo_minutos),
    )
    ponteiro.posicao = nova_posicao
    db.add(oferta)
    db.commit()
    return oferta


def assumir_oferta(db: Session, oferta_id: str) -> tuple[bool, OfertaLead | None]:
    """Trava o lead no vendedor da oferta. Idempotente e exclusiva por lead.

    "Primeiro clique vence, mesmo atrasado" (spec §5.3): a oferta anterior
    continua ``aberta``, então o botão velho ainda resolve — o que decide é
    se JÁ EXISTE trava para aquele telefone, não qual oferta é mais nova.
    """
    oferta = db.get(OfertaLead, oferta_id)
    if oferta is None:
        return False, None

    ja_travada = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == oferta.loja_id,
            OfertaLead.telefone_cliente == oferta.telefone_cliente,
            OfertaLead.estado == "travada",
        )
        .first()
    )
    if ja_travada is not None:
        return False, ja_travada

    agora = datetime.now(timezone.utc)
    oferta.estado = "travada"
    oferta.travada_em = agora

    # As demais ofertas deste lead morrem: o perdedor recebe "já foi pego".
    (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == oferta.loja_id,
            OfertaLead.telefone_cliente == oferta.telefone_cliente,
            OfertaLead.id != oferta.id,
            OfertaLead.estado == "aberta",
        )
        .update({"estado": "expirada"}, synchronize_session=False)
    )
    db.commit()
    return True, oferta
