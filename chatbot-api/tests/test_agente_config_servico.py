"""Rascunho → publicar → histórico (spec §3.2, §6)."""
from app import agente_config
from app.agente_prompt import CamposAgente


def _campos(nome="Motos do Léo", **over) -> CamposAgente:
    base = dict(nome_loja=nome, cidade="Piracicaba", uf="SP")
    base.update(over)
    return CamposAgente(**base)


def test_loja_sem_config_cai_no_padrao_revy(db, loja_a):
    """O bot nunca fica sem prompt."""
    prompt = agente_config.prompt_publicado(db, loja_a["loja_id"])
    assert "[REGRAS DO REVY" in prompt


def test_rascunho_nao_vai_ao_ar(db, loja_a):
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos(), autor="dono@x")
    assert "motos do léo" not in agente_config.prompt_publicado(db, loja_a["loja_id"]).lower()


def test_publicar_leva_o_rascunho_ao_ar(db, loja_a):
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos(), autor="dono@x")
    agente_config.publicar(db, loja_a["loja_id"], autor="dono@x")
    assert "motos do léo" in agente_config.prompt_publicado(db, loja_a["loja_id"]).lower()


def test_publicar_congela_o_prompt_da_versao(db, loja_a):
    from app.agente_prompt import NUCLEO_REVY

    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos(), autor="dono@x")
    versao = agente_config.publicar(db, loja_a["loja_id"], autor="dono@x")
    assert versao.prompt_gerado.rstrip().endswith(NUCLEO_REVY.rstrip())
    assert versao.publicado_em is not None


def test_restaurar_cria_versao_nova_e_nao_apaga_historico(db, loja_a):
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Um"), autor="a")
    primeira = agente_config.publicar(db, loja_a["loja_id"], autor="a")
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Dois"), autor="a")
    agente_config.publicar(db, loja_a["loja_id"], autor="a")

    agente_config.restaurar(db, loja_a["loja_id"], primeira.id, autor="a")
    agente_config.publicar(db, loja_a["loja_id"], autor="a")

    prompt = agente_config.prompt_publicado(db, loja_a["loja_id"]).lower()
    assert "loja um" in prompt
    assert len(agente_config.listar_versoes(db, loja_a["loja_id"])) >= 3


def test_config_de_uma_loja_nao_vaza_para_outra(db, loja_a, loja_b):
    """Isolamento por loja: o erro mais caro desta feature."""
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja A"), autor="a")
    agente_config.publicar(db, loja_a["loja_id"], autor="a")

    assert "loja a" not in agente_config.prompt_publicado(db, loja_b["loja_id"]).lower()
