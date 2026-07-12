from datetime import date, timedelta
from decimal import Decimal

import pytest

from conftest import csrf_da_resposta, login

from app.db import SessionLocal
from app.main import ultimo_dia_mes
from app.models import Meta


def periodo_atual():
    hoje = date.today()
    return hoje.replace(day=1), ultimo_dia_mes(hoje)


def dados_meta(tipo="quantidade", alvo="4", inicio=None, fim=None):
    padrao_inicio, padrao_fim = periodo_atual()
    return {
        "tipo": tipo,
        "valor_alvo": alvo,
        "periodo_inicio": (inicio or padrao_inicio).isoformat(),
        "periodo_fim": (fim or padrao_fim).isoformat(),
    }


def criar_meta(loja_slug="loja-teste", tipo="quantidade", ativa=True, inicio=None, fim=None):
    padrao_inicio, padrao_fim = periodo_atual()
    db = SessionLocal()
    meta = Meta(
        loja_slug=loja_slug,
        escopo="loja",
        tipo=tipo,
        periodo_inicio=inicio or padrao_inicio,
        periodo_fim=fim or padrao_fim,
        valor_alvo=Decimal("4"),
        ativa=ativa,
    )
    db.add(meta)
    db.commit()
    meta_id = meta.id
    db.close()
    return meta_id


def csrf_metas(client):
    return csrf_da_resposta(client.get("/app/metas"))


def test_dono_cria_meta_e_dashboard_reflete_imediatamente(client):
    login(client)
    pagina = client.get("/app/metas/nova")
    resposta = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_da_resposta(pagina), **dados_meta(alvo="5")},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/metas?ok=criada"
    db = SessionLocal()
    meta = db.query(Meta).one()
    assert meta.loja_slug == "loja-teste"
    assert meta.valor_alvo == Decimal("5.00")
    assert meta.ativa is True
    db.close()
    financeiro = client.get("/app/financeiro")
    assert "meta: 5" in financeiro.text
    assert "0.0%" in financeiro.text


def test_gerente_edita_meta_ativa(client):
    meta_id = criar_meta()
    login(client, papel="gerente")
    pagina = client.get(f"/app/metas/{meta_id}/editar")
    resposta = client.post(
        f"/app/metas/{meta_id}/editar",
        data={"csrf": csrf_da_resposta(pagina), **dados_meta(tipo="faturamento", alvo="125000")},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    db = SessionLocal()
    meta = db.get(Meta, meta_id)
    assert meta.tipo == "faturamento"
    assert meta.valor_alvo == Decimal("125000.00")
    db.close()


def test_vendedor_consulta_mas_nao_pode_criar_ou_editar(client):
    meta_id = criar_meta()
    login(client, papel="vendedor")
    lista = client.get("/app/metas")
    assert lista.status_code == 200
    assert "Quantidade de vendas" in lista.text
    assert "Cadastrar meta" not in lista.text
    assert client.get("/app/metas/nova", follow_redirects=False).headers["location"] == "/app/metas"
    resposta = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_metas(client), **dados_meta(tipo="faturamento", alvo="10")},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/app/metas"
    resposta = client.post(
        f"/app/metas/{meta_id}/desativar",
        data={"csrf": csrf_metas(client)},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/app/metas"
    db = SessionLocal()
    assert db.query(Meta).count() == 1
    assert db.get(Meta, meta_id).ativa is True
    db.close()


@pytest.mark.parametrize(
    ("alteracoes", "mensagem"),
    [
        ({"valor_alvo": "0"}, "maior que zero"),
        ({"tipo": "conversao"}, "tipo de meta válido"),
        ({"periodo_inicio": "2026-02-02", "periodo_fim": "2026-02-01"}, "data inicial"),
        ({"tipo": "quantidade", "valor_alvo": "1.5"}, "número inteiro"),
    ],
)
def test_validacao_da_meta(client, alteracoes, mensagem):
    login(client)
    pagina = client.get("/app/metas/nova")
    dados = dados_meta()
    dados.update(alteracoes)
    resposta = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_da_resposta(pagina), **dados},
    )
    assert resposta.status_code == 422
    assert mensagem in resposta.text
    db = SessionLocal()
    assert db.query(Meta).count() == 0
    db.close()


def test_bloqueia_sobreposicao_ativa_do_mesmo_tipo(client):
    inicio, fim = periodo_atual()
    criar_meta(inicio=inicio, fim=fim)
    login(client)
    pagina = client.get("/app/metas/nova")
    resposta = client.post(
        "/app/metas/nova",
        data={
            "csrf": csrf_da_resposta(pagina),
            **dados_meta(inicio=inicio + timedelta(days=1), fim=fim),
        },
    )
    assert resposta.status_code == 422
    assert "sobrepondo o período" in resposta.text
    db = SessionLocal()
    assert db.query(Meta).count() == 1
    db.close()


def test_desativar_libera_periodo_para_nova_meta(client):
    meta_id = criar_meta()
    login(client)
    resposta = client.post(
        f"/app/metas/{meta_id}/desativar",
        data={"csrf": csrf_metas(client)},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/app/metas?ok=desativada"
    pagina = client.get("/app/metas/nova")
    nova = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_da_resposta(pagina), **dados_meta(alvo="6")},
        follow_redirects=False,
    )
    assert nova.headers["location"] == "/app/metas?ok=criada"
    db = SessionLocal()
    assert db.query(Meta).filter(Meta.ativa.is_(True)).count() == 1
    assert db.query(Meta).filter(Meta.ativa.is_(False)).count() == 1
    db.close()


def test_nao_edita_nem_desativa_meta_de_outra_loja(client):
    meta_id = criar_meta(loja_slug="outra-loja")
    login(client)
    assert client.get(f"/app/metas/{meta_id}/editar", follow_redirects=False).headers["location"] == "/app/metas?erro=nao-encontrada"
    resposta = client.post(
        f"/app/metas/{meta_id}/desativar",
        data={"csrf": csrf_metas(client)},
        follow_redirects=False,
    )
    assert resposta.headers["location"] == "/app/metas?erro=nao-encontrada"
    db = SessionLocal()
    assert db.get(Meta, meta_id).ativa is True
    db.close()


def test_meta_inativa_nao_aparece_no_dashboard(client):
    criar_meta(ativa=False)
    login(client)
    resposta = client.get("/app/financeiro")
    assert "Nenhuma meta da loja para o período" in resposta.text
