"""Tabelas da config do agente (spec §3.2)."""
import uuid

from app import models_db


def test_versao_guarda_campos_e_prompt_congelado(db, loja_a):
    """prompt_gerado junto com campos NÃO é redundância: audita o que o bot recebeu."""
    versao = models_db.AgenteConfigVersao(
        id=str(uuid.uuid4()),
        loja_id=loja_a["loja_id"],
        estado="rascunho",
        campos={"nome_loja": "Motos do Léo"},
        prompt_gerado="[IDENTIDADE]\nvocê atende...",
    )
    db.add(versao)
    db.commit()

    lido = db.get(models_db.AgenteConfigVersao, versao.id)
    assert lido.campos["nome_loja"] == "Motos do Léo"
    assert lido.prompt_gerado.startswith("[IDENTIDADE]")
    assert lido.publicado_em is None


def test_config_aponta_para_a_versao_publicada(db, loja_a):
    versao = models_db.AgenteConfigVersao(
        id=str(uuid.uuid4()),
        loja_id=loja_a["loja_id"],
        estado="publicada",
        campos={},
        prompt_gerado="x",
    )
    db.add(versao)
    db.flush()
    db.add(
        models_db.AgenteConfig(
            loja_id=loja_a["loja_id"], versao_publicada_id=versao.id
        )
    )
    db.commit()

    cfg = db.get(models_db.AgenteConfig, loja_a["loja_id"])
    assert cfg.versao_publicada_id == versao.id
