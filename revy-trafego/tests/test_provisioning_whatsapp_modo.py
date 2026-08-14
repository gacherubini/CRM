from app.control.provisioning import ProvisioningControl
from app.control.types import StoreRef
from app.db import SessionLocal
from app.models import Loja


def _loja(modo: int = 1) -> str:
    """Loja ativa direto no banco. O que importa aqui é o snapshot, não o CRUD."""
    with SessionLocal() as db:
        loja = Loja(
            slug=f"loja-modo-{modo}", nome="Loja Modo", status="ativa",
            versao=1, whatsapp_modo=modo,
        )
        db.add(loja)
        db.commit()
        return loja.id


def test_snapshot_traz_o_modo_como_aggregate():
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=_loja(1)))
    modos = [e for e in snapshot.operational if e.aggregate == "whatsapp_modo"]
    assert len(modos) == 1
    assert modos[0].state == "1"


def test_modo_2_aparece_no_snapshot():
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=_loja(2)))
    modo = next(e for e in snapshot.operational if e.aggregate == "whatsapp_modo")
    assert modo.state == "2"


def test_aggregate_loja_continua_existindo():
    """Regressão: o envelope novo não pode substituir o de status da loja."""
    snapshot = ProvisioningControl(SessionLocal).snapshot(StoreRef(id=_loja(1)))
    assert any(e.aggregate == "loja" for e in snapshot.operational)
