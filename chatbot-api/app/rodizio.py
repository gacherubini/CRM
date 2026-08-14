"""Decisão do rodízio (spec §5.3), sem banco.

Separado do store de propósito: é aqui que mora a regra que erra fácil
(ponteiro circular, pular ocupado, saber que a volta fechou), e sem I/O
cada caso vira um teste de duas linhas.
"""
from __future__ import annotations


def escolher_proximo(
    ordem_ids: list[str],
    *,
    ponteiro: int,
    pendentes: set[str],
    ja_ofertados: set[str],
    posicao_inicial: int | None,
) -> tuple[str | None, int, bool]:
    """Devolve ``(vendedor_id, nova_posicao, volta_fechou)``.

    - ``None`` + ``volta_fechou=True``: acabou (fila vazia ou todo mundo já
      recebeu). O lead vira ``aguardando``.
    - ``None`` + ``volta_fechou=False``: todos estão com oferta aberta agora.
      O lead espera uma vaga; não é fim de fila.
    """
    total = len(ordem_ids)
    if total == 0:
        return None, ponteiro, True

    if posicao_inicial is not None and len(ja_ofertados) >= total:
        return None, ponteiro, True

    inicio = ponteiro % total
    for salto in range(total):
        indice = (inicio + salto) % total
        candidato = ordem_ids[indice]
        if candidato in pendentes or candidato in ja_ofertados:
            continue
        return candidato, (indice + 1) % total, False

    # Ninguém elegível. Distinguir "todos ocupados agora" de "todos já
    # receberam" é o que separa esperar de encerrar.
    livres = [v for v in ordem_ids if v not in ja_ofertados]
    return None, ponteiro, not livres
