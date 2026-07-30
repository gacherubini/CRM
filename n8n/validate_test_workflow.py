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
    # multi-WA: instance vem do body do webhook; só secrets usam placeholders.
    assert "__INSTANCE__" not in serialized, "workflow de teste não deve fixar __INSTANCE__"
    for placeholder in (
        "__EVOLUTION_KEY__",
        "__CHATBOT_TOKEN__",
        "__CHATBOT_WEBHOOK_TOKEN__",
    ):
        assert placeholder in serialized, f"placeholder ausente: {placeholder}"
    extract = by_name(test, "Extrair1")["parameters"]["jsCode"]
    assert "b.instance" in extract and "if (!instance) return []" in extract

    assert all(share["workflowId"] == TEST_ID for share in test.get("shared", []))
    test_prompt = by_name(test, 'AI Agent1')['parameters']['options']['systemMessage']
    canonical_prompt = by_name(canonical, 'AI Agent1')['parameters']['options']['systemMessage']
    assert 'jornada de catálogo antes da simulação' in test_prompt
    assert 'qual delas você quer conhecer melhor?' in test_prompt
    assert 'quer que eu mande as fotos do catálogo?' in test_prompt
    assert 'gostou dessa? se quiser, posso fazer uma simulação pra você.' in test_prompt
    assert 'qual moto você quer simular?' not in test_prompt
    assert 'jornada de catálogo antes da simulação' not in canonical_prompt
    assert 'qual moto você quer simular?' in canonical_prompt

    inventory = by_name(test, 'consultar_estoque1')
    canonical_inventory = by_name(canonical, 'consultar_estoque1')
    assert 'preserva a moto para oferecer fotos do catálogo' in inventory['parameters']['description']
    inventory_code = inventory['parameters']['jsCode']
    assert 'delete estadoTeste[' in inventory_code
    assert 'moto-escolhida:' in inventory_code
    assert 'veiculosTeste.length === 1' in inventory_code
    assert 'replace(/\\D/g' in inventory_code
    assert 'replace(/D/g' not in inventory_code
    assert inventory_code.index('delete estadoTeste[') < inventory_code.index('return JSON.stringify(resp)')
    assert 'delete estadoTeste' not in canonical_inventory['parameters']['jsCode']

    photo_tool = by_name(test, 'enviar_foto_veiculo1')
    canonical_photo_tool = by_name(canonical, 'enviar_foto_veiculo1')
    assert 'o veiculo_id é opcional nesse caso' in photo_tool['parameters']['description']
    assert 'moto-escolhida:' in photo_tool['parameters']['jsCode']
    assert 'telefone]?.id' in photo_tool['parameters']['jsCode']
    assert 'sem_veiculo_escolhido: true' in photo_tool['parameters']['jsCode']
    assert 'required' not in json.loads(photo_tool['parameters']['inputSchema'])
    assert 'sem_veiculo_escolhido' not in canonical_photo_tool['parameters']['jsCode']
    assert 'required' in json.loads(canonical_photo_tool['parameters']['inputSchema'])

    simulation_tool = by_name(test, 'simular1')
    canonical_simulation_tool = by_name(canonical, 'simular1')
    assert 'Use somente no fim da jornada' in simulation_tool['parameters']['description']
    assert 'qual moto o cliente quer conhecer melhor' in simulation_tool['parameters']['jsCode']
    assert 'qual moto o cliente quer simular' not in simulation_tool['parameters']['jsCode']
    assert 'Use somente no fim da jornada' not in canonical_simulation_tool['parameters']['description']

    print(
        "workflow de teste valido: "
        f"{len(test['nodes'])} nos, webhook={TEST_WEBHOOK}, telefone={TEST_PHONE}"
    )


if __name__ == "__main__":
    main()
