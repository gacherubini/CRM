"""Modelos canônicos do Motor (Plano #1A, Task 4).

`simulacoes` (job), `simulacao_resultados` (um por provedor/banco) e `idempotencia`.
Timestamps com timezone; UUID externo em `simulacoes`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class ClienteApiORM(Base):
    __tablename__ = "clientes_api"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class CredencialApiORM(Base):
    __tablename__ = "credenciais_api"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cliente_id: Mapped[str] = mapped_column(
        ForeignKey("clientes_api.id"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class CredencialProvedorORM(Base):
    """Credencial de portal bancário (login/senha) por cliente + provedor.

    Distinta de ``credenciais_api`` (Bearer de consumo da API): aqui guardamos o
    acesso do lojista ao portal do banco, com a senha CIFRADA em repouso pela mesma
    camada de ``app.cripto`` usada no payload pessoal. A senha nunca é devolvida em
    claro; rotaciona com frequência (~2 semanas) e é lida on-demand pelo worker.
    """

    __tablename__ = "credenciais_provedor"
    __table_args__ = (
        UniqueConstraint("cliente_id", "provedor", name="uq_credenciais_provedor_cliente_provedor"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cliente_id: Mapped[str] = mapped_column(
        ForeignKey("clientes_api.id"), nullable=False, index=True
    )
    provedor: Mapped[str] = mapped_column(String(100), nullable=False)
    usuario: Mapped[str] = mapped_column(String(200), nullable=False)
    # Senha do portal cifrada (Fernet via app.cripto); nunca em claro no storage.
    senha_cifrada: Mapped[str] = mapped_column(Text, nullable=False)
    # Configuração completa e tipada por provedor (API key, secret, id da loja
    # etc.), sempre cifrada. usuario/senha acima permanecem para compatibilidade
    # com credenciais de portais já cadastradas.
    config_cifrada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    habilitado: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Sinais operacionais (sem segredo): saúde da credencial e rotação.
    falhas_login: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ultimo_sucesso_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ultimo_erro_sanitizado: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )


class AuditoriaORM(Base):
    """Trilha de ações administrativas (sem payload pessoal nem segredo em claro)."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[str] = mapped_column(
        ForeignKey("clientes_api.id"), nullable=False, index=True
    )
    ator: Mapped[str] = mapped_column(String(200), nullable=False)
    acao: Mapped[str] = mapped_column(String(100), nullable=False)
    provedor: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)


class SimulacaoORM(Base):
    __tablename__ = "simulacoes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cliente_id: Mapped[str] = mapped_column(
        ForeignKey("clientes_api.id"), nullable=False, index=True
    )
    referencia_externa: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Quem disparou a simulação no Portal (email/identidade do ator via X-Ator).
    # Não é segredo; habilita o histórico por usuário (Task 16). Nulo em chamadas
    # diretas à API sem ator.
    solicitado_por: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, default="recebida", index=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )
    reserva_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reservada_ate: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Payload pessoal do job (cpf/nascimento/renda) cifrado em repouso; índice cego para dedup.
    payload_cifrado: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cpf_indice_cego: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    # Parte não-pessoal da solicitação, necessária ao worker para executar o job depois.
    categoria: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    valor: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    entrada: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    prazo_meses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provedores: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Campos do driver real (Task 12): não sensíveis; CPF/nasc continuam no payload cifrado.
    cnh: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    placa: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    uf_licenciamento: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    finalidade: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    prazos_meses: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Campos opcionais usados por APIs de financiamento (primeiro: Banco PAN).
    codigo_veiculo_provedor: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ano_modelo: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    zero_km: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    resultados: Mapped[list["ResultadoORM"]] = relationship(
        back_populates="simulacao", cascade="all, delete-orphan"
    )
    tentativas: Mapped[list["SimulacaoTentativaORM"]] = relationship(
        back_populates="simulacao", cascade="all, delete-orphan"
    )
    eventos: Mapped[list["SimulacaoEventoORM"]] = relationship(
        back_populates="simulacao", cascade="all, delete-orphan",
        order_by="SimulacaoEventoORM.id",
    )
    tarefas_provedor: Mapped[list["SimulacaoProvedorORM"]] = relationship(
        back_populates="simulacao",
        cascade="all, delete-orphan",
        order_by="SimulacaoProvedorORM.criada_em",
    )


class ResultadoORM(Base):
    __tablename__ = "simulacao_resultados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulacao_id: Mapped[str] = mapped_column(ForeignKey("simulacoes.id"))
    provedor: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="concluida")
    # Campos monetários ficam nulos quando o provedor falhou/rejeitou (sem parcela).
    valor_parcela: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    taxa_am: Mapped[Optional[float]] = mapped_column(Numeric(6, 4), nullable=True)
    prazo_meses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valor_financiado: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    # Entrada necessaria devolvida pelo banco (ex.: Santander calcula e retorna).
    entrada: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    codigo_erro: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    simulacao: Mapped["SimulacaoORM"] = relationship(back_populates="resultados")


class SimulacaoTentativaORM(Base):
    """Uma linha por tentativa de execução de um provedor (duração e erro sanitizado)."""

    __tablename__ = "simulacao_tentativas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulacao_id: Mapped[str] = mapped_column(ForeignKey("simulacoes.id"), index=True)
    provedor: Mapped[str] = mapped_column(String)
    tentativa: Mapped[int] = mapped_column(Integer)
    duracao_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String)
    codigo_erro: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)

    simulacao: Mapped["SimulacaoORM"] = relationship(back_populates="tentativas")


class SimulacaoEventoORM(Base):
    """Timeline sanitizada do job; nunca guarda CPF, senha ou HTML do portal."""

    __tablename__ = "simulacao_eventos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulacao_id: Mapped[str] = mapped_column(ForeignKey("simulacoes.id"), index=True)
    # Opcional: agrupa timeline por banco no fan-out multi-provedor.
    provedor: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    etapa: Mapped[str] = mapped_column(String(80), nullable=False)
    nivel: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    mensagem: Mapped[str] = mapped_column(String(240), nullable=False)
    # Caminho interno; a API nunca o devolve e só serve o arquivo após checar tenant.
    screenshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)

    simulacao: Mapped["SimulacaoORM"] = relationship(back_populates="eventos")


class SimulacaoProvedorORM(Base):
    """Tarefa filha: um banco por simulação (fan-out). Migration 0012."""

    __tablename__ = "simulacao_provedores"
    __table_args__ = (
        UniqueConstraint(
            "simulacao_id", "provedor", name="uq_simulacao_provedores_sim_provedor"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    simulacao_id: Mapped[str] = mapped_column(
        ForeignKey("simulacoes.id"), nullable=False, index=True
    )
    cliente_id: Mapped[str] = mapped_column(
        ForeignKey("clientes_api.id"), nullable=False, index=True
    )
    provedor: Mapped[str] = mapped_column(String(100), nullable=False)
    # api | playwright | mock
    tipo_driver: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    # recebida|acordando_worker|reservada|processando|concluida|rejeitada|falhou|cancelada
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="recebida", index=True)
    tentativa: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserva_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reservada_ate: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worker_slot_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    codigo_erro: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    iniciada_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finalizada_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )

    simulacao: Mapped["SimulacaoORM"] = relationship(back_populates="tarefas_provedor")


class WorkerSlotORM(Base):
    """Inventário de Machines Fly pré-criadas (workers Playwright/API)."""

    __tablename__ = "worker_slots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provedor: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tipo_driver: Mapped[str] = mapped_column(String(32), nullable=False, default="playwright")
    fly_machine_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    regiao: Mapped[str] = mapped_column(String(16), nullable=False, default="gru")
    memory_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    estado_observado: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    ultimo_start_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ultimo_stop_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ultima_falha_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_agora, onupdate=_agora
    )


class IdempotenciaORM(Base):
    __tablename__ = "idempotencia"

    cliente_id: Mapped[str] = mapped_column(
        ForeignKey("clientes_api.id"), primary_key=True
    )
    chave: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    simulacao_id: Mapped[str] = mapped_column(ForeignKey("simulacoes.id"))
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
