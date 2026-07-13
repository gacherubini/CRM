from app.cripto import cifrar, decifrar, gerar_chave


def test_cifrar_decifrar_roundtrip():
    token = cifrar("segredo-capi-123")
    assert token != "segredo-capi-123"
    assert decifrar(token) == "segredo-capi-123"


def test_gerar_chave_fernet():
    chave = gerar_chave()
    assert len(chave) >= 32
