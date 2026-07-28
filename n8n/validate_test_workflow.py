#!/usr/bin/env python3
"""Valida o isolamento do workflow de teste por numero de WhatsApp."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CANONICAL = ROOT / "workflow-ai-nao-salvos.json"
TEST_WORKFLOW = ROOT / "workflow-teste-numero-autorizado.json"
TEST_PHONE = "5551980336365"
TEST_PHONE_ALIAS = "555180336365"
TEST_ID = "wAiTesteRestrito01"
TEST_WEBHOOK = "whatsapp-ai-teste"


def by_name(workflow: dict, name: str) -> dict:
    return next(node for node in workflow["nodes"] if node.get("name") == name)


def main() -> None:
    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
    test = json.loads(TEST_WORKFLOW.read_text(encoding="utf-8"))

    assert test["id"] == TEST_ID
    assert test["name"] == f"WhatsApp IA - TESTE {TEST_PHONE}"
    assert test["active"] is False
    assert test["activeVersionId"] is None
    assert test["connections"]["Se resposta controle1"]["main"][1][0]["node"] == "AI Agent1"
    assert test["connections"] == canonical["connections"]
    assert len(test["nodes"]) == len(canonical["nodes"]) == 25
    assert [(node["name"], node["type"]) for node in test["nodes"]] == [
        (node["name"], node["type"]) for node in canonical["nodes"]
    ]
    nomes = {node["name"] for node in test["nodes"]}
    removidos = {
        "E audio1", "Transcrever audio1", "Aplicar transcricao1",
        "registrar_consentimento1", "registrar_lead1", "consultar_por_placa1",
        "E primeira mensagem1", "Aguardar 60 segundos1",
    }
    assert removidos.isdisjoint(nomes)
    assert "if (audio) return []" in by_name(test, "Extrair1")["parameters"]["jsCode"]

    webhook = by_name(test, "Webhook1")
    assert webhook["parameters"]["path"] == TEST_WEBHOOK
    assert webhook["webhookId"] == TEST_WEBHOOK
    assert by_name(canonical, "Webhook1")["parameters"]["path"] == "whatsapp-ai"

    code = by_name(test, "Extrair1")["parameters"]["jsCode"]
    canonical_code = by_name(canonical, "Extrair1")["parameters"]["jsCode"]
    assert f'const telefonesTeste = ["{TEST_PHONE}","{TEST_PHONE_ALIAS}"];' in code
    assert "remetentesPossiveis.some((numero) => telefonesTeste.includes(numero))" in code
    assert "[jid, jidAlt, jidTelefone, telefone, ...participantes]" in code
    assert "const telefonesTeste =" not in canonical_code

    gate_code = by_name(test, "Gate somente nao salvos1")["parameters"]["jsCode"]
    canonical_gate_code = by_name(canonical, "Gate somente nao salvos1")["parameters"]["jsCode"]
    assert f'["{TEST_PHONE}","{TEST_PHONE_ALIAS}"].includes' in gate_code
    assert "ehTelefoneTeste && !origem.ehGrupo && botAtivo" in gate_code
    assert "acao: 'cliente'" in gate_code
    assert "$getWorkflowStaticData('global')" in gate_code
    assert "vitorMotosFirstContact20260727v2" in gate_code
    assert "primeiraMensagem: primeiraMensagemTeste" in gate_code
    assert "ehTelefoneTeste" not in canonical_gate_code

    memory_key = by_name(test, "Memoria da conversa1")["parameters"]["sessionKey"]
    assert memory_key == (
        "={{ $('Extrair1').first().json.instance + ':' + "
        "$('Extrair1').first().json.telefone }}"
    )
    assert not memory_key.startswith("==")

    responder = json.dumps(by_name(test, "Responder WhatsApp1"), ensure_ascii=False)
    registrar_saida = json.dumps(by_name(test, "Registrar saida do bot1"), ensure_ascii=False)
    assert "$('Extrair1').item" not in responder
    assert "$('Extrair1').item" not in registrar_saida
    assert "$('Extrair1').first()" in responder
    assert "$('Extrair1').first()" in registrar_saida

    serialized = json.dumps(test, ensure_ascii=False)
    for placeholder in (
        "__INSTANCE__",
        "__EVOLUTION_KEY__",
        "__CHATBOT_TOKEN__",
        "__CHATBOT_WEBHOOK_TOKEN__",
    ):
        assert placeholder in serialized, f"placeholder ausente: {placeholder}"

    assert all(share["workflowId"] == TEST_ID for share in test.get("shared", []))
    print(
        "workflow de teste valido: "
        f"{len(test['nodes'])} nos, webhook={TEST_WEBHOOK}, telefone={TEST_PHONE}"
    )


if __name__ == "__main__":
    main()
