"""Credenciais Cloud **por loja** (spec §6.2): número, WABA e template.

Um workflow `n8n-cloud` serve N lojas, e o Revy é **um** app na Meta. O que é do
Revy (token de System User, App Secret, verify token) fica em variável de
ambiente e não entra aqui — nem no banco, nem em log. O que é de cada loja é só
identificador: ``phone_number_id``, ``waba_id`` e o nome do template de oferta.

Onde mora: ``whatsapp_canais``, ao lado dos canais Evolution. O canal Cloud é o
que tem ``waba_id`` gravado — template de mensagem é recurso da WABA, então um
canal sem WABA não é Cloud. O ``phone_number_id`` reusa a coluna
``evolution_instance`` (ver o comentário em ``models_db.WhatsAppCanal``).

Compatibilidade com a loja piloto: canal sem número/template gravado cai no
valor da variável de ambiente, que é exatamente o que o piloto usa hoje. Nada de
backfill manual.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import config
from app.models_db import Loja, WhatsAppCanal


@dataclass(frozen=True)
class CredenciaisCloud:
    """O trio que endereça um envio Cloud. Nenhum campo é segredo."""

    phone_number_id: str
    waba_id: str | None
    template_oferta: str


def canal_cloud_da_loja(db: Session, loja_id: str) -> WhatsAppCanal | None:
    """Canal Cloud da loja, ou ``None`` se ela ainda não tem um.

    Preferência: canal ativo, e entre os ativos o mais antigo — mesma regra de
    desempate de ``channels.obter_canal_principal_estoque``, para que ligar um
    segundo número não mude por acidente de quem a loja fala.

    Canal banido/restrito continua sendo escolhido de propósito: cair no número
    global do ambiente mandaria a mensagem da loja errada, que é pior do que
    falhar no envio.
    """
    if not loja_id:
        return None
    return (
        db.query(WhatsAppCanal)
        .filter(
            WhatsAppCanal.loja_id == loja_id,
            WhatsAppCanal.waba_id.isnot(None),
            WhatsAppCanal.waba_id != "",
        )
        .order_by(WhatsAppCanal.ativo.desc(), WhatsAppCanal.criado_em.asc())
        .first()
    )


def credenciais_cloud_da_loja(db: Session, loja_id: str) -> CredenciaisCloud:
    """Resolve o trio da loja, com fallback no ambiente campo a campo."""
    canal = canal_cloud_da_loja(db, loja_id)
    if canal is None:
        return CredenciaisCloud(
            phone_number_id=config.GRAPH_PHONE_NUMBER_ID,
            waba_id=None,
            template_oferta=config.GRAPH_TEMPLATE_OFERTA,
        )
    return CredenciaisCloud(
        phone_number_id=(canal.evolution_instance or "").strip()
        or config.GRAPH_PHONE_NUMBER_ID,
        waba_id=(canal.waba_id or "").strip() or None,
        template_oferta=(canal.template_oferta or "").strip()
        or config.GRAPH_TEMPLATE_OFERTA,
    )


def phone_number_id_da_loja(db: Session, loja_id: str) -> str:
    """Número de onde a loja fala no Modo 2. Único resolver de todo o outbound.

    Sem canal Cloud cadastrado devolve ``config.GRAPH_PHONE_NUMBER_ID`` — o
    piloto de hoje segue funcionando sem migração de dado.
    """
    return credenciais_cloud_da_loja(db, loja_id).phone_number_id


def template_oferta_da_loja(db: Session, loja_id: str) -> str:
    """Template de oferta aprovado na WABA da loja (spec §5.7, §6.2)."""
    return credenciais_cloud_da_loja(db, loja_id).template_oferta


def loja_id_do_phone_number_id(db: Session, phone_number_id: str) -> str | None:
    """Caminho inverso de ``phone_number_id_da_loja``: quem fala por este número.

    Quem envia conhece o número, não a loja — o ``phone_number_id`` é o
    ``instance`` de todo outbound. Os workers precisam voltar dele para a loja
    para escolher o transporte (Cloud × Modo 1), e é isso que esta função faz.

    Duas buscas porque há duas formas de o número estar cadastrado: no canal
    Cloud da loja, e — na loja piloto, sem canal — em ``lojas.evolution_instance``.
    Mesma resolução que o inbound de ``/webhook/cloud`` usa, de propósito: se o
    número entra por uma loja, a resposta tem de sair pela mesma.

    ``None`` quando ninguém cadastrou o número.
    """
    if not phone_number_id:
        return None
    canal = (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.evolution_instance == phone_number_id)
        .first()
    )
    if canal is not None:
        return canal.loja_id
    loja = (
        db.query(Loja).filter(Loja.evolution_instance == phone_number_id).first()
    )
    return loja.id if loja is not None else None
