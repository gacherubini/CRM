"""Cifra dos segredos por loja (spec §8).

Fail-closed de proposito: sem chave configurada nao ha degradacao para texto
puro. Guardar token de cliente em claro por causa de um secret esquecido e
pior do que a rota falhar.
"""
import pytest

from app import segredo_canal


CHAVE = "LvALLRsc3ZykD4ZrrFrm25elgLGhYThKQ7Z2ili9KYw="


def test_cifrado_nao_e_o_texto(monkeypatch):
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", CHAVE)
    cifrado = segredo_canal.cifrar("EAAG-token-de-negocio")
    assert cifrado != "EAAG-token-de-negocio"
    assert "EAAG" not in cifrado


def test_ida_e_volta(monkeypatch):
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", CHAVE)
    assert segredo_canal.decifrar(segredo_canal.cifrar("123456")) == "123456"


def test_duas_cifras_do_mesmo_valor_diferem(monkeypatch):
    """Fernet poe nonce: valor igual nao vira cifra igual.

    Importa porque a coluna e indexavel por engano — cifra deterministica
    deixaria comparar tokens sem decifrar.
    """
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", CHAVE)
    assert segredo_canal.cifrar("igual") != segredo_canal.cifrar("igual")


def test_sem_chave_falha_fechado(monkeypatch):
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", "")
    with pytest.raises(segredo_canal.SegredoIndisponivel):
        segredo_canal.cifrar("qualquer")
