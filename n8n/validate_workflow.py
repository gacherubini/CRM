#!/usr/bin/env python3
"""Valida invariantes de segurança do workflow WhatsApp versionado."""

from __future__ import annotations

import json
from pathlib import Path


WORKFLOW = Path(__file__).with_name("workflow-ai-nao-salvos.json")
WEBHOOK_URL = "http://chatbot-api:8000/webhook/mensagem"
WEBHOOK_HEADER = "X-Webhook-Token"
WEBHOOK_TOKEN_PLACEHOLDER = "__CHATBOT_WEBHOOK_TOKEN__"
CHATBOT_TOKEN_PLACEHOLDER = "__CHATBOT_TOKEN__"
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

    gate = next(
        (n for n in data.get("nodes", []) if n.get("name") == "Gate somente nao salvos1"),
        None,
    )
    assert gate is not None, "nó 'Gate somente nao salvos1' sumiu"
    gate_code = gate.get("parameters", {}).get("jsCode", "")
    assert "chat.isSaved === false" not in gate_code, (
        "gate voltou a atender por isSaved===false (regra antiga)"
    )
    assert "chat.chatFound === true" in gate_code, (
        "gate não checa histórico (chatFound)"
    )
    assert "estadoMensagem.bot_ativo !== false" in gate_code, (
        "gate não lê bot_ativo do registrar (handoff furado)"
    )
    assert "tem_saida" in gate_code, (
        "gate não usa tem_saida do registrar (conversa em andamento)"
    )
    assert "atendeLeadVirgem" in gate_code, (
        "gate deve concentrar a tranca em atendeLeadVirgem"
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
    # Simulação humana canônica: endpoint único (lead + pausa + alerta grupo).
    assert "/v1/operacao/solicitacoes-simulacao-humana" in simulation_code, (
        "tool de simulação deve usar o endpoint canônico de simulação humana"
    )
    assert "simulacao_humana_solicitada" in simulation_code, (
        "tool deve só confirmar ao cliente quando o backend aceitar a simulação"
    )
    assert (
        "cpfDigitosEfetivo.length !== 11" in simulation_code
        or "cpfDigitos.length !== 11" in simulation_code
    ), (
        "tool cria lead sem confirmar a presença de CPF"
    )
    assert "numeros-autorizados" not in simulation_code, (
        "alerta de simulação não deve mais listar vendedores no privado"
    )
    assert "/message/sendText/" not in simulation_code, (
        "envio WhatsApp do alerta deve ficar no Chatbot (grupo), não na tool n8n"
    )
    assert "origem.instance" in simulation_code or "const instance = String(origem.instance" in simulation_code, (
        "tool de simulação não lê instance do Extrair1"
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
    system_message_lower = system_message.lower()
    assert "privacidade do resultado" in system_message_lower, (
        "prompt não proíbe a divulgação do resultado"
    )
    assert "nunca crie lead por cumprimento" in system_message_lower, (
        "prompt ainda permite criar lead antes da qualificação"
    )
    assert "o lead só nasce dentro da tool simular" in system_message_lower, (
        "prompt não restringe a criação ao ponto da simulação"
    )
    assert "pausa o bot" in system_message_lower and "simulação humana" in system_message_lower, (
        "prompt deve explicar que simular pausa o bot para o atendente"
    )
    assert "nunca peça placa ao cliente" in system_message_lower, (
        "prompt ainda permite pedir a placa ao cliente"
    )
    assert "texto genérico do botão do anúncio" in system_message_lower, (
        "prompt não contextualiza a resposta ao CTA genérico da Meta"
    )
    assert "nunca diga que há outras unidades/opções" in system_message_lower, (
        "prompt ainda permite inventar alternativas do mesmo modelo"
    )
    assert "consulte o estoque novamente" in system_message_lower, (
        "prompt não recupera a placa internamente quando necessário"
    )
    # Jornada: moto clara → convite dual (fotos ou simulação); recusa sem insistir.
    assert "jornada de catálogo e simulação" in system_message_lower, (
        "prompt oficial deve usar a jornada de catálogo e simulação"
    )
    assert "mande as fotos do catálogo ou prefere" in system_message_lower or (
        "fotos do catálogo ou prefere que eu faça uma simulação" in system_message_lower
    ), (
        "prompt deve oferecer fotos e simulação no mesmo convite (moto única)"
    )
    assert "não exija foto antes" in system_message_lower, (
        "prompt deve permitir simulação sem foto prévia quando o cliente escolher simular"
    )
    assert "recusa e não insistir" in system_message_lower, (
        "prompt deve ter bloco explícito de recusa (não insistir após 'não precisa')"
    )
    assert "não ofereça de novo foto nem simulação" in system_message_lower, (
        "prompt deve proibir re-CTA quando o cliente recusa o convite"
    )
    assert "qual moto você quer simular?" not in system_message_lower, (
        "prompt antigo de simulação imediata não deve permanecer no oficial"
    )
    assert (
        "nunca repita a solicitação desses dados" in system_message_lower
        or "nunca repita a solicitação de dados já recebidos" in system_message_lower
    ), (
        "prompt ainda permite repetir CPF, nascimento e entrada"
    )
    assert "11 dígitos de cpf e uma data de nascimento" in system_message_lower, (
        "prompt não reconhece cpf e nascimento na mesma mensagem (entrada é opcional)"
    )
    assert "cnh (sim ou não) são obrigatórios" in system_message_lower or (
        "cnh (sim ou não) é obrigatória" in system_message_lower
    ), (
        "prompt deve exigir CNH objetiva (sim/não) antes de encaminhar simulação"
    )
    assert "motivo_bloqueio=menor_de_idade" in system_message_lower, (
        "prompt deve tratar bloqueio de menor de 18 anos com a mensagem da tool"
    )
    assert "insista com educação" in system_message_lower or "sim ou não" in system_message_lower, (
        "prompt deve insistir em resposta objetiva de CNH"
    )
    assert "cpf_cliente" in system_message_lower or "cpf mascarado" in system_message_lower, (
        "prompt deve orientar uso do cpf_cliente (não o histórico mascarado)"
    )
    assert "quer dar uma olhada nas motos disponíveis?" in system_message_lower, (
        "primeiro contato ainda oferece simulação antes da escolha"
    )
    assert "certinho" in system_message_lower and "minimalista" in system_message_lower, (
        "prompt não aplica o tom brasileiro minimalista"
    )
    assert "gostaria de seguir com uma simulação?" in system_message_lower, (
        "prompt não bloqueia a frase engessada"
    )
    assert "vitor motos" in system_message_lower and "primeira_mensagem" in system_message, (
        "primeiro contato não apresenta a vitor motos"
    )
    assert "letras minúsculas" in system_message_lower and "não use emojis" in system_message_lower, (
        "prompt não força a conversa leve em minúsculas e sem emojis"
    )
    assert "exclamações" in system_message_lower and "me conta" in system_message_lower, (
        "prompt não bloqueia exclamações e o convite desnecessário"
    )
    assert "oi, [primeiro nome]. aqui é da vitor motos." in system_message_lower, (
        "abertura minimalista da vitor motos ausente"
    )
    assert "veio_de_anuncio" in system_message and "à vista ou no financiamento" in system_message_lower, (
        "prompt não abre a mensagem de anúncio perguntando à vista ou financiamento"
    )
    assert "até 4 fotos do catálogo" in system_message_lower, (
        "prompt não orienta o envio das fotos do catálogo"
    )
    catalog_tool = next(
        (
            node
            for node in data.get("nodes", [])
            if node.get("name") == "enviar_link_catalogo1"
        ),
        None,
    )
    assert catalog_tool is not None, "tool enviar_link_catalogo1 ausente"
    assert catalog_tool.get("type") == "@n8n/n8n-nodes-langchain.toolCode"
    catalog_code = catalog_tool.get("parameters", {}).get("jsCode", "")
    assert "/v1/config/catalogo-bot" in catalog_code, (
        "tool de catálogo deve ler o link configurado no Chatbot/Estoque"
    )
    assert "enviar_link_catalogo" in system_message_lower, (
        "prompt deve mandar o link do catálogo quando o cliente pede para ver as motos"
    )
    assert any(
        item.get("node") == "AI Agent1" and item.get("type") == "ai_tool"
        for group in data.get("connections", {})
        .get("enviar_link_catalogo1", {})
        .get("ai_tool", [])
        for item in group
    ), "enviar_link_catalogo1 precisa estar ligada ao AI Agent"
    stock_node = next(
        (node for node in data.get("nodes", []) if node.get("name") == "consultar_estoque1"),
        None,
    )
    stock_code = stock_node.get("parameters", {}).get("jsCode", "") if stock_node else ""
    assert "veiculos.length === 1" in stock_code and "moto-escolhida:" in stock_code, (
        "consulta específica não preserva a moto escolhida"
    )
    temp_name = "TEMP continuar sem estoque1"
    temp_node = next(
        (node for node in data.get("nodes", []) if node.get("name") == temp_name),
        None,
    )
    assert temp_node is not None, "fallback temporário de estoque ausente"
    assert temp_node.get("type") == "@n8n/n8n-nodes-langchain.toolCode"
    temp_description = temp_node.get("parameters", {}).get("description", "").lower()
    temp_code = temp_node.get("parameters", {}).get("jsCode", "")
    assert "temporário" in temp_description and "não oferece fotos" in temp_description, (
        "fallback temporário deve estar identificado e proibir fotos"
    )
    assert "/v1/operacao/solicitacoes-simulacao-humana" in temp_code, (
        "fallback temporário deve usar o endpoint canônico de simulação humana"
    )
    assert "/v1/simulacoes/solicitar" not in temp_code, (
        "fallback sem veículo real nunca deve chamar o motor de simulação"
    )
    assert "pode_oferecer_fotos: false" in temp_code, (
        "fallback temporário deve bloquear a oferta de fotos"
    )
    assert "numeros-autorizados" not in temp_code and "/message/sendText/" not in temp_code, (
        "fallback não deve enviar alerta privado direto pela Evolution"
    )
    temp_schema = temp_node.get("parameters", {}).get("inputSchema", "")
    assert '"additionalProperties": true' in temp_schema.replace(
        " ", ""
    ) or '"additionalProperties":true' in temp_schema.replace(" ", ""), (
        "schema TEMP deve permitir campos de contexto do n8n (additionalProperties true)"
    )
    assert "simulacao_humana_solicitada" in system_message_lower or "ok:true" in system_message_lower, (
        "prompt deve proibir confirmação de simulação sem sucesso da tool"
    )
    assert temp_name in stock_node.get("parameters", {}).get("description", ""), (
        "consulta de estoque não encaminha resultado vazio ao fallback temporário"
    )
    assert "[temp_estoque_incompleto_inicio]" in system_message_lower
    assert "[temp_estoque_incompleto_fim]" in system_message_lower
    assert temp_name.lower() in system_message_lower
    temp_connections = data.get("connections", {}).get(temp_name, {})
    assert any(
        item.get("node") == "AI Agent1" and item.get("type") == "ai_tool"
        for group in temp_connections.get("ai_tool", [])
        for item in group
    ), "fallback temporário não está conectado ao AI Agent"
    memory_node = next(
        (node for node in data.get("nodes", []) if node.get("name") == "Memoria da conversa1"),
        None,
    )
    assert memory_node.get("parameters", {}).get("contextWindowLength", 0) >= 20, (
        "memória curta pode perder a moto antes da chegada dos dados"
    )

    responder_node = next(
        (node for node in data.get("nodes", []) if node.get("name") == "Responder WhatsApp1"),
        None,
    )
    responder_body = responder_node.get("parameters", {}).get("jsonBody", "") if responder_node else ""
    assert "toLocaleLowerCase('pt-BR')" in responder_body and "acao === 'cliente'" in responder_body, (
        "saída do cliente não garante letras minúsculas"
    )
    assert "Extended_Pictographic" in responder_body and "replace(/!+/g, '.')" in responder_body, (
        "saída do cliente não remove emojis e exclamações"
    )
    assert "me conta" in responder_body, "saída do cliente não remove o bordão rejeitado"
    agent_text = agent_node.get("parameters", {}).get("text", "")
    assert all(field in agent_text for field in (
        "nome_whatsapp", "primeira_mensagem", "veio_de_anuncio",
        "titulo_anuncio", "descricao_anuncio",
    )), "contexto do primeiro contato/anúncio não chega ao Agent"

    simulation_schema = json.loads(
        simulation_node.get("parameters", {}).get("inputSchema", "{}")
    )
    assert "placa" not in simulation_schema.get("required", []), (
        "schema ainda obriga o modelo a obter placa do cliente"
    )
    assert "anyOf" not in simulation_schema, (
        "schema não pode bloquear a recuperação automática da moto escolhida"
    )
    assert "moto-escolhida:" in simulation_code and "$getWorkflowStaticData('global')" in simulation_code, (
        "tool de simulação não recupera a moto escolhida"
    )
    assert "precisa_escolher_moto: true" in simulation_code, (
        "tool não bloqueia simulação sem escolha de moto"
    )
    assert "a moto ainda não foi escolhida" in simulation_code, (
        "fallback da tool não pede escolha de moto no catálogo"
    )
    assert "conhecer melhor" in simulation_code or "não repita dados" in simulation_code, (
        "fallback da tool ainda permite repetir CPF, nascimento e entrada"
    )
    assert "dataBr" in simulation_code and (
        "cpf: cpfDigitosEfetivo" in simulation_code or "cpf: cpfDigitos" in simulation_code
    ), (
        "tool não normaliza os dados enviados na mesma mensagem"
    )
    assert "cpf-cliente:" in simulation_code, (
        "tool deve recuperar CPF capturado quando o histórico está mascarado"
    )
    assert "temValorEstoque" in simulation_code and "categoriaValida" in simulation_code, (
        "tool não implementa fallback interno para estoque sem placa"
    )
    assert (
        "não peça cpf, nascimento, entrada ou placa agora" in simulation_code
        or "não fale em simulação e não peça cpf" in simulation_code
    ), (
        "tool não bloqueia coleta de dados antes da escolha do veículo"
    )
    assert "certo, já tenho seus dados. vou encaminhar pro setor de simulação" in simulation_code, (
        "confirmação minimalista da simulação está ausente"
    )
    assert "faltando.push('cnh')" in simulation_code or 'faltando.push("cnh")' in simulation_code, (
        "tool de simulação deve exigir CNH objetiva antes do envio"
    )
    assert "menor_de_idade" in simulation_code and "menores de 18 anos" in simulation_code, (
        "tool de simulação deve bloquear menor de 18 anos com mensagem fixa"
    )
    assert "resp.bloqueado" in simulation_code, (
        "tool deve repassar bloqueios do backend (idade/CNH) ao Agent"
    )
    assert "chamar um vendedor" not in simulation_code and "pra trazer" not in simulation_code, (
        "resposta ao cliente ainda promete chamar vendedor"
    )
    assert "certinho!" not in simulation_code, "confirmação ainda usa exclamação"
    assert "telefone" not in simulation_schema.get("required", []), (
        "schema não deve pedir telefone que já veio do webhook"
    )
    assert "interesse" in simulation_schema.get("properties", {}), (
        "schema deve registrar o veículo escolhido no lead qualificado"
    )
    assert "origem.telefone" in simulation_code and "input.telefone" not in simulation_code, (
        "telefone do lead deve vir do webhook, não do modelo"
    )
    for tool_name in ("registrar_lead1", "registrar_consentimento1"):
        assert tool_name not in data.get("connections", {}), (
            f"{tool_name} não pode ficar disponível antes da simulação"
        )

    handoff_node = next(
        (node for node in data.get("nodes", []) if node.get("name") == "solicitar_handoff1"),
        None,
    )
    assert handoff_node is not None, "tool solicitar_handoff1 ausente"
    handoff_code = handoff_node.get("parameters", {}).get("jsCode", "")
    handoff_schema = json.loads(handoff_node.get("parameters", {}).get("inputSchema", "{}"))
    assert "origem.telefone" in handoff_code and "input.telefone" not in handoff_code, (
        "telefone do handoff deve vir do webhook, não do modelo"
    )
    assert "/estado" in handoff_code and "bot_ativo: false" in handoff_code, (
        "handoff não pausa o bot"
    )
    assert "/v1/operacao/numeros-autorizados" in handoff_code, (
        "handoff não consulta o vendedor ativo"
    )
    assert (
        "/message/sendText/' + encodeURIComponent(instance)" in handoff_code
        or "/message/sendText/\" + encodeURIComponent(instance)" in handoff_code
    ), "handoff não avisa o vendedor pela Evolution com instance do webhook"
    assert "instance: instance" in handoff_code or "instance: instance || null" in handoff_code, (
        "handoff deve enviar instance no PATCH /estado (multi-WA)"
    )
    assert "https://app2037.fly.dev/app/conversas/" in handoff_code, (
        "handoff não inclui o link seguro do CRM"
    )
    assert "certo. vou encaminhar seu atendimento." in handoff_code, (
        "resposta curta do handoff está ausente"
    )
    assert "telefone" not in handoff_schema.get("properties", {}), (
        "schema do handoff ainda deixa o modelo escolher o telefone"
    )
    assert "depois da tool solicitar_handoff" in system_message_lower, (
        "prompt não fixa a resposta após o handoff"
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
    assert "grupo_jid" in vehicle_create_code and "origem.grupoJid" in vehicle_create_code, (
        "cadastro deve encaminhar o grupo real extraído do webhook"
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
    # n8n ToolCode injeta o item pai (telefone, remoteJid, acao, toolCallId…) no
    # input da tool. additionalProperties:false quebra o cadastro em runtime.
    # A segurança fica no jsCode: só repassa campos conhecidos + telefone do webhook.
    assert '"additionalProperties": true' in vehicle_create_schema.replace(
        " ", ""
    ) or '"additionalProperties":true' in vehicle_create_schema.replace(" ", ""), (
        "schema do cadastro deve permitir campos de contexto do n8n (additionalProperties true)"
    )
    assert "input.tipo" in vehicle_create_code and "input.placa" in vehicle_create_code, (
        "jsCode do cadastro deve ler só campos conhecidos do input"
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
    assert "/v1/estoque/buscar" in photo_code and "String(item?.id || '') === veiculoId" in photo_code, (
        "tool não resolve as fotos pelo id confiável no estoque tenant-scoped"
    )
    assert "slice(0, 4)" in photo_code and "for (const midia of midias)" in photo_code, (
        "tool não envia até quatro fotos do catálogo"
    )
    assert (
        "/message/sendMedia/' + encodeURIComponent(instance)" in photo_code
        or "/message/sendMedia/\" + encodeURIComponent(instance)" in photo_code
    ), "tool não envia mídia pela Evolution com instance do webhook"
    assert "mediatype: 'image'" in photo_code and "media: mediaUrl.toString()" in photo_code, (
        "payload de imagem da Evolution incompleto"
    )
    assert "fotos_enviadas" in photo_code and "foto da moto" in photo_code, (
        "tool não confirma o lote de fotos com legenda minimalista"
    )
    assert "👇" not in photo_code, "legenda de foto ainda usa emoji"
    assert '"veiculo_id"' in photo_schema and '"url"' not in photo_schema, (
        "modelo deve informar somente veiculo_id, nunca URL de mídia"
    )
    assert "origem.destino" in photo_code and "input.destino" not in photo_code, (
        "destino da foto deve vir do webhook, não do modelo"
    )
    system_prompt = agent_node.get("parameters", {}).get("options", {}).get("systemMessage", "")
    assert "enviar_foto_veiculo" in system_prompt and "envie no próprio whatsapp" in system_prompt, (
        "prompt não prioriza o envio da foto no próprio WhatsApp"
    )
    photo_connections = data.get("connections", {}).get("enviar_foto_veiculo1", {})
    assert any(
        item.get("node") == "AI Agent1" and item.get("type") == "ai_tool"
        for group in photo_connections.get("ai_tool", [])
        for item in group
    ), "tool de foto não está conectada ao AI Agent"

    nodes_by_name = {node.get("name"): node for node in data.get("nodes", [])}
    assert len(nodes_by_name) == 31, (
        "workflow deve ter 31 nós (inclui debounce, juiz, fallback e link catálogo)"
    )
    removidos = {
        "E audio1", "Transcrever audio1", "Aplicar transcricao1",
        "registrar_consentimento1", "registrar_lead1", "consultar_por_placa1",
        "E primeira mensagem1", "Aguardar 60 segundos1",
    }
    assert removidos.isdisjoint(nodes_by_name), "workflow ainda contém nós removidos"

    extract_code = nodes_by_name["Extrair1"].get("parameters", {}).get("jsCode", "")
    assert "b.instance" in extract_code and "__INSTANCE__" not in extract_code, (
        "Extrair1 deve usar body.instance do webhook, sem placeholder fixo"
    )
    assert "if (!instance) return []" in extract_code, (
        "Extrair1 deve rejeitar evento sem instance (multi-WA)"
    )
    assert "audioMessage" in extract_code and "if (audio) return []" in extract_code, (
        "áudio deve ser ignorado imediatamente na entrada"
    )
    assert "ehAudio" not in extract_code and "audioMimeType" not in extract_code, (
        "extração ainda transporta dados de áudio desnecessários"
    )
    assert "imageMessage" in extract_code and "ehImagem" in extract_code, (
        "extração não reconhece foto recebida"
    )
    assert "Boolean(imagem) && !fromMe" in extract_code, (
        "eco de imagem enviada pela própria loja entraria como upload"
    )
    assert "(ehGrupo && fromMe)" in extract_code, (
        "eco fromMe no grupo deve ser descartado na entrada — evita loop de menu"
    )
    assert "ehGrupo" in extract_code and "@g.us" in extract_code, (
        "extração não reconhece mensagens do grupo de estoque"
    )
    assert "participantAlt" in extract_code and "ehImagemEstoque" in extract_code, (
        "extração não separa participante e fotos do grupo"
    )
    assert all(field in extract_code for field in (
        "veioDeAnuncio", "anuncioTitulo", "anuncioDescricao", "externalAdReply",
    )), "extração não reconhece o contexto da mensagem de anúncio"
    assert "data.messageTimestamp" in extract_code, (
        "Extrair1 não lê o horário original da mensagem Evolution"
    )
    assert "MAX_MESSAGE_AGE_SECONDS = 300" in extract_code, (
        "Extrair1 deve bloquear replay com mais de 5 minutos"
    )
    assert "messageAgeSeconds == null" in extract_code, (
        "evento sem timestamp deve falhar fechado"
    )

    connections = data.get("connections", {})

    # Debounce só no caminho do cliente: Wait → confirma última entrada → IA → WhatsApp.
    # O menu da equipe continua sem espera.
    wait_node = nodes_by_name.get("Aguardar 40s cliente1")
    assert wait_node is not None, "falta nó Aguardar 40s cliente1 no caminho do cliente"
    assert wait_node.get("type") == "n8n-nodes-base.wait"
    wait_params = wait_node.get("parameters") or {}
    assert wait_params.get("resume") == "timeInterval"
    assert int(wait_params.get("amount") or 0) == 40
    assert str(wait_params.get("unit") or "") in {"seconds", "second"}
    verify_name = "Verificar mensagem mais recente1"
    debounce_gate_name = "Gate resposta mais recente1"
    verify_node = nodes_by_name.get(verify_name)
    assert verify_node is not None, "falta juiz HTTP da última mensagem"
    verify_params = verify_node.get("parameters") or {}
    assert "/pode-responder" in verify_params.get("url", "")
    assert "provider_message_id" in verify_params.get("jsonBody", "")
    assert "Extrair1" in verify_params.get("jsonBody", "")
    verify_headers = {
        header.get("name"): header.get("value")
        for header in verify_params.get("headerParameters", {}).get("parameters", [])
    }
    assert verify_headers.get("Authorization") == f"Bearer {CHATBOT_TOKEN_PLACEHOLDER}"

    debounce_gate = nodes_by_name.get(debounce_gate_name)
    assert debounce_gate is not None, "falta gate que elimina mensagem superada"
    debounce_code = debounce_gate.get("parameters", {}).get("jsCode", "")
    assert "pode_responder !== true" in debounce_code
    assert "Gate somente nao salvos1" in debounce_code

    assert connections.get("Aguardar 40s cliente1", {}).get("main", [[]])[0][0][
        "node"
    ] == verify_name, "Wait deve consultar se a mensagem ainda é a mais recente"
    assert connections.get(verify_name, {}).get("main", [[]])[0][0]["node"] == (
        debounce_gate_name
    )
    assert connections.get(debounce_gate_name, {}).get("main", [[]])[0][0][
        "node"
    ] == "AI Agent1"
    assert connections.get("AI Agent1", {}).get("main", [[]])[0][0]["node"] == (
        "Responder WhatsApp1"
    ), "AI Agent deve responder somente depois do debounce"
    se_ctrl = connections.get("Se resposta controle1", {}).get("main", [])
    assert se_ctrl[0][0]["node"] == "Responder WhatsApp1"
    assert se_ctrl[1][0]["node"] == "Aguardar 40s cliente1"

    assert connections.get("Extrair1", {}).get("main", [[]])[0][0].get("node") == "E imagem de estoque1"
    imagem_ramos = connections.get("E imagem de estoque1", {}).get("main", [])
    assert imagem_ramos[0][0].get("node") == "Salvar foto no estoque1"
    assert imagem_ramos[1][0].get("node") == "E grupo de estoque1"
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
    assert "grupo_jid" in imagem_body and "grupoJid" in imagem_body, (
        "ingestão da foto não informa o grupo ao backend"
    )
    assert "base64" not in imagem_body and "media:" not in imagem_body, (
        "n8n não deve transportar ou guardar o binário da foto"
    )
    assert connections.get("Salvar foto no estoque1", {}).get("main", [[]])[0][0].get("node") == "Foto deve responder1"
    assert connections.get("Foto deve responder1", {}).get("main", [[]])[0][0].get("node") == "Responder cadastro de foto1", (
        "foto ignorada pode gerar resposta indevida"
    )
    assert "audioFallback" not in agent_node.get("parameters", {}).get("text", ""), (
        "prompt ainda contém fallback de áudio"
    )
    for gate_name in ("Gate handoff e duplicidade1", "Gate somente nao salvos1"):
        gate_code = nodes_by_name[gate_name].get("parameters", {}).get("jsCode", "")
        assert "Aplicar transcricao1" not in gate_code, (
            f"{gate_name} ainda depende do ramo removido de áudio"
        )

    # Roteamento de operação: privado e grupo usam a mesma validação tenant-scoped.
    rota_nodes = [
        node
        for node in data.get("nodes", [])
        if node.get("parameters", {}).get("url") == ROTEAMENTO_URL
    ]
    assert len(rota_nodes) == 2, "esperados roteamentos separados para privado e grupo"
    for rota_node in rota_nodes:
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
    grupo_rota_body = nodes_by_name["Rotear grupo de estoque1"]["parameters"]["jsonBody"]
    assert "grupo_jid" in grupo_rota_body and "grupoJid" in grupo_rota_body, (
        "roteamento do grupo não encaminha o JID"
    )
    assert (
        connections.get("Rotear operacao1", {}).get("main", [[]])[0][0].get("node")
        == "Gate somente nao salvos1"
    ), "roteamento não alimenta o gate"
    # findChats vazio não pode matar o fluxo: alwaysOutputData + normalizador
    consultar = nodes_by_name["Consultar contato na Evolution1"]
    assert consultar.get("alwaysOutputData") is True, (
        "Consultar contato deve alwaysOutputData (lista vazia não encerra o fluxo)"
    )
    assert (
        connections.get("Consultar contato na Evolution1", {})
        .get("main", [[]])[0][0]
        .get("node")
        == "Normalizar isSaved Evolution1"
    ), "Consultar contato deve alimentar o normalizador de isSaved"
    assert (
        connections.get("Normalizar isSaved Evolution1", {})
        .get("main", [[]])[0][0]
        .get("node")
        == "Rotear operacao1"
    ), "normalizador deve alimentar o roteamento privado"
    normalize_code = nodes_by_name["Normalizar isSaved Evolution1"].get(
        "parameters", {}
    ).get("jsCode", "")
    # Vazio/desconhecido = null; o gate decide fail-open (não matar lead por lista vazia).
    assert "isSaved = null" in normalize_code or "isSaved=null" in normalize_code.replace(
        " ", ""
    ), "normalizador deve defaultar isSaved=null quando findChats vem vazio"
    assert "chatFound" in normalize_code, "normalizador deve expor chatFound"
    rota_body_priv = nodes_by_name["Rotear operacao1"]["parameters"].get("jsonBody", "")
    assert "Normalizar isSaved Evolution1" in rota_body_priv, (
        "roteamento privado deve ler is_saved do normalizador"
    )
    gate_salvos_code = nodes_by_name["Gate somente nao salvos1"].get(
        "parameters", {}
    ).get("jsCode", "")
    assert "Normalizar isSaved Evolution1" in gate_salvos_code, (
        "gate deve usar isSaved normalizado (não o raw do findChats)"
    )
    assert "$input.first()" in gate_salvos_code, "gate não consome a decisão de roteamento"
    assert "cadastro_controle" in gate_salvos_code, (
        "gate não trata a resposta de controle do cadastro"
    )
    assert "operacao_controle" in gate_salvos_code or "output" in gate_salvos_code, (
        "gate deve preparar output de menu/controle sem LLM"
    )
    # Menu/controle não passa pelo Agent
    assert (
        connections.get("Gate somente nao salvos1", {}).get("main", [[]])[0][0].get("node")
        == "Se resposta controle1"
    ), "gate deve alimentar o IF de resposta controle"
    if_true = connections.get("Se resposta controle1", {}).get("main", [[], []])
    assert if_true and if_true[0][0].get("node") == "Responder WhatsApp1", (
        "controle deve ir direto ao WhatsApp"
    )
    assert len(if_true) > 1 and if_true[1][0].get("node") == "Aguardar 40s cliente1", (
        "mensagem de cliente deve passar pelo debounce antes do Agent"
    )
    assert "estadoMensagem.primeira_mensagem === true" in gate_salvos_code, (
        "sinal de primeira mensagem não chega ao Agent"
    )
    grupo_ramos = connections.get("E grupo de estoque1", {}).get("main", [[], []])
    assert grupo_ramos[0][0].get("node") == "Rotear grupo de estoque1"
    assert grupo_ramos[1][0].get("node") == "Registrar mensagem e ler handoff1"
    assert (
        connections.get("Rotear grupo de estoque1", {}).get("main", [[]])[0][0].get("node")
        == "Gate somente nao salvos1"
    )
    saida_ramos = connections.get("E resposta de grupo1", {}).get("main", [[], []])
    assert not saida_ramos[0], "resposta do grupo não deve ser registrada como conversa de cliente"
    assert saida_ramos[1][0].get("node") == "Registrar saida do bot1"

    # multi-WA: um workflow, instance sempre dinâmica nas URLs Evolution
    for name in (
        "Responder WhatsApp1",
        "Responder cadastro de foto1",
        "Consultar contato na Evolution1",
    ):
        url = nodes_by_name[name]["parameters"].get("url", "")
        assert "encodeURIComponent" in url and "Extrair1" in url, (
            f"{name}: URL Evolution deve ser expressão com instance do Extrair1"
        )
        assert "__INSTANCE__" not in url, f"{name}: ainda usa __INSTANCE__ fixo"
    rota_body = nodes_by_name["Rotear operacao1"]["parameters"].get("jsonBody", "")
    assert "instance: o.instance" in rota_body and "__INSTANCE__" not in rota_body, (
        "roteamento deve enviar instance do webhook, não placeholder fixo"
    )
    assert "__INSTANCE__" not in json.dumps(data, ensure_ascii=False), (
        "workflow de produção não pode depender de __INSTANCE__ fixo"
    )

    print(
        "workflow n8n válido: 31 nós, replay >5min bloqueado, debounce pela última entrada, "
        "fallback temporário sem fotos, multi-WA instance dinâmica, áudio ignorado, "
        "webhook seguro e resultado privado"
    )


if __name__ == "__main__":
    main()
