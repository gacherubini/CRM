"""Gera mapa/<produto>.md a partir do codigo. Stdlib apenas.

Nao importa `app` de produto nenhum (invariante do AGENTS.md secao 5): tudo o
que entra aqui foi lido como texto e parseado com `ast` pelos extratores.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import cruzamentos
import extratores
import saude
import varredura
from varredura import Entrada

PASTA_MAPA = Path(__file__).resolve().parent / "mapa"

# Onde o Alembic de TODO produto guarda as versions. Medido em 23/08: os cinco
# produtos com migration usam exatamente esta pasta (o catalogo nao tem
# migration nenhuma). Uma constante so, porque o mesmo valor localiza o arquivo
# e recompoe o caminho que vai para o mapa - se fossem dois, um dia divergiam.
SUBPASTA_DE_MIGRATIONS = "alembic/versions"

ORDEM = ("aviso", "rota", "modelo", "worker", "flag", "migration", "template")
TITULOS = {
    "aviso": "Avisos do gerador",   # so aparece quando ha algo a avisar
    "rota": "Rotas", "modelo": "Modelos", "worker": "Workers",
    "flag": "Flags", "migration": "Migrations", "template": "Templates",
}

# A UNICA parte escrita a mao do mapa, porque nao e inferivel do codigo - e e
# onde moram as duas excecoes que sempre mordem quem chega agora.
TESTES: dict[str, dict[str, str]] = {
    "chatbot-api": {
        "macos": "cd chatbot-api && .venv/bin/python -m pytest -q",
        "windows": r"cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "portal-gestao": {
        "macos": "cd portal-gestao && .venv/bin/python -m pytest -q",
        "windows": (
            r"cd portal-gestao && .\.venv\Scripts\python.exe "
            r"-m pytest -p no:cacheprovider -q"
        ),
        "nota": (
            "No Windows, -p no:cacheprovider: o .pytest_cache do Portal quebra "
            "com WinError 183."
        ),
    },
    "motor-simulacao": {
        "macos": "cd motor-simulacao && .venv/bin/python -m pytest -q",
        "windows": r"cd motor-simulacao && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "estoque-api": {
        "macos": "cd estoque-api && .venv/bin/python -m pytest -q",
        "windows": r"cd estoque-api && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "catalogo-publico": {
        "macos": "cd catalogo-publico && .venv/bin/python -m pytest -q",
        "windows": r"cd catalogo-publico && .\.venv\Scripts\python.exe -m pytest -q",
    },
    "revy-trafego": {
        "macos": "cd revy-trafego && ../portal-gestao/.venv/bin/python -m pytest -q",
        "windows": (
            r"cd revy-trafego && ..\portal-gestao\.venv\Scripts\python.exe "
            r"-m pytest -q"
        ),
        "nota": "NAO tem .venv proprio. Usa o do portal-gestao.",
    },
}


def sha_atual(raiz: Path) -> str:
    saida = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=raiz, capture_output=True, text=True, check=False,
    )
    return saida.stdout.strip() or "desconhecido"


# Onde o mapa vive no git. O frescor so faz sentido para a copia versionada,
# entao este caminho e fixo mesmo quando PASTA_MAPA e trocada em teste.
CAMINHO_DO_MAPA_NO_GIT = ".claude/skills/revy-research/mapa"


def commit_do_mapa(raiz: Path) -> str:
    """O commit que atualizou `mapa/` por ultimo. String vazia se nunca houve.

    NAO usar o sha do selo para isto. O selo e lido ANTES do commit que grava o
    mapa, entao fica sempre um commit atras — e quando o `AGENTS.md` §6 e
    obedecido (regerar e commitar junto com o codigo), o diff a partir do selo
    lista as mudancas do proprio commit certo e acusa o produto de
    desatualizado. O aviso dispararia justamente quando o agente acertou, que e
    o modo de falha que o desenho existe para evitar.
    """
    saida = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", CAMINHO_DO_MAPA_NO_GIT],
        cwd=raiz, capture_output=True, text=True, check=False,
    )
    return saida.stdout.strip()


def frescor(raiz: Path, produtos: list[str]) -> dict[str, list[str]]:
    """{produto: arquivos mudados desde o commit que atualizou o mapa}.

    Produto sem mudanca nao aparece: silencio e a resposta certa. A
    granularidade e por produto de proposito — mexer no `site/` nao pode
    disparar aviso sobre o mapa do motor.
    """
    base = commit_do_mapa(raiz)
    if not base:
        return {}
    atrasados: dict[str, list[str]] = {}
    for produto in produtos:
        saida = subprocess.run(
            ["git", "diff", "--name-only", f"{base}..HEAD", "--", f"{produto}/"],
            cwd=raiz, capture_output=True, text=True, check=False,
        )
        mudados = [linha for linha in saida.stdout.splitlines() if linha.strip()]
        if mudados:
            atrasados[produto] = mudados
    return atrasados


def _com_pasta_de_migration(entrada: Entrada) -> Entrada:
    """Recompoe `alembic/versions/<nome>` no `arquivo` da migration.

    `extratores.migrations` guarda so o NOME do arquivo, porque a pasta e fixa
    e ele recebe a pasta pronta. Todas as outras secoes guardam caminho
    relativo a pasta do produto - que e o que o contrato da `Entrada` pede e o
    que o `--verificar` vai reabrir. Sem esta recomposicao o mapa mandaria o
    leitor para `0025_x.py`, que nao existe a partir da raiz do produto.

    Montar o caminho pela `chave` seria pior ainda: no motor a revision e
    "0014" e o arquivo e "0014_cliente_operacional_projecao.py".
    """
    if entrada.secao != "migration" or "/" in entrada.arquivo:
        return entrada
    return replace(entrada, arquivo=f"{SUBPASTA_DE_MIGRATIONS}/{entrada.arquivo}")


def _pasta_de_versions(raiz: Path, produto: str) -> Path:
    return raiz / produto / SUBPASTA_DE_MIGRATIONS


def coletar(raiz: Path, produto: str) -> list[Entrada]:
    base = raiz / produto
    entradas: list[Entrada] = []
    includes: list[tuple] = []
    for caminho in varredura.arquivos_py(raiz, produto):
        rel = caminho.relative_to(base).as_posix()
        texto = caminho.read_text(encoding="utf-8", errors="replace")
        entradas.extend(extratores.rotas(texto, rel))
        entradas.extend(extratores.modelos(texto, rel))
        entradas.extend(extratores.workers(texto, rel))
        entradas.extend(extratores.flags(texto, rel))
        includes.extend(extratores.prefixos_de_router(texto, rel))
    # Task 3 Step 3b: prefix= e cross-file, entao so da para aplicar aqui,
    # com o produto inteiro na mao. Hoje `includes` vem vazio e isto e no-op.
    entradas = extratores.aplicar_prefixos(entradas, includes)
    entradas.extend(extratores.templates(base))
    de_migration, _ = extratores.migrations(_pasta_de_versions(raiz, produto))
    entradas.extend(_com_pasta_de_migration(e) for e in de_migration)
    return entradas


def head_de(raiz: Path, produto: str) -> str:
    _, head = extratores.migrations(_pasta_de_versions(raiz, produto))
    return head


def render(produto: str, entradas: list[Entrada], head: str, sha: str) -> str:
    por_secao: dict[str, list[Entrada]] = {s: [] for s in ORDEM}
    for e in entradas:
        por_secao.setdefault(e.secao, []).append(e)

    contagem = " · ".join(
        f"{len(por_secao[s])} {TITULOS[s].lower()}"
        for s in ORDEM if s != "aviso" and por_secao[s]
    )
    linhas = [
        f"# {produto} · {contagem}",
        "",
        f"Gerado de `{sha}`. NAO editar a mao — saida de `gerar_mapa.py`.",
        f"Migration head: `{head or 'n/a'}`",
        "",
    ]
    for secao in ORDEM:
        itens = por_secao.get(secao) or []
        if not itens:
            continue
        linhas.append(f"## {TITULOS[secao]}")
        linhas.append("")
        for e in sorted(itens, key=lambda x: (x.arquivo, x.linha, x.chave)):
            # linha 0 = "basta o arquivo existir" (contrato do --verificar).
            # Escrever "arquivo:0" mandaria o leitor para uma linha que nao ha.
            alvo = f"{e.arquivo}:{e.linha}" if e.linha else e.arquivo
            linhas.append(f"- `{e.chave}` — {alvo}")
        linhas.append("")

    testes = TESTES[produto]
    linhas.append("## Testes")
    linhas.append("")
    if "nota" in testes:
        linhas.append(f"**{testes['nota']}**")
        linhas.append("")
    linhas.append(f"- macOS: `{testes['macos']}`")
    linhas.append(f"- Windows: `{testes['windows']}`")
    linhas.append("")
    return "\n".join(linhas)


def paths_declarados(entradas: list[Entrada]) -> set[str]:
    """Paths normalizados das rotas de um produto, para os cruzamentos.

    Sai da CHAVE, nunca do simbolo. O `simbolo` e o path cru escrito na linha do
    decorator, que e o que o `--verificar` reabre; a `chave` e a que leva o
    prefixo do `APIRouter(prefix=...)` ja composto. Ler o simbolo aqui faz as 4
    rotas do `api_v1.py` do control aparecerem como orfas de servidor.

    Existe como funcao para haver UMA definicao: quando isto estava copiado no
    teste, a copia ficou para tras e o teste passou a conferir contra si mesmo.
    """
    return {
        cruzamentos.normalizar(e.chave.split(" ", 1)[1])
        for e in entradas
        if e.secao == "rota"
    }


NUMERO_DA_PAGINA = re.compile(r'(data-numero="(\w+)">)[\d.]*<')


def numeros_vivos(sk: Path) -> dict[str, int]:
    """O que a `como-funciona.html` promete, medido no repo agora."""
    conta = lambda p: len([f for f in (sk / p).glob("*.md") if f.name != "INDEX.md"])
    vivos = {
        "produtos": len(varredura.PRODUTOS),
        "learnings": conta("learnings"),
        "decisoes": conta("decisoes"),
        "skill_linhas": len((sk / "SKILL.md").read_text(encoding="utf-8").splitlines()),
    }
    selo = PASTA_MAPA / "_frescor.json"
    if selo.exists():
        dados = json.loads(selo.read_text(encoding="utf-8"))
        vivos["entradas"] = sum(len(v) for v in dados.get("inventario", {}).values())
    return vivos


def atualizar_pagina(sk: Path) -> list[str]:
    """Reescreve so os `data-numero` da pagina; o resto e desenho a mao.

    Em 24/08 a suite reprovou porque a pagina dizia 32 learnings e a pasta
    tinha 34 — dois escritos na noite anterior. O teste estava certo: o defeito
    era a pagina depender de alguem lembrar de contar. Contador e saida de
    script, como o mapa.
    """
    pagina = sk / "como-funciona.html"
    if not pagina.exists():
        return []
    vivos = numeros_vivos(sk)
    trocados: list[str] = []

    def troca(m: re.Match) -> str:
        chave = m.group(2)
        if chave not in vivos:
            return m.group(0)
        antes = m.group(0)
        depois = f"{m.group(1)}{vivos[chave]}<"
        if antes != depois:
            trocados.append(chave)
        return depois

    novo = NUMERO_DA_PAGINA.sub(troca, pagina.read_text(encoding="utf-8"))
    if trocados:
        pagina.write_text(novo, encoding="utf-8")
    return trocados


CAMINHO_DA_SKILL_NO_GIT = ".claude/skills/revy-research"
_PAGINA_NO_GIT = f"{CAMINHO_DA_SKILL_NO_GIT}/como-funciona.html"


def mexeu_em_fonte_do_mapa(arquivos) -> bool:
    """O commit toca alguma coisa de que o mapa e feito?

    Nome de produto so conta como PASTA RAIZ: `docs/chatbot-api-notas.md` fala
    de produto e nao e produto. E a propria skill fica de fora — senao o
    gatilho se realimenta, regerando porque o mapa mudou.
    """
    for bruto in arquivos:
        rel = bruto.replace("\\", "/").strip()
        if not rel or rel.startswith(CAMINHO_DA_SKILL_NO_GIT):
            continue
        raiz = rel.split("/", 1)[0]
        if raiz in varredura.FONTES_DO_MAPA:
            return True
    return False


def escrever_tudo(raiz: Path) -> None:
    PASTA_MAPA.mkdir(parents=True, exist_ok=True)
    sha = sha_atual(raiz)
    inventario: dict[str, list[dict]] = {}
    rotas_por_produto: dict[str, set[str]] = {}
    for produto in varredura.PRODUTOS:
        entradas = coletar(raiz, produto)
        head = head_de(raiz, produto)
        (PASTA_MAPA / f"{produto}.md").write_text(
            render(produto, entradas, head, sha), encoding="utf-8"
        )
        inventario[produto] = [asdict(e) for e in entradas]
        rotas_por_produto[produto] = paths_declarados(entradas)
        print(f"{produto}: {len(entradas)} entradas")
    # Cruzamentos reaproveita o `inventario` que o laco acabou de preencher -
    # sem segunda coleta. Sai para arquivo proprio e NAO entra no selo: o
    # --verificar so cobra `Entrada`, e suspeita nao vira contrato.

    (PASTA_MAPA / "_cruzamentos.md").write_text(
        cruzamentos.render(raiz, rotas_por_produto), encoding="utf-8"
    )
    print(f"cruzamentos: {sum(len(v) for v in rotas_por_produto.values())} rotas declaradas")
    (PASTA_MAPA / "_frescor.json").write_text(
        json.dumps({"sha": sha, "inventario": inventario}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"selo de frescor: {sha}")
    # Pela PASTA_MAPA, nunca pelo `__file__`: a suite redireciona a PASTA_MAPA
    # para tmp, e olhar o `__file__` fazia o gerador escrever na pagina do repo
    # no meio do teste — rodar teste sujava o working tree.
    trocados = atualizar_pagina(PASTA_MAPA.parent)
    if trocados:
        print(f"como-funciona.html: {', '.join(trocados)} atualizado(s)")


def verificar(raiz: Path) -> list[str]:
    """Reabre cada `arquivo:linha` do selo e prova que a promessa se cumpre.

    Contrato da `Entrada`, literal: `linha > 0` -> o texto daquela linha
    precisa CONTER o `simbolo`; `linha == 0` -> basta o arquivo existir.

    De proposito NAO regenera nada antes de conferir. Se regenerasse, o mapa
    concordaria consigo mesmo e o comando passaria sempre - a graca e pegar o
    mapa commitado envelhecendo em relacao ao codigo.

    O `arquivo` da `Entrada` ja e relativo a pasta do produto, migration
    inclusive (`_com_pasta_de_migration` recompoe `alembic/versions/` na
    geracao). Recompor de novo aqui mandaria toda migration para
    `alembic/versions/alembic/versions/...` e inventaria centenas de
    divergencias que nao existem.
    """
    caminho = PASTA_MAPA / "_frescor.json"
    if not caminho.exists():
        return ["mapa/_frescor.json nao existe - rode o gerador"]
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    problemas: list[str] = []
    for produto, entradas in dados.get("inventario", {}).items():
        base = raiz / produto
        for bruta in entradas:
            alvo = base / bruta["arquivo"]
            if not alvo.exists():
                problemas.append(f"{produto}: sumiu {bruta['arquivo']}")
                continue
            if bruta["linha"] <= 0:
                continue
            linhas = alvo.read_text(encoding="utf-8", errors="replace").splitlines()
            if bruta["linha"] > len(linhas):
                problemas.append(
                    f"{produto}: {bruta['arquivo']}:{bruta['linha']} "
                    f"passou do fim do arquivo ({len(linhas)} linhas)"
                )
                continue
            if bruta["simbolo"] not in linhas[bruta["linha"] - 1]:
                problemas.append(
                    f"{produto}: {bruta['arquivo']}:{bruta['linha']} "
                    f"nao contem {bruta['simbolo']!r}"
                )
    return problemas


def avisar_reconferencia(sk: Path, alvos: list[str], hoje: date | None = None) -> int:
    """Cola o carimbo dos learnings na saida que o passo 2 ja roda.

    Sem isto o `verificado_em` e campo decorativo: ninguem o cobra, e o
    learning dos bancos prova o que um campo nao-cobrado vale — afirmou
    "Portal e Control sao SQLite" por uma semana depois de os dois virarem
    Postgres. Aviso, nunca erro: quem falha e o `--verificar`.
    """
    hoje = hoje or date.today()
    vistos: dict[str, saude.Reconferir] = {}
    for alvo in alvos:
        for v in saude.a_reconferir(sk, hoje, produto=alvo):
            vistos[v.arquivo] = v
    if not vistos:
        return 0
    vencidos = sorted(vistos.values(), key=lambda v: v.arquivo)
    print(f"{len(vencidos)} learning(s) pedem reconferencia antes de decidir em cima:")
    for v in vencidos[:4]:
        print(f"  {v.arquivo} ({v.fonte}, {v.motivo})")
    if len(vencidos) > 4:
        print(f"  ... e mais {len(vencidos) - 4}")
    print("conferiu? carimbe `verificado_em` no arquivo. Carimbo sem conferencia "
          "e o defeito que o campo existe para consertar.")
    return len(vencidos)


def pre_commit(raiz: Path, staged: list[str] | None = None) -> int:
    """Roda dentro do hook `.githooks/pre-commit`.

    Divide o trabalho pelo que da para automatizar com honestidade: o que e
    **saida de script** (o mapa e os contadores da pagina) ele conserta e
    coloca no proprio commit; o que precisa de **julgamento humano** (learning
    apontando para arquivo que nao existe mais) ele bloqueia, porque nenhum
    script sabe reescrever o texto certo.

    Nao bloqueia por erro do gerador: ferramenta quebrada travando o commit de
    todo mundo e pior que mapa velho, e o `--verificar` da suite ainda pega.
    """
    sk = Path(__file__).resolve().parent
    if staged is None:
        saida = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=raiz, capture_output=True, text=True, check=False,
        )
        staged = [linha for linha in saida.stdout.splitlines() if linha.strip()]
    if mexeu_em_fonte_do_mapa(staged):
        try:
            escrever_tudo(raiz)   # ja passa pela pagina no fim
        except Exception as erro:   # noqa: BLE001 - ver docstring
            print(f"AVISO: o gerador do mapa falhou ({erro}); commit segue.")
        else:
            subprocess.run(
                ["git", "add", "--", CAMINHO_DO_MAPA_NO_GIT, _PAGINA_NO_GIT],
                cwd=raiz, check=False,
            )
            print("mapa regerado e incluido no commit (AGENTS.md secao 6)")
    elif atualizar_pagina(sk):
        # Os contadores da pagina vem de `learnings/`, `decisoes/` e do
        # `SKILL.md` — nenhum deles e fonte do mapa. Sem este ramo, o commit
        # mais comum da camada (so learning) continuava deixando a pagina
        # mentindo, que foi o que aconteceu tres vezes em 24/08.
        subprocess.run(
            ["git", "add", "--", _PAGINA_NO_GIT], cwd=raiz, check=False,
        )
        print("como-funciona.html: contadores atualizados e incluidos no commit")
    mortas = saude.citacoes_mortas(sk, raiz)
    for m in mortas:
        print(f"CITACAO MORTA {m}")
    if mortas:
        print(
            f"{len(mortas)} citacao(oes) morta(s): um learning manda abrir algo "
            "que nao existe mais. Conserte o texto ou apague a nota — script "
            "nenhum sabe escrever a frase certa no lugar."
        )
        return 1
    return 0


def main(argv: list[str]) -> int:
    raiz = varredura.raiz_repo()
    if "--pre-commit" in argv:
        return pre_commit(raiz)
    if "--verificar" in argv:
        sk = Path(__file__).resolve().parent
        problemas = verificar(raiz)
        for p in problemas:
            print(f"DIVERGENCIA {p}")
        # A camada de prosa entra no MESMO comando de proposito: checagem que
        # precisa ser lembrada e checagem que nao acontece.
        mortas = saude.citacoes_mortas(sk, raiz)
        for p in mortas:
            print(f"CITACAO MORTA {p}")
        if problemas:
            print(
                f"{len(problemas)} divergencias - o mapa esta velho. "
                "Rode sem --verificar."
            )
        if mortas:
            print(
                f"{len(mortas)} citacao(oes) morta(s) em learnings/decisoes - "
                "conserte o texto ou apague a nota."
            )
        if problemas or mortas:
            return 1
        print("mapa confere com o codigo")
        print("learnings e decisoes nao apontam para o vazio")
        return 0
    if "--frescor" in argv:
        alvos = ([a for a in argv if not a.startswith("--")]
                 or list(varredura.FONTES_DO_MAPA))
        # Sem esta checagem o argumento ia direto para o git como pathspec, e
        # pasta que nao existe nao muda: `--frescor Motor` respondia "mapa em
        # dia". E "Motor", "Estoque", "Revy Loja" sao os nomes da tabela do
        # AGENTS.md secao 2 — o unico lugar onde o agente aprende como os
        # produtos se chamam ensinava exatamente os argumentos que este comando
        # engolia calado, e o passo 2 do protocolo manda seguir calado quando
        # ouve "mapa em dia". Falso "tudo certo" e pior que erro nenhum.
        desconhecidos = [a for a in alvos if a not in varredura.FONTES_DO_MAPA]
        if desconhecidos:
            print(f"nao conheco: {', '.join(desconhecidos)}")
            print(f"use um de: {', '.join(varredura.FONTES_DO_MAPA)}")
            return 2
        atrasados = frescor(raiz, alvos)
        if not atrasados:
            print("mapa em dia")
        else:
            for produto, arquivos in atrasados.items():
                print(f"{produto}: {len(arquivos)} arquivo(s) mudaram desde o mapa")
                for a in arquivos[:5]:
                    print(f"  {a}")
                if len(arquivos) > 5:
                    print(f"  ... e mais {len(arquivos) - 5}")
            print("regere com `python gerar_mapa.py` (no Mac, python3)")
        avisar_reconferencia(Path(__file__).resolve().parent, alvos)
        return 0   # aviso, nao erro: quem falha e o --verificar
    escrever_tudo(raiz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
