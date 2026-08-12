"""Corte do histórico do Copiloto por orçamento de TOKENS, não por turno.

Contagem fixa de turnos é a métrica errada: seis pares curtos custam quase
nada e seis pares longos podem estourar o contexto e o custo do provedor. O
que se quer limitar é volume de contexto — token —, não número de trocas.

Funções puras (sem banco, sem I/O): é o que torna este módulo testável sem
subir sessão, worker ou provedor.
"""
from __future__ import annotations

# Sobrecarga fixa por mensagem: toda mensagem de chat carrega delimitadores de
# papel/formato (role, separadores) além do texto em si. Um número pequeno e
# fixo evita subestimar mensagens curtas.
_SOBRECARGA_POR_MENSAGEM = 4

# ~1 token a cada 4 caracteres é a heurística mais citada para texto em
# inglês; superestima um pouco para português (mais acentuação e palavras
# maiores), o que é o lado seguro para um orçamento — preferimos cortar
# histórico de mais a estourar o contexto do provedor.
_CARACTERES_POR_TOKEN = 4


def estimar_tokens(texto: str) -> int:
    """Estima o custo em tokens de ``texto`` sem depender de um tokenizer real.

    É uma estimativa CONSERVADORA, não uma contagem exata: ~1 token a cada 4
    caracteres (arredondado para cima), mais uma sobrecarga fixa por
    mensagem. Não usamos o tokenizer específico do provedor de propósito —
    o provedor de LLM do Copiloto é trocável (§ config `copiloto_llm_*`), e
    amarrar a estimativa ao tokenizer de um provedor específico faria a
    estimativa MENTIR no dia em que o provedor trocar (tokenizers diferem
    entre modelos/fornecedores). Uma heurística de caracteres é pior em
    precisão, mas nunca fica desatualizada.
    """
    caracteres = len(texto or "")
    tokens_texto = -(-caracteres // _CARACTERES_POR_TOKEN)  # ceil division
    return tokens_texto + _SOBRECARGA_POR_MENSAGEM


def _custo_par(par: tuple[str, str]) -> int:
    pergunta, resposta = par
    return estimar_tokens(pergunta) + estimar_tokens(resposta)


def selecionar_historico(
    pares: list[tuple[str, str]], orcamento_tokens: int
) -> list[tuple[str, str]]:
    """Devolve o sufixo de ``pares`` que cabe em ``orcamento_tokens``.

    ``pares`` vem em ordem cronológica (mais antigo primeiro); a saída
    preserva essa ordem. Regras, todas obrigatórias:

    - Percorre do mais recente para o mais antigo, acumulando o custo
      estimado de cada par (pergunta + resposta, cada uma com sua
      sobrecarga de mensagem).
    - Para no primeiro par que não couber — não pula o par grande para
      continuar incluindo pares mais antigos. Um buraco no meio da
      conversa é pior que histórico curto: o modelo passaria a ver uma
      sequência que nunca aconteceu.
    - Sempre inclui o par mais recente, mesmo que sozinho exceda o
      orçamento. Perder a última troca é o pior corte possível — é
      justamente ela que dá sentido a perguntas como "e o mês passado?".
      Isto é seguro na prática porque a resposta do provedor é limitada
      por ``max_tokens`` (ver `runner.executar_turno`).
    - Lista vazia devolve ``[]``. Orçamento <= 0 ainda devolve o par mais
      recente, pela regra anterior.
    """
    if not pares:
        return []

    mais_recente = pares[-1]
    selecionados = [mais_recente]
    if orcamento_tokens <= 0:
        return selecionados

    custo_acumulado = _custo_par(mais_recente)
    for par in reversed(pares[:-1]):
        custo_par = _custo_par(par)
        if custo_acumulado + custo_par > orcamento_tokens:
            break
        selecionados.append(par)
        custo_acumulado += custo_par

    selecionados.reverse()
    return selecionados
