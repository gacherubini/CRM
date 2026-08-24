"""O bug do smoke, capturado em teste: o token da plataforma tem de achar a
conversa da loja da `instance`, não a de uma loja fixa (spec §6.2)."""
from app import servico


def _semear_entrada(client, instance, telefone, pmid):
    client.post(
        "/webhook/mensagem",
        json={
            "instance": instance,
            "telefone": telefone,
            "texto": "quero saber da moto",
            "provider_message_id": pmid,
        },
    )


def test_integracao_acha_conversa_da_loja_da_instance(client, db, loja_b):
    tel = "5511977710001"
    _semear_entrada(client, loja_b["instance"], tel, "SMOKE-B-1")
    token = servico.criar_credencial_integracao(db)

    r = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": loja_b["instance"], "provider_message_id": "SMOKE-B-1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 200
    assert r.json()["pode_responder"] is True


def test_um_token_de_integracao_serve_as_duas_lojas(client, db, loja_a, loja_b):
    """O ponto do card: um workflow, N lojas. Com uma loja so, o bug passa."""
    tel = "5511977710002"
    _semear_entrada(client, loja_a["instance"], tel, "MULTI-A-1")
    _semear_entrada(client, loja_b["instance"], tel, "MULTI-B-1")
    token = servico.criar_credencial_integracao(db)
    h = {"Authorization": f"Bearer {token}"}

    para_a = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": loja_a["instance"], "provider_message_id": "MULTI-A-1"},
        headers=h,
    )
    para_b = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": loja_b["instance"], "provider_message_id": "MULTI-B-1"},
        headers=h,
    )

    assert para_a.json()["pode_responder"] is True, para_a.json()
    assert para_b.json()["pode_responder"] is True, para_b.json()


def test_credencial_de_loja_segue_presa_a_propria_loja(client, db, loja_a, loja_b):
    """Expand-only e isolamento: token da A nao alcanca conversa da B.

    E 404, nao `conversa_nao_encontrada`: `_canal_id_opcional_por_instance`
    (servico.py:1245) recusa antes de procurar conversa quando a instancia
    pertence a outra loja. O card descreve o outro caminho -- os dois davam no
    mesmo silencio, mas so este vale como asserção.
    """
    tel = "5511977710003"
    _semear_entrada(client, loja_b["instance"], tel, "ISO-B-1")

    r = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": loja_b["instance"], "provider_message_id": "ISO-B-1"},
        headers=loja_a["headers"],
    )

    assert r.status_code == 404


def test_credencial_nova_de_loja_alcanca_a_propria_loja_e_so_ela(client, db, loja_a, loja_b):
    """O conserto do vazamento multi-loja no Portal depende desta emissão.

    Até existir isto, um deploy com N lojas só tinha o token de UMA — e como o
    chatbot resolve a loja pelo token, toda tela mostrava a mesma loja.
    """
    tel = "5511977712001"
    _semear_entrada(client, loja_a["instance"], tel, "CRED-A-1")
    token = servico.criar_credencial_loja(db, loja_a["slug"])
    h = {"Authorization": f"Bearer {token}"}

    r = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": loja_a["instance"], "provider_message_id": "CRED-A-1"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pode_responder"] is True

    # e nao alcanca a loja B, mesmo mandando a instance dela
    _semear_entrada(client, loja_b["instance"], tel, "CRED-B-1")
    proibido = client.post(
        f"/v1/conversas/{tel}/pode-responder",
        json={"instance": loja_b["instance"], "provider_message_id": "CRED-B-1"},
        headers=h,
    )
    assert proibido.status_code == 404, proibido.text


def test_credencial_de_loja_inexistente_recusa():
    import pytest
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        with pytest.raises(ValueError):
            servico.criar_credencial_loja(s, "nao-existe")
    finally:
        s.close()
