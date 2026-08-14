from app.meta_webhook import parse_inbound


def _envelope(value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": value}]}],
    }


def test_texto_simples():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111", "display_phone_number": "5511..."},
        "messages": [{
            "from": "5511988887777", "id": "wamid.A", "type": "text",
            "text": {"body": "quero uma biz"},
        }],
    }))
    assert len(eventos) == 1
    e = eventos[0]
    assert (e.tipo, e.phone_number_id, e.remetente, e.wamid) == (
        "texto", "111", "5511988887777", "wamid.A"
    )
    assert e.texto == "quero uma biz"


def test_audio_traz_media_id_e_nao_binario():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{
            "from": "5511988887777", "id": "wamid.B", "type": "audio",
            "audio": {"id": "media-9", "mime_type": "audio/ogg; codecs=opus"},
        }],
    }))
    assert eventos[0].tipo == "audio"
    assert eventos[0].media_id == "media-9"
    assert eventos[0].mime == "audio/ogg"


def test_clique_de_template_vira_clique_com_oferta():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{
            "from": "5511999990000", "id": "wamid.C", "type": "button",
            "button": {"payload": "pego:of-7", "text": "Peguei"},
        }],
    }))
    assert eventos[0].tipo == "clique"
    assert eventos[0].oferta_id == "of-7"


def test_clique_de_interativa_vira_clique_com_oferta():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{
            "from": "5511999990000", "id": "wamid.D", "type": "interactive",
            "interactive": {"type": "button_reply",
                            "button_reply": {"id": "pego:of-8", "title": "Peguei"}},
        }],
    }))
    assert eventos[0].tipo == "clique"
    assert eventos[0].oferta_id == "of-8"


def test_referral_de_anuncio_e_extraido():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{
            "from": "5511988887777", "id": "wamid.E", "type": "text",
            "text": {"body": "vi o anuncio"},
            "referral": {"source_id": "ad-123", "source_type": "ad"},
        }],
    }))
    assert eventos[0].referral_ad_id == "ad-123"


def test_status_nao_vira_mensagem():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "statuses": [{"id": "wamid.F", "status": "failed", "recipient_id": "5511988887777"}],
    }))
    assert len(eventos) == 1
    assert eventos[0].tipo == "status"
    assert eventos[0].status == "failed"


def test_varios_eventos_no_mesmo_post():
    eventos = parse_inbound({
        "object": "whatsapp_business_account",
        "entry": [{"id": "w", "changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "111"},
            "messages": [
                {"from": "1", "id": "wamid.G", "type": "text", "text": {"body": "a"}},
                {"from": "2", "id": "wamid.H", "type": "text", "text": {"body": "b"}},
            ],
        }}]}],
    })
    assert [e.wamid for e in eventos] == ["wamid.G", "wamid.H"]


def test_tipo_desconhecido_vira_ignorado_sem_estourar():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{"from": "1", "id": "wamid.I", "type": "sticker", "sticker": {}}],
    }))
    assert eventos[0].tipo == "ignorado"
