from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.clients.estoque import VeiculoNaoEncontrado
from app.loja.copiloto.acoes import (
    AcaoRecusada,
    desfazer_acao,
    executar_acao,
    validar_ajuste_preco,
)
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import CopilotoAcao, LojaOperacaoAuditoria

AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _ctx(loja_slug="loja-teste", ator_email="dono@loja.test"):
    return CopilotoContexto(
        loja_slug=loja_slug, papel="dono", ator_email=ator_email,
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    def __init__(self, preco=28000.0, slug="loja-teste", publicado=False):
        self.veiculo = {
            "id": "v1", "marca": "Honda", "modelo": "CB 500F", "ano_modelo": 2020,
            "preco": preco, "status": "disponivel", "publicado": publicado,
        }
        self.slug = slug
        self.patches = []
        self.acoes = []

    def obter_loja(self):
        return {"slug": self.slug}

    def obter(self, veiculo_id):
        if veiculo_id != "v1":
            raise VeiculoNaoEncontrado("não existe")
        return dict(self.veiculo)

    def atualizar(self, veiculo_id, dados):
        self.patches.append((veiculo_id, dados))
        self.veiculo.update(dados)
        return dict(self.veiculo)

    def acao(self, veiculo_id, acao):
        self.acoes.append((veiculo_id, acao))
        # Simula o efeito real do verbo — sem isto, os testes de desfazer de
        # publicação (I-1) não conseguem distinguir "publicado" de
        # "despublicado" na releitura, e a guarda 5 do desfazer (I-2) não
        # tem nada de real para comparar.
        if acao == "publicar":
            self.veiculo["publicado"] = True
        elif acao == "despublicar":
            self.veiculo["publicado"] = False
        return {"ok": True}


# --- validar_ajuste_preco: banda, piso, não-finitos (I-6) -----------------


def test_banda_aceita_ajuste_dentro_do_limite():
    assert validar_ajuste_preco(Decimal("28000"), Decimal("25000")) == Decimal("25000.00")


def test_banda_recusa_corte_absurdo():
    # R$ 5.000 está ACIMA do piso de R$ 1.000 (default) — só a banda pode
    # recusar este valor, e é exatamente isso que este teste existe para
    # provar. Com um valor abaixo do piso, o piso recusaria primeiro e o
    # teste passaria sem exercitar a banda.
    with pytest.raises(AcaoRecusada) as exc:
        validar_ajuste_preco(Decimal("28000"), Decimal("5000"))
    assert exc.value.code == "banda"


def test_banda_recusa_aumento_absurdo():
    with pytest.raises(AcaoRecusada) as exc:
        validar_ajuste_preco(Decimal("28000"), Decimal("90000"))
    assert exc.value.code == "banda"


def test_piso_recusa_preco_ridiculo():
    with pytest.raises(AcaoRecusada) as exc:
        validar_ajuste_preco(Decimal("1200"), Decimal("999"))
    assert exc.value.code in {"piso", "banda"}


@pytest.mark.parametrize("valor_hostil", ["NaN", "Infinity", "-Infinity"])
def test_validar_ajuste_preco_recusa_nao_finito(valor_hostil):
    """I-6: json.loads aceita o literal NaN — um payload de tool-call do LLM
    com "novo_preco": NaN não pode virar 500 (decimal.InvalidOperation)."""
    with pytest.raises(AcaoRecusada) as exc:
        validar_ajuste_preco(Decimal("28000"), valor_hostil)
    assert exc.value.code == "preco_invalido"


# --- executar_acao: whitelist, preco_esperado obrigatório (C-1) -----------


def test_acao_fora_da_whitelist_e_recusada(db):
    with pytest.raises(AcaoRecusada) as exc:
        executar_acao(
            db, _ctx(), acao="apagar_veiculo", parametros={"veiculo_id": "v1"},
            estoque=EstoqueStub(), agora=AGORA,
        )
    assert exc.value.code == "acao_invalida"


def test_ajustar_preco_sem_preco_esperado_e_recusado(db):
    """C-1 (Critical): sem preco_esperado a guarda 5 vira opcional — some.
    O cartão sempre sabe o preço que mostrou; não existe caso legítimo sem
    ele. A rede nunca deve ser tocada."""
    estoque = EstoqueStub(preco=28000.0)
    with pytest.raises(AcaoRecusada) as exc:
        executar_acao(
            db, _ctx(), acao="ajustar_preco",
            parametros={"veiculo_id": "v1", "novo_preco": "25000"},
            estoque=estoque, agora=AGORA,
        )
    assert exc.value.code == "preco_esperado_ausente"
    assert estoque.patches == []
    assert db.query(CopilotoAcao).count() == 0


def test_ajustar_preco_faz_patch_e_grava_anterior(db):
    estoque = EstoqueStub(preco=28000.0)
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={
            "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
        },
        estoque=estoque, agora=AGORA,
    )
    assert estoque.patches == [("v1", {"preco": 25000.0})]
    assert registro.valor_anterior == Decimal("28000.00")
    assert registro.valor_novo == Decimal("25000.00")
    assert registro.estado == "executada"
    assert registro.desfazer_ate > AGORA


def test_ajustar_preco_grava_auditoria(db):
    executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={
            "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
        },
        estoque=EstoqueStub(), agora=AGORA,
    )
    linha = db.query(LojaOperacaoAuditoria).one()
    assert linha.dominio == "copiloto"
    assert linha.acao == "ajustar_preco"
    assert linha.ator_email == "dono@loja.test"


def test_preco_divergente_do_cartao_aborta(db):
    """Alguém mexeu no preço entre o cartão e o clique: não sobrescreve."""
    estoque = EstoqueStub(preco=26000.0)
    with pytest.raises(AcaoRecusada) as exc:
        executar_acao(
            db, _ctx(), acao="ajustar_preco",
            parametros={
                "veiculo_id": "v1", "novo_preco": "25000",
                "preco_esperado": "28000",
            },
            estoque=estoque, agora=AGORA,
        )
    assert exc.value.code == "divergencia"
    assert estoque.patches == []


def test_veiculo_de_outra_loja_falha_fechado(db):
    with pytest.raises(AcaoRecusada) as exc:
        executar_acao(
            db, _ctx(), acao="ajustar_preco",
            parametros={
                "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
            },
            estoque=EstoqueStub(slug="outra-loja"), agora=AGORA,
        )
    assert exc.value.code == "escopo"


def test_veiculo_inexistente_tem_erro_proprio(db):
    with pytest.raises(AcaoRecusada) as exc:
        executar_acao(
            db, _ctx(), acao="ajustar_preco",
            parametros={
                "veiculo_id": "v99", "novo_preco": "25000", "preco_esperado": "28000",
            },
            estoque=EstoqueStub(), agora=AGORA,
        )
    assert exc.value.code == "nao_encontrado"


# --- ações de publicação: verbo certo + estado_anterior (I-1) -------------


def test_repostar_veiculo_publica(db):
    estoque = EstoqueStub()
    registro = executar_acao(
        db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    assert estoque.acoes == [("v1", "publicar")]
    assert registro.estado == "executada"
    assert registro.estado_anterior == "despublicar"


def test_despublicar_veiculo_manda_o_verbo_despublicar(db):
    """Sem isto, despublicar_veiculo publicaria o veículo — o oposto do
    que o dono confirmou no cartão."""
    estoque = EstoqueStub()
    executar_acao(
        db, _ctx(), acao="despublicar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    assert estoque.acoes == [("v1", "despublicar")]


def test_publicar_veiculo_manda_o_verbo_publicar(db):
    estoque = EstoqueStub()
    executar_acao(
        db, _ctx(), acao="publicar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    assert estoque.acoes == [("v1", "publicar")]


def test_verbo_estoque_cobre_toda_acao_nao_preco():
    """Se alguém acrescentar uma ação à whitelist e esquecer o verbo
    correspondente, o KeyError só apareceria em produção, no clique do
    dono — este teste move essa falha para o CI."""
    from app.loja.copiloto.acoes import ACOES_PERMITIDAS, VERBO_ESTOQUE

    assert set(VERBO_ESTOQUE) == ACOES_PERMITIDAS - {"ajustar_preco"}


# --- rate-limit: janela, isolamento por loja, conta falhas (I-3, I-7) -----


def test_rate_limit_por_hora(db, monkeypatch):
    monkeypatch.setenv("PORTAL_COPILOTO_MAX_ACOES_HORA", "1")
    estoque = EstoqueStub()
    executar_acao(
        db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    with pytest.raises(AcaoRecusada) as exc:
        executar_acao(
            db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
            estoque=estoque, agora=AGORA + timedelta(minutes=1),
        )
    assert exc.value.code == "rate_limit"


def test_rate_limit_conta_so_a_ultima_hora(db, monkeypatch):
    """Mata a mutação hours=1 -> hours=1000: uma ação de 2h atrás não pode
    contar contra o limite da hora corrente."""
    monkeypatch.setenv("PORTAL_COPILOTO_MAX_ACOES_HORA", "1")
    estoque = EstoqueStub()
    executar_acao(
        db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA - timedelta(hours=2),
    )
    registro = executar_acao(
        db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    assert registro.estado == "executada"


def test_rate_limit_e_por_loja(db, monkeypatch):
    """Mata a mutação que remove o filtro loja_slug do rate-limit: uma loja
    esgotar a cota não pode bloquear outra loja."""
    monkeypatch.setenv("PORTAL_COPILOTO_MAX_ACOES_HORA", "1")
    executar_acao(
        db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=EstoqueStub(), agora=AGORA,
    )
    outra_ctx = _ctx(loja_slug="outra-loja", ator_email="d@outra.test")
    registro = executar_acao(
        db, outra_ctx, acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=EstoqueStub(slug="outra-loja"), agora=AGORA + timedelta(minutes=1),
    )
    assert registro.estado == "executada"


def test_rate_limit_conta_tentativas_que_falharam(db, monkeypatch):
    """I-3 (Important): um laço martelando o botão com a estoque-api fora do
    ar precisa ser freado — não só sucessos. Mata a mutação que exclui
    estado == "falhou" da contagem."""
    monkeypatch.setenv("PORTAL_COPILOTO_MAX_ACOES_HORA", "1")

    class EstoqueQuebrado(EstoqueStub):
        def acao(self, veiculo_id, acao):
            raise RuntimeError("boom")

    estoque = EstoqueQuebrado()
    with pytest.raises(AcaoRecusada) as exc1:
        executar_acao(
            db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
            estoque=estoque, agora=AGORA,
        )
    assert exc1.value.code == "execucao"

    with pytest.raises(AcaoRecusada) as exc2:
        executar_acao(
            db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
            estoque=estoque, agora=AGORA + timedelta(minutes=1),
        )
    assert exc2.value.code == "rate_limit"


# --- falha e a janela pendente->executada/falhou (I-5) ---------------------


def test_falha_no_estoque_grava_acao_como_falhou(db):
    class EstoqueQuebrado(EstoqueStub):
        def atualizar(self, veiculo_id, dados):
            raise RuntimeError("boom")

    with pytest.raises(AcaoRecusada):
        executar_acao(
            db, _ctx(), acao="ajustar_preco",
            parametros={
                "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
            },
            estoque=EstoqueQuebrado(), agora=AGORA,
        )
    linha_acao = db.query(CopilotoAcao).one()
    assert linha_acao.estado == "falhou"
    # Mata a mutação que remove registrar_auditoria_copiloto(success=False)
    # do caminho de falha.
    linha_auditoria = db.query(LojaOperacaoAuditoria).one()
    assert linha_auditoria.success is False
    assert linha_auditoria.error_code == "RuntimeError"


def test_queda_apos_patch_deixa_linha_pendente(db, monkeypatch):
    """I-5 (Important): se o processo morre entre o PATCH real e o commit
    que promove a linha para "executada", a linha "pendente" — comitada
    ANTES da escrita — é o único rastro de que o preço da loja mudou."""
    from app.db import SessionLocal

    estoque = EstoqueStub(preco=28000.0)
    commit_original = db.commit
    chamadas = {"n": 0}

    def commit_instavel():
        chamadas["n"] += 1
        if chamadas["n"] >= 2:
            raise RuntimeError("processo caiu aqui, depois do PATCH")
        return commit_original()

    monkeypatch.setattr(db, "commit", commit_instavel)
    with pytest.raises(RuntimeError):
        executar_acao(
            db, _ctx(), acao="ajustar_preco",
            parametros={
                "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
            },
            estoque=estoque, agora=AGORA,
        )
    # o PATCH de fato aconteceu no estoque real
    assert estoque.patches == [("v1", {"preco": 25000.0})]

    monkeypatch.setattr(db, "commit", commit_original)
    # sessão separada: lê o que está REALMENTE persistido, sem o cache de
    # identidade da sessão que sofreu a queda simulada (senão o Python
    # devolveria o estado="executada" só em memória, nunca comitado).
    outra_sessao = SessionLocal()
    try:
        linha = outra_sessao.query(CopilotoAcao).one()
        assert linha.estado == "pendente"
    finally:
        outra_sessao.close()


# --- desfazer: prazo, releitura antes de escrever (I-2), isolamento -------


def test_desfazer_restaura_o_preco_anterior(db):
    estoque = EstoqueStub(preco=28000.0)
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={
            "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
        },
        estoque=estoque, agora=AGORA,
    )
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=AGORA) is True
    assert estoque.veiculo["preco"] == 28000.0
    db.refresh(registro)
    assert registro.estado == "desfeita"


def test_desfazer_fora_do_prazo_nao_funciona(db):
    estoque = EstoqueStub()
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={
            "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
        },
        estoque=estoque, agora=AGORA,
    )
    tarde = AGORA + timedelta(hours=3)
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=tarde) is False


def test_desfazer_aborta_se_preco_mudou_depois_da_acao(db):
    """I-2 (Important): a guarda 5 vale para o desfazer também. Outra
    pessoa reprecificou depois do Copiloto — restaurar por cima apagaria o
    trabalho dela, exatamente como o C-1 do lado da execução."""
    estoque = EstoqueStub(preco=28000.0)
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={
            "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
        },
        estoque=estoque, agora=AGORA,
    )
    # terceiro reprecifica depois da ação do Copiloto
    estoque.veiculo["preco"] = 24000.0
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=AGORA) is False
    assert estoque.veiculo["preco"] == 24000.0
    assert len(estoque.patches) == 1  # só o PATCH original da ação


def test_desfazer_restaura_publicacao_apos_repostar(db):
    """I-1 (Important): o desfazer de publicar/despublicar tinha virado
    decorativo — a linha prometia "desfazível" e o clique não fazia nada."""
    estoque = EstoqueStub()  # publicado=False antes da ação
    registro = executar_acao(
        db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    assert estoque.veiculo["publicado"] is True
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=AGORA) is True
    assert estoque.veiculo["publicado"] is False
    assert estoque.acoes == [("v1", "publicar"), ("v1", "despublicar")]
    db.refresh(registro)
    assert registro.estado == "desfeita"


def test_desfazer_restaura_publicacao_apos_despublicar(db):
    estoque = EstoqueStub(publicado=True)  # já publicado antes da ação
    registro = executar_acao(
        db, _ctx(), acao="despublicar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    assert estoque.veiculo["publicado"] is False
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=AGORA) is True
    assert estoque.veiculo["publicado"] is True


def test_desfazer_de_publicacao_aborta_se_estado_mudou_depois(db):
    """Mesma guarda 5, lado da publicação: alguém despublicou de novo por
    fora do Copiloto — o desfazer não pode assumir por cima disso."""
    estoque = EstoqueStub()
    registro = executar_acao(
        db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    estoque.veiculo["publicado"] = False  # terceiro mexeu depois
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=AGORA) is False
    assert estoque.acoes == [("v1", "publicar")]  # nenhuma chamada extra


def test_desfazer_de_publicacao_sem_estado_anterior_nao_funciona(db):
    """Linha de antes da migration 0022 (sem estado_anterior gravado):
    falha fechado em vez de adivinhar o verbo de restauração."""
    estoque = EstoqueStub()
    registro = CopilotoAcao(
        loja_slug="loja-teste", ator_email="dono@loja.test", acao="repostar_veiculo",
        entidade_ref="v1", estado_anterior=None, estado="executada",
        executada_em=AGORA, desfazer_ate=AGORA + timedelta(minutes=30),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=AGORA) is False


def test_desfazer_falha_se_credencial_do_estoque_aponta_outra_loja(db):
    """Guarda 3 dentro do desfazer: mesmo com o registro certo, se o
    EstoqueClient injetado responde por outra loja, aborta."""
    estoque = EstoqueStub()
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={
            "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
        },
        estoque=estoque, agora=AGORA,
    )
    estoque_errado = EstoqueStub(slug="outra-loja")
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque_errado, agora=AGORA) is False


def test_desfazer_respeita_isolamento_por_loja_na_consulta(db):
    """Mata a mutação que remove o filtro loja_slug da query do desfazer.

    O teste antigo ("de outra loja não funciona") passava pelo motivo
    errado: o mismatch de garantir_escopo_loja escondia o filtro de
    isolamento nunca sendo exercitado. Aqui a credencial do estoque
    injetado BATE com o contexto de "outra-loja" (guarda 3 não pode ser o
    motivo do False) e o preço atual do veículo dessa outra loja BATE com o
    valor_novo da ação original (guarda 5/I-2 não pode ser o motivo do
    False) — o único jeito de isto retornar False é o filtro loja_slug da
    query.
    """
    estoque = EstoqueStub(preco=28000.0)
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={
            "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000",
        },
        estoque=estoque, agora=AGORA,
    )
    outro_ctx = _ctx(loja_slug="outra-loja", ator_email="x@outra.test")
    outro_estoque = EstoqueStub(preco=25000.0, slug="outra-loja")
    assert desfazer_acao(db, outro_ctx, registro.id, estoque=outro_estoque, agora=AGORA) is False
    assert outro_estoque.patches == []


def test_desfazer_duas_vezes_a_segunda_nao_funciona(db):
    """Mata a mutação que remove o filtro estado == "executada" da query do
    desfazer. Constrói a linha já "desfeita" com valor_novo == preço atual
    do estoque de propósito: se o filtro de estado sumir, nada mais nesta
    função (nem a guarda de divergência) impediria um segundo desfazer."""
    estoque = EstoqueStub(preco=28000.0)
    registro = CopilotoAcao(
        loja_slug="loja-teste", ator_email="dono@loja.test", acao="ajustar_preco",
        entidade_ref="v1", valor_anterior=Decimal("30000.00"),
        valor_novo=Decimal("28000.00"), estado="desfeita",
        executada_em=AGORA, desfazer_ate=AGORA + timedelta(minutes=30),
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=AGORA) is False
    assert estoque.patches == []
