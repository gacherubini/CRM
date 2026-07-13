from app.motor.base import Condicoes, Pessoa, Veiculo


def test_pessoa_aceita_cnh_opcional():
    p = Pessoa(cpf="52998224725", nascimento="1990-01-01", cnh=True)
    assert p.cnh is True
    assert Pessoa(cpf="52998224725", nascimento="1990-01-01").cnh is None


def test_veiculo_aceita_placa_uf_finalidade_e_valor_opcional():
    v = Veiculo(placa="ABC1D23", uf_licenciamento="SP", finalidade="comum")
    assert v.placa == "ABC1D23" and v.uf_licenciamento == "SP" and v.finalidade == "comum"
    assert v.valor is None  # valor vem do portal


def test_condicoes_multiprazo_e_retrocompat():
    c = Condicoes(entrada=1000, prazos_meses=[24, 36, 48])
    assert c.prazos_meses == [24, 36, 48]
    assert c.prazo_meses == 24  # primeiro da lista
    # contrato antigo: prazo_meses único é aceito e vira lista de 1
    c2 = Condicoes(entrada=0, prazo_meses=60)
    assert c2.prazos_meses == [60]
