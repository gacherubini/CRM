"""Modelos do contrato público v1 (Plano #1A / Task 12 campos reais)."""
from typing import List, Literal, Optional

from pydantic import BaseModel, model_validator


class Pessoa(BaseModel):
    cpf: str
    nascimento: str
    renda: Optional[float] = None
    cnh: Optional[bool] = None
    ddd: Optional[str] = None
    celular: Optional[str] = None
    codigo_natureza_ocupacao: Optional[str] = None


class Veiculo(BaseModel):
    categoria: str = "moto"
    # Opcional quando o portal do banco resolve o valor pela placa.
    valor: Optional[float] = None
    placa: Optional[str] = None
    uf_licenciamento: Optional[str] = None
    finalidade: Optional[Literal["comum", "pcd"]] = None
    # Código retornado pelo catálogo do provedor (ex.: versão do veículo PAN).
    codigo_provedor: Optional[str] = None
    ano_modelo: Optional[int] = None
    zero_km: Optional[bool] = None


class Condicoes(BaseModel):
    entrada: float = 0
    # Contrato antigo: um prazo. Novo: lista multi-prazo (Santander real).
    prazo_meses: Optional[int] = None
    prazos_meses: List[int] = []

    @model_validator(mode="after")
    def _normaliza_prazos(self) -> "Condicoes":
        if not self.prazos_meses and self.prazo_meses is not None:
            object.__setattr__(self, "prazos_meses", [self.prazo_meses])
        if self.prazo_meses is None and self.prazos_meses:
            object.__setattr__(self, "prazo_meses", self.prazos_meses[0])
        return self


class SolicitacaoSimulacao(BaseModel):
    referencia_externa: Optional[str] = None
    pessoa: Pessoa
    veiculo: Veiculo
    condicoes: Condicoes
    provedores: List[str] = ["mock"]


class ResultadoProvedor(BaseModel):
    provedor: str
    status: str = "concluida"
    # Nulos quando o provedor falhou/rejeitou (sem oferta).
    valor_parcela: Optional[float] = None
    taxa_am: Optional[float] = None
    prazo_meses: Optional[int] = None
    valor_financiado: Optional[float] = None
    # Entrada necessaria devolvida pelo banco (Santander calcula e retorna).
    entrada: Optional[float] = None
    codigo_erro: Optional[str] = None


class TarefaProvedor(BaseModel):
    """Estado de uma tarefa-filha (um banco) no fan-out."""

    id: str
    provedor: str
    tipo_driver: str = "mock"
    status: str = "recebida"
    tentativa: int = 0
    codigo_erro: Optional[str] = None
    criada_em: Optional[str] = None
    iniciada_em: Optional[str] = None
    finalizada_em: Optional[str] = None


class Simulacao(BaseModel):
    id: str
    status: str
    criada_em: str
    provedores: List[str] = []
    tarefas: List[TarefaProvedor] = []
    resultados: List[ResultadoProvedor] = []
