import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.loja.copiloto.port import LLMFake, LLMIndisponivel, RespostaLLM, ToolCall
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.copiloto.tools import RecursosTools
from scripts.copiloto_validacao import (
    Avaliacao,
    Relatorio,
    avaliar_caso,
    carregar_casos,
    extrair_numeros_da_resposta,
    folhas_numericas,
    normalizar_numero,
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


# --- Métrica 4 (I6): todo número na resposta rastreia a algum payload de
# ferramenta desta conversa — medida SEPARADA de pct_tool/pct_cobertura.


def test_normalizar_numero_br_e_payload_cru_batem():
    """R$ 412.000,00 (formatação BR da resposta) e "412000.00" (Decimal
    serializado cru pelo to_dict() da ferramenta) têm que normalizar para o
    MESMO Decimal — senão a métrica reprova resposta certa só por causa de
    formatação, o caso que o dono pediu para blindar explicitamente."""
    assert normalizar_numero("R$ 412.000,00") == Decimal("412000.00")
    assert normalizar_numero("412000.00") == Decimal("412000.00")
    assert normalizar_numero("R$ 412.000,00") == normalizar_numero("412000.00")
    assert normalizar_numero("29.428,57") == normalizar_numero("29428.57") == Decimal("29428.57")
    assert normalizar_numero("40%") == Decimal("40")
    assert normalizar_numero("82,5") == Decimal("82.5")
    assert normalizar_numero("não é número") is None


def test_extrair_numeros_da_resposta_ignora_data_ano_e_ordinal():
    """Data, ano solto e ordinal são restatement de período, não claim
    numérico de negócio — a métrica tem que ignorá-los (viés a favor de
    falso negativo, como pedido: nunca acusar violação por causa disso)."""
    texto = (
        "Em 12/08/2026, seu 1º colocado vendeu 6 das 14 unidades em 2026, "
        "faturando R$ 412.000,00."
    )
    numeros = extrair_numeros_da_resposta(texto)
    assert Decimal("6") in numeros
    assert Decimal("14") in numeros
    assert Decimal("412000.00") in numeros
    assert Decimal("12") not in numeros  # dia da data
    assert Decimal("8") not in numeros  # mês da data
    assert Decimal("2026") not in numeros  # ano solto
    assert Decimal("1") not in numeros  # ordinal "1º"


def test_folhas_numericas_pega_numero_aninhado_em_dict_e_lista():
    payload = {
        "status": "ok",
        "cobertura_data": {"com_dado": 6, "total": 14},
        "itens": [{"preco": "29428.57"}, {"preco": None, "placa": "ABC1D23"}],
        "capital_preso": "412000.00",
    }
    folhas = folhas_numericas(payload)
    assert Decimal("6") in folhas
    assert Decimal("14") in folhas
    assert Decimal("29428.57") in folhas
    assert Decimal("412000.00") in folhas


def test_avaliar_caso_resposta_limpa_com_formatacao_br_score_limpo():
    """O exemplo exato do dono: resposta formatada em R$ contra payload cru
    em string decimal — NÃO pode ser flagrado."""
    caso = {"id": "v10", "pergunta": "x", "ferramenta_esperada": "vendas_resumo", "exige_cobertura": False}
    payload_numeros = frozenset({Decimal("412000.00"), Decimal("29428.57")})
    resultado = ResultadoFalso(
        "Sua receita foi R$ 412.000,00, com ticket médio de R$ 29.428,57.",
        ["vendas_resumo"],
    )
    av = avaliar_caso(caso, resultado, payload_numeros)
    assert av.numeros_relevante is True
    assert av.numeros_ok is True


def test_avaliar_caso_numero_inventado_e_flagrado():
    caso = {"id": "v11", "pergunta": "x", "ferramenta_esperada": "vendas_resumo", "exige_cobertura": False}
    payload_numeros = frozenset({Decimal("412000.00")})
    resultado = ResultadoFalso(
        "Sua receita foi R$ 412.000,00 e sua margem é de 37%.", ["vendas_resumo"]
    )
    av = avaliar_caso(caso, resultado, payload_numeros)
    assert av.numeros_relevante is True
    assert av.numeros_ok is False  # 37% não veio de nenhum payload desta conversa


def test_avaliar_caso_sem_payload_nao_participa_da_metrica_4():
    """Compatibilidade: chamador que não passa payload_numeros (testes
    antigos, ResultadoFalso sem 3º argumento) fica FORA do denominador — não
    finge medição que não foi feita."""
    caso = {"id": "x02", "pergunta": "x", "ferramenta_esperada": None, "exige_cobertura": False}
    av = avaliar_caso(caso, ResultadoFalso("Você vendeu 2.", []))
    assert av.numeros_relevante is False


def test_relatorio_pct_numeros_rastreaveis_denominador_explicito():
    limpos = [
        Avaliacao(f"c{i}", True, True, 1000, numeros_relevante=True, numeros_ok=True)
        for i in range(3)
    ]
    com_invencao = [
        Avaliacao("c9", True, True, 1000, numeros_relevante=True, numeros_ok=False)
    ]
    sem_numero = [
        Avaliacao("n0", True, True, 1000, numeros_relevante=False, numeros_ok=True)
    ]
    relatorio = Relatorio(limpos + com_invencao + sem_numero)

    assert relatorio.pct_numeros_rastreaveis == round(3 / 4 * 100, 1)
    assert "3/4" in relatorio.to_markdown()


def test_relatorio_pct_numeros_rastreaveis_none_sem_caso_aplicavel():
    """Nenhuma resposta do lote tinha número extraível: None, nunca 100%
    fingido por ausência de caso (mesmo desenho de pct_cobertura)."""
    relatorio = Relatorio(
        [Avaliacao("a", True, True, 1000, numeros_relevante=False, numeros_ok=True)]
    )
    assert relatorio.pct_numeros_rastreaveis is None
    assert "sem resposta com número" in relatorio.to_markdown().lower()


class _EstoqueComVeiculoParado:
    """Um veículo parado há 40 dias, preço fixo — payload com número real
    de uma ferramenta de verdade (não um double manual), para provar o
    caminho fim a fim de _payload_numeros_do_turno via rodar_validacao."""

    def obter_loja(self):
        return {"slug": "loja-teste"}

    def listar(self, **_kw):
        return [
            {
                "id": "v1",
                "status": "disponivel",
                "marca": "Fiat", "modelo": "Argo", "ano_modelo": 2022,
                "preco": "15000.00",
                "criado_em": "2026-07-02T12:00:00+00:00",  # 40 dias antes de AGORA
            }
        ]


def test_rodar_validacao_fim_a_fim_resposta_limpa_nao_e_flagrada(db):
    """A resposta cita exatamente o capital preso (R$ 15.000,00) e os dias
    parados (40) que a ferramenta estoque_parado devolveu de verdade."""
    caso = {
        "id": "e10", "pergunta": "tenho veículo parado?",
        "ferramenta_esperada": "estoque_parado", "exige_cobertura": False,
    }
    ctx = CopilotoContexto(
        loja_slug="loja-teste", papel="dono", ator_email="d@l.test",
        hoje=date(2026, 8, 11),
    )
    recursos = RecursosTools(
        db=db, estoque=_EstoqueComVeiculoParado(), chatbot=_ChatbotStub(), ctx=ctx,
        agora=datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
    )
    llm = LLMFake([
        _tool("estoque_parado"),
        _texto("Você tem 1 veículo parado há 40 dias, com R$ 15.000,00 de capital preso."),
    ])
    relatorio = rodar_validacao(llm, recursos, [caso])

    assert relatorio.avaliacoes[0].numeros_relevante is True
    assert relatorio.avaliacoes[0].numeros_ok is True
    assert relatorio.pct_numeros_rastreaveis == 100.0


def test_rodar_validacao_fim_a_fim_numero_inventado_e_flagrado(db):
    """Mesma ferramenta, mesmo payload real — mas a resposta inventa um
    capital preso que a ferramenta nunca devolveu."""
    caso = {
        "id": "e11", "pergunta": "tenho veículo parado?",
        "ferramenta_esperada": "estoque_parado", "exige_cobertura": False,
    }
    ctx = CopilotoContexto(
        loja_slug="loja-teste", papel="dono", ator_email="d@l.test",
        hoje=date(2026, 8, 11),
    )
    recursos = RecursosTools(
        db=db, estoque=_EstoqueComVeiculoParado(), chatbot=_ChatbotStub(), ctx=ctx,
        agora=datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc),
    )
    llm = LLMFake([
        _tool("estoque_parado"),
        _texto("Você tem capital preso de R$ 99.000,00 em veículos parados."),
    ])
    relatorio = rodar_validacao(llm, recursos, [caso])

    assert relatorio.avaliacoes[0].numeros_relevante is True
    assert relatorio.avaliacoes[0].numeros_ok is False
    assert relatorio.pct_numeros_rastreaveis == 0.0
