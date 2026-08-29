"""GET /v1/whatsapp/canais nao pode devolver segredo (spec §8).

A tela de numeros da Loja lista canais. Uma chave a mais no serializer
(`app/channels.py:27`) mandaria o token de WhatsApp do cliente para o
navegador.
"""
import uuid

from app.models_db import WhatsAppCanal

PROIBIDOS = {"token_cifrado", "pin_cifrado", "token", "pin", "access_token"}


def test_listagem_nao_traz_campo_de_segredo(client, db, loja_a):
    db.add(
        WhatsAppCanal(
            id=str(uuid.uuid4()),
            loja_id=loja_a["loja_id"],
            e164_or_label="linha-cloud",
            evolution_instance="1227059273831583",
            waba_id="waba-1",
            token_cifrado="gAAAAA-cifrado",
            pin_cifrado="gAAAAA-cifrado",
        )
    )
    db.commit()

    resposta = client.get("/v1/whatsapp/canais", headers=loja_a["headers"])
    assert resposta.status_code == 200

    canais = resposta.json()["canais"]
    assert canais, "a loja precisa ter canal, senao o teste passa sem olhar nada"
    for canal in canais:
        assert PROIBIDOS.isdisjoint(canal.keys()), canal.keys()
    assert "gAAAAA-cifrado" not in resposta.text
