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

``--esforco`` agora É o lever real (fix round 1): repassa para
``executar_turno(..., esforco_inicial=...)`` (app/loja/copiloto/runner.py),
que controla o PONTO DE PARTIDA de cada turno. A escalada automática do
runner continua intocada: assim que um turno chama qualquer ferramenta, o
esforço da chamada seguinte sobe para "high" incondicionalmente (runner.py,
guarda da 2ª rodada em diante) — isso vale mesmo que essa chamada seguinte
só devolva o texto final, sem uma 2ª ferramenta. Consequência: rodar
``--esforco low`` e ``--esforco high`` muda de fato o custo/latência de
perguntas SEM ferramenta (única chamada, no esforço pedido) e a PRIMEIRA
chamada de perguntas COM ferramenta (o que pode até mudar acerto de
tool-call, não só latência); a chamada final de um turno com ferramenta
sempre acaba em "high" nos dois casos, por escalada automática. A métrica 3
(§11) reporta o esforço que cada turno DE FATO atingiu (via
``_RegistradorEsforco`` abaixo — observa a última chamada ao provedor), que
pode ser igual ou maior que o pedido em ``--esforco``.

Nota: ``Ferramenta.esforco_sugerido`` (app/loja/copiloto/tools.py) existe
como metadado mas NÃO é lido em lugar nenhum do runner — não é um lever.
Não o recomende como remédio; ver docs/copiloto-validacao.md.
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

# "6 das 14", "6 de 14", "8 dos 12", "8 do total de 12" (concordância
# masculina E feminina — "veículos" pede "dos", "vendas" pede "das").
PADRAO_COBERTURA = re.compile(r"\b\d+\s+d[eoa]s?\s+\d+\b", re.IGNORECASE)


@dataclass(frozen=True)
class Avaliacao:
    caso_id: str
    acertou_tool: bool
    citou_cobertura: bool
    latencia_ms: int
    # Este caso EXIGIA citação de cobertura? Default True porque é o que os
    # testes existentes (que constroem Avaliacao com 4 args posicionais,
    # antes deste campo existir) sempre representaram na prática: um lote de
    # casos todos relevantes para a métrica de cobertura. avaliar_caso()
    # abaixo sempre passa o valor real do caso, então isto só importa para
    # Avaliacao construída à mão (testes).
    exige_cobertura: bool = True
    # Esforço que o turno de fato atingiu ("low" ou "high") — o pedido em
    # --esforco mais a escalada automática do runner, não só o pedido.
    esforco: str = "low"


def carregar_casos(caminho: Path = FIXTURE_PADRAO) -> list[dict]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def avaliar_caso(caso: dict, resultado) -> Avaliacao:
    chamadas = [p.ferramenta for p in getattr(resultado, "passos", ()) or ()]
    esperada = caso.get("ferramenta_esperada")
    # Fix round 1 (finding 6): um turno que terminou em erro (deadline,
    # provedor fora, teto de tokens...) não pode contar como acerto — nem
    # no caso "sem ferramenta esperada", onde zero tool-calls por ter
    # falhado no meio do caminho não é a mesma coisa que zero tool-calls
    # por ter decidido corretamente que não precisava de nenhuma.
    if getattr(resultado, "estado", "pronto") == "erro":
        acertou = False
    elif esperada is None:
        acertou = not chamadas
    else:
        acertou = esperada in chamadas

    texto = getattr(resultado, "texto", "") or ""
    exige = bool(caso.get("exige_cobertura"))
    citou = True
    if exige:
        citou = bool(PADRAO_COBERTURA.search(texto))

    return Avaliacao(
        caso_id=caso["id"],
        acertou_tool=acertou,
        citou_cobertura=citou,
        latencia_ms=int(getattr(resultado, "latencia_ms", 0) or 0),
        exige_cobertura=exige,
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
    def _casos_com_cobertura_exigida(self) -> list[Avaliacao]:
        return [a for a in self.avaliacoes if a.exige_cobertura]

    @property
    def pct_cobertura(self) -> float | None:
        """% de acerto SÓ entre os casos que exigiam citar cobertura.

        Fix round 1 (finding 1): dividir por TODOS os casos deixava o gate
        impossível de reprovar — 1 erro em 9 casos relevantes virava
        29/30=96.7% (passa a meta de 95%) em vez do real 8/9=88.9% (não
        passa). ``None`` quando não há nenhum caso relevante no lote —
        nunca finge 100% por ausência de dado.
        """
        relevantes = self._casos_com_cobertura_exigida
        if not relevantes:
            return None
        return round(
            sum(1 for a in relevantes if a.citou_cobertura) / len(relevantes) * 100,
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
        falhas = [
            a
            for a in self.avaliacoes
            if not a.acertou_tool or (a.exige_cobertura and not a.citou_cobertura)
        ]
        relevantes = self._casos_com_cobertura_exigida
        if self.pct_cobertura is None:
            linha_cobertura = (
                "- Aderência à cobertura: sem casos que exigiam cobertura neste "
                "lote (meta ≥ 95%)"
            )
        else:
            acertos = sum(1 for a in relevantes if a.citou_cobertura)
            linha_cobertura = (
                f"- Aderência à cobertura: **{self.pct_cobertura}%** "
                f"({acertos}/{len(relevantes)} casos que exigiam cobertura) "
                "(meta ≥ 95%)"
            )
        linhas = [
            "# Validação do Copiloto",
            "",
            f"- Acerto de tool-call: **{self.pct_tool}%** (meta ≥ 90%)",
            linha_cobertura,
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

    Desde o fix round 1, ``executar_turno`` aceita ``esforco_inicial`` — mas
    a escalada automática para "high" após a 1ª ferramenta continua
    acontecendo por cima do que foi pedido. Esta classe é a forma confiável
    de saber, de fora, que esforço a ÚLTIMA chamada de um turno atingiu de
    fato (pedido + escalada), não só o que foi solicitado no início.
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

    ``esforco`` é repassado como ``esforco_inicial`` de cada turno (fix round
    1 — ver runner.py e a nota no topo do módulo): controla de fato o ponto
    de partida. A escalada automática para "high" após a 1ª ferramenta
    continua acontecendo por cima disso. A métrica de latência por esforço
    (``Relatorio.latencia_p95_por_esforco``) usa o esforço que cada turno
    REALMENTE atingiu na última chamada (pedido + escalada), não este
    parâmetro isoladamente — os dois podem divergir para turnos com
    ferramenta.
    """
    from app.loja.copiloto.runner import executar_turno

    avaliacoes: list[Avaliacao] = []
    for caso in casos:
        registrador = _RegistradorEsforco(llm)
        inicio = time.monotonic()
        resultado = executar_turno(
            pergunta=caso["pergunta"], historico=[], llm=registrador, recursos=recursos,
            esforco_inicial=esforco,
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
