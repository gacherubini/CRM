from datetime import date

import httpx
import pytest

from app.clients.fipe import FipeClient, FipeIndisponivel
from app.loja.copiloto.fipe import (
    cache_fipe,
    consultar_fipe,
    consultar_fipe_do_veiculo,
    normalizar,
)
from app.loja.copiloto.tipos import CopilotoContexto


@pytest.fixture(autouse=True)
def _cache_limpo():
    """Cache de marcas/modelos é global: um teste não pode vazar no outro."""
    cache_fipe.invalidar()
    yield
    cache_fipe.invalidar()


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste", papel="dono", ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    """Só o que a consulta de FIPE precisa: escopo + obter."""

    def __init__(self, veiculo=None, slug="loja-teste"):
        self.veiculo = veiculo if veiculo is not None else {
            "id": "v1", "tipo": "moto", "marca": "Honda", "modelo": "CB 500F ABS",
            "ano_modelo": 2020, "preco": 28000.0, "status": "disponivel",
        }
        self.slug = slug

    def obter_loja(self):
        return {"slug": self.slug}

    def obter(self, veiculo_id):
        from app.clients.estoque import VeiculoNaoEncontrado

        if veiculo_id != self.veiculo["id"]:
            raise VeiculoNaoEncontrado("não existe")
        return dict(self.veiculo)


MARCAS = [{"codigo": "80", "nome": "Honda"}, {"codigo": "101", "nome": "Yamaha"}]
MODELOS_HONDA = {
    "modelos": [
        {"codigo": "5140", "nome": "CB 500F ABS"},
        {"codigo": "5141", "nome": "CB 500X ABS"},
        {"codigo": "5142", "nome": "CB 500F"},
    ]
}
ANOS = [{"codigo": "2020-1", "nome": "2020 Gasolina"}]
VALOR = {
    "Valor": "R$ 27.500,00",
    "Marca": "Honda",
    "Modelo": "CB 500F ABS",
    "AnoModelo": 2020,
    "MesReferencia": "agosto de 2026",
}


def _client(rotas, indisponivel=False, chamadas=None):
    def handler(request):
        if chamadas is not None:
            chamadas.append(request.url.path)
        if indisponivel:
            return httpx.Response(503, json={})
        for sufixo, corpo in rotas.items():
            if request.url.path.endswith(sufixo):
                return httpx.Response(200, json=corpo)
        return httpx.Response(404, json={})

    return FipeClient("https://fipe.test", transport=httpx.MockTransport(handler))


def _rotas_completas():
    return {
        "/motos/marcas": MARCAS,
        "/80/modelos": MODELOS_HONDA,
        "/5140/anos": ANOS,
        "/5140/anos/2020-1": VALOR,
    }


def test_normalizar_tira_acento_e_pontuacao():
    assert normalizar("CB 500F ABS!") == "cb 500f abs"
    assert normalizar("Ninjá  400") == "ninja 400"


def test_match_exato_devolve_valor():
    r = consultar_fipe(
        _client(_rotas_completas()), tipo="motos", marca="Honda",
        modelo="CB 500F ABS", ano=2020,
    )
    assert r.status == "ok"
    assert r.valor == "R$ 27.500,00"
    assert r.referencia == "agosto de 2026"


def test_termo_que_casa_com_varios_e_ambiguo_e_nao_escolhe():
    r = consultar_fipe(
        _client(_rotas_completas()), tipo="motos", marca="Honda", modelo="CB 500",
        ano=2020,
    )
    assert r.status == "ambiguo"
    assert r.valor is None
    assert len(r.candidatos) == 3
    assert {c.modelo_nome for c in r.candidatos} == {
        "CB 500F ABS",
        "CB 500X ABS",
        "CB 500F",
    }


def test_modelo_inexistente_nao_aproxima():
    r = consultar_fipe(
        _client(_rotas_completas()), tipo="motos", marca="Honda",
        modelo="Hayabusa", ano=2020,
    )
    assert r.status == "nao_encontrado"
    assert r.valor is None
    assert r.candidatos == ()


def test_marca_inexistente_nao_aproxima():
    r = consultar_fipe(
        _client(_rotas_completas()), tipo="motos", marca="Ducati", modelo="Monster"
    )
    assert r.status == "nao_encontrado"


def test_fipe_fora_do_ar_e_indisponivel_nao_zero():
    r = consultar_fipe(
        _client({}, indisponivel=True), tipo="motos", marca="Honda", modelo="CB 500F"
    )
    assert r.status == "indisponivel"
    assert r.valor is None


def test_codigo_persistido_pula_a_desambiguacao():
    """Com fipe_codigo salvo no veículo, não há matching nenhum."""
    r = consultar_fipe(
        _client(_rotas_completas()), tipo="motos", marca="Honda", modelo="qualquer",
        fipe_codigo="80/5140/2020-1",
    )
    assert r.status == "ok"
    assert r.valor == "R$ 27.500,00"


def test_client_levanta_indisponivel_em_erro():
    with pytest.raises(FipeIndisponivel):
        _client({}, indisponivel=True).marcas("motos")


# --- cache de marcas/modelos ------------------------------------------------


def test_marcas_e_modelos_sao_cacheados_entre_consultas():
    chamadas = []
    client = _client(_rotas_completas(), chamadas=chamadas)
    for _ in range(3):
        consultar_fipe(
            client, tipo="motos", marca="Honda", modelo="CB 500F ABS", ano=2020
        )
    assert sum(1 for c in chamadas if c.endswith("/motos/marcas")) == 1
    assert sum(1 for c in chamadas if c.endswith("/80/modelos")) == 1


def test_valor_nunca_e_cacheado():
    chamadas = []
    client = _client(_rotas_completas(), chamadas=chamadas)
    for _ in range(3):
        consultar_fipe(
            client, tipo="motos", marca="Honda", modelo="CB 500F ABS", ano=2020
        )
    assert sum(1 for c in chamadas if c.endswith("/anos/2020-1")) == 3


def test_tipos_diferentes_nao_compartilham_cache():
    chamadas = []
    rotas = dict(_rotas_completas())
    rotas["/carros/marcas"] = MARCAS
    client = _client(rotas, chamadas=chamadas)
    consultar_fipe(client, tipo="motos", marca="Honda", modelo="CB 500F ABS")
    consultar_fipe(client, tipo="carros", marca="Honda", modelo="CB 500F ABS")
    assert any(c.endswith("/motos/marcas") for c in chamadas)
    assert any(c.endswith("/carros/marcas") for c in chamadas)


def test_falha_nao_polui_o_cache():
    """FIPE fora numa consulta não pode envenenar a próxima."""
    assert consultar_fipe(
        _client({}, indisponivel=True), tipo="motos", marca="Honda", modelo="CB 500F"
    ).status == "indisponivel"
    r = consultar_fipe(
        _client(_rotas_completas()), tipo="motos", marca="Honda",
        modelo="CB 500F ABS", ano=2020,
    )
    assert r.status == "ok"


# --- consulta a partir do veículo do estoque --------------------------------


def test_consulta_pelo_veiculo_le_marca_modelo_e_ano_do_estoque():
    """O modelo não digita nada: os campos vêm da fonte."""
    r = consultar_fipe_do_veiculo(
        _client(_rotas_completas()), EstoqueStub(), _ctx(), veiculo_id="v1"
    )
    assert r.status == "ok"
    assert r.valor == "R$ 27.500,00"


def test_consulta_pelo_veiculo_traduz_o_tipo_do_estoque():
    """Estoque diz 'moto'; a FIPE espera 'motos'."""
    chamadas = []
    consultar_fipe_do_veiculo(
        _client(_rotas_completas(), chamadas=chamadas), EstoqueStub(), _ctx(),
        veiculo_id="v1",
    )
    assert any(c.endswith("/motos/marcas") for c in chamadas)


def test_consulta_pelo_veiculo_usa_fipe_codigo_salvo_e_pula_o_matching():
    """Pendência §12 já suportada: com o código salvo, é 1 GET só."""
    chamadas = []
    estoque = EstoqueStub(
        {
            "id": "v1", "tipo": "moto", "marca": "Honda", "modelo": "qualquer coisa",
            "ano_modelo": 2020, "fipe_codigo": "80/5140/2020-1",
        }
    )
    r = consultar_fipe_do_veiculo(
        _client(_rotas_completas(), chamadas=chamadas), estoque, _ctx(),
        veiculo_id="v1",
    )
    assert r.status == "ok"
    assert len(chamadas) == 1


def test_codigo_confirmado_pelo_usuario_vence_o_do_veiculo():
    chamadas = []
    r = consultar_fipe_do_veiculo(
        _client(_rotas_completas(), chamadas=chamadas), EstoqueStub(), _ctx(),
        veiculo_id="v1", fipe_codigo="80/5140/2020-1",
    )
    assert r.status == "ok"
    assert len(chamadas) == 1


def test_consulta_pelo_veiculo_de_outra_loja_falha_fechado():
    r = consultar_fipe_do_veiculo(
        _client(_rotas_completas()), EstoqueStub(slug="outra-loja"), _ctx(),
        veiculo_id="v1",
    )
    assert r.status == "nao_encontrado"
    assert r.valor is None


def test_veiculo_inexistente_nao_consulta_a_fipe():
    chamadas = []
    r = consultar_fipe_do_veiculo(
        _client(_rotas_completas(), chamadas=chamadas), EstoqueStub(), _ctx(),
        veiculo_id="v99",
    )
    assert r.status == "nao_encontrado"
    assert chamadas == []


def test_veiculo_sem_marca_nao_chuta():
    estoque = EstoqueStub(
        {"id": "v1", "tipo": "moto", "marca": "", "modelo": "CB 500F", "ano_modelo": 2020}
    )
    r = consultar_fipe_do_veiculo(
        _client(_rotas_completas()), estoque, _ctx(), veiculo_id="v1"
    )
    assert r.status == "nao_encontrado"


def test_estoque_indisponivel_nao_vira_fipe_nao_encontrada():
    class EstoqueFora(EstoqueStub):
        def obter(self, veiculo_id):
            from app.clients.estoque import EstoqueIndisponivel

            raise EstoqueIndisponivel("fora")

    r = consultar_fipe_do_veiculo(
        _client(_rotas_completas()), EstoqueFora(), _ctx(), veiculo_id="v1"
    )
    assert r.status == "indisponivel"
