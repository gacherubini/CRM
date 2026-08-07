from datetime import datetime, timezone
from decimal import Decimal

from app.control.dashboard import DashboardControl
from app.control.types import Actor
from app.db import SessionLocal
from app.models import GestorRevy, Loja, VendaProjetada


def _admin_actor() -> Actor:
    with SessionLocal() as db:
        admin = db.query(GestorRevy).filter(GestorRevy.papel == "admin").one()
        return Actor(id=admin.id, email=admin.email, name=admin.nome, role=admin.papel)


def _venda(loja_id, slug, preco, quando):
    return VendaProjetada(
        id=f"v-{slug}-{preco}",
        loja_slug=slug,
        loja_id=loja_id,
        preco_venda=Decimal(preco),
        status="confirmada",
        criada_em=quando,
        confirmada_em=quando,
        atualizada_em=quando,
    )


class _FakeLeads:
    def __init__(self, mapa):
        self.mapa = mapa

    def count_for_store(self, slug):
        return self.mapa.get(slug)


def test_network_overview_conta_vendas_ticket_e_leads():
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        viva = Loja(nome="Viva", slug="viva", status="ativa")
        parada = Loja(nome="Parada", slug="parada", status="suspensa")
        db.add_all([viva, parada])
        db.flush()
        db.add(_venda(viva.id, "viva", "10000.00", agora))
        db.add(_venda(viva.id, "viva", "20000.00", agora))
        db.commit()
        viva_id = viva.id

    overview = DashboardControl(SessionLocal).network_overview(
        _admin_actor(), leads_port=_FakeLeads({"viva": 8})
    )

    assert overview.lojas_ativas == 1
    assert overview.lojas_total == 2
    assert overview.vendas_mes == 2
    assert overview.ticket_medio == Decimal("15000.00")
    assert overview.leads_rede == 8
    assert len(overview.por_loja) == 1  # só a loja ativa
    perf = overview.por_loja[0]
    assert perf.store_id == viva_id
    assert perf.vendas == 2
    assert perf.leads == 8
    assert round(perf.conversao, 3) == 0.25  # 2/8


def test_network_overview_respeita_janela_explicita():
    """Janela declarada filtra as vendas e volta nos campos de período."""
    from datetime import date

    with SessionLocal() as db:
        loja = Loja(nome="Viva", slug="viva", status="ativa")
        db.add(loja)
        db.flush()
        db.add(
            _venda(
                loja.id, "viva", "10000.00",
                datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
            )
        )
        db.add(
            _venda(
                loja.id, "viva", "20000.00",
                datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
            )
        )
        db.commit()

    overview = DashboardControl(SessionLocal).network_overview(
        _admin_actor(),
        leads_port=_FakeLeads({}),
        desde=date(2026, 1, 1),
        ate=date(2026, 1, 31),
    )

    assert overview.vendas_mes == 1  # só a venda de janeiro
    assert overview.ticket_medio == Decimal("10000.00")
    assert overview.periodo_inicio == date(2026, 1, 1)
    assert overview.periodo_fim == date(2026, 1, 31)


def test_network_overview_inclui_venda_do_ultimo_dia_da_janela():
    """Janela é inclusiva no fim: venda de hoje não pode cair fora."""
    from datetime import date

    with SessionLocal() as db:
        loja = Loja(nome="Viva", slug="viva", status="ativa")
        db.add(loja)
        db.flush()
        db.add(
            _venda(
                loja.id, "viva", "10000.00",
                datetime(2026, 2, 10, 23, 30, tzinfo=timezone.utc),
            )
        )
        db.commit()

    overview = DashboardControl(SessionLocal).network_overview(
        _admin_actor(),
        leads_port=_FakeLeads({}),
        desde=date(2026, 2, 1),
        ate=date(2026, 2, 10),
    )

    assert overview.vendas_mes == 1


def test_network_overview_degrada_leads_quando_none():
    with SessionLocal() as db:
        viva = Loja(nome="Viva", slug="viva", status="ativa")
        db.add(viva)
        db.commit()

    overview = DashboardControl(SessionLocal).network_overview(
        _admin_actor(), leads_port=_FakeLeads({})  # sem contagem → None
    )

    assert overview.leads_rede is None
    assert overview.por_loja[0].leads is None
    assert overview.por_loja[0].conversao is None


def test_network_overview_exclui_vendas_canceladas():
    """Vendas com status='cancelada' não devem contar, mesmo com confirmada_em no mês."""
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        loja = Loja(nome="Loja", slug="loja", status="ativa")
        db.add(loja)
        db.flush()
        # Venda confirmada (deve contar)
        db.add(
            VendaProjetada(
                id="v-confirm",
                loja_slug="loja",
                loja_id=loja.id,
                preco_venda=Decimal("10000.00"),
                status="confirmada",
                criada_em=agora,
                confirmada_em=agora,
                atualizada_em=agora,
            )
        )
        # Venda cancelada (não deve contar, mesmo com confirmada_em no mês)
        db.add(
            VendaProjetada(
                id="v-cancelada",
                loja_slug="loja",
                loja_id=loja.id,
                preco_venda=Decimal("20000.00"),
                status="cancelada",
                criada_em=agora,
                confirmada_em=agora,
                atualizada_em=agora,
            )
        )
        db.commit()

    overview = DashboardControl(SessionLocal).network_overview(
        _admin_actor(), leads_port=_FakeLeads({})
    )

    # Apenas a venda confirmada deve contar
    assert overview.vendas_mes == 1
    assert overview.ticket_medio == Decimal("10000.00")
    assert overview.por_loja[0].vendas == 1
