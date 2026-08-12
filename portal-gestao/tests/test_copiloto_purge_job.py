from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.copiloto_purge_job import CopilotoPurgeWorker, purgar_loja
from app.db import SessionLocal
from app.loja.copiloto.conversas import criar_turno
from app.models import CopilotoAcao, CopilotoConversa, CopilotoTurno, LojaOperacaoAuditoria

AGORA = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
RETENCAO_DIAS = 30


def _turno(db, *, loja_slug="loja-teste", usuario_id="u1", pergunta="pergunta?",
           idade: timedelta, estado="pronto", conversa_id=None):
    """Cria um turno (via criar_turno, igual ao fluxo real) e o "envelhece"
    mexendo em criado_em/atualizada_em depois — a única forma de simular uma
    conversa antiga num teste que roda em um instante só."""
    turno = criar_turno(
        db, loja_slug=loja_slug, usuario_id=usuario_id, pergunta=pergunta,
        conversa_id=conversa_id,
    )
    turno.estado = estado
    turno.criado_em = AGORA - idade
    conversa = db.get(CopilotoConversa, turno.conversa_id)
    conversa.atualizada_em = AGORA - idade
    db.commit()
    db.refresh(turno)
    return turno


def _worker(**overrides):
    kwargs = dict(
        db_factory=SessionLocal,
        enabled=True,
        retencao_dias=RETENCAO_DIAS,
        agora=lambda: AGORA,
        lote=1000,
    )
    kwargs.update(overrides)
    return CopilotoPurgeWorker(**kwargs)


def test_turno_mais_velho_que_o_prazo_some(db):
    velho = _turno(db, idade=timedelta(days=RETENCAO_DIAS + 1))
    resultado = _worker().run_once()
    assert resultado["ok"] is True
    assert resultado["turnos"] == 1
    assert db.query(CopilotoTurno).filter_by(id=velho.id).first() is None


def test_turno_mais_novo_que_o_prazo_fica(db):
    novo = _turno(db, idade=timedelta(days=RETENCAO_DIAS - 1))
    resultado = _worker().run_once()
    assert resultado["turnos"] == 0
    assert db.query(CopilotoTurno).filter_by(id=novo.id).first() is not None


def test_fronteira_exata_do_prazo_fica(db):
    """corte = agora - retencao_dias; um turno EXATAMENTE no corte não é
    "mais velho que o prazo" — só o que é estritamente anterior sai."""
    na_fronteira = _turno(db, idade=timedelta(days=RETENCAO_DIAS))
    um_segundo_mais_velho = _turno(
        db, idade=timedelta(days=RETENCAO_DIAS) + timedelta(seconds=1),
        pergunta="outra?",
    )
    resultado = _worker().run_once()
    assert db.query(CopilotoTurno).filter_by(id=na_fronteira.id).first() is not None
    assert db.query(CopilotoTurno).filter_by(id=um_segundo_mais_velho.id).first() is None


def test_conversa_sem_turnos_restantes_some_junto(db):
    velho = _turno(db, idade=timedelta(days=RETENCAO_DIAS + 1))
    conversa_id = velho.conversa_id
    _worker().run_once()
    assert db.query(CopilotoTurno).filter_by(id=velho.id).first() is None
    assert db.query(CopilotoConversa).filter_by(id=conversa_id).first() is None


def test_conversa_com_turno_recente_permanece(db):
    velho = _turno(db, idade=timedelta(days=RETENCAO_DIAS + 1))
    velho_id, conversa_id = velho.id, velho.conversa_id
    recente = _turno(
        db, idade=timedelta(days=1), pergunta="e agora?", conversa_id=conversa_id,
    )
    recente_id = recente.id
    # Captura os IDs ANTES de rodar o worker: o commit de `_turno(recente=...)`
    # já expira os atributos de `velho` na sessão do teste (expire_on_commit),
    # e depois de o worker apagar a linha numa sessão separada, tocar em
    # `velho.id`/`velho.conversa_id` forçaria um refresh que não acha mais a
    # linha (ObjectDeletedError) — não é o que o teste quer verificar.
    resultado = _worker().run_once()
    assert resultado["turnos"] == 1
    assert db.query(CopilotoTurno).filter_by(id=velho_id).first() is None
    assert db.query(CopilotoTurno).filter_by(id=recente_id).first() is not None
    assert db.query(CopilotoConversa).filter_by(id=conversa_id).first() is not None


def test_copiloto_acao_sobrevive_mesmo_com_turno_de_origem_apagado(db):
    velho = _turno(db, idade=timedelta(days=RETENCAO_DIAS + 1))
    velho_id = velho.id
    db.add(
        CopilotoAcao(
            loja_slug="loja-teste",
            turno_id=velho_id,
            ator_email="dono@loja.test",
            acao="ajustar_preco",
            entidade_ref="v1",
            valor_anterior=Decimal("28000.00"),
            valor_novo=Decimal("25000.00"),
            estado="executada",
            executada_em=AGORA - timedelta(days=RETENCAO_DIAS + 1),
        )
    )
    db.commit()

    _worker().run_once()

    assert db.query(CopilotoTurno).filter_by(id=velho_id).first() is None
    acao = db.query(CopilotoAcao).one()
    assert acao.turno_id == velho_id  # referência solta, de propósito
    assert acao.estado == "executada"


def test_loja_operacao_auditoria_sobrevive_ao_purge(db):
    velho = _turno(db, idade=timedelta(days=RETENCAO_DIAS + 1))
    velho_id = velho.id
    db.add(
        LojaOperacaoAuditoria(
            loja_slug="loja-teste",
            dominio="copiloto",
            acao="ajustar_preco",
            ator_email="dono@loja.test",
            success=True,
            criado_em=AGORA - timedelta(days=RETENCAO_DIAS + 1),
        )
    )
    db.commit()

    _worker().run_once()

    assert db.query(CopilotoTurno).filter_by(id=velho_id).first() is None
    assert db.query(LojaOperacaoAuditoria).count() == 1


def test_turno_pendente_velho_nao_e_apagado(db):
    preso = _turno(db, idade=timedelta(days=RETENCAO_DIAS + 5), estado="pendente")
    resultado = _worker().run_once()
    assert resultado["turnos"] == 0
    assert db.query(CopilotoTurno).filter_by(id=preso.id).first() is not None


def test_turno_executando_velho_nao_e_apagado(db):
    preso = _turno(db, idade=timedelta(days=RETENCAO_DIAS + 5), estado="executando")
    resultado = _worker().run_once()
    assert resultado["turnos"] == 0
    assert db.query(CopilotoTurno).filter_by(id=preso.id).first() is not None


def test_purge_de_uma_loja_nao_toca_outra(db):
    velho_a = _turno(db, loja_slug="loja-a", idade=timedelta(days=RETENCAO_DIAS + 1))
    velho_b = _turno(db, loja_slug="loja-b", idade=timedelta(days=RETENCAO_DIAS + 1))
    velho_a_id, velho_b_id = velho_a.id, velho_b.id

    resultado = purgar_loja(
        db, "loja-a", corte=AGORA - timedelta(days=RETENCAO_DIAS), lote=1000
    )
    assert resultado["turnos"] == 1
    assert db.query(CopilotoTurno).filter_by(id=velho_a_id).first() is None
    assert db.query(CopilotoTurno).filter_by(id=velho_b_id).first() is not None


def test_teto_por_execucao_e_respeitado(db):
    for i in range(5):
        _turno(
            db, idade=timedelta(days=RETENCAO_DIAS + 1), pergunta=f"pergunta {i}?",
        )
    resultado = _worker(lote=2).run_once()
    assert resultado["turnos"] == 2
    assert db.query(CopilotoTurno).count() == 3


def test_desligado_nao_toca_o_banco(db):
    velho = _turno(db, idade=timedelta(days=RETENCAO_DIAS + 1))
    resultado = _worker(enabled=False).run_once()
    assert resultado["ok"] is False
    assert db.query(CopilotoTurno).filter_by(id=velho.id).first() is not None
