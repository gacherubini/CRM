from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    DriverContext,
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    resolver_drivers,
)
from app.motor.bradesco import (
    PROVEDOR,
    BradescoDriver,
    corpo_indica_recaptcha_falhou,
    parse_moeda_br,
    parse_parcelas_bradesco,
    _formatar_moeda_input,
)

FIXTURE = Path(__file__).parent / "fixtures" / "bradesco" / "ofertas.html"


def _sol(**kwargs):
    base = dict(
        pessoa=Pessoa(
            cpf="52998224725",
            nascimento="2002-12-13",
            celular="(51) 98033-6365",
        ),
        veiculo=Veiculo(
            placa="FUV7G58",
            valor=21900,
            categoria="moto",
            uf_licenciamento="SP",
        ),
        condicoes=Condicoes(entrada=0, prazos_meses=[18, 24, 36, 48]),
        provedores=[PROVEDOR],
    )
    base.update(kwargs)
    return SolicitacaoSimulacao(**base)


# --- parsers -----------------------------------------------------------------


def test_parse_moeda_br():
    assert parse_moeda_br("R$ 1.234,56") == Decimal("1234.56")
    assert parse_moeda_br("890,12") == Decimal("890.12")


def test_parse_parcelas_botoes_nx_de_rs():
    html = """
    <button>48x de R$ 890,12</button>
    <button>36x de R$ 1.050,00</button>
    <button>12x Entrada mínima necessária</button>
    """
    pares = parse_parcelas_bradesco(html)
    assert (48, Decimal("890.12")) in pares
    assert (36, Decimal("1050.00")) in pares
    # Prazo bloqueado por entrada minima nao vira parcela numerica.
    assert all(p[0] != 12 for p in pares)


def test_parse_parcelas_da_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    pares = parse_parcelas_bradesco(html)
    assert pares == [
        (18, Decimal("1910.30")),
        (24, Decimal("1480.55")),
        (36, Decimal("1050.00")),
        (48, Decimal("890.12")),
    ]


def test_parse_parcelas_com_tags_separadas():
    """Cards do portal quebram '48x' / 'de' / 'R$ 890,12' em nos separados."""
    html = "<button><b>48x</b> de <b>R$ 890,12</b></button>"
    assert parse_parcelas_bradesco(html) == [(48, Decimal("890.12"))]


def test_formatar_moeda_input():
    assert _formatar_moeda_input(21900.0) == "21.900,00"
    assert _formatar_moeda_input(1500.5) == "1.500,50"


# --- driver (modo fixture, sem browser) --------------------------------------


def test_driver_fixture_multi_prazo():
    d = BradescoDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    out = d(_sol())
    assert len(out) == 4
    assert all(r.provedor == PROVEDOR and r.status == "concluida" for r in out)
    por_prazo = {r.prazo_meses: r.valor_parcela for r in out}
    assert por_prazo[48] == Decimal("890.12")
    assert por_prazo[18] == Decimal("1910.30")


def test_driver_filtra_prazos_pedidos():
    d = BradescoDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    out = d(_sol(condicoes=Condicoes(entrada=0, prazos_meses=[36, 48])))
    assert sorted(r.prazo_meses for r in out) == [36, 48]


def test_driver_financiado_valor_menos_entrada():
    d = BradescoDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    out = d(_sol(condicoes=Condicoes(entrada=1900, prazos_meses=[48])))
    assert out[0].valor_financiado == Decimal("20000")


def test_driver_entrada_zero_financia_valor_cheio():
    d = BradescoDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    out = d(_sol(condicoes=Condicoes(entrada=0, prazos_meses=[48])))
    # Entrada nao e obrigatoria no Bradesco: sem entrada, financia o valor cheio.
    assert out[0].valor_financiado == Decimal("21900")


def test_driver_sem_parcelas_intervencao():
    d = BradescoDriver(html_simulacao="<html><body>sem ofertas</body></html>")
    with pytest.raises(IntervencaoNecessaria) as ei:
        d(_sol())
    assert ei.value.codigo == "bradesco_sem_oferta"


def test_driver_sem_celular_rejeita():
    d = BradescoDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(RejeicaoNegocio) as ei:
        d(_sol(pessoa=Pessoa(cpf="52998224725", nascimento="2002-12-13")))
    assert ei.value.codigo == "celular_obrigatorio"


def test_driver_sem_cpf_rejeita():
    d = BradescoDriver(html_simulacao=FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(RejeicaoNegocio) as ei:
        d(_sol(pessoa=Pessoa(cpf="", nascimento="2002-12-13", celular="(51) 98033-6365")))
    assert ei.value.codigo == "dados_cliente"


# --- gating REAL_DRIVERS ------------------------------------------------------


def test_bradesco_em_real_drivers():
    from app.motor import drivers as D

    D._registrar_drivers_reais()
    assert PROVEDOR in D.REAL_DRIVERS


def test_gating_bradesco_sem_credencial_nao_resolve(db):
    from app.motor import drivers as D

    D._registrar_drivers_reais()
    pares = resolver_drivers(
        [PROVEDOR], db=db, cliente_id="10000000-0000-0000-0000-000000000001"
    )
    assert pares == []


def test_gating_bradesco_com_credencial_resolve(db):
    import uuid

    from app import cripto
    from app.models_db import CredencialProvedorORM
    from conftest import TEST_CLIENT_ID

    db.add(
        CredencialProvedorORM(
            id=str(uuid.uuid4()),
            cliente_id=TEST_CLIENT_ID,
            provedor=PROVEDOR,
            usuario="12345678900",
            senha_cifrada=cripto.cifrar("senha-teste"),
            habilitado=True,
        )
    )
    db.commit()
    pares = resolver_drivers([PROVEDOR], db=db, cliente_id=TEST_CLIENT_ID)
    assert len(pares) == 1
    nome, driver = pares[0]
    assert nome == PROVEDOR
    if hasattr(driver, "html_simulacao"):
        driver.html_simulacao = FIXTURE.read_text(encoding="utf-8")
    out = driver(_sol(), DriverContext(db=db, cliente_id=TEST_CLIENT_ID))
    assert len(out) >= 1


# --- login (unit, sem browser real) ------------------------------------------


def test_pular_troca_senha_clica_depois_nunca_trocar():
    """Interstitial 'senha expira em N dias' -> clicar 'Trocar senha depois'."""
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.url = "https://turbo.bradesco/originacaolojista/first-access/flow-feedback"
    page.get_by_text.return_value.first.wait_for.return_value = None

    driver._pular_troca_senha(page)

    nomes = [
        c.kwargs.get("name") or (c.args[1] if len(c.args) > 1 else None)
        for c in page.get_by_role.call_args_list
    ]
    padroes = [n.pattern for n in nomes if hasattr(n, "pattern")]
    assert any("Trocar senha depois" in p for p in padroes)
    # Nunca aciona o botao que troca a senha de verdade.
    assert not any(
        "Trocar senha" in p and "depois" not in p for p in padroes
    )


def test_pular_troca_senha_ausente_nao_quebra():
    """Sem o aviso de expiracao, segue direto sem clicar nada."""
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.url = "https://turbo.bradesco/originacaolojista/dashboard"
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("nao ha")

    driver._pular_troca_senha(page)

    page.get_by_role.assert_not_called()


def test_selecionar_versao_veiculo_marca_a_primeira():
    """Modal de versoes da placa -> marca o primeiro radio."""
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.get_by_text.return_value.first.wait_for.return_value = None

    driver._selecionar_versao_veiculo(page)

    page.get_by_role.assert_any_call("radio")
    # Usa .first (a primeira versao), nunca outra posicao.
    page.get_by_role.return_value.first.check.assert_called_once()


def test_selecionar_versao_veiculo_sem_modal_nao_quebra():
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.get_by_text.return_value.first.wait_for.side_effect = RuntimeError("sem modal")

    driver._selecionar_versao_veiculo(page)

    page.get_by_role.assert_not_called()


def test_clicar_avancar_desabilitado_erra_rapido():
    """Botao 'Avancar' que nao habilita -> ErroTransitorio(form_incompleto),
    SEM clicar no botao desabilitado (antes travava ~90s no click)."""
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.wait_for_function.side_effect = RuntimeError("nao habilitou")

    with pytest.raises(ErroTransitorio) as ei:
        driver._clicar_avancar(page)
    assert ei.value.codigo == "form_incompleto"
    # Nunca clica no botao desabilitado.
    page.get_by_role.return_value.first.click.assert_not_called()


def test_clicar_avancar_habilitado_clica():
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.wait_for_function.return_value = None  # habilitou

    driver._clicar_avancar(page)

    page.get_by_role.return_value.first.click.assert_called_once()


def test_preencher_placa_confirma_valor():
    """Le o valor de volta: se a placa entrou, retorna True."""
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.get_by_role.return_value.first.input_value.return_value = "FUV7G58"

    assert driver._preencher_placa(page, "FUV7G58") is True


def test_preencher_placa_vazia_retorna_false():
    """Se o campo ficou vazio (type nao pegou), retorna False apos os retries."""
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.get_by_role.return_value.first.input_value.return_value = ""

    assert driver._preencher_placa(page, "FUV7G58") is False


def test_selecionar_uf_escolhe_opcao_por_role():
    """UF via role=option (mais estavel que casar texto solto)."""
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()

    driver._selecionar_uf(page, "SP")

    roles = [c.args[0] for c in page.get_by_role.call_args_list if c.args]
    assert "option" in roles


def test_login_reutiliza_sessao_autenticada_apos_timeout_networkidle():
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.url = "https://turbo.bradesco/originacaolojista/login"
    page.goto.side_effect = RuntimeError("networkidle timeout")
    # Marcador autenticado visivel (botao "Nova proposta").
    page.get_by_role.return_value.first.is_visible.return_value = True

    driver._passo_login(page, "nao-deve-usar", "nao-deve-usar")

    # Nao deve tentar preencher CPF/Senha quando ja esta autenticado.
    page.get_by_role.return_value.first.fill.assert_not_called()


# --- reCAPTCHA no login -------------------------------------------------------


def test_corpo_indica_recaptcha_banner_exato():
    """Banner do print do dono: 'Erro ao tentar verificar o reCAPTCHA'."""
    assert corpo_indica_recaptcha_falhou(
        "Vamos começar?\nErro ao tentar verificar o reCAPTCHA\nCPF *\nSenha *"
    )


def test_corpo_indica_recaptcha_variantes():
    assert corpo_indica_recaptcha_falhou("Erro: falha ao verificar o reCAPTCHA")
    assert corpo_indica_recaptcha_falhou(
        "reCAPTCHA: Não sou um robô — selecione as imagens"
    )
    assert not corpo_indica_recaptcha_falhou("CPF ou senha inválidos")
    assert not corpo_indica_recaptcha_falhou("Nova proposta")
    assert not corpo_indica_recaptcha_falhou("")


def test_aguardar_pos_login_recaptcha_vira_captcha_login():
    """Banner rosa de reCAPTCHA deve virar IntervencaoNecessaria(captcha_login)."""
    driver = BradescoDriver(timeout_ms=5_000)
    page = MagicMock()
    page.url = "https://turbo.bradesco/originacaolojista/login"
    page.wait_for_function.return_value = None
    page.inner_text.return_value = (
        "Vamos começar? Informe seu CPF e senha\n"
        "Erro ao tentar verificar o reCAPTCHA\n"
        "CPF *\nSenha *\nEntrar"
    )
    page.locator.return_value.count.return_value = 0
    # Ainda na tela de login (sem Nova proposta).
    page.get_by_role.return_value.first.is_visible.return_value = False

    with pytest.raises(IntervencaoNecessaria) as ei:
        driver._aguardar_pos_login(page)
    assert ei.value.codigo == "captcha_login"


def test_passo_login_espera_grecaptcha_antes_de_entrar():
    """Antes de clicar Entrar, deve esperar window.grecaptcha.execute."""
    driver = BradescoDriver(timeout_ms=20_000)
    page = MagicMock()
    page.url = "https://turbo.bradesco/originacaolojista/login"
    page.goto.return_value = None
    # Nao autenticado: is_visible False para "Nova proposta".
    page.get_by_role.return_value.first.is_visible.return_value = False
    page.get_by_role.return_value.first.click.return_value = None
    page.get_by_role.return_value.first.fill.return_value = None
    page.get_by_role.return_value.first.type.return_value = None
    # _aguardar_pos_login: simula sucesso saindo do login.
    page.wait_for_function.return_value = None
    page.inner_text.return_value = "Nova proposta"
    # Apos "sucesso" do wait, _portal_autenticado deve aceitar.
    page.get_by_role.return_value.first.is_visible.side_effect = [
        False,  # _portal_autenticado no inicio do login (apos goto)
        True,  # _portal_autenticado dentro de _aguardar_pos_login
    ]

    driver._passo_login(page, "12345678900", "senha-x")

    # Deve ter pedido grecaptcha.execute em algum wait_for_function.
    scripts = []
    for call in page.wait_for_function.call_args_list:
        arg0 = call.args[0] if call.args else ""
        scripts.append(arg0 if isinstance(arg0, str) else str(arg0))
    assert any("grecaptcha" in s for s in scripts), scripts
