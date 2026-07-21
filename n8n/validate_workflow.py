#!/usr/bin/env python3
"""Valida invariantes de segurança do workflow WhatsApp versionado."""

from __future__ import annotations

import json
from pathlib import Path


WORKFLOW = Path(__file__).with_name("workflow-ai-nao-salvos.json")
WEBHOOK_URL = "http://chatbot-api:8000/webhook/mensagem"
WEBHOOK_HEADER = "X-Webhook-Token"
WEBHOOK_TOKEN_PLACEHOLDER = "__CHATBOT_WEBHOOK_TOKEN__"
AUDIO_URL = "http://chatbot-api:8000/webhook/audio/transcrever"
IMAGE_INGEST_URL = "http://chatbot-api:8000/webhook/operacao/veiculos/foto"
ROTEAMENTO_URL = "http://chatbot-api:8000/v1/operacao/roteamento"


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

    vehicle_create_node = next(
        (
            node
            for node in data.get("nodes", [])
            if node.get("name") == "cadastrar_veiculo1"
        ),
        None,
    )
    assert vehicle_create_node is not None, "tool cadastrar_veiculo1 ausente"
    vehicle_create_code = vehicle_create_node.get("parameters", {}).get("jsCode", "")
    vehicle_create_schema = vehicle_create_node.get("parameters", {}).get(
        "inputSchema", ""
    )
    assert "origem.telefone" in vehicle_create_code, (
        "telefone do cadastro deve vir do webhook"
    )
    assert "origem.providerMessageId" in vehicle_create_code, (
        "idempotência do cadastro deve vir da mensagem real"
    )
    assert "input.telefone_solicitante" not in vehicle_create_code, (
        "modelo ainda controla o telefone autorizado"
    )
    assert "input.idempotency_key" not in vehicle_create_code, (
        "modelo ainda controla a chave idempotente"
    )
    assert '"telefone_solicitante"' not in vehicle_create_schema, (
        "schema não deve pedir telefone ao modelo"
    )
    assert '"idempotency_key"' not in vehicle_create_schema, (
        "schema não deve pedir idempotência ao modelo"
    )
    assert '"additionalProperties": false' in vehicle_create_schema, (
        "schema do cadastro deve rejeitar campos extras do modelo"
    )
    assert "input.foto_url" not in vehicle_create_code, (
        "modelo não pode escolher URL de foto no cadastro"
    )
    assert "input.codigo_interno" not in vehicle_create_code, (
        "modelo não deve enviar campo fora do schema do cadastro"
    )

    photo_node = next(
        (node for node in data.get("nodes", []) if node.get("name") == "enviar_foto_veiculo1"),
        None,
    )
    assert photo_node is not None, "tool enviar_foto_veiculo1 ausente"
    photo_code = photo_node.get("parameters", {}).get("jsCode", "")
    photo_schema = photo_node.get("parameters", {}).get("inputSchema", "")
    assert "/v1/estoque/veiculos/" in photo_code and "/midia-principal" in photo_code, (
        "tool não resolve a foto confiável no backend tenant-scoped"
    )
    assert "/message/sendMedia/__INSTANCE__" in photo_code, (
        "tool não envia mídia pela Evolution"
    )
    assert "mediatype: 'image'" in photo_code and "media: mediaUrl.toString()" in photo_code, (
        "payload de imagem da Evolution incompleto"
    )
    assert '"veiculo_id"' in photo_schema and '"url"' not in photo_schema, (
        "modelo deve informar somente veiculo_id, nunca URL de mídia"
    )
    assert "origem.destino" in photo_code and "input.destino" not in photo_code, (
        "destino da foto deve vir do webhook, não do modelo"
    )
    system_prompt = agent_node.get("parameters", {}).get("options", {}).get("systemMessage", "")
    assert "enviar_foto_veiculo" in system_prompt and "não mande o cliente abrir site" in system_prompt, (
        "prompt não prioriza o envio da foto no próprio WhatsApp"
    )
    photo_connections = data.get("connections", {}).get("enviar_foto_veiculo1", {})
    assert any(
        item.get("node") == "AI Agent1" and item.get("type") == "ai_tool"
        for group in photo_connections.get("ai_tool", [])
        for item in group
    ), "tool de foto não está conectada ao AI Agent"

    nodes_by_name = {node.get("name"): node for node in data.get("nodes", [])}
    audio_node = nodes_by_name.get("Transcrever audio1")
    assert audio_node is not None, "nó de transcrição de áudio ausente"
    audio_params = audio_node.get("parameters", {})
    assert audio_params.get("url") == AUDIO_URL, "áudio não passa pela Chatbot API"
    audio_headers = {
        header.get("name"): header.get("value")
        for header in audio_params.get("headerParameters", {}).get("parameters", [])
    }
    assert audio_headers.get(WEBHOOK_HEADER) == WEBHOOK_TOKEN_PLACEHOLDER, (
        "transcrição de áudio sem autenticação do webhook"
    )
    extract_code = nodes_by_name["Extrair1"].get("parameters", {}).get("jsCode", "")
    assert "audioMessage" in extract_code and "ehAudio" in extract_code, (
        "extração não reconhece áudio recebido"
    )
    assert "imageMessage" in extract_code and "ehImagem" in extract_code, (
        "extração não reconhece foto recebida"
    )
    assert "Boolean(imagem) && !fromMe" in extract_code, (
        "eco de imagem enviada pela própria loja entraria como upload"
    )
    connections = data.get("connections", {})
    assert (
        connections.get("Extrair1", {}).get("main", [[]])[0][0].get("node")
        == "E imagem de estoque1"
    )
    imagem_ramos = connections.get("E imagem de estoque1", {}).get("main", [])
    assert imagem_ramos[0][0].get("node") == "Salvar foto no estoque1"
    assert imagem_ramos[1][0].get("node") == "E audio1"
    imagem_node = nodes_by_name.get("Salvar foto no estoque1")
    assert imagem_node is not None, "nó de ingestão automática da foto ausente"
    imagem_params = imagem_node.get("parameters", {})
    assert imagem_params.get("url") == IMAGE_INGEST_URL
    imagem_headers = {
        header.get("name"): header.get("value")
        for header in imagem_params.get("headerParameters", {}).get("parameters", [])
    }
    assert imagem_headers.get(WEBHOOK_HEADER) == WEBHOOK_TOKEN_PLACEHOLDER
    imagem_body = imagem_params.get("jsonBody", "")
    assert "provider_message_id" in imagem_body and "telefone_solicitante" in imagem_body
    assert "base64" not in imagem_body and "media:" not in imagem_body, (
        "n8n não deve transportar ou guardar o binário da foto"
    )
    assert (
        connections.get("Salvar foto no estoque1", {}).get("main", [[]])[0][0].get("node")
        == "Responder cadastro de foto1"
    )
    assert (
        connections.get("Transcrever audio1", {}).get("main", [[]])[0][0].get("node")
        == "Aplicar transcricao1"
    )
    assert "audioFallback" in agent_node.get("parameters", {}).get("text", ""), (
        "fallback de áudio não chega ao fluxo conversacional"
    )
    for gate_name in ("Gate handoff e duplicidade1", "Gate somente nao salvos1"):
        gate_code = nodes_by_name[gate_name].get("parameters", {}).get("jsCode", "")
        assert "Aplicar transcricao1" in gate_code, (
            f"{gate_name} descarta o texto transcrito"
        )

    # Roteamento de operação: número autorizado salvo entra no cadastro sem bypass no JSON.
    rota_node = next(
        (
            node
            for node in data.get("nodes", [])
            if node.get("parameters", {}).get("url") == ROTEAMENTO_URL
        ),
        None,
    )
    assert rota_node is not None, "nó de roteamento de operação ausente"
    rota_params = rota_node["parameters"]
    rota_headers = {
        header.get("name"): header.get("value")
        for header in rota_params.get("headerParameters", {}).get("parameters", [])
    }
    assert rota_headers.get(WEBHOOK_HEADER) == WEBHOOK_TOKEN_PLACEHOLDER, (
        "roteamento sem autenticação do webhook"
    )
    rota_body = rota_params.get("jsonBody", "")
    assert "is_saved" in rota_body and "telefone" in rota_body, (
        "roteamento não envia telefone/is_saved"
    )
    assert rota_node.get("continueOnFail") is True, (
        "roteamento deve permitir fallback (continueOnFail)"
    )
    assert (
        connections.get("Rotear operacao1", {}).get("main", [[]])[0][0].get("node")
        == "Gate somente nao salvos1"
    ), "roteamento não alimenta o gate"
    gate_salvos_code = nodes_by_name["Gate somente nao salvos1"].get(
        "parameters", {}
    ).get("jsCode", "")
    assert "Rotear operacao1" in gate_salvos_code, (
        "gate não consome a decisão de roteamento"
    )
    assert "cadastro_controle" in gate_salvos_code, (
        "gate não trata a resposta de controle do cadastro"
    )

    print(
        "workflow n8n válido: webhook seguro, áudio efêmero, "
        "foto automática no estoque e resultado privado"
    )


if __name__ == "__main__":
    main()
