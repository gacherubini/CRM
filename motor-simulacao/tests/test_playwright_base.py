from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import DriverContext, ResultadoDriver
from app.motor.playwright_base import PlaywrightBankDriver


class _FakeDriver(PlaywrightBankDriver):
    provedor = "fake_banco"

    def simular(self, sol, ctx=None):
        prazos = sol.condicoes.prazos_meses or [sol.condicoes.prazo_meses or 0]
        return [
            ResultadoDriver(
                self.provedor,
                "concluida",
                valor_parcela=100 + p,
                taxa_am=1.5,
                prazo_meses=p,
                valor_financiado=9000,
            )
            for p in prazos
        ]


def test_playwright_base_callable_retorna_lista():
    d = _FakeDriver()
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-01-01"),
        veiculo=Veiculo(placa="ABC1D23", finalidade="comum"),
        condicoes=Condicoes(entrada=0, prazos_meses=[24, 48]),
    )
    out = d(sol, DriverContext())
    assert isinstance(out, list) and len(out) == 2
    assert out[0].provedor == "fake_banco"
    assert d.real is True


def test_falha_campo_gera_intervencao():
    d = _FakeDriver()
    exc = d._falha_campo("CPF")
    assert exc.codigo == "campo_nao_encontrado"
    assert "CPF" in str(exc)


def test_browser_headless_padrao_e_zero_por_padrao(monkeypatch):
    from app.motor.playwright_base import browser_headless_padrao

    monkeypatch.delenv("MOTOR_BROWSER_HEADLESS", raising=False)
    assert browser_headless_padrao() is False
    monkeypatch.setenv("MOTOR_BROWSER_HEADLESS", "1")
    assert browser_headless_padrao() is True
    monkeypatch.setenv("MOTOR_BROWSER_HEADLESS", "0")
    assert browser_headless_padrao() is False


def test_stealth_init_remove_webdriver_flag():
    from app.motor import playwright_base as pb

    assert "webdriver" in pb._STEALTH_INIT
    assert "--enable-automation" in pb._IGNORE_DEFAULT_ARGS
