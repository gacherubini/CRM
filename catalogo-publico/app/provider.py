from typing import Any, Optional

import httpx
from pydantic import ValidationError

from app.contracts import Store, Vehicle, VehiclePage


class InventoryNotFound(Exception):
    pass


class InventoryUnavailable(Exception):
    pass


class HttpInventoryProvider:
    """Cliente do contrato público da Estoque API; nunca acessa seu banco."""

    def __init__(
        self,
        base_url: str,
        token: str = "",
        timeout: float = 5,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.transport = transport

    def _get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise InventoryUnavailable("estoque temporariamente indisponível") from exc

        if response.status_code == 404:
            raise InventoryNotFound("recurso não encontrado")
        if response.status_code >= 400:
            raise InventoryUnavailable("estoque temporariamente indisponível")
        try:
            return response.json()
        except ValueError as exc:
            raise InventoryUnavailable("resposta inválida do estoque") from exc

    def get_store(self, slug: str) -> Store:
        try:
            return Store.model_validate(self._get(f"/public/v1/lojas/{slug}"))
        except ValidationError as exc:
            raise InventoryUnavailable("contrato de loja inválido") from exc

    def list_vehicles(
        self,
        slug: str,
        *,
        tipo: Optional[str] = None,
        marca: Optional[str] = None,
        preco_min: Optional[float] = None,
        preco_max: Optional[float] = None,
        limit: int = 12,
        offset: int = 0,
    ) -> VehiclePage:
        params = {
            key: value
            for key, value in {
                "tipo": tipo,
                "marca": marca,
                "preco_min": preco_min,
                "preco_max": preco_max,
                "limit": limit,
                "offset": offset,
            }.items()
            if value not in (None, "")
        }
        try:
            return VehiclePage.model_validate(
                self._get(f"/public/v1/lojas/{slug}/veiculos", params=params)
            )
        except ValidationError as exc:
            raise InventoryUnavailable("contrato da vitrine inválido") from exc

    def get_vehicle(self, slug: str, vehicle_id: str) -> Vehicle:
        try:
            return Vehicle.model_validate(
                self._get(f"/public/v1/lojas/{slug}/veiculos/{vehicle_id}")
            )
        except ValidationError as exc:
            raise InventoryUnavailable("contrato de veículo inválido") from exc
