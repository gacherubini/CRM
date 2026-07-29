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


class StoreEditConflict(ControlError):
    def __init__(self, current: "StoreStatus") -> None:
        self.current = current
        super().__init__(
            f"Loja em {current.value} não pode mais editar dados cadastrais"
        )


class InvalidStoreSlug(ControlError):
    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__("slug de Loja inválido")


class InvalidStoreTransition(ControlError):
    def __init__(self, current: "StoreStatus", target: "StoreStatus") -> None:
        self.current = current
        self.target = target
        super().__init__(f"transição de {current.value} para {target.value} não permitida")


class StoreReadinessBlocked(ControlError):
    def __init__(self, store_id: str, requirement: str) -> None:
        self.store_id = store_id
        self.requirement = requirement
        if requirement == "activatable_owner":
            message = (
                "Loja precisa de ao menos um Dono com acesso ativável "
                "(pendente ou ativo) neste estado"
            )
        else:
            message = "Loja precisa manter ao menos um Dono ativo neste estado"
        super().__init__(message)


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


class PersonNotFound(ControlError):
    pass


class InvalidPersonEmail(ControlError):
    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__("e-mail da Pessoa Revy inválido")


class PersonEmailConflict(ControlError):
    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__("já existe Pessoa Revy com este e-mail")


class ControlAccountConflict(ControlError):
    pass


class ControlInvitationInvalid(ControlError):
    pass


class WeakControlPassword(ControlError):
    pass


class ControlRecoveryInvalid(ControlError):
    pass


class StoreRoleConflict(ControlError):
    def __init__(self, store_id: str, person_id: str, role: "StoreRole") -> None:
        self.store_id = store_id
        self.person_id = person_id
        self.role = role
        super().__init__("a Pessoa Revy já possui este cargo ativo na Loja")


class StoreRoleNotFound(ControlError):
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


class StoreRole(str, Enum):
    OWNER = "dono"
    MANAGER = "gerente"
    SELLER = "vendedor"


class ControlAccountRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "gestor"


class ControlAccountStatus(str, Enum):
    PENDING = "pendente"
    ACTIVE = "ativo"
    DISABLED = "desativado"


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
class UpdateStore:
    store: StoreRef
    name: str


@dataclass(frozen=True)
class StoreView:
    id: str
    name: str
    slug: str
    status: StoreStatus
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RegisterPerson:
    name: str
    email: str


@dataclass(frozen=True)
class PersonRef:
    id: str


@dataclass(frozen=True)
class PersonView:
    id: str
    name: str
    email: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ControlAccountView:
    id: str
    person_id: str
    person_name: str
    person_email: str
    role: ControlAccountRole
    status: ControlAccountStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class InviteControlAccess:
    person: PersonRef
    role: ControlAccountRole


@dataclass(frozen=True)
class ActivateControlAccess:
    token: str
    password: str


@dataclass(frozen=True)
class IssuedControlInvitation:
    access_id: str
    person_email: str
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class ActivatedControlAccount:
    access_id: str
    person_email: str
    role: ControlAccountRole
    status: ControlAccountStatus


@dataclass(frozen=True)
class IssueControlPasswordRecovery:
    access_id: str


@dataclass(frozen=True)
class ConsumeControlPasswordRecovery:
    token: str
    password: str


@dataclass(frozen=True)
class IssuedControlPasswordRecovery:
    access_id: str
    person_email: str
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class RecoveredControlAccount:
    access_id: str
    person_email: str
    status: ControlAccountStatus


@dataclass(frozen=True)
class AssignStoreRole:
    store: StoreRef
    person: PersonRef
    role: StoreRole


@dataclass(frozen=True)
class StoreRoleRef:
    id: str


@dataclass(frozen=True)
class RevokeStoreRole:
    store: StoreRef
    assignment: StoreRoleRef
    reason: str | None = None


@dataclass(frozen=True)
class StoreRoleView:
    id: str
    store_id: str
    person_id: str
    role: StoreRole
    source: str
    source_id: str | None
    started_at: datetime
    ended_at: datetime | None

    @property
    def active(self) -> bool:
        return self.ended_at is None


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
