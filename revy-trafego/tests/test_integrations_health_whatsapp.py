"""Task 7 do plano de status de integrações: check_whatsapp ao vivo.

Não usa `httpx` de verdade — `FakeWppPort` local garante que o teste nunca
bate na rede. Segue o padrão de `test_integrations_health_meta.py`.
"""

from __future__ import annotations

from app.control.integrations_health import HealthStatus, check_whatsapp


class FakeWppPort:
    def __init__(self, canais=None, indisponivel=False, erro=False):
        self.canais, self.indisponivel, self.erro = canais, indisponivel, erro

    def listar_canais(self, loja_slug):
        if self.erro:
            raise RuntimeError("timeout")
        return None if self.indisponivel else (self.canais or [])


class _Store:
    id = "loja-1"
    slug = "loja-1"


def test_whatsapp_missing_sem_config():
    assert check_whatsapp(_Store(), FakeWppPort(indisponivel=True)).status is HealthStatus.MISSING


def test_whatsapp_missing_sem_canais_operaveis():
    canais = [{"e164_or_label": "x", "estado": "inativo", "ativo": False}]
    assert check_whatsapp(_Store(), FakeWppPort(canais)).status is HealthStatus.MISSING


def test_whatsapp_connected_todos_conectados():
    canais = [
        {"e164_or_label": "a", "estado": "conectado", "ativo": True},
        {"e164_or_label": "b", "estado": "conectado", "ativo": True},
    ]
    assert check_whatsapp(_Store(), FakeWppPort(canais)).status is HealthStatus.CONNECTED


def test_whatsapp_error_se_algum_caido():
    canais = [
        {"e164_or_label": "a", "estado": "conectado", "ativo": True},
        {"e164_or_label": "b", "estado": "desconectado", "ativo": True},
    ]
    g = check_whatsapp(_Store(), FakeWppPort(canais))
    assert g.status is HealthStatus.ERROR
    assert any(i.status is HealthStatus.ERROR for i in g.itens)


def test_whatsapp_error_quando_chamada_falha():
    assert check_whatsapp(_Store(), FakeWppPort(erro=True)).status is HealthStatus.ERROR
