"""Pre-flight da revy-deploy: decide o que precisa subir e bloqueia o que morde.

Nada aqui deploya. Este modulo so responde duas perguntas:
  1. o que mudou desde o que esta em prod, e para qual alvo isso vai;
  2. ha alguma armadilha conhecida armada agora.

O deploy em si esta no SKILL.md, porque e ele que precisa de julgamento.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- constantes

# Produtos que o Dockerfile.app empacota numa imagem so.
PRODUTOS_BUNDLE = (
    "portal-gestao",
    "revy-trafego",
    "chatbot-api",
    "estoque-api",
    "catalogo-publico",
    "motor-simulacao",
)

# Produtos que servem CSS proprio. Sao DOIS app.css, com ?v= independentes.
PRODUTOS_COM_CSS = ("portal-gestao", "revy-trafego")

# Dentro de deploy/fly/3vm/ nem tudo vai para o mesmo app.
ARQUIVOS_SO_N8N = {"fly.n8n.toml", "run-n8n.sh", "prepare-workflow.ps1"}
ARQUIVOS_SO_MOTOR = {"fly.worker.toml", "Dockerfile.worker", ".dockerignore.worker"}
ARQUIVOS_MOTOR_E_BUNDLE = {"motor-entrypoint.sh", "run-motor.sh"}

URL_HEALTHZ = "https://app2037.fly.dev/healthz"
URL_SITE_BUILD = "https://revyapp.com.br/build.txt"


def raiz_repo(inicio: Path | None = None) -> Path:
    """Sobe ate achar o AGENTS.md. A skill roda de qualquer subpasta."""
    atual = (inicio or Path(__file__)).resolve()
    for candidato in [atual, *atual.parents]:
        if (candidato / "AGENTS.md").exists():
            return candidato
    raise RuntimeError("nao achei a raiz do repo (AGENTS.md)")


# ------------------------------------------------------------------ roteador


def alvos_para(caminhos: list[str]) -> set[str]:
    """Caminhos mudados -> apps que precisam subir.

    O que nao esta aqui nao sobe: doc, teste, plano e mapa nao vao para prod.
    """
    alvos: set[str] = set()
    for bruto in caminhos:
        caminho = bruto.strip().replace("\\", "/")
        if not caminho:
            continue
        partes = caminho.split("/")
        topo = partes[0]

        if topo == "site":
            alvos.add("site")
            continue

        # O systemMessage do bot mora no workflow, nao no chatbot-api.
        if topo == "n8n":
            alvos.add("n8n2037")
            continue

        if caminho.startswith("deploy/fly/3vm/"):
            arquivo = partes[-1]
            if arquivo in ARQUIVOS_SO_N8N:
                alvos.add("n8n2037")
            elif arquivo in ARQUIVOS_SO_MOTOR:
                alvos.add("motor2037")
            elif arquivo in ARQUIVOS_MOTOR_E_BUNDLE:
                alvos.update({"app2037", "motor2037"})
            else:
                alvos.add("app2037")
            continue

        if topo in PRODUTOS_BUNDLE and len(partes) > 1 and partes[1] in ("app", "alembic"):
            alvos.add("app2037")
            # motor-api vive no bundle; o worker Playwright e outro app.
            if topo == "motor-simulacao":
                alvos.add("motor2037")

    return alvos


# ---------------------------------------------------------------- cache bust


def versoes_css(raiz: Path) -> dict[str, dict[str, str]]:
    """{produto: {template: versao do ?v=}}.

    O Portal escreve `app.css?v=v15`; o Control escreve
    `{{ public_path('/static/css/app.css') }}?v=v12`. Um regex ancorado no
    `app.css?v=` acha so o Portal e deixa o Control servir CSS velho.
    """
    achados: dict[str, dict[str, str]] = {}
    for produto in PRODUTOS_COM_CSS:
        templates = raiz / produto / "app" / "templates"
        if not templates.is_dir():
            continue
        por_arquivo: dict[str, str] = {}
        for html in sorted(templates.rglob("*.html")):
            for linha in html.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "app.css" not in linha:
                    continue
                achado = re.search(r"\?v=([\w.\-]+)", linha)
                if achado:
                    por_arquivo[html.name] = achado.group(1)
                    break
        if por_arquivo:
            achados[produto] = por_arquivo
    return achados


def versoes_divergentes(por_arquivo: dict[str, str]) -> list[str]:
    """Templates cujo ?v= nao acompanha o base.html.

    Bumpar so o base.html e o erro classico: login, convite e as telas de
    senha tem `?v=` proprio e continuam servindo o CSS antigo.
    """
    if not por_arquivo:
        return []
    referencia = por_arquivo.get("base.html")
    if referencia is None:
        referencia = max(set(por_arquivo.values()), key=list(por_arquivo.values()).count)
    return [arq for arq, versao in por_arquivo.items() if versao != referencia]


def cache_bust_pendente(
    caminhos: list[str],
    versoes_antes: dict[str, str],
    versoes_agora: dict[str, str],
) -> list[str]:
    """Produtos cujo app.css mudou sem o ?v= subir.

    Sem o bump, prod serve o CSS velho e a mudanca simplesmente nao aparece.
    """
    pendentes = []
    for produto in PRODUTOS_COM_CSS:
        css = f"{produto}/app/static/css/app.css"
        mexeu = any(c.replace("\\", "/") == css for c in caminhos)
        if mexeu and versoes_antes.get(produto) == versoes_agora.get(produto):
            pendentes.append(produto)
    return pendentes


# ------------------------------------------------------------------ git / io


def _git(raiz: Path, *args: str) -> str:
    saida = subprocess.run(
        ["git", *args], cwd=raiz, capture_output=True, text=True, check=True
    )
    return saida.stdout


def repo_limpo(raiz: Path) -> tuple[bool, list[str]]:
    """`fly deploy` empacota a ARVORE LOCAL, nao o commit.

    Subir com o repo sujo poe em prod codigo que nao existe em lugar nenhum —
    e o repo e o unico lugar onde alguem vai procurar depois.
    """
    linhas = [l for l in _git(raiz, "status", "--porcelain").splitlines() if l.strip()]
    return (not linhas), linhas


def arquivos_mudados(raiz: Path, sha_a: str, sha_b: str = "HEAD") -> list[str]:
    return [l for l in _git(raiz, "diff", "--name-only", f"{sha_a}..{sha_b}").splitlines() if l]


def sha_atual(raiz: Path) -> str:
    return _git(raiz, "rev-parse", "--short", "HEAD").strip()


def carimbar_site(raiz: Path) -> Path:
    """Escreve site/build.txt com o SHA do HEAD.

    Por script, nao com `>` do shell: o PowerShell 5.1 grava UTF-16/BOM e o
    pos-flight passaria a reprovar por codificacao, nao por deploy errado.
    O arquivo e gitignorado e vai ao ar junto com a pasta.
    """
    destino = raiz / "site" / "build.txt"
    destino.write_text(sha_atual(raiz) + "\n", encoding="ascii")
    return destino


def sha_do_healthz(corpo: str) -> str | None:
    """Le o carimbo do /healthz. None = nao da para rotear.

    None acontece em dois casos, e os dois significam 'nao sei o que esta la':
    prod anterior ao carimbo, ou health falhando.
    """
    achado = re.search(r"\bsha:([\w.\-]+)", corpo or "")
    return achado.group(1) if achado else None


# A Cloudflare recusa o User-Agent padrao do urllib ("Python-urllib/3.x") com
# 403 na frente do revyapp.com.br. Sem este cabecalho o pos-flight do site da
# **falso negativo**: o deploy foi certo, o `curl` responde 200, e o verificar.py
# anuncia "nao respondeu" — indistinguivel de falha real, que e como se aprende a
# ignorar a checagem que existe para pegar falha silenciosa.
_UA = "revy-deploy/1.0 (+https://revyapp.com.br)"


def buscar(url: str, timeout: float = 8.0) -> str | None:
    pedido = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


# ------------------------------------------------------------------- relato


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="pre-flight do deploy da Revy")
    parser.add_argument(
        "--carimbar-site",
        action="store_true",
        help="grava site/build.txt com o SHA do HEAD, antes do upload ao Cloudflare",
    )
    parser.add_argument(
        "--desde",
        help="SHA de referencia. Default: o carimbo do /healthz de prod.",
    )
    args = parser.parse_args(argv)

    raiz = raiz_repo()
    if args.carimbar_site:
        print(f"carimbado: {carimbar_site(raiz)}")
        return 0
    problemas: list[str] = []

    limpo, sujos = repo_limpo(raiz)
    print(f"repo: {'limpo' if limpo else 'SUJO'} | HEAD {sha_atual(raiz)}")
    if not limpo:
        for linha in sujos[:10]:
            print(f"    {linha}")
        problemas.append(
            "repo sujo - fly deploy usa a arvore local: commite antes ou prod diverge do repo"
        )

    desde = args.desde or sha_do_healthz(buscar(URL_HEALTHZ) or "")
    if not desde:
        print("prod: sem carimbo (/healthz nao respondeu ou e anterior ao ARG GIT_SHA)")
        problemas.append(
            "sem SHA de prod - nao da para saber o que mudou; use --desde <sha> desta vez"
        )
        alvos: set[str] = set()
        mudados: list[str] = []
    else:
        print(f"prod: {desde}")
        mudados = arquivos_mudados(raiz, desde)
        alvos = alvos_para(mudados)
        print(f"mudou: {len(mudados)} arquivo(s) desde prod")
        print(f"alvos: {', '.join(sorted(alvos)) if alvos else 'NENHUM - nada a deployar'}")

    agora = {p: (versoes_css(raiz).get(p) or {}).get("base.html", "") for p in PRODUTOS_COM_CSS}
    for produto, por_arquivo in versoes_css(raiz).items():
        fora = versoes_divergentes(por_arquivo)
        if fora:
            problemas.append(
                f"{produto}: ?v= fora de sincronia em {', '.join(sorted(fora))} "
                "- essas telas vao servir CSS velho"
            )
    if desde:
        antes = {}
        for produto in PRODUTOS_COM_CSS:
            base = f"{produto}/app/templates/base.html"
            try:
                conteudo = _git(raiz, "show", f"{desde}:{base}")
            except subprocess.CalledProcessError:
                continue
            for linha in conteudo.splitlines():
                if "app.css" in linha:
                    achado = re.search(r"\?v=([\w.\-]+)", linha)
                    if achado:
                        antes[produto] = achado.group(1)
                        break
        for produto in cache_bust_pendente(mudados, antes, agora):
            problemas.append(
                f"{produto}: app.css mudou e o ?v= continua em {agora.get(produto)} "
                "- prod vai servir o CSS antigo"
            )

    print()
    if problemas:
        print(f"BLOQUEIO ({len(problemas)}):")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("pre-flight ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
