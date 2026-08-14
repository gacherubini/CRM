from app.web.loja_shell import regras_elegiveis, central_disponivel


class _U:
    def __init__(self, papel):
        self.papel = papel
        self.id = "u1"


def _ents_vazio():
    from app.loja.types import EntitlementState

    return EntitlementState(
        loja_slug="loja-a",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
    )


def test_copiloto_off_nao_libera_regras():
    regras = regras_elegiveis(
        _ents_vazio(), _U("dono"),
        shell_enabled=True, copiloto_enabled=False, entitlements_enabled=False,
    )
    assert regras == frozenset()
    assert central_disponivel(
        _ents_vazio(), _U("dono"),
        shell_enabled=True, copiloto_enabled=False, entitlements_enabled=False,
    ) is False


def test_copiloto_on_devolve_regras_do_copiloto():
    regras = regras_elegiveis(
        _ents_vazio(), _U("dono"),
        shell_enabled=True, copiloto_enabled=True, entitlements_enabled=False,
    )
    assert "estoque_parado" in regras
    assert "simulacao_pronta" not in regras


def test_sem_shell_nao_ve_nada():
    regras = regras_elegiveis(
        _ents_vazio(), _U("dono"),
        shell_enabled=False, copiloto_enabled=True, entitlements_enabled=False,
    )
    assert regras == frozenset()
