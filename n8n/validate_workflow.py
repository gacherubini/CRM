#!/usr/bin/env python3
"""Valida invariantes de segurança do workflow WhatsApp versionado."""

from __future__ import annotations

import json
from pathlib import Path


WORKFLOW = Path(__file__).with_name("workflow-ai-nao-salvos.json")
WEBHOOK_URL = "http://chatbot-api:8000/webhook/mensagem"
WEBHOOK_HEADER = "X-Webhook-Token"
WEBHOOK_TOKEN_PLACEHOLDER = "__CHATBOT_WEBHOOK_TOKEN__"


def main() -> None:
    data = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    serialized = json.dumps(data, ensure_ascii=False).lower()

    assert "bypass_teste" not in serialized, "workflow contém bypass_teste"
    assert "bypass de testes" not in serialized, "workflow contém bypass por telefone"

    webhook_nodes = [
        node
        for node in data.get("nodes", [])
        if node.get("parameters", {}).get("url") == WEBHOOK_URL
    ]
    assert len(webhook_nodes) == 2, "esperados dois POSTs para o webhook do Chatbot"

    for node in webhook_nodes:
        parameters = node["parameters"]
        headers = parameters.get("headerParameters", {}).get("parameters", [])
        assert parameters.get("sendHeaders") is True, (
            f"{node.get('name')}: envio de headers desativado"
        )
        assert {header.get("name"): header.get("value") for header in headers}.get(
            WEBHOOK_HEADER
        ) == WEBHOOK_TOKEN_PLACEHOLDER, (
            f"{node.get('name')}: {WEBHOOK_HEADER} ausente ou inseguro"
        )

    simulation_node = next(
        (node for node in data.get("nodes", []) if node.get("name") == "simular1"),
        None,
    )
    assert simulation_node is not None, "tool simular1 ausente"
    simulation_code = simulation_node.get("parameters", {}).get("jsCode", "")
    assert "/v1/simulacoes/solicitar" in simulation_code, (
        "tool não usa a solicitação assíncrona e privada"
    )
    assert "/estado" in simulation_code and "bot_ativo: false" in simulation_code, (
        "tool de simulação não força handoff para o vendedor"
    )
    assert "Idempotency-Key" in simulation_code and "providerMessageId" in simulation_code, (
        "tool de simulação não deduplica pela mensagem do WhatsApp"
    )
    assert "JSON.stringify(resp)" not in simulation_code, (
        "tool de simulação pode expor a resposta financeira ao modelo"
    )
    assert "valor_parcela" not in simulation_code and "taxa_am" not in simulation_code, (
        "tool de simulação contém campos financeiros na resposta"
    )
    assert "solicitacao_registrada" not in simulation_code, (
        "tool expõe status técnico ao modelo"
    )

    agent_node = next(
        (node for node in data.get("nodes", []) if node.get("name") == "AI Agent1"),
        None,
    )
    system_message = (
        agent_node.get("parameters", {}).get("options", {}).get("systemMessage", "")
        if agent_node
        else ""
    )
    assert "PRIVACIDADE DO RESULTADO" in system_message, (
        "prompt não proíbe a divulgação do resultado"
    )

    print(
        "workflow n8n válido: sem bypass, webhook autenticado e resultado financeiro privado"
    )


if __name__ == "__main__":
    main()
