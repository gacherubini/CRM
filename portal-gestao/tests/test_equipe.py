import pytest

from conftest import csrf_da_resposta, login

from app.auth import autenticar, hash_senha, verifica_senha
from app.db import SessionLocal
from app.models import Usuario


def criar_membro(
    *,
    email="vendedor@loja.test",
    nome="Vera Vendas",
    papel="vendedor",
    loja_slug="loja-teste",
    ativo=True,
):
    db = SessionLocal()
    membro = Usuario(
        email=email,
        nome=nome,
        senha_hash=hash_senha("senha-do-membro"),
        papel=papel,
        loja_slug=loja_slug,
        ativo=ativo,
    )
    db.add(membro)
    db.commit()
    membro_id = membro.id
    db.close()
    return membro_id


def dados_novo(**alteracoes):
    dados = {
        "nome": "  Bruno   Comercial  ",
        "email": "  BRUNO@LOJA.TEST ",
        "papel": "vendedor",
        "senha": "senha-inicial-forte",
        "senha_confirmacao": "senha-inicial-forte",
    }
    dados.update(alteracoes)
    return dados


def csrf_equipe(client):
    return csrf_da_resposta(client.get("/app/equipe"))


def test_dono_lista_somente_membros_da_propria_loja_sem_expor_hash(client):
    membro_id = criar_membro()
    criar_membro(
        email="oculto@outra.test",
        nome="Membro Outra Loja",
        loja_slug="outra-loja",
    )
    login(client)

    resposta = client.get("/app/equipe")

    assert resposta.status_code == 200
    assert "Vera Vendas" in resposta.text
    assert "vendedor@loja.test" in resposta.text
    assert "Membro Outra Loja" not in resposta.text
    assert "oculto@outra.test" not in resposta.text
    db = SessionLocal()
    assert db.get(Usuario, membro_id).senha_hash not in resposta.text
    db.close()


def test_dono_cria_vendedor_normalizando_identidade_e_hash_da_senha(client):
    login(client)
    pagina = client.get("/app/equipe/novo")

    resposta = client.post(
        "/app/equipe/novo",
        data={"csrf": csrf_da_resposta(pagina), **dados_novo()},
        follow_redirects=False,
    )

    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app/equipe?ok=criado"
    db = SessionLocal()
    membro = db.query(Usuario).filter(Usuario.email == "bruno@loja.test").one()
    assert membro.nome == "Bruno Comercial"
    assert membro.papel == "vendedor"
    assert membro.loja_slug == "loja-teste"
    assert membro.ativo is True
    assert membro.senha_hash != "senha-inicial-forte"
    assert verifica_senha(membro.senha_hash, "senha-inicial-forte")
    db.close()


def test_admin_plataforma_pode_criar_gerente_na_loja_atual(client):
    login(client, papel="admin_plataforma", email="admin@plataforma.test")
    pagina = client.get("/app/equipe/novo")

    resposta = client.post(
        "/app/equipe/novo",
        data={
            "csrf": csrf_da_resposta(pagina),
            **dados_novo(email="GERENTE@LOJA.TEST", papel="gerente"),
        },
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/equipe?ok=criado"
    db = SessionLocal()
    gerente = db.query(Usuario).filter(Usuario.email == "gerente@loja.test").one()
    assert gerente.papel == "gerente"
    assert gerente.loja_slug == "loja-teste"
    db.close()


@pytest.mark.parametrize(
    ("alteracoes", "mensagem"),
    [
        ({"nome": " "}, "nome completo"),
        ({"email": "email-invalido"}, "e-mail válido"),
        ({"papel": "dono"}, "gerente ou vendedor"),
        ({"senha": "curta", "senha_confirmacao": "curta"}, "pelo menos 10"),
        ({"senha_confirmacao": "outra-senha-segura"}, "não confere"),
    ],
)
def test_criacao_valida_dados_com_mensagens_claras(client, alteracoes, mensagem):
    login(client)
    pagina = client.get("/app/equipe/novo")
    resposta = client.post(
        "/app/equipe/novo",
        data={"csrf": csrf_da_resposta(pagina), **dados_novo(**alteracoes)},
    )

    assert resposta.status_code == 422
    assert mensagem in resposta.text
    db = SessionLocal()
    assert db.query(Usuario).count() == 1
    db.close()


def test_criacao_rejeita_email_ja_usado_sem_duplicar_usuario(client):
    criar_membro(email="bruno@loja.test")
    login(client)
    pagina = client.get("/app/equipe/novo")

    resposta = client.post(
        "/app/equipe/novo",
        data={"csrf": csrf_da_resposta(pagina), **dados_novo()},
    )

    assert resposta.status_code == 422
    assert "não está disponível" in resposta.text
    db = SessionLocal()
    assert db.query(Usuario).count() == 2
    db.close()


@pytest.mark.parametrize("papel", ["gerente", "vendedor"])
def test_rbac_impede_gerente_e_vendedor_de_gerir_equipe(client, papel):
    login(client, papel=papel, email=f"{papel}@loja.test")
    dashboard = client.get("/app")
    csrf = csrf_da_resposta(dashboard)

    pagina = client.get("/app/equipe", follow_redirects=False)
    criacao = client.post(
        "/app/equipe/novo",
        data={"csrf": csrf, **dados_novo()},
        follow_redirects=False,
    )

    assert pagina.status_code == 303
    assert pagina.headers["location"] == "/app"
    assert criacao.status_code == 303
    assert criacao.headers["location"] == "/app"
    db = SessionLocal()
    assert db.query(Usuario).count() == 1
    db.close()


def test_csrf_invalido_nao_cria_nem_altera_membro(client):
    membro_id = criar_membro()
    login(client)

    criacao = client.post(
        "/app/equipe/novo",
        data={"csrf": "invalido", **dados_novo()},
    )
    desativacao = client.post(
        f"/app/equipe/{membro_id}/desativar",
        data={"csrf": "invalido"},
    )

    assert criacao.status_code == 400
    assert "Sessão expirada" in criacao.text
    assert desativacao.status_code == 400
    db = SessionLocal()
    assert db.query(Usuario).count() == 2
    assert db.get(Usuario, membro_id).ativo is True
    db.close()


def test_edita_nome_e_papel_mas_email_permanece_imutavel(client):
    membro_id = criar_membro()
    login(client)
    pagina = client.get(f"/app/equipe/{membro_id}/editar")

    resposta = client.post(
        f"/app/equipe/{membro_id}/editar",
        data={
            "csrf": csrf_da_resposta(pagina),
            "nome": "  Vera   Gerente ",
            "email": "tentativa@troca.test",
            "papel": "gerente",
        },
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/equipe?ok=editado"
    db = SessionLocal()
    membro = db.get(Usuario, membro_id)
    assert membro.nome == "Vera Gerente"
    assert membro.papel == "gerente"
    assert membro.email == "vendedor@loja.test"
    db.close()


def test_redefine_senha_sem_expor_hash_e_invalida_senha_anterior(client):
    membro_id = criar_membro()
    login(client)
    pagina = client.get(f"/app/equipe/{membro_id}/senha")
    db = SessionLocal()
    hash_anterior = db.get(Usuario, membro_id).senha_hash
    db.close()

    assert hash_anterior not in pagina.text
    resposta = client.post(
        f"/app/equipe/{membro_id}/senha",
        data={
            "csrf": csrf_da_resposta(pagina),
            "senha": "nova-senha-super-segura",
            "senha_confirmacao": "nova-senha-super-segura",
        },
        follow_redirects=False,
    )

    assert resposta.headers["location"] == "/app/equipe?ok=senha"
    db = SessionLocal()
    novo_hash = db.get(Usuario, membro_id).senha_hash
    assert novo_hash != hash_anterior
    assert not verifica_senha(novo_hash, "senha-do-membro")
    assert verifica_senha(novo_hash, "nova-senha-super-segura")
    db.close()


def test_desativa_e_reativa_sem_excluir_membro(client):
    membro_id = criar_membro()
    login(client)
    csrf = csrf_equipe(client)

    desativar = client.post(
        f"/app/equipe/{membro_id}/desativar",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert desativar.headers["location"] == "/app/equipe?ok=desativar"
    db = SessionLocal()
    assert db.get(Usuario, membro_id).ativo is False
    assert db.query(Usuario).filter(Usuario.id == membro_id).count() == 1
    assert autenticar(db, "vendedor@loja.test", "senha-do-membro") is None
    db.close()

    ativar = client.post(
        f"/app/equipe/{membro_id}/ativar",
        data={"csrf": csrf},
        follow_redirects=False,
    )
    assert ativar.headers["location"] == "/app/equipe?ok=ativar"
    db = SessionLocal()
    assert db.get(Usuario, membro_id).ativo is True
    assert autenticar(db, "vendedor@loja.test", "senha-do-membro") is not None
    db.close()


def test_nao_acessa_nem_altera_membro_de_outra_loja(client):
    membro_id = criar_membro(
        email="outra@loja.test",
        loja_slug="outra-loja",
    )
    login(client)
    csrf = csrf_equipe(client)

    pagina = client.get(f"/app/equipe/{membro_id}/editar", follow_redirects=False)
    edicao = client.post(
        f"/app/equipe/{membro_id}/editar",
        data={"csrf": csrf, "nome": "Ataque", "papel": "gerente"},
        follow_redirects=False,
    )
    senha = client.post(
        f"/app/equipe/{membro_id}/senha",
        data={
            "csrf": csrf,
            "senha": "senha-tentativa-forte",
            "senha_confirmacao": "senha-tentativa-forte",
        },
        follow_redirects=False,
    )
    acesso = client.post(
        f"/app/equipe/{membro_id}/desativar",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    for resposta in (pagina, edicao, senha, acesso):
        assert resposta.headers["location"] == "/app/equipe?erro=nao-encontrado"
    db = SessionLocal()
    membro = db.get(Usuario, membro_id)
    assert membro.nome == "Vera Vendas"
    assert membro.papel == "vendedor"
    assert membro.ativo is True
    assert verifica_senha(membro.senha_hash, "senha-do-membro")
    db.close()


def test_dono_nao_pode_se_desativar_nem_mudar_o_proprio_papel(client):
    login(client)
    db = SessionLocal()
    dono = db.query(Usuario).filter(Usuario.email == "dono@loja.test").one()
    dono_id = dono.id
    db.close()
    pagina = client.get(f"/app/equipe/{dono_id}/editar")
    csrf = csrf_da_resposta(pagina)

    edicao = client.post(
        f"/app/equipe/{dono_id}/editar",
        data={"csrf": csrf, "nome": "Ana Alterada", "papel": "vendedor"},
    )
    desativacao = client.post(
        f"/app/equipe/{dono_id}/desativar",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    assert edicao.status_code == 422
    assert "conta protegida" in edicao.text
    assert desativacao.headers["location"] == "/app/equipe?erro=auto-desativacao"
    db = SessionLocal()
    dono = db.get(Usuario, dono_id)
    assert dono.nome == "Ana Loja"
    assert dono.papel == "dono"
    assert dono.ativo is True
    db.close()


def test_dono_nao_pode_gerir_outra_conta_protegida_da_mesma_loja(client):
    outro_dono_id = criar_membro(
        email="socio@loja.test",
        nome="Sócio da Loja",
        papel="dono",
    )
    login(client)
    csrf = csrf_equipe(client)

    editar = client.get(
        f"/app/equipe/{outro_dono_id}/editar",
        follow_redirects=False,
    )
    senha = client.post(
        f"/app/equipe/{outro_dono_id}/senha",
        data={
            "csrf": csrf,
            "senha": "tentativa-nao-autorizada",
            "senha_confirmacao": "tentativa-nao-autorizada",
        },
        follow_redirects=False,
    )
    desativar = client.post(
        f"/app/equipe/{outro_dono_id}/desativar",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    for resposta in (editar, senha, desativar):
        assert resposta.headers["location"] == "/app/equipe?erro=conta-protegida"
    db = SessionLocal()
    outro_dono = db.get(Usuario, outro_dono_id)
    assert outro_dono.ativo is True
    assert verifica_senha(outro_dono.senha_hash, "senha-do-membro")
    db.close()
