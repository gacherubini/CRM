import re
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import config
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    DriverContext,
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    resolver_drivers,
)
from app.motor.fontecred import (
    COMUNICADO_TITULO,
    PROVEDOR,
    FontecredDriver,
    parse_entrada,
    parse_moeda_br,
    parse_parcelas_texto,
    parse_valor_financiado,
    _formatar_moeda_input,
    _formatar_nascimento_iso,
)

FIXTURE = Path(__file__).parent / "fixtures" / "fontecred" / "simulacao_parcelas.html"


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


def test_parse_moeda_br():
    assert parse_moeda_br("1.212,76") == Decimal("1212.76")
    assert parse_moeda_br("R$ 928,95") == Decimal("928.95")


def test_parse_parcelas_da_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    pares = parse_parcelas_texto(html)
    assert pares == [
        (24, Decimal("1212.76")),
        (36, Decimal("928.95")),
        (48, Decimal("809.63")),
    ]


def test_parse_parcelas_com_spans_separados():
    """Botões do portal quebram '24x' e '1.212,76' em nós separados."""
    html = """
    <button><span>Melhor Condição</span><span>24x</span><span>1.212,76</span><span>Proposta</span></button>
    <button><span>36x</span><span>928,95</span></button>
    <div>48x
    809,63</div>
    """
    assert parse_parcelas_texto(html) == [
        (24, Decimal("1212.76")),
        (36, Decimal("928.95")),
        (48, Decimal("809.63")),
    ]


def test_parse_entrada_da_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    assert parse_entrada(html) == Decimal("3956.40")


def test_parse_entrada_aceita_rotulo_minima():
    assert parse_entrada("Entrada mínima R$ 1.500,00") == Decimal("1500.00")
    assert parse_entrada("Sua entrada: 3.956,40") == Decimal("3956.40")


def test_parse_entrada_ausente_retorna_none():
    assert parse_entrada("<html><body>sem entrada</body></html>") is None


def test_parse_valor_financiado():
    assert parse_valor_financiado("Valor de financiamento R$ 17.943,60") == Decimal(
        "17943.60"
    )
    assert parse_valor_financiado("sem financiado") is None


def test_formatar_moeda_input():
    assert _formatar_moeda_input(21900.0) == "21.900,00"
    assert _formatar_moeda_input(0.0) == "0,00"
    assert _formatar_moeda_input(1500.5) == "1.500,50"


def test_formatar_nascimento_iso():
    assert _formatar_nascimento_iso("2002-12-13") == "2002-12-13"
    assert _formatar_nascimento_iso("13/12/2002") == "2002-12-13"


def test_driver_fixture_multi_prazo():
    html = FIXTURE.read_text(encoding="utf-8")
    d = FontecredDriver(html_simulacao=html)
    out = d(_sol())
    assert len(out) == 3
    assert all(r.provedor == PROVEDOR and r.status == "concluida" for r in out)
    por_prazo = {r.prazo_meses: r.valor_parcela for r in out}
    assert por_prazo[24] == Decimal("1212.76")
    assert por_prazo[48] == Decimal("809.63")


def test_driver_devolve_entrada_minima_em_cada_prazo():
    html = FIXTURE.read_text(encoding="utf-8")
    d = FontecredDriver(html_simulacao=html)
    out = d(_sol())
    # Portal devolve a entrada mínima (mesma para todos os prazos).
    assert all(r.entrada == Decimal("3956.40") for r in out)


def test_driver_financiado_fallback_valor_menos_entrada():
    html = FIXTURE.read_text(encoding="utf-8")
    d = FontecredDriver(html_simulacao=html)
    out = d(_sol())
    # Financiado não vem no inner_text (é input readonly) => valor - entrada.
    assert all(r.valor_financiado == Decimal("17943.60") for r in out)


def test_driver_filtra_prazos_pedidos():
    html = FIXTURE.read_text(encoding="utf-8")
    d = FontecredDriver(html_simulacao=html)
    out = d(_sol(condicoes=Condicoes(entrada=0, prazos_meses=[36, 48])))
    assert sorted(r.prazo_meses for r in out) == [36, 48]


def test_driver_sem_parcelas_intervencao():
    d = FontecredDriver(html_simulacao="<html><body>sem cards</body></html>")
    with pytest.raises(IntervencaoNecessaria) as ei:
        d(_sol())
    assert ei.value.codigo == "parcelas_nao_encontradas"


def test_driver_sem_celular_rejeita():
    d = FontecredDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(RejeicaoNegocio) as ei:
        d(_sol(pessoa=Pessoa(cpf="52998224725", nascimento="2002-12-13")))
    assert ei.value.codigo == "celular_obrigatorio"


def test_driver_sem_placa_rejeita():
    d = FontecredDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(RejeicaoNegocio) as ei:
        d(_sol(veiculo=Veiculo(valor=21900, categoria="moto")))
    assert ei.value.codigo == "placa_obrigatoria"


def test_fechar_comunicados_usa_seletor_bootstrap_5():
    driver = FontecredDriver()
    page = MagicMock()
    titulo = MagicMock()
    titulo.is_visible.return_value = False
    page.get_by_text.return_value.first = titulo
    page.get_by_role.return_value.first.click.side_effect = RuntimeError("sem botão")

    driver._fechar_comunicados(page)

    seletor = page.locator.call_args.args[0]
    assert ".btn-close" in seletor
    assert "data-bs-dismiss" in seletor
    page.locator.return_value.first.click.assert_called_once_with(
        timeout=3_000, force=True
    )
    titulo.wait_for.assert_any_call(state="visible", timeout=5_000)
    titulo.wait_for.assert_any_call(state="hidden", timeout=5_000)


def test_fechar_comunicados_falha_se_modal_persistir():
    driver = FontecredDriver()
    page = MagicMock()
    page.get_by_text.return_value.first.is_visible.return_value = True
    page.get_by_role.return_value.first.click.side_effect = RuntimeError("sem botão")
    page.locator.return_value.first.click.side_effect = RuntimeError("sem X")

    with pytest.raises(ErroTransitorio) as ei:
        driver._fechar_comunicados(page)

    assert ei.value.codigo == "comunicados_nao_fechou"
    page.keyboard.press.assert_called_once_with("Escape")


def test_comunicado_no_singular_tambem_e_detectado():
    """O portal usa COMUNICADO na tela de proposta e COMUNICADOS no dashboard.

    Casar so o plural fazia o driver seguir sem fechar e bater no overlay ao
    clicar no CPF (sim 20260904-150259, codigo enganoso `nova_proposta_falhou`).
    """
    padrao = re.compile(COMUNICADO_TITULO, re.I)
    assert padrao.match("COMUNICADO")
    assert padrao.match("COMUNICADOS")
    assert padrao.match("  Comunicado  ")
    assert not padrao.match("COMUNICADO PENDENTE")


def test_nova_proposta_fecha_modal_antes_de_clicar_no_cpf():
    """Modal aberto na tela de proposta vira erro proprio, nao `nova_proposta_falhou`."""
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    page.get_by_text.return_value.first.is_visible.return_value = True
    page.get_by_role.return_value.first.click.side_effect = RuntimeError("sem botão")
    page.locator.return_value.first.click.side_effect = RuntimeError("sem X")

    with pytest.raises(ErroTransitorio) as ei:
        driver._passo_nova_proposta(page)

    assert ei.value.codigo == "comunicados_nao_fechou"


def test_nova_proposta_aceita_timeout_se_cpf_ja_apareceu():
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    page.goto.side_effect = RuntimeError("timeout após commit")
    # Sem modal nesta tela: o título não aparece e não há nada a fechar.
    titulo = page.get_by_text.return_value.first
    titulo.wait_for.side_effect = RuntimeError("sem modal")
    titulo.is_visible.return_value = False
    cpf_box = page.get_by_role.return_value.first

    driver._passo_nova_proposta(page)

    page.goto.assert_called_once_with(
        "https://app.fontecred.com.br/clientes/criarComProposta",
        wait_until="commit",
        timeout=20_000,
    )
    cpf_box.wait_for.assert_called_once_with(state="visible", timeout=15_000)
    cpf_box.click.assert_called_once_with(trial=True, timeout=15_000)
    page.wait_for_load_state.assert_called_once_with(
        "domcontentloaded", timeout=20_000
    )


def test_pos_login_aguarda_dashboard_e_dom_pronto():
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()

    driver._aguardar_pos_login(page)

    expressao = page.wait_for_function.call_args_list[0].args[0]
    assert "COMUNICADOS" in expressao
    assert "Dashboard" in expressao
    page.wait_for_load_state.assert_called_once_with(
        "domcontentloaded", timeout=20_000
    )


def test_login_reutiliza_sessao_autenticada_apos_timeout_networkidle():
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    page.url = "https://app.fontecred.com.br/login#step-1"
    page.goto.side_effect = RuntimeError("networkidle timeout")
    page.get_by_text.return_value.first.is_visible.return_value = True

    driver._passo_login(page, "nao-deve-usar", "nao-deve-usar")

    page.goto.assert_called_once_with(
        "https://app.fontecred.com.br/login#step-1",
        wait_until="networkidle",
        timeout=20_000,
    )
    page.get_by_role.assert_not_called()
    page.wait_for_load_state.assert_called_once_with(
        "domcontentloaded", timeout=20_000
    )


def test_evento_registra_print_por_etapa(monkeypatch):
    driver = FontecredDriver()
    ctx = MagicMock()
    ctx.screenshot_dir = None
    ctx.simulacao_id = "sim-teste"
    page = MagicMock()
    page.screenshot.return_value = b"fake-jpeg"
    monkeypatch.setattr(config, "EVENT_SCREENSHOTS", True)

    driver._evento(ctx, "login_confirmado", "Login confirmado.", page, True)

    page.screenshot.assert_called()
    assert ctx.registrar_evento.called
    kwargs = ctx.registrar_evento.call_args
    assert kwargs[0][0] == "login_confirmado"
    assert kwargs[0][1] == "Login confirmado."
    # path e/ou bytes de print
    assert kwargs.kwargs.get("screenshot_path") or kwargs.kwargs.get("screenshot_conteudo")


def test_gating_fontecred_sem_credencial_nao_resolve(db):
    from app.motor import drivers as D

    D._registrar_drivers_reais()
    assert PROVEDOR in D.REAL_DRIVERS
    pares = resolver_drivers(
        [PROVEDOR], db=db, cliente_id="10000000-0000-0000-0000-000000000001"
    )
    assert pares == []


def test_gating_fontecred_com_credencial_resolve(db):
    import uuid

    from app import cripto
    from app.models_db import CredencialProvedorORM
    from conftest import TEST_CLIENT_ID

    db.add(
        CredencialProvedorORM(
            id=str(uuid.uuid4()),
            cliente_id=TEST_CLIENT_ID,
            provedor=PROVEDOR,
            usuario="lojista@example.com",
            senha_cifrada=cripto.cifrar("senha-teste"),
            habilitado=True,
        )
    )
    db.commit()
    pares = resolver_drivers([PROVEDOR], db=db, cliente_id=TEST_CLIENT_ID)
    assert len(pares) == 1
    nome, driver = pares[0]
    assert nome == PROVEDOR
    d = driver
    if hasattr(d, "html_simulacao"):
        d.html_simulacao = FIXTURE.read_text(encoding="utf-8")
    out = d(_sol(), DriverContext(db=db, cliente_id=TEST_CLIENT_ID))
    assert len(out) >= 1


def test_produto_preenchido_conta_como_veiculo_resolvido():
    """Sucesso e lido da pagina (#produto), nao de "o clique nao deu erro"."""
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    page.locator.return_value.first.input_value.return_value = "8049"

    driver._confirmar_produto_resolvido(page)  # nao levanta


def test_produto_vazio_e_veiculo_nao_resolvido():
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    page.locator.return_value.first.input_value.return_value = ""

    with pytest.raises(ErroTransitorio) as ei:
        driver._confirmar_produto_resolvido(page)

    assert ei.value.codigo == "veiculo_nao_resolvido"


def test_modal_de_placa_tratado_dispensa_a_linha_com_botao():
    """Depois do modal escolhido nao sobra 'linha com botao'; clicar la era o bug."""
    driver = FontecredDriver(timeout_ms=20_000)
    assert driver._resolver_modal_placa.__doc__  # documenta o retorno bool

    page = MagicMock()
    page.get_by_text.return_value.first.wait_for.side_effect = [None, None]
    page.get_by_role.return_value.first.click.return_value = None

    assert driver._resolver_modal_placa(page) is True


def test_placa_de_versao_unica_nao_abre_modal():
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("sem modal")

    assert driver._resolver_modal_placa(page) is False
    page.get_by_role.assert_not_called()


def test_valor_de_venda_que_nao_gruda_falha_na_hora():
    """Overlay deixava o campo vazio e o driver so morria 90s depois, no Simular."""
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    caixa = page.get_by_role.return_value.first
    caixa.input_value.return_value = ""

    with pytest.raises(ErroTransitorio) as ei:
        driver._passo_financiamento(page, _sol())

    assert ei.value.codigo == "valor_venda_nao_aplicou"


def test_autorizacao_ja_marcada_nao_reclica():
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    page.evaluate.return_value = True

    driver._marcar_autorizacao(page)

    page.get_by_role.assert_not_called()


def test_autorizacao_que_nao_gruda_falha_com_codigo_proprio():
    """Sem ela o portal recusa o Simular; o `except: pass` antigo escondia isso."""
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    page.evaluate.return_value = False  # nunca marca

    with pytest.raises(ErroTransitorio) as ei:
        driver._marcar_autorizacao(page)

    assert ei.value.codigo == "autorizacao_scr_nao_marcada"


def test_autorizacao_marcada_na_segunda_tentativa():
    driver = FontecredDriver(timeout_ms=20_000)
    page = MagicMock()
    # nao marcada, 1a tentativa falha, 2a funciona
    page.evaluate.side_effect = [False, False, True]
    page.get_by_role.return_value.first.check.side_effect = RuntimeError("sem role")

    driver._marcar_autorizacao(page)

    page.get_by_text.return_value.first.click.assert_called_once()
