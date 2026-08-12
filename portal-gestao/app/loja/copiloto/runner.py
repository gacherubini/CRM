"""Loop do turno: pergunta → tool calls → resposta. Rígido de propósito.

Cinco guardas: deadline global, teto de iterações, teto de tokens, rejeição de
tool-call malformada e degradação quando o provedor cai. Nenhuma delas pode
terminar com número inventado — na dúvida, o turno vira erro legível.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Sequence

from app.loja.copiloto.port import (
    EsforcoLLM,
    LLMIndisponivel,
    MensagemLLM,
    RespostaLLMInvalida,
)
from app.loja.copiloto.prompt import montar_system_prompt
from app.loja.copiloto.tools import (
    Ferramenta,
    FerramentaDesconhecida,
    RecursosTools,
    despachar,
    registro_padrao,
    schemas,
)

logger = logging.getLogger("portal.copiloto.runner")

# Preço oficial do provedor (§3.3): $0.14/M entrada, $0.28/M saída.
PRECO_ENTRADA_POR_TOKEN = Decimal("0.14") / Decimal(1_000_000)
PRECO_SAIDA_POR_TOKEN = Decimal("0.28") / Decimal(1_000_000)

MENSAGEM_DEADLINE = (
    "Não consegui consultar seus dados a tempo. Tente de novo em instantes — "
    "prefiro não responder a te dar um número errado."
)
MENSAGEM_PROVEDOR = (
    "O assistente está indisponível agora. Os alertas e o resumo de hoje "
    "continuam funcionando normalmente."
)
MENSAGEM_TETO_TOKENS = (
    "Essa pergunta ficou grande demais para responder num único turno. Tente "
    "quebrar em perguntas mais específicas."
)
MENSAGEM_MAX_ITERACOES = (
    "Essa pergunta precisou de passos demais para eu responder com segurança. "
    "Tente perguntar de um jeito mais direto ou em partes."
)
MENSAGEM_RESPOSTA_INVALIDA = (
    "O assistente não conseguiu montar uma chamada de função válida mesmo "
    "depois de tentar de novo. Tente reformular a pergunta."
)

# Nudge textual quando o provedor devolve uma tool-call com JSON quebrado
# (RespostaLLMInvalida, levantada dentro de completar() — antes de existir
# qualquer ToolCall/tool_call_id para responder como mensagem role=tool).
NUDGE_JSON_QUEBRADO = (
    "A chamada de função anterior veio com argumentos em JSON inválido e foi "
    "descartada sem executar nada. Chame a função de novo com um objeto JSON "
    "válido nos argumentos."
)


def custo_estimado(tokens_entrada: int, tokens_saida: int) -> Decimal:
    total = (
        Decimal(tokens_entrada) * PRECO_ENTRADA_POR_TOKEN
        + Decimal(tokens_saida) * PRECO_SAIDA_POR_TOKEN
    )
    return total.quantize(Decimal("0.000001"))


@dataclass(frozen=True)
class Passo:
    ferramenta: str
    argumentos: dict[str, Any]
    status: str  # ok | erro
    resumo: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ferramenta": self.ferramenta,
            "argumentos": self.argumentos,
            "status": self.status,
            "resumo": self.resumo,
        }


@dataclass(frozen=True)
class ResultadoTurno:
    estado: str  # pronto | erro
    texto: str | None
    passos: tuple[Passo, ...] = ()
    tokens_entrada: int = 0
    tokens_saida: int = 0
    erro_code: str | None = None

    @property
    def custo(self) -> Decimal:
        return custo_estimado(self.tokens_entrada, self.tokens_saida)

    def passos_dict(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.passos]


def _mensagens_iniciais(
    pergunta: str,
    historico: Sequence[tuple[str, str]],
    recursos: RecursosTools,
    ferramentas: Sequence[Ferramenta],
    agora: datetime | None,
) -> list[MensagemLLM]:
    mensagens = [
        MensagemLLM(
            papel="system",
            conteudo=montar_system_prompt(recursos.ctx, ferramentas, agora=agora),
        )
    ]
    for pergunta_antiga, resposta_antiga in historico:
        mensagens.append(MensagemLLM(papel="user", conteudo=pergunta_antiga))
        mensagens.append(MensagemLLM(papel="assistant", conteudo=resposta_antiga))
    mensagens.append(MensagemLLM(papel="user", conteudo=pergunta))
    return mensagens


def executar_turno(
    *,
    pergunta: str,
    historico: Sequence[tuple[str, str]],
    llm: Any,
    recursos: RecursosTools,
    ferramentas: tuple[Ferramenta, ...] | None = None,
    max_iteracoes: int = 4,
    deadline_segundos: float = 45.0,
    teto_tokens: int = 20_000,
    max_tokens_resposta: int = 800,
    on_passo: Callable[[list[dict]], None] | None = None,
    relogio: Callable[[], float] = time.monotonic,
    agora: datetime | None = None,
    esforco_inicial: EsforcoLLM = "low",
) -> ResultadoTurno:
    registro = ferramentas or registro_padrao()
    catalogo = schemas(registro)
    mensagens = _mensagens_iniciais(pergunta, historico, recursos, registro, agora)

    passos: list[Passo] = []
    tokens_entrada = 0
    tokens_saida = 0
    inicio = relogio()
    # Ponto de partida configurável (§11 da suíte de validação: comparar o
    # custo de "low" contra "high"). A escalada automática continua igual —
    # sobe para "high" na 1ª rodada que chamar ferramenta (guarda abaixo),
    # não é afetada por este parâmetro.
    esforco: EsforcoLLM = esforco_inicial
    correcao_json_usada = False

    def _erro(code: str, texto: str | None) -> ResultadoTurno:
        return ResultadoTurno(
            estado="erro",
            texto=texto,
            passos=tuple(passos),
            tokens_entrada=tokens_entrada,
            tokens_saida=tokens_saida,
            erro_code=code,
        )

    for iteracao in range(max_iteracoes):
        if relogio() - inicio > deadline_segundos:
            return _erro("deadline", MENSAGEM_DEADLINE)
        # Projeta o pior caso da próxima chamada (resposta cheia) para poder
        # recusar SEM chamar o provedor de novo — só o já gasto não seria
        # suficiente para barrar a próxima rodada a tempo. Esta checagem
        # também protege a chamada de correção do guard #4 abaixo: ela roda
        # de novo a cada volta do for, então uma retentativa nunca contorna
        # o teto de tokens.
        if tokens_entrada + tokens_saida + max_tokens_resposta > teto_tokens:
            return _erro("teto_tokens", MENSAGEM_TETO_TOKENS)

        try:
            resposta = llm.completar(
                mensagens, catalogo, esforco=esforco, max_tokens=max_tokens_resposta
            )
        except LLMIndisponivel:
            return _erro("provedor", MENSAGEM_PROVEDOR)
        except RespostaLLMInvalida:
            # Guard #4, sub-caso "JSON quebrado": a exceção nasce dentro do
            # completar() do provedor, antes de existir qualquer ToolCall —
            # não há tool_call_id para responder como mensagem role=tool, ao
            # contrário do sub-caso "ferramenta desconhecida" (despachar()).
            # Damos UMA chance de correção com um nudge textual; na segunda
            # vez, desistimos. O teto de iterações do próprio for já limita
            # quantas vezes isso pode se repetir por turno.
            if correcao_json_usada:
                return _erro("resposta_invalida", MENSAGEM_RESPOSTA_INVALIDA)
            correcao_json_usada = True
            mensagens.append(MensagemLLM(papel="user", conteudo=NUDGE_JSON_QUEBRADO))
            continue

        tokens_entrada += resposta.tokens_entrada
        tokens_saida += resposta.tokens_saida

        if not resposta.tool_calls:
            return ResultadoTurno(
                estado="pronto",
                texto=(resposta.texto or "").strip() or None,
                passos=tuple(passos),
                tokens_entrada=tokens_entrada,
                tokens_saida=tokens_saida,
            )

        mensagens.append(
            MensagemLLM(
                papel="assistant",
                conteudo=resposta.texto or "",
                tool_calls=resposta.tool_calls,
            )
        )

        for chamada in resposta.tool_calls:
            if relogio() - inicio > deadline_segundos:
                return _erro("deadline", MENSAGEM_DEADLINE)
            try:
                saida = despachar(
                    chamada.nome, chamada.argumentos, recursos, ferramentas=registro
                )
                status = "ok"
                resumo = str(saida.get("status", "ok"))
                conteudo = json.dumps(saida, ensure_ascii=False)
            except FerramentaDesconhecida:
                status = "erro"
                resumo = "ferramenta desconhecida"
                conteudo = json.dumps(
                    {"erro": "ferramenta_desconhecida", "nome": chamada.nome},
                    ensure_ascii=False,
                )
            except Exception as exc:
                # Falha de fonte não pode virar 500 nem número inventado.
                status = "erro"
                resumo = type(exc).__name__
                conteudo = json.dumps(
                    {"erro": "fonte_indisponivel", "status": "indisponivel"},
                    ensure_ascii=False,
                )
                logger.warning(
                    "copiloto_runner tool=%s falha=%s", chamada.nome, type(exc).__name__
                )

            passos.append(
                Passo(
                    ferramenta=chamada.nome,
                    argumentos=chamada.argumentos,
                    status=status,
                    resumo=resumo,
                )
            )
            mensagens.append(
                MensagemLLM(
                    papel="tool",
                    conteudo=conteudo,
                    tool_call_id=chamada.id,
                    nome=chamada.nome,
                )
            )

        if on_passo is not None:
            on_passo([p.to_dict() for p in passos])

        # Segunda rodada = cadeia/desambiguação: sobe o esforço (§3.3).
        esforco = "high"

    return _erro("max_iteracoes", MENSAGEM_MAX_ITERACOES)
