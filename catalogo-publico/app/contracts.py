from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Store(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str
    nome: str
    whatsapp: Optional[str] = None


class Vehicle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    tipo: str
    marca: str
    modelo: str
    versao: Optional[str] = None
    ano_modelo: int
    cor: Optional[str] = None
    km: int = 0
    preco: float = Field(ge=0)
    foto_url: Optional[str] = None
    fotos: list[str] = Field(default_factory=list)

    @property
    def imagens(self) -> list[str]:
        imagens = [url for url in self.fotos if url]
        if not imagens and self.foto_url:
            imagens.append(self.foto_url)
        return imagens


class Pagination(BaseModel):
    model_config = ConfigDict(extra="ignore")

    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    quantidade: int = Field(ge=0)
    # Total filtrado (contrato público estoque ≥ 2026-08). Default 0 em mocks legados.
    total: int = Field(default=0, ge=0)


class VehiclePage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    loja: Store
    veiculos: list[Vehicle]
    paginacao: Pagination
