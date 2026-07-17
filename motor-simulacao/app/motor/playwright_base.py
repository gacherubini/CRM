"""Base reutilizável para drivers bancários via Playwright (Task 12).

Anti-detecção (WAF/Akamai):
- Preferir **headed** sob Xvfb no worker (headless_shell é o mais bloqueado).
- Remover flags de automação; spoof navigator/webdriver/chrome/plugins.
- UA + Client Hints + locale/timezone BR.
- Um browser Playwright **por banco** (isolamento de sessão).
"""
from __future__ import annotations

import os
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.motor.base import SolicitacaoSimulacao
from app.motor.drivers import (
    DriverContext,
    IntervencaoNecessaria,
    ResultadoDriver,
)


def capturar_print_evento(
    page,
    *,
    screenshot_dir: str | Path | None,
    simulacao_id: str | None,
    etapa: str,
) -> tuple[str | None, bytes | None]:
    """Captura print de diagnóstico e devolve (path, bytes).

    Usa JPEG (menor) para caber no blob Postgres e ser servido pela API
    em outra Machine (workers sob demanda não compartilham disco).
    """
    if page is None:
        return None, None
    base = Path(screenshot_dir or "data/screenshots")
    # MagicMock / tipos estranhos em testes: sempre string.
    sim_raw = "sem-id" if simulacao_id is None else str(simulacao_id)
    sim_id = re.sub(r"[^a-zA-Z0-9_-]", "", sim_raw) or "sem-id"
    etapa_segura = re.sub(r"[^a-zA-Z0-9_-]", "_", str(etapa or "etapa"))[:60]
    destino = base / sim_id / f"{etapa_segura}_{int(time.time())}.jpg"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        # JPEG qualidade moderada: full-page PNG de portal facilmente passa de 5–10 MB.
        dados = page.screenshot(type="jpeg", quality=55, full_page=True)
        if not dados:
            dados = page.screenshot(type="jpeg", quality=55, full_page=False)
        if not dados:
            return None, None
        destino.write_bytes(dados)
        return str(destino), bytes(dados)
    except Exception:
        return None, None

# Chrome 131 desktop Windows — alinhado ao build do Playwright.
_CHROME_MAJOR = "131"
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) Chrome/{_CHROME_MAJOR}.0.0.0 Safari/537.36"
)

_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-features=IsolateOrigins,site-per-process",
    "--window-size=1366,768",
    "--lang=pt-BR",
]

# Remove flags que o Chromium do Playwright adiciona e o Akamai checa.
_IGNORE_DEFAULT_ARGS = [
    "--enable-automation",
    "--enable-blink-features=IdleDetection",
]

# Script injetado antes de qualquer JS da página.
_STEALTH_INIT = r"""
(() => {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  } catch (e) {}
  try {
    // chrome.runtime costuma existir em Chrome real
    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || {};
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['pt-BR', 'pt', 'en-US', 'en'],
    });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'plugins', {
      get: () => [1, 2, 3, 4, 5],
    });
  } catch (e) {}
  try {
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
      parameters && parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
    );
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
  } catch (e) {}
  try {
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
  } catch (e) {}
})();
"""


def browser_headless_padrao() -> bool:
    """Headless só se MOTOR_BROWSER_HEADLESS=1. Padrão: headed (Xvfb no Docker)."""
    raw = (os.getenv("MOTOR_BROWSER_HEADLESS") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


class PlaywrightBankDriver(ABC):
    """Base para bancos sem API: browser + sessão + screenshots.

    Cada instância de driver = **um** browser (isolamento por banco).

    Contrato de login (decisão B+D):
    - com ``storage_state`` + portal já autenticado → **não** preencher senha
      (evento ``login_pulado`` / ``sessao_quente``) e seguir o fluxo;
    - com tela de login → login frio → ``login_confirmado``.
    """

    provedor: str = "desconhecido"
    real: bool = True
    # Conta no teto MOTOR_MAX_BROWSER_WORKERS / MOTOR_BROWSER_CONCURRENCY.
    usa_browser: bool = True
    # Stealth (UA falso + client hints + spoof navigator) foi feita p/ o Akamai do
    # Santander. Em portais com reCAPTCHA v3 (ex.: Fontecred) o UA descasado
    # (Chrome 131 vs Chromium real 149) faz o token não ser gerado e o submit trava.
    # Nesses casos use ``stealth = False`` (contexto vanilla, como o codegen).
    stealth: bool = True

    def __init__(
        self,
        *,
        headless: bool | None = None,
        storage_state_path: str | Path | None = None,
        screenshot_dir: str | Path | None = None,
        timeout_ms: int = 30_000,
    ):
        self.headless = browser_headless_padrao() if headless is None else headless
        self.storage_state_path = Path(storage_state_path) if storage_state_path else None
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        self.timeout_ms = timeout_ms

    def _storage_path_efetivo(self, ctx: DriverContext | None = None) -> Path | None:
        """Path para **leitura**: ctx canônico, ou legado ``{provedor}.json`` se existir."""
        if ctx is not None and getattr(ctx, "storage_state_path", None):
            p = Path(ctx.storage_state_path)
            if p.is_file():
                return p
            try:
                from app import config as _cfg

                legado = Path(_cfg.STORAGE_STATE_DIR) / p.name
                if legado.is_file():
                    return legado
            except Exception:
                pass
            return p
        return self.storage_state_path

    def _storage_path_gravacao(self, ctx: DriverContext | None = None) -> Path | None:
        """Path para **gravação** (sempre canônico por cliente quando ctx define path)."""
        if ctx is not None and getattr(ctx, "storage_state_path", None):
            return Path(ctx.storage_state_path)
        return self.storage_state_path

    def _salvar_storage_state(self, browser_ctx, ctx: DriverContext | None = None) -> None:
        destino = self._storage_path_gravacao(ctx)
        if destino is None:
            return
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            browser_ctx.storage_state(path=str(destino))
            if ctx is not None:
                ctx.registrar_evento(
                    "sessao_gravada",
                    f"Sessão do portal {self.provedor} persistida para reuso.",
                    "sucesso",
                )
        except Exception:
            pass

    def __call__(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        """Ponto de entrada do worker — subclasses implementam ``simular``."""
        return self.simular(sol, ctx)

    @abstractmethod
    def simular(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        """Executa o fluxo no portal e devolve um resultado por prazo."""

    def _launch_browser(self, playwright):
        """Abre Chromium evitando headless_shell e flags de automação."""
        # Headless shell é o que o Akamai mais bloqueia; headed (Xvfb) usa Chromium completo.
        # Se headless for obrigatório, desliga o headless_shell via env no compose.
        return playwright.chromium.launch(
            headless=self.headless,
            args=list(_LAUNCH_ARGS),
            ignore_default_args=list(_IGNORE_DEFAULT_ARGS),
            chromium_sandbox=False,
        )

    def _new_context(self, browser, ctx: DriverContext | None = None):
        """Contexto isolado com fingerprint de desktop BR (ou vanilla se stealth off)."""
        if not self.stealth:
            return self._new_context_vanilla(browser, ctx)
        kwargs: dict = {
            "user_agent": _DEFAULT_UA,
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
            "viewport": {"width": 1366, "height": 768},
            "screen": {"width": 1366, "height": 768},
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "java_script_enabled": True,
            "color_scheme": "light",
            "extra_http_headers": {
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "sec-ch-ua": (
                    f'"Google Chrome";v="{_CHROME_MAJOR}", '
                    f'"Chromium";v="{_CHROME_MAJOR}", '
                    '"Not_A Brand";v="24"'
                ),
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1",
            },
        }
        storage = self._storage_path_efetivo(ctx)
        if storage is not None and storage.is_file():
            kwargs["storage_state"] = str(storage)
        browser_ctx = browser.new_context(**kwargs)
        browser_ctx.add_init_script(_STEALTH_INIT)
        return browser_ctx

    def _new_context_vanilla(self, browser, ctx: DriverContext | None = None):
        """Contexto próximo do Chromium real (como o codegen): sem UA falso, sem
        client hints mentirosos, sem init script. Necessário p/ reCAPTCHA v3 gerar
        token (UA descasado trava o submit). Mantém só locale/timezone/viewport BR.
        """
        kwargs: dict = {
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
            "viewport": {"width": 1366, "height": 768},
        }
        storage = self._storage_path_efetivo(ctx)
        if storage is not None and storage.is_file():
            kwargs["storage_state"] = str(storage)
        return browser.new_context(**kwargs)

    def _assert_portal_acessivel(self, page) -> None:
        """Detecta WAF/Akamai Access Denied e falha com código legível."""
        try:
            titulo = (page.title() or "").strip()
            url = page.url or ""
            html = page.content() or ""
        except Exception:
            return
        snip = f"{titulo}\n{url}\n{html[:4000]}"
        if (
            "Access Denied" in snip
            or "errors.edgesuite" in snip
            or "You don't have permission to access" in snip
            or ("Reference #" in snip and "Permission" in snip)
        ):
            raise IntervencaoNecessaria(
                "portal_bloqueado",
                "Portal do banco bloqueou o browser (WAF/Akamai). "
                "Worker deve rodar headed+Xvfb (MOTOR_BROWSER_HEADLESS=0). "
                "Se persistir, IP/datacenter pode estar na lista negra do banco.",
            )

    def _screenshot_falha(self, page, nome: str = "falha") -> Optional[Path]:
        """Grava screenshot se houver diretório configurado; nunca levanta."""
        if page is None or not self.screenshot_dir:
            return None
        try:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            destino = self.screenshot_dir / f"{self.provedor}_{nome}.png"
            page.screenshot(path=str(destino), full_page=True)
            return destino
        except Exception:
            return None

    def _falha_campo(self, campo: str) -> IntervencaoNecessaria:
        return IntervencaoNecessaria(
            codigo="campo_nao_encontrado",
            mensagem=f"campo {campo} não encontrado no portal {self.provedor}",
        )
