"""As rotas restantes do bot na credencial de integração (spec §6.2, Task 5).

O contrato é o mesmo em todas: token de loja segue como hoje; token de
integração exige `instance` e é 400 sem ela — nunca cai em "alguma" loja.
"""
import pytest

from app import servico


@pytest.fixture
def token_integracao(db):
    return {"Authorization": f"Bearer {servico.criar_credencial_integracao(db)}"}


POSTS_SEM_INSTANCE = [
    (
        "/v1/operacao/solicitacoes-simulacao-humana",
        {"telefone": "5511977730001", "interesse": "moto"},
        {"Idempotency-Key": "IDEM-INT-1"},
    ),
    ("/v1/operacao/moto-escolhida", {"telefone": "5511977730002", "placa": "ABC1D23"}, {}),
    (
        "/v1/simulacoes/solicitar",
        {"cpf": "11144477735", "nascimento": "1990-01-01", "placa": "ABC1D23"},
        {},
    ),
]


@pytest.mark.parametrize("rota,corpo,extra", POSTS_SEM_INSTANCE)
def test_post_com_integracao_sem_instance_e_400(
    client, token_integracao, rota, corpo, extra
):
    r = client.post(rota, json=corpo, headers={**token_integracao, **extra})

    assert r.status_code == 400, r.text


def test_buscar_estoque_com_integracao_resolve_pela_query(client, token_integracao, loja_a):
    r = client.get(
        "/v1/estoque/buscar",
        params={"termo": "honda", "instance": loja_a["instance"]},
        headers=token_integracao,
    )

    assert r.status_code == 200, r.text


def test_buscar_estoque_com_integracao_sem_instance_e_400(client, token_integracao):
    r = client.get(
        "/v1/estoque/buscar", params={"termo": "honda"}, headers=token_integracao
    )

    assert r.status_code == 400, r.text


def test_buscar_estoque_com_token_de_loja_segue_sem_instance(client, loja_a):
    """Expand-only: a query de hoje, sem instance, continua valendo."""
    r = client.get(
        "/v1/estoque/buscar", params={"termo": "honda"}, headers=loja_a["headers"]
    )

    assert r.status_code == 200, r.text
