"""SimulationProvider plugável (Plano #2A Task 6).

- none: edição Atendimento (sem simulação).
- mock: demonstração autônoma (taxas FICTÍCIAS, sem Motor).
- http: delega ao Motor de Simulação real (Plano #1A) via /v1/simulacoes.

Trocar de provider é configuração (SIMULATION_PROVIDER), não edição de código/n8n.
"""
from typing import Protocol

import httpx
from fastapi import HTTPException

from app import config


class SimulationProvider(Protocol):
    def disponivel(self) -> bool: ...
    def simular(self, payload: dict, idempotency_key: str) -> dict: ...


class NoSimulationProvider:
    def disponivel(self) -> bool:
        return False

    def simular(self, payload: dict, idempotency_key: str) -> dict:
        raise HTTPException(status_code=409, detail="simulação não habilitada nesta instalação")


# Taxas de demonstração — FICTÍCIAS, nunca são oferta real.
_TAXAS_DEMO = {"BancoDemo A": 0.019, "BancoDemo B": 0.021}


class MockSimulationProvider:
    def disponivel(self) -> bool:
        return True

    def simular(self, payload: dict, idempotency_key: str) -> dict:
        valor = payload["veiculo"]["valor"]
        entrada = payload["condicoes"].get("entrada", 0)
        prazo = payload["condicoes"]["prazo_meses"]
        financiado = max(valor - entrada, 0)
        resultados = []
        for banco, taxa in _TAXAS_DEMO.items():
            if prazo > 0:
                parcela = round(
                    financiado * (taxa * (1 + taxa) ** prazo) / ((1 + taxa) ** prazo - 1), 2
                )
            else:
                parcela = 0.0
            resultados.append(
                {
                    "provedor": banco,
                    "status": "concluida",
                    "valor_parcela": parcela,
                    "taxa_am": round(taxa * 100, 2),
                    "prazo_meses": prazo,
                    "valor_financiado": financiado,
                }
            )
        return {"status": "concluida", "resultados": resultados}


class HttpSimulationProvider:
    def __init__(self, base_url: str | None = None, timeout: float = 8.0):
        self.base_url = (base_url or config.MOTOR_URL).rstrip("/")
        self.timeout = timeout

    def disponivel(self) -> bool:
        return bool(self.base_url)

    def simular(self, payload: dict, idempotency_key: str) -> dict:
        try:
            r = httpx.post(
                f"{self.base_url}/v1/simulacoes",
                json=payload,
                headers={"Idempotency-Key": idempotency_key},
                timeout=self.timeout,
            )
            r.raise_for_status()
            sim = r.json()
            if sim.get("status") in ("concluida", "parcial"):
                g = httpx.get(
                    f"{self.base_url}/v1/simulacoes/{sim['id']}", timeout=self.timeout
                )
                g.raise_for_status()
                return g.json()
            return {"status": sim.get("status", "processando"), "id": sim.get("id"), "resultados": []}
        except Exception:
            return {
                "status": "falhou",
                "resultados": [],
                "mensagem": "Não consegui simular agora; posso chamar um atendente.",
            }


def get_simulation_provider() -> SimulationProvider:
    tipo = config.SIMULATION_PROVIDER
    if tipo == "mock":
        return MockSimulationProvider()
    if tipo == "http":
        return HttpSimulationProvider()
    return NoSimulationProvider()
