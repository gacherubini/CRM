"""Driver real Banco PAN via **portal do lojista** (veiculos.bancopan.com.br).

Caminho Playwright para quando a loja opera so com usuario/senha de lojista
(sem api_key/secret de developer). Convive com ``PanDriver(ApiBankDriver)`` em
``pan.py``: o dispatcher em ``drivers.py`` escolhe API quando a config OpenAPI
esta completa, senao cai neste portal.

Fluxo mapeado pelo codegen do lojista (secao "buscopan", 2026-07):
  0. Login: textbox Usuario + (banner "Got it!") + Senha -> Entrar
  1. Cliente: CPF + celular
  2. Veiculo: botao "Busca placa" -> combobox "Digite a placa..."
  3. Valor de venda -> Simular
  4. (entrada opcional) -> le a grade de parcelas

Entrada e OPCIONAL: so preenche "Entrada:" quando o usuario mandar valor > 0.

Modos:
- **fixture/html** (testes): ``html_simulacao=`` ou env ``MOTOR_PAN_PORTAL_FIXTURE_HTML``
- **live** (Playwright): so com credencial + browser instalado

Nunca logar usuario/senha/CPF/celular. Provedor canonico = "pan" (mesmo da API).
"""
from __future__ import annotations

import os
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app import config
from app.motor.base import SolicitacaoSimulacao
from app.motor.drivers import (
    DriverContext,
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
    ResultadoDriver,
)
from app.motor.playwright_base import PlaywrightBankDriver

PROVEDOR = "pan"

LOGIN_URL_DEFAULT = "https://veiculos.bancopan.com.br/login"

# Cards de parcela: "24x 1.212,76" / "24x de R$ 1.212,76" (R$ pode faltar).
_RE_PARCELA = re.compile(
    r"(\d{1,3})\s*x\b[^0-9]{0,20}?(?:R\$\s*)?(\d[\d.]*,\d{2})",
    re.IGNORECASE,
)
# Entrada minima exibida pos-simulacao ("Entrada: R$ 3.956,40").
_RE_ENTRADA = re.compile(
    r"(?:Entrada\s+m[ií]nima|Entrada)\s*:?\s*(?:R\$\s*)?(\d[\d.]*,\d{2})",
    re.IGNORECASE,
)


def _texto_plano(texto: str) -> str:
    """Normaliza HTML/texto para parsing (tags e quebras viram espaco)."""
    s = texto or ""
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", s)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("\xa0", " ").replace("&nbsp;", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def parse_moeda_br(texto: str) -> Decimal:
    """Converte '1.234,56' ou 'R$ 1.234,56' em Decimal."""
    s = (texto or "").strip()
    s = re.sub(r"[R$\s]", "", s, flags=re.IGNORECASE)
    s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"moeda invalida: {texto!r}") from exc


def parse_parcelas_pan_portal(texto: str) -> list[tuple[int, Decimal]]:
    """Extrai (prazo_meses, parcela) da grade de resultado do portal.

    Mantem a primeira ocorrencia de cada prazo (HTML cru pode duplicar cards).
    """
    plano = _texto_plano(texto)
    vistos: dict[int, Decimal] = {}
    for m in _RE_PARCELA.finditer(plano):
        prazo = int(m.group(1))
        parcela = parse_moeda_br(m.group(2))
        vistos.setdefault(prazo, parcela)
    return sorted(vistos.items(), key=lambda x: x[0])


def parse_entrada(texto: str) -> Decimal | None:
    """Entrada minima devolvida pelo portal, se exibida."""
    plano = _texto_plano(texto)
    m = _RE_ENTRADA.search(plano)
    return parse_moeda_br(m.group(1)) if m else None


def _formatar_moeda_input(valor: float) -> str:
    """Formato BR com milhar para inputs: 21900.00 -> 21.900,00."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _html_fixture_path() -> Path | None:
    raw = os.getenv("MOTOR_PAN_PORTAL_FIXTURE_HTML", "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_file() else None
    return None


class PanPortalDriver(PlaywrightBankDriver):
    """Robo do portal do lojista Banco PAN (veiculos.bancopan.com.br)."""

    provedor = PROVEDOR
    real = True
    # Portal desconhecido; comecamos vanilla (como o codegen). Se aparecer
    # Akamai/Access Denied, reavaliar stealth=True (licao Santander).
    stealth = False

    def __init__(
        self,
        *,
        headless: bool | None = None,
        storage_state_path: str | Path | None = None,
        screenshot_dir: str | Path | None = None,
        timeout_ms: int | None = None,
        login_url: str | None = None,
        html_simulacao: str | None = None,
    ):
        super().__init__(
            headless=headless,
            storage_state_path=storage_state_path,
            screenshot_dir=screenshot_dir or getattr(config, "SCREENSHOT_DIR", None),
            timeout_ms=timeout_ms
            if timeout_ms is not None
            else int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        )
        self.login_url = login_url or getattr(
            config, "PAN_PORTAL_LOGIN_URL", LOGIN_URL_DEFAULT
        )
        self.html_simulacao = html_simulacao

    # --- entrada ------------------------------------------------------------

    def simular(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        self._validar_solicitacao(sol)

        html = self.html_simulacao
        if html is None:
            fix = _html_fixture_path()
            if fix is not None:
                html = fix.read_text(encoding="utf-8")
        if html is not None:
            return self._resultados_de_html(html, sol)

        return self._simular_playwright(sol, ctx)

    def _validar_solicitacao(self, sol: SolicitacaoSimulacao) -> None:
        if not sol.pessoa.cpf:
            raise RejeicaoNegocio("dados_cliente", "CPF do cliente e obrigatorio")
        if not sol.pessoa.celular:
            raise RejeicaoNegocio(
                "celular_obrigatorio", "Celular e obrigatorio no portal Pan"
            )
        if not sol.veiculo.placa:
            raise RejeicaoNegocio(
                "placa_obrigatoria", "Placa e obrigatoria no portal Pan"
            )
        if sol.veiculo.valor is None:
            raise RejeicaoNegocio("valor_obrigatorio", "Valor de venda e obrigatorio")

    def _resultados_de_html(
        self, html: str, sol: SolicitacaoSimulacao
    ) -> list[ResultadoDriver]:
        pares = parse_parcelas_pan_portal(html)
        if not pares:
            raise RejeicaoNegocio("pan_sem_oferta")
        entrada_minima = parse_entrada(html)
        entrada_informada = Decimal(str(sol.condicoes.entrada or 0))
        entrada = entrada_minima if entrada_minima is not None else (
            entrada_informada if entrada_informada > 0 else None
        )
        financiado: Decimal | None = None
        if sol.veiculo.valor is not None:
            desconto = entrada if entrada is not None else Decimal("0")
            financiado = Decimal(str(sol.veiculo.valor)) - desconto
            if financiado < 0:
                financiado = Decimal("0")

        pedidos = set(sol.condicoes.prazos_meses or [])
        out: list[ResultadoDriver] = []
        for prazo, parcela in pares:
            if pedidos and prazo not in pedidos:
                continue
            out.append(
                ResultadoDriver(
                    provedor=self.provedor,
                    status="concluida",
                    valor_parcela=parcela,
                    taxa_am=None,
                    prazo_meses=prazo,
                    valor_financiado=financiado,
                    entrada=entrada,
                )
            )
        if not out:
            out = [
                ResultadoDriver(
                    provedor=self.provedor,
                    status="concluida",
                    valor_parcela=parcela,
                    prazo_meses=prazo,
                    valor_financiado=financiado,
                    entrada=entrada,
                )
                for prazo, parcela in pares
            ]
        return out

    # --- Playwright live ----------------------------------------------------

    def _simular_playwright(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None
    ) -> list[ResultadoDriver]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise IntervencaoNecessaria(
                "playwright_ausente",
                "instale playwright e chromium no worker do Motor",
            ) from exc

        usuario, senha = self._credencial(ctx)
        self._evento(ctx, "browser_iniciando", "Preparando o navegador do Pan.")

        with sync_playwright() as p:
            browser = self._launch_browser(p)
            browser_ctx = self._new_context(browser)
            page = browser_ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                self._evento(ctx, "browser_pronto", "Navegador iniciado; abrindo o portal.")
                self._passo_login(page, usuario, senha)
                self._evento(
                    ctx, "login_confirmado", "Login confirmado pelo portal.", page, True
                )
                self._passo_cliente(page, sol)
                self._passo_veiculo(page, sol)
                self._passo_valor(page, sol)
                self._evento(
                    ctx,
                    "dados_preenchidos",
                    "Dados do cliente, veiculo e valor preenchidos.",
                    page,
                    True,
                )
                self._passo_simular(page, sol)
                self._evento(
                    ctx, "simulacao_enviada", "Consulta enviada; aguardando ofertas."
                )
                self._passo_aguardar_ofertas(page)
                self._evento(
                    ctx, "ofertas_recebidas", "Ofertas carregadas na tela.", page, True
                )
                try:
                    texto = page.inner_text("body") or ""
                except Exception:
                    texto = ""
                html = page.content() or ""
                resultados = self._resultados_de_html(texto + "\n" + html, sol)
                self._salvar_storage(browser_ctx)
                self._evento(
                    ctx,
                    "parcelas_lidas",
                    "Parcelas interpretadas e prontas para salvar.",
                    nivel="sucesso",
                )
                return resultados
            except (RejeicaoNegocio, IntervencaoNecessaria, ErroTransitorio):
                self._evento(
                    ctx,
                    "falha_portal",
                    "O fluxo bancario foi interrompido; consulte o codigo do resultado.",
                    page,
                    True,
                    "erro",
                )
                self._screenshot_falha(page, "erro")
                raise
            except Exception as exc:
                tipo_erro = type(exc).__name__
                self._evento(
                    ctx,
                    "falha_inesperada",
                    f"O portal apresentou uma falha inesperada ({tipo_erro}).",
                    page,
                    True,
                    "erro",
                )
                self._screenshot_falha(page, "inesperado")
                detalhe = str(exc).replace("\n", " ")[:180]
                raise ErroTransitorio(
                    "portal_falhou",
                    f"falha no portal Pan: {type(exc).__name__}: {detalhe}",
                ) from exc
            finally:
                browser_ctx.close()
                browser.close()

    # --- observabilidade ----------------------------------------------------

    def _evento(
        self,
        ctx: DriverContext | None,
        etapa: str,
        mensagem: str,
        page=None,
        capturar_print: bool = False,
        nivel: str = "info",
    ) -> None:
        if ctx is None:
            return
        screenshot_path = None
        if capturar_print and page is not None and config.EVENT_SCREENSHOTS:
            screenshot_path = self._capturar_print_evento(page, ctx, etapa)
        ctx.registrar_evento(etapa, mensagem, nivel, screenshot_path)

    def _capturar_print_evento(
        self, page, ctx: DriverContext, etapa: str
    ) -> str | None:
        base = Path(ctx.screenshot_dir or self.screenshot_dir or "data/screenshots")
        sim_id = re.sub(r"[^a-zA-Z0-9_-]", "", ctx.simulacao_id or "sem-id")
        etapa_segura = re.sub(r"[^a-zA-Z0-9_-]", "_", etapa)[:60]
        destino = base / sim_id / f"{etapa_segura}_{int(time.time())}.png"
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(destino), full_page=True)
            return str(destino)
        except Exception:
            return None

    def _credencial(self, ctx: DriverContext | None) -> tuple[str, str]:
        if ctx is None or ctx.db is None or not ctx.cliente_id:
            raise IntervencaoNecessaria(
                "sem_contexto", "driver real exige cliente_id e sessao DB"
            )
        from app.credenciais import obter_segredo_para_uso

        segredo = obter_segredo_para_uso(ctx.db, ctx.cliente_id, self.provedor)
        if not segredo:
            raise IntervencaoNecessaria(
                "sem_credencial",
                "cadastre usuario/senha do lojista em Acessos bancos (Portal)",
            )
        return segredo

    # --- passos do portal ---------------------------------------------------

    def _passo_login(self, page, usuario: str, senha: str) -> None:
        url = self.login_url
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        try:
            page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
        except Exception:
            if self._portal_autenticado(page):
                self._aguardar_dom_pronto(page)
                page.wait_for_timeout(600)
                return
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        page.wait_for_timeout(700)
        self._assert_portal_acessivel(page)
        if self._portal_autenticado(page):
            self._aguardar_dom_pronto(page)
            page.wait_for_timeout(600)
            return

        self._fechar_got_it(page)
        usuario_box = page.get_by_role(
            "textbox", name=re.compile(r"Usu[aá]rio", re.I)
        ).first
        usuario_box.wait_for(state="visible", timeout=self.timeout_ms)
        usuario_box.click()
        usuario_box.fill("")
        usuario_box.type(usuario, delay=35)
        self._fechar_got_it(page)
        senha_box = page.get_by_role("textbox", name=re.compile(r"Senha", re.I)).first
        senha_box.click()
        senha_box.fill("")
        senha_box.type(senha, delay=40)
        page.wait_for_timeout(300)
        page.get_by_role("button", name=re.compile(r"^Entrar$", re.I)).first.click()
        self._aguardar_pos_login(page)

    def _fechar_got_it(self, page) -> None:
        """Banner de cookie/onboarding com botao 'Got it!' (best-effort)."""
        try:
            page.get_by_role(
                "button", name=re.compile(r"Got it", re.I)
            ).first.click(timeout=3_000)
            page.wait_for_timeout(200)
        except Exception:
            pass

    def _portal_autenticado(self, page) -> bool:
        try:
            url = str(page.url or "")
            if url and not re.search(r"/login\b", url, re.I):
                return True
        except Exception:
            pass
        return False

    def _aguardar_pos_login(self, page) -> None:
        timeout = max(self.timeout_ms, 45_000)
        try:
            page.wait_for_function(
                "() => !/\\/login\\b/i.test(location.pathname)",
                timeout=timeout,
            )
            self._aguardar_dom_pronto(page)
            page.wait_for_timeout(600)
            return
        except Exception:
            pass
        self._assert_portal_acessivel(page)
        body = ""
        try:
            body = (page.inner_text("body") or "")[:1200]
        except Exception:
            body = ""
        if re.search(
            r"inv[aá]lid|incorret|n[aã]o autorizado|usu[aá]rio ou senha|"
            r"credencia|acesso negado|tente novamente",
            body,
            re.I,
        ):
            raise IntervencaoNecessaria(
                "credencial_invalida",
                "Portal rejeitou usuario/senha do lojista. Atualize em Acessos bancos.",
            )
        raise ErroTransitorio(
            "login_timeout", "Login nao concluiu a tempo (ainda na tela de login)."
        )

    def _aguardar_dom_pronto(self, page, timeout_ms: int | None = None) -> None:
        timeout = min(timeout_ms or self.timeout_ms, 20_000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass
        try:
            page.wait_for_function(
                "() => document.readyState === 'interactive' "
                "|| document.readyState === 'complete'",
                timeout=timeout,
            )
        except Exception:
            pass

    def _passo_cliente(self, page, sol: SolicitacaoSimulacao) -> None:
        cpf = re.sub(r"\D", "", sol.pessoa.cpf or "")
        # CPF do cliente: no codegen era um combobox com mascara. Preferimos
        # role=combobox por rotulo CPF; fallback no primeiro combobox/textbox.
        cpf_box = None
        for tentativa in (
            lambda: page.get_by_role("combobox", name=re.compile(r"CPF", re.I)).first,
            lambda: page.get_by_role("textbox", name=re.compile(r"CPF", re.I)).first,
            lambda: page.get_by_role("combobox").first,
        ):
            try:
                box = tentativa()
                box.wait_for(state="visible", timeout=min(self.timeout_ms, 8_000))
                cpf_box = box
                break
            except Exception:
                continue
        if cpf_box is None:
            raise self._falha_campo("CPF do cliente")
        cpf_box.click()
        cpf_box.fill("")
        cpf_box.type(cpf, delay=30)
        page.wait_for_timeout(300)
        # Celular: no codegen o rotulo era "Icone do input" (fragil). Tentamos
        # rotulos melhores; fallback proximo textbox de telefone.
        cel = sol.pessoa.celular or ""
        for tentativa in (
            lambda: page.get_by_role(
                "textbox", name=re.compile(r"Celular|Telefone|Ícone", re.I)
            ).first,
        ):
            try:
                box = tentativa()
                box.wait_for(state="visible", timeout=min(self.timeout_ms, 8_000))
                box.click()
                box.fill("")
                box.type(cel, delay=30)
                break
            except Exception:
                continue
        page.wait_for_timeout(300)

    def _passo_veiculo(self, page, sol: SolicitacaoSimulacao) -> None:
        placa = (sol.veiculo.placa or "").replace("-", "").upper()
        # Caminho principal do codegen: botao "Busca placa" -> campo de placa.
        try:
            page.get_by_role(
                "button", name=re.compile(r"Busca\s+placa", re.I)
            ).first.click(timeout=min(self.timeout_ms, 8_000))
            page.wait_for_timeout(400)
        except Exception:
            pass
        placa_box = None
        for tentativa in (
            lambda: page.get_by_role(
                "combobox", name=re.compile(r"placa", re.I)
            ).first,
            lambda: page.get_by_role(
                "textbox", name=re.compile(r"placa", re.I)
            ).first,
        ):
            try:
                box = tentativa()
                box.wait_for(state="visible", timeout=min(self.timeout_ms, 8_000))
                placa_box = box
                break
            except Exception:
                continue
        if placa_box is None:
            raise self._falha_campo("Placa")
        placa_box.click()
        placa_box.fill("")
        placa_box.type(placa, delay=40)
        page.keyboard.press("Tab")
        page.wait_for_timeout(1_000)

    def _passo_valor(self, page, sol: SolicitacaoSimulacao) -> None:
        if sol.veiculo.valor is None:
            return
        try:
            valor_box = page.get_by_role(
                "textbox", name=re.compile(r"Valor de venda", re.I)
            ).first
            valor_box.wait_for(state="visible", timeout=min(self.timeout_ms, 10_000))
            valor_box.click()
            valor_box.fill("")
            valor_box.type(_formatar_moeda_input(float(sol.veiculo.valor)), delay=25)
            page.wait_for_timeout(300)
        except Exception:
            pass

    def _passo_simular(self, page, sol: SolicitacaoSimulacao) -> None:
        simular = page.get_by_role("button", name=re.compile(r"^Simular$", re.I)).first
        simular.wait_for(state="visible", timeout=self.timeout_ms)
        simular.click()
        page.wait_for_timeout(600)
        # Entrada e OPCIONAL: so preenche apos simular se o usuario mandou > 0.
        entrada = sol.condicoes.entrada or 0
        if entrada and float(entrada) > 0:
            try:
                entrada_box = page.get_by_role(
                    "textbox", name=re.compile(r"Entrada", re.I)
                ).first
                entrada_box.wait_for(state="visible", timeout=min(self.timeout_ms, 8_000))
                entrada_box.click()
                entrada_box.fill("")
                entrada_box.type(_formatar_moeda_input(float(entrada)), delay=25)
                page.keyboard.press("Tab")
                page.wait_for_timeout(500)
            except Exception:
                pass

    def _passo_aguardar_ofertas(self, page) -> None:
        timeout = max(self.timeout_ms, 60_000)
        prazo_fim = time.monotonic() + (timeout / 1000.0)
        cards = re.compile(r"\d+\s*x\b", re.I)
        estavel = 0
        while time.monotonic() < prazo_fim:
            if page.get_by_text(
                re.compile(r"Ocorreu um erro|indispon[ií]vel|falha", re.I)
            ).count() > 0:
                raise ErroTransitorio(
                    "portal_simulacao_erro", "erro exibido na tela de ofertas"
                )
            if page.get_by_text(cards).count() > 0:
                estavel += 1
                if estavel >= 2:
                    page.wait_for_timeout(600)
                    return
            else:
                estavel = 0
            page.wait_for_timeout(500)
        self._assert_portal_acessivel(page)
        raise ErroTransitorio(
            "portal_falhou", "grade de parcelas nao carregou a tempo"
        )

    def _salvar_storage(self, browser_ctx) -> None:
        if not self.storage_state_path:
            return
        try:
            self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            browser_ctx.storage_state(path=str(self.storage_state_path))
        except Exception:
            pass


def fabrica_pan_portal() -> PanPortalDriver:
    from app.motor.playwright_base import browser_headless_padrao

    return PanPortalDriver(
        headless=browser_headless_padrao(),
        screenshot_dir=config.SCREENSHOT_DIR,
        storage_state_path=Path(config.STORAGE_STATE_DIR) / "pan_portal.json",
        timeout_ms=int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        login_url=getattr(config, "PAN_PORTAL_LOGIN_URL", LOGIN_URL_DEFAULT),
    )
