"""Pos-flight da revy-deploy: prova que subiu.

'O comando terminou sem erro' nao e prova. O wrangler responde 200 para um
preview que ninguem esta vendo; o Fly volta a versao anterior calado; o n8n
aceita o import e deixa o workflow desativado. As tres falhas sao silenciosas,
e as tres se detectam do lado de fora, comparando com o SHA que voce mandou.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from preflight import (  # noqa: E402
    URL_HEALTHZ,
    URL_SITE_BUILD,
    buscar,
    raiz_repo,
    sha_atual,
    sha_do_healthz,
)


def conferir_app(corpo: str | None, sha_esperado: str) -> tuple[bool, str]:
    """O /healthz do app2037 tem que devolver 2xx E o carimbo novo."""
    if corpo is None:
        return False, "app2037: /healthz nao respondeu - a VM pode nao ter subido"
    if corpo.startswith("fail:"):
        quebrados = corpo[len("fail:"):].strip()
        return False, f"app2037: health reprovou em {quebrados} - deploy subiu, servico nao"
    achado = sha_do_healthz(corpo)
    if achado is None:
        return False, "app2037: sem carimbo - a imagem no ar e anterior ao ARG GIT_SHA"
    if achado != sha_esperado:
        return False, (
            f"app2037: prod ainda em {achado}, esperado {sha_esperado} "
            "- o deploy nao trocou a maquina"
        )
    return True, f"app2037: no ar em {achado}"


def conferir_site(corpo: str | None, sha_esperado: str) -> tuple[bool, str]:
    """O dominio - nao o <hash>.pages.dev - tem que servir o SHA novo."""
    if corpo is None:
        return False, "site: revyapp.com.br/build.txt nao respondeu"
    achado = corpo.lstrip("\ufeff").strip()
    if achado != sha_esperado:
        return False, (
            f"site: o dominio ainda serve {achado}, esperado {sha_esperado}. "
            "Isto e o preview silencioso: sem --branch=main o wrangler publica "
            "num <hash>.pages.dev, responde 200 e deixa o dominio na versao velha. "
            "Republique com --branch=main."
        )
    return True, f"site: no ar em {achado}"


def conferir_n8n(workflows: list[dict], nome: str) -> tuple[bool, str]:
    """Existe e esta ATIVO. O import desativa; publish nao reativa."""
    for wf in workflows or []:
        if wf.get("name") == nome:
            if wf.get("active"):
                return True, f"n8n: '{nome}' ativo"
            return False, (
                f"n8n: '{nome}' importado mas DESATIVADO. O webhook vai dar 404 "
                "para sempre e a Evolution cancela o retry ao ver 404. Ative com "
                "n8n update:workflow --id=<id> --active=true"
            )
    nomes = ", ".join(sorted(w.get("name", "?") for w in workflows or [])) or "nenhum"
    return False, f"n8n: '{nome}' nao esta na instancia (achei: {nomes})"


def main(argv: list[str]) -> int:
    alvos = set(argv) or {"app2037", "site"}
    sha = sha_atual(raiz_repo())
    print(f"conferindo o HEAD {sha} em: {', '.join(sorted(alvos))}\n")

    reprovas = 0
    if "app2037" in alvos:
        ok, msg = conferir_app(buscar(URL_HEALTHZ), sha)
        print(("  ok  " if ok else "  X   ") + msg)
        reprovas += 0 if ok else 1
    if "site" in alvos:
        ok, msg = conferir_site(buscar(URL_SITE_BUILD), sha)
        print(("  ok  " if ok else "  X   ") + msg)
        reprovas += 0 if ok else 1
    if "n8n2037" in alvos:
        print("  ?   n8n: confira na mao - n8n list:workflow (precisa da chave da instancia)")

    print()
    if reprovas:
        print(f"NAO SUBIU DIREITO ({reprovas}). Nao diga que acabou.")
        return 1
    print("no ar e conferido")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
