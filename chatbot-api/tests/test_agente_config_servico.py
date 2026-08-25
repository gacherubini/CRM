"""Rascunho → publicar → histórico (spec §3.2, §6)."""
import pytest

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


def test_salvar_rascunho_duas_vezes_reaproveita_a_mesma_linha(db, loja_a):
    """Escritor e leitor do rascunho tinham ordenação diferente: com duas
    linhas 'rascunho' da mesma loja, o PUT escrevia numa e a resposta do
    próprio PUT devolvia outra. Duas chamadas seguidas têm que devolver o
    MESMO id, e o que `obter_rascunho` lê tem que ser o que acabou de ser
    escrito."""
    primeira = agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Um"), autor="a")
    segunda = agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Dois"), autor="a")

    assert segunda.id == primeira.id
    rascunho = agente_config.obter_rascunho(db, loja_a["loja_id"])
    assert rascunho.id == primeira.id
    assert rascunho.campos["nome_loja"] == "Loja Dois"


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


def test_restaurar_traz_a_versao_antiga_de_volta_sem_apagar_historico(db, loja_a):
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


def test_restaurar_versao_de_outra_loja_e_bloqueado(db, loja_a, loja_b):
    """Task 5 vai expor `restaurar` a input externo: o loja_id não pode ser um crachá aceito."""
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja A"), autor="a")
    versao_a = agente_config.publicar(db, loja_a["loja_id"], autor="a")

    rascunho_b_antes = agente_config.obter_rascunho(db, loja_b["loja_id"])

    with pytest.raises(LookupError):
        agente_config.restaurar(db, loja_b["loja_id"], versao_a.id, autor="b")

    rascunho_b_depois = agente_config.obter_rascunho(db, loja_b["loja_id"])
    assert rascunho_b_depois.id == rascunho_b_antes.id
    assert rascunho_b_depois.campos == rascunho_b_antes.campos


def test_publicar_arquiva_a_anterior_e_move_o_ponteiro(db, loja_a):
    """`prompt_publicado` segue o ponteiro e nunca lê `estado` — a máquina de
    estados em si precisa de teste próprio, senão duas `publicada` ao mesmo
    tempo passariam batido."""
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Um"), autor="a")
    primeira = agente_config.publicar(db, loja_a["loja_id"], autor="a")

    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Dois"), autor="a")
    segunda = agente_config.publicar(db, loja_a["loja_id"], autor="a")

    versoes = agente_config.listar_versoes(db, loja_a["loja_id"])
    publicadas = [v for v in versoes if v.estado == "publicada"]
    assert [v.id for v in publicadas] == [segunda.id]

    primeira_recarregada = next(v for v in versoes if v.id == primeira.id)
    assert primeira_recarregada.estado == "arquivada"

    cfg = db.get(agente_config.models_db.AgenteConfig, loja_a["loja_id"])
    assert cfg.versao_publicada_id == segunda.id


def test_restaurar_sobrescreve_o_rascunho_em_andamento(db, loja_a):
    """A docstring de `restaurar` documenta isto: ela mexe no rascunho atual,
    não cria versão nova — se houver rascunho não publicado, ele é perdido."""
    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja Antiga"), autor="a")
    antiga = agente_config.publicar(db, loja_a["loja_id"], autor="a")

    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Rascunho Em Andamento"), autor="a")

    restaurado = agente_config.restaurar(db, loja_a["loja_id"], antiga.id, autor="a")

    assert restaurado.estado == "rascunho"
    assert restaurado.campos["nome_loja"] == "Loja Antiga"
    rascunho_atual = agente_config.obter_rascunho(db, loja_a["loja_id"])
    assert rascunho_atual.id == restaurado.id
    assert rascunho_atual.campos["nome_loja"] == "Loja Antiga"


def test_campos_publicados_cai_no_padrao_e_depois_reflete_a_publicacao(db, loja_a):
    from app.agente_prompt import CAMPOS_PADRAO_REVY

    assert agente_config.campos_publicados(db, loja_a["loja_id"]) == CAMPOS_PADRAO_REVY

    agente_config.salvar_rascunho(db, loja_a["loja_id"], _campos("Loja A"), autor="a")
    agente_config.publicar(db, loja_a["loja_id"], autor="a")

    campos = agente_config.campos_publicados(db, loja_a["loja_id"])
    assert campos.nome_loja == "Loja A"
