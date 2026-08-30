"""A Loja desenha a tela lendo ESTE dicionario (spec §6).

Sem `waba_id` aqui a Loja nao distingue canal Cloud de canal Modo 1, e oferece
nele o botao que pede QR na Evolution. Sem `onboarding_elo` e `onboarding_erro`
a tela nao sabe dizer qual passo parou, e manda o lojista abrir o painel da
Meta — que e o que este projeto existe para acabar.
"""
import uuid

from app.channels import _canal_dict
from app.models_db import WhatsAppCanal

PROIBIDOS = {"token_cifrado", "pin_cifrado", "token", "pin", "access_token"}


def _canal(**campos):
    base = dict(
        id=str(uuid.uuid4()),
        loja_id="l1",
        e164_or_label="linha-cloud",
        evolution_instance="1227059273831620",
        estado="cloud_pendente",
    )
    base.update(campos)
    return WhatsAppCanal(**base)


def test_expoe_o_que_a_tela_da_loja_precisa():
    dados = _canal_dict(
        _canal(waba_id="waba-1", template_oferta="chama_vendedor",
               onboarding_elo=3, onboarding_erro="parou ao registrar")
    )

    assert dados["waba_id"] == "waba-1"
    assert dados["template_oferta"] == "chama_vendedor"
    assert dados["onboarding_elo"] == 3
    assert dados["onboarding_erro"] == "parou ao registrar"


def test_canal_do_modo_1_traz_os_campos_nulos():
    """Modo 1 nao tem nada disso, e `None` e a resposta certa — nao ausencia,
    que obrigaria a Loja a usar `.get` com default em toda leitura."""
    dados = _canal_dict(_canal(estado="conectado"))

    assert dados["waba_id"] is None
    assert dados["onboarding_elo"] is None


def test_continua_sem_devolver_segredo():
    dados = _canal_dict(
        _canal(waba_id="waba-1", token_cifrado="gAAAA-x", pin_cifrado="gAAAA-y")
    )

    assert PROIBIDOS.isdisjoint(dados.keys())
    assert "gAAAA" not in str(dados)
