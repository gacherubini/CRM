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


class _FakePage:
    """Página mínima: só o que `_assert_portal_acessivel` lê."""

    def __init__(self, titulo: str, url: str, html: str):
        self._titulo = titulo
        self.url = url
        self._html = html

    def title(self) -> str:
        return self._titulo

    def content(self) -> str:
        return self._html


# Página real recebida pelo worker do Fontecred em 19 e 20/09/2026
# (Ray IDs a3dcabf918fdf191 e a3e1d06dfb04f8bf). Sem ela o driver procurava
# o campo de e-mail e terminava em `login_timeout`, escondendo o bloqueio.
_HTML_BLOQUEIO_CLOUDFLARE = """
<html><body>
<h1>Sorry, you have been blocked</h1>
<h2>You are unable to access fontecred.com.br</h2>
<p>This website is using a security service to protect itself from online attacks.</p>
<p>Cloudflare Ray ID: <code>a3e1d06dfb04f8bf</code> &bull;
Performance &amp; security by <a href="https://www.cloudflare.com">Cloudflare</a></p>
</body></html>
"""

# O portal do Fontecred fica ATRÁS da Cloudflare: a página boa também carrega
# script dela. Detector que olhe só a marca derruba login que estava funcionando.
_HTML_LOGIN_NORMAL = """
<html><head><title>Portal do Lojista</title></head><body>
<form><input name="email" type="email"><input name="senha" type="password">
<button>Login</button></form>
<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>
<script>window.__CF$cv$params={r:'a3e1d06dfb04f8bf'};</script>
</body></html>
"""


def test_bloqueio_da_cloudflare_vira_portal_bloqueado():
    from app.motor.drivers import IntervencaoNecessaria

    d = _FakeDriver()
    page = _FakePage(
        "Attention Required! | Cloudflare",
        "https://portal.fontecred.com.br/login",
        _HTML_BLOQUEIO_CLOUDFLARE,
    )
    try:
        d._assert_portal_acessivel(page)
    except IntervencaoNecessaria as exc:
        assert exc.codigo == "portal_bloqueado"
    else:
        raise AssertionError("bloqueio da Cloudflare passou batido")


def test_pagina_normal_atras_da_cloudflare_nao_e_bloqueio():
    d = _FakeDriver()
    page = _FakePage(
        "Portal do Lojista",
        "https://portal.fontecred.com.br/login",
        _HTML_LOGIN_NORMAL,
    )
    d._assert_portal_acessivel(page)
