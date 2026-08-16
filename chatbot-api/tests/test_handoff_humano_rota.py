"""3º gatilho da §5.2 pela porta HTTP: o cliente pediu humano.

Os outros dois gatilhos entram por ``solicitacoes-simulacao-humana``, que exige
CPF e nascimento. Este não pode exigir — a §5.2 diz que "pediu humano" pode vir
**antes** da simulação. Sem esta rota o agente do Modo 2 nao consegue abrir o
rodizio para quem so disse "quero falar com uma pessoa".
"""
import pytest

from app.models_db import FilaVendedor, LojaOperacionalProjecao, OfertaLead

CLIENTE_MODO2 = "5511966660001"
CLIENTE_MODO1 = "5511966660002"


@pytest.fixture
def _fila(db, loja_a):
    for i in range(2):
        db.add(FilaVendedor(
            id=f"{loja_a['loja_id'][:8]}-hh{i}",
            loja_id=loja_a["loja_id"],
            nome=f"Vend{i}",
            telefone=f"551197777000{i}",
            ordem=i,
            ativo=True,
            usuario_id=f"uhh-{i}",
        ))
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


def _ligar_modo2(db, loja_id, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    db.add(LojaOperacionalProjecao(
        loja_id=loja_id, aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-hh-{loja_id[:8]}",
    ))
    db.commit()


def test_pediu_humano_abre_o_rodizio_sem_exigir_cpf(
    client, db, loja_a, monkeypatch, _fila, outbound_fake
):
    """O corpo tem só telefone — e mesmo assim o vendedor é chamado."""
    _ligar_modo2(db, loja_a["loja_id"], monkeypatch)

    resposta = client.post(
        "/v1/operacao/handoff-humano",
        json={"telefone": CLIENTE_MODO2, "motivo": "quero falar com alguem"},
        headers=loja_a["headers"],
    )

    assert resposta.status_code == 202, resposta.text
    assert resposta.json()["acionado"] is True

    oferta = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == loja_a["loja_id"],
            OfertaLead.telefone_cliente == CLIENTE_MODO2,
        )
        .one()
    )
    assert oferta.estado == "aberta"
    # O cliente nao pode ficar no vacuo (§5.3): ele e avisado de que vao chamar.
    assert any(tipo == "texto" for tipo, _ in outbound_fake.enviados)


def test_loja_fora_do_modo_2_nao_abre_oferta(
    client, db, loja_a, monkeypatch, _fila, outbound_fake
):
    """Modo 1 tem grupo de estoque, nao rodizio: a rota nao pode ter efeito."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)  # flag ligada...
    # ...mas sem projecao whatsapp_modo=2 a loja segue no Modo 1.

    resposta = client.post(
        "/v1/operacao/handoff-humano",
        json={"telefone": CLIENTE_MODO1},
        headers=loja_a["headers"],
    )

    assert resposta.status_code == 202
    assert resposta.json() == {"acionado": False, "motivo": "loja_fora_do_modo_2"}
    assert (
        db.query(OfertaLead)
        .filter(OfertaLead.telefone_cliente == CLIENTE_MODO1)
        .count()
        == 0
    )
    assert outbound_fake.enviados == []


def test_telefone_invalido_recusado(client, db, loja_a, monkeypatch):
    _ligar_modo2(db, loja_a["loja_id"], monkeypatch)
    resposta = client.post(
        "/v1/operacao/handoff-humano",
        json={"telefone": "   "},
        headers=loja_a["headers"],
    )
    assert resposta.status_code == 422
