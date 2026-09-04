"""Driver real Motrix (plataforma joinbank).

Fluxo mapeado no portal em 04/09/2026 com `scripts/_diag_motrix.py`:
  0. Login: usuario (CPF do operador) + senha em `#accessId` / `#password`,
     botao "Login" — nao "Entrar".
  1. `/loan-simulations/menu` -> card "Simulacao de Financiamento Veicular"
     (produto 950009). E o unico card da loja.
  2. Passo 1/4 "Consulta CPF": CPF -> "Validar CPF" -> o portal responde
     "Cliente elegivel a simulacao" e SO ENTAO revela o campo Celular -> "Proximo".
  3. Passo 2/4 "Simulacao de Proposta": modal com Tipo do veiculo, Placa, Chassi,
     Marca/Modelo/Versao/Ano, UF, Renavam, entrada e valor de venda -> "Simular".
  4. Le as ofertas. **Para aqui.**

Por que nao e driver de API. O portal e um SPA sobre `api-joinbank.ukam.io/v3`, com
`POST /v3/auth/sign-in` devolvendo bearer token de ~24h. Tentador, mas cada chamada
carrega tambem um header `x-version-<sufixo>` no formato `<timestamp>.<sha256>`,
assinado pelo JS da pagina. Sem ele a API responde 401 — testado em 04/09 com o
token valido em seis formatos de Authorization. Reproduzir a assinatura seria
contornar controle anti-automacao e quebraria a cada build deles. Fica Playwright.

Duas armadilhas que custaram rodada:

- **Placa so existe com "Tipo do veiculo = Usado".** Em "Novo" (o padrao) o campo
  nem e renderizado, porque moto zero nao tem placa. Preencher a placa exige
  trocar o tipo primeiro.
- **`mat-input-N` nao e seletor.** O id do Angular Material e sequencial por
  sessao: o CPF nasce `mat-input-0` e vira `mat-input-1` depois que o campo Celular
  aparece. Tudo aqui ancora no rotulo visivel do `mat-form-field`.

O driver **nunca** avanca para os passos 3 (Confirmacao) e 4 (Formalizacao): o 4
dispara link de formalizacao para o cliente, e simular nao e contratar.

Nunca logar usuario, senha ou CPF.
"""
from __future__ import annotations

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

PROVEDOR = "motrix"

PRODUTO_CARD = re.compile(r"Simula[çc][ãa]o de Financiamento Veicular", re.I)
ELEGIVEL = re.compile(r"Cliente eleg[íi]vel", re.I)
# Recusa de negocio, nao erro: o portal responde isso dentro do proprio modal.
SEM_OFERTA = re.compile(r"N[ãa]o h[áa] oferta de cr[ée]dito", re.I)
CPF_INVALIDO = re.compile(r"CPF\s+(inv[áa]lido|n[ãa]o\s+encontrado)", re.I)

# Ofertas: "24x R$ 1.212,76" / "24 x 1.212,76". O "R$" as vezes vem em outra tag.
# O `(?<!\d)` nao e enfeite: sem ele o regex casa o SUFIXO de um numero maior, e
# "2021 x" (ano modelo) virava prazo 21, "950009 x" (codigo do produto) virava 9.
_RE_PARCELA = re.compile(
    r"(?<!\d)(\d{1,3})\s*x\b[^0-9]{0,20}?(?:R\$\s*)?(\d[\d.]*,\d{2})", re.IGNORECASE
)
_RE_TAXA = re.compile(r"(\d{1,2},\d{2})\s*%\s*a\.?\s*m", re.IGNORECASE)

# Acha o input/select pelo rotulo do mat-form-field. Devolve um id estavel que a
# gente mesmo carimba, porque mat-input-N muda de numero entre os passos.
_POR_ROTULO = """([rotulo, tipo]) => {
  const campos = [...document.querySelectorAll('mat-form-field, .mat-mdc-form-field')];
  for (const f of campos) {
    const t = (f.innerText || '').trim().toLowerCase();
    if (!t.includes(rotulo.toLowerCase())) continue;
    const alvo = tipo === 'select'
      ? f.querySelector('mat-select, [role=combobox]')
      : f.querySelector('input, textarea');
    if (alvo) {
      if (!alvo.id) alvo.id = 'motrix-' + Math.random().toString(36).slice(2, 8);
      return alvo.id;
    }
  }
  return null;
}"""


def parse_moeda_br(texto: str) -> Decimal:
    """'1.097,45' ou 'R$ 1.097,45' -> Decimal('1097.45')."""
    s = re.sub(r"[R$\s]", "", (texto or "").strip(), flags=re.IGNORECASE)
    s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"moeda inválida: {texto!r}") from exc


def parse_ofertas(texto: str) -> list[tuple[int, Decimal]]:
    """Extrai (prazo, parcela) do painel de ofertas, sem repetir prazo."""
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


def parse_taxa(texto: str) -> Decimal | None:
    achado = _RE_TAXA.search(texto or "")
    if not achado:
        return None
    try:
        return parse_moeda_br(achado.group(1))
    except ValueError:
        return None


def _formatar_moeda_input(valor: float) -> str:
    """21900.0 -> '21.900,00' (o campo tem máscara e recusa ponto decimal)."""
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


class MotrixDriver(PlaywrightBankDriver):
    """Robô do portal Motrix (simulação de financiamento veicular)."""

    provedor = PROVEDOR
    real = True
    # Sem reCAPTCHA e sem Akamai na tela de login (conferido em 04/09: zero
    # iframes, nenhum pixel de bot manager). Ainda assim contexto vanilla, que é
    # o que o recon usou e o que passou.
    stealth = False

    def __init__(
        self,
        *,
        headless: bool | None = None,
        storage_state_path: str | Path | None = None,
        screenshot_dir: str | Path | None = None,
        timeout_ms: int | None = None,
        login_url: str | None = None,
        menu_url: str | None = None,
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
        self.login_url = login_url or getattr(config, "MOTRIX_LOGIN_URL", "")
        self.menu_url = menu_url or getattr(config, "MOTRIX_MENU_URL", "")
        self.html_simulacao = html_simulacao

    # --- entrada ------------------------------------------------------------

    def simular(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        self._validar_solicitacao(sol)
        html = self.html_simulacao
        if html is None:
            import os

            fixture = (os.getenv("MOTOR_MOTRIX_FIXTURE_HTML") or "").strip()
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
                "celular_obrigatorio", "Celular é obrigatório no Motrix"
            )
        if not sol.veiculo.placa:
            raise RejeicaoNegocio(
                "placa_obrigatoria",
                "Placa é obrigatória: o Motrix resolve o veículo por ela",
            )
        if sol.veiculo.valor is None:
            raise RejeicaoNegocio("valor_obrigatorio", "Valor de venda é obrigatório")

    def _resultados_de_texto(
        self, texto: str, sol: SolicitacaoSimulacao
    ) -> list[ResultadoDriver]:
        if SEM_OFERTA.search(texto):
            raise RejeicaoNegocio(
                "motrix_sem_oferta", "Motrix não ofertou crédito para este cliente"
            )
        ofertas = parse_ofertas(texto)
        if not ofertas:
            raise RejeicaoNegocio("motrix_sem_oferta", "nenhuma parcela lida na tela")

        pedidos = set(sol.condicoes.prazos_meses or [])
        taxa = parse_taxa(texto)
        entrada = Decimal(str(sol.condicoes.entrada or 0))
        valor = Decimal(str(sol.veiculo.valor or 0))
        financiado = max(valor - entrada, Decimal("0"))

        resultados = [
            ResultadoDriver(
                provedor=PROVEDOR,
                status="concluida",
                valor_parcela=parcela,
                taxa_am=taxa,
                prazo_meses=prazo,
                valor_financiado=financiado,
                entrada=entrada,
            )
            for prazo, parcela in ofertas
            if not pedidos or prazo in pedidos
        ]
        if not resultados:
            raise RejeicaoNegocio(
                "motrix_prazo_indisponivel",
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
                self._passo_login(page, usuario, senha)
                self._evento(ctx, "login_confirmado", "Sessão do Motrix aberta.", page)
                self._salvar_storage_state(browser_ctx, ctx)

                self._passo_abrir_produto(page)
                self._evento(ctx, "produto_aberto", "Wizard de simulação aberto.", page)

                self._passo_consulta_cpf(page, sol, ctx)
                self._passo_veiculo(page, sol, ctx)
                texto = self._passo_ler_ofertas(page, ctx)
            except (RejeicaoNegocio, IntervencaoNecessaria, ErroTransitorio):
                self._screenshot_falha(page, "motrix_falha")
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
                "cadastre usuário/senha do Motrix em Acessos bancos (Portal)",
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
            screenshot_path=screenshot_path,
            screenshot_conteudo=screenshot_conteudo,
        )

    # --- passos -------------------------------------------------------------

    def _campo(self, page, rotulo: str, tipo: str = "input"):
        """Locator ancorado no rótulo visível; None se o campo não está na tela."""
        ident = page.evaluate(_POR_ROTULO, [rotulo, tipo])
        return page.locator(f"#{ident}").first if ident else None

    def _preencher(self, page, rotulo: str, valor: str, *, digitos: bool = False):
        """Preenche e relê. Campo com máscara come dígito e o erro só aparece 3
        passos depois — por isso a leitura de volta é obrigatória, não opcional."""
        campo = self._campo(page, rotulo)
        if campo is None:
            raise self._falha_campo(rotulo)
        campo.fill(valor)
        lido = campo.input_value()
        if digitos:
            esperado = "".join(c for c in valor if c.isdigit())
            obtido = "".join(c for c in lido if c.isdigit())
        else:
            esperado, obtido = valor.strip(), lido.strip()
        if obtido != esperado:
            raise ErroTransitorio(
                "campo_nao_aceito",
                f"campo {rotulo!r} recebeu {len(esperado)} e devolveu {len(obtido)}",
            )
        return campo

    def _passo_login(self, page, usuario: str, senha: str) -> None:
        page.goto(self.login_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        page.wait_for_timeout(3_000)
        self._assert_portal_acessivel(page)

        # Sessão quente cai direto no dashboard; gastar login à toa é o que
        # desativou o acesso do BV em 04/09.
        if "sign-in" not in page.url:
            self._aguardar_spa(page)
            return

        page.fill("#accessId", usuario)
        if page.input_value("#accessId").strip() != usuario:
            raise ErroTransitorio("campo_nao_aceito", "campo de usuário não reteve o valor")
        page.fill("#password", senha)
        if len(page.input_value("#password")) != len(senha):
            raise ErroTransitorio("campo_nao_aceito", "campo de senha não reteve o valor")

        # O botão diz "Login" e não tem type=submit; procurar "Entrar" só gera
        # timeout num botão que nunca existiu.
        page.get_by_role("button", name="Login", exact=True).first.click()
        page.wait_for_timeout(10_000)

        if "sign-in" in page.url:
            texto = page.inner_text("body")[:2_000]
            raise IntervencaoNecessaria(
                "credencial_invalida",
                "Motrix recusou o login"
                + (" (usuário ou senha)" if "inválid" in texto.lower() else ""),
            )
        self._aguardar_spa(page)

    def _aguardar_spa(self, page) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            page.wait_for_timeout(2_000)

    def _passo_abrir_produto(self, page) -> None:
        page.goto(self.menu_url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        page.wait_for_timeout(4_000)
        card = page.get_by_text(PRODUTO_CARD).first
        if not card.count():
            raise ErroTransitorio(
                "produto_indisponivel",
                "card 'Simulação de Financiamento Veicular' não apareceu no menu",
            )
        card.click()
        page.wait_for_timeout(6_000)

    def _passo_consulta_cpf(
        self, page, sol: SolicitacaoSimulacao, ctx: DriverContext | None
    ) -> None:
        cpf = "".join(c for c in sol.pessoa.cpf if c.isdigit())
        self._preencher(page, "cpf", cpf, digitos=True)

        validar = page.get_by_role("button", name=re.compile(r"Validar CPF", re.I)).first
        self._aguardar_habilitado(validar, "validar_cpf")
        validar.click()

        # A consulta bate em Receita/bureaus/SCR e demora. Sem elegibilidade o
        # campo Celular nem é renderizado.
        prazo = int(getattr(config, "OFERTAS_TIMEOUT_MS", 240_000))
        try:
            page.wait_for_function(
                "() => /Cliente eleg[íi]vel|N[ãa]o h[áa] oferta|CPF inv[áa]lido/i"
                ".test(document.body.innerText)",
                timeout=min(prazo, 120_000),
            )
        except Exception as exc:
            raise ErroTransitorio(
                "consulta_cpf_sem_resposta",
                "portal não respondeu à validação do CPF",
            ) from exc

        corpo = page.inner_text("body")
        if CPF_INVALIDO.search(corpo):
            raise RejeicaoNegocio("cpf_invalido", "Motrix não aceitou o CPF")
        if SEM_OFERTA.search(corpo):
            raise RejeicaoNegocio(
                "motrix_sem_oferta", "Motrix não ofertou crédito para este cliente"
            )
        if not ELEGIVEL.search(corpo):
            raise ErroTransitorio(
                "elegibilidade_indefinida", "portal não confirmou a elegibilidade"
            )
        self._evento(ctx, "cliente_elegivel", "Motrix aceitou o CPF do cliente.", page)

        celular = "".join(c for c in (sol.pessoa.celular or "") if c.isdigit())
        self._preencher(page, "celular", celular, digitos=True)

        proximo = page.get_by_role("button", name=re.compile(r"Pr[óo]ximo", re.I)).first
        self._aguardar_habilitado(proximo, "proximo_passo1")
        proximo.click()
        page.wait_for_timeout(8_000)

    def _passo_veiculo(
        self, page, sol: SolicitacaoSimulacao, ctx: DriverContext | None
    ) -> None:
        # O modal já vem aberto ao entrar no passo 2; se não, "Adicionar Simulação".
        if self._campo(page, "tipo do ve", "select") is None:
            adicionar = page.get_by_role(
                "button", name=re.compile(r"Adicionar Simula", re.I)
            ).first
            if adicionar.count():
                adicionar.click()
                page.wait_for_timeout(5_000)

        tipo = self._campo(page, "tipo do ve", "select")
        if tipo is None:
            raise self._falha_campo("tipo do veículo")
        # Placa só existe em "Usado" — em "Novo" o campo nem é renderizado.
        tipo.click()
        page.wait_for_timeout(1_500)
        page.get_by_role("option", name="Usado", exact=True).first.click()
        page.wait_for_timeout(4_000)

        placa = (sol.veiculo.placa or "").strip().upper().replace("-", "")
        self._preencher(page, "placa", placa)

        page.get_by_role("button", name=re.compile(r"^Buscar$", re.I)).first.click()
        # A consulta de placa preenche Marca/Modelo/Versão/Ano; sem ela o Simular
        # não habilita e o driver morreria num passo inocente lá na frente.
        try:
            page.wait_for_function(
                "() => /Dados do ve[íi]culo obtidos na consulta/i.test(document.body.innerText)",
                timeout=60_000,
            )
        except Exception as exc:
            raise ErroTransitorio(
                "placa_nao_resolvida",
                f"Motrix não resolveu o veículo pela placa {placa}",
            ) from exc
        self._evento(ctx, "veiculo_resolvido", f"Placa {placa} resolvida.", page)

        if sol.veiculo.uf_licenciamento:
            uf = self._campo(page, "uf do licenciamento", "select")
            if uf is not None:
                uf.click()
                page.wait_for_timeout(1_000)
                opcao = page.get_by_role(
                    "option", name=sol.veiculo.uf_licenciamento.upper(), exact=True
                ).first
                if opcao.count():
                    opcao.click()
                    page.wait_for_timeout(1_000)

        self._preencher(
            page, "valor da entrada", _formatar_moeda_input(sol.condicoes.entrada or 0)
        )
        self._preencher(
            page, "valor de venda", _formatar_moeda_input(sol.veiculo.valor or 0)
        )

        # O botão do MODAL é "Simular". "Adicionar Simulação" é o da tela de trás:
        # clicar nele abre outro modal em vez de simular.
        simular = page.get_by_role("button", name=re.compile(r"^Simular$", re.I)).first
        self._aguardar_habilitado(simular, "simular")
        simular.click()

    def _passo_ler_ofertas(self, page, ctx: DriverContext | None) -> str:
        prazo = int(getattr(config, "OFERTAS_TIMEOUT_MS", 240_000))
        try:
            page.wait_for_function(
                "() => /N[ãa]o h[áa] oferta de cr[ée]dito|\\d{1,3}\\s*x/i"
                ".test(document.body.innerText)",
                timeout=prazo,
            )
        except Exception as exc:
            raise ErroTransitorio(
                "ofertas_sem_resposta", "portal não devolveu oferta nem recusa"
            ) from exc
        page.wait_for_timeout(3_000)
        self._evento(ctx, "ofertas_lidas", "Resposta da simulação na tela.", page, True)
        # Para aqui: passos 3 (Confirmação) e 4 (Formalização) não são simulação.
        return page.inner_text("body")

    def _aguardar_habilitado(self, locator, nome: str, tentativas: int = 30) -> None:
        """Espera o botão habilitar. Falha rápido em vez de clicar num disabled por
        90s — foi assim que o Bradesco escondeu um formulário vazio em julho."""
        for _ in range(tentativas):
            if locator.count() and locator.is_enabled():
                return
            locator.page.wait_for_timeout(500)
        raise ErroTransitorio(
            "botao_nao_habilitou", f"botão {nome!r} não habilitou; formulário incompleto"
        )


def fabrica_motrix() -> MotrixDriver:
    return MotrixDriver()
