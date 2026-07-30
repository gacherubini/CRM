"""Testes do read model EstoqueOverview e rotas /app/loja/estoque* (Fase 2).

Fórmulas explícitas, estados vazio/erro, flag de shell e ausência de IA.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.loja.estoque_overview import (
    ContagensEstoque,
    montar_estoque_overview,
)
from conftest import login


# ---------------------------------------------------------------------------
# Fixtures de fórmulas (read model puro — sem HTTP)
# ---------------------------------------------------------------------------

AGORA = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)


def _v(
    id_: str,
    *,
    status: str = "disponivel",
    preco: float | None = 100.0,
    foto_url: str | None = "http://x/f.jpg",
    marca: str = "Honda",
    modelo: str = "Civic",
    tipo: str = "carro",
    ano_modelo: int | None = 2022,
    placa: str | None = None,
    publicado: bool = False,
    criado_em: str | None = None,
    atualizado_em: str | None = None,
    **extra,
) -> dict:
    base = {
        "id": id_,
        "status": status,
        "preco": preco,
        "foto_url": foto_url,
        "marca": marca,
        "modelo": modelo,
        "tipo": tipo,
        "ano_modelo": ano_modelo,
        "placa": placa,
        "publicado": publicado,
        "criado_em": criado_em,
        "atualizado_em": atualizado_em,
    }
    base.update(extra)
    return base


def test_contagens_por_status_formula_explicita():
    veiculos = [
        _v("a", status="disponivel", publicado=True),
        _v("b", status="disponivel", publicado=False),
        _v("c", status="reservado"),
        _v("d", status="vendido"),
        _v("e", status="indisponivel"),
        _v("f", status="vendido"),
    ]
    ov = montar_estoque_overview(veiculos, agora=AGORA)
    assert ov.status == "parcial"  # ativos sem criado_em
    assert ov.contagens == ContagensEstoque(
        disponivel=2,
        reservado=1,
        vendido=2,
        indisponivel=1,
        publicados=1,
        total=6,
    )


def test_faixas_idade_com_criado_em():
    veiculos = [
        # 10 dias
        _v("d10", criado_em="2026-07-19T12:00:00+00:00"),
        # 45 dias
        _v("d45", criado_em="2026-06-14T12:00:00+00:00"),
        # 75 dias
        _v("d75", criado_em="2026-05-15T12:00:00+00:00"),
        # 120 dias
        _v("d120", criado_em="2026-03-31T12:00:00+00:00"),
        # vendido não entra na idade
        _v("sold", status="vendido", criado_em="2026-01-01T00:00:00+00:00"),
    ]
    ov = montar_estoque_overview(veiculos, agora=AGORA)
    assert ov.status == "ok"
    assert ov.idade is not None
    assert ov.idade.ate_30 == 1
    assert ov.idade.de_31_a_60 == 1
    assert ov.idade.de_61_a_90 == 1
    assert ov.idade.acima_90 == 1
    assert ov.idade.com_data == 4
    assert ov.idade.sem_data == 0


def test_idade_omitida_quando_sem_datas():
    veiculos = [_v("x"), _v("y", status="reservado")]
    ov = montar_estoque_overview(veiculos, agora=AGORA)
    assert ov.idade is None
    assert ov.status == "parcial"
    assert ov.contagens is not None
    assert ov.contagens.disponivel == 1
    assert ov.contagens.reservado == 1


def test_lacunas_preco_foto_e_obrigatorios():
    veiculos = [
        _v("ok", preco=50, foto_url="http://x/a.jpg", placa="ABC1D23"),
        _v("nopreco", preco=None, foto_url="http://x/a.jpg", placa="BBB2B22"),
        _v("zeropreco", preco=0, foto_url="http://x/a.jpg"),
        _v("nofoto", preco=10, foto_url=None),
        _v("nomarca", preco=10, foto_url="http://x/a.jpg", marca=""),
        _v("sold-gap", status="vendido", preco=None, foto_url=None),  # ignorado
    ]
    ov = montar_estoque_overview(veiculos, agora=AGORA, limite_lacunas=10)
    ids = {l.id for l in ov.lacunas}
    assert "ok" not in ids
    assert "sold-gap" not in ids
    assert "nopreco" in ids
    assert "zeropreco" in ids
    assert "nofoto" in ids
    assert "nomarca" in ids
    faltas_nopreco = next(l.faltas for l in ov.lacunas if l.id == "nopreco")
    assert "preco" in faltas_nopreco
    faltas_foto = next(l.faltas for l in ov.lacunas if l.id == "nofoto")
    assert "foto" in faltas_foto
    assert ov.total_lacunas == 4


def test_recentes_reservas_e_vendas_ordenados():
    veiculos = [
        _v(
            "r1",
            status="reservado",
            atualizado_em="2026-07-28T10:00:00+00:00",
            placa="RES1A11",
        ),
        _v(
            "v1",
            status="vendido",
            atualizado_em="2026-07-27T10:00:00+00:00",
            placa="VEN1A11",
        ),
        _v("d1", status="disponivel", atualizado_em="2026-07-29T10:00:00+00:00"),
    ]
    ov = montar_estoque_overview(veiculos, agora=AGORA)
    assert len(ov.recentes) == 2
    assert ov.recentes[0].id == "r1"
    assert ov.recentes[0].tipo == "reserva"
    assert ov.recentes[1].id == "v1"
    assert ov.recentes[1].tipo == "venda"


def test_lista_vazia_status_vazio_sem_metricas_inventadas_de_erro():
    ov = montar_estoque_overview([], agora=AGORA)
    assert ov.status == "vazio"
    assert ov.contagens is not None
    assert ov.contagens.total == 0
    assert ov.contagens.disponivel == 0
    assert ov.idade is None
    assert ov.lacunas == ()
    assert ov.recentes == ()
    assert ov.erro is None


def test_api_falha_status_erro_sem_contagens():
    ov = montar_estoque_overview(
        None, erro="Não foi possível acessar o estoque agora", agora=AGORA
    )
    assert ov.status == "erro"
    assert ov.contagens is None
    assert ov.idade is None
    assert ov.lacunas == ()
    assert ov.recentes == ()
    assert ov.erro is not None


def test_tem_foto_flag_evita_lacuna():
    v = _v("com-flag", foto_url=None, tem_foto=True)
    ov = montar_estoque_overview([v], agora=AGORA)
    assert ov.lacunas == ()


def test_nenhum_import_de_provedor_ia_no_modulo():
    """Estoque não usa IA — o módulo e o pacote loja não importam provedores."""
    raiz = Path(__file__).resolve().parents[1] / "app" / "loja"
    proibidos = (
        "openai",
        "anthropic",
        "langchain",
        "seller_ai",
        "SellerAI",
        "generativeai",
        "vertexai",
    )
    for path in raiz.rglob("*.py"):
        texto = path.read_text(encoding="utf-8")
        for termo in proibidos:
            assert termo not in texto, f"{path} menciona {termo}"
    web = Path(__file__).resolve().parents[1] / "app" / "web" / "loja_estoque.py"
    texto_web = web.read_text(encoding="utf-8")
    for termo in proibidos:
        assert termo not in texto_web


# ---------------------------------------------------------------------------
# Rotas HTTP (flag + estados de UI)
# ---------------------------------------------------------------------------


@pytest.fixture
def shell_on(monkeypatch):
    # Settings é frozen; patcha o gate da rota (Settings já foi materializado no import).
    monkeypatch.setattr("app.web.loja_estoque._shell_ativo", lambda: True)


def test_rota_visao_flag_off_redireciona_legado(client):
    login(client)
    # default flag off
    resp = client.get("/app/loja/estoque", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/estoque"


def test_rota_veiculos_flag_off_redireciona_legado(client):
    login(client)
    resp = client.get("/app/loja/estoque/veiculos", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/estoque"


def test_rota_visao_ok_com_dados(client, shell_on, estoque_fake):
    login(client)
    # enriquece fake com data para status ok
    estoque_fake.veiculos[0]["criado_em"] = "2026-07-01T00:00:00+00:00"
    estoque_fake.veiculos[0]["placa"] = "ABC1D23"
    estoque_fake.veiculos[1]["criado_em"] = "2026-06-01T00:00:00+00:00"
    resp = client.get("/app/loja/estoque")
    assert resp.status_code == 200
    assert "Visão geral" in resp.text
    assert "Disponíveis" in resp.text
    assert "Honda Civic" in resp.text or "Pendências" in resp.text
    # fake: v1 sem foto → lacuna
    assert "foto" in resp.text.lower() or "Pendências" in resp.text
    # sem linguagem de IA
    assert "inteligência artificial" not in resp.text.lower()
    assert "seller ai" not in resp.text.lower()


def test_rota_visao_vazio(client, shell_on, estoque_fake):
    login(client)
    estoque_fake.veiculos = []
    resp = client.get("/app/loja/estoque")
    assert resp.status_code == 200
    assert "Nenhum veículo cadastrado" in resp.text
    # não inventa card de "0 disponíveis" como se fosse erro recuperado
    assert "Estoque indisponível" not in resp.text


def test_rota_visao_erro_api(client, shell_on, estoque_fake):
    login(client)
    estoque_fake.indisponivel = True
    resp = client.get("/app/loja/estoque")
    assert resp.status_code == 200
    assert "Estoque indisponível" in resp.text
    assert "Nenhum indicador é exibido" in resp.text
    # não mostra contagens zeradas inventadas
    assert "prontos para venda" not in resp.text


def test_rota_veiculos_redireciona_legado_com_flag(client, shell_on):
    login(client)
    resp = client.get(
        "/app/loja/estoque/veiculos?status=disponivel", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/estoque?status=disponivel"


def test_legado_estoque_permanece(client):
    """Rotas /app/estoque* não são removidas nem quebradas pela Fase 2."""
    login(client)
    resp = client.get("/app/estoque")
    assert resp.status_code == 200
    assert "Honda Civic" in resp.text


def test_vendedor_visao_sem_custo(client, shell_on, estoque_fake):
    login(client, papel="vendedor")
    estoque_fake.veiculos[0]["custo"] = 102000.0
    resp = client.get("/app/loja/estoque")
    assert resp.status_code == 200
    # Visão geral não renderiza custo/margem; vendedor não deve vê-los.
    assert "102.000" not in resp.text
    assert "102000" not in resp.text
    assert "margem" not in resp.text.lower()


def test_nao_autenticado_redireciona_login(client, shell_on):
    resp = client.get("/app/loja/estoque", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]
