import json
from datetime import date, datetime, timezone
from pathlib import Path

from app.loja.copiloto.port import LLMFake, LLMIndisponivel, RespostaLLM, ToolCall
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.copiloto.tools import RecursosTools
from scripts.copiloto_validacao import (
    Avaliacao,
    Relatorio,
    avaliar_caso,
    carregar_casos,
    rodar_validacao,
)

FIXTURE = Path(__file__).parent / "fixtures" / "copiloto_perguntas.json"


class ResultadoFalso:
    def __init__(self, texto, ferramentas, latencia_ms=1200):
        self.texto = texto
        self.passos = tuple(
            type("P", (), {"ferramenta": f, "status": "ok"})() for f in ferramentas
        )
        self.latencia_ms = latencia_ms
        self.estado = "pronto"


def test_fixture_tem_pelo_menos_trinta_casos():
    """Fix round 2 (sample size): a fixture cresceu de 30 para 42 casos —
    os 12 novos são todos coverage-bearing (ver
    test_fixture_casos_de_cobertura_sao_alcancaveis_pela_ferramenta), para
    tirar a métrica de cobertura de n=6 (só 7 valores possíveis, sem
    graduação real entre 83.3% e 100%) para n=18."""
    casos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(casos) == 42
    assert all("pergunta" in c and "id" in c for c in casos)
    ids = [c["id"] for c in casos]
    assert len(ids) == len(set(ids)), "ids da fixture precisam ser únicos"


def test_fixture_cobre_as_seis_ferramentas():
    casos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    esperadas = {c["ferramenta_esperada"] for c in casos if c["ferramenta_esperada"]}
    assert esperadas == {
        "vendas_resumo",
        "ranking_vendedores",
        "venda_origem",
        "estoque_parado",
        "leads_status",
        "roi_canais",
    }


def test_fixture_casos_de_cobertura_sao_alcancaveis_pela_ferramenta():
    """Fix round 1 (finding 3): _f_roi_canais (app/loja/copiloto/tools.py)
    nunca devolve com_dado/total — só ``status`` (ok|parcial|indisponivel) e
    ``detalhe_disponivel`` (bool). Exigir citação "N de M" dela forçaria um
    modelo bem-comportado a inventar um número, violando a Regra 1. Por
    isso nenhum caso ``exige_cobertura`` pode mirar roi_canais.

    Fix round 2 (sample size): o lote relevante cresceu de 6 para 18 casos
    — vendas_resumo (margem/lucro), venda_origem (escopo periodo) e
    estoque_parado (cobertura_data), as 3 ferramentas verificadas para
    realmente produzirem ``Cobertura(com_dado, total)``."""
    casos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    exigem = [c for c in casos if c["exige_cobertura"]]
    assert len(exigem) == 18
    assert all(c["ferramenta_esperada"] != "roi_canais" for c in exigem)
    assert {c["ferramenta_esperada"] for c in exigem} == {
        "vendas_resumo",
        "venda_origem",
        "estoque_parado",
    }


def test_acerto_de_tool_call():
    caso = {"id": "v01", "pergunta": "x", "ferramenta_esperada": "vendas_resumo", "exige_cobertura": False}
    ok = avaliar_caso(caso, ResultadoFalso("Você vendeu 2.", ["vendas_resumo"]))
    assert ok.acertou_tool is True
    errou = avaliar_caso(caso, ResultadoFalso("Você vendeu 2.", ["estoque_parado"]))
    assert errou.acertou_tool is False


def test_caso_sem_ferramenta_acerta_quando_nao_chama_nada():
    caso = {"id": "x01", "pergunta": "x", "ferramenta_esperada": None, "exige_cobertura": False}
    assert avaliar_caso(caso, ResultadoFalso("Não tenho esse dado hoje.", [])).acertou_tool is True
    assert avaliar_caso(caso, ResultadoFalso("...", ["vendas_resumo"])).acertou_tool is False


def test_cobertura_citada_e_reconhecida():
    caso = {"id": "v03", "pergunta": "x", "ferramenta_esperada": "vendas_resumo", "exige_cobertura": True}
    citou = avaliar_caso(
        caso,
        ResultadoFalso("Margem de 18%, calculada sobre 6 das 14 vendas.", ["vendas_resumo"]),
    )
    assert citou.citou_cobertura is True
    calou = avaliar_caso(caso, ResultadoFalso("Sua margem é 18%.", ["vendas_resumo"]))
    assert calou.citou_cobertura is False


def test_padrao_cobertura_aceita_concordancia_masculina_e_feminina():
    """Fix round 1 (finding 2): "dos" (masculino, ex. "veículos") tinha que
    ser reconhecido tanto quanto "das" (feminino, ex. "vendas") — a regex
    original só cobria feminino."""
    caso = {"id": "e03", "pergunta": "x", "ferramenta_esperada": "estoque_parado", "exige_cobertura": True}
    masculino = avaliar_caso(
        caso,
        ResultadoFalso(
            "Consegui a data de cadastro de 8 dos 12 veículos parados.",
            ["estoque_parado"],
        ),
    )
    assert masculino.citou_cobertura is True
    feminino = avaliar_caso(
        caso,
        ResultadoFalso("Calculei sobre 6 das 14 vendas.", ["estoque_parado"]),
    )
    assert feminino.citou_cobertura is True


def test_turno_com_erro_nao_conta_como_acerto_sem_ferramenta():
    """Fix round 1 (finding 6): zero tool-calls por ter falhado no meio
    (deadline, provedor fora...) não pode ler como "decidiu corretamente
    que não precisava de ferramenta"."""
    caso = {"id": "x01", "pergunta": "x", "ferramenta_esperada": None, "exige_cobertura": False}
    resultado_com_erro = ResultadoFalso("Não consegui responder desta vez.", [])
    resultado_com_erro.estado = "erro"
    avaliacao = avaliar_caso(caso, resultado_com_erro)
    assert avaliacao.acertou_tool is False


def test_relatorio_calcula_percentuais_e_p95():
    relatorio = Relatorio(
        [
            Avaliacao("a", True, True, 1000),
            Avaliacao("b", True, False, 2000),
            Avaliacao("c", False, True, 30000),
            Avaliacao("d", True, True, 1500),
        ]
    )
    assert relatorio.pct_tool == 75.0
    assert relatorio.pct_cobertura == 75.0
    assert relatorio.latencia_p95 >= 2000
    assert "acerto de tool-call" in relatorio.to_markdown().lower()


def test_pct_cobertura_conta_so_casos_que_exigem_cobertura():
    """Fix round 1 (finding 1), worked example do reviewer: dividir por
    TODOS os 30 casos deixava o gate impossível de reprovar — 1 erro em 9
    casos relevantes vazava para 29/30=96.7% (passaria a meta de 95%) em
    vez do real 8/9=88.9% (não passa)."""
    relevantes = [Avaliacao(f"c{i}", True, i != 0, 1000, exige_cobertura=True) for i in range(9)]
    irrelevantes = [
        Avaliacao(f"n{i}", True, True, 1000, exige_cobertura=False) for i in range(21)
    ]
    relatorio = Relatorio(relevantes + irrelevantes)

    assert len(relatorio.avaliacoes) == 30
    assert relatorio.pct_cobertura == round(8 / 9 * 100, 1)
    assert relatorio.pct_cobertura < 95.0
    markdown = relatorio.to_markdown()
    assert "8/9" in markdown


def test_pct_cobertura_sem_casos_aplicaveis_nao_finge_100():
    relatorio = Relatorio([Avaliacao("a", True, True, 1000, exige_cobertura=False)])
    assert relatorio.pct_cobertura is None
    assert "sem casos" in relatorio.to_markdown().lower()
    assert "100%" not in relatorio.to_markdown()


def test_carregar_casos_le_a_fixture():
    assert len(carregar_casos(FIXTURE)) == 42


# --- rodar_validacao fim a fim, sempre contra LLMFake: determinístico, sem
# rede e sem chave. É este caminho que roda no CI; o CLI real de
# scripts/copiloto_validacao.py (main()) é o único que fala com o provedor,
# e só no go-live manual contra uma loja piloto — nunca em teste automatizado.


class _EstoqueStub:
    def obter_loja(self):
        return {"slug": "loja-teste"}

    def listar(self, **_kw):
        return []


class _ChatbotStub:
    def listar_conversas(self, **_kw):
        return []

    def listar_leads(self, etapa=None):
        return []


def _recursos(db):
    ctx = CopilotoContexto(
        loja_slug="loja-teste", papel="dono", ator_email="d@l.test",
        hoje=date(2026, 8, 11),
    )
    return RecursosTools(
        db=db, estoque=_EstoqueStub(), chatbot=_ChatbotStub(), ctx=ctx,
        agora=datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
    )


def _tool(nome, id_="c1"):
    return RespostaLLM(
        texto=None, tool_calls=(ToolCall(id=id_, nome=nome, argumentos={}),),
        tokens_entrada=500, tokens_saida=20, finish_reason="tool_calls",
    )


def _texto(txt):
    return RespostaLLM(
        texto=txt, tool_calls=(), tokens_entrada=600, tokens_saida=40,
        finish_reason="stop",
    )


def test_rodar_validacao_fim_a_fim_contra_llmfake(db):
    casos = [
        {"id": "v03", "pergunta": "minha margem esse mês",
         "ferramenta_esperada": "vendas_resumo", "exige_cobertura": True},
        {"id": "x01", "pergunta": "quantos funcionários eu posso contratar?",
         "ferramenta_esperada": None, "exige_cobertura": False},
    ]
    llm = LLMFake([
        _tool("vendas_resumo"),
        _texto("Margem de 18%, calculada sobre 6 das 14 vendas."),
        _texto("Não tenho esse dado — isso é uma decisão sua."),
    ])
    relatorio = rodar_validacao(llm, _recursos(db), casos)

    assert relatorio.pct_tool == 100.0
    # Só v03 exige cobertura (x01 não conta no denominador — fix round 1,
    # finding 1); v03 citou "6 das 14", então 1/1 = 100%.
    assert relatorio.pct_cobertura == 100.0
    assert len(relatorio.avaliacoes) == 2
    # v03 chamou uma ferramenta: o runner sobe o esforço para a rodada
    # seguinte (a de resposta final) mesmo sem uma 2ª ferramenta — ver
    # runner.py:269 e a nota no topo de scripts/copiloto_validacao.py.
    assert relatorio.avaliacoes[0].esforco == "high"
    # x01 nunca chamou ferramenta: resolveu na única chamada, que fica "low".
    assert relatorio.avaliacoes[1].esforco == "low"
    assert all(a.latencia_ms >= 0 for a in relatorio.avaliacoes)


def test_rodar_validacao_registra_esforco_alto_quando_turno_encadeia(db):
    casos = [
        {"id": "e01", "pergunta": "e aí, tudo parado?",
         "ferramenta_esperada": "estoque_parado", "exige_cobertura": False},
    ]
    llm = LLMFake([
        _tool("estoque_parado"), _tool("vendas_resumo", id_="c2"), _texto("Pronto."),
    ])
    relatorio = rodar_validacao(llm, _recursos(db), casos)

    assert relatorio.avaliacoes[0].acertou_tool is True
    assert relatorio.avaliacoes[0].esforco == "high"
    assert relatorio.latencia_p95_por_esforco() == {
        "high": relatorio.avaliacoes[0].latencia_ms
    }


class _LLMDerruba:
    """Provedor que sempre cai — para forçar ``executar_turno`` a devolver
    ``estado="erro"`` DE VERDADE (não um ``ResultadoFalso`` construído à
    mão), pelo mesmo caminho que o guard #2 do runner usa em produção
    (``except LLMIndisponivel`` em app/loja/copiloto/runner.py)."""

    def completar(self, mensagens, ferramentas, *, esforco="low", max_tokens=800):
        raise LLMIndisponivel("provedor fora do ar (teste)")


def test_rodar_validacao_turno_com_erro_de_verdade_nao_conta_como_acerto(db):
    """Fix round 2 (finding 6, o caminho que importa): a versão anterior do
    fix em ``avaliar_caso`` só funcionava porque
    ``test_turno_com_erro_nao_conta_como_acerto_sem_ferramenta`` construía o
    resultado à mão com ``.estado`` setado direto. Em ``rodar_validacao`` —
    o caminho que o CLI e o gate real usam — o resultado é reembrulhado num
    ``SimpleNamespace``, e a versão anterior desse wrapper listava só
    texto/passos/latencia_ms, descartando ``.estado`` por engano: o guard
    nunca disparava de verdade. Este teste passa pelo ``executar_turno``
    real (via ``LLMIndisponivel``, sem rede) para provar que o erro
    sobrevive até ``Avaliacao.acertou_tool``."""
    caso = {
        "id": "x99", "pergunta": "oi, tudo bem?",
        "ferramenta_esperada": None, "exige_cobertura": False,
    }
    relatorio = rodar_validacao(_LLMDerruba(), _recursos(db), [caso])

    assert len(relatorio.avaliacoes) == 1
    avaliacao = relatorio.avaliacoes[0]
    # Zero tool-calls (o provedor nunca respondeu) + ferramenta_esperada
    # None seria "acerto" pela regra ingênua — mas o turno FALHOU, não
    # decidiu corretamente que não precisava de ferramenta.
    assert avaliacao.acertou_tool is False
