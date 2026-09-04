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

# Modal de agente/operador do go!PAN (componente `mahoe-select`, ids proprios:
# certifiedAgent / commercialOperator).
MODAL_AGENTE_TITULO = re.compile(r"Configure seu agente", re.I)
# Botao fixo no cabecalho da Nova Proposta. Abrir por ele e deterministico; esperar
# o modal auto-abrir nao e (ver `_modal_agente_aberto`).
MODAL_AGENTE_BOTAO = re.compile(r"Agente e operador", re.I)

# UF -> nome por extenso (o dropdown pode listar sigla ou nome completo).
_UF_NOME: dict[str, str] = {
    "AC": "ACRE", "AL": "ALAGOAS", "AP": "AMAPÁ", "AM": "AMAZONAS",
    "BA": "BAHIA", "CE": "CEARÁ", "DF": "DISTRITO FEDERAL",
    "ES": "ESPÍRITO SANTO", "GO": "GOIÁS", "MA": "MARANHÃO",
    "MT": "MATO GROSSO", "MS": "MATO GROSSO DO SUL", "MG": "MINAS GERAIS",
    "PA": "PARÁ", "PB": "PARAÍBA", "PR": "PARANÁ", "PE": "PERNAMBUCO",
    "PI": "PIAUÍ", "RJ": "RIO DE JANEIRO", "RN": "RIO GRANDE DO NORTE",
    "RS": "RIO GRANDE DO SUL", "RO": "RONDÔNIA", "RR": "RORAIMA",
    "SC": "SANTA CATARINA", "SP": "SÃO PAULO", "SE": "SERGIPE",
    "TO": "TOCANTINS",
}

# Cards de parcela: "24x 1.212,76" / "24x de R$ 1.212,76" (R$ pode faltar).
_RE_PARCELA = re.compile(
    r"(\d{1,3})\s*x\b[^0-9]{0,20}?(?:R\$\s*)?(\d[\d.]*,\d{2})",
    re.IGNORECASE,
)
# Entrada minima exibida pos-simulacao ("Entrada: R$ 3.956,40").
_RE_ENTRADA = re.compile(
    r"(?:Entrada\s+m[ií]nima|Entrada)\s*:?\s*(?:R\$\s*)?(\d[\d.]*,\d{1,2})",
    re.IGNORECASE,
)
# Valor financiado exibido no card ("Financiado: R$ 15.116,80").
_RE_FINANCIADO = re.compile(
    r"Financiad[oa]\s*:?\s*(?:R\$\s*)?(\d[\d.]*,\d{1,2})",
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


def parse_financiado(texto: str) -> Decimal | None:
    """Valor financiado exibido no card ('Financiado: R$ ...'), se houver."""
    plano = _texto_plano(texto)
    m = _RE_FINANCIADO.search(plano)
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
        # Prefere o "Financiado" que o portal exibe; so cai no calculo
        # (valor - entrada) quando o card nao trouxer o valor.
        financiado = parse_financiado(html)
        if financiado is None and sol.veiculo.valor is not None:
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
            browser_ctx = self._new_context(browser, ctx)
            page = browser_ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                self._evento(ctx, "browser_pronto", "Navegador iniciado; abrindo o portal.")
                self._passo_login(page, usuario, senha)
                # Cookies/LGPD costumam aparecer so depois de autenticar.
                self._fechar_got_it(page)
                self._evento(
                    ctx, "login_confirmado", "Login confirmado pelo portal.", page, True
                )
                self._configurar_agente_operador(page)
                self._evento(
                    ctx,
                    "agente_definido",
                    "Agente certificado e operador confirmados no portal.",
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
                texto = self._texto_ofertas(page)
                html = page.content() or ""
                resultados = self._resultados_de_html(texto + "\n" + html, sol)
                self._salvar_storage(browser_ctx, ctx)
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
                "cadastre usuario/senha do lojista em Acessos bancos (Portal)",
            )
        return segredo

    # --- passos do portal ---------------------------------------------------

    def _passo_login(self, page, usuario: str, senha: str) -> None:
        url = self.login_url
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        # go!PAN mantem conexoes abertas (chat/analytics): networkidle NUNCA
        # estabiliza e trava o timeout inteiro (licao Fontecred). Usamos
        # domcontentloaded e esperamos o proprio campo de login aparecer.
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        except Exception:
            pass
        page.wait_for_timeout(800)
        self._assert_portal_acessivel(page)
        self._aguardar_dom_pronto(page)

        # Decidir por PRESENCA do campo de login, nao pela URL: se o input de
        # usuario existe, logamos; se nao existe, assumimos sessao ja autenticada.
        self._fechar_got_it(page)
        try:
            usuario_box = self._campo_usuario(page)
        except Exception:
            if self._portal_autenticado(page):
                page.wait_for_timeout(400)
                return
            raise
        usuario_box.click()
        usuario_box.fill("")
        usuario_box.type(usuario, delay=35)
        self._fechar_got_it(page)
        senha_box = self._campo_senha(page)
        senha_box.click()
        senha_box.fill("")
        senha_box.type(senha, delay=40)
        page.wait_for_timeout(300)
        self._fechar_got_it(page)  # garante que o banner nao intercepta o clique
        # Botao Entrar fica disabled ate o form validar CPF/senha.
        try:
            page.wait_for_function(
                """() => {
                  const bs = [...document.querySelectorAll('button')];
                  const b = bs.find(x => /^\\s*Entrar\\s*$/i.test((x.textContent||'').trim()));
                  return b && !b.disabled;
                }""",
                timeout=min(self.timeout_ms, 12_000),
            )
        except Exception:
            pass
        page.get_by_role("button", name=re.compile(r"^Entrar$", re.I)).first.click()
        self._aguardar_pos_login(page)

    def _campo_usuario(self, page):
        """Usuario do lojista (pan-mahoe: formcontrolname='login', id='login',
        label='Usuário' como ATRIBUTO custom — sem nome acessivel via role)."""
        candidatos = (
            lambda: page.locator("input#login").first,
            lambda: page.locator("input[formcontrolname='login']").first,
            lambda: page.locator("input[name='login']").first,
            lambda: page.locator("input[label='Usuário'], input[label='Usuario']").first,
            lambda: page.get_by_role("textbox", name=re.compile(r"Usu[aá]rio", re.I)).first,
            lambda: page.locator(
                "input[type='text'], input[type='tel'], input:not([type])"
            ).first,
        )
        return self._primeiro_visivel(page, candidatos, "Usuário (login)")

    def _campo_senha(self, page):
        """Senha do lojista (pan-mahoe: type=password / formcontrolname)."""
        candidatos = (
            lambda: page.locator("input[type='password']").first,
            lambda: page.locator(
                "input[formcontrolname='senha'], input[formcontrolname='password']"
            ).first,
            lambda: page.locator("input#senha, input#password").first,
            lambda: page.locator("input[label='Senha']").first,
            lambda: page.get_by_role("textbox", name=re.compile(r"Senha", re.I)).first,
        )
        return self._primeiro_visivel(page, candidatos, "Senha (login)")

    def _digitar_mascarado(
        self, page, box, valor: str, normaliza: str = r"\D"
    ) -> None:
        """Digita em campo com mascara (mahoe) e CONFERE. A mascara insere
        pontuacao sozinha e perde caractere em digitacao rapida, entao:
        limpa o campo de forma robusta, digita devagar e refaz mais devagar
        ate os digitos baterem (delays 110 -> 200 -> 300 ms)."""
        alvo = re.sub(normaliza, "", valor).upper()
        for delay in (110, 200, 300):
            try:
                box.click()
                # Limpeza robusta: seleciona tudo e apaga (fill('') as vezes nao
                # limpa mascara).
                try:
                    box.press("Control+a")
                    box.press("Delete")
                except Exception:
                    box.fill("")
                box.press_sequentially(valor, delay=delay)
                page.wait_for_timeout(150)
                atual = re.sub(normaliza, "", box.input_value() or "").upper()
                if atual == alvo:
                    return
            except Exception:
                continue
        # Ultima tentativa: fill direto (campos sem mascara real).
        try:
            box.fill(valor)
        except Exception:
            pass

    def _primeiro_visivel(self, page, candidatos, campo: str):
        """Retorna o primeiro locator visivel; senao levanta campo_nao_encontrado.

        Espera curta por tentativa (2,5s): o candidato correto deste portal e
        sempre o 1o e renderiza rapido; timeout alto so faz o fallback custar
        6s cada quando o 1o nao casa. Total de 2 passadas cobre render lento.
        """
        curto = min(self.timeout_ms, 3_500)
        for gerar in candidatos:
            try:
                box = gerar()
                box.wait_for(state="visible", timeout=curto)
                return box
            except Exception:
                continue
        raise self._falha_campo(campo)

    def _modal_agente_aberto(self, page) -> bool:
        """Diz se o dialogo esta REALMENTE aberto, pela altura do container.

        O go!PAN deixa o `.mahoe-modal__dialog` no DOM com `height: 0` e
        `overflow: hidden` quando fechado. O conteudo continua la, com geometria
        propria, apenas recortado. Playwright nao analisa clipping, entao o
        titulo responde `is_visible() == True` com o modal fechado e o clique
        seguinte estoura o timeout sem explicacao (sim 20260904-151456). A altura
        do dialogo e o unico sinal que separa os dois estados.
        """
        try:
            return bool(
                page.evaluate(
                    """() => {
                        const d = document.querySelector('.mahoe-modal__dialog');
                        return !!d && d.getBoundingClientRect().height > 0;
                    }"""
                )
            )
        except Exception:
            return False

    def _abrir_modal_agente(self, page) -> None:
        """Abre o dialogo pelo botao do cabecalho, que existe sempre."""
        if self._modal_agente_aberto(page):
            return
        page.get_by_role("button", name=MODAL_AGENTE_BOTAO).first.click(
            timeout=min(self.timeout_ms, 10_000)
        )
        page.wait_for_timeout(800)
        if not self._modal_agente_aberto(page):
            raise ErroTransitorio(
                "pan_modal_agente_nao_abriu",
                "botao 'Agente e operador' nao abriu o dialogo de configuracao",
            )

    def _configurar_agente_operador(self, page) -> None:
        """Fixa agente certificado e operador antes de comecar a proposta.

        Eles definem a quem a proposta e atribuida. Com sessao quente o portal
        as vezes NAO abre o modal sozinho, entao esperar por ele nao serve:
        abrimos pelo botao do cabecalho e escolhemos sempre.

        Sem nome configurado so agimos se o modal estiver bloqueando a tela —
        senao o passo seguinte morre em `campo_nao_encontrado` culpando o campo
        Celular, que na verdade estava atras do overlay (sim 20260904-150259).
        """
        quer_definir = bool(config.PAN_AGENTE_CERTIFICADO or config.PAN_OPERADOR)
        if not quer_definir and not self._modal_agente_aberto(page):
            return

        self._abrir_modal_agente(page)
        self._escolher_no_combo(
            page, "certifiedAgent", config.PAN_AGENTE_CERTIFICADO, "agente certificado"
        )
        self._escolher_no_combo(
            page, "commercialOperator", config.PAN_OPERADOR, "operador"
        )

        page.get_by_role(
            "button", name=re.compile(r"^\s*Salvar\s*$", re.I)
        ).first.click(timeout=min(self.timeout_ms, 10_000))
        for _ in range(20):
            page.wait_for_timeout(500)
            if not self._modal_agente_aberto(page):
                return
        raise ErroTransitorio(
            "pan_agente_nao_salvou",
            "dialogo de agente/operador continuou aberto depois do Salvar",
        )

    def _escolher_no_combo(
        self, page, campo_id: str, nome: str, rotulo: str
    ) -> None:
        """Escolhe no `mahoe-select` a opcao que casa com ``nome``.

        O portal TRUNCA o texto da opcao em 20 caracteres ("Bruna Cristina Mulle"),
        entao a comparacao e por prefixo nos dois sentidos, nunca igualdade. Dois
        candidatos = erro, para nao atribuir a proposta a pessoa errada em silencio.
        """
        if not nome:
            return
        alvo = nome.strip().lower()
        entrada = page.locator(f"#{campo_id}-value")
        entrada.click(timeout=min(self.timeout_ms, 8_000))
        # O listbox so renderiza depois do clique; enumerar antes devolve zero.
        page.locator(f"#{campo_id}-listbox").first.wait_for(
            state="visible", timeout=min(self.timeout_ms, 8_000)
        )

        opcoes = page.locator(f"#{campo_id}-listbox [role='option']")
        disponiveis: list[str] = []
        casados: list[int] = []
        for i in range(opcoes.count()):
            texto = (opcoes.nth(i).inner_text() or "").strip()
            disponiveis.append(texto)
            curto = texto.lower()
            if curto and (curto.startswith(alvo) or alvo.startswith(curto)):
                casados.append(i)

        if not casados:
            raise IntervencaoNecessaria(
                "pan_agente_indisponivel",
                f"{rotulo} '{nome}' nao esta na lista do portal: {disponiveis}",
            )
        if len(casados) > 1:
            raise IntervencaoNecessaria(
                "pan_agente_ambiguo",
                f"{rotulo} '{nome}' casa com mais de uma opcao: "
                f"{[disponiveis[i] for i in casados]}",
            )

        opcoes.nth(casados[0]).click(timeout=min(self.timeout_ms, 8_000))
        # Le de volta: clique engolido deixaria o combo vazio e o Salvar seguiria.
        lido = (entrada.input_value() or "").strip().lower()
        if not lido or not (
            lido.startswith(alvo) or alvo.startswith(lido) or lido in disponiveis[casados[0]].lower()
        ):
            raise ErroTransitorio(
                "pan_agente_nao_aplicou",
                f"{rotulo} nao ficou selecionado apos o clique",
            )

    def _fechar_got_it(self, page) -> None:
        """Fecha banners que bloqueiam a tela: onboarding 'Got it!' e o
        aviso de cookies/LGPD ('Aceitar', 'Aceitar todos', 'Concordo', ...).

        Best-effort: cada tentativa tem timeout curto e nunca levanta. Roda
        depois do login e antes de preencher, porque o overlay de cookies
        intercepta cliques e faz os passos seguintes estourarem timeout.
        """
        nomes = (
            r"Got it",
            r"Permitir\s+todos\s+os\s+cookies",  # banner LGPD do go!PAN
            r"Permitir\s+todos",
            r"Rejeitar\s+cookies",               # tambem fecha o banner
            r"Aceitar\s+todos",
            r"Aceitar\s+cookies",
            r"^Aceitar$",
            r"Aceito",
            r"Concordo",
            r"^Entendi$",
            r"Prosseguir",
        )
        for padrao in nomes:
            try:
                btn = page.get_by_role(
                    "button", name=re.compile(padrao, re.I)
                ).first
                if btn.count() and btn.is_visible():
                    btn.click(timeout=2_500)
                    page.wait_for_timeout(250)
            except Exception:
                continue

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
        self._fechar_got_it(page)  # cookies podem cobrir os campos
        cpf = re.sub(r"\D", "", sol.pessoa.cpf or "")
        # Tela /captura/inicio: "informe o CPF do cliente". Campo pan-mahoe com
        # mascara "000.000.000-00" e sem nome acessivel -> ancorar por placeholder
        # da mascara e formcontrolname.
        self._digitar_mascarado(page, self._campo_cpf(page), cpf)
        page.keyboard.press("Tab")
        page.wait_for_timeout(600)
        # O portal pode avancar sozinho ao completar o CPF ou exigir um botao
        # Continuar/Avancar. Best-effort para seguir.
        for padrao in (r"^Continuar$", r"^Avan[çc]ar$", r"^Prosseguir$", r"^Simular$"):
            try:
                btn = page.get_by_role("button", name=re.compile(padrao, re.I)).first
                if btn.count() and btn.is_visible() and btn.is_enabled():
                    btn.click(timeout=4_000)
                    self._aguardar_dom_pronto(page, 10_000)
                    break
            except Exception:
                continue
        page.wait_for_timeout(300)

    def _campo_cpf(self, page):
        """CPF do cliente (pan-mahoe, mascara '000.000.000-00').

        IMPORTANTE: ancorar no <input> interno — o wrapper <pan-mahoe-input>
        tambem carrega o placeholder e nao e preenchivel (fill quebra nele).
        """
        candidatos = (
            lambda: page.locator("input[placeholder*='000.000.000-00']").first,
            lambda: page.locator(
                "input[formcontrolname='cpf'], input[formcontrolname='documento'], "
                "input[formcontrolname='cpfCliente']"
            ).first,
            lambda: page.locator("input#cpf, input[label='CPF']").first,
            lambda: page.locator("input[inputmode='numeric']").first,
            lambda: page.get_by_role("textbox", name=re.compile(r"CPF", re.I)).first,
        )
        return self._primeiro_visivel(page, candidatos, "CPF do cliente")

    def _passo_veiculo(self, page, sol: SolicitacaoSimulacao) -> None:
        # Tela /comparador: celular ("Digite o celular...") + veiculo por placa.
        self._fechar_got_it(page)
        # So digitos: a mascara insere ( ) - sozinha. Digitacao lenta com
        # verificacao (mascara mahoe perde caractere em type rapido).
        cel = re.sub(r"\D", "", sol.pessoa.celular or "")
        self._digitar_mascarado(page, self._campo_celular(page), cel)
        page.keyboard.press("Tab")
        page.wait_for_timeout(400)

        placa = (sol.veiculo.placa or "").replace("-", "").upper()
        # "Busca placa" pode ser um toggle/botao antes do campo de placa.
        try:
            btn = page.get_by_role(
                "button", name=re.compile(r"Busca\s+placa", re.I)
            ).first
            if btn.count() and btn.is_visible():
                btn.click(timeout=min(self.timeout_ms, 6_000))
                page.wait_for_timeout(400)
        except Exception:
            pass
        self._digitar_mascarado(
            page, self._campo_placa(page), placa, normaliza=r"[^A-Za-z0-9]"
        )
        page.keyboard.press("Tab")
        page.wait_for_timeout(1_200)
        # Estado/UF de licenciamento (dropdown na tela do comparador). So troca
        # se a solicitacao informar a UF; senao mantem o default do portal.
        self._passo_uf(page, sol)

    def _passo_uf(self, page, sol: SolicitacaoSimulacao) -> None:
        uf = (sol.veiculo.uf_licenciamento or "").strip().upper()
        if not uf or uf not in _UF_NOME:
            return
        nome = _UF_NOME[uf]
        # 1) Abrir o dropdown "UF licenciamento" (rotulo visto na tela do
        #    comparador). O select mahoe mostra a sigla atual (ex.: "SP").
        abriu = False
        # xpath case-insensitive: acha o rotulo (UF/licenciamento/estado) e
        # pega o proximo elemento clicavel de selecao.
        _lower = (
            "translate(normalize-space(.),"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
        )
        abridores = (
            lambda: page.get_by_role(
                "combobox", name=re.compile(r"\bUF\b|licenciamento|Estado", re.I)
            ).first,
            lambda: page.locator(
                f"xpath=//*[contains({_lower},'uf licenciamento') "
                f"or normalize-space({_lower})='uf' "
                f"or contains({_lower},'licenciamento')]"
                "/following::*[self::select or self::mat-select "
                "or @role='combobox' or @role='listbox' "
                "or contains(@class,'select')][1]"
            ).first,
            lambda: page.locator("mat-select, [role='combobox']").last,
        )
        for gerar in abridores:
            try:
                alvo = gerar()
                alvo.wait_for(state="visible", timeout=min(self.timeout_ms, 5_000))
                alvo.click()
                abriu = True
                break
            except Exception:
                continue
        if not abriu:
            return
        page.wait_for_timeout(300)
        # 2) Selecionar a opcao pela sigla ou nome por extenso.
        for gerar in (
            lambda: page.get_by_role(
                "option", name=re.compile(rf"^\s*{re.escape(uf)}\s*$", re.I)
            ).first,
            lambda: page.get_by_role(
                "option", name=re.compile(re.escape(nome), re.I)
            ).first,
            lambda: page.get_by_text(
                re.compile(rf"^\s*{re.escape(uf)}\s*$", re.I)
            ).first,
            lambda: page.get_by_text(re.compile(re.escape(nome), re.I)).first,
        ):
            try:
                opc = gerar()
                opc.wait_for(state="visible", timeout=min(self.timeout_ms, 5_000))
                opc.click()
                page.wait_for_timeout(300)
                return
            except Exception:
                continue

    def _campo_celular(self, page):
        """Celular do cliente (placeholder 'Digite o celular...')."""
        candidatos = (
            lambda: page.locator("input[placeholder*='Digite o celular']").first,
            lambda: page.locator("input[placeholder*='celular']").first,
            lambda: page.locator(
                "input[formcontrolname='celular'], input[formcontrolname='telefone']"
            ).first,
            lambda: page.locator("input[label='Celular'], input[label='Telefone']").first,
            lambda: page.get_by_role(
                "textbox", name=re.compile(r"Celular|Telefone", re.I)
            ).first,
        )
        return self._primeiro_visivel(page, candidatos, "Celular do cliente")

    def _campo_placa(self, page):
        """Placa do veiculo (placeholder 'Digite a placa...')."""
        candidatos = (
            lambda: page.locator("input[placeholder*='Digite a placa']").first,
            lambda: page.locator("input[placeholder*='placa']").first,
            lambda: page.locator("input[formcontrolname='placa']").first,
            lambda: page.locator("input[label='Placa']").first,
            lambda: page.get_by_role("combobox", name=re.compile(r"placa", re.I)).first,
            lambda: page.get_by_role("textbox", name=re.compile(r"placa", re.I)).first,
        )
        return self._primeiro_visivel(page, candidatos, "Placa")

    def _passo_valor(self, page, sol: SolicitacaoSimulacao) -> None:
        if sol.veiculo.valor is None:
            return
        # Campo "Venda" (mahoe, sem nome acessivel). Placa costuma pre-preencher
        # um valor; sobrescrevemos com o valor da solicitacao. Best-effort.
        candidatos = (
            lambda: page.locator(
                "input[placeholder*='Valor de venda'], input[placeholder*='Venda'], "
                "input[placeholder*='venda']"
            ).first,
            lambda: page.locator(
                "input[formcontrolname*='venda' i], input[formcontrolname*='valor' i]"
            ).first,
            lambda: page.locator(
                "input[label='Venda'], input[label='Valor de venda']"
            ).first,
            # Rotulo "Venda:" fica ao lado do input (mahoe): pega o input que
            # segue um elemento com esse texto.
            lambda: page.locator(
                "xpath=//*[normalize-space(text())='Venda:' or "
                "normalize-space(text())='Venda']/following::input[1]"
            ).first,
            lambda: page.get_by_role(
                "textbox", name=re.compile(r"Valor de venda|Venda", re.I)
            ).first,
        )
        try:
            valor_box = self._primeiro_visivel(page, candidatos, "Valor de venda")
        except Exception:
            return  # portal pode resolver o valor pela placa
        self._digitar_valor(page, valor_box, float(sol.veiculo.valor))
        page.keyboard.press("Tab")
        page.wait_for_timeout(400)

    def _digitar_valor(self, page, box, valor: float) -> None:
        """Digita moeda auto-detectando a mascara: tenta o inteiro em reais
        ('21900') e, se o valor lido nao bater, a forma em centavos ('2190000').
        Confere pelo NUMERO lido, nao pela string (mascara varia por campo)."""
        alvo = Decimal(str(valor))
        reais = str(int(round(valor)))          # 21900
        centavos = str(int(round(valor * 100)))  # 2190000
        for tentativa in (reais, centavos, reais):
            try:
                box.click()
                try:
                    box.press("Control+a")
                    box.press("Delete")
                except Exception:
                    box.fill("")
                box.press_sequentially(tentativa, delay=90)
                page.wait_for_timeout(150)
                try:
                    lido = parse_moeda_br(box.input_value() or "0")
                except Exception:
                    lido = None
                if lido is not None and lido == alvo:
                    return
            except Exception:
                continue

    def _passo_simular(self, page, sol: SolicitacaoSimulacao) -> None:
        self._fechar_got_it(page)
        simular = page.get_by_role("button", name=re.compile(r"^Simular$", re.I)).first
        simular.wait_for(state="visible", timeout=self.timeout_ms)
        # Botao Simular fica disabled ate placa/valor/veiculo validarem.
        try:
            page.wait_for_function(
                """() => {
                  const bs = [...document.querySelectorAll('button')];
                  const b = bs.find(x => /^\\s*Simular\\s*$/i.test((x.textContent||'').trim()));
                  return b && !b.disabled;
                }""",
                timeout=min(self.timeout_ms, 15_000),
            )
        except Exception:
            pass
        try:
            simular.click(timeout=min(self.timeout_ms, 8_000))
        except Exception:
            simular.click(force=True)
        page.wait_for_timeout(800)
        # Entrada e OPCIONAL: so preenche apos simular se o usuario mandou > 0.
        entrada = sol.condicoes.entrada or 0
        if entrada and float(entrada) > 0:
            candidatos = (
                lambda: page.locator("input[placeholder*='Entrada']").first,
                lambda: page.locator("input[formcontrolname='entrada']").first,
                lambda: page.locator("input[label='Entrada']").first,
                lambda: page.get_by_role(
                    "textbox", name=re.compile(r"Entrada", re.I)
                ).first,
            )
            try:
                entrada_box = self._primeiro_visivel(page, candidatos, "Entrada")
                entrada_box.click()
                entrada_box.fill("")
                entrada_box.type(_formatar_moeda_input(float(entrada)), delay=25)
                page.keyboard.press("Tab")
                page.wait_for_timeout(500)
            except Exception:
                pass

    def _passo_aguardar_ofertas(self, page) -> None:
        """Espera a simulacao concluir e os valores ESTABILIZAREM antes de ler.

        Por condicao: retorna assim que (a) ha um sinal de conclusao
        (Aprovado/Reprovado/Financiado) e (b) as parcelas lidas se repetem em
        duas leituras seguidas. Nao gasta o timeout cheio quando ja esta pronto;
        o teto so vale se nunca estabilizar.
        """
        timeout = max(self.timeout_ms, 60_000)
        prazo_fim = time.monotonic() + (timeout / 1000.0)
        concluido = re.compile(r"Aprovad|Reprovad|Negad|Financiad", re.I)
        erro = re.compile(r"Ocorreu um erro|indispon[ií]vel|falha", re.I)
        anterior = None
        while time.monotonic() < prazo_fim:
            if page.get_by_text(erro).count() > 0:
                raise ErroTransitorio(
                    "portal_simulacao_erro", "erro exibido na tela de ofertas"
                )
            tem_conclusao = page.get_by_text(concluido).count() > 0
            # parcela vem do textContent (option colapsada e oculta); nao usar
            # get_by_text (so ve texto visivel). O parse e a fonte de verdade.
            atual = tuple(parse_parcelas_pan_portal(self._texto_ofertas(page)))
            # Estavel = mesmas parcelas em duas leituras + sinal de conclusao.
            if tem_conclusao and atual and atual == anterior:
                return
            anterior = atual
            page.wait_for_timeout(500)
        self._assert_portal_acessivel(page)
        raise ErroTransitorio(
            "portal_falhou", "grade de parcelas nao carregou/estabilizou a tempo"
        )

    def _texto_ofertas(self, page) -> str:
        """Texto da tela + valores dos <input> (entrada/venda ficam em input,
        que inner_text NAO enxerga) rotulados por um label CURTO ao lado do
        campo — nunca o texto do card inteiro (isso fazia o regex de entrada
        grudar num numero errado)."""
        try:
            corpo = page.inner_text("body") or ""
        except Exception:
            corpo = ""
        extra = ""
        try:
            extra = page.evaluate(
                """() => {
                    const curto = (inp) => {
                        // 1) <label> associado
                        if (inp.labels && inp.labels.length) {
                            const t = (inp.labels[0].innerText || '').trim();
                            if (t) return t;
                        }
                        // 2) atributos label/aria-label/placeholder
                        const a = inp.getAttribute('label')
                            || inp.getAttribute('aria-label')
                            || inp.placeholder || '';
                        if (a.trim()) return a.trim();
                        // 3) irmao/ancestral proximo com texto curto
                        let p = inp.previousElementSibling;
                        for (let i = 0; i < 3 && p; i++, p = p.previousElementSibling) {
                            const t = (p.innerText || '').replace(/\\s+/g,' ').trim();
                            if (t && t.length <= 24) return t;
                        }
                        let anc = inp.parentElement;
                        for (let i = 0; i < 3 && anc; i++, anc = anc.parentElement) {
                            let s = anc.previousElementSibling;
                            for (let j = 0; j < 2 && s; j++, s = s.previousElementSibling) {
                                const t = (s.innerText || '').replace(/\\s+/g,' ').trim();
                                if (t && t.length <= 24) return t;
                            }
                        }
                        return '';
                    };
                    const out = [];
                    document.querySelectorAll('input').forEach(inp => {
                        const v = (inp.value || '').trim();
                        if (!v) return;
                        const lab = curto(inp);
                        // Rotulo curto (p/ entrada/venda) + valor cru (p/ parcela
                        // que pode estar num input sem rotulo, ex.: "48x R$ 800,00").
                        if (lab && lab.length <= 24) out.push(lab + ' ' + v);
                        out.push(v);
                    });
                    // Parcela: componente <app-custom-select id="installment-select">
                    // com a opcao num <span> dentro de [role=option]. O menu fica
                    // colapsado (aria-expanded=false), entao o texto NAO entra no
                    // inner_text; textContent ignora visibilidade e pega. Cobre
                    // tambem <select> nativo por seguranca.
                    const seletores = [
                        'app-custom-select',
                        '#installment-select',
                        '[id^="installment"]',
                        '[role="option"]',
                        '.vehicle-offer__value__select__option',
                        '.combo__menu',
                    ];
                    document.querySelectorAll(seletores.join(',')).forEach(el => {
                        const t = (el.textContent || '').replace(/\\s+/g,' ').trim();
                        if (t) out.push(t);
                    });
                    document.querySelectorAll('select').forEach(sel => {
                        (sel.options ? Array.from(sel.options) : []).forEach(o => {
                            const t = (o.textContent || '').replace(/\\s+/g,' ').trim();
                            if (t) out.push(t);
                        });
                    });
                    return out.join('\\n');
                }"""
            ) or ""
        except Exception:
            extra = ""
        # Locators do Playwright enxergam texto renderizado (inclusive shadow DOM
        # aberto): pega elementos que parecem parcela ("Nx R$") e usa o texto real.
        via_loc = self._parcelas_via_locator(page)
        texto = corpo + "\n" + extra + "\n" + via_loc
        # Debug opcional: grava o que o parser enxerga (MOTOR_PAN_PORTAL_DEBUG=1).
        if os.getenv("MOTOR_PAN_PORTAL_DEBUG"):
            try:
                base = Path(self.screenshot_dir or "data/screenshots")
                base.mkdir(parents=True, exist_ok=True)
                (base / "pan_ofertas_debug.txt").write_text(texto, encoding="utf-8")
            except Exception:
                pass
        return texto

    def _parcelas_via_locator(self, page) -> str:
        """Coleta textos de elementos que parecem parcela ('Nx ... R$').

        Usa locators (nao inner_text do body): pegam o texto renderizado de
        componentes custom/mahoe onde o valor do dropdown nao entra no
        inner_text nem em querySelectorAll('select')."""
        partes: list[str] = []
        try:
            loc = page.get_by_text(re.compile(r"\d+\s*x\b.*R\$", re.I))
            n = min(loc.count(), 12)
            for i in range(n):
                try:
                    t = loc.nth(i).inner_text(timeout=1_000)
                    if t:
                        partes.append(t.replace("\n", " "))
                except Exception:
                    continue
        except Exception:
            pass
        return "\n".join(partes)

    def _salvar_storage(self, browser_ctx, ctx=None) -> None:
        self._salvar_storage_state(browser_ctx, ctx)


def fabrica_pan_portal() -> PanPortalDriver:
    from app.motor.playwright_base import browser_headless_padrao

    return PanPortalDriver(
        headless=browser_headless_padrao(),
        screenshot_dir=config.SCREENSHOT_DIR,
        storage_state_path=Path(config.STORAGE_STATE_DIR) / "pan_portal.json",
        timeout_ms=int(getattr(config, "BROWSER_TIMEOUT_MS", 45_000)),
        login_url=getattr(config, "PAN_PORTAL_LOGIN_URL", LOGIN_URL_DEFAULT),
    )
