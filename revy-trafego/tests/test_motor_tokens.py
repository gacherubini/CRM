"""Cofre de tokens do Motor por loja (Control guarda cifrado, Portal consome).

Cobre: ensure cria e guarda só blob; segunda chamada não reemite; leitura
serve ao Portal com service token e nega sem ele; sem chave responde 503;
falha do Motor no nascimento não quebra criar_loja; migration aplica. O teste
NUNCA bate na rede: o POST ensure-cliente do Motor é substituído por fake.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet

from app import config as config_mod
from app.control import motor_tokens
from app.control.stores import StoreControl
from app.control.types import Actor, CreateStore
from app.db import SessionLocal
from app.models import GestorRevy, MotorTokenCofre

APP_DIR = Path(__file__).resolve().parents[1]
CHAVE_TESTE = Fernet.generate_key().decode()
TOKEN_EMITIDO = "tok-motor-emitido-1x"
PORTAL_TOKEN = "tok-portal-servico"


@pytest.fixture(autouse=True)
def _restaura_settings():
    original = config_mod.settings
    yield
    config_mod.settings = original


def _cfg(**kwargs) -> None:
    config_mod.settings = replace(config_mod.settings, **kwargs)


def _com_cofre(**kwargs) -> None:
    _cfg(control_tokens_key=CHAVE_TESTE, **kwargs)


def _fake_ensure(status: int, corpo: dict, *, chamadas: list | None = None):
    def fake(slug: str, **kw):
        if chamadas is not None:
            chamadas.append(slug)
        return status, dict(corpo)

    return fake


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def test_ensure_cria_e_guarda_somente_blob_cifrado(monkeypatch):
    _com_cofre(motor_url="http://motor:8000", motor_provisioning_token="svc")
    monkeypatch.setattr(
        motor_tokens,
        "_chamar_ensure_motor",
        _fake_ensure(201, {"token": TOKEN_EMITIDO}),
    )
    with SessionLocal() as db:
        token = motor_tokens.ensure_motor_token(db, "loja-nova")
        db.commit()
        assert token == TOKEN_EMITIDO
        linha = db.get(MotorTokenCofre, "loja-nova")
        assert linha is not None
        # No banco fica só o blob: diferente do claro e sem o claro dentro.
        assert linha.token_ciphertext != TOKEN_EMITIDO
        assert TOKEN_EMITIDO not in linha.token_ciphertext
        assert (
            Fernet(CHAVE_TESTE.encode())
            .decrypt(linha.token_ciphertext.encode())
            .decode()
            == TOKEN_EMITIDO
        )


def test_segunda_chamada_nao_reemite(monkeypatch):
    _com_cofre(motor_url="http://motor:8000", motor_provisioning_token="svc")
    chamadas: list = []
    monkeypatch.setattr(
        motor_tokens,
        "_chamar_ensure_motor",
        _fake_ensure(201, {"token": TOKEN_EMITIDO}, chamadas=chamadas),
    )
    with SessionLocal() as db:
        assert motor_tokens.ensure_motor_token(db, "loja-repetida") == TOKEN_EMITIDO
        db.commit()
        assert motor_tokens.ensure_motor_token(db, "loja-repetida") == TOKEN_EMITIDO
        db.commit()
    assert chamadas == ["loja-repetida"]


def test_repeticao_ja_existia_no_motor_nao_guarda_nada(monkeypatch):
    _com_cofre(motor_url="http://motor:8000", motor_provisioning_token="svc")
    monkeypatch.setattr(
        motor_tokens,
        "_chamar_ensure_motor",
        _fake_ensure(200, {"ja_existia": True, "token": None}),
    )
    with SessionLocal() as db:
        assert motor_tokens.ensure_motor_token(db, "loja-antiga") is None
        db.commit()
        assert db.get(MotorTokenCofre, "loja-antiga") is None


def test_cofre_primeiro_mapa_env_depois(monkeypatch):
    _com_cofre(motor_tokens_json='{"loja-x": "tok-do-mapa"}')
    with SessionLocal() as db:
        # Sem linha no cofre, cai no mapa em env (sem bater no Motor).
        assert motor_tokens.token_para_portal(db, "loja-x") == "tok-do-mapa"
        # Com linha no cofre, o cofre vence o mapa.
        assert motor_tokens.guardar_token(db, "loja-x", "tok-do-cofre") is True
        assert motor_tokens.guardar_token(db, "loja-x", "outro") is False
        db.commit()
        assert motor_tokens.token_para_portal(db, "loja-x") == "tok-do-cofre"
        assert motor_tokens.token_para_portal(db, "loja-sem-nada") is None


def test_slug_fora_do_canonico_nao_entra_nem_sai():
    _com_cofre()
    with SessionLocal() as db:
        for invalido in ["", "Loja_OK", "-loja", "loja-", "loja com espaco", "a" * 121]:
            with pytest.raises(motor_tokens.SlugInvalido):
                motor_tokens.ensure_motor_token(db, invalido)
            with pytest.raises(motor_tokens.SlugInvalido):
                motor_tokens.ler_token(db, invalido)
        assert motor_tokens.slug_canonico(" Loja-X ") == "loja-x"


def test_sem_chave_leitura_e_emissao_falham_fechado():
    _cfg(control_tokens_key="")
    with SessionLocal() as db:
        with pytest.raises(motor_tokens.CofreIndisponivel):
            motor_tokens.ler_token(db, "loja-x")
        with pytest.raises(motor_tokens.CofreIndisponivel):
            motor_tokens.ensure_motor_token(db, "loja-x")


def test_endpoint_serve_com_service_token_e_nega_sem_ele(client):
    _com_cofre(portal_service_token=PORTAL_TOKEN)
    with SessionLocal() as db:
        motor_tokens.guardar_token(db, "loja-portal", "tok-secreto-portal")
        db.commit()
    headers = {"Authorization": f"Bearer {PORTAL_TOKEN}"}
    r = client.get("/internal/motor-tokens/loja-portal", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"token": "tok-secreto-portal"}

    assert client.get("/internal/motor-tokens/loja-portal").status_code == 401
    errado = client.get(
        "/internal/motor-tokens/loja-portal",
        headers={"Authorization": "Bearer errado"},
    )
    assert errado.status_code == 401
    assert "tok-secreto-portal" not in errado.text


def test_endpoint_sem_token_da_loja_responde_404_sem_vazar(client):
    _com_cofre(
        portal_service_token=PORTAL_TOKEN,
        motor_url="",
        motor_provisioning_token="",
    )
    headers = {"Authorization": f"Bearer {PORTAL_TOKEN}"}
    r = client.get("/internal/motor-tokens/loja-sem-token", headers=headers)
    assert r.status_code == 404
    assert r.json()["erro"]["code"] == "sem_token"

    invalido = client.get("/internal/motor-tokens/-loja", headers=headers)
    assert invalido.status_code == 404
    assert invalido.json()["erro"]["code"] == "sem_token"


def test_endpoint_sem_chave_responde_503(client):
    _cfg(control_tokens_key="", portal_service_token=PORTAL_TOKEN)
    headers = {"Authorization": f"Bearer {PORTAL_TOKEN}"}
    r = client.get("/internal/motor-tokens/loja-qualquer", headers=headers)
    assert r.status_code == 503
    assert r.json()["erro"]["code"] == "cofre_indisponivel"


def test_endpoint_emite_sob_demanda_quando_falta(monkeypatch, client):
    _com_cofre(
        portal_service_token=PORTAL_TOKEN,
        motor_url="http://motor:8000",
        motor_provisioning_token="svc",
    )
    chamadas: list = []
    monkeypatch.setattr(
        motor_tokens,
        "_chamar_ensure_motor",
        _fake_ensure(201, {"token": "tok-sob-demanda"}, chamadas=chamadas),
    )
    headers = {"Authorization": f"Bearer {PORTAL_TOKEN}"}
    r = client.get("/internal/motor-tokens/loja-demanda", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"token": "tok-sob-demanda"}
    assert chamadas == ["loja-demanda"]
    with SessionLocal() as db:
        linha = db.get(MotorTokenCofre, "loja-demanda")
        assert linha is not None
        assert "tok-sob-demanda" not in linha.token_ciphertext


def test_falha_do_motor_no_nascimento_nao_quebra_criar_loja(monkeypatch):
    # Sem chaves: o pré-aquecimento nem tenta rede e a loja nasce normal.
    _cfg(control_tokens_key="", motor_provisioning_token="")
    loja = StoreControl(SessionLocal).create(
        _admin_actor(), CreateStore(name="Loja Sem Motor", slug="loja-sem-motor")
    )
    assert loja.slug == "loja-sem-motor"
    with SessionLocal() as db:
        assert db.get(MotorTokenCofre, "loja-sem-motor") is None

    # Com chaves mas Motor fora: best-effort engole e a loja nasce igual.
    _com_cofre(motor_url="http://motor:8000", motor_provisioning_token="svc")

    def quebrado(slug: str, **kw):
        raise motor_tokens.MotorIndisponivel("motor inacessível para emissão")

    monkeypatch.setattr(motor_tokens, "_chamar_ensure_motor", quebrado)
    loja2 = StoreControl(SessionLocal).create(
        _admin_actor(), CreateStore(name="Loja Motor Fora", slug="loja-motor-fora")
    )
    assert loja2.slug == "loja-motor-fora"


def test_erro_do_motor_nao_carrega_token():
    _com_cofre(motor_url="", motor_provisioning_token="")
    with SessionLocal() as db:
        with pytest.raises(motor_tokens.MotorIndisponivel) as excinfo:
            motor_tokens.ensure_motor_token(db, "loja-x")
    assert TOKEN_EMITIDO not in str(excinfo.value)


def test_ensures_concorrentes_guardam_uma_linha_so(monkeypatch):
    _com_cofre(motor_url="http://motor:8000", motor_provisioning_token="svc")
    monkeypatch.setattr(
        motor_tokens,
        "_chamar_ensure_motor",
        _fake_ensure(201, {"token": TOKEN_EMITIDO}),
    )
    resultados: list = []

    def _rodar():
        with SessionLocal() as db:
            resultados.append(motor_tokens.ensure_motor_token(db, "loja-corrida"))
            db.commit()

    fios = [threading.Thread(target=_rodar) for _ in range(5)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join()
    assert resultados == [TOKEN_EMITIDO] * 5
    with SessionLocal() as db:
        assert db.query(MotorTokenCofre).filter(
            MotorTokenCofre.loja_slug == "loja-corrida"
        ).count() == 1


def _alembic_upgrade(database_url: str, revision: str) -> None:
    env = os.environ.copy()
    env["REVY_TRAFEGO_DATABASE_URL"] = database_url
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            revision,
        ],
        cwd=APP_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_0021_cria_cofre_e_aplica_no_head(tmp_path):
    banco = tmp_path / "control-motor-tokens.db"
    database_url = f"sqlite:///{banco}"
    _alembic_upgrade(database_url, "head")

    engine = sa.create_engine(database_url)
    inspetor = sa.inspect(engine)
    assert "motor_tokens_cofre" in inspetor.get_table_names()
    colunas = {c["name"] for c in inspetor.get_columns("motor_tokens_cofre")}
    assert {"loja_slug", "token_ciphertext", "criado_em", "atualizado_em"} <= colunas
    checks = {c["name"] for c in inspetor.get_check_constraints("motor_tokens_cofre")}
    assert "ck_motor_tokens_cofre_slug" in checks
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO motor_tokens_cofre "
                "(loja_slug, token_ciphertext, criado_em, atualizado_em) "
                "VALUES ('loja-a', 'blob', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        assert (
            conn.execute(
                sa.text(
                    "SELECT token_ciphertext FROM motor_tokens_cofre "
                    "WHERE loja_slug = 'loja-a'"
                )
            ).scalar_one()
            == "blob"
        )
