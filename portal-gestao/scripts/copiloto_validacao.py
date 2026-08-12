"""Gate de go-live do Copiloto: 30 perguntas reais de dono, 3 métricas.

Mede SEPARADO: acerto de tool-call, aderência à regra de cobertura e
latência por esforço. A cobertura é medida sozinha porque é a regra que
nenhum modelo obedece de graça — e é a que sustenta a confiança do dono.

Uso (contra o provedor real, fora do pytest):
    python scripts/copiloto_validacao.py --esforco low
    python scripts/copiloto_validacao.py --esforco high

Decisão do dono: nunca trocar de modelo. Se uma meta cair abaixo do
aceitável, os levers são, NESTA ORDEM: subir o esforço do turno → endurecer
o prompt → limitar ferramentas por turno. Ver docs/copiloto-validacao.md.

Desvio em relação ao design original (documentado, não silencioso):
``executar_turno`` (app/loja/copiloto/runner.py) não aceita um esforço
inicial vindo de quem chama — o runner decide sozinho, começando em "low" e
subindo para "high" incondicionalmente depois da PRIMEIRA rodada que chamou
alguma ferramenta, antes da chamada seguinte ao provedor (runner.py:154 e
:269). Isso vale mesmo quando essa chamada seguinte só devolve o texto
final, sem nenhuma 2ª ferramenta — não é preciso haver cadeia de duas
ferramentas para chegar em "high". Na prática: turno que nunca chama
ferramenta fica em "low" (uma única chamada); QUALQUER turno que chama ao
menos uma ferramenta termina em "high" (a chamada que produz a resposta
final já vem escalada). Por isso a flag ``--esforco`` não força o
comportamento do provedor: ela só rotula a rodada no relatório. O que a
métrica 3 (§11) realmente mede é o esforço QUE CADA TURNO ATINGIU de fato —
via ``_RegistradorEsforco`` abaixo, que envolve o LLM (fake ou real) e
observa o parâmetro ``esforco`` da ÚLTIMA chamada do turno — e reporta a
latência separada entre "sem ferramenta" (low) e "com ferramenta" (high).
Isso é mais honesto que uma flag que não teria efeito nenhum, e é também o
dado que calibra a política real: hoje não existe uma pergunta que use
ferramenta e ainda assim custe "low".
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

FIXTURE_PADRAO = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "copiloto_perguntas.json"

# "6 das 14", "6 de 14", "sobre 6 das 14 vendas".
PADRAO_COBERTURA = re.compile(r"\b\d+\s+d[ea]s?\s+\d+\b", re.IGNORECASE)


@dataclass(frozen=True)
class Avaliacao:
    caso_id: str
    acertou_tool: bool
    citou_cobertura: bool
    latencia_ms: int
    # Esforço que o turno de fato atingiu ("low" ou "high") — não o que a
    # flag de CLI pediu. Ver nota de desvio no topo do módulo. Default "low"
    # mantém compatível a chamada posicional de 4 argumentos usada nos testes.
    esforco: str = "low"


def carregar_casos(caminho: Path = FIXTURE_PADRAO) -> list[dict]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def avaliar_caso(caso: dict, resultado) -> Avaliacao:
    chamadas = [p.ferramenta for p in getattr(resultado, "passos", ()) or ()]
    esperada = caso.get("ferramenta_esperada")
    if esperada is None:
        acertou = not chamadas
    else:
        acertou = esperada in chamadas

    texto = getattr(resultado, "texto", "") or ""
    citou = True
    if caso.get("exige_cobertura"):
        citou = bool(PADRAO_COBERTURA.search(texto))

    return Avaliacao(
        caso_id=caso["id"],
        acertou_tool=acertou,
        citou_cobertura=citou,
        latencia_ms=int(getattr(resultado, "latencia_ms", 0) or 0),
    )


@dataclass
class Relatorio:
    avaliacoes: list[Avaliacao]

    @property
    def pct_tool(self) -> float:
        if not self.avaliacoes:
            return 0.0
        return round(
            sum(1 for a in self.avaliacoes if a.acertou_tool) / len(self.avaliacoes) * 100,
            1,
        )

    @property
    def pct_cobertura(self) -> float:
        if not self.avaliacoes:
            return 0.0
        return round(
            sum(1 for a in self.avaliacoes if a.citou_cobertura) / len(self.avaliacoes) * 100,
            1,
        )

    @property
    def latencia_p50(self) -> int:
        return int(statistics.median([a.latencia_ms for a in self.avaliacoes] or [0]))

    @property
    def latencia_p95(self) -> int:
        valores = sorted(a.latencia_ms for a in self.avaliacoes)
        if not valores:
            return 0
        indice = max(0, int(round(0.95 * (len(valores) - 1))))
        return valores[indice]

    def latencia_p95_por_esforco(self) -> dict[str, int]:
        """p95 separado entre turnos que nunca chamaram ferramenta ("low")
        e turnos que chamaram ao menos uma ("high", pois o runner escala o
        esforço antes da chamada de resposta final — ver nota de desvio no
        topo do módulo) — a métrica 3 do §11."""
        saida: dict[str, int] = {}
        for nivel in ("low", "high", "max"):
            valores = sorted(a.latencia_ms for a in self.avaliacoes if a.esforco == nivel)
            if not valores:
                continue
            indice = max(0, int(round(0.95 * (len(valores) - 1))))
            saida[nivel] = valores[indice]
        return saida

    def to_markdown(self) -> str:
        falhas = [a for a in self.avaliacoes if not a.acertou_tool or not a.citou_cobertura]
        linhas = [
            "# Validação do Copiloto",
            "",
            f"- Acerto de tool-call: **{self.pct_tool}%** (meta ≥ 90%)",
            f"- Aderência à cobertura: **{self.pct_cobertura}%** (meta ≥ 95%)",
            f"- Latência p50/p95 (geral): **{self.latencia_p50}ms / {self.latencia_p95}ms**",
            f"- Casos: {len(self.avaliacoes)}",
            "",
            "## Latência por esforço atingido",
            "",
        ]
        por_esforco = self.latencia_p95_por_esforco()
        if por_esforco:
            linhas += [f"- p95 `{nivel}`: **{ms}ms**" for nivel, ms in por_esforco.items()]
        else:
            linhas.append("- sem dados")
        linhas += ["", "## Falhas"]
        linhas += (
            [
                f"- `{a.caso_id}`: tool={'ok' if a.acertou_tool else 'ERRO'} "
                f"cobertura={'ok' if a.citou_cobertura else 'ERRO'}"
                for a in falhas
            ]
            or ["- nenhuma"]
        )
        return "\n".join(linhas)


class _RegistradorEsforco:
    """Envolve qualquer LLMPort (fake ou real) só para observar o esforço de
    cada chamada de um turno, sem alterar LLMFake nem DeepSeekClient.

    ``executar_turno`` não recebe esforço inicial de quem chama (ver nota de
    desvio no topo do módulo): o runner decide sozinho e só sobe para "high"
    a partir da 2ª rodada de tool-calls. Esta classe é a única forma
    confiável de saber, de fora, que esforço um turno específico atingiu.
    """

    def __init__(self, llm: Any):
        self._llm = llm
        self.ultimo_esforco = "low"

    def completar(self, mensagens, ferramentas, *, esforco="low", max_tokens=800):
        self.ultimo_esforco = esforco
        return self._llm.completar(
            mensagens, ferramentas, esforco=esforco, max_tokens=max_tokens
        )


def rodar_validacao(llm, recursos, casos: list[dict], *, esforco: str = "low") -> Relatorio:
    """Roda os 30 casos contra ``llm`` (LLMFake nos testes; DeepSeekClient no
    go-live real) e devolve o Relatorio com as 3 métricas do §11.

    ``esforco`` rotula a rodada (útil para nomear o relatório quando se roda
    ``--esforco low`` e depois ``--esforco high`` em sequência), mas NÃO
    força o comportamento do runner — ver nota de desvio no topo do módulo.
    A métrica de latência por esforço usa o esforço realmente atingido por
    cada turno, não este parâmetro.
    """
    from app.loja.copiloto.runner import executar_turno

    avaliacoes: list[Avaliacao] = []
    for caso in casos:
        registrador = _RegistradorEsforco(llm)
        inicio = time.monotonic()
        resultado = executar_turno(
            pergunta=caso["pergunta"], historico=[], llm=registrador, recursos=recursos
        )
        latencia_ms = int((time.monotonic() - inicio) * 1000)
        resultado_avaliavel = SimpleNamespace(
            texto=resultado.texto, passos=resultado.passos, latencia_ms=latencia_ms
        )
        avaliacao = avaliar_caso(caso, resultado_avaliavel)
        avaliacoes.append(replace(avaliacao, esforco=registrador.ultimo_esforco))
    return Relatorio(avaliacoes)


def main() -> None:  # pragma: no cover - entrada de CLI, roda contra o provedor real
    parser = argparse.ArgumentParser(
        description="Gate de go-live do Copiloto: roda as 30 perguntas contra o "
        "provedor real (DeepSeek) e mede tool-call, cobertura e latência."
    )
    parser.add_argument("--esforco", default="low", choices=["low", "high", "max"])
    parser.add_argument("--fixture", default=str(FIXTURE_PADRAO))
    parser.add_argument(
        "--loja-slug",
        default="loja-teste",
        help="Slug de uma loja PILOTO com dados reais (venda, estoque, lead). "
        "Nunca rodar contra banco vazio — ver docs/copiloto-validacao.md.",
    )
    parser.add_argument("--papel", default="dono")
    parser.add_argument("--ator-email", default="validacao@revy.local")
    args = parser.parse_args()

    from datetime import datetime, timezone

    from app.clients.deepseek import DeepSeekClient
    from app.config import settings
    from app.db import SessionLocal
    from app.loja.copiloto.tipos import CopilotoContexto
    from app.loja.copiloto.tools import RecursosTools
    from app.main import get_chatbot_client, get_estoque_client

    if not settings.copiloto_llm_key:
        # Nunca ler chave de literal no código: só do ambiente/config. Sem
        # chave configurada, DeepSeekClient.completar() levantaria
        # LLMIndisponivel no primeiro turno — falhamos cedo com uma mensagem
        # legível em vez de deixar isso acontecer 30 vezes.
        print(
            "REVY_LOJA_COPILOTO_LLM_KEY não está configurada no ambiente. "
            "Este script fala com o provedor real e não roda sem uma chave "
            "válida (nunca commitada). Exporte a variável antes de rodar.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    db = SessionLocal()
    try:
        ctx = CopilotoContexto(
            loja_slug=args.loja_slug,
            papel=args.papel,
            ator_email=args.ator_email,
            hoje=datetime.now(timezone.utc).date(),
        )
        recursos = RecursosTools(
            db=db, estoque=get_estoque_client(), chatbot=get_chatbot_client(), ctx=ctx
        )
        llm = DeepSeekClient(
            settings.copiloto_llm_url,
            settings.copiloto_llm_key,
            settings.copiloto_llm_model,
            timeout=settings.copiloto_llm_timeout,
            retries=settings.copiloto_llm_retries,
        )
        relatorio = rodar_validacao(
            llm, recursos, carregar_casos(Path(args.fixture)), esforco=args.esforco
        )
        print(relatorio.to_markdown())
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover
    main()
