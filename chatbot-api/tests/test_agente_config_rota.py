"""GET /v1/agente/config — multi-loja de verdade (spec §3.3)."""
from app import agente_config, servico
from app.agente_prompt import NUCLEO_REVY, CamposAgente


def _publicar(db, loja_id, nome):
    agente_config.salvar_rascunho(
        db, loja_id, CamposAgente(nome_loja=nome, cidade="Piracicaba", uf="SP"), autor="t"
    )
    agente_config.publicar(db, loja_id, autor="t")


def test_credencial_de_loja_recebe_o_proprio_prompt(client, db, loja_a):
    _publicar(db, loja_a["loja_id"], "Loja A")
    r = client.get("/v1/agente/config", headers=loja_a["headers"])
    assert r.status_code == 200
    assert "loja a" in r.json()["prompt"].lower()


def test_prompt_da_rota_termina_no_nucleo(client, db, loja_a):
    """Fronteira que o n8n de fato lê: um rodapé colado depois do núcleo,
    dentro da rota, tem que derrubar este teste."""
    _publicar(db, loja_a["loja_id"], "Loja A")
    r = client.get("/v1/agente/config", headers=loja_a["headers"])
    assert r.json()["prompt"].rstrip().endswith(NUCLEO_REVY.rstrip())


def test_integracao_sem_instance_da_400_e_nao_423(client, db):
    """O gate com loja_id=None responderia 423 e engoliria o erro de verdade."""
    token = servico.criar_credencial_integracao(db)
    db.commit()
    r = client.get("/v1/agente/config", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400
    assert "instance" in r.json()["detail"]


def test_integracao_com_instance_recebe_o_prompt_daquela_loja(client, db, loja_a, loja_b):
    _publicar(db, loja_a["loja_id"], "Loja A")
    _publicar(db, loja_b["loja_id"], "Loja B")
    token = servico.criar_credencial_integracao(db)
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    r = client.get(f"/v1/agente/config?instance={loja_b['instance']}", headers=headers)
    assert r.status_code == 200
    corpo = r.json()["prompt"].lower()
    assert "loja b" in corpo
    assert "loja a" not in corpo


def test_loja_suspensa_da_423_para_o_fluxo_parar(client, db, loja_sem_projecao):
    """Fallback do n8n é só para falha técnica: 423 tem que parar o bot."""
    r = client.get("/v1/agente/config", headers=loja_sem_projecao["headers"])
    assert r.status_code == 423


def test_teto_de_tokens_acompanha_o_tamanho_da_resposta(client, db, loja_a):
    agente_config.salvar_rascunho(
        db,
        loja_a["loja_id"],
        CamposAgente(nome_loja="X", cidade="Y", uf="SP", tamanho_resposta="longo"),
        autor="t",
    )
    agente_config.publicar(db, loja_a["loja_id"], autor="t")
    r = client.get("/v1/agente/config", headers=loja_a["headers"])
    assert r.json()["max_output_tokens"] == 700


def test_loja_sem_config_recebe_o_padrao_revy(client, loja_a):
    r = client.get("/v1/agente/config", headers=loja_a["headers"])
    assert r.status_code == 200
    assert "[REGRAS DO REVY" in r.json()["prompt"]
