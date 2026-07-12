import os
import re

import pytest
from fastapi.testclient import TestClient

os.environ["PORTAL_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["PORTAL_SESSION_SECRET"] = "segredo-de-teste"
os.environ["ESTOQUE_API_TOKEN"] = "token-de-teste"

from app.auth import hash_senha  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app, get_estoque_client  # noqa: E402
from app.models import Usuario  # noqa: E402


class EstoqueFake:
    def __init__(self):
        self.veiculos = [
            {
                "id": "v1", "tipo": "carro", "marca": "Honda", "modelo": "Civic",
                "versao": "EX", "ano_modelo": 2022, "cor": "Preto", "km": 22000,
                "preco": 118900.0, "custo": 102000.0, "codigo_interno": "H01",
                "foto_url": None, "status": "disponivel", "publicado": True,
            },
            {
                "id": "v2", "tipo": "moto", "marca": "Yamaha", "modelo": "MT-03",
                "versao": None, "ano_modelo": 2024, "cor": "Azul", "km": 800,
                "preco": 31900.0, "custo": None, "codigo_interno": None,
                "foto_url": None, "status": "reservado", "publicado": False,
            },
        ]
        self.criados = []
        self.acoes = []

    def listar(self, **filtros):
        itens = self.veiculos
        for campo in ("tipo", "status"):
            if filtros.get(campo):
                itens = [v for v in itens if v[campo] == filtros[campo]]
        if filtros.get("publicado") is not None:
            itens = [v for v in itens if v["publicado"] == filtros["publicado"]]
        if filtros.get("busca"):
            termo = filtros["busca"].lower()
            itens = [v for v in itens if termo in f"{v['marca']} {v['modelo']}".lower()]
        return itens

    def obter(self, veiculo_id):
        return next(v for v in self.veiculos if v["id"] == veiculo_id)

    def criar(self, dados):
        self.criados.append(dados)
        return {"id": "novo", **dados}

    def atualizar(self, veiculo_id, dados):
        return {"id": veiculo_id, **dados}

    def acao(self, veiculo_id, acao):
        self.acoes.append((veiculo_id, acao))
        return {"ok": True}


@pytest.fixture(autouse=True)
def banco_limpo():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def estoque_fake():
    fake = EstoqueFake()
    app.dependency_overrides[get_estoque_client] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def client(estoque_fake):
    with TestClient(app) as cliente:
        yield cliente


def criar_usuario(papel="dono", email="dono@loja.test"):
    db = SessionLocal()
    usuario = Usuario(
        email=email,
        nome="Ana Loja",
        senha_hash=hash_senha("senha-segura"),
        papel=papel,
        loja_slug="loja-teste",
    )
    db.add(usuario)
    db.commit()
    db.close()


def csrf_da_resposta(resposta):
    return re.search(r'name="csrf" value="([^"]+)"', resposta.text).group(1)


def login(client, papel="dono"):
    criar_usuario(papel=papel)
    pagina = client.get("/login")
    return client.post(
        "/login",
        data={"email": "dono@loja.test", "senha": "senha-segura", "csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
