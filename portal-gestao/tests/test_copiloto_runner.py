from datetime import date, datetime, timezone
from decimal import Decimal

from app.loja.copiloto.port import (
    LLMFake,
    LLMIndisponivel,
    RespostaLLM,
    ToolCall,
)
from app.loja.copiloto.runner import custo_estimado, executar_turno
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.copiloto.tools import RecursosTools

AGORA = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste", papel="dono", ator_email="d@l.test",
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    def obter_loja(self):
        return {"slug": "loja-teste"}

    def listar(self, **f):
        return []


class ChatbotStub:
    def listar_conversas(self, **k):
        return []

    def listar_leads(self, etapa=None):
        return []


def _recursos(db):
    return RecursosTools(
        db=db, estoque=EstoqueStub(), chatbot=ChatbotStub(), ctx=_ctx(), agora=AGORA
    )


def _tool(nome, args=None, id_="c1"):
    return RespostaLLM(
        texto=None,
        tool_calls=(ToolCall(id=id_, nome=nome, argumentos=args or {}),),
        tokens_entrada=1000, tokens_saida=20, finish_reason="tool_calls",
    )


def _texto(txt, entrada=1200, saida=40):
    return RespostaLLM(
        texto=txt, tool_calls=(), tokens_entrada=entrada, tokens_saida=saida,
        finish_reason="stop",
    )


def test_pergunta_com_uma_ferramenta(db):
    llm = LLMFake([_tool("vendas_resumo"), _texto("Você não vendeu nada em agosto.")])
    r = executar_turno(
        pergunta="quanto vendi?", historico=[], llm=llm, recursos=_recursos(db)
    )
    assert r.estado == "pronto"
    assert r.texto == "Você não vendeu nada em agosto."
    assert [p.ferramenta for p in r.passos] == ["vendas_resumo"]
    assert r.passos[0].status == "ok"


def test_resposta_direta_sem_ferramenta(db):
    llm = LLMFake([_texto("Posso te dizer vendas, estoque e leads.")])
    r = executar_turno(
        pergunta="o que você faz?", historico=[], llm=llm, recursos=_recursos(db)
    )
    assert r.estado == "pronto"
    assert r.passos == ()


def test_cadeia_de_duas_ferramentas_sobe_o_esforco(db):
    llm = LLMFake(
        [_tool("estoque_parado", {"dias_min": 60}), _tool("vendas_resumo", id_="c2"),
         _texto("Pronto.")]
    )
    r = executar_turno(
        pergunta="e aí?", historico=[], llm=llm, recursos=_recursos(db)
    )
    assert [p.ferramenta for p in r.passos] == ["estoque_parado", "vendas_resumo"]
    assert llm.chamadas[0]["esforco"] == "low"
    assert llm.chamadas[1]["esforco"] == "high"


def test_ferramenta_desconhecida_nao_executa_e_o_modelo_corrige(db):
    llm = LLMFake([_tool("apagar_tudo"), _texto("Desculpa, vou usar a função certa.")])
    r = executar_turno(
        pergunta="apaga tudo", historico=[], llm=llm, recursos=_recursos(db)
    )
    assert r.estado == "pronto"
    assert r.passos[0].status == "erro"
    assert "apagar_tudo" == r.passos[0].ferramenta


def test_provedor_fora_vira_erro_e_nao_texto(db):
    class LLMQuebrado:
        def completar(self, *a, **k):
            raise LLMIndisponivel("fora")

    r = executar_turno(
        pergunta="quanto vendi?", historico=[], llm=LLMQuebrado(),
        recursos=_recursos(db),
    )
    assert r.estado == "erro"
    assert r.erro_code == "provedor"
    assert r.texto is None or "número" not in (r.texto or "")


def test_deadline_encerra_sem_inventar_numero(db):
    marcas = iter([0.0, 1.0, 99.0, 99.0, 99.0])
    llm = LLMFake([_tool("vendas_resumo"), _texto("Você vendeu 12 motos.")])
    r = executar_turno(
        pergunta="quanto vendi?", historico=[], llm=llm, recursos=_recursos(db),
        deadline_segundos=45, relogio=lambda: next(marcas),
    )
    assert r.estado == "erro"
    assert r.erro_code == "deadline"
    assert "12 motos" not in (r.texto or "")


def test_teto_de_iteracoes_encerra_o_loop(db):
    llm = LLMFake([_tool("vendas_resumo", id_=f"c{i}") for i in range(6)])
    r = executar_turno(
        pergunta="loop", historico=[], llm=llm, recursos=_recursos(db),
        max_iteracoes=3,
    )
    assert r.estado == "erro"
    assert r.erro_code == "max_iteracoes"
    assert len(r.passos) == 3


def test_teto_de_tokens_recusa_antes_de_chamar_o_provedor(db):
    llm = LLMFake([_tool("vendas_resumo"), _texto("ok", entrada=50000, saida=100)])
    r = executar_turno(
        pergunta="quanto vendi?", historico=[], llm=llm, recursos=_recursos(db),
        teto_tokens=1500,
    )
    assert r.estado == "erro"
    assert r.erro_code == "teto_tokens"
    # Só a primeira chamada aconteceu: o teto barrou a segunda.
    assert len(llm.chamadas) == 1


def test_callback_de_passo_alimenta_a_ui(db):
    vistos = []
    llm = LLMFake([_tool("vendas_resumo"), _texto("ok")])
    executar_turno(
        pergunta="quanto vendi?", historico=[], llm=llm, recursos=_recursos(db),
        on_passo=lambda passos: vistos.append(len(passos)),
    )
    assert vistos and vistos[-1] == 1


def test_historico_entra_como_contexto(db):
    llm = LLMFake([_texto("ok")])
    executar_turno(
        pergunta="e o mês passado?",
        historico=[("qual meu ticket?", "Foi R$ 25.000.")],
        llm=llm,
        recursos=_recursos(db),
    )
    papeis = [m.papel for m in llm.chamadas[0]["mensagens"]]
    assert papeis[0] == "system"
    assert "assistant" in papeis
    assert papeis[-1] == "user"


def test_tokens_somam_todas_as_chamadas(db):
    llm = LLMFake([_tool("vendas_resumo"), _texto("ok")])
    r = executar_turno(
        pergunta="quanto vendi?", historico=[], llm=llm, recursos=_recursos(db)
    )
    assert r.tokens_entrada == 2200
    assert r.tokens_saida == 60


def test_custo_estimado_usa_a_tabela_do_provedor():
    # $0.14/M entrada, $0.28/M saída.
    assert custo_estimado(1_000_000, 0) == Decimal("0.140000")
    assert custo_estimado(0, 1_000_000) == Decimal("0.280000")
