"""Quem chama quem entre produtos. Tudo aqui e SUSPEITA, nunca erro.

Quatro costuras: cliente HTTP -> rota do produto alvo, funcao publica sem
chamador, n8n -> chatbot e fly.toml -> app declarado.

Nenhuma delas prova nada sozinha. Dispatch dinamico, URL montada em pedaco e
funcao consumida so por template dao falso positivo. A regra que vale para
este arquivo inteiro: **suspeita nao vira commit, vira pergunta.**
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import varredura

# Escrito a mao: qual produto cada cliente HTTP consome. Nao e inferivel — o
# alvo mora na base_url, que vem de config em runtime.
# fipe.py e deepseek.py sao servicos externos e ficam de fora de proposito.
ALVO_POR_CLIENTE: dict[str, str] = {
    "portal-gestao/app/clients/motor.py": "motor-simulacao",
    "portal-gestao/app/clients/chatbot.py": "chatbot-api",
    "portal-gestao/app/clients/estoque.py": "estoque-api",
    "portal-gestao/app/clients/revy_trafego.py": "revy-trafego",
    "chatbot-api/app/inventory.py": "estoque-api",
    "chatbot-api/app/simulation.py": "motor-simulacao",
}

_PARAMETRO = re.compile(r"\{[^}]*\}")


def normalizar(path: str) -> str:
    """`/v1/lojas/{id}` e `/v1/lojas/{loja_id}` viram o mesmo path.

    Tira tambem a barra final, senao `/v1/conversas/` e `/v1/conversas` ficam
    sendo dois paths diferentes e um deles vira falso positivo.
    """
    limpo = _PARAMETRO.sub("{}", path.strip())
    if len(limpo) > 1:
        limpo = limpo.rstrip("/")
    return limpo


# ------------------------------------------------------------------ costura 1
# Cliente HTTP -> rota declarada no produto alvo.

def _de_fstring(no: ast.JoinedStr) -> str:
    partes = []
    for pedaco in no.values:
        if isinstance(pedaco, ast.Constant) and isinstance(pedaco.value, str):
            partes.append(pedaco.value)
        else:
            partes.append("{}")
    return "".join(partes)


def _texto_de(no: ast.AST) -> str | None:
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.JoinedStr):
        return _de_fstring(no)
    return None


def paths_chamados(texto: str) -> set[str]:
    """Paths HTTP que este modulo chama, ja normalizados.

    Duas formas convivem no repo e ignorar uma delas nao quebra nada — so
    devolve menos e segue verde, que e o pior jeito de errar:

    1. argumento de chamada: `self._request("GET", "/v1/provedores")` e
       `self._request("GET", f"/v1/provedores/{nome}/credenciais")`
       (portal-gestao/app/clients/*.py);
    2. URL montada sobre a base e guardada em variavel:
       `url = f"{self.base_url}/v1/simulacoes"` (chatbot-api/app/simulation.py
       e app/inventory.py). Aqui o `{}` da frente e o host, nao um parametro
       de rota — tira-se para sobrar o path.

    `base_url.rstrip("/")` e uma chamada com o argumento `"/"`. Sem descartar
    path de um caractere so, todo cliente do repo aparecia devendo a rota `/`.
    """
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return set()
    candidatos: list[ast.AST] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            candidatos.extend(no.args)
            candidatos.extend(
                kw.value for kw in no.keywords if kw.arg in {"url", "path", "endpoint"}
            )
        elif isinstance(no, ast.Assign):
            candidatos.append(no.value)
        elif isinstance(no, ast.AnnAssign) and no.value is not None:
            candidatos.append(no.value)

    achados: set[str] = set()
    for candidato in candidatos:
        bruto = _texto_de(candidato)
        if bruto is None:
            continue
        valor = normalizar(bruto)
        if valor.startswith("{}/"):   # f"{self.base_url}/v1/..." -> "/v1/..."
            valor = valor[2:]
        if valor.startswith("/") and len(valor) > 1:
            achados.add(valor)
    return achados


# ------------------------------------------------------------------ costura 2
# Funcao publica que ninguem nomeia em lugar nenhum.

def funcoes_publicas(raiz: Path, produto: str) -> dict[str, tuple[str, int]]:
    """Funcoes de modulo, publicas e SEM decorator.

    Funcao decorada esta registrada em algum lugar — rota do FastAPI,
    middleware, exception handler, fixture — e quem a chama e o framework,
    nunca o nome. Medido em 23/08: incluindo as decoradas a secao vinha com
    336 linhas, quase todas handler de rota. Seccao que grita lobo e secao
    que ninguem le; sem elas sobram 9.
    """
    achadas: dict[str, tuple[str, int]] = {}
    base = raiz / produto
    for caminho in varredura.arquivos_py(raiz, produto):
        rel = caminho.relative_to(base).as_posix()
        if rel.startswith(("tests/", "alembic/")):
            continue
        if caminho.name.startswith("test_") or caminho.name == "conftest.py":
            continue
        try:
            arvore = ast.parse(caminho.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for no in arvore.body:
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if no.name.startswith("_") or no.decorator_list:
                continue
            achadas.setdefault(no.name, (rel, no.lineno))
    return achadas


def nomes_usados(raiz: Path) -> set[str]:
    """Todo identificador referenciado em qualquer produto. Calcular UMA vez.

    `ast.alias` entra junto com Name e Attribute: `from app.campanhas import
    payload_form as campanha_payload_form` e uso, e sem ele o `payload_form`
    do Portal e do Control apareciam como orfaos sendo importados na linha 95
    do `main.py`.
    """
    usados: set[str] = set()
    for produto in varredura.PRODUTOS:
        for caminho in varredura.arquivos_py(raiz, produto):
            try:
                arvore = ast.parse(caminho.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for no in ast.walk(arvore):
                if isinstance(no, ast.Name):
                    usados.add(no.id)
                elif isinstance(no, ast.Attribute):
                    usados.add(no.attr)
                elif isinstance(no, ast.alias):
                    usados.add(no.name.split(".")[0])
                    if no.asname:
                        usados.add(no.asname)
    return usados


def sem_chamador(raiz: Path, produto: str, usados: set[str]) -> list[tuple[str, str, int]]:
    # a propria definicao nao conta: um `def foo` vira FunctionDef, nao Name
    return [
        (nome, arquivo, linha)
        for nome, (arquivo, linha) in sorted(funcoes_publicas(raiz, produto).items())
        if nome not in usados
    ]


# ------------------------------------------------------------------ costura 3
# n8n -> chatbot: a junta de maior severidade do repo. Quando abre, o bot emudece.

# Escrito a mao: quais workflows estao PUBLICADOS no n8n. Conferido no painel
# em 23/08. Nao e derivavel do repo — o arquivo existir nao significa estar no
# ar. workflow-teste-numero-autorizado.json existe no repo e NAO esta publicado;
# workflow morto chamando rota removida nao e incidente, e alarme falso mata a
# secao. O render denuncia todo workflow-*.json fora desta tabela.
PUBLICADOS: dict[str, str] = {
    "workflow-ai-nao-salvos.json": "WhatsApp IA - Somente Nao Salvos",
    "workflow-cloud.json": "whatsapp-cloud",
}

HOST_CHATBOT = "chatbot-api:8000"

_ABRE = "([{"
_FECHA = ")]}"


def _campos_do_json(no, chaves=("url", "path")) -> set[tuple[str, str]]:
    """Desce a arvore do workflow atras de campos url/path."""
    achados: set[tuple[str, str]] = set()
    if isinstance(no, dict):
        for chave, valor in no.items():
            if chave in chaves and isinstance(valor, str):
                achados.add((chave, valor))
            else:
                achados |= _campos_do_json(valor, chaves)
    elif isinstance(no, list):
        for item in no:
            achados |= _campos_do_json(item, chaves)
    return achados


def _termos(expr: str) -> list[str]:
    """Quebra a expressao do n8n nos `+` de nivel zero, respeitando aspas."""
    termos: list[str] = []
    atual: list[str] = []
    profundidade = 0
    aspas = ""
    i = 0
    while i < len(expr):
        c = expr[i]
        if aspas:
            atual.append(c)
            if c == "\\" and i + 1 < len(expr):
                atual.append(expr[i + 1])
                i += 2
                continue
            if c == aspas:
                aspas = ""
        elif c in "'\"`":
            aspas = c
            atual.append(c)
        elif c in _ABRE:
            profundidade += 1
            atual.append(c)
        elif c in _FECHA:
            profundidade -= 1
            atual.append(c)
        elif c == "+" and profundidade == 0:
            termos.append("".join(atual))
            atual = []
        else:
            atual.append(c)
        i += 1
    termos.append("".join(atual))
    return termos


def _literal_js(termo: str) -> str | None:
    t = termo.strip()
    if len(t) >= 2 and t[0] in "'\"`" and t[-1] == t[0] and t[0] not in t[1:-1]:
        return t[1:-1]
    return None


def url_montada(bruto: str) -> str:
    """Junta a URL de um no do n8n, com `{}` onde houver expressao.

    O nó chama assim:

        ={{ 'http://chatbot-api:8000/v1/conversas/'
            + encodeURIComponent(String($('Extrair1').first().json.telefone))
            + '/pode-responder' }}

    Cortar no primeiro apostrofo depois do host devolve `/v1/conversas/` — e
    foi exatamente isso que acusou `/pode-responder` como rota faltando, um
    falso positivo por prefixo. A rota certa existe em
    `chatbot-api/app/main.py:921`. Aqui se remonta o path INTEIRO.
    """
    texto = bruto.strip()
    if not texto.startswith("="):
        return texto
    texto = texto[1:].strip()
    if texto.startswith("{{") and texto.endswith("}}"):
        texto = texto[2:-2]
    partes = []
    for termo in _termos(texto):
        literal = _literal_js(termo)
        partes.append(literal if literal is not None else "{}")
    return "".join(partes)


def path_do_chatbot(bruto: str) -> str | None:
    """Path normalizado do chatbot dentro de uma URL de no, ou None."""
    montada = url_montada(bruto)
    if HOST_CHATBOT not in montada:
        return None
    resto = montada.split(HOST_CHATBOT, 1)[1].split("?", 1)[0]
    if not resto.startswith("/"):
        return None
    return normalizar(resto)


def paths_do_workflow(caminho: Path) -> set[str]:
    """Paths do chatbot que ESTE arquivo de workflow chama."""
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, OSError):
        return set()
    achados: set[str] = set()
    for chave, valor in _campos_do_json(dados):
        if chave != "url":
            continue
        path = path_do_chatbot(valor)
        if path:
            achados.add(path)
    return achados


def _webhook_do_json(dados) -> str:
    """O `path` do no de webhook: um segmento so, sem host e sem expressao."""
    candidatos = sorted(
        valor for chave, valor in _campos_do_json(dados)
        if chave == "path" and valor and "/" not in valor
        and not valor.startswith(("http", "=", "{"))
    )
    return candidatos[0] if candidatos else ""


def n8n_costura(raiz: Path) -> tuple[list[dict], set[str]]:
    """(um dict por workflow, paths do chatbot chamados pelos PUBLICADOS)."""
    workflows: list[dict] = []
    chamadas: set[str] = set()
    for arquivo in sorted((raiz / "n8n").glob("workflow-*.json")):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError):
            continue
        publicado = arquivo.name in PUBLICADOS
        if publicado:
            chamadas |= paths_do_workflow(arquivo)
        workflows.append({
            "arquivo": arquivo.name,
            "nome": dados.get("name", "?"),
            "webhook": _webhook_do_json(dados),
            "publicado": publicado,
        })
    return workflows, chamadas


# ------------------------------------------------------------------ costura 4
# fly.toml -> app declarado. So lista; nao julga qual app ainda existe.

_APP_NO_TOML = re.compile(r'^\s*app\s*=\s*[\'"]([^\'"]+)[\'"]', re.MULTILINE)


def fly_tomls(raiz: Path) -> list[tuple[str, str]]:
    achados: list[tuple[str, str]] = []
    for toml in sorted(raiz.rglob("fly.toml")):
        partes = toml.relative_to(raiz).parts
        if any(p in varredura.IGNORADOS or p.startswith("test-tmp") for p in partes):
            continue
        m = _APP_NO_TOML.search(toml.read_text(encoding="utf-8", errors="replace"))
        achados.append((toml.relative_to(raiz).as_posix(), m.group(1) if m else "?"))
    return achados


# ---------------------------------------------------------------------- render

def render(raiz: Path, rotas_por_produto: dict[str, set[str]]) -> str:
    """Os paths de `rotas_por_produto` ja chegam normalizados."""
    linhas = [
        "# Cruzamentos entre produtos",
        "",
        "**Tudo aqui e SUSPEITA, nao erro.** Chamada por string montada, dispatch",
        "dinamico, prefixo de router e funcao consumida so por template geram",
        "falso positivo. Regra: suspeita nao vira commit, vira pergunta.",
        "",
        "NAO editar a mao — saida de `gerar_mapa.py`.",
        "",
        "## Rotas chamadas por cliente HTTP sem servidor declarado",
        "",
        "Casamento de path INTEIRO normalizado, nunca de prefixo.",
        "Duas causas conhecidas de falso positivo aqui: segmento montado em",
        "runtime (`f\"/v1/veiculos/{id}/{acao}\"`) e rota declarada num router",
        "com `prefix=` que o mapa ainda nao aplica.",
        "",
    ]
    achou_orfa = False
    for arquivo_cliente, alvo in sorted(ALVO_POR_CLIENTE.items()):
        caminho = raiz / arquivo_cliente
        if not caminho.exists():
            linhas.append(f"- cliente sumiu do repo: `{arquivo_cliente}`")
            achou_orfa = True
            continue
        chamados = paths_chamados(caminho.read_text(encoding="utf-8", errors="replace"))
        declarados = rotas_por_produto.get(alvo, set())
        for path in sorted(chamados - declarados):
            linhas.append(f"- `{path}` chamado em `{arquivo_cliente}` — `{alvo}` nao declara")
            achou_orfa = True
    if not achou_orfa:
        linhas.append("Nenhuma. Todo path chamado tem rota declarada no produto alvo.")
    linhas.append("")

    linhas.append("## Funcoes publicas sem nenhum chamador")
    linhas.append("")
    linhas.append("Funcao de modulo, publica, SEM decorator e sem nenhuma mencao ao")
    linhas.append("nome em nenhum produto (import conta como mencao). Handler de rota")
    linhas.append("nao entra: quem chama e o framework.")
    linhas.append("")
    achou_solta = False
    usados = nomes_usados(raiz)  # uma varredura so, nao uma por produto
    for produto in varredura.PRODUTOS:
        for nome, arquivo, linha in sem_chamador(raiz, produto, usados):
            linhas.append(f"- `{nome}` — {produto}/{arquivo}:{linha}")
            achou_solta = True
    if not achou_solta:
        linhas.append("Nenhuma.")
    linhas.append("")

    # --- costura n8n x chatbot: a junta onde o bot fica mudo ---
    workflows, chamadas = n8n_costura(raiz)
    declaradas = rotas_por_produto.get("chatbot-api", set())
    linhas.append("## n8n x chatbot")
    linhas.append("")
    linhas.append("| Arquivo | Nome | Webhook | No ar |")
    linhas.append("|---|---|---|---|")
    for w in workflows:
        marca = "SIM" if w["publicado"] else "nao"
        linhas.append(f"| `{w['arquivo']}` | {w['nome']} | `{w['webhook'] or '-'}` | {marca} |")
    linhas.append("")
    fora_da_tabela = [w["arquivo"] for w in workflows if not w["publicado"]]
    if fora_da_tabela:
        linhas.append(
            "Fora da tabela PUBLICADOS em `cruzamentos.py` (nao conferidos): "
            + ", ".join(f"`{a}`" for a in fora_da_tabela)
            + ". Se algum entrou no ar, acrescente — senao a checagem abaixo o ignora."
        )
        linhas.append("")
    linhas.append("Rotas chamadas pelos workflows **no ar**:")
    linhas.append("")
    faltando = sorted(chamadas - declaradas)
    if faltando:
        for path in faltando:
            linhas.append(f"- **SEM SERVIDOR** `{path}` — nenhuma rota do chatbot declara")
        linhas.append("")
        linhas.append("Nao commite conserto por causa desta linha: ou e falso positivo")
        linhas.append("de normalizacao, ou e o bot prestes a ficar mudo. Leve ao dono.")
    else:
        linhas.append(f"Todas as {len(chamadas)} estao declaradas no chatbot:")
        linhas.append("")
        for path in sorted(chamadas):
            linhas.append(f"- `{path}`")
    linhas.append("")

    # --- fly.toml: quais existem e para que app cada um aponta ---
    linhas.append("## fly.toml no repo")
    linhas.append("")
    linhas.append("So a lista: qual arquivo aponta para qual app. Quais desses apps")
    linhas.append("ainda existem e conhecimento humano que muda com o tempo — ver")
    linhas.append("`AGENTS.md` secao 5. Deploy so por `deploy/fly/3vm/`.")
    linhas.append("")
    for caminho, app in fly_tomls(raiz):
        linhas.append(f"- `{caminho}` -> `{app}`")
    linhas.append("")
    return "\n".join(linhas)
