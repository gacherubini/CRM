"""Modelos do contrato público v1 (Plano #1A / Plano #0)."""
from typing import List, Optional

from pydantic import BaseModel


class Pessoa(BaseModel):
    cpf: str
    nascimento: str
    renda: Optional[float] = None


class Veiculo(BaseModel):
    categoria: str = "moto"
    valor: float


class Condicoes(BaseModel):
    entrada: float = 0
    prazo_meses: int


class SolicitacaoSimulacao(BaseModel):
    referencia_externa: Optional[str] = None
    pessoa: Pessoa
    veiculo: Veiculo
    condicoes: Condicoes
    provedores: List[str] = ["mock"]


class ResultadoProvedor(BaseModel):
    provedor: str
    status: str = "concluida"
    valor_parcela: float
    taxa_am: float
    prazo_meses: int
    valor_financiado: float
    codigo_erro: Optional[str] = None


class Simulacao(BaseModel):
    id: str
    status: str
    criada_em: str
    resultados: List[ResultadoProvedor] = []
