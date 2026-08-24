"""Port e adapters da projeção do Revy Control (identidade + entitlements)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.loja.types import (
    ROLES_OPERACIONAIS,
    EntitlementState,
    StoreMembership,
)


class ControlProjectionPort(Protocol):
    """Contrato versionado consumido pelo Revy Loja (sem FastAPI no domínio)."""

    def get_memberships(self, pessoa_id: str) -> list[StoreMembership]:
        """Memberships ativas da pessoa nas lojas operacionais."""
        ...

    def get_entitlements(self, loja_slug: str) -> EntitlementState | None:
        """Estado de módulos da loja; None se desconhecido / indisponível."""
        ...

    def apply_payload(self, loja_slug: str, payload: dict[str, Any]) -> list[str]:
        """Aplica snapshot versionado (idempotente). Retorna razões por envelope."""
        ...


def _roles_from_payload(raw: Any) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple, set, frozenset)):
        items = list(raw)
    else:
        return frozenset()
    return frozenset(
        str(r).strip().lower()
        for r in items
        if str(r).strip().lower() in ROLES_OPERACIONAIS
    )


def parse_memberships_from_payload(payload: dict[str, Any]) -> list[StoreMembership]:
    """Extrai memberships de um payload no shape de provisionamento do Control."""
    out: list[StoreMembership] = []
    people = payload.get("people") or []
    for person in people:
        if not isinstance(person, dict):
            continue
        loja_slug = str(
            person.get("loja_slug") or payload.get("loja_slug") or ""
        ).strip()
        roles = _roles_from_payload(person.get("roles") or person.get("cargos"))
        if not loja_slug:
            continue
        ativo = person.get("ativo", person.get("active", True))
        if person.get("state") in {"revogado", "inativo", "pendente"}:
            ativo = False
        if person.get("invite_status") in {"pending", "pendente"}:
            ativo = False
        out.append(
            StoreMembership(
                loja_slug=loja_slug,
                roles=roles,
                ativo=bool(ativo),
            )
        )
    # roles[] top-level opcional: [{pessoa_id, loja_slug, role, state}]
    for row in payload.get("roles") or []:
        if not isinstance(row, dict):
            continue
        loja_slug = str(row.get("loja_slug") or payload.get("loja_slug") or "").strip()
        role = str(row.get("role") or row.get("cargo") or "").strip().lower()
        if not loja_slug or role not in ROLES_OPERACIONAIS:
            continue
        state = str(row.get("state") or "ativo").lower()
        ativo = state in {"ativo", "active", "ativa"}
        out.append(
            StoreMembership(
                loja_slug=loja_slug,
                roles=frozenset({role}) if ativo else frozenset(),
                ativo=ativo,
            )
        )
    return out


def entitlements_from_operational(
    loja_slug: str,
    operational: list[dict[str, Any]] | None,
) -> EntitlementState:
    """Deriva EntitlementState a partir de envelopes operational do Control."""
    states: dict[str, str] = {}
    for env in operational or []:
        if not isinstance(env, dict):
            continue
        agg = str(env.get("aggregate") or "").strip()
        st = str(env.get("state") or "").strip()
        if agg:
            states[agg] = st
    loja_ativa = states.get("loja") == "ativa"
    vendas = loja_ativa and states.get("vendas") == "ativo"
    estoque = loja_ativa and states.get("estoque") == "ativo"
    return EntitlementState(
        loja_slug=loja_slug,
        loja_ativa=loja_ativa,
        vendas_enabled=vendas,
        estoque_enabled=estoque,
        source="control",
    )


@dataclass
class InMemoryControlProjectionPort:
    """Adapter em memória para testes e degradacao local."""

    memberships_by_pessoa: dict[str, list[StoreMembership]] = field(
        default_factory=dict
    )
    entitlements_by_loja: dict[str, EntitlementState] = field(default_factory=dict)
    applied_versions: dict[tuple[str, str], int] = field(default_factory=dict)
    apply_log: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def get_memberships(self, pessoa_id: str) -> list[StoreMembership]:
        return list(self.memberships_by_pessoa.get(pessoa_id, []))

    def get_entitlements(self, loja_slug: str) -> EntitlementState | None:
        return self.entitlements_by_loja.get(loja_slug)

    def set_memberships(self, pessoa_id: str, memberships: list[StoreMembership]) -> None:
        self.memberships_by_pessoa[pessoa_id] = list(memberships)

    def set_entitlements(self, state: EntitlementState) -> None:
        self.entitlements_by_loja[state.loja_slug] = state

    def apply_payload(self, loja_slug: str, payload: dict[str, Any]) -> list[str]:
        """Aplica envelopes operational de forma monotônica (mesma regra do Portal)."""
        self.apply_log.append((loja_slug, payload))
        reasons: list[str] = []
        for envelope in payload.get("operational") or []:
            if not isinstance(envelope, dict):
                continue
            aggregate = str(envelope.get("aggregate") or "")
            if not aggregate:
                continue
            version = int(envelope.get("version") or 0)
            key = (loja_slug, aggregate)
            prev = self.applied_versions.get(key)
            if prev is not None and prev > version:
                reasons.append("stale")
                continue
            if prev is not None and prev == version:
                reasons.append("idempotent")
                continue
            self.applied_versions[key] = version
            reasons.append("applied")

        # Atualiza entitlements derivados
        ents = entitlements_from_operational(
            loja_slug, payload.get("operational") or []
        )
        # Só sobrescreve se houve apply/idempotent de loja ou módulos
        if any(r in {"applied", "idempotent"} for r in reasons):
            # Se tudo stale, não reativa — mas idempotent mantém
            if not all(r == "stale" for r in reasons):
                # Recalcula a partir do que está em applied_versions + last states
                # Simplificação: usa payload atual se não for totalmente stale
                if "applied" in reasons or "idempotent" in reasons:
                    # Merge com estado anterior se partial
                    prev_ent = self.entitlements_by_loja.get(loja_slug)
                    if prev_ent and all(r != "applied" for r in reasons):
                        pass  # idempotent only — keep previous
                    else:
                        self.entitlements_by_loja[loja_slug] = ents

        # People/roles
        for m in parse_memberships_from_payload(payload):
            # index by synthetic pessoa from payload people
            pass
        people = payload.get("people") or []
        for person in people:
            if not isinstance(person, dict):
                continue
            pid = str(person.get("pessoa_id") or person.get("id") or person.get("email") or "")
            if not pid:
                continue
            mems = parse_memberships_from_payload(
                {**payload, "people": [person], "roles": []}
            )
            existing = self.memberships_by_pessoa.setdefault(pid, [])
            # replace same loja_slug
            for new_m in mems:
                existing = [e for e in existing if e.loja_slug != new_m.loja_slug]
                existing.append(new_m)
            self.memberships_by_pessoa[pid] = existing

        return reasons


@dataclass
class HttpControlProjectionPort:
    """Adapter HTTP para projeção local do Control via DB.

    Substitui o stub original em Fase 2: lê memberships persistidas
    na tabela ``vinculo_loja_pessoa`` (preenchida por apply_payload do provisioning).
    """

    base_url: str = ""
    service_token: str = ""
    timeout: float = 3.0
    db_session: Any = None

    def get_memberships(self, pessoa_id: str) -> list[StoreMembership]:
        from app.models import VinculoLojaPessoa
        from sqlalchemy.orm import Session

        if not self.db_session:
            return []
        if not isinstance(self.db_session, Session):
            return []

        try:
            rows = self.db_session.query(VinculoLojaPessoa).filter(
                VinculoLojaPessoa.pessoa_id == pessoa_id,
                VinculoLojaPessoa.state == "ativo",
            ).all()

            out: dict[str, StoreMembership] = {}
            for row in rows:
                key = row.loja_slug
                # Mesmo filtro de parse_memberships_from_payload: só cargo
                # operacional da Loja vira role. `admin_plataforma` gravado num
                # vínculo não pode virar acesso de loja por esta porta — a
                # decisão está em identity.py::_roles_from_papel.
                cargo = _roles_from_payload([row.cargo])
                if key in out:
                    existing = out[key]
                    out[key] = StoreMembership(
                        loja_slug=existing.loja_slug,
                        roles=frozenset(existing.roles | cargo),
                        ativo=True,
                    )
                else:
                    out[key] = StoreMembership(
                        loja_slug=row.loja_slug,
                        roles=cargo,
                        ativo=True,
                    )
            return list(out.values())
        except Exception:
            return []

    def get_entitlements(self, loja_slug: str) -> EntitlementState | None:
        return None

    def apply_payload(self, loja_slug: str, payload: dict[str, Any]) -> list[str]:
        # Produção continua em app.provisioning.apply_payload via endpoint internal.
        return []
