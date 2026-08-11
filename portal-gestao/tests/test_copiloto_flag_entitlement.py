"""Flag global (kill-switch) + entitlement por loja do Copiloto."""
from app.config import revy_loja_copiloto_enabled
from app.loja.entitlements import fail_open, from_allows_processing
from app.loja.types import Module


def test_flag_copiloto_default_off(monkeypatch):
    monkeypatch.delenv("REVY_LOJA_COPILOTO_ENABLED", raising=False)
    assert revy_loja_copiloto_enabled() is False
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    assert revy_loja_copiloto_enabled() is True


def test_fail_open_libera_copiloto_para_quem_tem_cargo():
    """Entitlements off = comportamento legado; a flag de env decide sozinha."""
    assert fail_open("loja-teste", {"dono"}).copiloto_enabled is True
    assert fail_open("loja-teste", set()).copiloto_enabled is False


def test_projecao_gate_copiloto_por_modulo():
    """Com entitlements on, o Copiloto é módulo contratável e pode faltar."""
    consultados = []

    def allows(slug, module=None):
        consultados.append(module)
        return module != Module.COPILOTO.value

    estado = from_allows_processing("loja-teste", allows)
    assert estado.copiloto_enabled is False
    assert estado.vendas_enabled is True
    assert Module.COPILOTO.value in consultados


def test_module_enabled_reconhece_copiloto():
    """Enum novo sem entrada em module_enabled = módulo que nunca autoriza."""
    from app.loja.permissions import module_enabled
    from app.loja.types import EntitlementState

    ligado = fail_open("loja-teste", {"dono"})
    assert module_enabled(ligado, Module.COPILOTO) is True

    desligado = EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="projecao",
        copiloto_enabled=False,
    )
    assert module_enabled(desligado, Module.COPILOTO) is False

    inativa = EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=False,
        vendas_enabled=False,
        estoque_enabled=False,
        source="projecao",
        copiloto_enabled=True,
    )
    assert module_enabled(inativa, Module.COPILOTO) is False
