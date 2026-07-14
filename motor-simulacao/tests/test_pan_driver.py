import base64
import json
from decimal import Decimal

import httpx

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.pan import PanDriver, parse_simulacoes_pan


CONFIG = {
    "api_key": "api-key-teste",
    "secret_key": "secret-teste",
    "usuario": "usuario-npv",
    "senha": "senha-npv",
    "id_loja": "98329834",
    "tipo_id_loja": "CODIGO",
    "codigo_produto": "MOTOS",
    "tipo_calculo": "VALOR_ENTRADA",
}


def _sol():
    return SolicitacaoSimulacao(
        pessoa=Pessoa(
            cpf="52998224725",
            nascimento="1990-01-01",
            renda=4000,
            ddd="11",
            celular="999999999",
            codigo_natureza_ocupacao="01",
        ),
        veiculo=Veiculo(
            categoria="moto",
            valor=22000,
            uf_licenciamento="SP",
            codigo_provedor="HONDA-CG-2025",
            ano_modelo=2025,
            zero_km=True,
        ),
        condicoes=Condicoes(entrada=5000, prazos_meses=[24, 36, 48]),
        provedores=["pan"],
    )


def _resposta_simulacao():
    return {
        "results": {
            "simulacoes": [
                {
                    "prazo": {"quantidade": 24},
                    "valores": {"parcela": 910.25, "principal": 17000},
                    "informacoesOperacao": {"taxasJuros": {"baseMes": 1.79}},
                },
                {
                    "prazo": {"quantidade": 48},
                    "valores": {"parcela": 512.30, "liberado": 17000},
                    "informacoesOperacao": {
                        "taxasJuros": {"cetMes": 2.06},
                        "valorTotalFinanciamento": 18100,
                    },
                },
            ]
        }
    }


def test_parse_resposta_pan_normaliza_ofertas():
    out = parse_simulacoes_pan(_resposta_simulacao(), _sol())
    assert [r.prazo_meses for r in out] == [24, 48]
    assert out[0].valor_parcela == Decimal("910.25")
    assert out[0].taxa_am == Decimal("1.79")
    assert out[1].valor_financiado == Decimal("18100")
    assert all(r.provedor == "pan" and r.status == "concluida" for r in out)


def test_driver_autentica_e_simula_sem_expor_segredos():
    requisicoes = []

    def handler(request: httpx.Request) -> httpx.Response:
        requisicoes.append(request)
        if request.url.path == "/veiculos/v0/tokens":
            esperado = base64.b64encode(b"api-key-teste:secret-teste").decode()
            assert request.headers["Authorization"] == f"Basic {esperado}"
            corpo = json.loads(request.content)
            assert corpo == {
                "username": "usuario-npv",
                "password": "senha-npv",
                "grant_type": "client_credentials+password",
            }
            return httpx.Response(200, json={"access_token": "token-curto"})
        assert request.url.path == "/openapi/veiculos/v1/simulacao"
        assert request.headers["Authorization"] == "Bearer token-curto"
        payload = json.loads(request.content)
        assert payload["dadosBasicos"]["idLoja"] == "98329834"
        assert payload["dadosCliente"]["cpf"] == "52998224725"
        assert payload["dadosVeiculos"][0]["categoria"] == "MOTOS"
        assert payload["simulacao"]["prazos"] == [
            {"quantidade": 24},
            {"quantidade": 36},
            {"quantidade": 48},
        ]
        return httpx.Response(200, json=_resposta_simulacao())

    driver = PanDriver(
        base_url="https://sandbox.pan.test",
        transport=httpx.MockTransport(handler),
        configuracao=CONFIG,
    )
    out = driver(_sol())
    assert len(out) == 2
    assert len(requisicoes) == 2
