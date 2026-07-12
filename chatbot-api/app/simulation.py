"""SimulationProvider plugável (Plano #2A Task 6).

- none: edição Atendimento (sem simulação).
- mock: demonstração autônoma (taxas FICTÍCIAS, sem Motor).
- http: delega ao Motor de Simulação real (Plano #1A) via /v1/simulacoes.

Trocar de provider é configuração (SIMULATION_PROVIDER), não edição de código/n8n.
"""
import time
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
    ESTADOS_TERMINAIS = {
        "concluida", "parcial", "falhou", "aguardando_intervencao", "cancelada"
    }

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        poll_timeout: float | None = None,
        poll_interval: float | None = None,
        token: str | None = None,
    ):
        self.base_url = (base_url or config.MOTOR_URL).rstrip("/")
        self.timeout = config.MOTOR_REQUEST_TIMEOUT if timeout is None else timeout
        self.poll_timeout = config.MOTOR_POLL_TIMEOUT if poll_timeout is None else poll_timeout
        self.poll_interval = (
            config.MOTOR_POLL_INTERVAL if poll_interval is None else poll_interval
        )
        self.token = config.MOTOR_TOKEN if token is None else token

    def disponivel(self) -> bool:
        return bool(self.base_url and self.token)

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    @staticmethod
    def _fallback(mensagem: str) -> dict:
        return {"status": "falhou", "resultados": [], "mensagem": mensagem}

    def simular(self, payload: dict, idempotency_key: str) -> dict:
        try:
            resposta = httpx.post(
                f"{self.base_url}/v1/simulacoes",
                json=payload,
                headers=self._headers(idempotency_key),
                timeout=self.timeout,
            )
            resposta.raise_for_status()
            criada = resposta.json()
            sim_id = criada.get("id")
            if not sim_id:
                return self._fallback(
                    "O serviço de simulação respondeu de forma inválida; posso chamar um atendente."
                )

            limite = time.monotonic() + self.poll_timeout
            while True:
                consulta = httpx.get(
                    f"{self.base_url}/v1/simulacoes/{sim_id}",
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                consulta.raise_for_status()
                atual = consulta.json()
                status = atual.get("status")
                if status in self.ESTADOS_TERMINAIS:
                    if status in {"falhou", "aguardando_intervencao", "cancelada"}:
                        atual.setdefault(
                            "mensagem",
                            "Não consegui concluir a simulação agora; posso chamar um atendente.",
                        )
                    return atual
                if time.monotonic() >= limite:
                    return self._fallback(
                        "A simulação está demorando mais que o esperado; posso chamar um atendente."
                    )
                if self.poll_interval > 0:
                    time.sleep(self.poll_interval)
        except Exception:
            return self._fallback(
                "Não consegui simular agora; posso chamar um atendente."
            )


def get_simulation_provider() -> SimulationProvider:
    tipo = config.SIMULATION_PROVIDER
    if tipo == "mock":
        return MockSimulationProvider()
    if tipo == "http":
        return HttpSimulationProvider()
    return NoSimulationProvider()
