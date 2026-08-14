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

Este módulo também guarda o catálogo ``regra -> (rótulo, ícone, severidade
padrão)`` (F4/Task 5). Hoje ``sinais.py`` tem sete regras e o rótulo de cada
uma vivia espalhado — quando a 8ª regra chegasse, seria preciso caçar
template, painel e tela do Copiloto pra escrever o nome dela em algum lugar.
``catalogo_regra`` é o ponto único: painel do sino e tela do Copiloto devem
ler daqui, nunca reescrever o mapa.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.loja.copiloto.cache import CacheTTL
from app.loja.copiloto.sinais_store import contar_sinais_novos

TTL_SEGUNDOS = 45.0

# Público (não `_cache`) pelo mesmo motivo de `cache_overview` em cache.py:
# testes precisam invalidar entre casos sem esperar o TTL de relógio real.
cache_nao_vistos = CacheTTL(ttl_segundos=TTL_SEGUNDOS)


def _chave(
    loja_slug: str, usuario_id: str, regras: frozenset[str] | None = None
) -> str:
    """Usuário entra na chave: a contagem é pessoal desde a Task 0.

    Cachear só por loja devolveria a contagem de uma pessoa (ex: o sócio)
    para outra que renderizasse o shell logo em seguida.
    """
    return f"{loja_slug}:{usuario_id}:{hash(frozenset(regras)) if regras else 'all'}"


def contar_nao_vistos(
    db: Session,
    loja_slug: str,
    usuario_id: str,
    regras: frozenset[str] | None = None,
) -> int:
    """Contagem cacheada (TTL curto) de sinais novos do usuário nesta loja."""

    def _contar() -> int:
        if regras is None:
            return contar_sinais_novos(db, loja_slug, usuario_id)
        return contar_sinais_novos(db, loja_slug, usuario_id, regras=regras)

    return cache_nao_vistos.obter(_chave(loja_slug, usuario_id, regras), _contar)


def invalidar_contagem(loja_slug: str, usuario_id: str | None = None) -> None:
    """Força releitura na próxima chamada a ``contar_nao_vistos``.

    Sem ``usuario_id``, limpa TODAS as entradas da loja: quem cria um sinal
    novo (o worker de sincronização) não sabe — nem deveria saber — quem
    está com o cache quente. Sem esse alcance mais largo, o sino só
    refletiria o sinal novo quando o TTL de cada pessoa expirasse por conta
    própria.
    """
    # Prefixo do usuário, não a chave completa: depois do B1 a chave leva
    # o hash das regras (`:all` vs `:<hash>`), e quem invalida por pessoa
    # (transferência 1:1) precisa limpar os dois.
    prefixo = f"{loja_slug}:" if usuario_id is None else f"{loja_slug}:{usuario_id}:"
    cache_nao_vistos.invalidar(prefixo=prefixo)


# =============================================================================
# Catálogo de regras (F4/Task 5) — regra -> (rótulo, ícone, severidade padrão)
# =============================================================================


@dataclass(frozen=True)
class EntradaCatalogo:
    """Como uma regra de ``sinais.py`` aparece pra quem usa a loja.

    ``severidade_padrao`` é um fallback: cada candidato já traz sua própria
    severidade (calculada em cima do dado real, ex.: "crítico" só quando o
    veículo parado passa de 120 dias). Este campo existe pro catálogo cumprir
    o contrato "rótulo, ícone e severidade padrão" e servir de base caso
    algum consumidor futuro precise de severidade sem ter um candidato em
    mãos — não substitui a severidade calculada pela regra.
    """

    rotulo: str
    icone: str
    severidade_padrao: str  # info | atencao | critico


_ROTULO_GENERICO = "Alerta"
_ICONE_GENERICO = "generico"

#: Regra desconhecida (ainda não catalogada, ou dado inesperado) cai aqui —
#: nunca no nome cru da função/regra. Mesma disciplina que ``rotulos_passo``
#: aplica aos passos do chat em ``copiloto.html`` (Fase 2): nome de função
#: vazando pra tela do lojista é vazamento de implementação.
ENTRADA_GENERICA = EntradaCatalogo(
    rotulo=_ROTULO_GENERICO, icone=_ICONE_GENERICO, severidade_padrao="info"
)

#: Uma entrada por regra registrada em ``sinais.py``. Toda regra nova
#: precisa ganhar uma linha aqui — é o que ``test_copiloto_notificacoes_shell``
#: trava, iterando as regras de verdade (lidas do AST de ``sinais.py``, não
#: copiadas à mão) em vez de confiar que alguém lembra de atualizar uma lista.
CATALOGO_REGRAS: dict[str, EntradaCatalogo] = {
    "estoque_parado": EntradaCatalogo(
        rotulo="Estoque parado", icone="estoque", severidade_padrao="atencao"
    ),
    "lead_sem_resposta": EntradaCatalogo(
        rotulo="Lead sem resposta", icone="leads", severidade_padrao="critico"
    ),
    "meta_em_risco": EntradaCatalogo(
        rotulo="Meta em risco", icone="meta", severidade_padrao="atencao"
    ),
    "margem_incompleta": EntradaCatalogo(
        rotulo="Margem incompleta", icone="margem", severidade_padrao="atencao"
    ),
    "cadastro_incompleto": EntradaCatalogo(
        rotulo="Cadastro incompleto", icone="cadastro", severidade_padrao="info"
    ),
    "preco_fora_da_faixa": EntradaCatalogo(
        rotulo="Preço fora da faixa da FIPE", icone="preco", severidade_padrao="atencao"
    ),
    "atribuicao_baixa": EntradaCatalogo(
        rotulo="Atribuição de origem baixa", icone="atribuicao", severidade_padrao="atencao"
    ),
}


def catalogo_regra(regra: str) -> EntradaCatalogo:
    """Devolve a entrada do catálogo para ``regra``.

    Regra desconhecida cai em ``ENTRADA_GENERICA`` — nunca no nome cru da
    regra/função. Painel do sino e tela do Copiloto devem chamar esta função
    em vez de manter seu próprio mapa de rótulos.
    """
    return CATALOGO_REGRAS.get(regra, ENTRADA_GENERICA)
