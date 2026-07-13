"""Base reutilizável para drivers bancários via Playwright (Task 12).

Nesta fatia: apenas o esqueleto (sem login real). O ``SantanderDriver`` preenche
os passos do portal. Testes de integração usam fixtures HTML; smoke live é gated.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.motor.base import SolicitacaoSimulacao
from app.motor.drivers import (
    DriverContext,
    IntervencaoNecessaria,
    ResultadoDriver,
)


class PlaywrightBankDriver(ABC):
    """Base para bancos sem API: browser headless + sessão + screenshots."""

    provedor: str = "desconhecido"
    real: bool = True

    def __init__(
        self,
        *,
        headless: bool = True,
        storage_state_path: str | Path | None = None,
        screenshot_dir: str | Path | None = None,
        timeout_ms: int = 30_000,
    ):
        self.headless = headless
        self.storage_state_path = Path(storage_state_path) if storage_state_path else None
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        self.timeout_ms = timeout_ms

    def __call__(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        """Ponto de entrada do worker — subclasses implementam ``simular``."""
        return self.simular(sol, ctx)

    @abstractmethod
    def simular(
        self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None
    ) -> list[ResultadoDriver]:
        """Executa o fluxo no portal e devolve um resultado por prazo."""

    def _screenshot_falha(self, page, nome: str = "falha") -> Optional[Path]:
        """Grava screenshot se houver diretório configurado; nunca levanta."""
        if page is None or not self.screenshot_dir:
            return None
        try:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            destino = self.screenshot_dir / f"{self.provedor}_{nome}.png"
            page.screenshot(path=str(destino), full_page=True)
            return destino
        except Exception:
            return None

    def _falha_campo(self, campo: str) -> IntervencaoNecessaria:
        return IntervencaoNecessaria(
            codigo="campo_nao_encontrado",
            mensagem=f"campo {campo} não encontrado no portal {self.provedor}",
        )
