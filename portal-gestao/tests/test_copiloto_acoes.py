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


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste", papel="dono", ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    def __init__(self, preco=28000.0, slug="loja-teste"):
        self.veiculo = {
            "id": "v1", "marca": "Honda", "modelo": "CB 500F", "ano_modelo": 2020,
            "preco": preco, "status": "disponivel", "publicado": False,
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
        return {"ok": True}


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
    with pytest.raises(AcaoRecusada):
        validar_ajuste_preco(Decimal("28000"), Decimal("90000"))


def test_piso_recusa_preco_ridiculo():
    with pytest.raises(AcaoRecusada) as exc:
        validar_ajuste_preco(Decimal("1200"), Decimal("999"))
    assert exc.value.code in {"piso", "banda"}


def test_acao_fora_da_whitelist_e_recusada(db):
    with pytest.raises(AcaoRecusada) as exc:
        executar_acao(
            db, _ctx(), acao="apagar_veiculo", parametros={"veiculo_id": "v1"},
            estoque=EstoqueStub(), agora=AGORA,
        )
    assert exc.value.code == "acao_invalida"


def test_ajustar_preco_faz_patch_e_grava_anterior(db):
    estoque = EstoqueStub(preco=28000.0)
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={"veiculo_id": "v1", "novo_preco": "25000"},
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
        parametros={"veiculo_id": "v1", "novo_preco": "25000"},
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
            parametros={"veiculo_id": "v1", "novo_preco": "25000"},
            estoque=EstoqueStub(slug="outra-loja"), agora=AGORA,
        )
    assert exc.value.code == "escopo"


def test_veiculo_inexistente_tem_erro_proprio(db):
    with pytest.raises(AcaoRecusada) as exc:
        executar_acao(
            db, _ctx(), acao="ajustar_preco",
            parametros={"veiculo_id": "v99", "novo_preco": "25000"},
            estoque=EstoqueStub(), agora=AGORA,
        )
    assert exc.value.code == "nao_encontrado"


def test_repostar_veiculo_publica(db):
    estoque = EstoqueStub()
    registro = executar_acao(
        db, _ctx(), acao="repostar_veiculo", parametros={"veiculo_id": "v1"},
        estoque=estoque, agora=AGORA,
    )
    assert estoque.acoes == [("v1", "publicar")]
    assert registro.estado == "executada"


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


def test_desfazer_restaura_o_preco_anterior(db):
    estoque = EstoqueStub(preco=28000.0)
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={"veiculo_id": "v1", "novo_preco": "25000"},
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
        parametros={"veiculo_id": "v1", "novo_preco": "25000"},
        estoque=estoque, agora=AGORA,
    )
    tarde = AGORA + timedelta(hours=3)
    assert desfazer_acao(db, _ctx(), registro.id, estoque=estoque, agora=tarde) is False


def test_desfazer_acao_de_outra_loja_nao_funciona(db):
    estoque = EstoqueStub()
    registro = executar_acao(
        db, _ctx(), acao="ajustar_preco",
        parametros={"veiculo_id": "v1", "novo_preco": "25000"},
        estoque=estoque, agora=AGORA,
    )
    outro = CopilotoContexto(
        loja_slug="outra-loja", papel="dono", ator_email="x@o.test",
        hoje=date(2026, 8, 11),
    )
    assert desfazer_acao(db, outro, registro.id, estoque=estoque, agora=AGORA) is False


def test_falha_no_estoque_grava_acao_como_falhou(db):
    class EstoqueQuebrado(EstoqueStub):
        def atualizar(self, veiculo_id, dados):
            raise RuntimeError("boom")

    with pytest.raises(AcaoRecusada):
        executar_acao(
            db, _ctx(), acao="ajustar_preco",
            parametros={"veiculo_id": "v1", "novo_preco": "25000"},
            estoque=EstoqueQuebrado(), agora=AGORA,
        )
    assert db.query(CopilotoAcao).one().estado == "falhou"
