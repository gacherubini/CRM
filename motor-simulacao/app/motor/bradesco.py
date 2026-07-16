"""Driver real Bradesco Financiamentos (portal Turbo Lojista) — Task 12.

Fluxo mapeado pelo codegen do lojista (turbo.bradesco, 2026-07):
  0. Login: CPF do lojista + Senha -> Entrar
  1. Botao "Nova proposta"
  2. Pre-analise da pessoa: CPF do cliente + Celular + aceite (checkbox) -> Avancar
  3. Veiculo: UF (mat-select), Placa (Opcional), seleciona o modelo -> Confirmar
  4. Valores: Valor do veiculo, Valor da entrada (opcional) -> Avancar
  5. Simulacao: fecha modal (se houver) -> Avancar
  6. Ofertas (multi-prazo): botoes "48x de R$ ...", "36x ...", ... e um prazo
     bloqueado "12x Entrada minima necessaria" (sem parcela numerica).

Portal em Angular Material (como o Santander): ancorar por role + texto visivel,
nunca por placeholder (o placeholder HTML fica vazio no Material).

Regra de negocio do dono: a **entrada nao e obrigatoria** no Bradesco. So
preenchemos "Valor da entrada (opcional)" quando o usuario mandar um valor > 0.

Modos:
- **fixture/html** (testes): ``html_simulacao=`` ou env ``MOTOR_BRADESCO_FIXTURE_HTML``
- **live** (Playwright): so com credencial + browser instalado

Nunca logar CPF/senha/celular. Login do lojista = campo ``usuario`` da credencial
(o CPF do LOJISTA, nao o do cliente).
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

# Provedor canonico (minusculo).
PROVEDOR = "bradesco"

LOGIN_URL_DEFAULT = "https://turbo.bradesco/originacaolojista/login"
STEP_VEHICLE_URL = "https://turbo.bradesco/originacaolojista/pre-analysis/step-vehicle"
SIMULATION_URL = "https://turbo.bradesco/originacaolojista/simulation"

# Cards de oferta: "48x de R$ 890,12" (o "de"/"R$" podem vir em tags separadas).
_RE_PARCELA = re.compile(
    r"(\d{1,3})\s*x\s*de\s*R\$\s*([\d.]+,\d{2})",
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


def parse_parcelas_bradesco(texto: str) -> list[tuple[int, Decimal]]:
    """Extrai (prazo_meses, parcela) dos botoes de oferta.

    Casa "Nx de R$ valor". O prazo bloqueado por entrada minima
    ("12x Entrada minima necessaria") nao tem "de R$ valor" e e ignorado.
    Mantem a primeira ocorrencia de cada prazo (o HTML cru pode duplicar cards).
    """
    plano = _texto_plano(texto)
    vistos: dict[int, Decimal] = {}
    for m in _RE_PARCELA.finditer(plano):
        prazo = int(m.group(1))
        parcela = parse_moeda_br(m.group(2))
        vistos.setdefault(prazo, parcela)
    return sorted(vistos.items(), key=lambda x: x[0])


def _formatar_moeda_input(valor: float) -> str:
    """Formato BR com milhar para inputs: 21900.00 -> 21.900,00."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _html_fixture_path() -> Path | None:
    raw = os.getenv("MOTOR_BRADESCO_FIXTURE_HTML", "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_file() else None
    return None


class BradescoDriver(PlaywrightBankDriver):
    """Robo do portal Turbo Lojista Bradesco (cotacao multi-prazo de motos)."""

    provedor = PROVEDOR
    real = True
    # Portal novo; o codegen do dono rodou em contexto vanilla e funcionou.
    # Comecamos como Fontecred (stealth off) para nao arriscar quebrar login por
    # reCAPTCHA (UA descasado trava o token). Se aparecer WAF/Akamai (Access
    # Denied), reavaliar ligando stealth=True como no Santander.
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
            config, "BRADESCO_LOGIN_URL", LOGIN_URL_DEFAULT
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
                "celular_obrigatorio", "Celular e obrigatorio no Bradesco"
            )

    def _resultados_de_html(
        self, html: str, sol: SolicitacaoSimulacao
    ) -> list[ResultadoDriver]:
        pares = parse_parcelas_bradesco(html)
        if not pares:
            raise IntervencaoNecessaria(
                "bradesco_sem_oferta",
                "nenhum botao de prazo legivel na tela de ofertas",
            )
        # Entrada e opcional no Bradesco; financiado = valor - entrada informada.
        entrada = Decimal(str(sol.condicoes.entrada or 0))
        financiado: Decimal | None = None
        if sol.veiculo.valor is not None:
            financiado = Decimal(str(sol.veiculo.valor)) - entrada
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
                    taxa_am=None,  # card nao exibe taxa a.m.
                    prazo_meses=prazo,
                    valor_financiado=financiado,
                    entrada=entrada if entrada > 0 else None,
                )
            )
        if not out:
            # filtro esvaziou => devolve todos os cards (parcial util)
            out = [
                ResultadoDriver(
                    provedor=self.provedor,
                    status="concluida",
                    valor_parcela=parcela,
                    prazo_meses=prazo,
                    valor_financiado=financiado,
                    entrada=entrada if entrada > 0 else None,
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

        cpf_lojista, senha = self._credencial(ctx)
        self._evento(ctx, "browser_iniciando", "Preparando o navegador do Bradesco.")

        with sync_playwright() as p:
            browser = self._launch_browser(p)
            browser_ctx = self._new_context(browser)
            page = browser_ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                self._evento(ctx, "browser_pronto", "Navegador iniciado; abrindo o portal.")
                self._passo_login(page, cpf_lojista, senha)
                self._evento(
                    ctx, "login_confirmado", "Login confirmado pelo portal.", page, True
                )
                self._pular_troca_senha(page)
                self._passo_nova_proposta(page)
                self._evento(
                    ctx, "proposta_aberta", "Tela de nova proposta carregada.", page, True
                )
                self._passo_pessoa(page, sol)
                self._passo_veiculo(page, sol)
                self._passo_valores(page, sol)
                self._evento(
                    ctx,
                    "dados_preenchidos",
                    "Dados do cliente, veiculo e valores preenchidos.",
                    page,
                    True,
                )
                self._passo_simular_e_modais(page)
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
                    f"falha no portal Bradesco: {type(exc).__name__}: {detalhe}",
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
        screenshot_conteudo = None
        if capturar_print and page is not None and config.EVENT_SCREENSHOTS:
            from app.motor.playwright_base import capturar_print_evento

            screenshot_path, screenshot_conteudo = capturar_print_evento(
                page,
                screenshot_dir=ctx.screenshot_dir or self.screenshot_dir,
                simulacao_id=ctx.simulacao_id,
                etapa=etapa,
            )
        ctx.registrar_evento(
            etapa,
            mensagem,
            nivel,
            screenshot_path=screenshot_path,
            screenshot_conteudo=screenshot_conteudo,
        )

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
                "cadastre CPF/senha do lojista em Acessos bancos (Portal)",
            )
        return segredo

    # --- passos do portal ---------------------------------------------------

    def _passo_login(self, page, cpf_lojista: str, senha: str) -> None:
        url = self.login_url
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        try:
            page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
        except Exception:
            # Storage state valido pode redirecionar direto ao portal autenticado;
            # networkidle expira mas a sessao ja esta pronta.
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

        cpf_box = page.get_by_role("textbox", name=re.compile(r"CPF", re.I)).first
        senha_box = page.get_by_role("textbox", name=re.compile(r"Senha", re.I)).first
        cpf_box.click()
        cpf_box.fill("")
        cpf_box.type(re.sub(r"\D", "", cpf_lojista), delay=35)
        page.wait_for_timeout(200)
        senha_box.click()
        senha_box.fill("")
        senha_box.type(senha, delay=40)
        page.wait_for_timeout(300)
        entrar = page.get_by_role("button", name=re.compile(r"^Entrar$", re.I))
        # Material deixa o botao disabled ate validar CPF/senha.
        try:
            page.wait_for_function(
                """() => {
                  const bs = [...document.querySelectorAll('button')];
                  const b = bs.find(x => /^\\s*Entrar\\s*$/i.test(x.textContent || ''));
                  return b && !b.disabled;
                }""",
                timeout=min(self.timeout_ms, 15_000),
            )
        except Exception:
            pass
        entrar.first.click()
        self._aguardar_pos_login(page)

    def _portal_autenticado(self, page) -> bool:
        """Reconhece area autenticada por uma sessao persistida valida."""
        try:
            url = str(page.url or "")
            if url and not re.search(r"/login\b", url, re.I):
                return True
        except Exception:
            pass
        try:
            if page.get_by_role(
                "button", name=re.compile(r"Nova proposta", re.I)
            ).first.is_visible():
                return True
        except Exception:
            pass
        return False

    def _aguardar_pos_login(self, page) -> None:
        timeout = max(self.timeout_ms, 45_000)
        try:
            page.wait_for_function(
                """() => {
                    const texto = document.body?.innerText || '';
                    return !/\\/login\\b/i.test(location.pathname)
                        || /Nova proposta/i.test(texto);
                }""",
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
                "Portal rejeitou CPF/senha do lojista. Atualize em Acessos bancos.",
            )
        raise ErroTransitorio(
            "login_timeout", "Login nao concluiu a tempo (ainda na tela de login)."
        )

    def _aguardar_dom_pronto(self, page, timeout_ms: int | None = None) -> None:
        """Aguarda o DOM utilizavel sem exigir networkidle do portal."""
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

    def _pular_troca_senha(self, page) -> None:
        """Interstitial pos-login: "Sua senha expira em N dias" (first-access/
        flow-feedback). Clica "Trocar senha depois" para seguir ao dashboard.

        So aparece perto do vencimento/primeiro acesso; e best-effort (se nao
        estiver, segue direto). NUNCA clicar "Trocar senha" (mudaria a senha).
        """
        try:
            # Marcador da tela: aviso de expiracao. Espera curta — pode nem aparecer.
            aviso = page.get_by_text(re.compile(r"senha expira", re.I)).first
            visivel = False
            try:
                aviso.wait_for(state="visible", timeout=min(self.timeout_ms, 6_000))
                visivel = True
            except Exception:
                visivel = "first-access" in (page.url or "").lower()
            if not visivel:
                return
            for papel in ("button", "link"):
                try:
                    page.get_by_role(
                        papel, name=re.compile(r"Trocar senha depois", re.I)
                    ).first.click(timeout=min(self.timeout_ms, 6_000))
                    self._aguardar_dom_pronto(page, 10_000)
                    page.wait_for_timeout(400)
                    return
                except Exception:
                    continue
        except Exception:
            pass

    def _passo_nova_proposta(self, page) -> None:
        nova = page.get_by_role("button", name=re.compile(r"Nova proposta", re.I)).first
        nova.wait_for(state="visible", timeout=self.timeout_ms)
        nova.click()
        self._aguardar_dom_pronto(page)
        # Espera o campo CPF do cliente ficar acionavel.
        try:
            page.get_by_role("textbox", name=re.compile(r"CPF", re.I)).first.wait_for(
                state="visible", timeout=min(self.timeout_ms, 15_000)
            )
        except Exception:
            pass

    def _passo_pessoa(self, page, sol: SolicitacaoSimulacao) -> None:
        cpf = re.sub(r"\D", "", sol.pessoa.cpf or "")
        cpf_box = page.get_by_role("textbox", name=re.compile(r"CPF", re.I)).first
        cpf_box.wait_for(state="visible", timeout=self.timeout_ms)
        cpf_box.click()
        cpf_box.fill("")
        cpf_box.type(cpf, delay=30)
        cel_box = page.get_by_role("textbox", name=re.compile(r"Celular", re.I)).first
        cel_box.wait_for(state="visible", timeout=self.timeout_ms)
        cel_box.click()
        cel_box.fill("")
        cel_box.type(sol.pessoa.celular or "", delay=30)
        page.wait_for_timeout(300)
        # Aceite obrigatorio (checkbox Material). Preferir role acessivel; o
        # ".mat-checkbox-inner-container" do codegen e fragil (fallback).
        self._marcar_aceite(page)
        self._clicar_avancar(page)

    def _marcar_aceite(self, page) -> None:
        try:
            cb = page.get_by_role("checkbox").first
            cb.wait_for(state="visible", timeout=min(self.timeout_ms, 8_000))
            cb.check()
            return
        except Exception:
            pass
        try:
            page.locator(".mat-checkbox-inner-container").first.click(
                force=True, timeout=5_000
            )
        except Exception:
            pass

    def _passo_veiculo(self, page, sol: SolicitacaoSimulacao) -> None:
        # UF do licenciamento (mat-select). Default SP se nao informado.
        uf = (sol.veiculo.uf_licenciamento or "SP").strip().upper()
        try:
            page.locator(".mat-select-placeholder, mat-select").first.click(
                timeout=min(self.timeout_ms, 10_000)
            )
            page.get_by_text(re.compile(rf"^\s*{re.escape(uf)}\s*$", re.I)).first.click(
                timeout=min(self.timeout_ms, 8_000)
            )
        except Exception:
            pass
        # Placa (opcional no portal, mas usamos quando disponivel para resolver
        # o veiculo). Se ausente, o portal exige selecao manual do modelo.
        placa = (sol.veiculo.placa or "").replace("-", "").upper()
        if placa:
            try:
                placa_box = page.get_by_role(
                    "textbox", name=re.compile(r"Placa", re.I)
                ).first
                placa_box.wait_for(state="visible", timeout=min(self.timeout_ms, 10_000))
                placa_box.click()
                placa_box.fill("")
                placa_box.type(placa, delay=40)
                page.keyboard.press("Tab")
                page.wait_for_timeout(1_200)
            except Exception:
                pass
        # Modal "Foram encontradas diferentes versoes para a placa": seleciona a
        # PRIMEIRA versao e confirma (regra do dono). So aparece quando a placa
        # casa varias versoes; e best-effort.
        self._selecionar_versao_veiculo(page)
        self._clicar_confirmar(page)

    def _selecionar_versao_veiculo(self, page) -> None:
        """No modal de versoes da placa, marca a primeira opcao (radio)."""
        try:
            aviso = page.get_by_text(
                re.compile(r"selecione a vers[aã]o|diferentes vers[oõ]es", re.I)
            ).first
            try:
                aviso.wait_for(state="visible", timeout=min(self.timeout_ms, 10_000))
            except Exception:
                # Sem modal (placa resolveu versao unica) -> nada a fazer.
                return
            # Primeira opcao: role=radio e o alvo estavel; fallback no container.
            for alvo in (
                lambda: page.get_by_role("radio").first.check(
                    timeout=min(self.timeout_ms, 6_000)
                ),
                lambda: page.get_by_role("radio").first.click(
                    force=True, timeout=min(self.timeout_ms, 6_000)
                ),
                lambda: page.locator("mat-radio-button").first.click(
                    force=True, timeout=min(self.timeout_ms, 6_000)
                ),
            ):
                try:
                    alvo()
                    break
                except Exception:
                    continue
            page.wait_for_timeout(300)
        except Exception:
            pass

    def _passo_valores(self, page, sol: SolicitacaoSimulacao) -> None:
        # Valor do veiculo (se editavel / nao resolvido pela placa).
        if sol.veiculo.valor is not None:
            try:
                valor_box = page.get_by_role(
                    "textbox", name=re.compile(r"Valor do ve[ií]culo", re.I)
                ).first
                valor_box.wait_for(state="visible", timeout=min(self.timeout_ms, 10_000))
                valor_box.click()
                valor_box.fill("")
                valor_box.type(_formatar_moeda_input(float(sol.veiculo.valor)), delay=25)
            except Exception:
                pass
        # Entrada e OPCIONAL: so preenche se o usuario mandou valor > 0.
        entrada = sol.condicoes.entrada or 0
        if entrada and float(entrada) > 0:
            try:
                entrada_box = page.get_by_role(
                    "textbox", name=re.compile(r"Valor da entrada", re.I)
                ).first
                entrada_box.click()
                entrada_box.fill("")
                entrada_box.type(_formatar_moeda_input(float(entrada)), delay=25)
            except Exception:
                pass
        self._clicar_avancar(page)

    def _passo_simular_e_modais(self, page) -> None:
        # A tela de simulacao pode abrir um modal informativo -> Fechar.
        try:
            page.get_by_role("button", name=re.compile(r"^Fechar$", re.I)).first.click(
                timeout=min(self.timeout_ms, 5_000)
            )
            page.wait_for_timeout(400)
        except Exception:
            pass
        # Avanca para a etapa de ofertas (se houver botao Avancar nesta tela).
        try:
            page.get_by_role("button", name=re.compile(r"^Avan[çc]ar$", re.I)).first.click(
                timeout=min(self.timeout_ms, 5_000)
            )
        except Exception:
            pass

    def _clicar_avancar(self, page) -> None:
        btn = page.get_by_role("button", name=re.compile(r"^Avan[çc]ar$", re.I)).first
        btn.wait_for(state="visible", timeout=self.timeout_ms)
        try:
            page.wait_for_function(
                """() => {
                  const bs = [...document.querySelectorAll('button')];
                  const b = bs.find(x => /^\\s*Avan[çc]ar\\s*$/i.test(x.textContent || ''));
                  return b && !b.disabled;
                }""",
                timeout=min(self.timeout_ms, 12_000),
            )
        except Exception:
            pass
        btn.click()
        self._aguardar_dom_pronto(page, 10_000)

    def _clicar_confirmar(self, page) -> None:
        try:
            btn = page.get_by_role(
                "button", name=re.compile(r"^Confirmar$", re.I)
            ).first
            btn.wait_for(state="visible", timeout=min(self.timeout_ms, 10_000))
            btn.click()
            self._aguardar_dom_pronto(page, 10_000)
        except Exception:
            pass

    def _passo_aguardar_ofertas(self, page) -> None:
        """Espera os botoes de prazo ("Nx de R$") aparecerem de fato."""
        timeout = max(self.timeout_ms, 60_000)
        prazo_fim = time.monotonic() + (timeout / 1000.0)
        cards = re.compile(r"\d+\s*x\s*de\s*R\$", re.I)
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
            "portal_falhou", "botoes de prazo nao carregaram a tempo"
        )

    def _salvar_storage(self, browser_ctx) -> None:
        if not self.storage_state_path:
            return
        try:
            self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            browser_ctx.storage_state(path=str(self.storage_state_path))
        except Exception:
            pass


def fabrica_bradesco() -> BradescoDriver:
    from app.motor.playwright_base import browser_headless_padrao

    return BradescoDriver(
        headless=browser_headless_padrao(),
        screenshot_dir=config.SCREENSHOT_DIR,
        storage_state_path=Path(config.STORAGE_STATE_DIR) / "bradesco.json",
        timeout_ms=int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        login_url=getattr(config, "BRADESCO_LOGIN_URL", LOGIN_URL_DEFAULT),
    )
