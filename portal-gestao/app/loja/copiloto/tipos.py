"""Contratos do Copiloto — sem FastAPI, sem ORM, sem cliente HTTP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

# Mesmo vocabulário do SalesOverview: a tela e o copiloto falam a mesma língua.
StatusCopiloto = Literal["ok", "vazio", "parcial", "erro", "indisponivel"]

STATUS_OK = "ok"
STATUS_VAZIO = "vazio"
STATUS_PARCIAL = "parcial"
STATUS_ERRO = "erro"
STATUS_INDISPONIVEL = "indisponivel"

# Papéis que enxergam o negócio inteiro da loja (dono/gerente + admin).
PAPEIS_GESTAO_COPILOTO = frozenset({"dono", "gerente", "admin_plataforma"})


@dataclass(frozen=True)
class Cobertura:
    """Sobre quantos itens o número vale.

    É a defesa contra o número *silenciosamente parcial* (§6.2 do design):
    margem calculada sobre 6 de 14 vendas não é "a margem do mês".
    """

    com_dado: int
    total: int

    def __post_init__(self) -> None:
        if self.com_dado < 0 or self.total < 0:
            raise ValueError("cobertura não aceita negativo")
        if self.com_dado > self.total:
            raise ValueError("com_dado não pode ser maior que total")

    @property
    def completa(self) -> bool:
        return self.com_dado == self.total

    @property
    def parcial(self) -> bool:
        # 0 de 0 é vazio, não parcial.
        return self.total > 0 and self.com_dado < self.total

    def to_dict(self) -> dict[str, int]:
        return {"com_dado": self.com_dado, "total": self.total}


@dataclass(frozen=True)
class CopilotoContexto:
    """Quem está perguntando. Nunca é preenchido por parâmetro de rota.

    ``loja_slug`` e ``papel`` saem da sessão autenticada. O LLM (fase 2) não
    enxerga nem consegue preencher estes campos.
    """

    loja_slug: str
    papel: str
    ator_email: str
    hoje: date
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "papel", (self.papel or "").strip().casefold())
        object.__setattr__(
            self, "ator_email", (self.ator_email or "").strip().casefold()
        )

    @property
    def pode_ver_margem(self) -> bool:
        return self.papel in PAPEIS_GESTAO_COPILOTO
