"""Driver real Santander Financiamentos (Aymoré) — Task 12.

Fluxo mapeado pelas telas do portal do lojista (2026-07):
  0. Login: CPF do lojista + senha
  1. Cliente (CPF, nascimento, CNH) + veículo por placa + valor + UF + finalidade
  2. Concordar termos → modal UF → Continuar
  3. Simulação (1/2) Padrão: entrada + ler cards de parcela → fim (cotação)

Modos:
- **fixture/html** (testes): ``html_simulacao=`` ou env ``MOTOR_SANTANDER_FIXTURE_HTML``
- **live** (Playwright): só com credencial + browser instalado

Nunca logar CPF/senha. Login do lojista = campo ``usuario`` da credencial (CPF).
"""
from __future__ import annotations

import os
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

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

# Provedor canônico (minúsculo) — mock usa "Santander" com S maiúsculo.
PROVEDOR = "santander"

LOGIN_URL_DEFAULT = (
    "https://financiamentos.santander.com.br/originacao-auto/login"
)

# UF → rótulo como no portal (prints: "SAO PAULO").
UF_PARA_PORTAL: dict[str, str] = {
    "AC": "ACRE",
    "AL": "ALAGOAS",
    "AP": "AMAPA",
    "AM": "AMAZONAS",
    "BA": "BAHIA",
    "CE": "CEARA",
    "DF": "DISTRITO FEDERAL",
    "ES": "ESPIRITO SANTO",
    "GO": "GOIAS",
    "MA": "MARANHAO",
    "MT": "MATO GROSSO",
    "MS": "MATO GROSSO DO SUL",
    "MG": "MINAS GERAIS",
    "PA": "PARA",
    "PB": "PARAIBA",
    "PR": "PARANA",
    "PE": "PERNAMBUCO",
    "PI": "PIAUI",
    "RJ": "RIO DE JANEIRO",
    "RN": "RIO GRANDE DO NORTE",
    "RS": "RIO GRANDE DO SUL",
    "RO": "RONDONIA",
    "RR": "RORAIMA",
    "SC": "SANTA CATARINA",
    "SP": "SAO PAULO",
    "SE": "SERGIPE",
    "TO": "TOCANTINS",
}

# Cards: "48x de R$ 946,28" — no portal real o "R$" costuma vir em outra tag/linha.
_RE_PARCELA = re.compile(
    r"(\d+)\s*x\s*de\s*R\$\s*([\d.]+,\d{2})",
    re.IGNORECASE,
)
# Só imediatamente após o rótulo — o antigo ".*?" caía no R$ da parcela (ex.: 946,28).
_RE_VALOR_LIBERADO = re.compile(
    r"Valor liberado\s+R\$\s*([\d.]+,\d{2})",
    re.IGNORECASE,
)
# Fallback com pouco lixo no meio, sem atravessar cards "Nx de".
_RE_VALOR_LIBERADO_FROUXO = re.compile(
    r"Valor liberado\s{0,40}R\$\s*([\d.]+,\d{2})",
    re.IGNORECASE,
)
# Entrada necessaria que o Santander calcula e devolve na tela de ofertas.
# \b evita casar "Valor liberado"/"Valor do veículo"; ancorado no proprio rotulo.
_RE_ENTRADA = re.compile(
    r"\bEntrada\b\s+R\$\s*([\d.]+,\d{2})",
    re.IGNORECASE,
)


def _texto_plano_portal(texto: str) -> str:
    """Normaliza HTML/texto do portal para parsing (tags e quebras viram espaço)."""
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
    """Extrai (prazo_meses, parcela) de HTML/texto da tela de simulação.

    Aceita layout real do Portal Auto onde o card quebra linha:
    ``48x de`` + ``R$ 946,28`` em nós separados.
    """
    plano = _texto_plano_portal(texto)
    vistos: dict[int, Decimal] = {}
    for m in _RE_PARCELA.finditer(plano):
        prazo = int(m.group(1))
        parcela = parse_moeda_br(m.group(2))
        # mantém a primeira ocorrência de cada prazo
        vistos.setdefault(prazo, parcela)
    return sorted(vistos.items(), key=lambda x: x[0])


def parse_valor_liberado(texto: str) -> Decimal | None:
    """Valor financiado (rótulo 'Valor liberado'). Não confunde com parcela."""
    plano = _texto_plano_portal(texto)
    for rx in (_RE_VALOR_LIBERADO, _RE_VALOR_LIBERADO_FROUXO):
        m = rx.search(plano)
        if not m:
            continue
        # Descarta se o trecho entre rótulo e R$ contém card de parcela.
        meio = plano[m.start() : m.start(1)]
        if re.search(r"\d+\s*x\s*de", meio, re.I):
            continue
        val = parse_moeda_br(m.group(1))
        # Financiado real é tipicamente milhares; parcela sozinha ~centenas–2k
        # e já existe em "Nx de R$". Se o valor bate com uma parcela parseada, ignora.
        parcelas = {p for _, p in parse_parcelas_texto(plano)}
        if val in parcelas:
            continue
        return val
    return None


def parse_entrada(texto: str) -> Decimal | None:
    """Entrada necessaria devolvida pela tela (rotulo 'Entrada').

    O Santander calcula a entrada; nao a recebemos como input. Ancorado no
    rotulo com \\b para nao confundir com 'Valor liberado'/'Valor do veiculo';
    descarta se casar o R$ de um card de parcela.
    """
    plano = _texto_plano_portal(texto)
    for m in _RE_ENTRADA.finditer(plano):
        val = parse_moeda_br(m.group(1))
        # Um card "Nx de R$ ..." imediatamente antes do valor => nao e a entrada.
        meio = plano[m.start() : m.start(1)]
        if re.search(r"\d+\s*x\s*de", meio, re.I):
            continue
        parcelas = {p for _, p in parse_parcelas_texto(plano)}
        if val in parcelas:
            continue
        return val
    return None


def uf_para_portal(uf: str | None) -> str:
    if not uf:
        return "SAO PAULO"
    u = uf.strip().upper()
    if len(u) == 2:
        return UF_PARA_PORTAL.get(u, u)
    return u.replace("Ã", "A").replace("Ç", "C")  # normalização leve


def _html_fixture_path() -> Path | None:
    raw = os.getenv("MOTOR_SANTANDER_FIXTURE_HTML", "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_file() else None
    return None


class SantanderDriver(PlaywrightBankDriver):
    """Robô do portal do lojista Santander (cotação multi-prazo)."""

    provedor = PROVEDOR
    real = True

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
            headless=headless,  # None → headed (anti-Akamai); ver browser_headless_padrao
            storage_state_path=storage_state_path,
            screenshot_dir=screenshot_dir
            or getattr(config, "SCREENSHOT_DIR", None),
            timeout_ms=timeout_ms
            if timeout_ms is not None
            else int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        )
        self.login_url = login_url or getattr(
            config, "SANTANDER_LOGIN_URL", LOGIN_URL_DEFAULT
        )
        # Testes: HTML da tela de parcelas sem abrir browser
        self.html_simulacao = html_simulacao

    def simular(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        self._validar_solicitacao(sol)

        # Modo fixture (testes / dev offline)
        html = self.html_simulacao
        if html is None:
            fix = _html_fixture_path()
            if fix is not None:
                html = fix.read_text(encoding="utf-8")
        if html is not None:
            return self._resultados_de_html(html, sol)

        # Live Playwright
        return self._simular_playwright(sol, ctx)

    def _validar_solicitacao(self, sol: SolicitacaoSimulacao) -> None:
        if not sol.pessoa.cpf or not sol.pessoa.nascimento:
            raise RejeicaoNegocio("dados_cliente", "CPF e nascimento são obrigatórios")
        if not sol.veiculo.placa:
            raise RejeicaoNegocio("placa_obrigatoria", "Placa é obrigatória no Santander")
        if sol.veiculo.valor is None and not sol.veiculo.placa:
            raise RejeicaoNegocio("valor_ou_placa", "Informe valor ou placa")

    def _resultados_de_html(
        self, html: str, sol: SolicitacaoSimulacao
    ) -> list[ResultadoDriver]:
        pares = parse_parcelas_texto(html)
        if not pares:
            raise IntervencaoNecessaria(
                "parcelas_nao_encontradas",
                "nenhum card de parcela encontrado na tela de simulação",
            )
        # Entrada necessaria: o Santander calcula e devolve na tela (nao e input).
        entrada_necessaria = parse_entrada(html)
        financiado = parse_valor_liberado(html)
        if financiado is None and sol.veiculo.valor is not None:
            desconto = entrada_necessaria if entrada_necessaria is not None else Decimal(
                str(sol.condicoes.entrada or 0)
            )
            financiado = Decimal(str(sol.veiculo.valor)) - desconto
            if financiado < 0:
                financiado = Decimal("0")
        # Filtra prazos pedidos se a solicitação trouxe lista
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
                    taxa_am=None,  # portal desta tela não exibe taxa a.m. no card
                    prazo_meses=prazo,
                    valor_financiado=financiado,
                    entrada=entrada_necessaria,
                )
            )
        if not out:
            # se filtro esvaziou, devolve todos os cards (parcial útil)
            out = [
                ResultadoDriver(
                    provedor=self.provedor,
                    status="concluida",
                    valor_parcela=parcela,
                    prazo_meses=prazo,
                    valor_financiado=financiado,
                    entrada=entrada_necessaria,
                )
                for prazo, parcela in pares
            ]
        return out

    # --- Playwright live -----------------------------------------------------

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

        cred = self._credencial(ctx)
        cpf_lojista, senha = cred
        self._evento(ctx, "browser_iniciando", "Preparando o navegador do Santander.")

        with sync_playwright() as p:
            # Um browser por banco (isolamento multi-provedor).
            browser = self._launch_browser(p)
            browser_ctx = self._new_context(browser, ctx)
            page = browser_ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                self._evento(ctx, "browser_pronto", "Navegador iniciado; abrindo o portal.")
                self._passo_login(page, cpf_lojista, senha)
                self._evento(
                    ctx, "login_confirmado", "Login confirmado pelo portal.", page, True
                )
                self._passo_cliente_veiculo(page, sol)
                self._evento(
                    ctx,
                    "dados_preenchidos",
                    "Dados do cliente e do veículo preenchidos.",
                    page,
                    True,
                )
                self._passo_termos_e_modal_uf(page)
                self._evento(
                    ctx, "simulacao_enviada", "Consulta enviada; aguardando ofertas do banco."
                )
                self._passo_aguardar_simulacao(page)
                self._evento(
                    ctx, "ofertas_recebidas", "Ofertas carregadas na tela do banco.", page, True
                )
                # Santander calcula a entrada necessaria e a devolve na tela; nao
                # enviamos entrada como input (ver parse_entrada / _resultados_de_html).
                # inner_text é mais estável que HTML cru (cards quebram "de" / "R$")
                try:
                    texto = page.inner_text("body") or ""
                except Exception:
                    texto = ""
                html = page.content() or ""
                resultados = self._resultados_de_html(texto + "\n" + html, sol)
                self._salvar_storage(browser_ctx, ctx)
                self._evento(
                    ctx, "parcelas_lidas", "Parcelas interpretadas e prontas para salvar.",
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
                raise
            except Exception as exc:
                self._evento(
                    ctx,
                    "falha_inesperada",
                    "O portal apresentou uma falha inesperada.",
                    page,
                    True,
                    "erro",
                )
                # Não logar stack com PII; mensagem curta só com tipo + trecho.
                detalhe = str(exc).replace("\n", " ")[:180]
                raise ErroTransitorio(
                    "portal_falhou",
                    f"falha no portal Santander: {type(exc).__name__}: {detalhe}",
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
                "sem_contexto", "driver real exige cliente_id e sessão DB"
            )
        from app.credenciais import obter_segredo_para_uso

        segredo = obter_segredo_para_uso(ctx.db, ctx.cliente_id, self.provedor)
        if not segredo:
            raise IntervencaoNecessaria(
                "sem_credencial",
                "cadastre CPF/senha do lojista em Acessos bancos (Portal)",
            )
        return segredo

    def _passo_login(self, page, cpf_lojista: str, senha: str) -> None:
        # Força HTTPS (WAF às vezes responde Access Denied em http).
        url = self.login_url
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        # networkidle costuma ajudar a passar desafios JS do WAF; fallback domcontentloaded.
        try:
            page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        # Pausa curta “humana” — bots disparam fill imediato.
        page.wait_for_timeout(800)
        self._assert_portal_acessivel(page)
        # Angular Material: placeholder HTML fica vazio; o texto “Digite o seu CPF”
        # é label flutuante. get_by_placeholder nunca acha o campo → timeout ~60s.
        cpf_box = self._campo_login_cpf(page)
        senha_box = self._campo_login_senha(page)
        cpf_box.click()
        cpf_box.fill("")
        cpf_box.type(re.sub(r"\D", "", cpf_lojista), delay=35)
        page.wait_for_timeout(200)
        senha_box.click()
        senha_box.fill("")
        senha_box.type(senha, delay=40)
        page.wait_for_timeout(300)
        entrar = page.get_by_role("button", name=re.compile(r"^Entrar$", re.I))
        # Material deixa o botão disabled até validar CPF/senha.
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
        entrar.click()
        self._aguardar_pos_login(page)

    def _aguardar_pos_login(self, page) -> None:
        """Espera o login de verdade — não usar 'Cliente' (casa com 'clientes' na landing)."""
        timeout = max(self.timeout_ms, 60_000)
        # Overlay "Por favor, aguarde..." após clicar Entrar (pode demorar a aparecer).
        overlay = page.get_by_text(re.compile(r"Por favor,?\s*aguarde", re.I))
        try:
            overlay.first.wait_for(state="visible", timeout=5_000)
        except Exception:
            pass
        try:
            overlay.first.wait_for(state="hidden", timeout=timeout)
        except Exception:
            pass
        # Marcadores da área logada (passo 1 / menu). Evitar substring genérica.
        marcadores = re.compile(
            r"Informações básicas|CPF ou CNPJ|Dados do cliente|"
            r"Nova proposta|Busca por placa|Simular",
            re.I,
        )
        try:
            page.get_by_text(marcadores).first.wait_for(state="visible", timeout=timeout)
            return
        except Exception:
            pass
        # URL saiu de /login?
        try:
            page.wait_for_function(
                "() => !/\\/login\\b/i.test(location.href) && !/\\/login\\b/i.test(location.hash)",
                timeout=5_000,
            )
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
                "login_rejeitado",
                "Portal rejeitou CPF/senha do lojista. Atualize em Acessos bancos.",
            )
        url = page.url or ""
        if re.search(r"/login", url, re.I) or re.search(
            r"Por favor,?\s*aguarde|Portal do lojista", body, re.I
        ):
            raise ErroTransitorio(
                "login_timeout",
                "Login não concluiu a tempo (overlay ou ainda na tela de login).",
            )
        raise ErroTransitorio(
            "portal_falhou",
            "pós-login: tela esperada não apareceu",
        )

    def _campo_login_cpf(self, page):
        """CPF lojista — Material: placeholder HTML vazio; input type=tel com máscara."""
        # Preferir type=tel (estável no Portal Auto); label flutuante demora a montar.
        tel = page.locator("input[type=tel]").first
        try:
            tel.wait_for(state="visible", timeout=min(self.timeout_ms, 20_000))
            return tel
        except Exception:
            pass
        loc = page.get_by_label(re.compile(r"^CPF\b", re.I))
        if loc.count() > 0:
            return loc.first
        box = page.get_by_role("textbox").nth(0)
        box.wait_for(state="visible", timeout=min(self.timeout_ms, 15_000))
        return box

    def _campo_login_senha(self, page):
        # Campo senha no portal é type=text (não password), mas tem label "senha".
        loc = page.get_by_label(re.compile(r"senha", re.I))
        try:
            loc.first.wait_for(state="visible", timeout=min(self.timeout_ms, 15_000))
            return loc.first
        except Exception:
            pass
        box = page.get_by_role("textbox").nth(1)
        box.wait_for(state="visible", timeout=min(self.timeout_ms, 10_000))
        return box

    def _aguardar_loading(self, page, timeout_ms: int | None = None) -> None:
        """Espera sumir o overlay 'Por favor, aguarde...' do portal."""
        t = timeout_ms or self.timeout_ms
        overlay = page.locator(
            ".loading-indicator__text, app-loading-indicator .loading-indicator__text"
        )
        try:
            overlay.first.wait_for(state="visible", timeout=3_000)
        except Exception:
            pass
        try:
            # pode haver vários; espera todos hidden
            page.locator(".loading-indicator__text").first.wait_for(
                state="hidden", timeout=t
            )
        except Exception:
            pass
        page.wait_for_timeout(200)

    def _fechar_modal_simulacoes_anteriores(self, page) -> None:
        """Cliente com proposta em andamento abre modal — fecha com X para nova simulação."""
        titulo = page.get_by_role(
            "heading", name=re.compile(r"Simula[cç][oõ]es anteriores", re.I)
        )
        try:
            titulo.wait_for(state="visible", timeout=8_000)
        except Exception:
            return
        dialog = page.locator(".cdk-overlay-pane").filter(
            has=page.get_by_role(
                "heading", name=re.compile(r"Simula[cç][oõ]es anteriores", re.I)
            )
        )
        # Nunca clicar "Continuar essa simulação" aqui — queremos nova cotação.
        # Ordem: mat-dialog-close / botão sem "Continuar" (o X) / Escape.
        for attempt in (
            lambda: dialog.locator("button[mat-dialog-close]").first.click(
                timeout=2_000, force=True
            ),
            lambda: dialog.locator("[mat-dialog-close]").first.click(
                timeout=2_000, force=True
            ),
            lambda: dialog.get_by_role("button")
            .filter(has_not_text=re.compile(r"Continuar", re.I))
            .first.click(timeout=2_000, force=True),
            lambda: dialog.locator("button").filter(has=page.locator("mat-icon")).first.click(
                timeout=2_000, force=True
            ),
            lambda: page.keyboard.press("Escape"),
        ):
            try:
                attempt()
            except Exception:
                continue
            try:
                titulo.wait_for(state="hidden", timeout=4_000)
                break
            except Exception:
                continue
        # Backdrop some quando o dialog fecha de verdade.
        try:
            page.locator(".cdk-overlay-backdrop").first.wait_for(
                state="hidden", timeout=8_000
            )
        except Exception:
            pass
        try:
            titulo.wait_for(state="hidden", timeout=5_000)
        except Exception:
            # último recurso: force hide via Escape + force click fora
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                page.keyboard.press("Escape")
            except Exception:
                pass
        self._aguardar_loading(page, timeout_ms=15_000)

    def _preencher_por_label(self, page, padrao: str, valor: str) -> None:
        """Preenche input Material por label acessível (placeholder HTML costuma vazio)."""
        rx = re.compile(padrao, re.I)
        loc = page.get_by_label(rx)
        if loc.count() == 0:
            loc = page.get_by_role("textbox", name=rx)
        if loc.count() == 0:
            # formcontrolname comum no Portal Auto
            if re.search(r"nascimento", padrao, re.I):
                loc = page.locator('input[formcontrolname="dateOfBirth"]')
            elif re.search(r"placa", padrao, re.I):
                loc = page.locator(
                    'input[formcontrolname*="plate" i], input[formcontrolname*="placa" i]'
                )
            elif re.search(r"CPF|CNPJ", padrao, re.I):
                loc = page.locator(
                    'input[formcontrolname*="document" i], input[formcontrolname*="cpf" i]'
                )
        if loc.count() == 0:
            raise self._falha_campo(padrao)
        # Preferir textbox real — get_by_label("Placa") às vezes pega o radio
        # "Busca por placa" (input type=radio).
        box = loc.first
        try:
            tag = (box.evaluate("el => (el.type || el.tagName || '').toLowerCase()") or "")
            if tag in ("radio", "checkbox"):
                textbox = page.get_by_role("textbox", name=rx)
                if textbox.count() > 0:
                    box = textbox.first
                else:
                    # próximo input de texto/tel visível com formcontrol de placa
                    alt = page.locator(
                        'input[formcontrolname*="plate" i], '
                        'input[formcontrolname*="placa" i], '
                        'input[type="text"]:not([formcontrolname="dateOfBirth"])'
                    )
                    if alt.count() > 0:
                        box = alt.last
        except Exception:
            pass
        # force evita falha se residual do cdk-overlay interceptar hit-test
        box.click(force=True, timeout=min(self.timeout_ms, 15_000))
        box.fill("")
        box.type(str(valor), delay=30)

    def _passo_cliente_veiculo(self, page, sol: SolicitacaoSimulacao) -> None:
        """Passo 1 real do Portal Auto (2026-07): CPF → (modal) → nasc/CNH → placa → valor."""
        cpf = re.sub(r"\D", "", sol.pessoa.cpf or "")
        # 1) CPF/CNPJ do cliente + Tab para disparar consulta
        self._preencher_por_label(page, r"CPF ou CNPJ", cpf)
        page.keyboard.press("Tab")
        self._aguardar_loading(page)
        # Modal se o cliente já tem proposta em andamento
        self._fechar_modal_simulacoes_anteriores(page)

        # 2) Nascimento (só aparece após consulta do CPF)
        nasc = _formatar_nascimento(sol.pessoa.nascimento)
        try:
            page.get_by_label(re.compile(r"nascimento", re.I)).first.wait_for(
                state="visible", timeout=self.timeout_ms
            )
        except Exception as exc:
            raise ErroTransitorio(
                "portal_falhou",
                "campo data de nascimento não apareceu após CPF do cliente",
            ) from exc
        self._preencher_por_label(page, r"nascimento", nasc)

        # 3) CNH — default do portal é "Sim"; só clica se precisar "Não"
        if sol.pessoa.cnh is False:
            try:
                page.get_by_text(re.compile(r"^Não$", re.I)).first.click(
                    force=True, timeout=5_000
                )
            except Exception:
                page.locator("mat-radio-button").filter(
                    has_text=re.compile(r"Não", re.I)
                ).first.click(force=True)

        # 4) Busca por placa
        try:
            page.locator("mat-radio-button").filter(
                has_text=re.compile(r"Busca por placa", re.I)
            ).click(force=True, timeout=10_000)
        except Exception:
            page.get_by_text(re.compile(r"Busca por placa", re.I)).first.click(
                force=True
            )
        page.wait_for_timeout(600)
        placa = (sol.veiculo.placa or "").replace("-", "").upper()
        # Campo de placa só existe após marcar "Busca por placa".
        placa_box = page.get_by_role("textbox", name=re.compile(r"Placa", re.I))
        if placa_box.count() == 0:
            placa_box = page.locator(
                'input[formcontrolname*="plate" i], input[formcontrolname*="placa" i]'
            )
        if placa_box.count() == 0:
            # fallback: último text input novo (não CPF, não data)
            placa_box = page.locator(
                'input[type="text"]:not([formcontrolname="dateOfBirth"])'
            )
        try:
            placa_box.last.wait_for(state="visible", timeout=15_000)
        except Exception as exc:
            raise ErroTransitorio(
                "portal_falhou", "campo Placa não apareceu após Busca por placa"
            ) from exc
        pb = placa_box.last
        pb.click(force=True)
        pb.fill("")
        pb.type(placa, delay=40)
        page.keyboard.press("Tab")
        self._aguardar_loading(page)
        # Aguarda retorno de veículo (marca/modelo/FIPE ou valor)
        try:
            page.get_by_text(re.compile(r"Marca|Modelo|FIPE|Ano", re.I)).first.wait_for(
                timeout=self.timeout_ms
            )
        except Exception:
            pass

        # 5) Valor do veículo (se ainda editável)
        if sol.veiculo.valor is not None:
            valor_fmt = _formatar_moeda_input(float(sol.veiculo.valor))
            try:
                self._preencher_por_label(page, r"Valor", valor_fmt)
            except Exception:
                try:
                    page.locator(
                        'input[formcontrolname*="value" i], input[formcontrolname*="valor" i]'
                    ).first.fill(valor_fmt)
                except Exception:
                    pass

        # 6) Finalidade (default Comum)
        fin = (sol.veiculo.finalidade or "comum").lower()
        if fin == "pcd":
            page.locator("mat-radio-button").filter(
                has_text=re.compile(r"PCD", re.I)
            ).first.click(force=True)
        else:
            try:
                page.locator("mat-radio-button").filter(
                    has_text=re.compile(r"Comum", re.I)
                ).first.click(force=True, timeout=5_000)
            except Exception:
                pass

        # 7) UF de licenciamento se o seletor existir
        uf_label = uf_para_portal(sol.veiculo.uf_licenciamento)
        try:
            page.get_by_text(re.compile(r"Licenciamento", re.I)).click(timeout=3_000)
            page.get_by_text(uf_label, exact=False).first.click(timeout=3_000)
        except Exception:
            pass
        # Fecha mat-select / autocomplete que deixam backdrop transparente.
        self._fechar_overlays_soltos(page)

    def _fechar_overlays_soltos(self, page) -> None:
        """Remove backdrop transparente de mat-select que bloqueia cliques."""
        for _ in range(3):
            try:
                page.keyboard.press("Escape")
            except Exception:
                break
            page.wait_for_timeout(150)
        try:
            page.locator(".cdk-overlay-backdrop.cdk-overlay-backdrop-showing").first.wait_for(
                state="hidden", timeout=3_000
            )
        except Exception:
            try:
                page.evaluate(
                    """() => {
                      document.querySelectorAll('.cdk-overlay-backdrop').forEach(e => {
                        e.classList.remove('cdk-overlay-backdrop-showing');
                        e.style.pointerEvents = 'none';
                      });
                    }"""
                )
            except Exception:
                pass

    def _passo_termos_e_modal_uf(self, page) -> None:
        self._fechar_overlays_soltos(page)
        btn = page.get_by_role(
            "button", name=re.compile(r"Concordar e continuar", re.I)
        )
        if btn.count() == 0:
            btn = page.get_by_role(
                "button", name=re.compile(r"^Continuar$", re.I)
            )
        btn.last.wait_for(state="visible", timeout=self.timeout_ms)
        # botão disabled até campos + termos ok
        try:
            page.wait_for_function(
                """() => {
                  const bs = [...document.querySelectorAll('button')];
                  const b = bs.find(x => /Concordar e continuar/i.test(
                    (x.innerText || '').trim()
                  ));
                  return b && !b.disabled;
                }""",
                timeout=self.timeout_ms,
            )
        except Exception:
            pass
        page.wait_for_timeout(400)
        self._fechar_overlays_soltos(page)
        btn.last.click(force=True)
        self._aguardar_loading(page)
        # Modal: "O licenciamento será feito no estado de ...?"
        modal = page.get_by_text(re.compile(r"licenciamento será feito", re.I))
        try:
            modal.wait_for(timeout=10_000)
            page.get_by_role("button", name=re.compile(r"^Continuar$", re.I)).click(
                force=True
            )
            self._aguardar_loading(page)
        except Exception:
            pass

    def _passo_aguardar_simulacao(self, page) -> None:
        """Espera os CARDS de parcela carregarem — nao so o titulo/skeleton.

        O titulo "Escolha a parcela desejada" aparece antes dos cards, que nascem
        como skeleton (sem texto). So o texto real de parcela ("48x de") conta;
        exige 2 leituras seguidas para nao pegar o instante do primeiro card sair
        do skeleton.

        A espera usa `config.OFERTAS_TIMEOUT_MS`, o mesmo botao do Bradesco
        (`bradesco.py:841`). Antes eram 90s cravados aqui, ignorando a config: em
        dia lento o portal passava disso e o driver desistia com o skeleton ainda
        na tela (sim 20260904-154158, 225s). Orcamento: pior login observado
        (~135s ate `simulacao_enviada`) + 240s = 375s, ainda sob os 420s de
        MOTOR_DRIVER_TIMEOUT_SECONDS.
        """
        timeout = max(self.timeout_ms, config.OFERTAS_TIMEOUT_MS)
        prazo_fim = time.monotonic() + (timeout / 1000.0)
        cards = re.compile(r"\d+\s*x\s*de", re.I)
        # Seleciona a aba Padrao cedo (default) para os cards certos carregarem.
        try:
            page.get_by_role("button", name=re.compile(r"^Padrão$", re.I)).click(
                force=True, timeout=3_000
            )
        except Exception:
            pass
        estavel = 0
        while time.monotonic() < prazo_fim:
            # Erro do portal no passo 2 (banner vermelho).
            if page.get_by_text(re.compile(r"Ocorreu um erro", re.I)).count() > 0:
                detalhe = "ocorreu um erro na simulação do portal"
                try:
                    page.get_by_text(re.compile(r"Saiba mais", re.I)).first.click(
                        force=True, timeout=2_000
                    )
                    page.wait_for_timeout(600)
                    body = (page.inner_text("body") or "")[:500]
                    detalhe = re.sub(r"\s+", " ", body)[:180]
                except Exception:
                    pass
                raise ErroTransitorio("portal_simulacao_erro", detalhe)
            if page.get_by_text(cards).count() > 0:
                estavel += 1
                if estavel >= 2:
                    page.wait_for_timeout(800)  # settle final dos demais cards
                    return
            else:
                estavel = 0
            page.wait_for_timeout(500)
        self._assert_portal_acessivel(page)
        raise ErroTransitorio(
            "portal_falhou",
            "cards de parcela não carregaram a tempo (skeleton)",
        )

    def _salvar_storage(self, browser_ctx, ctx=None) -> None:
        self._salvar_storage_state(browser_ctx, ctx)


def _formatar_nascimento(nasc: str) -> str:
    """Aceita ISO YYYY-MM-DD ou já DD/MM/YYYY."""
    s = (nasc or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return s


def _formatar_moeda_input(valor: float) -> str:
    """Formato BR aproximado para inputs: 21900.00 → 21900,00."""
    return f"{valor:.2f}".replace(".", ",")


def fabrica_santander() -> SantanderDriver:
    from app.motor.playwright_base import browser_headless_padrao

    return SantanderDriver(
        # Padrão headed (Xvfb no Docker) — headless_shell é bloqueado pelo Akamai.
        headless=browser_headless_padrao(),
        screenshot_dir=config.SCREENSHOT_DIR,
        storage_state_path=Path(config.STORAGE_STATE_DIR) / "santander.json",
        timeout_ms=int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        login_url=getattr(config, "SANTANDER_LOGIN_URL", LOGIN_URL_DEFAULT),
    )
