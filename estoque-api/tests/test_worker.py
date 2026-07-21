"""Agendamento da manutenção automática executada junto ao worker da outbox."""

from app.worker import executar_limpeza_se_devida


def test_limpeza_executa_no_inicio_e_respeita_intervalo():
    chamadas = []

    def limpar():
        chamadas.append(True)
        return {"removidos": 2, "modo": "aplicar"}

    proxima, resumo = executar_limpeza_se_devida(100, 0, 3600, limpar)
    assert proxima == 3700
    assert resumo == {"removidos": 2, "modo": "aplicar"}

    mesma_proxima, ignorado = executar_limpeza_se_devida(
        200, proxima, 3600, limpar
    )
    assert mesma_proxima == proxima
    assert ignorado is None
    assert len(chamadas) == 1


def test_limpeza_pode_ser_desativada():
    proxima, resumo = executar_limpeza_se_devida(
        100,
        0,
        0,
        lambda: (_ for _ in ()).throw(AssertionError("não deveria executar")),
    )
    assert proxima == 0
    assert resumo is None


def test_falha_na_limpeza_nao_mata_worker_e_aplica_backoff(caplog):
    def falhar():
        raise OSError("volume indisponível")

    proxima, resumo = executar_limpeza_se_devida(50, 0, 600, falhar)

    assert proxima == 650
    assert resumo is None
    assert "falha na limpeza periódica de mídias" in caplog.text
