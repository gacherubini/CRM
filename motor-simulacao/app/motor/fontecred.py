"""Driver real Fontecred (financeira especialista em motos).

Fluxo mapeado pelo portal do lojista (app.fontecred.com.br, 2026-07) via codegen:
  0. Login: E-MAIL do lojista + senha (nao CPF, como no Santander)
  1. Fecha pop-up "COMUNICADOS" -> Propostas -> Criar Proposta
  2. Dados Pessoais: CPF, nascimento (ISO), celular
  3. Veiculo: 0KM=Nao, digita PLACA -> portal resolve o veiculo -> clica a linha
  4. Financiamento: valor de venda, entrada BAIXA (para extrair a minima), prazo,
     marca o checkbox de autorizacao SCR
  5. Simular -> trata modal PEP ("Voce e um PEP?") e upsell de seguro
     ("Continuar sem protecao")
  6. Resultado (multi-prazo): botoes "24x 1.212,76" etc. + "Sua entrada: R$ ..."

Entrada: diferente do Santander, aqui a entrada e um INPUT. O portal, porem,
DEVOLVE a entrada minima exigida ("Sua entrada") quando enviamos um valor baixo;
e esse valor minimo que reportamos (campo `entrada` de cada resultado).

Modos:
- **fixture/html** (testes): ``html_simulacao=`` ou env ``MOTOR_FONTECRED_FIXTURE_HTML``
- **live** (Playwright): so com credencial + browser instalado

Nunca logar e-mail/senha/CPF. Login do lojista = campo ``usuario`` da credencial
(o E-MAIL, nao o CPF).
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

PROVEDOR = "fontecred"

LOGIN_URL_DEFAULT = "https://app.fontecred.com.br/login#step-1"
NOVA_PROPOSTA_URL = "https://app.fontecred.com.br/clientes/criarComProposta"

# Cards de resultado: "24x 1.212,76" (o "R$" costuma vir em outra tag ou ausente).
# Non-greedy com folga curta para casar "24x" e "1.212,76" em nos separados.
_RE_PARCELA = re.compile(
    r"(\d{1,3})\s*x\b[^0-9]{0,20}?(?:R\$\s*)?(\d[\d.]*,\d{2})",
    re.IGNORECASE,
)
# Entrada minima exibida no painel ("Sua entrada: R$ 3.956,40" / "Entrada minima").
_RE_ENTRADA = re.compile(
    r"(?:Sua\s+entrada|Entrada\s+m[ií]nima)\s*:?\s*(?:R\$\s*)?(\d[\d.]*,\d{2})",
    re.IGNORECASE,
)
# Valor financiado echo no form ("Valor de financiamento").
_RE_FINANCIADO = re.compile(
    r"Valor\s+de\s+financiamento\s*:?\s*(?:R\$\s*)?(\d[\d.]*,\d{2})",
    re.IGNORECASE,
)


def _texto_plano(texto: str) -> str:
    """Normaliza HTML/texto para parsing (tags e quebras viram espaço)."""
    s = texto or ""
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", s)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("\xa0", " ").replace("&nbsp;", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def parse_moeda_br(texto: str) -> Decimal:
    """Converte '1.097,45' ou 'R$ 1.097,45' em Decimal."""
    s = (texto or "").strip()
    s = re.sub(r"[R$\s]", "", s, flags=re.IGNORECASE)
    s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"moeda inválida: {texto!r}") from exc


def parse_parcelas_texto(texto: str) -> list[tuple[int, Decimal]]:
    """Extrai (prazo_meses, parcela) dos botoes de resultado.

    O painel de resultado do Fontecred lista todos os prazos de uma vez
    (ex.: 24x / 36x / 48x). Mantem a primeira ocorrencia de cada prazo
    (aria-label + spans podem duplicar o mesmo card no HTML cru).
    """
    plano = _texto_plano(texto)
    vistos: dict[int, Decimal] = {}
    for m in _RE_PARCELA.finditer(plano):
        prazo = int(m.group(1))
        parcela = parse_moeda_br(m.group(2))
        vistos.setdefault(prazo, parcela)
    return sorted(vistos.items(), key=lambda x: x[0])


def parse_entrada(texto: str) -> Decimal | None:
    """Entrada minima devolvida pelo portal (rotulo 'Sua entrada')."""
    plano = _texto_plano(texto)
    m = _RE_ENTRADA.search(plano)
    if m:
        return parse_moeda_br(m.group(1))
    return None


def parse_valor_financiado(texto: str) -> Decimal | None:
    """Valor financiado echo no form ('Valor de financiamento')."""
    plano = _texto_plano(texto)
    m = _RE_FINANCIADO.search(plano)
    if m:
        return parse_moeda_br(m.group(1))
    return None


def _formatar_nascimento_iso(nasc: str) -> str:
    """Portal usa input type=date; fill aceita ISO YYYY-MM-DD."""
    s = (nasc or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return s


def _formatar_moeda_input(valor: float) -> str:
    """Formato BR com milhar para inputs: 21900.00 -> 21.900,00."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _html_fixture_path() -> Path | None:
    raw = os.getenv("MOTOR_FONTECRED_FIXTURE_HTML", "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_file() else None
    return None


class FontecredDriver(PlaywrightBankDriver):
    """Robô do portal do lojista Fontecred (cotação multi-prazo de motos)."""

    provedor = PROVEDOR
    real = True
    # Portal tem reCAPTCHA v3: UA falso/descasado trava o submit do login.
    # Contexto vanilla (como o codegen) deixa o token ser gerado.
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
            screenshot_dir=screenshot_dir
            or getattr(config, "SCREENSHOT_DIR", None),
            timeout_ms=timeout_ms
            if timeout_ms is not None
            else int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        )
        self.login_url = login_url or getattr(
            config, "FONTECRED_LOGIN_URL", LOGIN_URL_DEFAULT
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
        if not sol.pessoa.cpf or not sol.pessoa.nascimento:
            raise RejeicaoNegocio("dados_cliente", "CPF e nascimento são obrigatórios")
        if not sol.pessoa.celular:
            raise RejeicaoNegocio("celular_obrigatorio", "Celular é obrigatório no Fontecred")
        if not sol.veiculo.placa:
            raise RejeicaoNegocio("placa_obrigatoria", "Placa é obrigatória no Fontecred")
        if sol.veiculo.valor is None:
            raise RejeicaoNegocio("valor_obrigatorio", "Valor de venda é obrigatório")

    def _resultados_de_html(
        self, html: str, sol: SolicitacaoSimulacao
    ) -> list[ResultadoDriver]:
        pares = parse_parcelas_texto(html)
        if not pares:
            raise IntervencaoNecessaria(
                "parcelas_nao_encontradas",
                "nenhum card de parcela encontrado na tela de simulação",
            )
        # Entrada minima que o portal exige (mesma para todos os prazos).
        entrada_minima = parse_entrada(html)
        financiado = parse_valor_financiado(html)
        if financiado is None and sol.veiculo.valor is not None:
            desconto = entrada_minima if entrada_minima is not None else Decimal(
                str(sol.condicoes.entrada or 0)
            )
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
                    taxa_am=None,  # painel não exibe taxa a.m. por card
                    prazo_meses=prazo,
                    valor_financiado=financiado,
                    entrada=entrada_minima,
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
                    entrada=entrada_minima,
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

        email_lojista, senha = self._credencial(ctx)
        self._evento(ctx, "browser_iniciando", "Preparando o navegador do Fontecred.")

        with sync_playwright() as p:
            browser = self._launch_browser(p)
            browser_ctx = self._new_context(browser)
            page = browser_ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                self._evento(ctx, "browser_pronto", "Navegador iniciado; abrindo o portal.")
                self._passo_login(page, email_lojista, senha)
                self._evento(
                    ctx, "login_confirmado", "Login confirmado pelo portal.", page, True
                )
                self._fechar_comunicados(page)
                self._evento(
                    ctx,
                    "comunicados_fechados",
                    "Comunicados do portal verificados e fechados.",
                )
                self._passo_nova_proposta(page)
                self._evento(
                    ctx,
                    "proposta_aberta",
                    "Tela de criação da proposta carregada.",
                    page,
                    True,
                )
                self._passo_dados_pessoais(page, sol)
                self._passo_veiculo(page, sol)
                self._passo_financiamento(page, sol)
                self._evento(
                    ctx,
                    "dados_preenchidos",
                    "Dados do cliente, veículo e financiamento preenchidos.",
                    page,
                    True,
                )
                self._passo_simular_e_modais(page)
                self._evento(
                    ctx,
                    "simulacao_enviada",
                    "Consulta enviada; aguardando ofertas do banco.",
                )
                self._passo_aguardar_resultado(page)
                self._evento(
                    ctx,
                    "ofertas_recebidas",
                    "Ofertas carregadas na tela do banco.",
                    page,
                    True,
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
                    "O fluxo bancário foi interrompido; consulte o código do resultado.",
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
                    f"falha no portal Fontecred: {type(exc).__name__}: {detalhe}",
                ) from exc
            finally:
                browser_ctx.close()
                browser.close()

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
        """Print por job/etapa; nome não contém CPF, placa ou outro dado pessoal."""
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
                "sem_contexto", "driver real exige cliente_id e sessão DB"
            )
        from app.credenciais import obter_segredo_para_uso

        segredo = obter_segredo_para_uso(ctx.db, ctx.cliente_id, self.provedor)
        if not segredo:
            raise IntervencaoNecessaria(
                "sem_credencial",
                "cadastre e-mail/senha do lojista em Acessos bancos (Portal)",
            )
        return segredo

    def _passo_login(self, page, email_lojista: str, senha: str) -> None:
        url = self.login_url
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        try:
            page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
        except Exception:
            # Storage state válido pode redirecionar /login direto ao Dashboard.
            # Nesse cenário o portal mantém conexões abertas, networkidle expira,
            # mas a sessão já está pronta e não devemos procurar e-mail/senha.
            if self._portal_autenticado(page):
                self._aguardar_dom_pronto(page)
                page.wait_for_timeout(800)
                return
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        page.wait_for_timeout(600)
        self._assert_portal_acessivel(page)
        if self._portal_autenticado(page):
            self._aguardar_dom_pronto(page)
            page.wait_for_timeout(800)
            return

        email_box = page.get_by_role("textbox", name=re.compile(r"e-?mail", re.I))
        senha_box = page.get_by_role("textbox", name=re.compile(r"senha", re.I))
        email_box.first.click()
        email_box.first.fill("")
        email_box.first.type(email_lojista, delay=30)
        page.wait_for_timeout(150)
        senha_box.first.click()
        senha_box.first.fill("")
        senha_box.first.type(senha, delay=35)
        page.wait_for_timeout(200)
        # reCAPTCHA v3: o submit só POSTa depois que grecaptcha.execute() devolve um
        # token. Espera o grecaptcha carregar antes de clicar, senão o clique "não faz
        # nada" (handler segura o submit aguardando o token).
        try:
            page.wait_for_function(
                "() => window.grecaptcha && typeof window.grecaptcha.execute === 'function'",
                timeout=15_000,
            )
        except Exception:
            pass
        page.wait_for_timeout(400)
        page.get_by_role("button", name=re.compile(r"^Login$", re.I)).first.click()
        self._aguardar_pos_login(page)

    def _portal_autenticado(self, page) -> bool:
        """Reconhece Dashboard já aberto por uma sessão persistida válida."""
        try:
            url = str(page.url or "")
            if url and not re.search(r"/login\b", url, re.I):
                return True
        except Exception:
            pass
        for texto in (r"^\s*COMUNICADOS\s*$", r"^\s*Dashboard\s*$"):
            try:
                if page.get_by_text(re.compile(texto, re.I)).first.is_visible():
                    return True
            except Exception:
                continue
        return False

    def _aguardar_pos_login(self, page) -> None:
        timeout = max(self.timeout_ms, 45_000)
        # O portal pode renderizar o Dashboard antes de atualizar /login. Esperamos
        # um sinal real da área autenticada, em vez de depender apenas da URL.
        try:
            page.wait_for_function(
                """() => {
                    const texto = document.body?.innerText || '';
                    return !/\\/login\\b/i.test(location.pathname)
                        || /COMUNICADOS/i.test(texto)
                        || /Dashboard/i.test(texto);
                }""",
                timeout=timeout,
            )
            self._aguardar_dom_pronto(page)
            # Dá tempo para o modal concluir a animação de entrada.
            page.wait_for_timeout(800)
            return
        except Exception:
            pass
        # reCAPTCHA que desafiou (iframe visível) -> intervenção manual.
        if page.locator("iframe[src*='recaptcha']").count() > 0:
            body = ""
            try:
                body = (page.inner_text("body") or "")[:600]
            except Exception:
                body = ""
            if re.search(r"não sou um robô|verificação|selecione", body, re.I):
                raise IntervencaoNecessaria(
                    "captcha_login",
                    "Portal Fontecred exigiu reCAPTCHA no login (intervenção manual).",
                )
        body = ""
        try:
            body = (page.inner_text("body") or "")[:1200]
        except Exception:
            body = ""
        if re.search(
            r"inv[aá]lid|incorret|senha|credencia|não autorizado|tente novamente",
            body,
            re.I,
        ):
            raise IntervencaoNecessaria(
                "login_rejeitado",
                "Portal rejeitou e-mail/senha do lojista. Atualize em Acessos bancos.",
            )
        raise ErroTransitorio(
            "login_timeout", "Login não concluiu a tempo (ainda na tela de login)."
        )

    def _aguardar_dom_pronto(self, page, timeout_ms: int | None = None) -> None:
        """Aguarda o DOM utilizável sem exigir networkidle do portal."""
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

    def _fechar_comunicados(self, page) -> None:
        """Fecha o pop-up COMUNICADOS e confirma que não bloqueia mais a tela."""
        titulo = page.get_by_text(
            re.compile(r"^\s*COMUNICADOS\s*$", re.I)
        ).first
        try:
            titulo.wait_for(
                state="visible", timeout=min(self.timeout_ms, 5_000)
            )
        except Exception:
            if not self._comunicados_visivel(page):
                return

        for tentativa in (
            lambda: page.get_by_role("button", name=re.compile(r"Fechar", re.I)).first.click(
                timeout=3_000
            ),
            lambda: page.locator(
                ".modal.show .btn-close, .modal.show [data-bs-dismiss='modal'], "
                ".modal .btn-close, .modal [data-bs-dismiss='modal'], "
                ".modal button.close, .modal [data-dismiss='modal']"
            ).first.click(timeout=3_000, force=True),
            lambda: page.keyboard.press("Escape"),
        ):
            try:
                tentativa()
                try:
                    titulo.wait_for(state="hidden", timeout=5_000)
                except Exception:
                    pass
                if not self._comunicados_visivel(page):
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue
        raise ErroTransitorio(
            "comunicados_nao_fechou",
            "modal de comunicados permaneceu aberto após o login",
        )

    def _comunicados_visivel(self, page) -> bool:
        try:
            titulo = page.get_by_text(
                re.compile(r"^\s*COMUNICADOS\s*$", re.I)
            ).first
            return titulo.is_visible()
        except Exception:
            return False

    def _passo_nova_proposta(self, page) -> None:
        """Abre Nova Proposta por URL e usa o menu como fallback."""
        cpf_box = page.get_by_role("textbox", name=re.compile(r"^CPF", re.I)).first
        try:
            page.goto(
                NOVA_PROPOSTA_URL,
                wait_until="commit",
                timeout=self.timeout_ms,
            )
        except Exception:
            # O portal pode concluir a troca de página e manter requisições pendentes.
            # Nesse caso o goto lança timeout, mas o formulário já está utilizável.
            pass
        self._aguardar_dom_pronto(page)
        try:
            cpf_box.wait_for(state="visible", timeout=min(self.timeout_ms, 15_000))
            cpf_box.click(trial=True, timeout=min(self.timeout_ms, 15_000))
            return
        except Exception:
            pass

        for nome in (r"^Propostas$", r"Criar Proposta", r"Nova Proposta"):
            clicou = False
            for papel in ("link", "button"):
                try:
                    page.get_by_role(
                        papel, name=re.compile(nome, re.I)
                    ).first.click(timeout=3_000)
                    page.wait_for_timeout(400)
                    clicou = True
                    break
                except Exception:
                    continue
            if clicou:
                self._aguardar_dom_pronto(page, 10_000)
                try:
                    cpf_box.wait_for(state="visible", timeout=5_000)
                    cpf_box.click(trial=True, timeout=5_000)
                    return
                except Exception:
                    continue

        raise ErroTransitorio(
            "nova_proposta_falhou",
            "tela de Nova Proposta (Criar Proposta) não abriu",
        )

    def _passo_dados_pessoais(self, page, sol: SolicitacaoSimulacao) -> None:
        cpf = re.sub(r"\D", "", sol.pessoa.cpf or "")
        cpf_box = page.get_by_role("textbox", name=re.compile(r"^CPF", re.I)).first
        cpf_box.fill(cpf)
        cpf_box.blur()  # dispara a consulta do CPF (portal reage ao sair do campo)
        page.wait_for_timeout(800)
        nasc = _formatar_nascimento_iso(sol.pessoa.nascimento)
        nasc_box = page.get_by_role("textbox", name=re.compile(r"Nascimento", re.I)).first
        nasc_box.wait_for(state="visible", timeout=self.timeout_ms)
        nasc_box.click(trial=True, timeout=self.timeout_ms)
        nasc_box.fill(nasc)
        # Portal só carrega (habilita o restante) ao SAIR do campo — blur = "clicar fora".
        nasc_box.blur()
        cel_box = page.get_by_role("textbox", name=re.compile(r"Celular", re.I)).first
        cel_box.wait_for(state="visible", timeout=self.timeout_ms)
        cel_box.click(trial=True, timeout=self.timeout_ms)
        cel_box.fill(sol.pessoa.celular or "")
        cel_box.blur()
        page.wait_for_timeout(500)

    def _passo_veiculo(self, page, sol: SolicitacaoSimulacao) -> None:
        # Moto usada (0KM = Não, value "0")
        try:
            page.get_by_label(re.compile(r"Veículo 0KM", re.I)).select_option("0")
        except Exception:
            pass
        placa = (sol.veiculo.placa or "").replace("-", "").upper()
        placa_box = page.get_by_role("textbox", name=re.compile(r"^Placa$", re.I))
        placa_box.first.wait_for(state="visible", timeout=self.timeout_ms)
        placa_box.first.click(trial=True, timeout=self.timeout_ms)
        placa_box.first.click()
        placa_box.first.fill(placa)
        page.keyboard.press("Tab")
        page.wait_for_timeout(1_200)
        # Portal resolve o veículo pela placa e mostra uma linha p/ selecionar.
        try:
            selecionar = page.get_by_role("row").filter(
                has=page.get_by_role("button")
            ).first.get_by_role("button")
            selecionar.wait_for(state="visible", timeout=self.timeout_ms)
            selecionar.click(timeout=self.timeout_ms)
        except Exception:
            # Sem linha => placa não resolveu.
            raise ErroTransitorio(
                "veiculo_nao_resolvido",
                "Portal não resolveu o veículo pela placa informada.",
            )
        page.wait_for_timeout(500)

    def _passo_financiamento(self, page, sol: SolicitacaoSimulacao) -> None:
        # 1) Valor de venda -> blur para o portal calcular o financiamento.
        valor_fmt = _formatar_moeda_input(float(sol.veiculo.valor))
        valor_box = page.get_by_role(
            "textbox", name=re.compile(r"Valor de venda", re.I)
        ).first
        valor_box.fill(valor_fmt)
        valor_box.blur()  # "clicar fora" — sem isso o financiamento não atualiza
        page.wait_for_timeout(1_200)

        # 2) Prazo (dropdown) precisa ser selecionado antes de simular; o resultado
        #    devolve todos os prazos de qualquer forma.
        prazo = None
        if sol.condicoes.prazos_meses:
            prazo = max(sol.condicoes.prazos_meses)
        elif sol.condicoes.prazo_meses:
            prazo = sol.condicoes.prazo_meses
        if prazo:
            self._selecionar_prazo(page, prazo)
            page.wait_for_timeout(500)

        # 3) Entrada baixa -> blur, para o portal devolver a mínima exigida.
        entrada = sol.condicoes.entrada or 0
        entrada_fmt = _formatar_moeda_input(float(entrada))
        try:
            entrada_box = page.get_by_role(
                "textbox", name=re.compile(r"Valor de entrada", re.I)
            ).first
            entrada_box.fill(entrada_fmt)
            entrada_box.blur()
            page.wait_for_timeout(600)
        except Exception:
            pass

        # 4) Autorização SCR (obrigatória antes de simular).
        try:
            page.get_by_role(
                "checkbox", name=re.compile(r"autoriza a consulta", re.I)
            ).check()
        except Exception:
            pass

    def _selecionar_prazo(self, page, prazo: int) -> None:
        """Prazo pode ser <select> nativo ou combobox pesquisável (select2)."""
        combo = page.get_by_role(
            "combobox", name=re.compile(r"Prazo em meses", re.I)
        ).first
        try:
            combo.select_option(str(prazo))
            return
        except Exception:
            pass
        # combobox pesquisável: abre, digita o prazo e confirma a opção.
        try:
            combo.click()
            page.wait_for_timeout(300)
            page.keyboard.type(str(prazo))
            page.wait_for_timeout(300)
            opcao = page.get_by_role("option", name=re.compile(rf"^\s*{prazo}\b"))
            if opcao.count() > 0:
                opcao.first.click(timeout=3_000)
            else:
                page.keyboard.press("Enter")
        except Exception:
            pass

    def _passo_simular_e_modais(self, page) -> None:
        simular = page.get_by_role("button", name=re.compile(r"^Simular$", re.I)).first
        simular.wait_for(state="visible", timeout=self.timeout_ms)
        simular.click(trial=True, timeout=self.timeout_ms)
        simular.click()
        # Aguarda o portal reagir: modal PEP, seguro, resultado ou erro. Se a
        # simulação ainda estiver processando, o passo seguinte mantém a espera.
        try:
            page.wait_for_function(
                r"""() => {
                    const texto = document.body?.innerText || '';
                    return /PEP|Continuar sem prote|Ocorreu um erro|falha/i.test(texto)
                        || /\d+\s*x\b/i.test(texto);
                }""",
                timeout=min(self.timeout_ms, 15_000),
            )
        except Exception:
            pass
        # Modal PEP ("Você é um PEP?") — respondemos p/ seguir (não-PEP: "Não").
        try:
            dialog = page.get_by_role("dialog", name=re.compile(r"PEP", re.I))
            if dialog.count() > 0:
                for nome in (r"^Não$", r"Continuar", r"Confirmar"):
                    try:
                        dialog.get_by_role(
                            "button", name=re.compile(nome, re.I)
                        ).first.click(timeout=2_000)
                        break
                    except Exception:
                        continue
        except Exception:
            pass
        # Upsell de seguro — segue sem proteção.
        try:
            page.get_by_role(
                "button", name=re.compile(r"Continuar sem prote", re.I)
            ).first.click(timeout=3_000)
        except Exception:
            pass

    def _passo_aguardar_resultado(self, page) -> None:
        """Espera os cards de parcela (dado real), não o container (lição #11)."""
        timeout = max(self.timeout_ms, 60_000)
        prazo_fim = time.monotonic() + (timeout / 1000.0)
        cards = re.compile(r"\d+\s*x\b", re.I)
        estavel = 0
        while time.monotonic() < prazo_fim:
            if page.get_by_text(re.compile(r"Ocorreu um erro|falha", re.I)).count() > 0:
                raise ErroTransitorio(
                    "portal_simulacao_erro", "erro exibido na tela de simulação"
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
            "portal_falhou", "cards de parcela não carregaram a tempo"
        )

    def _salvar_storage(self, browser_ctx) -> None:
        if not self.storage_state_path:
            return
        try:
            self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            browser_ctx.storage_state(path=str(self.storage_state_path))
        except Exception:
            pass


def fabrica_fontecred() -> FontecredDriver:
    from app.motor.playwright_base import browser_headless_padrao

    return FontecredDriver(
        headless=browser_headless_padrao(),
        screenshot_dir=config.SCREENSHOT_DIR,
        storage_state_path=Path(config.STORAGE_STATE_DIR) / "fontecred.json",
        timeout_ms=int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        login_url=getattr(config, "FONTECRED_LOGIN_URL", LOGIN_URL_DEFAULT),
    )
