from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import DriverContext, ResultadoDriver
from app.motor.playwright_base import PlaywrightBankDriver


class _FakeDriver(PlaywrightBankDriver):
    provedor = "fake_banco"

    def simular(self, sol, ctx=None):
        prazos = sol.condicoes.prazos_meses or [sol.condicoes.prazo_meses or 0]
        return [
            ResultadoDriver(
                self.provedor,
                "concluida",
                valor_parcela=100 + p,
                taxa_am=1.5,
                prazo_meses=p,
                valor_financiado=9000,
            )
            for p in prazos
        ]


def test_playwright_base_callable_retorna_lista():
    d = _FakeDriver()
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-01-01"),
        veiculo=Veiculo(placa="ABC1D23", finalidade="comum"),
        condicoes=Condicoes(entrada=0, prazos_meses=[24, 48]),
    )
    out = d(sol, DriverContext())
    assert isinstance(out, list) and len(out) == 2
    assert out[0].provedor == "fake_banco"
    assert d.real is True


def test_falha_campo_gera_intervencao():
    d = _FakeDriver()
    exc = d._falha_campo("CPF")
    assert exc.codigo == "campo_nao_encontrado"
    assert "CPF" in str(exc)
