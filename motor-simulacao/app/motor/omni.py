"""Driver real Omni+ (financiamento de motocicletas) — Task Omni 10/09/2026.

Fluxo mapeado ao vivo com `scripts/_diag_omni*.py` (gitignored):
  0. Login: usuario + senha + "Continuar" em `/login`. Sem WAF/captcha em 10/09.
  1. `/app/rodas/visao-geral` -> modal "Nova simulação": Financiamento + PF +
     card "Motocicletas" + select de vendedor (`.select_dropdown_item`) -> Continuar.
  2. `/simulacao/documento`: `app-huge-input` com mascara `000.000.000-00`.
     Se o CPF ja tem proposta em andamento, o portal pergunta: clicar
     "Continuar com a proposta" (reaproveita, nao cria proposta nova a cada rodada).
  3. `/simulacao/geral/telefone`: `input[testid='telephone-input']`.
     Efeito colateral real: o cliente recebe WhatsApp (Open Finance).
  4. `/simulacao/geral/dados-veiculo`: radios plate/zeroKm/manual +
     `[testid='vehicle-plate']`. A placa resolve modelo e cotação.
  5. `/simulacao/geral/valor-veiculo`: `[testid='vehicle-value-input']` com
     mascara de moeda — so aceita digitacao real (teclado) + Tab; `fill` e
     ignorado pelo Angular ("Campo obrigatório").
  6. `/simulacao/resultado-simulacao`: esperar os skeletons sumirem e ler as
     ofertas (`48x de R$ 710,71` ...). **Para aqui: nunca clicar o Continuar
     final** — ele avanca a proposta para a contratação.

Lições aplicadas dos outros drivers: toda escrita lê de volta; espera de oferta
usa `config.OFERTAS_TIMEOUT_MS`; nunca logar usuario, senha, CPF ou celular.
"""
from __future__ import annotations

import os
import re
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

PROVEDOR = "omni"

CONTINUAR = re.compile(r"Continuar com a proposta", re.I)
NOVA_SIMULACAO = re.compile(r"Nova Simula", re.I)
# Recusa de negócio (nenhuma observada até 10/09: o cliente de teste aprovou).
# Se o portal negar, estas frases caem em RejeicaoNegocio em vez de quebrar o parser.
SEM_OFERTA = re.compile(
    r"N[ãa]o h[áa] (oferta|cr[ée]dito)|sem oferta|proposta (recusada|negada|reprovada)|"
    r"cr[ée]dito n[ãa]o aprovado|CPF inv[áa]lido",
    re.I,
)

# Ofertas: "48x de R$ 710,71". O `(?<!\d)` evita casar sufixo de número maior
# (ex.: "70099127" da proposta) e o `de` separa de "12x Entrada mínima".
_RE_PARCELA = re.compile(
    r"(?<!\d)(\d{1,3})\s*x\s*de\s*R\$\s*(\d[\d.]*,\d{2})", re.IGNORECASE
)
_RE_MOEDA = re.compile(r"R\$\s*([\d.]+,\d{2})")
_RE_RESUMO = re.compile(
    r"(Valor|Financiado|Entrada)\s*:\s*R\$\s*([\d.]+,\d{2})", re.IGNORECASE
)

JS_TEM_RESPOSTA = (
    "() => /"
    + SEM_OFERTA.pattern
    + "|(\\d{1,3}\\s*x\\s*de\\s*R\\$)/i.test(document.body.innerText)"
)


def parse_moeda_br(texto: str) -> Decimal:
    """'1.212,76' ou 'R$ 1.212,76' -> Decimal('1212.76')."""
    s = re.sub(r"[R$\s]", "", (texto or "").strip(), flags=re.IGNORECASE)
    s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"moeda inválida: {texto!r}") from exc


def parse_ofertas(texto: str) -> list[tuple[int, Decimal]]:
    """Extrai (prazo, parcela) do painel de resultado, sem repetir prazo."""
    vistos: dict[int, Decimal] = {}
    for prazo_raw, parcela_raw in _RE_PARCELA.findall(texto or ""):
        try:
            prazo = int(prazo_raw)
            parcela = parse_moeda_br(parcela_raw)
        except (ValueError, InvalidOperation):
            continue
        # Prazo de financiamento de moto: 6 a 60. Fora disso é outro número.
        if not 6 <= prazo <= 60:
            continue
        vistos.setdefault(prazo, parcela)
    return sorted(vistos.items())


def parse_resumo(texto: str) -> dict[str, Decimal]:
    """Lê Valor/Financiado/Entrada do rodapé do resultado ("Entrada: R$ 5.760,00")."""
    achados: dict[str, Decimal] = {}
    for rotulo, valor_raw in _RE_RESUMO.findall(texto or ""):
        try:
            achados.setdefault(rotulo.lower(), parse_moeda_br(valor_raw))
        except ValueError:
            continue
    return achados


_RE_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b")
_RE_FONE = re.compile(r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}|\b\d{10,11}\b")


def _resumo_painel(texto: str, limite: int = 600) -> str:
    """Painel em uma linha, sem CPF/telefone, para mensagem de erro."""
    achatado = " ".join((texto or "").split())
    achatado = _RE_CPF.sub("<cpf>", achatado)
    return _RE_FONE.sub("<fone>", achatado)[:limite]


def _formatar_cpf(cpf: str) -> str:
    """Só dígitos -> '000.000.000-00' (a máscara do portal exige)."""
    d = re.sub(r"\D", "", cpf or "")
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return cpf


def _formatar_fone(fone: str) -> str:
    d = re.sub(r"\D", "", fone or "")
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return fone


class OmniDriver(PlaywrightBankDriver):
    """Robô do portal Omni+ (simulação de financiamento de motocicleta)."""

    provedor = PROVEDOR
    real = True
    # Sem WAF/Akamai nem captcha no login em 10/09: contexto vanilla.
    stealth = False

    def __init__(
        self,
        *,
        headless: bool | None = None,
        storage_state_path: str | Path | None = None,
        screenshot_dir: str | Path | None = None,
        timeout_ms: int | None = None,
        login_url: str | None = None,
        visao_url: str | None = None,
        vendedor: str | None = None,
        html_simulacao: str | None = None,
    ):
        super().__init__(
            headless=headless,
            storage_state_path=storage_state_path,
            screenshot_dir=screenshot_dir or getattr(config, "SCREENSHOT_DIR", None),
            timeout_ms=timeout_ms
            if timeout_ms is not None
            else int(getattr(config, "BROWSER_TIMEOUT_MS", 90_000)),
        )
        self.login_url = login_url or getattr(config, "OMNI_LOGIN_URL", "")
        self.visao_url = visao_url or getattr(config, "OMNI_VISAO_URL", "")
        self.vendedor = (
            vendedor
            if vendedor is not None
            else getattr(config, "OMNI_VENDEDOR", "")
        )
        self.html_simulacao = html_simulacao

    # --- entrada -----------------------------------------------------------

    def simular(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        self._validar_solicitacao(sol)
        html = self.html_simulacao
        if html is None:
            fixture = (os.getenv("MOTOR_OMNI_FIXTURE_HTML") or "").strip()
            if fixture and Path(fixture).is_file():
                html = Path(fixture).read_text(encoding="utf-8")
        if html is not None:
            return self._resultados_de_texto(html, sol)
        return self._simular_playwright(sol, ctx)

    def _validar_solicitacao(self, sol: SolicitacaoSimulacao) -> None:
        if not sol.pessoa.cpf:
            raise RejeicaoNegocio("dados_cliente", "CPF é obrigatório")
        if not sol.pessoa.celular:
            raise RejeicaoNegocio(
                "celular_obrigatorio", "Celular é obrigatório na Omni"
            )
        if not sol.veiculo.placa:
            raise RejeicaoNegocio(
                "placa_obrigatoria",
                "Placa é obrigatória: a Omni resolve o veículo por ela",
            )
        if sol.veiculo.valor is None:
            raise RejeicaoNegocio("valor_obrigatorio", "Valor de venda é obrigatório")

    def _resultados_de_texto(
        self, texto: str, sol: SolicitacaoSimulacao
    ) -> list[ResultadoDriver]:
        if SEM_OFERTA.search(texto or "") and not parse_ofertas(texto):
            raise RejeicaoNegocio(
                "omni_sem_oferta", "Omni não ofertou crédito para este cliente"
            )
        ofertas = parse_ofertas(texto)
        if not ofertas:
            # Painel sem recusa e sem parcela legível não é decisão de crédito:
            # é o parser não entendendo a tela.
            raise IntervencaoNecessaria(
                "ofertas_ilegiveis",
                f"painel sem recusa e sem parcela legível: {_resumo_painel(texto)}",
            )
        pedidos = set(sol.condicoes.prazos_meses or [])
        resumo = parse_resumo(texto)
        # O portal pode trocar o valor pelo cotação: o que vale é a tela.
        entrada = resumo.get("entrada", Decimal(str(sol.condicoes.entrada or 0)))
        financiado = resumo.get("financiado")
        if financiado is None:
            valor = resumo.get("valor", Decimal(str(sol.veiculo.valor or 0)))
            financiado = max(valor - entrada, Decimal("0"))
        resultados = [
            ResultadoDriver(
                provedor=PROVEDOR,
                status="concluida",
                valor_parcela=parcela,
                taxa_am=None,
                prazo_meses=prazo,
                valor_financiado=financiado,
                entrada=entrada,
            )
            for prazo, parcela in ofertas
            if not pedidos or prazo in pedidos
        ]
        if not resultados:
            raise RejeicaoNegocio(
                "omni_prazo_indisponivel",
                f"portal ofertou {[p for p, _ in ofertas]}, pedimos {sorted(pedidos)}",
            )
        return resultados

    # --- live ---------------------------------------------------------------

    def _simular_playwright(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None
    ) -> list[ResultadoDriver]:
        from playwright.sync_api import sync_playwright

        usuario, senha = self._credencial(ctx)
        with sync_playwright() as p:
            browser = self._launch_browser(p)
            browser_ctx = self._new_context(browser, ctx)
            page = browser_ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                self._passo_login(page, usuario, senha, ctx)
                self._passo_nova_simulacao(page, ctx)
                self._passo_documento(page, sol, ctx)
                self._passo_telefone(page, sol, ctx)
                self._passo_veiculo(page, sol, ctx)
                self._passo_valor(page, sol, ctx)
                self._passo_entrada(page, sol, ctx)
                texto = self._passo_ler_ofertas(page, ctx)
            except (RejeicaoNegocio, IntervencaoNecessaria, ErroTransitorio):
                self._screenshot_falha(page, "omni_falha")
                raise
            finally:
                try:
                    browser_ctx.close()
                    browser.close()
                except Exception:
                    pass
        return self._resultados_de_texto(texto, sol)

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
                "cadastre usuário/senha da Omni em Acessos bancos (Portal)",
            )
        return segredo

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
            screenshot_path,
            screenshot_conteudo=screenshot_conteudo,
        )

    def _clicar_continuar(self, page, timeout_ms: int = 15_000) -> None:
        page.locator("omni-button:has-text('Continuar') button").last.click(
            timeout=timeout_ms
        )

    # --- passos --------------------------------------------------------------

    def _passo_login(self, page, usuario: str, senha: str, ctx) -> None:
        page.goto(self.login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(4_000)
        self._assert_portal_acessivel(page)
        if "/app/" in (page.url or ""):
            # Sessão quente: o portal já autenticou pelo storage_state.
            self._evento(ctx, "login_pulado", "Sessão quente Omni reaproveitada.", page)
            return
        page.get_by_role("textbox").first.fill(usuario)
        page.locator("input[type='password']").first.fill(senha)
        # Toda escrita lê de volta antes de avançar.
        if page.get_by_role("textbox").first.input_value() != usuario:
            raise IntervencaoNecessaria(
                "campo_nao_encontrado", "campo Usuário não aceitou digitação na Omni"
            )
        self._clicar_continuar(page)
        page.wait_for_timeout(6_000)
        if "/app/" not in (page.url or ""):
            corpo = (page.evaluate("() => document.body.innerText || ''") or "")[:500]
            if re.search(r"usuário|senha|inválid|incorret|bloque", corpo, re.I):
                raise IntervencaoNecessaria(
                    "login_recusado",
                    "Omni recusou usuário/senha. Pare: nova tentativa pode "
                    "desativar o login.",
                )
            raise ErroTransitorio(
                "login_nao_confirmado", "Omni não saiu da tela de login"
            )
        self._evento(ctx, "login_confirmado", "Sessão da Omni aberta.", page)
        try:
            self._salvar_storage_state(page.context, ctx)
        except Exception:
            pass

    def _passo_nova_simulacao(self, page, ctx) -> None:
        page.get_by_text(NOVA_SIMULACAO).first.click()
        page.wait_for_timeout(3_000)
        page.get_by_text("Motocicletas", exact=True).first.click()
        page.wait_for_timeout(800)
        page.locator("omni-select input[readonly]").first.click()
        page.wait_for_timeout(2_000)
        itens = page.locator(".select_dropdown_item").all()
        if not itens:
            raise self._falha_campo("vendedor")
        alvo = (self.vendedor or "").strip().lower()
        escolhido = None
        for item in itens:
            try:
                texto = (item.inner_text() or "").strip()
            except Exception:
                continue
            if texto and (not alvo or alvo in texto.lower()):
                escolhido = item
                break
        (escolhido or itens[0]).click()
        page.wait_for_timeout(1_000)
        self._clicar_continuar(page)
        page.wait_for_timeout(6_000)
        self._evento(ctx, "modal_aberto", "Nova simulação Omni iniciada.", page)

    def _passo_documento(self, page, sol, ctx) -> None:
        page.locator("app-huge-input .app-huge-input__web input").first.fill(
            _formatar_cpf(sol.pessoa.cpf)
        )
        page.wait_for_timeout(800)
        campo = page.locator("app-huge-input .app-huge-input__web input").first
        lido = re.sub(r"\D", "", campo.input_value() or "")
        if lido != re.sub(r"\D", "", sol.pessoa.cpf or ""):
            raise IntervencaoNecessaria(
                "campo_nao_encontrado", "campo CPF não aceitou digitação na Omni"
            )
        self._clicar_continuar(page)
        # Aguarda telefone, veículo, valor ou resultado — ou o dialog de
        # proposta em andamento ("Continuar com a proposta").
        for _ in range(25):
            page.wait_for_timeout(1_000)
            try:
                dlg = page.get_by_text(CONTINUAR).first
                if dlg.count() and dlg.is_visible():
                    dlg.click()
                    page.wait_for_timeout(4_000)
                    continue
            except Exception:
                pass
            try:
                if page.locator("input[testid='telephone-input']").count():
                    break
            except Exception:
                pass
            url = page.url or ""
            if "dados-veiculo" in url or "valor-veiculo" in url or "resultado" in url:
                break
        self._evento(ctx, "documento_ok", "CPF Omni aceito.", page)

    def _passo_telefone(self, page, sol, ctx) -> None:
        url = page.url or ""
        if "dados-veiculo" in url or "valor-veiculo" in url or "resultado" in url:
            # Proposta retomada já tem telefone.
            return
        page.locator("input[testid='telephone-input']").first.fill(
            _formatar_fone(sol.pessoa.celular or "")
        )
        page.wait_for_timeout(800)
        self._clicar_continuar(page)
        page.wait_for_timeout(8_000)
        self._evento(ctx, "telefone_ok", "Telefone Omni informado.", page)

    def _passo_veiculo(self, page, sol, ctx) -> None:
        url = page.url or ""
        if "valor-veiculo" in url or "resultado" in url:
            return
        page.locator("[testid='vehicle-plate'] input, [testid='vehicle-plate']").first.fill(
            (sol.veiculo.placa or "").upper()
        )
        page.wait_for_timeout(2_000)
        page.locator("[testid='continue-simulation']").first.click()
        page.wait_for_timeout(8_000)
        if "valor-veiculo" not in (page.url or "") and "resultado" not in (
            page.url or ""
        ):
            raise IntervencaoNecessaria(
                "placa_nao_resolvida",
                "Omni não resolveu o veículo pela placa",
            )
        self._evento(ctx, "veiculo_ok", "Veículo Omni resolvido pela placa.", page)

    def _passo_valor(self, page, sol, ctx) -> None:
        if "resultado" in (page.url or ""):
            return
        campo = page.locator(
            "[testid='vehicle-value-input'] input, [testid='vehicle-value-input']"
        ).first
        # A máscara de moeda ignora `fill`: digita dígitos + Tab.
        campo.click()
        page.wait_for_timeout(500)
        digitos = str(int(round(float(sol.veiculo.valor or 0) * 100)))
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.press("Backspace")
        for d in digitos:
            page.keyboard.type(d, delay=60)
        page.wait_for_timeout(800)
        page.keyboard.press("Tab")
        page.wait_for_timeout(1_000)
        if not (campo.input_value() or "").strip():
            raise IntervencaoNecessaria(
                "campo_nao_encontrado", "campo valor de venda não aceitou digitação"
            )
        page.locator("[testid='continue-simulation']").first.click()
        page.wait_for_timeout(8_000)
        if "resultado" not in (page.url or ""):
            raise ErroTransitorio(
                "valor_nao_confirmado", "Omni não avançou ao resultado"
            )
        self._evento(ctx, "valor_ok", "Valor de venda Omni confirmado.", page)

    def _passo_entrada(self, page, sol, ctx) -> None:
        # O portal escolhe 30% por padrão; só mexe quando o pedido exige entrada.
        entrada = float(sol.condicoes.entrada or 0)
        if entrada <= 0:
            return
        try:
            campo = page.locator(
                "[testid='down-payment-input'] input, [testid='down-payment-input']"
            ).first
            if not campo.is_enabled():
                return
            campo.click()
            page.wait_for_timeout(500)
            page.keyboard.press("ControlOrMeta+a")
            page.keyboard.press("Backspace")
            for d in str(int(round(entrada * 100))):
                page.keyboard.type(d, delay=60)
            page.wait_for_timeout(800)
            page.keyboard.press("Tab")
            page.wait_for_timeout(8_000)
            self._evento(ctx, "entrada_ok", "Entrada Omni ajustada.", page)
        except Exception:
            # Entrada indisponível: segue com o padrão do portal.
            return

    def _passo_ler_ofertas(self, page, ctx) -> str:
        # As ofertas chegam via AJAX: espera os skeletons sumirem.
        orcamento = int(getattr(config, "OFERTAS_TIMEOUT_MS", 240_000))
        insistencias = max(10, orcamento // 1_000)
        for _ in range(insistencias):
            page.wait_for_timeout(1_000)
            try:
                if page.locator(".omni-skeleton").count() == 0:
                    break
            except Exception:
                break
        page.wait_for_timeout(2_000)
        texto = page.evaluate("() => document.body.innerText || ''") or ""
        self._evento(ctx, "ofertas_lidas", "Resultado Omni lido.", page,
                     capturar_print=True)
        # Para aqui: o Continuar desta tela avança para a contratação.
        return texto


def fabrica_omni(**kwargs) -> OmniDriver:
    return OmniDriver(**kwargs)
