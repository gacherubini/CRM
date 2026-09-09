"""Trocar a loja muda dados e permissões de vendas, sem alterar o usuário."""
from decimal import Decimal

import pytest

from conftest import csrf_da_resposta, login, seed_loja_operacional
from app.db import SessionLocal
from app.models import LojaOperacionalProjecao, Usuario, Venda
from test_loja_identity import _selecionar, _semear_vinculos
from test_loja_vendas_registro import _criar_venda


def _trocar(client, monkeypatch, cargo="dono"):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    _semear_vinculos("dono@loja.test", ["loja-b"], cargo=cargo)
    with SessionLocal() as db:
        for slug in ("loja-teste", "loja-b"):
            db.add(LojaOperacionalProjecao(
                loja_slug=slug, aggregate="vendas", state="ativo",
                version=1, event_id=f"vendas-{slug}",
            ))
        db.commit()
    resposta = _selecionar(client, "loja-b")
    assert resposta.headers["location"] == "/app"


@pytest.mark.parametrize("rota", ["/app/loja/vendas/lista", "/app/vendas"])
def test_lista_usa_loja_selecionada(client, monkeypatch, rota):
    _trocar(client, monkeypatch)
    _criar_venda(descricao="Venda somente A")
    _criar_venda(loja_slug="loja-b", descricao="Venda somente B")
    pagina = client.get(rota)
    assert pagina.status_code == 200
    assert "Venda somente B" in pagina.text
    assert "Venda somente A" not in pagina.text


def test_criar_grava_na_loja_selecionada_sem_mudar_usuario(client, monkeypatch):
    _trocar(client, monkeypatch)
    csrf = csrf_da_resposta(client.get("/app/vendas/nova?origem=loja"))
    resposta = client.post("/app/vendas/nova?origem=loja", data={
        "csrf": csrf, "descricao": "Venda criada em B", "preco_venda": "15000",
    }, follow_redirects=False)
    assert "ok=registrada" in resposta.headers["location"]
    with SessionLocal() as db:
        assert db.query(Venda).one().loja_slug == "loja-b"
        usuario = db.query(Usuario).filter_by(email="dono@loja.test").one()
        assert (usuario.loja_slug, usuario.papel) == ("loja-teste", "dono")


@pytest.mark.parametrize("prefixo", ["/app/loja/vendas", "/app/vendas"])
@pytest.mark.parametrize("acao", ["confirmar", "cancelar"])
def test_acao_atinge_so_venda_da_loja_selecionada(client, monkeypatch, prefixo, acao):
    _trocar(client, monkeypatch)
    a = _criar_venda()
    b = _criar_venda(loja_slug="loja-b")
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))
    for venda_id in (a, b):
        resposta = client.post(f"{prefixo}/{venda_id}/{acao}", data={
            "csrf": csrf, "motivo": "Cliente desistiu",
        }, follow_redirects=False)
        assert ("erro=acao" if venda_id == a else "ok=") in resposta.headers["location"]
    with SessionLocal() as db:
        assert db.get(Venda, a).status == "registrada"
        assert db.get(Venda, b).status == {"confirmar": "confirmada", "cancelar": "cancelada"}[acao]


def test_editar_e_excluir_respeitam_loja_ativa(client, monkeypatch):
    _trocar(client, monkeypatch)
    a = _criar_venda()
    b = _criar_venda(loja_slug="loja-b")
    assert "erro=acao" in client.get(f"/app/loja/vendas/{a}/editar", follow_redirects=False).headers["location"]
    pagina = client.get(f"/app/loja/vendas/{b}/editar")
    assert pagina.status_code == 200
    csrf = csrf_da_resposta(pagina)
    client.post(f"/app/loja/vendas/{b}/editar", data={
        "csrf": csrf, "descricao": "Corrigida B", "preco_venda": "18000",
    }, follow_redirects=False)
    for venda_id in (a, b):
        client.post(f"/app/loja/vendas/{venda_id}/excluir", data={"csrf": csrf}, follow_redirects=False)
    with SessionLocal() as db:
        assert db.get(Venda, a).status == "registrada"
        assert db.get(Venda, b).status == "excluida"
        assert db.get(Venda, b).preco_venda == Decimal("18000")


def test_cargo_dono_da_origem_nao_vira_gestao_na_loja_b(client, monkeypatch):
    _trocar(client, monkeypatch, cargo="vendedor")
    propria = _criar_venda(loja_slug="loja-b", vendedor_email="dono@loja.test", descricao="Venda propria B")
    _criar_venda(loja_slug="loja-b", descricao="Venda colega B")
    pagina = client.get("/app/loja/vendas/lista")
    assert "Venda propria B" in pagina.text
    assert "Venda colega B" not in pagina.text
    assert client.get(f"/app/loja/vendas/{propria}/editar").status_code == 403
    csrf = csrf_da_resposta(pagina)
    client.post(f"/app/loja/vendas/{propria}/excluir", data={"csrf": csrf}, follow_redirects=False)
    with SessionLocal() as db:
        assert db.get(Venda, propria).status == "registrada"


def test_vinculo_revogado_nao_cai_silenciosamente_na_loja_de_origem(client, monkeypatch):
    from app.models import VinculoLojaPessoa
    _trocar(client, monkeypatch)
    with SessionLocal() as db:
        db.query(VinculoLojaPessoa).filter_by(loja_slug="loja-b").update({"state": "revogado"})
        db.commit()
    assert client.get("/app/loja/vendas/lista").status_code == 403


def test_suspensao_da_loja_ativa_bloqueia_confirmacao(client, monkeypatch):
    _trocar(client, monkeypatch)
    b = _criar_venda(loja_slug="loja-b")
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))
    with SessionLocal() as db:
        seed_loja_operacional(db, "loja-b", state="suspensa", version=2)
        db.commit()
    resposta = client.post(f"/app/loja/vendas/{b}/confirmar", data={"csrf": csrf}, follow_redirects=False)
    assert resposta.status_code == 403
    with SessionLocal() as db:
        assert db.get(Venda, b).status == "registrada"


def test_resultado_conta_so_confirmadas_da_loja_ativa(client, monkeypatch):
    _trocar(client, monkeypatch)
    _criar_venda(status="confirmada")
    _criar_venda(status="confirmada")
    _criar_venda(loja_slug="loja-b", status="confirmada")
    dados = client.get("/app/loja/vendas/dados")
    assert dados.status_code == 200
    assert dados.json()["qtd_vendas"] == 1


def test_custo_direto_respeita_loja_selecionada(client, monkeypatch):
    from app.models import VendaCustoDireto
    _trocar(client, monkeypatch)
    a = _criar_venda()
    b = _criar_venda(loja_slug="loja-b")
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))
    for venda_id in (a, b):
        client.post(f"/app/loja/vendas/{venda_id}/custos", data={
            "csrf": csrf, "categoria": "frete", "valor": "300",
        }, follow_redirects=False)
    with SessionLocal() as db:
        assert not db.get(Venda, a).custos_diretos
        custo = db.get(Venda, b).custos_diretos[0]
        custo_id = custo.id
        assert custo.valor == Decimal("300")
    client.post(f"/app/loja/vendas/{a}/custos/{custo_id}/remover", data={"csrf": csrf}, follow_redirects=False)
    with SessionLocal() as db:
        assert db.get(VendaCustoDireto, custo_id) is not None
    client.post(f"/app/loja/vendas/{b}/custos/{custo_id}/remover", data={"csrf": csrf}, follow_redirects=False)
    with SessionLocal() as db:
        assert db.get(VendaCustoDireto, custo_id) is None


def test_formulario_nao_oferece_veiculos_da_credencial_de_outra_loja(client, monkeypatch):
    _trocar(client, monkeypatch)
    pagina = client.get("/app/vendas/nova")
    assert pagina.status_code == 200
    assert 'value="v1"' not in pagina.text
    assert 'value="v2"' not in pagina.text


def test_confirmacao_nao_baixa_veiculo_com_credencial_de_outra_loja(client, monkeypatch, estoque_fake):
    _trocar(client, monkeypatch)
    b = _criar_venda(loja_slug="loja-b")
    with SessionLocal() as db:
        db.get(Venda, b).veiculo_ref = "v1"
        db.commit()
    csrf = csrf_da_resposta(client.get("/app/loja/vendas/lista"))
    resposta = client.post(f"/app/loja/vendas/{b}/confirmar", data={"csrf": csrf}, follow_redirects=False)
    assert "erro=estoque-indisponivel" in resposta.headers["location"]
    assert estoque_fake.acoes == []
    with SessionLocal() as db:
        assert db.get(Venda, b).status == "registrada"
