from decimal import Decimal
from pathlib import Path

import pytest

from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import DriverContext, IntervencaoNecessaria, resolver_drivers
from app.motor.santander import (
    PROVEDOR,
    parse_moeda_br,
    parse_parcelas_texto,
    parse_valor_liberado,
    uf_para_portal,
    SantanderDriver,
)

FIXTURE = Path(__file__).parent / "fixtures" / "santander" / "simulacao_parcelas.html"


def _sol(**kwargs):
    base = dict(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-01-01", cnh=True),
        veiculo=Veiculo(
            placa="FUV7G58",
            uf_licenciamento="SP",
            finalidade="comum",
            valor=21900,
            categoria="moto",
        ),
        condicoes=Condicoes(entrada=1123.20, prazos_meses=[12, 24, 36, 48]),
        provedores=[PROVEDOR],
    )
    base.update(kwargs)
    return SolicitacaoSimulacao(**base)


def test_parse_moeda_br():
    assert parse_moeda_br("1.097,45") == Decimal("1097.45")
    assert parse_moeda_br("R$ 946,28") == Decimal("946.28")


def test_parse_parcelas_da_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    pares = parse_parcelas_texto(html)
    assert pares == [
        (12, Decimal("2539.64")),
        (24, Decimal("1452.60")),
        (36, Decimal("1097.45")),
        (48, Decimal("946.28")),
    ]
    assert parse_valor_liberado(html) == Decimal("20776.80")


def test_uf_para_portal():
    assert uf_para_portal("SP") == "SAO PAULO"
    assert uf_para_portal("rj") == "RIO DE JANEIRO"


def test_driver_fixture_html_devolve_multi_prazo():
    html = FIXTURE.read_text(encoding="utf-8")
    d = SantanderDriver(html_simulacao=html)
    out = d(_sol())
    assert len(out) == 4
    assert all(r.provedor == PROVEDOR and r.status == "concluida" for r in out)
    por_prazo = {r.prazo_meses: r.valor_parcela for r in out}
    assert por_prazo[48] == Decimal("946.28")
    assert por_prazo[12] == Decimal("2539.64")
    assert out[0].valor_financiado == Decimal("20776.80")


def test_driver_filtra_prazos_pedidos():
    html = FIXTURE.read_text(encoding="utf-8")
    d = SantanderDriver(html_simulacao=html)
    out = d(_sol(condicoes=Condicoes(entrada=1000, prazos_meses=[36, 48])))
    assert sorted(r.prazo_meses for r in out) == [36, 48]


def test_driver_sem_parcelas_intervencao():
    d = SantanderDriver(html_simulacao="<html><body>sem cards</body></html>")
    with pytest.raises(IntervencaoNecessaria) as ei:
        d(_sol())
    assert ei.value.codigo == "parcelas_nao_encontradas"


def test_gating_santander_sem_credencial_nao_resolve(db):
    from app.motor import drivers as D

    D._registrar_drivers_reais()
    assert PROVEDOR in D.REAL_DRIVERS
    pares = resolver_drivers(
        [PROVEDOR], db=db, cliente_id="10000000-0000-0000-0000-000000000001"
    )
    assert pares == []


def test_gating_santander_com_credencial_resolve(db):
    from app import cripto
    from app.models_db import CredencialProvedorORM
    from app.motor import drivers as D
    from conftest import TEST_CLIENT_ID
    import uuid

    db.add(
        CredencialProvedorORM(
            id=str(uuid.uuid4()),
            cliente_id=TEST_CLIENT_ID,
            provedor=PROVEDOR,
            usuario="00000000191",
            senha_cifrada=cripto.cifrar("senha-teste"),
            habilitado=True,
        )
    )
    db.commit()
    pares = resolver_drivers([PROVEDOR], db=db, cliente_id=TEST_CLIENT_ID)
    assert len(pares) == 1
    nome, driver = pares[0]
    assert nome == PROVEDOR
    # driver real com fixture não precisa browser
    html = FIXTURE.read_text(encoding="utf-8")
    if isinstance(driver, type):
        d = driver(html_simulacao=html)
    else:
        # instância SantanderDriver
        d = driver
        if hasattr(d, "html_simulacao"):
            d.html_simulacao = html
    out = d(_sol(), DriverContext(db=db, cliente_id=TEST_CLIENT_ID))
    assert len(out) >= 1
