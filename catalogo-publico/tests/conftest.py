import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.contracts import Pagination, Store, Vehicle, VehiclePage
from app.events import InterestStore
from app.main import app
from app.provider import InventoryNotFound, InventoryUnavailable


@pytest.fixture
def contract_data():
    path = Path(__file__).parent / "fixtures" / "estoque_publico.json"
    return json.loads(path.read_text(encoding="utf-8"))


class FakeProvider:
    def __init__(self, contract):
        self.store = Store.model_validate(contract["loja"])
        self.vehicle = Vehicle.model_validate(contract["veiculo"])
        self.fail = False
        self.missing = False
        self.last_filters = None

    def _check(self):
        if self.fail:
            raise InventoryUnavailable()
        if self.missing:
            raise InventoryNotFound()

    def get_store(self, slug):
        self._check()
        return self.store

    def list_vehicles(self, slug, **filters):
        self._check()
        self.last_filters = filters
        return VehiclePage(
            loja=self.store,
            veiculos=[self.vehicle],
            paginacao=Pagination(
                limit=filters["limit"], offset=filters["offset"], quantidade=1
            ),
        )

    def get_vehicle(self, slug, vehicle_id):
        self._check()
        if vehicle_id != self.vehicle.id:
            raise InventoryNotFound()
        return self.vehicle


@pytest.fixture
def fake_provider(contract_data):
    return FakeProvider(contract_data)


@pytest.fixture
def interest_store(tmp_path):
    return InterestStore(str(tmp_path / "catalog.db"))


@pytest.fixture
def client(fake_provider, interest_store):
    previous_provider = app.state.catalog_provider
    previous_store = app.state.interest_store
    app.state.catalog_provider = fake_provider
    app.state.interest_store = interest_store
    with TestClient(app) as test_client:
        yield test_client
    app.state.catalog_provider = previous_provider
    app.state.interest_store = previous_store
