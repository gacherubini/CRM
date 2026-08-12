"""Sanitização de texto escrito por terceiro (marca, modelo, descrição).

Texto de terceiro (cadastro de veículo, nome de lead, mensagem de cliente)
não é vetor de XSS aqui — isso já está fechado por autoescape do Jinja e por
``textContent`` no JS (nunca ``innerHTML``). O risco que esta função reduz é
outro: um valor escolhido com cuidado pode (a) carregar caractere de
controle ou override bidirecional que confunde a leitura, ou (b) continuar
gramaticalmente uma frase escrita pelo servidor quando concatenado sem
cerca. Por isso todo texto de terceiro que chega a um rótulo de UI ou ao
contexto do modelo passa por ``sanitizar_texto_externo`` e, quando for para
UI, por ``truncar_com_reticencias`` — nunca colado dentro de uma frase do
servidor (isso é responsabilidade de quem chama, não desta função).
"""
from __future__ import annotations

import re

# Controle (inclui \n, \r, \t) e DEL.
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")

# Marcas de direção e overrides bidirecionais: LRM/RLM (U+200E/U+200F),
# LRE/RLE/PDF/LRO/RLO (U+202A-U+202E) e os isolates LRI/RLI/FSI/PDI
# (U+2066-U+2069). Sobrevivem à remoção de controle porque não são controle
# ASCII; um U+202E no meio do rótulo inverte a leitura visual do que vem
# depois dele. Escapados como \uXXXX (nunca colados literais no
# código-fonte) para o caractere ficar auditável no diff.
_BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")

_ESPACOS = re.compile(r"\s+")


def sanitizar_texto_externo(texto: str) -> str:
    """Remove controle/bidi e colapsa espaço em branco em texto de terceiro."""
    sem_controle = _CONTROLE.sub(" ", texto or "")
    sem_bidi = _BIDI.sub("", sem_controle)
    return _ESPACOS.sub(" ", sem_bidi).strip()


def truncar_com_reticencias(texto: str, limite: int) -> str:
    """Corta em ``limite`` caracteres; acrescenta "…" só quando corta de fato."""
    if len(texto) <= limite:
        return texto
    return texto[: max(0, limite - 1)].rstrip() + "…"
