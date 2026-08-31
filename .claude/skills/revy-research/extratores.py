"""Extratores puros: texto de um arquivo -> list[Entrada]. Nunca importam o app."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, replace
from pathlib import Path

from varredura import IGNORADOS, Entrada

VERBOS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _decorators_de_rota(no: ast.AST):
    """(verbo, no_do_path, objeto). Quem resolve o path e `_resolver_path`.

    A linha usada la fora e a do NO DO PATH, nao a do decorator. Quando o
    decorator quebra em varias linhas (o estilo de control.py e control_ui.py,
    com o path numa linha propria), `dec.lineno` aponta para a linha do
    @router.post, onde o path nao esta escrito — e o --verificar acusa mentira.
    Mesma armadilha que o TemplateResponse ja tinha.
    """
    for dec in getattr(no, "decorator_list", []):
        if not isinstance(dec, ast.Call):
            continue
        alvo = dec.func
        if not isinstance(alvo, ast.Attribute) or alvo.attr not in VERBOS:
            continue
        objeto = alvo.value.id if isinstance(alvo.value, ast.Name) else ""
        if not dec.args:
            continue
        yield alvo.attr.upper(), dec.args[0], objeto


def _constantes_de_modulo(arvore: ast.Module) -> dict[str, str]:
    """{nome: valor} das constantes string do topo do modulo.

    Resolve NA ORDEM do arquivo e reaproveitando o que ja resolveu, porque o
    repo encadeia constante em cima de constante:

        _PAGINA = "/app/loja/financeiro"
        _DESPESAS = _PAGINA + "/despesas"     # loja_financeiro.py:43

    Ler so o literal acha `_PAGINA` e perde `_DESPESAS` — e com ela as quatro
    rotas de despesa. Foi exatamente o erro que este arquivo ja tinha, repetido
    um nivel acima na primeira tentativa de conserto: assumir UMA forma onde o
    repo usa duas. Vale mais desconfiar da propria correcao.
    """
    achadas: dict[str, str] = {}
    for no in arvore.body:
        alvo = None
        if isinstance(no, ast.Assign) and len(no.targets) == 1:
            alvo = no.targets[0]
        elif isinstance(no, ast.AnnAssign):
            alvo = no.target
        if not isinstance(alvo, ast.Name) or no.value is None:
            continue
        lido = _resolver_path(no.value, achadas)
        if lido is not None:
            achadas[alvo.id] = lido[0]
    return achadas


def _resolver_path(no: ast.AST, constantes: dict[str, str]):
    """(path, ancora) ou None se o gerador nao souber ler.

    `ancora` e o que esta ESCRITO na linha — e o que o --verificar reabre e
    exige. Para `@router.get("/x")` a ancora e o proprio path; para
    `@router.get(_PAGINA)` a ancora e `_PAGINA`, porque e isso que o leitor
    encontra naquela linha.

    Existe porque so `ast.Constant` deixava 25 rotas fora do mapa — e nao
    quaisquer 25: as de loja_copiloto, loja_financeiro, loja_whatsapp,
    loja_integracoes e loja_perfil, ou seja, exatamente os modulos novos, que
    sao os que mais se pede para mexer. O `--verificar` seguia dizendo "mapa
    confere com o codigo", porque ele so reabre o que esta no mapa: ausencia
    ele nao ve. Sexta vez que a mesma assinatura aparece neste projeto —
    assumir UMA forma sintatica onde o repo usa duas, devolver menos e
    continuar verde.
    """
    if isinstance(no, ast.Constant):
        return (no.value, no.value) if isinstance(no.value, str) else None
    if isinstance(no, ast.Name):
        valor = constantes.get(no.id)
        return (valor, no.id) if valor is not None else None
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
        esq = _resolver_path(no.left, constantes)
        dir_ = _resolver_path(no.right, constantes)
        if esq is None or dir_ is None:
            return None
        # a ancora e a da esquerda: e ela que abre a expressao na linha
        return esq[0] + dir_[0], esq[1]
    return None


def _prefixos_de_construtor(arvore: ast.Module) -> dict[str, str]:
    """{nome_da_variavel: prefixo} para `x = APIRouter(prefix="/v1")`.

    O prefixo do repo mora AQUI, nao no include_router: veja
    revy-trafego/app/api_v1.py:37. Como o construtor esta no mesmo arquivo das
    rotas, isto resolve estaticamente sem nada cross-file — e nao ha o que
    marcar com `?` quando o literal existe.
    """
    achados: dict[str, str] = {}
    for no in ast.walk(arvore):
        alvo = None
        if isinstance(no, ast.Assign) and len(no.targets) == 1:
            alvo = no.targets[0]
        elif isinstance(no, ast.AnnAssign):
            alvo = no.target
        if not isinstance(alvo, ast.Name) or not isinstance(no.value, ast.Call):
            continue
        func = no.value.func
        nome = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if nome != "APIRouter":
            continue
        kw = next((k for k in no.value.keywords if k.arg == "prefix"), None)
        if kw is None:
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            achados[alvo.id] = kw.value.value
    return achados


def rotas(texto: str, arquivo_rel: str) -> list[Entrada]:
    """Todo `@app.<verbo>("/path")` / `@router.<verbo>("/path")` do arquivo.

    `simbolo` e o PATH, nao o nome da funcao: o `--verificar` reabre a linha do
    decorator, e o que esta escrito naquela linha e o path. O nome da funcao
    existe no AST mas mora na linha de baixo, entao nao serve de ancora.
    """
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    prefixos = _prefixos_de_construtor(arvore)
    constantes = _constantes_de_modulo(arvore)
    achadas: list[Entrada] = []
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for verbo, no_path, objeto in _decorators_de_rota(no):
            lido = _resolver_path(no_path, constantes)
            if lido is None:
                # Cegueira DECLARADA. O modo de falha que este projeto repete e
                # sumir calado: quem le um mapa que nao avisa conclui que a
                # rota nao existe. Ancora no nome da funcao, que esta escrito
                # na linha do `def`, entao o --verificar prova o aviso tambem.
                achadas.append(Entrada(
                    secao="aviso",
                    chave=f"{verbo} com path que o gerador nao leu, "
                          f"em `{no.name}` - a lista de rotas esta incompleta",
                    simbolo=no.name,
                    arquivo=arquivo_rel,
                    linha=no.lineno,
                ))
                continue
            path, ancora = lido
            # `simbolo` e o que esta ESCRITO na linha (path cru ou o nome da
            # constante); so a `chave` leva o prefixo do router ja composto.
            achadas.append(Entrada(
                secao="rota",
                chave=f"{verbo} {prefixos.get(objeto, '')}{path}",
                simbolo=ancora,
                arquivo=arquivo_rel,
                linha=no_path.lineno,
            ))
    return achadas


def _alias_para_modulo(arvore: ast.Module) -> dict[str, str]:
    """{nome_local: stem_do_modulo} para os imports deste arquivo."""
    mapa: dict[str, str] = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            origem = (no.module or "").rsplit(".", 1)[-1]
            for a in no.names:
                mapa[a.asname or a.name] = origem
        elif isinstance(no, ast.Import):
            for a in no.names:
                mapa[a.asname or a.name] = a.name.rsplit(".", 1)[-1]
    return mapa


def prefixos_de_router(texto: str, arquivo_rel: str) -> list[tuple]:
    """Todo `include_router(x, prefix=...)` deste arquivo.

    Devolve [(stem_do_modulo | None, prefixo | None, "arquivo:linha")].
    None em qualquer posicao = nao deu para resolver estaticamente.
    include_router SEM prefix= nao entra: nao altera path nenhum.
    """
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    alias = _alias_para_modulo(arvore)
    achados: list[tuple] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        nome = alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", "")
        if nome != "include_router":
            continue
        kw = next((k for k in no.keywords if k.arg == "prefix"), None)
        if kw is None:
            continue
        prefixo = kw.value.value if isinstance(kw.value, ast.Constant) else None
        if not isinstance(prefixo, str):
            prefixo = None
        primeiro = no.args[0] if no.args else None
        stem = None
        if isinstance(primeiro, ast.Name):
            stem = alias.get(primeiro.id)
        elif isinstance(primeiro, ast.Attribute) and isinstance(primeiro.value, ast.Name):
            stem = alias.get(primeiro.value.id)
        achados.append((stem, prefixo, f"{arquivo_rel}:{no.lineno}"))
    return achados


def aplicar_prefixos(entradas: list[Entrada], includes: list[tuple]) -> list[Entrada]:
    """Compoe prefixo + path na `chave` das rotas. Nunca inventa.

    `simbolo` NUNCA muda: continua o path do decorator, que e o texto escrito na
    linha e o que o `--verificar` reabre. E por isso que compor a `chave` nao
    quebra a verificacao.
    """
    if not includes:
        return entradas
    por_stem: dict[str, set] = {}
    orfaos: list[str] = []
    for stem, prefixo, onde in includes:
        if stem is None:
            orfaos.append(onde)          # nao da para saber a quais rotas se aplica
        else:
            por_stem.setdefault(stem, set()).add(prefixo)

    saida: list[Entrada] = []
    for e in entradas:
        if e.secao != "rota":
            saida.append(e)
            continue
        stem = e.arquivo.rsplit("/", 1)[-1].removesuffix(".py")
        prefixos = por_stem.get(stem)
        if not prefixos:
            saida.append(e)
        elif len(prefixos) == 1 and None not in prefixos:
            verbo, path = e.chave.split(" ", 1)
            saida.append(replace(e, chave=f"{verbo} {next(iter(prefixos))}{path}"))
        else:
            # prefixo nao literal, ou dois prefixos diferentes para o mesmo modulo
            saida.append(replace(e, chave=f"{e.chave} ?"))

    for onde in sorted(set(orfaos)):
        arquivo, _, _linha = onde.rpartition(":")
        saida.append(Entrada(
            secao="aviso",
            chave="`include_router` com `prefix=` que nao deu para rastrear - "
                  "os paths deste produto podem estar incompletos",
            simbolo="",
            arquivo=arquivo,
            linha=0,
        ))
    return saida


def modelos(texto: str, arquivo_rel: str) -> list[Entrada]:
    """Toda classe com `__tablename__ = "..."` literal deste arquivo.

    A chave e o nome da TABELA, nao o da classe: e o nome da tabela que aparece
    na migration, no SQL do dono e na linha que o `--verificar` reabre.
    """
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    achados: list[Entrada] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ClassDef):
            continue
        for corpo in no.body:
            alvo_ok = (
                isinstance(corpo, ast.Assign)
                and len(corpo.targets) == 1
                and isinstance(corpo.targets[0], ast.Name)
                and corpo.targets[0].id == "__tablename__"
                and isinstance(corpo.value, ast.Constant)
                and isinstance(corpo.value.value, str)
            )
            if alvo_ok:
                tabela = corpo.value.value
                achados.append(Entrada(
                    secao="modelo",
                    chave=tabela,
                    simbolo=tabela,
                    arquivo=arquivo_rel,
                    linha=corpo.lineno,
                ))
    return achados


def _constante_str(no: ast.AST) -> tuple[str, str] | None:
    """(nome, valor) de `x = "s"` OU de `x: T = "s"`, no topo do modulo.

    As migrations do repo usam os DOIS estilos: as antigas escrevem
    `revision: str = "0001"` (AnnAssign) e as novas `revision = "0020_..."`
    (Assign). Ler so um dos dois perde metade dos arquivos e, pior, quebra a
    cadeia do head: cada arquivo perdido vira uma head solta.
    """
    if isinstance(no, ast.Assign):
        if len(no.targets) != 1 or not isinstance(no.targets[0], ast.Name):
            return None
        nome = no.targets[0].id
    elif isinstance(no, ast.AnnAssign):
        if not isinstance(no.target, ast.Name):
            return None
        nome = no.target.id
    else:
        return None
    if not isinstance(no.value, ast.Constant) or not isinstance(no.value.value, str):
        return None
    return nome, no.value.value


def _revisions(texto: str) -> tuple[str, str]:
    """(revision, down_revision) lidos como constantes de modulo, por AST.

    Nunca importa o modulo do Alembic: rodar uma migration para descobrir o id
    dela executaria codigo de produto (invariante do AGENTS.md).
    """
    revision = down = ""
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return "", ""
    for no in arvore.body:
        par = _constante_str(no)
        if par is None:
            continue
        nome, valor = par
        if nome == "revision":
            revision = valor
        elif nome == "down_revision":
            down = valor
    return revision, down


def migrations(pasta_versions: Path) -> tuple[list[Entrada], str]:
    """As migrations de UM produto e a head (a revision que ninguem aponta).

    Head com virgula = duas heads = migration divergente naquele produto. E um
    achado real, nao um bug do gerador: nao esconda somando ou escolhendo uma.
    """
    if not pasta_versions.is_dir():
        return [], ""
    entradas: list[Entrada] = []
    revisions: set[str] = set()
    apontadas: set[str] = set()
    for arquivo in sorted(pasta_versions.glob("*.py")):
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        revision, down = _revisions(texto)
        if not revision:
            continue
        revisions.add(revision)
        if down:
            apontadas.add(down)
        entradas.append(Entrada(
            secao="migration",
            chave=revision,
            simbolo=revision,
            arquivo=str(arquivo.name),
            linha=0,
        ))
    heads = sorted(revisions - apontadas)
    return entradas, (heads[0] if len(heads) == 1 else ",".join(heads))


PREFIXOS_DE_FLAG = ("REVY_", "MULTI_")
SUFIXOS_DE_FLAG = ("_ENABLED",)

# So o prefixo REVY_/MULTI_ deixava 16 flags de rollout fora contra 13 dentro,
# incluindo CHATBOT_WHATSAPP_MODO2_ENABLED, o gate do Modo 2 — a flag que mais
# se procura. O ensaio cego bateu nisso. Listar todas as 216 env vars lidas
# seria ruido (37 tem nome de secret); `_ENABLED` mira em rollout, que e o que
# esta secao promete.
NOME_DE_ENV = re.compile(r"[A-Z][A-Z0-9_]*")

# `_job.py` e `_workers.py` sao o padrao, mas o motor e o estoque chamam o deles
# de `app/worker.py`. So com os dois primeiros sufixos, esses dois produtos
# ficariam com ZERO worker no mapa - e worker que nao aparece no mapa e worker
# que ninguem lembra de subir no deploy.
SUFIXOS_DE_WORKER = ("_job.py", "_jobs.py", "worker.py", "workers.py")


def _e_arquivo_de_teste(arquivo_rel: str) -> bool:
    """`tests/test_rodizio_job.py` casa com `_job.py` e nao e worker nenhum.

    Sem esta guarda, cada `def test_...` de 7 arquivos de teste entra no mapa
    como se fosse um job de producao.
    """
    partes = arquivo_rel.split("/")
    nome = partes[-1]
    return (
        nome.startswith("test_")
        or nome == "conftest.py"
        or any(parte in {"tests", "test"} for parte in partes[:-1])
    )


# Modulos em que o arquivo INTEIRO e o worker: nao ha classe, a entrada e
# `main`. So o motor e o estoque fazem assim.
ARQUIVOS_QUE_SAO_O_WORKER = ("worker.py", "workers.py")
ENTRADA_DO_MODULO = "main"


def workers(texto: str, arquivo_rel: str) -> list[Entrada]:
    """Classes `*Worker`, mais o `main` de um modulo que E o worker.

    A regra antiga aceitava **qualquer** funcao publica de topo de arquivo de
    job, e a secao virou um despejo: 82 linhas das quais so 19 eram worker. O
    resto era ciclo de vida (`start_worker`, `stop_worker`, `get_worker` —
    sozinhos, 30 linhas), helper de env (`env_int`, `env_float`) e funcao de
    dominio do modulo (`avaliar_loja`, `texto_followup`, `processar_turno`).

    Nao mentia — os simbolos estavam nas linhas e o `--verificar` passava. Mas
    quem lia "Workers: 31" no cabecalho do portal concluia que ha 31 processos
    de fundo, quando ha 6. Secao que promete demais gasta a atencao que o mapa
    existe para poupar.

    Medido antes de trocar a regra: **todo** `*_job.py` do repo tem uma classe
    `*Worker`, entao a regra de funcao nunca foi necessaria para eles. Ela so
    faz falta em `app/worker.py` do motor e do estoque, onde nao ha classe. E
    nao ha worker escondido em classe de outro nome: as unicas classes com
    `start`/`stop` fora do padrao sao `_Periodico` (agendador privado e
    generico do `modo2_workers.py`) e as de `motor-simulacao/app/lifecycle.py`,
    que ligam e desligam **maquina do Fly**, nao worker.

    Fica de fora, de proposito, `chatbot-api/app/modo2_workers.py`: ele importa
    e sobe `RodizioWorker`, `FollowupWorker` e `CloudRetryWorker`, que ja estao
    no mapa cada um no seu arquivo. E lancador, nao worker.
    """
    if _e_arquivo_de_teste(arquivo_rel):
        return []
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    o_modulo_e_o_worker = arquivo_rel.endswith(ARQUIVOS_QUE_SAO_O_WORKER)
    achados: list[Entrada] = []
    for no in arvore.body:
        nome = getattr(no, "name", "")
        if not nome:
            continue
        e_worker = (
            isinstance(no, ast.ClassDef) and nome.endswith("Worker")
        ) or (
            o_modulo_e_o_worker
            and nome == ENTRADA_DO_MODULO
            and isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        if e_worker:
            achados.append(Entrada(
                secao="worker",
                chave=nome,
                simbolo=nome,
                arquivo=arquivo_rel,
                linha=no.lineno,
            ))
    if not achados and arquivo_rel.endswith(("_job.py", "_jobs.py")):
        # Job em estilo de funcao existiria fora das duas regras acima. Hoje
        # nao ha nenhum — todo `*_job.py` do repo tem sua classe `*Worker` — e
        # por isso este aviso nasce mudo. Mas estreitar criterio sem declarar o
        # que passou a ficar de fora e como as 25 rotas sumiram: o
        # `--verificar` so reabre o que ESTA no mapa, entao ausencia ninguem ve.
        achados.append(Entrada(
            secao="aviso",
            chave="arquivo de job sem classe `*Worker` - se o job aqui e uma "
                  "funcao, ele nao esta na secao Workers",
            simbolo="",
            arquivo=arquivo_rel,
            linha=0,
        ))
    return achados


# Chamadas que ESCREVEM ou apagam o ambiente. Sao a excecao, nao a regra: ver
# `_le_do_ambiente`.
ESCRITAS_DE_ENV = frozenset({
    "setenv", "delenv", "unsetenv", "putenv", "pop", "setdefault", "update",
})


def _le_do_ambiente(nome_chamada: str) -> bool:
    """A chamada esta LENDO uma variavel de ambiente?

    `os.getenv` e o caso obvio, mas as flags que mais importam NAO passam por
    ele: o portal le por `_env_bool("REVY_LOJA_COPILOTO_ENABLED", "0")`, o
    control por `_env_flag("REVY_CONTROL_DASHBOARD_ENABLED")` e o outbox por
    `_numero("...", 60)`. Casar so `getenv` perde exatamente as flags de
    rollout da Loja e do Control - as unicas que alguem procura no mapa.

    Por isso a regra e invertida: quem recebe o NOME de uma flag como primeiro
    argumento esta lendo, a menos que esteja na lista de escritas. Assim o
    proximo helper que alguem inventar ja entra sozinho.
    """
    return nome_chamada not in ESCRITAS_DE_ENV


def flags(texto: str, arquivo_rel: str) -> list[Entrada]:
    """Toda flag `REVY_*` / `MULTI_*` lida do ambiente, com o default do codigo.

    O default entra na `chave` porque e o unico jeito de o mapa responder "esta
    ligada?" sem abrir o arquivo. Sem default na chave = a chamada nao passa
    default literal (`_env_flag("X")`, que decide o default dentro do helper).
    `os.environ["REVY_X"] = "1"` NAO entra: isso e um teste ESCREVENDO no
    ambiente, nao o codigo declarando um default.
    """
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    vistos: dict[str, Entrada] = {}
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not no.args:
            continue
        alvo = no.func
        nome_chamada = (
            alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", "")
        )
        if not _le_do_ambiente(nome_chamada):
            continue
        primeiro = no.args[0]
        if not isinstance(primeiro, ast.Constant) or not isinstance(primeiro.value, str):
            continue
        nome = primeiro.value
        e_flag = nome.startswith(PREFIXOS_DE_FLAG) or nome.endswith(SUFIXOS_DE_FLAG)
        if not e_flag or nome in vistos:
            continue
        if not NOME_DE_ENV.fullmatch(nome):
            continue     # frase que so COMECA com o nome da flag (log, mensagem)
        rotulo = nome
        if len(no.args) > 1 and isinstance(no.args[1], ast.Constant):
            valor = no.args[1].value
            padrao = "''" if valor == "" else str(valor)
            rotulo = f"{nome} (default: {padrao})"
        vistos[nome] = Entrada(
            secao="flag",
            chave=rotulo,
            simbolo=nome,
            arquivo=arquivo_rel,
            linha=primeiro.lineno,
        )
    return list(vistos.values())


def _fora_do_projeto(caminho: Path, base: Path) -> bool:
    for parte in caminho.relative_to(base).parts:
        if parte in IGNORADOS or parte.startswith("test-tmp"):
            return True
    return False


def _nome_de_template(no: ast.Call) -> tuple[str, int] | None:
    """(nome, linha DA STRING) do template pedido numa chamada TemplateResponse.

    O repo escreve a chamada de TRES jeitos, e ler so um perde a maioria:
      `TemplateResponse("x.html", ctx)`            - assinatura antiga
      `TemplateResponse(request, "x.html", ctx)`   - assinatura nova do Starlette
      `TemplateResponse(request=request, name="x.html", ...)` - por keyword

    A linha e a da STRING, nao a do `TemplateResponse(`: quase toda chamada do
    repo quebra em varias linhas, e o `--verificar` exige que o texto da linha
    contenha o simbolo. Apontar para a linha do `(` daria falso negativo.
    """
    for kw in no.keywords:
        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, str):
                return kw.value.value, kw.value.lineno
    for arg in no.args[:2]:      # arg 0 (antiga) ou arg 1 (request vem antes)
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value, arg.lineno
    return None


def _renderizacoes(base_produto: Path) -> dict[str, tuple[str, int]]:
    """{nome_do_template: (arquivo_py, linha)} - quem renderiza o que."""
    mapa: dict[str, tuple[str, int]] = {}
    for py in sorted(base_produto.rglob("*.py")):
        if not py.is_file() or _fora_do_projeto(py, base_produto):
            continue
        try:
            arvore = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        rel = py.relative_to(base_produto).as_posix()
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            alvo = no.func
            chamada = (
                alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", "")
            )
            if chamada != "TemplateResponse":
                continue
            achado = _nome_de_template(no)
            if achado is None:
                continue
            nome, linha = achado
            mapa.setdefault(nome, (rel, linha))   # primeiro que renderiza, estavel
    return mapa


def templates(base_produto: Path) -> list[Entrada]:
    """Todo `.html` do produto, apontando para a rota que o renderiza.

    Template renderizado aponta para a linha do `TemplateResponse` (e o simbolo
    e o nome como esta escrito la). Template solto - que nenhuma rota renderiza
    - fica com `linha=0`, que no contrato do `--verificar` quer dizer "basta o
    arquivo existir". Nao se inventa linha para template que ninguem chama.
    """
    if not base_produto.is_dir():
        return []
    render = _renderizacoes(base_produto)
    # do nome mais longo para o mais curto: "loja/x.html" ganha de "x.html"
    nomes = sorted(render, key=len, reverse=True)
    achados: list[Entrada] = []
    for html in sorted(base_produto.rglob("*.html")):
        if not html.is_file() or _fora_do_projeto(html, base_produto):
            continue
        # HTML sob tests/ nao e template: no motor sao paginas de banco salvas
        # como fixture do Playwright. Lista-las faria o mapa dizer que o motor
        # renderiza HTML, que e falso — a unica forma que sobra de o mapa mentir.
        if "tests" in html.relative_to(base_produto).parts:
            continue
        rel = html.relative_to(base_produto).as_posix()
        casado = next(
            (n for n in nomes if rel == n or rel.endswith("/" + n.lstrip("/"))), None
        )
        if casado is None:
            achados.append(Entrada(
                secao="template",
                chave=rel,
                simbolo=html.name,
                arquivo=rel,
                linha=0,
            ))
        else:
            arquivo_py, linha = render[casado]
            achados.append(Entrada(
                secao="template",
                chave=rel,
                simbolo=casado,
                arquivo=arquivo_py,
                linha=linha,
            ))
    return achados


@dataclass(frozen=True)
class Relacao:
    """Uma chave estrangeira, com a cardinalidade que o SQLAlchemy ja declara.

    `de` e `para` sao nomes de TABELA (mesma chave que `modelos` emite), nao de
    classe — e' o nome da tabela que aparece na migration e no SQL do dono.
    """
    de: str
    para: str
    coluna: str
    cardinalidade: str      # "n:1" | "1:1"
    opcional: bool          # nullable=True -> a ponta pode nao existir
    arquivo: str
    linha: int


def _fk_alvo(no: ast.AST) -> str | None:
    """`ForeignKey("lojas.id")` -> `"lojas"`. Qualquer outra coisa -> None."""
    if not (isinstance(no, ast.Call) and _nome_chamado(no) == "ForeignKey"):
        return None
    if not (no.args and isinstance(no.args[0], ast.Constant)
            and isinstance(no.args[0].value, str)):
        return None
    return no.args[0].value.split(".")[0] or None


def _nome_chamado(no: ast.Call) -> str:
    alvo = no.func
    if isinstance(alvo, ast.Name):
        return alvo.id
    if isinstance(alvo, ast.Attribute):
        return alvo.attr
    return ""


def _kw_verdadeiro(chamada: ast.Call, nome: str) -> bool:
    for kw in chamada.keywords:
        if kw.arg == nome and isinstance(kw.value, ast.Constant):
            return bool(kw.value.value)
    return False


def relacoes(texto: str, arquivo_rel: str) -> list[Relacao]:
    """As arestas do mapa conceitual de banco, lidas do proprio modelo.

    A cardinalidade NAO e' chutada — ela ja esta escrita no SQLAlchemy, e so
    nao estava sendo lida:

    - `ForeignKey("lojas.id")` numa coluna comum: varias linhas daqui apontam
      pra UMA de la. **n:1**.
    - a mesma FK com `primary_key=True` ou `unique=True`: a FK E' a chave, entao
      existe no maximo UMA linha daqui por linha de la. **1:1**. E' o caso de
      `agente_config`, `rodizio_ponteiro` e `loja_operacional_projecao` no
      Chatbot — tres tabelas que sao extensao de `lojas`, e o desenho antigo
      mostrava igualzinho a uma tabela de muitos.
    - `nullable=True`: a ponta pode nao existir (`opcional`), que e' diferente
      de nao existir relacao.

    n:n nao e' inferido aqui de proposito: no SQLAlchemy ele aparece como
    `relationship(secondary=...)` ou como tabela de associacao (PK composta so
    de FK). Nenhum produto da Revy tem uma hoje — inventar o caso sem ter onde
    conferir seria desenhar o que nao existe.

    Le como TEXTO (`ast`), nunca importando `app` (AGENTS.md secao 5).
    """
    try:
        arvore = ast.parse(texto)
    except SyntaxError:
        return []
    achados: list[Relacao] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ClassDef):
            continue
        tabela = _tabela_da_classe(no)
        if not tabela:
            continue
        for corpo in no.body:
            # `x: Mapped[str] = mapped_column(ForeignKey(...))` (AnnAssign) e
            # `x = Column(ForeignKey(...))` (Assign): os dois estilos existem
            # no repo, entao os dois entram.
            valor = getattr(corpo, "value", None)
            alvos = getattr(corpo, "targets", None) or [getattr(corpo, "target", None)]
            if not isinstance(valor, ast.Call) or not alvos or alvos[0] is None:
                continue
            if not isinstance(alvos[0], ast.Name):
                continue
            for arg in list(valor.args) + [kw.value for kw in valor.keywords]:
                destino = _fk_alvo(arg)
                if not destino:
                    continue
                um_pra_um = (_kw_verdadeiro(valor, "primary_key")
                             or _kw_verdadeiro(valor, "unique"))
                achados.append(Relacao(
                    de=tabela, para=destino, coluna=alvos[0].id,
                    cardinalidade="1:1" if um_pra_um else "n:1",
                    opcional=_kw_verdadeiro(valor, "nullable"),
                    arquivo=arquivo_rel, linha=corpo.lineno,
                ))
    return achados


def _tabela_da_classe(classe: ast.ClassDef) -> str | None:
    for corpo in classe.body:
        if (isinstance(corpo, ast.Assign) and len(corpo.targets) == 1
                and isinstance(corpo.targets[0], ast.Name)
                and corpo.targets[0].id == "__tablename__"
                and isinstance(corpo.value, ast.Constant)
                and isinstance(corpo.value.value, str)):
            return corpo.value.value
    return None
