from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    DriverContext,
    RejeicaoNegocio,
    resolver_drivers,
)
from app.motor.pan_portal import (
    PROVEDOR,
    PanPortalDriver,
    parse_entrada,
    parse_financiado,
    parse_moeda_br,
    parse_parcelas_pan_portal,
    _formatar_moeda_input,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pan_portal" / "resultado.html"


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


# --- parsers -----------------------------------------------------------------


def test_parse_moeda_br():
    assert parse_moeda_br("R$ 1.095,00") == Decimal("1095.00")
    assert parse_moeda_br("620,45") == Decimal("620.45")


def test_parse_parcelas_da_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    assert parse_parcelas_pan_portal(html) == [
        (24, Decimal("1095.00")),
        (36, Decimal("780.10")),
        (48, Decimal("620.45")),
    ]


def test_parse_parcelas_spans_separados():
    html = "<button><span>24x</span><span>1.095,00</span></button>"
    assert parse_parcelas_pan_portal(html) == [(24, Decimal("1095.00"))]


def test_parse_entrada_da_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    assert parse_entrada(html) == Decimal("2190.00")


def test_parse_financiado():
    # aceita 1 ou 2 casas (portal as vezes trunca: "15.116,8")
    assert parse_financiado("Financiado: R$ 15.116,80") == Decimal("15116.80")
    assert parse_financiado("Financiado R$ 15.116,8") == Decimal("15116.8")
    assert parse_financiado("sem financiado") is None


def test_driver_usa_financiado_do_portal():
    html = (
        "<div>48x R$ 800,00</div>"
        "<div>Financiado: R$ 15.116,80</div>"
        "<div>Entrada: R$ 6.783,20</div>"
    )
    d = PanPortalDriver(html_simulacao=html)
    out = d(_sol(condicoes=Condicoes(entrada=0, prazos_meses=[48])))
    assert out[0].valor_financiado == Decimal("15116.80")
    assert out[0].entrada == Decimal("6783.20")


def test_formatar_moeda_input():
    assert _formatar_moeda_input(21900.0) == "21.900,00"


# --- driver (modo fixture) ---------------------------------------------------


def test_driver_fixture_multi_prazo():
    d = PanPortalDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    out = d(_sol())
    assert len(out) == 3
    assert all(r.provedor == PROVEDOR and r.status == "concluida" for r in out)
    por_prazo = {r.prazo_meses: r.valor_parcela for r in out}
    assert por_prazo[48] == Decimal("620.45")


def test_driver_devolve_entrada_minima():
    d = PanPortalDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    out = d(_sol())
    assert all(r.entrada == Decimal("2190.00") for r in out)


def test_driver_filtra_prazos():
    d = PanPortalDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    out = d(_sol(condicoes=Condicoes(entrada=0, prazos_meses=[36])))
    assert [r.prazo_meses for r in out] == [36]


def test_driver_sem_parcelas_rejeita():
    d = PanPortalDriver(html_simulacao="<html><body>sem cards</body></html>")
    with pytest.raises(RejeicaoNegocio) as ei:
        d(_sol())
    assert ei.value.codigo == "pan_sem_oferta"


def test_driver_sem_celular_rejeita():
    d = PanPortalDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(RejeicaoNegocio) as ei:
        d(_sol(pessoa=Pessoa(cpf="52998224725", nascimento="2002-12-13")))
    assert ei.value.codigo == "celular_obrigatorio"


def test_driver_sem_placa_rejeita():
    d = PanPortalDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(RejeicaoNegocio) as ei:
        d(_sol(veiculo=Veiculo(valor=21900, categoria="moto")))
    assert ei.value.codigo == "placa_obrigatoria"


# --- login (unit) ------------------------------------------------------------


def test_login_fecha_got_it_banner():
    driver = PanPortalDriver(timeout_ms=20_000)
    page = MagicMock()
    page.url = "https://veiculos.bancopan.com.br/login"
    page.goto.side_effect = RuntimeError("networkidle timeout")
    # nao autenticado (url ainda em /login) -> segue login normal
    page.get_by_role.return_value.first.wait_for.return_value = None

    driver._fechar_got_it(page)

    nomes = [
        c.kwargs.get("name") or (c.args[1] if len(c.args) > 1 else None)
        for c in page.get_by_role.call_args_list
    ]
    padroes = [n.pattern for n in nomes if hasattr(n, "pattern")]
    assert any("Got it" in p for p in padroes)


# --- dual-path: API vs portal ------------------------------------------------


def test_pan_resolve_portal_com_so_usuario_senha(db):
    import uuid

    from app import cripto
    from app.models_db import CredencialProvedorORM
    from conftest import TEST_CLIENT_ID
    from app.motor.pan_portal import PanPortalDriver as _PPD

    db.add(
        CredencialProvedorORM(
            id=str(uuid.uuid4()),
            cliente_id=TEST_CLIENT_ID,
            provedor="pan",
            usuario="loja42",
            senha_cifrada=cripto.cifrar("senha-teste"),
            habilitado=True,
        )
    )
    db.commit()
    pares = resolver_drivers(["pan"], db=db, cliente_id=TEST_CLIENT_ID)
    assert len(pares) == 1
    nome, driver = pares[0]
    assert nome == "pan"
    # driver e o dispatcher; ao rodar sem config API, instancia o PanPortalDriver.
    # Confirmamos que o caminho portal e escolhido injetando html de fixture.
    from app.motor import pan_portal

    chamado = {}
    original = pan_portal.fabrica_pan_portal

    def _fabrica_espia():
        d = original()
        d.html_simulacao = FIXTURE.read_text(encoding="utf-8")
        chamado["portal"] = True
        return d

    pan_portal.fabrica_pan_portal = _fabrica_espia
    try:
        out = driver(_sol(), DriverContext(db=db, cliente_id=TEST_CLIENT_ID))
    finally:
        pan_portal.fabrica_pan_portal = original
    assert chamado.get("portal") is True
    assert len(out) >= 1


def test_pan_usa_api_quando_config_completa(db, monkeypatch):
    from conftest import TEST_CLIENT_ID
    from app import credenciais
    from app.motor import pan as pan_mod

    campos = {
        "api_key": "k",
        "secret_key": "s",
        "usuario": "u",
        "senha": "p",
        "id_loja": "1",
        "tipo_id_loja": "CODIGO",
        "codigo_produto": "MOTOS",
        "tipo_calculo": "VALOR_ENTRADA",
    }
    # Config OpenAPI completa -> gating e dispatcher enxergam todos os campos.
    monkeypatch.setattr(
        credenciais, "obter_configuracao_para_uso", lambda *a, **k: dict(campos)
    )

    chamado = {}

    def _fake_fabrica_pan():
        d = MagicMock(return_value=["API_OK"])
        chamado["api"] = True
        return d

    monkeypatch.setattr(pan_mod, "fabrica_pan", _fake_fabrica_pan)
    pares = resolver_drivers(["pan"], db=db, cliente_id=TEST_CLIENT_ID)
    assert len(pares) == 1
    _, driver = pares[0]
    out = driver(_sol(), DriverContext(db=db, cliente_id=TEST_CLIENT_ID))
    assert chamado.get("api") is True
    assert out == ["API_OK"]
