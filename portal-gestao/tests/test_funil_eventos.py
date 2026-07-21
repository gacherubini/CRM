from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db import SessionLocal
from app.funil_eventos import (
    EventoFunilIdempotenciaConflitante,
    EventoFunilInvalido,
    materializar_eventos_chatbot,
    registrar_evento,
    resumo_funil,
)
from app.models import FunilEvento


UTC = timezone.utc
BASE = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)


def _registrar(
    db,
    lead_ref: str,
    tipo: str,
    minutos: int,
    *,
    loja_slug: str = "loja-a",
    chave: str | None = None,
    payload=None,
):
    return registrar_evento(
        db,
        loja_slug=loja_slug,
        lead_ref=lead_ref,
        tipo=tipo,
        ocorrido_em=BASE + timedelta(minutes=minutos),
        ator_email="operador@loja.test",
        payload=payload,
        idempotency_key=chave or f"{lead_ref}:{tipo}:{minutos}",
    )


def test_registrar_evento_idempotente_por_loja_e_sem_commit_implicito():
    db = SessionLocal()
    try:
        primeiro, criado = _registrar(
            db,
            "lead-1",
            "etapa_manual",
            5,
            chave="crm:lead-1:etapa:contato",
            payload={"etapa_anterior": "novo", "etapa_nova": "contato"},
        )
        repetido, criado_repetido = _registrar(
            db,
            "lead-1",
            "etapa_manual",
            5,
            chave="crm:lead-1:etapa:contato",
            payload={"etapa_nova": "contato", "etapa_anterior": "novo"},
        )

        assert criado is True
        assert criado_repetido is False
        assert repetido.id == primeiro.id
        assert db.query(FunilEvento).count() == 1
        assert json.loads(primeiro.payload_json) == {
            "etapa_anterior": "novo",
            "etapa_nova": "contato",
        }

        db.rollback()
        assert db.query(FunilEvento).count() == 0
    finally:
        db.close()


def test_mesma_chave_e_valida_em_lojas_diferentes():
    db = SessionLocal()
    try:
        evento_a, criado_a = _registrar(
            db, "lead-1", "lead_criado", 0, loja_slug="loja-a", chave="chatbot:evento-42"
        )
        evento_b, criado_b = _registrar(
            db, "lead-1", "lead_criado", 0, loja_slug="loja-b", chave="chatbot:evento-42"
        )
        db.commit()

        assert criado_a is True and criado_b is True
        assert evento_a.id != evento_b.id
        assert db.query(FunilEvento).count() == 2
    finally:
        db.close()


def test_reuso_conflitante_da_chave_na_mesma_loja_e_rejeitado():
    db = SessionLocal()
    try:
        _registrar(db, "lead-1", "lead_criado", 0, chave="origem:99")

        with pytest.raises(EventoFunilIdempotenciaConflitante):
            _registrar(db, "lead-2", "primeira_resposta", 2, chave="origem:99")

        assert db.query(FunilEvento).count() == 1
    finally:
        db.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"telefone": "5511999999999"},
        {"cpf": "00000000000"},
        {"email": "cliente@example.test"},
        {"placa": "ABC1D23"},
        {"detalhes_livres": "texto que pode carregar PII"},
        {"status": {"anterior": "novo"}},
    ],
)
def test_payload_rejeita_pii_campos_livres_e_estruturas(payload):
    db = SessionLocal()
    try:
        with pytest.raises(EventoFunilInvalido):
            _registrar(db, "lead-1", "etapa_manual", 0, payload=payload)
        assert db.query(FunilEvento).count() == 0
    finally:
        db.close()


def test_validacoes_de_tipo_identificadores_e_periodo():
    db = SessionLocal()
    try:
        with pytest.raises(EventoFunilInvalido, match="tipo de evento desconhecido"):
            _registrar(db, "lead-1", "evento_inventado", 0)
        with pytest.raises(EventoFunilInvalido, match="lead_ref é obrigatório"):
            _registrar(db, "", "lead_criado", 0)
        with pytest.raises(EventoFunilInvalido, match="idempotency_key excede"):
            _registrar(db, "lead-1", "lead_criado", 0, chave="x" * 161)
        with pytest.raises(EventoFunilInvalido, match="fim deve"):
            resumo_funil(db, loja_slug="loja-a", inicio=BASE, fim=BASE - timedelta(seconds=1))
    finally:
        db.close()


def test_resumo_funil_calcula_coorte_tempos_e_conversao_sem_misturar_lojas():
    db = SessionLocal()
    try:
        # Lead A: resposta em 5 min, conversão em 2 h, com simulação.
        _registrar(db, "lead-a", "lead_criado", 0)
        _registrar(db, "lead-a", "primeira_resposta", 5)
        _registrar(db, "lead-a", "simulacao_solicitada", 10)
        _registrar(db, "lead-a", "venda_registrada", 60)
        _registrar(db, "lead-a", "venda_confirmada", 120)

        # Lead B: resposta em 15 min e perda.
        _registrar(db, "lead-b", "lead_criado", 0)
        _registrar(db, "lead-b", "primeira_resposta", 15)
        _registrar(db, "lead-b", "perda", 60, payload={"motivo_codigo": "sem_interesse"})

        # Lead C: conversão após 24 h, sem resposta registrada.
        _registrar(db, "lead-c", "lead_criado", 0)
        _registrar(db, "lead-c", "venda_confirmada", 24 * 60)

        # Mesmo lead_ref em outra loja não pode entrar no resumo.
        _registrar(db, "lead-a", "lead_criado", 0, loja_slug="loja-b")
        _registrar(db, "lead-a", "primeira_resposta", 1, loja_slug="loja-b")
        _registrar(db, "lead-a", "venda_confirmada", 1, loja_slug="loja-b")

        # A coorte usa a primeira criação. Esta duplicata posterior não leva o
        # lead antigo para o período consultado.
        _registrar(db, "lead-antigo", "lead_criado", -(24 * 60))
        _registrar(db, "lead-antigo", "lead_criado", 30)
        _registrar(db, "lead-antigo", "venda_confirmada", 40)
        db.commit()

        resumo = resumo_funil(
            db,
            loja_slug="loja-a",
            inicio=BASE - timedelta(minutes=1),
            fim=BASE + timedelta(minutes=1),
        )

        assert resumo["total_leads"] == 3
        assert resumo["etapas"]["lead_criado"] == 3
        assert resumo["etapas"]["primeira_resposta"] == 2
        assert resumo["etapas"]["simulacao_solicitada"] == 1
        assert resumo["etapas"]["venda_registrada"] == 1
        assert resumo["etapas"]["venda_confirmada"] == 2
        assert resumo["etapas"]["perda"] == 1
        assert resumo["taxa_resposta_pct"] == Decimal("66.67")
        assert resumo["taxa_conversao_pct"] == Decimal("66.67")
        assert resumo["tempo_medio_primeira_resposta_segundos"] == 600
        assert resumo["tempo_mediano_primeira_resposta_segundos"] == 600
        assert resumo["tempo_medio_conversao_segundos"] == 46800
        assert resumo["tempo_mediano_conversao_segundos"] == 46800
    finally:
        db.close()


def test_resumo_vazio_nao_inventa_taxas_ou_tempos_e_aceita_datetime_naive():
    db = SessionLocal()
    try:
        resumo = resumo_funil(
            db,
            loja_slug="loja-sem-eventos",
            inicio=datetime(2026, 7, 1),
            fim=datetime(2026, 7, 2),
        )

        assert resumo["total_leads"] == 0
        assert all(valor == 0 for valor in resumo["etapas"].values())
        assert resumo["taxa_resposta_pct"] is None
        assert resumo["taxa_conversao_pct"] is None
        assert resumo["tempo_medio_primeira_resposta_segundos"] is None
        assert resumo["tempo_mediano_conversao_segundos"] is None
    finally:
        db.close()


def test_materializa_eventos_chatbot_sem_duplicar():
    eventos = [
        {
            "lead_ref": "lead-http-1",
            "tipo": "lead_criado",
            "ocorrido_em": "2026-07-01T10:00:00+00:00",
            "idempotency_key": "chatbot:lead:lead-http-1:criado",
            "payload": {"origem": "catalogo", "canal": "site"},
        },
        {
            "lead_ref": "lead-http-1",
            "tipo": "primeira_resposta",
            "ocorrido_em": "2026-07-01T10:02:00+00:00",
            "idempotency_key": "chatbot:mensagem:m-1:primeira-resposta",
            "payload": None,
        },
    ]
    db = SessionLocal()
    try:
        primeira = materializar_eventos_chatbot(
            db, loja_slug="loja-a", eventos=eventos
        )
        db.commit()
        repetida = materializar_eventos_chatbot(
            db, loja_slug="loja-a", eventos=eventos
        )
        db.commit()

        assert primeira == {"criados": 2, "repetidos": 0}
        assert repetida == {"criados": 0, "repetidos": 2}
        assert db.query(FunilEvento).filter_by(loja_slug="loja-a").count() == 2
    finally:
        db.close()
