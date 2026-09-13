from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    NOMES_REAIS,
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    resolver_drivers,
)
from app.motor.omni import (
    PROVEDOR,
    OmniDriver,
    _formatar_cpf,
    _formatar_fone,
    _resumo_painel,
    parse_moeda_br,
    parse_ofertas,
    parse_resumo,
)

# Captura REAL do painel de resultado em 10/09/2026 (proposta/nome anonimizados).
# Mantém as armadilhas verdadeiras: número da proposta, "15/30/60 dias",
# "1º pagamento" e o "0" do slider antes do 48x.
OFERTAS_REAIS = """
Simulação de financiamento Seguro e Assistências
Ajuste a entrada ou o valor financiado Valor da entrada Valor financiado
Essa proposta tem boa chance de aprovação, confirme com a consulta de crédito.
Entrada mínima: R$ 0 Entrada máxima: R$ 17.200 Parcelamento 0
48x de R$ 710,71 36x de R$ 746,72 24x de R$ 994,11 18x de R$ 1.246,05
12x de R$ 1.754,30 Venc. 1° parcela: 10 Out 2026 15 dias 30 dias 60 dias
Proposta n° 10000000 Fulano de Tal Veículo Yamaha Fazer 2021
Valor: R$ 19.200,00 Financiado: R$ 13.440,00 Entrada: R$ 5.760,00
1º pagamento: 10 Out 2026 Parcelas: 48x de R$ 710,71
Condições sujeitas à análise de crédito
"""


def _sol(**kwargs):
    base = dict(
        pessoa=Pessoa(
            cpf="52998224725",
            nascimento="2002-12-13",
            celular="(51) 98033-6365",
        ),
        veiculo=Veiculo(placa="FUV7G58", valor=21900, categoria="moto"),
        condicoes=Condicoes(entrada=0, prazos_meses=[24, 36, 48]),
        provedores=[PROVEDOR],
    )
    base.update(kwargs)
    return SolicitacaoSimulacao(**base)


# --- parsers ---------------------------------------------------------------


def test_parse_moeda_br():
    assert parse_moeda_br("1.212,76") == Decimal("1212.76")
    assert parse_moeda_br("R$ 710,71") == Decimal("710.71")


def test_parse_ofertas_le_painel_real():
    assert parse_ofertas(OFERTAS_REAIS) == [
        (12, Decimal("1754.30")),
        (18, Decimal("1246.05")),
        (24, Decimal("994.11")),
        (36, Decimal("746.72")),
        (48, Decimal("710.71")),
    ]


def test_parse_ofertas_ignora_numero_que_nao_e_prazo():
    # "10000000" é a proposta, "2026" o ano, "15/30/60 dias" o vencimento,
    # "1º pagamento" e o "0" do slider: nenhum é prazo.
    assert parse_ofertas(OFERTAS_REAIS)
    texto = "proposta 10000000 ano 2021 x 2.000,00 15 dias 24x de R$ 500,00"
    assert parse_ofertas(texto) == [(24, Decimal("500.00"))]


def test_parse_ofertas_nao_repete_prazo():
    texto = "48x de R$ 710,71 e de novo 48x de R$ 700,00"
    assert parse_ofertas(texto) == [(48, Decimal("710.71"))]


def test_parse_resumo_le_valor_financiado_entrada():
    resumo = parse_resumo(OFERTAS_REAIS)
    assert resumo["valor"] == Decimal("19200.00")
    assert resumo["financiado"] == Decimal("13440.00")
    assert resumo["entrada"] == Decimal("5760.00")


def test_formatar_cpf_e_fone():
    assert _formatar_cpf("52998224725") == "529.982.247-25"
    assert _formatar_fone("51980336365") == "(51) 98033-6365"


def test_resumo_painel_mascara_cpf():
    assert "<cpf>" in _resumo_painel("cliente 529.982.247-25 fim")
    assert "529" not in _resumo_painel("cliente 529.982.247-25 fim")


# --- desfechos do driver ---------------------------------------------------


def test_driver_filtra_prazos_pedidos_e_usa_resumo_do_portal():
    driver = OmniDriver(html_simulacao=OFERTAS_REAIS)
    resultados = driver.simular(_sol(), None)
    assert [(r.prazo_meses, r.valor_parcela) for r in resultados] == [
        (24, Decimal("994.11")),
        (36, Decimal("746.72")),
        (48, Decimal("710.71")),
    ]
    # O portal trocou o valor pelo cotação: o que vale é a tela.
    assert resultados[0].valor_financiado == Decimal("13440.00")
    assert resultados[0].entrada == Decimal("5760.00")
    assert all(r.status == "concluida" and r.provedor == "omni" for r in resultados)


def test_driver_prazo_indisponivel_rejeita():
    driver = OmniDriver(html_simulacao=OFERTAS_REAIS)
    sol = _sol(condicoes=Condicoes(entrada=0, prazos_meses=[60]))
    with pytest.raises(RejeicaoNegocio) as exc:
        driver.simular(sol, None)
    assert exc.value.codigo == "omni_prazo_indisponivel"


def test_driver_sem_oferta_rejeita():
    driver = OmniDriver(html_simulacao="Não há oferta de crédito para este cliente")
    with pytest.raises(RejeicaoNegocio) as exc:
        driver.simular(_sol(), None)
    assert exc.value.codigo == "credito_recusado"


FIXTURE_RECUSA = Path(__file__).parent / "fixtures" / "omni" / "recusa_credito.html"


def test_recusa_real_vira_credito_recusado():
    driver = OmniDriver(html_simulacao=FIXTURE_RECUSA.read_text(encoding="utf-8"))
    with pytest.raises(RejeicaoNegocio) as exc:
        driver.simular(_sol(), None)
    assert exc.value.codigo == "credito_recusado"


def test_driver_painel_ilegivei_pede_intervencao():
    driver = OmniDriver(html_simulacao="Simulação de financiamento aguarde")
    with pytest.raises(IntervencaoNecessaria) as exc:
        driver.simular(_sol(), None)
    assert exc.value.codigo == "ofertas_ilegiveis"


def test_driver_valida_solicitacao():
    driver = OmniDriver(html_simulacao=OFERTAS_REAIS)
    with pytest.raises(RejeicaoNegocio):
        driver.simular(
            _sol(pessoa=Pessoa(cpf="", nascimento="2002-12-13",
                               celular="(51) 98033-6365")),
            None,
        )
    with pytest.raises(RejeicaoNegocio):
        driver.simular(
            _sol(pessoa=Pessoa(cpf="52998224725", nascimento="2002-12-13",
                               celular="")),
            None,
        )
    with pytest.raises(RejeicaoNegocio):
        driver.simular(_sol(veiculo=Veiculo(valor=21900, categoria="moto")), None)


# --- registro ----------------------------------------------------------------


def test_omni_registrado_como_real():
    assert "omni" in NOMES_REAIS
    db = MagicMock()
    from app import credenciais as _cred

    _orig = _cred.configuracao_completa
    _cred.configuracao_completa = lambda db_, cid, prov: prov == "omni"
    try:
        pares = resolver_drivers(["omni"], cliente_id="loja-1", db=db)
    finally:
        _cred.configuracao_completa = _orig
    assert [nome for nome, _ in pares] == ["omni"]
