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

# Cards: "48x de R$ 946,28" (com ou sem quebra de linha)
_RE_PARCELA = re.compile(
    r"(\d+)\s*x\s*de\s*R\$\s*([\d.]+,\d{2})",
    re.IGNORECASE,
)
_RE_VALOR_LIBERADO = re.compile(
    r"Valor liberado.*?R\$\s*([\d.]+,\d{2})",
    re.IGNORECASE | re.DOTALL,
)


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
    """Extrai (prazo_meses, parcela) de HTML/texto da tela de simulação."""
    vistos: dict[int, Decimal] = {}
    for m in _RE_PARCELA.finditer(texto or ""):
        prazo = int(m.group(1))
        parcela = parse_moeda_br(m.group(2))
        # mantém a primeira ocorrência de cada prazo
        vistos.setdefault(prazo, parcela)
    return sorted(vistos.items(), key=lambda x: x[0])


def parse_valor_liberado(texto: str) -> Decimal | None:
    m = _RE_VALOR_LIBERADO.search(texto or "")
    if not m:
        return None
    return parse_moeda_br(m.group(1))


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
        headless: bool = True,
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
        financiado = parse_valor_liberado(html)
        if financiado is None and sol.veiculo.valor is not None:
            financiado = Decimal(str(max(sol.veiculo.valor - sol.condicoes.entrada, 0)))
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

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context_kwargs: dict = {}
            if self.storage_state_path and self.storage_state_path.is_file():
                context_kwargs["storage_state"] = str(self.storage_state_path)
            browser_ctx = browser.new_context(**context_kwargs)
            page = browser_ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                self._passo_login(page, cpf_lojista, senha)
                self._passo_cliente_veiculo(page, sol)
                self._passo_termos_e_modal_uf(page)
                html = self._passo_aguardar_simulacao(page)
                if sol.condicoes.entrada:
                    self._ajustar_entrada(page, sol.condicoes.entrada)
                    html = page.content()
                resultados = self._resultados_de_html(html, sol)
                self._salvar_storage(browser_ctx)
                return resultados
            except (RejeicaoNegocio, IntervencaoNecessaria, ErroTransitorio):
                self._screenshot_falha(page, "erro")
                raise
            except Exception as exc:
                self._screenshot_falha(page, "inesperado")
                raise ErroTransitorio(
                    "portal_falhou", f"falha no portal Santander: {type(exc).__name__}"
                ) from exc
            finally:
                browser_ctx.close()
                browser.close()

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
        page.goto(self.login_url, wait_until="domcontentloaded")
        # Placeholders da tela de login
        page.get_by_placeholder(re.compile("CPF", re.I)).fill(cpf_lojista)
        page.get_by_placeholder(re.compile("senha", re.I)).fill(senha)
        page.get_by_role("button", name=re.compile("Entrar", re.I)).click()
        # Pós-login: menu ou passo 1
        page.get_by_text(re.compile("Informações básicas|Cliente", re.I)).first.wait_for(
            timeout=self.timeout_ms
        )

    def _passo_cliente_veiculo(self, page, sol: SolicitacaoSimulacao) -> None:
        # CPF / nascimento
        page.get_by_placeholder(re.compile("CPF ou CNPJ", re.I)).fill(sol.pessoa.cpf)
        nasc = _formatar_nascimento(sol.pessoa.nascimento)
        page.get_by_placeholder(re.compile("00/00/0000|nascimento", re.I)).fill(nasc)
        # CNH
        if sol.pessoa.cnh is False:
            page.get_by_text("Não", exact=True).click()
        else:
            page.get_by_text("Sim", exact=True).first.click()
        # Placa
        page.get_by_text(re.compile("Busca por placa", re.I)).click()
        placa = (sol.veiculo.placa or "").replace("-", "").upper()
        page.get_by_placeholder(re.compile("Placa", re.I)).fill(placa)
        # Aguarda FIPE / marca
        page.get_by_text(re.compile("Marca|Modelo|FIPE", re.I)).first.wait_for(
            timeout=self.timeout_ms
        )
        # Valor do veículo
        if sol.veiculo.valor is not None:
            valor_fmt = _formatar_moeda_input(sol.veiculo.valor)
            # campo "Valor" / "Valor do veículo"
            try:
                page.get_by_label(re.compile("Valor", re.I)).fill(valor_fmt)
            except Exception:
                page.locator('input[placeholder*="Valor" i]').first.fill(valor_fmt)
        # Finalidade
        fin = (sol.veiculo.finalidade or "comum").lower()
        if fin == "pcd":
            page.get_by_text("PCD", exact=True).click()
        else:
            page.get_by_text("Comum", exact=True).click()
        # UF — se o seletor existir
        uf_label = uf_para_portal(sol.veiculo.uf_licenciamento)
        try:
            page.get_by_text(re.compile("Licenciamento", re.I)).click()
            page.get_by_text(uf_label, exact=False).first.click()
        except Exception:
            pass  # UF já pode vir preenchida pela placa

    def _passo_termos_e_modal_uf(self, page) -> None:
        btn = page.get_by_role("button", name=re.compile("Concordar e continuar", re.I))
        btn.wait_for(state="visible", timeout=self.timeout_ms)
        # botão pode começar disabled até valor OK
        page.wait_for_timeout(500)
        btn.click()
        # Modal: "O licenciamento será feito no estado de ...?"
        modal = page.get_by_text(re.compile("licenciamento será feito", re.I))
        try:
            modal.wait_for(timeout=10_000)
            page.get_by_role("button", name=re.compile("^Continuar$", re.I)).click()
        except Exception:
            pass  # alguns fluxos não mostram modal

    def _passo_aguardar_simulacao(self, page) -> str:
        """AGORA ESPERA — tela de parcelas pode demorar a montar."""
        page.get_by_text(re.compile("Escolha a parcela desejada", re.I)).wait_for(
            timeout=max(self.timeout_ms, 60_000)
        )
        # preferir aba Padrão
        try:
            page.get_by_role("button", name=re.compile("^Padrão$", re.I)).click()
        except Exception:
            pass
        return page.content()

    def _ajustar_entrada(self, page, entrada: float) -> None:
        try:
            page.get_by_label(re.compile("^Entrada$", re.I)).fill(
                _formatar_moeda_input(entrada)
            )
            page.wait_for_timeout(800)
        except Exception:
            pass

    def _salvar_storage(self, browser_ctx) -> None:
        if not self.storage_state_path:
            return
        try:
            self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            browser_ctx.storage_state(path=str(self.storage_state_path))
        except Exception:
            pass


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
    return SantanderDriver(
        headless=os.getenv("MOTOR_BROWSER_HEADLESS", "1") != "0",
        screenshot_dir=config.SCREENSHOT_DIR,
        storage_state_path=Path(config.STORAGE_STATE_DIR) / "santander.json",
        timeout_ms=int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        login_url=getattr(config, "SANTANDER_LOGIN_URL", LOGIN_URL_DEFAULT),
    )
