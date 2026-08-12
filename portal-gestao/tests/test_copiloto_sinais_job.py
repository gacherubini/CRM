from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from conftest import seed_loja_operacional

from app.clients.chatbot import ChatbotClient
from app.clients.estoque import EstoqueClient, VeiculoNaoEncontrado
from app.clients.fipe import FipeClient
from app.copiloto_sinais_job import (
    CopilotoSinaisWorker,
    _parse_valor_fipe,
    avaliar_loja,
)
from app.db import SessionLocal
from app.loja.copiloto.fipe import cache_fipe
from app.loja.types import Module
from app.models import CopilotoSinal, LojaOperacionalProjecao, Venda

AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _cache_fipe_limpo():
    """Cache de marca/modelo da FIPE é global (Fase 3): isolar entre testes
    deste arquivo, mesmo padrão de tests/test_copiloto_fipe.py."""
    cache_fipe.invalidar()
    yield
    cache_fipe.invalidar()


class EstoqueStub:
    def __init__(self, veiculos=None, slug="loja-teste"):
        self.veiculos = veiculos if veiculos is not None else []
        self.slug = slug

    def obter_loja(self):
        return {"slug": self.slug}

    def listar(self, **filtros):
        return list(self.veiculos)

    def obter(self, veiculo_id):
        for v in self.veiculos:
            if str(v.get("id")) == str(veiculo_id):
                return dict(v)
        raise VeiculoNaoEncontrado("não existe")


class ChatbotStub:
    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        return []

    def listar_leads(self, etapa=None):
        return []


def _veiculo_parado(dias=90):
    return {
        "id": "v1",
        "marca": "Honda",
        "modelo": "CB 500F",
        "ano_modelo": 2020,
        "preco": 25000.0,
        "status": "disponivel",
        "criado_em": (AGORA - timedelta(days=dias)).isoformat(),
        "tem_foto": True,
    }


def _veiculo_fipe(id_, dias, preco, modelo="CB 500F ABS"):
    """Igual a ``_veiculo_parado``, mas com ``tipo`` — necessário para o
    matching FIPE (``_tipo_fipe`` falha fechado sem ele)."""
    return {
        "id": id_,
        "tipo": "moto",
        "marca": "Honda",
        "modelo": modelo,
        "ano_modelo": 2020,
        "preco": preco,
        "status": "disponivel",
        "criado_em": (AGORA - timedelta(days=dias)).isoformat(),
        "tem_foto": True,
    }


# --- fixtures FIPE (mesmo padrão de tests/test_copiloto_fipe.py) -----------

_FIPE_MARCAS = [{"codigo": "80", "nome": "Honda"}]
_FIPE_MODELOS = {
    "modelos": [
        {"codigo": "5140", "nome": "CB 500F ABS"},
        {"codigo": "5141", "nome": "CB 500X ABS"},
    ]
}
_FIPE_ANOS = [{"codigo": "2020-1", "nome": "2020 Gasolina"}]
_FIPE_VALOR = {"Valor": "R$ 25.000,00", "MesReferencia": "agosto de 2026"}


def _fipe_client(indisponivel=False, chamadas=None):
    def handler(request):
        if chamadas is not None:
            chamadas.append(request.url.path)
        if indisponivel:
            return httpx.Response(503, json={})
        rotas = {
            "/motos/marcas": _FIPE_MARCAS,
            "/80/modelos": _FIPE_MODELOS,
            "/5140/anos": _FIPE_ANOS,
            "/5140/anos/2020-1": _FIPE_VALOR,
        }
        for sufixo, corpo in rotas.items():
            if request.url.path.endswith(sufixo):
                return httpx.Response(200, json=corpo)
        return httpx.Response(404, json={})

    return FipeClient("https://fipe.test", transport=httpx.MockTransport(handler))


class EstoqueListarQuebraNaSegundaChamada(EstoqueStub):
    """Bug real, não o offline conhecido: a 1ª leitura (usada por
    ``estoque_parado``) funciona; a 2ª leitura direta do ``avaliar_loja``
    (usada por ``regra_cadastro_incompleto``) explode com payload malformado
    — não é ``EstoqueIndisponivel``."""

    def __init__(self, veiculos=None, slug="loja-teste"):
        super().__init__(veiculos, slug)
        self.chamadas = 0

    def listar(self, **filtros):
        self.chamadas += 1
        if self.chamadas == 1:
            return super().listar(**filtros)
        raise TypeError("payload malformado do estoque")


def test_falha_inesperada_em_estoque_listar_degrada_e_loga(db, caplog):
    seed_loja_operacional(db)
    db.commit()
    with caplog.at_level("WARNING", logger="app.copiloto_sinais_job"):
        candidatos = avaliar_loja(
            db,
            "loja-teste",
            estoque=EstoqueListarQuebraNaSegundaChamada(),
            chatbot=ChatbotStub(),
            agora=AGORA,
        )
    regras = {c.regra for c in candidatos}
    assert "cadastro_incompleto" not in regras
    avisos = [rec for rec in caplog.records if rec.levelname == "WARNING"]
    assert any(
        "estoque.listar" in rec.getMessage() and "loja-teste" in rec.getMessage()
        for rec in avisos
    )


def test_avaliar_loja_gera_candidato_de_estoque_parado(db):
    seed_loja_operacional(db)
    db.commit()
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub([_veiculo_parado()]),
        chatbot=ChatbotStub(),
        agora=AGORA,
    )
    regras = {c.regra for c in candidatos}
    assert "estoque_parado" in regras


def test_avaliar_loja_gera_margem_incompleta(db):
    seed_loja_operacional(db)
    for i in range(4):
        db.add(
            Venda(
                loja_slug="loja-teste",
                vendedor_email="ana@loja.test",
                descricao="Moto",
                preco_venda=Decimal("20000"),
                custo_veiculo=Decimal("16000") if i == 0 else None,
                status="confirmada",
                criada_em=AGORA - timedelta(days=2),
            )
        )
    db.commit()
    candidatos = avaliar_loja(
        db, "loja-teste", estoque=EstoqueStub(), chatbot=ChatbotStub(), agora=AGORA
    )
    regras = {c.regra for c in candidatos}
    assert "margem_incompleta" in regras
    assert "atribuicao_baixa" in regras


def test_run_once_persiste_sinais_da_loja_ativa(db):
    seed_loja_operacional(db)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    resultado = worker.run_once()
    assert resultado["ok"] is True
    assert resultado["lojas"] == 1
    assert db.query(CopilotoSinal).filter(CopilotoSinal.regra == "estoque_parado").count() == 1


def test_run_once_desligado_nao_toca_o_banco(db):
    seed_loja_operacional(db)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=False,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    assert worker.run_once()["ok"] is False
    assert db.query(CopilotoSinal).count() == 0


def test_loja_inativa_nao_e_avaliada(db):
    seed_loja_operacional(db, loja_slug="loja-teste", state="suspensa", version=2)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    assert worker.run_once()["lojas"] == 0
    assert db.query(CopilotoSinal).count() == 0


def test_falha_em_uma_loja_nao_derruba_o_ciclo(db):
    seed_loja_operacional(db, loja_slug="loja-teste")
    seed_loja_operacional(db, loja_slug="loja-2")
    db.commit()

    class EstoqueQuebrado(EstoqueStub):
        def listar(self, **filtros):
            raise RuntimeError("boom")

    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueQuebrado(slug="loja-teste"),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    resultado = worker.run_once()
    assert resultado["ok"] is True
    assert resultado["erros"] >= 1


def test_loja_sem_entitlement_copiloto_e_pulada(db, monkeypatch):
    """Gate duplo: com REVY_LOJA_ENTITLEMENTS_ENABLED=1, loja ativa mas sem o
    módulo Copiloto contratado não é avaliada — nenhum dado é buscado, nenhum
    sinal é gravado. A loja entitled ao lado continua funcionando normalmente.
    """
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    seed_loja_operacional(db, loja_slug="loja-teste")  # sem módulo copiloto
    seed_loja_operacional(db, loja_slug="loja-2")
    db.add(
        LojaOperacionalProjecao(
            loja_slug="loja-2",
            aggregate=Module.COPILOTO.value,
            version=1,
            state="ativo",
            event_id="seed-copiloto",
        )
    )
    for i in range(4):
        db.add(
            Venda(
                loja_slug="loja-2",
                vendedor_email="ana@loja.test",
                descricao="Moto",
                preco_venda=Decimal("20000"),
                custo_veiculo=Decimal("16000") if i == 0 else None,
                status="confirmada",
                criada_em=AGORA - timedelta(days=2),
            )
        )
    db.commit()

    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueStub(slug="loja-2"),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    resultado = worker.run_once()
    assert resultado["ok"] is True
    assert resultado["lojas"] == 1  # só a loja-2, entitled
    assert db.query(CopilotoSinal).filter(CopilotoSinal.loja_slug == "loja-teste").count() == 0
    assert (
        db.query(CopilotoSinal)
        .filter(CopilotoSinal.loja_slug == "loja-2", CopilotoSinal.regra == "margem_incompleta")
        .count()
        == 1
    )


def test_clients_padrao_nao_importa_app_main(db):
    """O caminho de produção (sem factories injetadas) constrói os clients
    direto de app.clients/app.config — não pode depender de app.main (import
    de volta para o módulo que inicia o worker), e não pode ficar sem
    cobertura só porque os testes acima sempre injetam stub.
    """
    worker = CopilotoSinaisWorker(db_factory=SessionLocal, enabled=True, agora=lambda: AGORA)
    estoque, chatbot, fipe = worker._clients()
    assert isinstance(estoque, EstoqueClient)
    assert isinstance(chatbot, ChatbotClient)
    assert isinstance(fipe, FipeClient)


# --- regra 7: preço fora da faixa da FIPE, ligada ao worker ----------------


def test_avaliar_loja_preco_muito_acima_da_fipe_gera_sinal(db):
    seed_loja_operacional(db)
    db.commit()
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub([_veiculo_fipe("v1", dias=5, preco=40000)]),
        chatbot=ChatbotStub(),
        fipe=_fipe_client(),
        agora=AGORA,
    )
    sinais_preco = [c for c in candidatos if c.regra == "preco_fora_da_faixa"]
    assert len(sinais_preco) == 1
    assert sinais_preco[0].entidade_ref == "v1"
    assert sinais_preco[0].severidade == "atencao"


def test_avaliar_loja_fipe_indisponivel_nao_gera_sinal_de_preco(db):
    """FIPE fora do ar para o veículo -> nenhum sinal. Não existe
    "provavelmente caro"."""
    seed_loja_operacional(db)
    db.commit()
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub([_veiculo_fipe("v1", dias=5, preco=99999)]),
        chatbot=ChatbotStub(),
        fipe=_fipe_client(indisponivel=True),
        agora=AGORA,
    )
    assert "preco_fora_da_faixa" not in {c.regra for c in candidatos}


def test_avaliar_loja_com_fipe_fora_nao_derruba_as_outras_regras(db):
    """Verificação de fechamento da F4: "com a FIPE fora, nenhum sinal de
    preço, e os alertas das outras regras continuam aparecendo". A regra 7
    fica atrás de um `if fipe is not None` isolado (`avaliar_loja` acima) —
    este teste prova isso na integração, não só por leitura de código: um
    estoque e vendas que disparam QUATRO das outras seis regras ao mesmo
    tempo em que a FIPE está fora continuam gerando os quatro sinais, e
    nenhum sinal de preço aparece.

    ``_veiculo_parado()`` não tem o campo ``tipo`` (só ``_veiculo_fipe`` tem,
    de propósito, para o matching FIPE) — por isso também é lacuna de
    cadastro, além de estoque parado; junto com as 4 vendas sem custo do
    padrão de ``test_avaliar_loja_gera_margem_incompleta``, cobre
    estoque_parado, cadastro_incompleto, margem_incompleta e
    atribuicao_baixa nesta mesma chamada."""
    seed_loja_operacional(db)
    for i in range(4):
        db.add(
            Venda(
                loja_slug="loja-teste",
                vendedor_email="ana@loja.test",
                descricao="Moto",
                preco_venda=Decimal("20000"),
                custo_veiculo=Decimal("16000") if i == 0 else None,
                status="confirmada",
                criada_em=AGORA - timedelta(days=2),
            )
        )
    db.commit()
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub([_veiculo_parado()]),
        chatbot=ChatbotStub(),
        fipe=_fipe_client(indisponivel=True),
        agora=AGORA,
    )
    regras = {c.regra for c in candidatos}
    assert "preco_fora_da_faixa" not in regras
    assert {
        "estoque_parado",
        "cadastro_incompleto",
        "margem_incompleta",
        "atribuicao_baixa",
    } <= regras


def test_avaliar_loja_fipe_ambiguo_nao_gera_sinal_de_preco(db):
    """Matching sem candidato exato e único -> nenhum sinal, mesmo com preço
    absurdo: a Fase 3 nunca adivinha, e um alerta proativo é pior lugar para
    adivinhar do que uma resposta de chat, porque ninguém perguntou nada."""
    seed_loja_operacional(db)
    db.commit()
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub(
            [_veiculo_fipe("v1", dias=5, preco=99999, modelo="CB 500")]
        ),
        chatbot=ChatbotStub(),
        fipe=_fipe_client(),
        agora=AGORA,
    )
    assert "preco_fora_da_faixa" not in {c.regra for c in candidatos}


def test_avaliar_loja_sem_fipe_client_pula_a_regra(db):
    """fipe=None (default) degrada como qualquer outra dependência externa
    deste arquivo — não derruba o ciclo, só pula a regra 7."""
    seed_loja_operacional(db)
    db.commit()
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub([_veiculo_fipe("v1", dias=5, preco=99999)]),
        chatbot=ChatbotStub(),
        agora=AGORA,
    )
    assert "preco_fora_da_faixa" not in {c.regra for c in candidatos}


def test_avaliar_loja_respeita_teto_e_prioriza_mais_parado(db, monkeypatch):
    """Teto por ciclo (default 10, aqui forçado a 1) é convivência com API
    comunitária sem SLA — e quem é consultado primeiro é quem está parado há
    mais tempo, nunca ordem de cadastro."""
    monkeypatch.setenv("PORTAL_COPILOTO_FIPE_POR_CICLO", "1")
    seed_loja_operacional(db)
    db.commit()
    chamadas: list[str] = []
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub(
            [
                _veiculo_fipe("v1", dias=200, preco=40000),
                _veiculo_fipe("v2", dias=50, preco=40000),
            ]
        ),
        chatbot=ChatbotStub(),
        fipe=_fipe_client(chamadas=chamadas),
        agora=AGORA,
    )
    sinais_preco = [c for c in candidatos if c.regra == "preco_fora_da_faixa"]
    assert len(sinais_preco) == 1
    assert sinais_preco[0].entidade_ref == "v1"  # 200 dias > 50 dias
    # /anos nunca é cacheado (só marca/modelo): contar essa rota isola
    # quantos veículos de fato foram consultados nesta rodada.
    assert sum(1 for c in chamadas if c.endswith("/5140/anos")) == 1


# --- _parse_valor_fipe: dado externo malformado nunca vira valor aproximado


def test_parse_valor_fipe_formato_br_padrao():
    assert _parse_valor_fipe("R$ 27.500,00") == Decimal("27500.00")


def test_parse_valor_fipe_sem_separador_de_milhar():
    assert _parse_valor_fipe("R$ 500,00") == Decimal("500.00")


def test_parse_valor_fipe_varios_separadores_de_milhar():
    assert _parse_valor_fipe("R$ 1.234.567,89") == Decimal("1234567.89")


def test_parse_valor_fipe_sem_espaco_apos_cifrao():
    assert _parse_valor_fipe("R$27.500,00") == Decimal("27500.00")


def test_parse_valor_fipe_negativo_e_rejeitado_nao_vira_positivo():
    """O defeito real encontrado na revisão: o regex antigo removia o '-' em
    vez de rejeitar o valor inteiro, e '-27.500,00' virava Decimal positivo.
    Um 'Valor' negativo não é preço malformado que dá para consertar — é
    sinal de que a resposta não deve ser usada."""
    assert _parse_valor_fipe("-27.500,00") is None
    assert _parse_valor_fipe("R$ -27.500,00") is None


def test_parse_valor_fipe_zero_e_rejeitado():
    assert _parse_valor_fipe("R$ 0,00") is None


def test_parse_valor_fipe_vazio_e_none_sao_rejeitados():
    assert _parse_valor_fipe("") is None
    assert _parse_valor_fipe(None) is None


def test_parse_valor_fipe_formato_americano_e_rejeitado():
    """'27500.00' não é BR — se fosse aceito por engano, viraria 100x o
    valor real (2750000) ao tratar o ponto como separador de milhar."""
    assert _parse_valor_fipe("27500.00") is None


def test_parse_valor_fipe_sem_cifrao_e_rejeitado():
    assert _parse_valor_fipe("27.500,00") is None


def test_parse_valor_fipe_texto_arbitrario_e_rejeitado():
    assert _parse_valor_fipe("consulte o revendedor") is None


# --- dedupe/cooldown pelo caminho do worker (brief item 7) ------------------


def test_avaliar_loja_preco_fora_da_faixa_atualiza_em_vez_de_duplicar_no_worker(db):
    """O brief pede prova pelo caminho do worker, não só da regra: rodar
    avaliar_loja + sincronizar_sinais duas vezes para o MESMO veículo caro
    tem que reconciliar (1 criado, depois 1 atualizado), nunca duplicar uma
    segunda linha 'preco_fora_da_faixa' para o mesmo entidade_ref."""
    from app.loja.copiloto.sinais_store import sincronizar_sinais

    seed_loja_operacional(db)
    db.commit()

    estoque = EstoqueStub([_veiculo_fipe("v1", dias=90, preco=40000)])
    chatbot = ChatbotStub()
    fipe = _fipe_client()

    candidatos_1 = avaliar_loja(
        db, "loja-teste", estoque=estoque, chatbot=chatbot, fipe=fipe, agora=AGORA
    )
    resultado_1 = sincronizar_sinais(db, "loja-teste", candidatos_1, agora=AGORA)
    db.commit()
    # dias=90 também passa do limiar de "estoque parado" (60 dias): a regra 1
    # dispara junto com a regra 7 para o mesmo veículo — 2 sinais no ciclo 1,
    # não é sinal de duplicação da regra 7.
    assert resultado_1.criados == 2

    agora_2 = AGORA + timedelta(minutes=30)
    candidatos_2 = avaliar_loja(
        db, "loja-teste", estoque=estoque, chatbot=chatbot, fipe=fipe, agora=agora_2
    )
    resultado_2 = sincronizar_sinais(db, "loja-teste", candidatos_2, agora=agora_2)
    db.commit()
    assert resultado_2.criados == 0
    assert resultado_2.atualizados == 2

    linhas = (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.loja_slug == "loja-teste",
            CopilotoSinal.regra == "preco_fora_da_faixa",
        )
        .all()
    )
    assert len(linhas) == 1
    assert linhas[0].entidade_ref == "v1"
