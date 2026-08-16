"""Fluxo do Modo 2, de ponta a ponta.

Existe porque os testes unitários dos planos anteriores passavam com o
produto morto: cada função tinha teste chamando ela direto, e ninguém
percorria "chega mensagem → o rodízio começa". Resultado: `disparar_handoff`
ficou sem chamador e nenhum vendedor era chamado, nunca.

Este teste atravessa webhook → gatilho → oferta → clique → trava. Se ele
passar e o produto estiver morto de novo, é porque o buraco mudou de lugar.
"""
import hashlib
import hmac
import json

import pytest

from app.models_db import (
    FilaVendedor,
    LojaOperacionalProjecao,
    NotificacaoOperacional,
    OfertaLead,
)

SEGREDO = "app-secret-fluxo"

# Um cliente por teste: o SQLite dos testes é StaticPool compartilhado, sem
# limpeza entre casos, e uma busca por "oferta aberta da loja" pegaria a do
# teste vizinho.
CLIENTE_GATILHO = "5511977770001"
CLIENTE_CLIQUE = "5511977770002"


@pytest.fixture(autouse=True)
def _modo2_ligado(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    monkeypatch.setattr("app.main.config.GRAPH_PHONE_NUMBER_ID", "pnid-fluxo")
    projecao = LojaOperacionalProjecao(
        loja_id=loja_a["loja_id"], aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-fluxo-{loja_a['loja_id'][:8]}",
    )
    db.add(projecao)
    db.commit()
    yield
    # Teardown obrigatório: o SQLite dos testes é StaticPool compartilhado.
    # Deixar a projeção viva jogaria os testes seguintes que usam `loja_a` no
    # Modo 2, e o alerta de grupo do Modo 1 pararia de sair — falha que só
    # aparece na suíte inteira, nunca no arquivo isolado.
    db.delete(projecao)
    # O pedido de simulação cria NotificacaoOperacional antes do desvio do
    # Modo 2. Deixá-las pendentes faz o teste do drenador, que conta global,
    # achar 4 em vez de 1 — de novo, falha só na suíte inteira.
    db.query(NotificacaoOperacional).filter(
        NotificacaoOperacional.loja_id == loja_a["loja_id"]
    ).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def outbound_fake(monkeypatch):
    class _Fake:
        def __init__(self):
            self.enviados = []

        def send_text(self, **kw):
            self.enviados.append(("texto", kw))
            return {"messages": [{"id": "wamid.T"}]}

        def send_template_button(self, **kw):
            self.enviados.append(("template", kw))
            return {"messages": [{"id": "wamid.B"}]}

        def send_interactive_button(self, **kw):
            self.enviados.append(("interativa", kw))
            return {"messages": [{"id": "wamid.I"}]}

    fake = _Fake()
    monkeypatch.setattr("app.whatsapp_outbound.outbound_para_loja", lambda db, loja_id: fake)
    monkeypatch.setattr("app.main.outbound_para_loja", lambda db, loja_id: fake, raising=False)
    return fake


def _assinar(corpo: bytes) -> dict:
    mac = hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={mac}", "Content-Type": "application/json"}


def _inbound(phone_number_id: str, **mensagem) -> bytes:
    """`phone_number_id` é o que mapeia para a loja — usa a instância da fixture."""
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba", "changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": phone_number_id},
            "messages": [mensagem],
        }}]}],
    }).encode()


def _pedido(telefone: str) -> dict:
    """Intake completo: o endpoint bloqueia sem CPF e nascimento válidos."""
    return {
        "telefone": telefone,
        "interesse": "Biz 125",
        "tem_cnh": "sim",
        "cpf": "39053344705",
        "nascimento": "10/05/1990",
        "cpf_recebido": True,
        "nascimento_recebido": True,
    }


def _fila(db, loja_id, quantos=2):
    for i in range(quantos):
        db.add(FilaVendedor(
            id=f"{loja_id[:8]}-fluxo{i}", loja_id=loja_id, nome=f"Vend{i}",
            telefone=f"551198888000{i}", ordem=i, ativo=True, usuario_id=f"u-{i}",
        ))
    db.commit()


def test_pedido_de_humano_abre_o_rodizio(client, db, loja_a, outbound_fake):
    """O gatilho tem que sair do fluxo real, não de chamada direta em teste."""
    _fila(db, loja_a["loja_id"])

    resposta = client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        json=_pedido(CLIENTE_GATILHO),
        headers={**loja_a["headers"], "Idempotency-Key": "fluxo-1"},
    )
    assert resposta.status_code in (200, 202), resposta.text

    abertas = db.query(OfertaLead).filter(
        OfertaLead.loja_id == loja_a["loja_id"],
        OfertaLead.telefone_cliente == CLIENTE_GATILHO,
        OfertaLead.estado == "aberta",
    ).all()
    assert len(abertas) == 1, "o rodízio não começou: nenhum vendedor foi chamado"
    assert abertas[0].vendedor_id.endswith("fluxo0")


def test_clique_do_vendedor_trava_o_lead(client, db, loja_a, outbound_fake):
    _fila(db, loja_a["loja_id"])
    client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        json=_pedido(CLIENTE_CLIQUE),
        headers={**loja_a["headers"], "Idempotency-Key": "fluxo-2"},
    )
    oferta = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == loja_a["loja_id"],
            OfertaLead.telefone_cliente == CLIENTE_CLIQUE,
            OfertaLead.estado == "aberta",
        )
        .one()
    )

    corpo = _inbound(loja_a["instance"], **{
        "from": "5511988880000", "id": "wamid.clique", "type": "button",
        "button": {"payload": f"pego:{oferta.id}", "text": "Peguei"},
    })
    assert client.post(
        "/webhook/cloud", content=corpo, headers=_assinar(corpo)
    ).status_code == 200

    db.refresh(oferta)
    assert oferta.estado == "travada"


def test_loja_modo_1_nao_abre_rodizio(client, db, loja_b, outbound_fake, monkeypatch):
    """Regressão do Modo 1: o grupo continua sendo o caminho lá."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_b["loja_id"])

    client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        json=_pedido("5511955554444"),
        headers={**loja_b["headers"], "Idempotency-Key": "fluxo-3"},
    )

    assert db.query(OfertaLead).filter(OfertaLead.loja_id == loja_b["loja_id"]).count() == 0


CLIENTE_VOLTA = "5511977770003"


def test_cliente_que_volta_a_escrever_recebe_recado(client, db, loja_a, outbound_fake):
    """Spec §5.4: a central se cala, mas o cliente não pode falar sozinho.

    Sem esta ligação, `cliente_voltou_a_escrever` existe e nada a chama: o
    cliente escreve no número do anúncio e ninguém responde nada.
    """
    _fila(db, loja_a["loja_id"])
    client.post(
        "/v1/operacao/solicitacoes-simulacao-humana",
        json=_pedido(CLIENTE_VOLTA),
        headers={**loja_a["headers"], "Idempotency-Key": "fluxo-4"},
    )
    oferta = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == loja_a["loja_id"],
            OfertaLead.telefone_cliente == CLIENTE_VOLTA,
            OfertaLead.estado == "aberta",
        )
        .one()
    )
    from app.rodizio import assumir_oferta

    assumir_oferta(db, oferta.id)
    antes = len(outbound_fake.enviados)

    corpo = _inbound(loja_a["instance"], **{
        "from": CLIENTE_VOLTA, "id": "wamid.volta", "type": "text",
        "text": {"body": "oi, alguém aí?"},
    })
    assert client.post(
        "/webhook/cloud", content=corpo, headers=_assinar(corpo)
    ).status_code == 200

    enviados = outbound_fake.enviados[antes:]
    assert any(
        kw.get("number") == CLIENTE_VOLTA for _tipo, kw in enviados
    ), "cliente falou sozinho: nenhum recado saiu"
