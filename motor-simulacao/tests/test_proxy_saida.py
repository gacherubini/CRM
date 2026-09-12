"""Saída de rede do browser por proxy (MOTOR_PROXY_URL) e conferência do IP."""
import pytest

from app.motor.drivers import IntervencaoNecessaria
from app.motor.playwright_base import PlaywrightBankDriver, proxy_padrao


class _Driver(PlaywrightBankDriver):
    provedor = "fake_banco"

    def simular(self, sol, ctx=None):  # pragma: no cover - não usado
        return []


class _Page:
    def __init__(self, browser):
        self.browser = browser

    def goto(self, url, **kwargs):
        self.browser.visitas.append(url)
        if self.browser.erro_goto:
            raise RuntimeError("net::ERR_PROXY_CONNECTION_FAILED")

    def inner_text(self, seletor):
        return self.browser.ip_visto + "\n"


class _Context:
    def __init__(self, browser):
        self.browser = browser
        self.fechado = False

    def new_page(self):
        return _Page(self.browser)

    def close(self):
        self.fechado = True


class _Browser:
    def __init__(self, ip_visto="200.1.2.3", erro_goto=False):
        self.ip_visto = ip_visto
        self.erro_goto = erro_goto
        self.visitas: list[str] = []
        self.fechado = False

    def new_context(self, **kwargs):
        return _Context(self)

    def close(self):
        self.fechado = True


class _Chromium:
    def __init__(self, browser):
        self.browser = browser
        self.kwargs: dict = {}

    def launch(self, **kwargs):
        self.kwargs = kwargs
        return self.browser


class _Playwright:
    def __init__(self, browser):
        self.chromium = _Chromium(browser)


@pytest.fixture(autouse=True)
def _sem_proxy(monkeypatch):
    monkeypatch.delenv("MOTOR_PROXY_URL", raising=False)
    monkeypatch.delenv("MOTOR_PROXY_EXPECTED_IP", raising=False)


def test_sem_env_nao_ha_proxy():
    assert proxy_padrao() is None


def test_url_http_vira_proxy_do_playwright(monkeypatch):
    monkeypatch.setenv("MOTOR_PROXY_URL", "http://cliente:s%40nha@1.2.3.4:12323")
    assert proxy_padrao() == {
        "server": "http://1.2.3.4:12323",
        "username": "cliente",
        "password": "s@nha",
    }


def test_url_sem_credencial(monkeypatch):
    monkeypatch.setenv("MOTOR_PROXY_URL", "http://1.2.3.4:12323")
    assert proxy_padrao() == {"server": "http://1.2.3.4:12323"}


def test_socks5_com_senha_e_recusado(monkeypatch):
    # Chromium não autentica SOCKS5: falhar no boot é melhor que sair direto.
    monkeypatch.setenv("MOTOR_PROXY_URL", "socks5://cliente:senha@1.2.3.4:12324")
    with pytest.raises(ValueError) as exc:
        proxy_padrao()
    assert "senha" not in str(exc.value)


@pytest.mark.parametrize("url", ["1.2.3.4:12323", "ftp://1.2.3.4:21", "http://:12323"])
def test_url_invalida_e_recusada(monkeypatch, url):
    monkeypatch.setenv("MOTOR_PROXY_URL", url)
    with pytest.raises(ValueError):
        proxy_padrao()


def test_launch_sem_proxy_nao_muda_nada():
    pw = _Playwright(_Browser())
    browser = _Driver()._launch_browser(pw)
    assert browser is pw.chromium.browser
    assert "proxy" not in pw.chromium.kwargs
    assert pw.chromium.browser.visitas == []


def test_launch_com_proxy_passa_proxy_e_bloqueia_webrtc_direto(monkeypatch):
    monkeypatch.setenv("MOTOR_PROXY_URL", "http://cliente:senha@1.2.3.4:12323")
    pw = _Playwright(_Browser())
    _Driver()._launch_browser(pw)
    assert pw.chromium.kwargs["proxy"]["server"] == "http://1.2.3.4:12323"
    assert (
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"
        in pw.chromium.kwargs["args"]
    )


def test_ip_esperado_confere_antes_do_banco(monkeypatch):
    monkeypatch.setenv("MOTOR_PROXY_URL", "http://cliente:senha@1.2.3.4:12323")
    monkeypatch.setenv("MOTOR_PROXY_EXPECTED_IP", "200.1.2.3")
    browser = _Browser(ip_visto="200.1.2.3")
    assert _Driver()._launch_browser(_Playwright(browser)) is browser
    assert len(browser.visitas) == 1
    assert browser.fechado is False


def test_ip_divergente_para_sem_tocar_no_banco(monkeypatch):
    # Sem MOTOR_PROXY_URL o browser sai pelo IP do Fly: o esperado pega o esquecimento.
    monkeypatch.setenv("MOTOR_PROXY_EXPECTED_IP", "200.1.2.3")
    browser = _Browser(ip_visto="66.241.124.9")
    with pytest.raises(IntervencaoNecessaria) as exc:
        _Driver()._launch_browser(_Playwright(browser))
    assert exc.value.codigo == "saida_de_rede_divergente"
    assert "66.241.124.9" in str(exc.value)
    assert browser.fechado is True


def test_proxy_fora_do_ar_para_e_nao_vaza_senha(monkeypatch):
    monkeypatch.setenv("MOTOR_PROXY_URL", "http://cliente:senhasecreta@1.2.3.4:12323")
    monkeypatch.setenv("MOTOR_PROXY_EXPECTED_IP", "200.1.2.3")
    browser = _Browser(erro_goto=True)
    with pytest.raises(IntervencaoNecessaria) as exc:
        _Driver()._launch_browser(_Playwright(browser))
    assert exc.value.codigo == "proxy_indisponivel"
    assert "senhasecreta" not in str(exc.value)
    assert browser.fechado is True
