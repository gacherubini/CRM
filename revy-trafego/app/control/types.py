from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ControlError(Exception):
    """Erro estável exposto pelas interfaces do Revy Control."""


class AccessDenied(ControlError):
    pass


class StoreNotFound(ControlError):
    pass


class StoreSlugConflict(ControlError):
    pass


class InvalidStoreTransition(ControlError):
    def __init__(self, current: "StoreStatus", target: "StoreStatus") -> None:
        self.current = current
        self.target = target
        super().__init__(f"transição de {current.value} para {target.value} não permitida")


class ActiveResponsibleConflict(ControlError):
    def __init__(self, store_id: str, manager_id: str) -> None:
        self.store_id = store_id
        self.manager_id = manager_id
        super().__init__("a Loja já possui Gestor Responsável ativo")


class TrafficLinkNotFound(ControlError):
    pass


class TrafficLinkConflict(ControlError):
    pass


class ManagerNotFound(ControlError):
    pass


class StoreStatus(str, Enum):
    DRAFT = "rascunho"
    CONFIGURING = "em_configuracao"
    READY = "pronta"
    ACTIVE = "ativa"
    SUSPENDED = "suspensa"
    CLOSED = "encerrada"


class TrafficRole(str, Enum):
    RESPONSIBLE = "responsavel"
    COLLABORATOR = "colaborador"


class AuditResult(str, Enum):
    SUCCESS = "sucesso"
    DENIED = "negado"
    ERROR = "erro"


@dataclass(frozen=True)
class Actor:
    id: str
    email: str
    name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass(frozen=True)
class CreateStore:
    name: str
    slug: str


@dataclass(frozen=True)
class StoreRef:
    id: str | None = None
    slug: str | None = None

    def __post_init__(self) -> None:
        if bool(self.id) == bool(self.slug):
            raise ValueError("informe exatamente um identificador da Loja")


@dataclass(frozen=True)
class StoreView:
    id: str
    name: str
    slug: str
    status: StoreStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TransitionStore:
    store: StoreRef
    target: StoreStatus
    reason: str | None = None


@dataclass(frozen=True)
class GrantTrafficAccess:
    store: StoreRef
    manager_id: str
    role: TrafficRole


@dataclass(frozen=True)
class RevokeTrafficAccess:
    store: StoreRef
    manager_id: str
    reason: str | None = None


@dataclass(frozen=True)
class TrafficLinkView:
    id: str
    store_id: str
    manager_id: str
    role: TrafficRole
    started_at: datetime
    ended_at: datetime | None

    @property
    def active(self) -> bool:
        return self.ended_at is None


@dataclass(frozen=True)
class AccessibleStore:
    store: StoreView
    role: TrafficRole | None


@dataclass(frozen=True)
class AuditQuery:
    store_id: str | None = None
    limit: int = 100


@dataclass(frozen=True)
class AuditEventView:
    id: str
    store_id: str | None
    actor_id: str | None
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    result: AuditResult
    before: dict[str, object] | None
    after: dict[str, object] | None
    reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class AuditPage:
    items: tuple[AuditEventView, ...]
