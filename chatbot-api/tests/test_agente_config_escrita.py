"""Rotas de escrita da config (spec §6). Quem consome é a Revy Loja."""

CAMPOS = {"nome_loja": "Motos do Léo", "cidade": "Piracicaba", "uf": "SP"}


def test_put_rascunho_devolve_o_prompt_gerado(client, loja_a):
    r = client.put("/v1/agente/rascunho", json=CAMPOS, headers=loja_a["headers"])
    assert r.status_code == 200
    assert "motos do léo" in r.json()["prompt"].lower()


def test_rascunho_salvo_nao_muda_o_publicado(client, loja_a):
    antes = client.get("/v1/agente/config", headers=loja_a["headers"]).json()["prompt"]
    client.put("/v1/agente/rascunho", json=CAMPOS, headers=loja_a["headers"])
    depois = client.get("/v1/agente/config", headers=loja_a["headers"]).json()["prompt"]
    assert depois == antes
    assert "motos do léo" not in depois.lower()


def test_publicar_leva_ao_ar(client, loja_a):
    client.put("/v1/agente/rascunho", json=CAMPOS, headers=loja_a["headers"])
    assert client.post("/v1/agente/publicar", headers=loja_a["headers"]).status_code == 200
    publicado = client.get("/v1/agente/config", headers=loja_a["headers"]).json()["prompt"]
    assert "motos do léo" in publicado.lower()


def test_conflito_avisa_mas_deixa_salvar(client, loja_a):
    """Avisa, não bloqueia (decisão do dono, spec §4.5)."""
    corpo = dict(CAMPOS, instrucoes="pode dizer o valor da parcela pro cliente")
    r = client.put("/v1/agente/rascunho", json=corpo, headers=loja_a["headers"])
    assert r.status_code == 200
    assert "parcela" in r.json()["conflitos"]


def test_instrucao_acima_do_teto_e_recusada(client, loja_a):
    corpo = dict(CAMPOS, instrucoes="a" * 1001)
    assert client.put("/v1/agente/rascunho", json=corpo, headers=loja_a["headers"]).status_code == 422


def test_restaurar_traz_a_versao_antiga_para_o_rascunho(client, loja_a):
    client.put("/v1/agente/rascunho", json=dict(CAMPOS, nome_loja="Loja Um"), headers=loja_a["headers"])
    client.post("/v1/agente/publicar", headers=loja_a["headers"])
    primeira = client.get("/v1/agente/versoes", headers=loja_a["headers"]).json()[0]["id"]

    client.put("/v1/agente/rascunho", json=dict(CAMPOS, nome_loja="Loja Dois"), headers=loja_a["headers"])
    client.post("/v1/agente/publicar", headers=loja_a["headers"])

    r = client.post(f"/v1/agente/versoes/{primeira}/restaurar", headers=loja_a["headers"])
    assert r.status_code == 200
    assert "loja um" in r.json()["prompt"].lower()


def test_uma_loja_nao_restaura_versao_da_outra(client, loja_a, loja_b):
    client.put("/v1/agente/rascunho", json=CAMPOS, headers=loja_a["headers"])
    client.post("/v1/agente/publicar", headers=loja_a["headers"])
    versao_a = client.get("/v1/agente/versoes", headers=loja_a["headers"]).json()[0]["id"]

    r = client.post(f"/v1/agente/versoes/{versao_a}/restaurar", headers=loja_b["headers"])
    assert r.status_code == 404
