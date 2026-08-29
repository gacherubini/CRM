"""Campos de retomada do onboarding Cloud (spec §5).

Canal antigo nao ganha valor nenhum: a migration e expand-only e sem backfill,
entao tudo nasce None e o Modo 1 nao muda.

A loja vem da fixture `loja_a` do conftest — `Loja.evolution_instance` e
obrigatoria e UNIQUE, entao construir Loja a mao no teste quebra na segunda.
"""
import uuid

from app.models_db import WhatsAppCanal


def _canal(loja_id, instance, **campos):
    """WhatsAppCanal minimo. `id` nao tem default e `e164_or_label` e NOT NULL."""
    return WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        e164_or_label="linha-cloud",
        evolution_instance=instance,
        **campos,
    )


def test_campos_de_onboarding_nascem_nulos(db, loja_a):
    canal = _canal(loja_a["loja_id"], "1227059273831581")
    db.add(canal)
    db.commit()
    db.refresh(canal)

    assert canal.business_id is None
    assert canal.onboarding_elo is None
    assert canal.onboarding_erro is None
    assert canal.token_cifrado is None
    assert canal.pin_cifrado is None
    # Contador do teto de 10/72h do elo 3: nasce 0, nunca None.
    assert canal.registro_tentativas == 0


def test_campos_de_onboarding_guardam_valor(db, loja_a):
    canal = _canal(
        loja_a["loja_id"],
        "1227059273831582",
        waba_id="waba-1",
        business_id="biz-1",
        onboarding_elo=3,
        onboarding_erro="numero ainda ativo no aplicativo",
    )
    db.add(canal)
    db.commit()
    db.refresh(canal)

    assert canal.business_id == "biz-1"
    assert canal.onboarding_elo == 3
    assert canal.onboarding_erro == "numero ainda ativo no aplicativo"
