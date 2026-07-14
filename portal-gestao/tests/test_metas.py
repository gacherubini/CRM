from datetime import date, timedelta
from decimal import Decimal

import pytest

from conftest import criar_usuario, csrf_da_resposta, login

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


def test_gerente_converte_meta_da_loja_em_meta_individual(client):
    criar_usuario(papel="vendedor", email="vendedor@loja.test")
    meta_id = criar_meta()
    login(client, papel="gerente")
    pagina = client.get(f"/app/metas/{meta_id}/editar")
    assert 'value="loja"' in pagina.text
    resposta = client.post(
        f"/app/metas/{meta_id}/editar",
        data={"csrf": csrf_da_resposta(pagina), **dados_meta_vendedor("vendedor@loja.test")},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    db = SessionLocal()
    meta = db.get(Meta, meta_id)
    assert meta.escopo == "vendedor"
    assert meta.vendedor_email == "vendedor@loja.test"
    db.close()
    pagina_editada = client.get(f"/app/metas/{meta_id}/editar")
    assert 'value="vendedor@loja.test" selected' in pagina_editada.text


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


def dados_meta_vendedor(vendedor_email, tipo="quantidade", alvo="3", inicio=None, fim=None):
    dados = dados_meta(tipo=tipo, alvo=alvo, inicio=inicio, fim=fim)
    dados["escopo"] = "vendedor"
    dados["vendedor_email"] = vendedor_email
    return dados


def test_dono_cria_meta_por_vendedor(client):
    criar_usuario(papel="vendedor", email="vendedor@loja.test")
    login(client)
    pagina = client.get("/app/metas/nova")
    assert "vendedor@loja.test" in pagina.text
    resposta = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_da_resposta(pagina), **dados_meta_vendedor("vendedor@loja.test", alvo="5")},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/metas?ok=criada"
    db = SessionLocal()
    meta = db.query(Meta).one()
    assert meta.escopo == "vendedor"
    assert meta.vendedor_email == "vendedor@loja.test"
    assert meta.valor_alvo == Decimal("5.00")
    db.close()
    lista = client.get("/app/metas")
    assert "Vendedor" in lista.text
    assert "vendedor@loja.test" in lista.text


def test_meta_vendedor_exige_selecao_de_vendedor(client):
    criar_usuario(papel="vendedor", email="vendedor@loja.test")
    login(client)
    pagina = client.get("/app/metas/nova")
    dados = dados_meta_vendedor("", alvo="5")
    resposta = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_da_resposta(pagina), **dados},
    )
    assert resposta.status_code == 422
    assert "Selecione o vendedor" in resposta.text
    db = SessionLocal()
    assert db.query(Meta).count() == 0
    db.close()


def test_meta_vendedor_rejeita_vendedor_de_outra_loja(client):
    db = SessionLocal()
    from app.auth import hash_senha
    from app.models import Usuario

    db.add(
        Usuario(
            email="forasteiro@outra.test",
            nome="Forasteiro",
            senha_hash=hash_senha("senha-segura"),
            papel="vendedor",
            loja_slug="outra-loja",
        )
    )
    db.commit()
    db.close()
    login(client)
    pagina = client.get("/app/metas/nova")
    resposta = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_da_resposta(pagina), **dados_meta_vendedor("forasteiro@outra.test", alvo="5")},
    )
    assert resposta.status_code == 422
    assert "vendedor ativo desta loja" in resposta.text
    db = SessionLocal()
    assert db.query(Meta).count() == 0
    db.close()


def test_bloqueia_sobreposicao_de_meta_individual_do_mesmo_vendedor(client):
    criar_usuario(papel="vendedor", email="vendedor@loja.test")
    inicio, fim = periodo_atual()
    login(client)
    pagina = client.get("/app/metas/nova")
    primeira = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_da_resposta(pagina), **dados_meta_vendedor("vendedor@loja.test", inicio=inicio, fim=fim)},
        follow_redirects=False,
    )
    assert primeira.status_code == 303
    pagina2 = client.get("/app/metas/nova")
    segunda = client.post(
        "/app/metas/nova",
        data={
            "csrf": csrf_da_resposta(pagina2),
            **dados_meta_vendedor(
                "vendedor@loja.test", inicio=inicio + timedelta(days=1), fim=fim
            ),
        },
    )
    assert segunda.status_code == 422
    assert "sobrepondo o período" in segunda.text
    db = SessionLocal()
    assert db.query(Meta).count() == 1
    db.close()


def test_meta_loja_e_meta_individual_no_mesmo_periodo_nao_conflitam(client):
    criar_usuario(papel="vendedor", email="vendedor@loja.test")
    inicio, fim = periodo_atual()
    login(client)
    pagina = client.get("/app/metas/nova")
    loja = client.post(
        "/app/metas/nova",
        data={"csrf": csrf_da_resposta(pagina), **dados_meta(inicio=inicio, fim=fim)},
        follow_redirects=False,
    )
    assert loja.status_code == 303
    pagina2 = client.get("/app/metas/nova")
    individual = client.post(
        "/app/metas/nova",
        data={
            "csrf": csrf_da_resposta(pagina2),
            **dados_meta_vendedor("vendedor@loja.test", inicio=inicio, fim=fim),
        },
        follow_redirects=False,
    )
    assert individual.status_code == 303
    db = SessionLocal()
    assert db.query(Meta).count() == 2
    db.close()


def test_vendedor_nao_ve_metas_individuais_de_outros_na_lista_geral(client):
    criar_meta_individual_para_teste("vendedor@loja.test")
    login(client, papel="vendedor", email="vendedor@loja.test")
    lista = client.get("/app/metas")
    assert lista.status_code == 200
    # Só há uma meta cadastrada e ela é individual (escopo=vendedor): a lista geral
    # do vendedor mostra apenas metas de escopo=loja, então deve aparecer vazia.
    assert "Nenhuma meta cadastrada" in lista.text


def criar_meta_individual_para_teste(vendedor_email, tipo="quantidade", alvo="3"):
    padrao_inicio, padrao_fim = periodo_atual()
    db = SessionLocal()
    meta = Meta(
        loja_slug="loja-teste",
        escopo="vendedor",
        vendedor_email=vendedor_email,
        tipo=tipo,
        periodo_inicio=padrao_inicio,
        periodo_fim=padrao_fim,
        valor_alvo=Decimal(alvo),
        ativa=True,
    )
    db.add(meta)
    db.commit()
    db.close()
