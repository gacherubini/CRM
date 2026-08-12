"""Gate de go-live do Copiloto: 42 perguntas reais de dono, 4 métricas.

Mede SEPARADO: acerto de tool-call, aderência à regra de cobertura, latência
por esforço e — a métrica 4, I6 — se todo número que aparece na resposta
rastreia a algum valor que uma ferramenta devolveu NESTA conversa. É a
promessa central do produto (o modelo nunca produz número de cabeça: todo
número vem de uma chamada de função) e as três primeiras métricas não a
mediam — só QUAL ferramenta foi chamada e se um texto no formato "N de M"
apareceu, nunca se os números em si batem com o payload. A cobertura é
medida sozinha porque é a regra que nenhum modelo obedece de graça — e é a
que sustenta a confiança do dono.

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
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from typing import Any

FIXTURE_PADRAO = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "copiloto_perguntas.json"

# "6 das 14", "6 de 14", "8 dos 12", "8 do total de 12" (concordância
# masculina E feminina — "veículos" pede "dos", "vendas" pede "das").
PADRAO_COBERTURA = re.compile(r"\b\d+\s+d[eoa]s?\s+\d+\b", re.IGNORECASE)


# --- Métrica 4 (I6): todo número na resposta rastreia ao payload -----------
#
# NÃO detecta um número ERRADO que por acaso aparece em algum lugar do
# payload (ex.: o modelo trocar receita por ticket médio, mas ambos vierem
# da mesma ferramenta) — só detecta número que não aparece em NENHUM lugar
# do payload. É um piso, não uma prova de resposta correta; ver
# docs/copiloto-validacao.md.

# Data: "12/08" ou "12/08/2026" — restatement de período, não claim de dado.
_PADRAO_DATA = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
# Ordinal: "1º", "2ª" — não é figura de negócio.
_PADRAO_ORDINAL = re.compile(r"\b\d+[ºª]")
# Ano solto de 4 dígitos (1900–2099) sem R$/%: "agosto de 2026" restatement.
_PADRAO_ANO = re.compile(r"^(19|20)\d{2}$")

# Ordem importa: alternativas mais específicas primeiro, porque o motor de
# regex do Python usa a PRIMEIRA alternativa que casa naquela posição, não a
# mais longa (sem tentar as outras se a primeira já deu match).
_PADRAO_NUMERO = re.compile(
    r"R\$\s*-?\d[\d.]*(?:,\d+)?"        # moeda: "R$ 412.000,00", "R$ 40"
    r"|-?\d{1,3}(?:\.\d{3})+(?:,\d+)?"  # milhar com ponto: "412.000", "1.234,50"
    r"|-?\d+,\d+\s*%?"                  # decimal com vírgula: "29,5", "29,5%"
    r"|-?\d+\s*%"                       # percentual inteiro: "40%"
    r"|-?\d+(?:\.\d+)?\b"               # fallback simples: "6", "14", "3.5"
)


def normalizar_numero(token: str) -> Decimal | None:
    """Um número textual (BR: ponto=milhar, vírgula=decimal; ou já em
    formato de payload: ponto=decimal, sem separador de milhar) vira um
    ``Decimal`` canônico. ``None`` se não for um número de verdade.

    Existe para que "R$ 412.000,00" (resposta) e "412000.00" (payload JSON)
    comparem iguais — sem isto, a métrica acusaria toda resposta formatada
    como violação.
    """
    limpo = token.replace("R$", "").replace("%", "").strip()
    if not limpo:
        return None
    if "," in limpo:
        # BR: ponto é separador de milhar, vírgula é decimal.
        limpo = limpo.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", limpo):
        # BR sem casa decimal: "1.234" -> 1234 (não confundir com "3.5" do
        # payload, que não bate neste padrão — grupos de EXATAMENTE 3 dígitos).
        limpo = limpo.replace(".", "")
    try:
        return Decimal(limpo)
    except InvalidOperation:
        return None


def extrair_numeros_da_resposta(texto: str) -> list[Decimal]:
    """Números que a resposta apresenta como fato — exclui data, ordinal e
    ano solto (restatement de período, não claim numérico de negócio)."""
    sem_data = _PADRAO_DATA.sub(" ", texto or "")
    sem_ordinal = _PADRAO_ORDINAL.sub(" ", sem_data)
    numeros: list[Decimal] = []
    for m in _PADRAO_NUMERO.finditer(sem_ordinal):
        bruto = m.group()
        if _PADRAO_ANO.match(bruto.strip()):
            continue
        valor = normalizar_numero(bruto)
        if valor is not None:
            numeros.append(valor)
    return numeros


def rastreia_ao_payload(numero: Decimal, payload: set[Decimal]) -> bool:
    """O número aparece no payload, ou é diferença/soma exata de dois valores
    dele.

    A derivação existe por um caso real, medido no gate de 2026-08-12: com
    ``cobertura_margem {com_dado: 6, total: 14}``, o modelo escreveu "6 das 14
    vendas, porque as outras **8** ainda não têm custo". O 8 é ``14 - 6`` --
    exato, correto, e deixa a resposta melhor. Sem esta função a métrica
    reprovava justamente o comportamento que queremos, e as 9 respostas com
    dado real do primeiro gate falharam todas por isso.

    O escopo é deliberadamente estreito: SÓ soma e subtração de DOIS valores
    do payload. Aceitar qualquer aritmética tornaria a métrica incapaz de
    reprovar um número inventado, que é a única coisa que ela existe para
    pegar. Regra 1 proíbe estimar e supor -- não proíbe subtrair.
    """
    if numero in payload:
        return True
    valores = list(payload)
    for i, a in enumerate(valores):
        for b in valores[i:]:
            if numero == a - b or numero == b - a or numero == a + b:
                return True
    return False


def folhas_numericas(valor: Any) -> list[Decimal]:
    """Todo número folha de um payload JSON aninhado (dict/list) — inclusive
    strings numéricas, porque os ``to_dict()`` do domínio serializam Decimal
    como ``str`` (ex.: ``"receita": "412000.00"``)."""
    saida: list[Decimal] = []
    if isinstance(valor, dict):
        for v in valor.values():
            saida.extend(folhas_numericas(v))
    elif isinstance(valor, list):
        for v in valor:
            saida.extend(folhas_numericas(v))
    elif isinstance(valor, bool):
        pass  # bool é subclasse de int em Python — nunca é claim numérico
    elif isinstance(valor, (int, float)):
        saida.append(Decimal(str(valor)))
    elif isinstance(valor, str):
        n = normalizar_numero(valor)
        if n is not None:
            saida.append(n)
    return saida


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
    # Métrica 4 (I6). ``numeros_relevante`` = a resposta continha algum
    # número extraível (senão o caso não entra no denominador — mesmo
    # espírito de ``exige_cobertura``). ``numeros_ok`` = todo número
    # extraído apareceu em algum payload de ferramenta desta conversa.
    # Default (False/True) deixa ``Avaliacao`` construída à mão nos testes
    # antigos, sem payload, de fora do denominador — não finge medição que
    # não foi feita.
    numeros_relevante: bool = False
    numeros_ok: bool = True


def carregar_casos(caminho: Path = FIXTURE_PADRAO) -> list[dict]:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def avaliar_caso(
    caso: dict, resultado, payload_numeros: frozenset[Decimal] | None = None
) -> Avaliacao:
    """``payload_numeros``: todo número (folha) devolvido pelas ferramentas
    chamadas neste turno — ``None`` quando o chamador não mede a métrica 4
    (compatibilidade com testes/chamadores antigos; ver ``Avaliacao``)."""
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

    numeros_relevante = False
    numeros_ok = True
    if payload_numeros is not None:
        numeros_resposta = extrair_numeros_da_resposta(texto)
        if numeros_resposta:
            numeros_relevante = True
            numeros_ok = all(
                rastreia_ao_payload(n, payload_numeros) for n in numeros_resposta
            )

    return Avaliacao(
        caso_id=caso["id"],
        acertou_tool=acertou,
        citou_cobertura=citou,
        latencia_ms=int(getattr(resultado, "latencia_ms", 0) or 0),
        exige_cobertura=exige,
        numeros_relevante=numeros_relevante,
        numeros_ok=numeros_ok,
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
    def _casos_com_numero_na_resposta(self) -> list[Avaliacao]:
        return [a for a in self.avaliacoes if a.numeros_relevante]

    @property
    def pct_numeros_rastreaveis(self) -> float | None:
        """% de respostas em que TODO número citado aparece em algum payload
        de ferramenta desta conversa (I6, métrica 4 — medida separada, não
        entra em ``pct_tool`` nem em ``pct_cobertura``).

        Só entram no denominador casos cuja resposta continha algum número
        extraível — mesmo desenho de ``pct_cobertura``: nunca finge 100% por
        ausência de caso aplicável. ``None`` quando nenhum caso do lote se
        aplica (nenhuma resposta tinha número, ou nenhum turno foi medido —
        ver ``avaliar_caso``).

        NÃO prova que o número está CERTO — só que ele aparece em algum
        lugar do payload devolvido nesta conversa. Ver docs/copiloto-validacao.md.
        """
        relevantes = self._casos_com_numero_na_resposta
        if not relevantes:
            return None
        return round(
            sum(1 for a in relevantes if a.numeros_ok) / len(relevantes) * 100,
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
            if not a.acertou_tool
            or (a.exige_cobertura and not a.citou_cobertura)
            or (a.numeros_relevante and not a.numeros_ok)
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
        relevantes_numero = self._casos_com_numero_na_resposta
        if self.pct_numeros_rastreaveis is None:
            linha_numeros = (
                "- Números rastreáveis ao payload: sem resposta com número "
                "neste lote"
            )
        else:
            acertos_numero = sum(1 for a in relevantes_numero if a.numeros_ok)
            linha_numeros = (
                f"- Números rastreáveis ao payload: **{self.pct_numeros_rastreaveis}%** "
                f"({acertos_numero}/{len(relevantes_numero)} respostas com número) "
                "— não prova número certo, só que ele veio de algum payload "
                "desta conversa"
            )
        linhas = [
            "# Validação do Copiloto",
            "",
            f"- Acerto de tool-call: **{self.pct_tool}%** (meta ≥ 90%)",
            linha_cobertura,
            linha_numeros,
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
                f"cobertura={'ok' if a.citou_cobertura else 'ERRO'} "
                f"numeros={'ok' if a.numeros_ok else 'ERRO'}"
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
        # Métrica 4 (I6): a ÚLTIMA chamada de um turno recebe ``mensagens``
        # com o histórico INTEIRO já acumulado (a mesma lista, mutada por
        # append a cada rodada do runner — ver executar_turno em runner.py),
        # então guardar a referência aqui, na última chamada, já é capturar
        # toda mensagem role="tool" (o JSON que cada ferramenta devolveu)
        # do turno inteiro, sem precisar instrumentar o runner.
        self.ultimas_mensagens: list = []

    def completar(self, mensagens, ferramentas, *, esforco="low", max_tokens=800):
        self.ultimo_esforco = esforco
        self.ultimas_mensagens = list(mensagens)
        return self._llm.completar(
            mensagens, ferramentas, esforco=esforco, max_tokens=max_tokens
        )


def _payload_numeros_do_turno(mensagens: list) -> frozenset[Decimal]:
    """Todo número folha de todo payload de ferramenta (``role="tool"``) que
    apareceu no turno — a fonte de verdade da métrica 4 (I6)."""
    numeros: list[Decimal] = []
    for m in mensagens:
        if getattr(m, "papel", None) != "tool":
            continue
        try:
            payload = json.loads(m.conteudo)
        except (TypeError, ValueError):
            continue
        numeros.extend(folhas_numericas(payload))
    return frozenset(numeros)


def rodar_validacao(llm, recursos, casos: list[dict], *, esforco: str = "low") -> Relatorio:
    """Roda os casos da fixture contra ``llm`` (LLMFake nos testes; DeepSeekClient no
    go-live real) e devolve o Relatorio com as 4 métricas (ver docstring do módulo).

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
        # Fix round 2 (finding 6): ResultadoTurno é frozen e não tem
        # latencia_ms (medida fora do runner), então precisa de um wrapper —
        # mas um wrapper que rechama campos NOMEADOS é uma fonte de bug
        # recorrente: a versão anterior listava só texto/passos/latencia_ms
        # e descartava .estado por engano, fazendo o guard de turno-com-erro
        # (avaliar_caso) nunca disparar no caminho real (só em testes que
        # construíam o objeto à mão). ``vars(resultado)`` copia TODOS os
        # campos do dataclass automaticamente (estado, texto, passos,
        # tokens_entrada, tokens_saida, erro_code) — nenhum campo futuro do
        # ResultadoTurno pode ser esquecido aqui de novo por omissão.
        resultado_avaliavel = SimpleNamespace(**vars(resultado), latencia_ms=latencia_ms)
        payload_numeros = _payload_numeros_do_turno(registrador.ultimas_mensagens)
        avaliacao = avaliar_caso(caso, resultado_avaliavel, payload_numeros)
        avaliacoes.append(replace(avaliacao, esforco=registrador.ultimo_esforco))
    return Relatorio(avaliacoes)


def main() -> None:  # pragma: no cover - entrada de CLI, roda contra o provedor real
    parser = argparse.ArgumentParser(
        description="Gate de go-live do Copiloto: roda as perguntas da fixture contra o "
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
