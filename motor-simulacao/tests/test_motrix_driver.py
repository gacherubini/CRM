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
from app.motor.motrix import (
    PROVEDOR,
    MotrixDriver,
    _formatar_moeda_input,
    parse_moeda_br,
    parse_ofertas,
    parse_taxa,
)

FIXTURE_SEM_OFERTA = Path(__file__).parent / "fixtures" / "motrix" / "sem_oferta.txt"

# O portal nunca devolveu oferta para o cliente de teste (recusou em 04/09), entao
# nao ha captura real do painel de ofertas. Estes textos sao SINTETICOS e existem
# so para fixar o parser; quando aparecer uma oferta de verdade, troque por captura.
OFERTAS_SINTETICAS = """
Simulacao
Tabela R0
24x R$ 1.212,76
36x R$ 928,95
48x R$ 809,63
Taxa 2,49% a.m.
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
    assert parse_moeda_br("R$ 928,95") == Decimal("928.95")


def test_parse_ofertas_le_prazo_e_parcela():
    assert parse_ofertas(OFERTAS_SINTETICAS) == [
        (24, Decimal("1212.76")),
        (36, Decimal("928.95")),
        (48, Decimal("809.63")),
    ]


def test_parse_ofertas_ignora_numero_que_nao_e_prazo():
    # "950009" e o codigo do produto e "2021" o ano modelo: nenhum e prazo.
    texto = "produto 950009 x 1.000,00 ano 2021 x 2.000,00 24x R$ 500,00"
    assert parse_ofertas(texto) == [(24, Decimal("500.00"))]


def test_parse_ofertas_nao_repete_prazo():
    texto = "24x R$ 500,00 e de novo 24x R$ 600,00"
    assert parse_ofertas(texto) == [(24, Decimal("500.00"))]


def test_parse_taxa():
    assert parse_taxa("Taxa 2,49% a.m.") == Decimal("2.49")
    assert parse_taxa("sem taxa aqui") is None


def test_formatar_moeda_input():
    # O campo tem mascara e recusa ponto decimal.
    assert _formatar_moeda_input(21900) == "21.900,00"
    assert _formatar_moeda_input(0) == "0,00"


# --- desfechos do driver ---------------------------------------------------


def test_driver_le_ofertas_de_texto():
    driver = MotrixDriver(html_simulacao=OFERTAS_SINTETICAS)
    resultados = driver.simular(_sol())
    assert [r.prazo_meses for r in resultados] == [24, 36, 48]
    assert all(r.provedor == PROVEDOR for r in resultados)
    assert all(r.status == "concluida" for r in resultados)


def test_driver_filtra_prazos_pedidos():
    driver = MotrixDriver(html_simulacao=OFERTAS_SINTETICAS)
    resultados = driver.simular(_sol(condicoes=Condicoes(entrada=0, prazos_meses=[36])))
    assert [r.prazo_meses for r in resultados] == [36]


def test_driver_financiado_desconta_entrada():
    driver = MotrixDriver(html_simulacao=OFERTAS_SINTETICAS)
    resultados = driver.simular(
        _sol(condicoes=Condicoes(entrada=1900, prazos_meses=[24]))
    )
    assert resultados[0].valor_financiado == Decimal("20000")
    assert resultados[0].entrada == Decimal("1900")


def test_recusa_do_portal_vira_rejeicao_de_negocio():
    """A captura real de 04/09: o Motrix respondeu que nao ha oferta."""
    texto = FIXTURE_SEM_OFERTA.read_text(encoding="utf-8")
    driver = MotrixDriver(html_simulacao=texto)
    with pytest.raises(RejeicaoNegocio) as exc:
        driver.simular(_sol())
    assert exc.value.codigo == "motrix_sem_oferta"


def test_tela_sem_parcela_nao_vira_sucesso_vazio():
    driver = MotrixDriver(html_simulacao="Simulacao\nTabela R0\n")
    with pytest.raises(RejeicaoNegocio):
        driver.simular(_sol())


def test_prazo_ofertado_diferente_do_pedido_e_rejeicao_explicita():
    driver = MotrixDriver(html_simulacao="12x R$ 2.000,00")
    with pytest.raises(RejeicaoNegocio) as exc:
        driver.simular(_sol(condicoes=Condicoes(entrada=0, prazos_meses=[48])))
    assert exc.value.codigo == "motrix_prazo_indisponivel"


# --- validacao de entrada --------------------------------------------------


@pytest.mark.parametrize(
    "campo, kwargs, codigo",
    [
        ("celular", {"pessoa": Pessoa(cpf="52998224725", nascimento="2002-12-13")},
         "celular_obrigatorio"),
        ("placa", {"veiculo": Veiculo(valor=21900, categoria="moto")},
         "placa_obrigatoria"),
        ("valor", {"veiculo": Veiculo(placa="FUV7G58", categoria="moto")},
         "valor_obrigatorio"),
    ],
)
def test_driver_rejeita_sem_campo_obrigatorio(campo, kwargs, codigo):
    driver = MotrixDriver(html_simulacao=OFERTAS_SINTETICAS)
    with pytest.raises(RejeicaoNegocio) as exc:
        driver.simular(_sol(**kwargs))
    assert exc.value.codigo == codigo


def test_live_sem_contexto_pede_intervencao():
    driver = MotrixDriver()
    with pytest.raises(IntervencaoNecessaria) as exc:
        driver.simular(_sol())
    assert exc.value.codigo == "sem_contexto"


# --- registro --------------------------------------------------------------


def test_motrix_esta_no_conjunto_de_nomes_reais():
    """O conjunto era escrito a mao em dois lugares de drivers.py; banco novo
    esquecido no segundo sumia em silencio."""
    assert "motrix" in NOMES_REAIS


def test_motrix_resolve_com_credencial():
    db = MagicMock()
    with pytest.MonkeyPatch.context() as mp:
        import app.motor.drivers as mod

        mp.setattr(mod, "_tem_credencial_real", lambda *a, **k: True)
        pares = resolver_drivers(["motrix"], cliente_id="c1", db=db)
    assert [nome for nome, _ in pares] == ["motrix"]


def test_motrix_sem_credencial_nao_cai_no_mock():
    db = MagicMock()
    with pytest.MonkeyPatch.context() as mp:
        import app.motor.drivers as mod

        mp.setattr(mod, "_tem_credencial_real", lambda *a, **k: False)
        pares = resolver_drivers(["motrix"], cliente_id="c1", db=db)
    assert pares == []


def test_motrix_no_catalogo_de_provedores():
    from app.motor.providers import obter_provedor

    meta = obter_provedor("motrix")
    assert meta is not None
    assert meta["real"] is True
    assert {c["nome"] for c in meta["campos_credencial"]} == {"usuario", "senha"}


def test_motrix_nao_usa_browser_alem_do_teto():
    """Driver Playwright conta no teto de 2 browsers (decisao B+D de IP)."""
    assert MotrixDriver.usa_browser is True


def test_pedido_de_prazo_fora_da_faixa_nao_e_lido_como_oferta():
    assert parse_ofertas("2021 x R$ 100,00") == []
    assert parse_ofertas("72x R$ 100,00") == []
