import hashlib
import hmac
import json

from app.meta_webhook import assinatura_valida

SEGREDO = "app-secret-de-teste"
CORPO = b'{"entry":[{"id":"1","changes":[]}],"object":"whatsapp_business_account"}'


def _assinar(corpo: bytes, segredo: str = SEGREDO) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


def test_assinatura_correta_passa():
    assert assinatura_valida(CORPO, _assinar(CORPO), app_secret=SEGREDO) is True


def test_corpo_alterado_reprova():
    assert assinatura_valida(CORPO + b" ", _assinar(CORPO), app_secret=SEGREDO) is False


def test_segredo_errado_reprova():
    assert assinatura_valida(CORPO, _assinar(CORPO, "outro"), app_secret=SEGREDO) is False


def test_header_ausente_ou_torto_reprova():
    assert assinatura_valida(CORPO, "", app_secret=SEGREDO) is False
    assert assinatura_valida(CORPO, "abc123", app_secret=SEGREDO) is False
    assert assinatura_valida(CORPO, "sha1=abc", app_secret=SEGREDO) is False


def test_reserializar_o_json_quebra_a_assinatura():
    """Documenta a armadilha: reserializar muda os bytes e invalida o HMAC."""
    reserializado = json.dumps(json.loads(CORPO)).encode()
    assert reserializado != CORPO
    assert assinatura_valida(reserializado, _assinar(CORPO), app_secret=SEGREDO) is False


def test_sem_app_secret_configurado_reprova():
    """Fail-closed: sem segredo, não valida nada — não libera tudo."""
    assert assinatura_valida(CORPO, _assinar(CORPO), app_secret="") is False
