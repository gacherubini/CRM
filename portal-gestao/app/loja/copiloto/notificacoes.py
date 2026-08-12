"""Contagem cacheada de sinais não vistos — alimenta o sino do shell (F4).

``contar_sinais_novos`` (``sinais_store.py``, Task 0) já é pessoal: filtra
por ``usuario_id``, não só por ``loja_slug``. Este módulo só acrescenta uma
camada de cache TTL curto por cima dela.

O cache aqui não é otimização — é obrigatório. ``template_extras``
(``app/web/loja_shell.py``) roda em TODA renderização do shell, inclusive em
telas sem nada a ver com o Copiloto (Vendas, Estoque, Atendimento). Sem
cache, cada page view nessas telas vira uma query extra.

Escopo consciente: cache por processo, no mesmo espírito de
``cache_overview`` (``cache.py``) — não distribuído, TTL curto. Um alerta
que aparece até um minuto depois não muda a vida de ninguém.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.loja.copiloto.cache import CacheTTL
from app.loja.copiloto.sinais_store import contar_sinais_novos

TTL_SEGUNDOS = 45.0

# Público (não `_cache`) pelo mesmo motivo de `cache_overview` em cache.py:
# testes precisam invalidar entre casos sem esperar o TTL de relógio real.
cache_nao_vistos = CacheTTL(ttl_segundos=TTL_SEGUNDOS)


def _chave(loja_slug: str, usuario_id: str) -> str:
    """Usuário entra na chave: a contagem é pessoal desde a Task 0.

    Cachear só por loja devolveria a contagem de uma pessoa (ex: o sócio)
    para outra que renderizasse o shell logo em seguida.
    """
    return f"{loja_slug}:{usuario_id}"


def contar_nao_vistos(db: Session, loja_slug: str, usuario_id: str) -> int:
    """Contagem cacheada (TTL curto) de sinais novos do usuário nesta loja."""
    return cache_nao_vistos.obter(
        _chave(loja_slug, usuario_id),
        lambda: contar_sinais_novos(db, loja_slug, usuario_id),
    )


def invalidar_contagem(loja_slug: str, usuario_id: str | None = None) -> None:
    """Força releitura na próxima chamada a ``contar_nao_vistos``.

    Sem ``usuario_id``, limpa TODAS as entradas da loja: quem cria um sinal
    novo (o worker de sincronização) não sabe — nem deveria saber — quem
    está com o cache quente. Sem esse alcance mais largo, o sino só
    refletiria o sinal novo quando o TTL de cada pessoa expirasse por conta
    própria.
    """
    prefixo = f"{loja_slug}:" if usuario_id is None else _chave(loja_slug, usuario_id)
    cache_nao_vistos.invalidar(prefixo=prefixo)
