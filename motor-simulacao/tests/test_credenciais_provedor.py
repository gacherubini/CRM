"""Credenciais de portal bancário por cliente+provedor (Plano #1A, Task 11).

Cobre: upsert cifrado (nada em claro no storage), GET mascarado, isolamento por
cliente, auditoria do ator, leitura on-demand (novo PUT reflete sem restart) e
métrica de falha de autenticação por provedor sem vazar segredo.
"""
import uuid

from fastapi.testclient import TestClient

from app import credenciais, observabilidade
from app.auth import hash_token
from app.main import app
from app.models_db import AuditoriaORM, ClienteApiORM, CredencialApiORM, CredencialProvedorORM


def _cliente(db, nome, token):
    cliente_id = str(uuid.uuid4())
    db.add(ClienteApiORM(id=cliente_id, nome=nome))
    db.add(
        CredencialApiORM(
            id=str(uuid.uuid4()), cliente_id=cliente_id, nome="principal",
            token_hash=hash_token(token),
        )
    )
    db.commit()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"}), cliente_id


def test_put_credencial_cifra_e_nao_persiste_senha_em_claro(client, db):
    resp = client.put(
        "/v1/provedores/Pan/credenciais",
        json={"usuario": "loja42", "senha": "senha-super-secreta"},
    )
    assert resp.status_code == 200

    row = db.query(CredencialProvedorORM).filter_by(provedor="Pan").one()
    blob = row.senha_cifrada or ""
    assert "senha-super-secreta" not in blob
    assert row.usuario == "loja42"
    # mas é recuperável para uso pelo driver
    usuario, senha = credenciais.obter_segredo_para_uso(db, row.cliente_id, "Pan")
    assert (usuario, senha) == ("loja42", "senha-super-secreta")


def test_get_nunca_vaza_senha(client):
    client.put(
        "/v1/provedores/Pan/credenciais",
        json={"usuario": "loja42", "senha": "senha-super-secreta"},
    )
    lista = client.get("/v1/provedores/credenciais").json()
    item = next(p for p in lista["credenciais"] if p["provedor"] == "Pan")
    assert item["usuario"] == "loja42"
    assert item["senha_configurada"] is True
    assert item["senha_mascara"] == "****"
    # nenhuma chave/valor da resposta pode conter a senha em claro
    assert "senha-super-secreta" not in str(lista)
    assert "senha" not in item  # a senha em claro nunca é uma chave do payload


def test_credencial_e_isolada_por_cliente(db):
    cliente_a, id_a = _cliente(db, "Loja A", "token-a")
    cliente_b, id_b = _cliente(db, "Loja B", "token-b")
    cliente_a.put(
        "/v1/provedores/Pan/credenciais", json={"usuario": "user-a", "senha": "pw-a"}
    )

    lista_b = cliente_b.get("/v1/provedores/credenciais").json()
    assert all(p["senha_configurada"] is False for p in lista_b["credenciais"])
    # a loja B nunca lê o segredo da loja A
    assert credenciais.obter_segredo_para_uso(db, id_b, "Pan") is None
    assert credenciais.obter_segredo_para_uso(db, id_a, "Pan") == ("user-a", "pw-a")


def test_auditoria_registra_ator_sem_logar_senha(client, db):
    resp = client.put(
        "/v1/provedores/Pan/credenciais",
        json={"usuario": "loja42", "senha": "senha-super-secreta"},
        headers={"X-Ator": "gerente@loja.com"},
    )
    assert resp.status_code == 200
    registro = db.query(AuditoriaORM).filter_by(acao="credencial_provedor_upsert").one()
    assert registro.ator == "gerente@loja.com"
    assert registro.provedor == "Pan"
    # a auditoria não guarda a senha nova nem antiga
    assert "senha-super-secreta" not in str(registro.__dict__)


def test_novo_put_reflete_sem_restart(client, db):
    cliente_id = db.query(CredencialApiORM).one().cliente_id
    client.put(
        "/v1/provedores/Pan/credenciais", json={"usuario": "loja42", "senha": "pw-antiga"}
    )
    assert credenciais.obter_segredo_para_uso(db, cliente_id, "Pan") == ("loja42", "pw-antiga")

    # rotação da senha (sem reiniciar o processo): próxima leitura pega o valor novo
    client.put(
        "/v1/provedores/Pan/credenciais", json={"usuario": "loja42", "senha": "pw-nova"}
    )
    assert credenciais.obter_segredo_para_uso(db, cliente_id, "Pan") == ("loja42", "pw-nova")


def test_upsert_desabilitado_nao_e_usado(client, db):
    cliente_id = db.query(CredencialApiORM).one().cliente_id
    client.put(
        "/v1/provedores/Pan/credenciais",
        json={"usuario": "loja42", "senha": "pw", "habilitado": False},
    )
    assert credenciais.obter_segredo_para_uso(db, cliente_id, "Pan") is None


def test_testar_login_e_placeholder_ate_task12(client):
    client.put(
        "/v1/provedores/Pan/credenciais", json={"usuario": "loja42", "senha": "pw"}
    )
    resp = client.post("/v1/provedores/Pan/testar-login")
    assert resp.status_code == 200
    corpo = resp.json()
    # placeholder honesto: não finge autenticar em banco real (Task 12)
    assert corpo["status"] == "placeholder"


def test_testar_login_sem_credencial_retorna_404(client):
    resp = client.post("/v1/provedores/Pan/testar-login")
    assert resp.status_code == 404


def test_metrica_de_falha_de_auth_por_provedor_sem_vazar_segredo(client, db):
    cliente_id = db.query(CredencialApiORM).one().cliente_id
    client.put(
        "/v1/provedores/Pan/credenciais", json={"usuario": "loja42", "senha": "pw"}
    )
    credenciais.registrar_falha_login(db, cliente_id, "Pan", "credencial_invalida")
    credenciais.registrar_falha_login(db, cliente_id, "Pan", "credencial_invalida")

    texto = observabilidade.gerar_metricas(db)
    assert 'motor_provider_auth_failures{provider="Pan"} 2' in texto
    assert "pw" not in texto  # segredo nunca aparece nas métricas

    # um sucesso zera o contador de falhas
    credenciais.registrar_sucesso_login(db, cliente_id, "Pan")
    texto = observabilidade.gerar_metricas(db)
    assert 'motor_provider_auth_failures{provider="Pan"} 0' in texto


def test_rotas_de_credenciais_exigem_bearer():
    sem_auth = TestClient(app)
    assert sem_auth.get("/v1/provedores/credenciais").status_code == 401
    assert sem_auth.put(
        "/v1/provedores/Pan/credenciais", json={"usuario": "x", "senha": "y"}
    ).status_code == 401
    assert sem_auth.post("/v1/provedores/Pan/testar-login").status_code == 401
