"""O vendedor da fila precisa apontar para a pessoa da Loja (`Usuario.id`).

Sem isso, o sinal do sino é endereçado ao `fila_vendedor.id` — um UUID do
chatbot que nenhum usuário do Portal tem — e o sino não toca para ninguém.
"""
import pytest

from app.models_db import FilaVendedor, LojaOperacionalProjecao
from app.rodizio import abrir_oferta


@pytest.fixture(autouse=True)
def _modo2_on(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    db.add(LojaOperacionalProjecao(
        loja_id=loja_a["loja_id"], aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-vinc-{loja_a['loja_id'][:8]}",
    ))
    db.commit()


def test_vendedor_nasce_sem_vinculo(db, loja_a):
    """Nullable: fila cadastrada por API antes da tela continua válida."""
    v = FilaVendedor(
        id=f"{loja_a['loja_id'][:8]}-fv0", loja_id=loja_a["loja_id"],
        nome="Ana", telefone="5511999990000", ordem=0,
    )
    db.add(v)
    db.commit()
    assert v.usuario_id is None


def test_criar_pela_rota_guarda_o_usuario_da_loja(client, loja_a):
    criado = client.post(
        "/v1/fila-vendedores",
        json={"nome": "Ana", "telefone": "11999990000", "usuario_id": "u-ana"},
        headers=loja_a["headers"],
    ).json()
    assert criado["usuario_id"] == "u-ana"


def test_patch_vincula_vendedor_ja_cadastrado(client, loja_a):
    criado = client.post(
        "/v1/fila-vendedores",
        json={"nome": "Bruno", "telefone": "11988887777"},
        headers=loja_a["headers"],
    ).json()
    assert criado["usuario_id"] is None

    atualizado = client.patch(
        f"/v1/fila-vendedores/{criado['id']}",
        json={"usuario_id": "u-bruno"},
        headers=loja_a["headers"],
    ).json()
    assert atualizado["usuario_id"] == "u-bruno"


def test_oferta_expoe_o_usuario_para_o_sino(client, db, loja_a):
    """É este campo que vira `destinatario_usuario_id` no Portal."""
    db.add(FilaVendedor(
        id=f"{loja_a['loja_id'][:8]}-fv1", loja_id=loja_a["loja_id"],
        nome="Ana", telefone="5511999990000", ordem=0, usuario_id="u-ana",
    ))
    db.commit()
    abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    corpo = client.get("/v1/ofertas", headers=loja_a["headers"]).json()
    assert corpo[0]["vendedor_usuario_id"] == "u-ana"


def test_oferta_de_vendedor_sem_vinculo_expoe_none(db, client, loja_a):
    """O Portal precisa distinguir 'sem vínculo' para não endereçar a ninguém."""
    db.add(FilaVendedor(
        id=f"{loja_a['loja_id'][:8]}-fv2", loja_id=loja_a["loja_id"],
        nome="Sem Vinculo", telefone="5511977776666", ordem=0,
    ))
    db.commit()
    abrir_oferta(db, loja_a["loja_id"], "5511966665555")

    corpo = client.get("/v1/ofertas", headers=loja_a["headers"]).json()
    assert corpo[0]["vendedor_usuario_id"] is None
