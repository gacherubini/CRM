#!/usr/bin/env python3
"""Gera `workflow-cloud.json` como fork do `workflow-ai-nao-salvos.json`.

A spec §5.9 é explícita: *"O `n8n-cloud` é **cópia do fluxo atual**
(`workflow-ai-nao-salvos.json`) trocando Evolution por Graph API — não um bot
novo"*. Um fork escrito à mão vira outro bot na primeira divergência, então o
fork é **gerado**: o AI Agent, o Gemini, a memória e as ferramentas saem daqui
byte-a-byte iguais aos do Modo 1, e mudança no Modo 1 se propaga rodando de novo.

Rode da raiz do repo:

    python n8n/fork_cloud_workflow.py

O que muda em relação ao Modo 1, e por quê:

- **Entrada**: webhook da Evolution → dois webhooks da Meta (GET de verificação e
  POST de inbound com `rawBody`, §6.1). O POST repassa o **corpo cru** ao
  `chatbot-api`, que confere a assinatura (só fecha sobre os bytes originais),
  deduplica por `wamid`, persiste e devolve `mensagens` já normalizadas.
- **Saída**: `sendText` da Evolution → `POST /v1/operacao/responder` no chatbot.
  Não vai direto ao Graph de propósito: a §6.2 põe o segredo da Meta no chatbot
  e o validador recusa qualquer vestígio dele aqui dentro.
- **Some o gate virgem/salvo** (`Consultar contato na Evolution`,
  `Normalizar isSaved`, `Gate somente nao salvos`, `Rotear operacao`): a §5.9 diz
  que ele "não se aplica no Modo 2 da mesma forma" — a central é só-bot.
- **Some o fluxo do grupo de estoque** (foto, cadastro): grupo é Modo 1.
- **Some `Registrar mensagem e ler handoff`**: no Modo 2 quem registra a entrada
  é o `/webhook/cloud`; repetir aqui gravaria a mensagem duas vezes.
- **`solicitar_handoff` reescrito**: no Modo 1 ele avisa a equipe pela Evolution;
  no Modo 2 ele abre o **rodízio** (`/v1/operacao/handoff-humano`, §5.2).

Herdado sem discussão, como manda a §5.9: debounce de 40 s (só a última
mensagem), replay >5 min bloqueado, intake + simulação no Motor, atraso anti-ban.

O nó normalizador se chama `Extrair1` de propósito: as ferramentas referenciam
`$('Extrair1')` no código delas, e renomear obrigaria a reescrever cada uma —
que é justamente como um fork deixa de ser cópia.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BASE = RAIZ / "workflow-ai-nao-salvos.json"
SAIDA = RAIZ / "workflow-cloud.json"

WORKFLOW_ID = "wCloudMeta0001"
CHATBOT = "http://chatbot-api:8000"

# Herdados byte-a-byte do Modo 1.
HERDADOS = [
    "Aguardar 40s cliente1",
    "Verificar mensagem mais recente1",
    "Gate resposta mais recente1",
    "AI Agent1",
    "Google Gemini Chat Model1",
    "Memoria da conversa1",
    "consultar_estoque1",
    "simular1",
    "TEMP continuar sem estoque1",
    "enviar_link_catalogo1",
    "Atraso anti-ban1",
]

# Ficam de fora, com o motivo — para ninguém "consertar" isso por engano depois.
DESCARTADOS = {
    "Webhook1": "entrada é da Meta, não da Evolution",
    "Extrair1": "reescrito para o formato normalizado do /webhook/cloud",
    "E imagem de estoque1": "fluxo do grupo de estoque é Modo 1",
    "Salvar foto no estoque1": "fluxo do grupo de estoque é Modo 1",
    "Foto deve responder1": "fluxo do grupo de estoque é Modo 1",
    "Responder cadastro de foto1": "fluxo do grupo de estoque é Modo 1",
    "E grupo de estoque1": "fluxo do grupo de estoque é Modo 1",
    "Rotear grupo de estoque1": "fluxo do grupo de estoque é Modo 1",
    "E resposta de grupo1": "fluxo do grupo de estoque é Modo 1",
    "cadastrar_veiculo1": "cadastro de veículo é do grupo de estoque (Modo 1)",
    "enviar_foto_veiculo1": (
        "envia mídia pela Evolution; a central Cloud precisaria de envio de "
        "imagem pelo Graph, que ainda não existe. enviar_link_catalogo cobre "
        "'quero ver as motos' sem deixar o bot mudo"
    ),
    "Consultar contato na Evolution1": "gate virgem/salvo não se aplica (§5.9)",
    "Normalizar isSaved Evolution1": "gate virgem/salvo não se aplica (§5.9)",
    "Rotear operacao1": "roteamento por isSaved é do Modo 1",
    "Se resposta controle1": "sem roteamento de operação, não há resposta de controle",
    "Registrar saida do bot1": "/v1/operacao/responder já registra a saída",
    "Responder WhatsApp1": "reescrito para responder pelo chatbot (§6.2)",
    "solicitar_handoff1": "reescrito para abrir o rodízio (§5.2)",
}

# --- nós novos ---------------------------------------------------------------

EXTRAIR_JS = """
// Normaliza o que o /webhook/cloud devolveu para o formato que as ferramentas
// do agente esperam. Os nomes de campo sao os do Modo 1 de proposito: as tools
// referenciam $('Extrair1').first().json.telefone / .instance / .destino, e
// mudar isso obrigaria a reescrever cada ferramenta.
const resposta = $input.first().json || {};
const mensagens = Array.isArray(resposta.mensagens) ? resposta.mensagens : [];
// Sem mensagem do cliente nao ha o que o agente faca: clique de vendedor,
// status de entrega e lead ja travado se resolvem dentro do chatbot.
if (!mensagens.length) return [];
return mensagens.map((m) => ({
  json: {
    instance: String(m.phone_number_id || ''),
    telefone: String(m.telefone || ''),
    destino: String(m.telefone || ''),
    texto: String(m.texto || ''),
    providerMessageId: String(m.wamid || ''),
    fromMe: false,
    loja_id: m.loja_id || null,
    conversa_id: m.conversa_id || null,
    meta_ad_id: m.referral_ad_id || null,
    historicoRecente: m.historico_recente || '',
    historico_recente: m.historico_recente || '',
  },
}));
""".strip()

# Duas pontes. O `AI Agent1` e o `Gate resposta mais recente1` vem do Modo 1
# byte-a-byte e citam nos que nao existem aqui — e manter esses dois identicos e
# o proposito do fork. Em vez de reescrever o agente (que e o que transformaria
# copia em bot novo), o fork oferece nos com o mesmo NOME e o mesmo formato de
# saida. A topologia que o Modo 1 pressupoe continua valendo.

PONTE_REGISTRO_JS = """
// Ponte de nome: no Modo 2 quem registra a entrada e o /webhook/cloud (a
// assinatura da Meta so fecha sobre o corpo cru, entao nao da pra registrar
// aqui). Este no existe porque o AI Agent1, herdado byte-a-byte, le
// $('Registrar mensagem e ler handoff1').first().json.historico_recente.
const e = $input.first().json || {};
return [{ json: { historico_recente: e.historico_recente || '', bot_ativo: true } }];
""".strip()

PONTE_GATE_JS = """
// Ponte de nome: a spec 5.9 diz que o gate virgem/salvo "nao se aplica no Modo 2
// da mesma forma" — a central e so-bot, todo inbound de cliente e conversa. O no
// existe porque o Gate resposta mais recente1, herdado byte-a-byte, devolve
// $('Gate somente nao salvos1').first().json como a origem do turno.
const e = $('Extrair1').first().json || {};
return [{ json: { ...e, acao: 'cliente' } }];
""".strip()

SOLICITAR_HANDOFF_JS = """
// Modo 2: o handoff NAO avisa grupo (nao existe grupo) — ele abre o rodizio.
// Terceiro gatilho da spec 5.2, "cliente pediu humano". Sem CPF/nascimento de
// proposito: a 5.2 diz que este gatilho pode vir antes da simulacao.
const input = typeof query === 'string' ? { motivo: query } : (query || {});
const origem = $('Extrair1').first().json;
const telefone = String(origem.telefone || '').replace(/\\D/g, '');
const motivo = String(input.motivo || 'cliente pediu atendimento humano').trim().slice(0, 120);
if (!telefone) return JSON.stringify({ mensagem: 'nao consegui identificar a conversa para encaminhar.' });

try {
  await helpers.httpRequest({
    method: 'PATCH',
    url: 'CHATBOT_BASE/v1/conversas/' + encodeURIComponent(telefone) + '/estado',
    headers: { Authorization: 'Bearer __CHATBOT_TOKEN__', 'Content-Type': 'application/json' },
    body: { bot_ativo: false, instance: String(origem.instance || '') || null },
    json: true,
    timeout: 10000,
  });
} catch (_) {
  return JSON.stringify({ mensagem: 'nao consegui encaminhar agora. tente novamente em alguns instantes.' });
}

try {
  const r = await helpers.httpRequest({
    method: 'POST',
    url: 'CHATBOT_BASE/v1/operacao/handoff-humano',
    headers: { Authorization: 'Bearer __CHATBOT_TOKEN__', 'Content-Type': 'application/json' },
    body: { telefone, motivo },
    json: true,
    timeout: 15000,
  });
  if (r && r.acionado === false) {
    return JSON.stringify({ mensagem: 'ja avisei a equipe. em instantes alguem te chama.' });
  }
} catch (_) {
  // O bot ja esta pausado; o worker do rodizio ainda pode pegar o lead.
  return JSON.stringify({ mensagem: 'ja avisei a equipe. em instantes alguem te chama.' });
}

return JSON.stringify({ mensagem: 'pronto, ja estou chamando um vendedor pra falar com voce.' });
""".strip().replace("CHATBOT_BASE", CHATBOT)


def novos_nos() -> list[dict]:
    return [
        {
            "parameters": {
                "httpMethod": "GET",
                "path": "whatsapp-cloud",
                "responseMode": "lastNode",
                "options": {},
            },
            "id": "webhook-get",
            "name": "Meta verificacao",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [-460, -160],
            "webhookId": "whatsapp-cloud",
        },
        {
            "parameters": {
                "method": "GET",
                "url": f"{CHATBOT}/webhook/cloud",
                "sendQuery": True,
                "specifyQuery": "keypair",
                "queryParameters": {
                    "parameters": [
                        {"name": "hub.mode", "value": "={{ $json.query['hub.mode'] }}"},
                        {
                            "name": "hub.verify_token",
                            "value": "={{ $json.query['hub.verify_token'] }}",
                        },
                        {
                            "name": "hub.challenge",
                            "value": "={{ $json.query['hub.challenge'] }}",
                        },
                    ]
                },
                "options": {
                    "response": {
                        "response": {"neverError": True, "responseFormat": "text"}
                    }
                },
            },
            "id": "http-get",
            "name": "Repassar verificacao",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [-240, -160],
        },
        {
            "parameters": {
                "httpMethod": "POST",
                "path": "whatsapp-cloud",
                "responseMode": "onReceived",
                "responseCode": 200,
                "options": {"rawBody": True},
            },
            "id": "webhook-post",
            "name": "Meta inbound",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [-460, 40],
            "webhookId": "whatsapp-cloud",
        },
        {
            "parameters": {
                "method": "POST",
                "url": f"{CHATBOT}/webhook/cloud",
                "sendHeaders": True,
                "specifyHeaders": "keypair",
                "headerParameters": {
                    "parameters": [
                        {
                            "name": "X-Hub-Signature-256",
                            "value": "={{ $json.headers['x-hub-signature-256'] }}",
                        },
                        {"name": "X-Webhook-Token", "value": "__CHATBOT_WEBHOOK_TOKEN__"},
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "contentType": "raw",
                "rawContentType": "application/json",
                "body": "={{ $json.body }}",
                "options": {"response": {"response": {"neverError": True}}},
            },
            "id": "http-post",
            "name": "Repassar inbound",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [-240, 40],
        },
        {
            "parameters": {"jsCode": EXTRAIR_JS},
            "id": "extrair-cloud",
            "name": "Extrair1",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-20, 40],
        },
        {
            "parameters": {"jsCode": PONTE_REGISTRO_JS},
            "id": "ponte-registro",
            "name": "Registrar mensagem e ler handoff1",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-20, 200],
        },
        {
            "parameters": {"jsCode": PONTE_GATE_JS},
            "id": "ponte-gate",
            "name": "Gate somente nao salvos1",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-20, 360],
        },
        {
            "parameters": {
                "method": "POST",
                "url": f"{CHATBOT}/v1/operacao/responder",
                "sendHeaders": True,
                "specifyHeaders": "keypair",
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": "Bearer __CHATBOT_TOKEN__"},
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                # Mesma higienizacao do Modo 1 (minusculas, sem emoji, sem "!"),
                # que la vive no jsonBody do Responder WhatsApp1.
                "jsonBody": (
                    "={{ (() => { const texto = String($json.output || ''); "
                    "const limpo = texto.toLocaleLowerCase('pt-BR')"
                    ".replace(/[\\p{Extended_Pictographic}\\uFE0F\\u200D]/gu, '')"
                    ".replace(/!+/g, '.')"
                    ".replace(/\\bme conta[:,]?\\s*/g, '')"
                    ".replace(/\\s{2,}/g, ' ')"
                    ".replace(/\\s+([.,?])/g, '$1').trim(); "
                    "return { telefone: $('Extrair1').first().json.telefone, text"
                    "o: limpo }; })() }}"
                ),
                "options": {"timeout": 30000},
            },
            "id": "responder-cloud",
            "name": "Responder WhatsApp1",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [860, 40],
        },
    ]


CONEXOES = {
    "Meta verificacao": {"main": [[{"node": "Repassar verificacao", "type": "main", "index": 0}]]},
    "Meta inbound": {"main": [[{"node": "Repassar inbound", "type": "main", "index": 0}]]},
    "Repassar inbound": {"main": [[{"node": "Extrair1", "type": "main", "index": 0}]]},
    "Extrair1": {
        "main": [[{"node": "Registrar mensagem e ler handoff1", "type": "main", "index": 0}]]
    },
    "Registrar mensagem e ler handoff1": {
        "main": [[{"node": "Gate somente nao salvos1", "type": "main", "index": 0}]]
    },
    "Gate somente nao salvos1": {
        "main": [[{"node": "Aguardar 40s cliente1", "type": "main", "index": 0}]]
    },
    "Aguardar 40s cliente1": {
        "main": [[{"node": "Verificar mensagem mais recente1", "type": "main", "index": 0}]]
    },
    "Verificar mensagem mais recente1": {
        "main": [[{"node": "Gate resposta mais recente1", "type": "main", "index": 0}]]
    },
    "Gate resposta mais recente1": {"main": [[{"node": "AI Agent1", "type": "main", "index": 0}]]},
    "AI Agent1": {"main": [[{"node": "Atraso anti-ban1", "type": "main", "index": 0}]]},
    "Atraso anti-ban1": {"main": [[{"node": "Responder WhatsApp1", "type": "main", "index": 0}]]},
    "Google Gemini Chat Model1": {
        "ai_languageModel": [[{"node": "AI Agent1", "type": "ai_languageModel", "index": 0}]]
    },
    "Memoria da conversa1": {
        "ai_memory": [[{"node": "AI Agent1", "type": "ai_memory", "index": 0}]]
    },
    **{
        tool: {"ai_tool": [[{"node": "AI Agent1", "type": "ai_tool", "index": 0}]]}
        for tool in ("consultar_estoque1", "simular1", "solicitar_handoff1",
                     "TEMP continuar sem estoque1", "enviar_link_catalogo1")
    },
}


def main() -> None:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    por_nome = {n["name"]: n for n in base["nodes"]}

    faltando = [n for n in HERDADOS if n not in por_nome]
    if faltando:
        sys.exit(f"ERRO: o Modo 1 não tem mais estes nós (renomeados?): {faltando}")

    nos = [json.loads(json.dumps(por_nome[n])) for n in HERDADOS]

    # A única ferramenta que muda de conteúdo: no Modo 1 avisa a equipe pela
    # Evolution, aqui abre o rodízio.
    handoff = json.loads(json.dumps(por_nome["solicitar_handoff1"]))
    handoff["parameters"]["jsCode"] = SOLICITAR_HANDOFF_JS
    nos.append(handoff)

    nos.extend(novos_nos())

    # Reposiciona a esteira para o editor não virar espaguete.
    trilha = [
        "Aguardar 40s cliente1", "Verificar mensagem mais recente1",
        "Gate resposta mais recente1", "AI Agent1", "Atraso anti-ban1",
    ]
    for i, nome in enumerate(trilha):
        for n in nos:
            if n["name"] == nome:
                n["position"] = [200 + i * 165, 40]

    workflow = {
        "id": WORKFLOW_ID,
        "name": "whatsapp-cloud",
        "nodes": nos,
        "connections": CONEXOES,
        "settings": base.get("settings", {}),
        "active": False,
    }

    _conferir_referencias(workflow)

    SAIDA.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"gerado {SAIDA.name}: {len(nos)} nós")
    print(f"  herdados do Modo 1 : {len(HERDADOS)}")
    print(f"  reescritos         : 2 (solicitar_handoff1, Responder WhatsApp1)")
    print(f"  novos              : {len(novos_nos()) - 1} + Extrair1")
    print(f"  descartados        : {len(DESCARTADOS)}")


def _conferir_referencias(workflow: dict) -> None:
    """Recusa `$('Nó')` apontando para nó que não veio no fork.

    É o erro que um fork por recorte comete calado: a ferramenta continua
    citando um nó do Modo 1 que ficou para trás, e só quebra em produção.
    """
    nomes = {n["name"] for n in workflow["nodes"]}
    texto = json.dumps(workflow, ensure_ascii=False)
    citados = set(re.findall(r"\$\('([^']+)'\)", texto))
    orfaos = sorted(citados - nomes)
    if orfaos:
        sys.exit(f"ERRO: referência a nó que não existe no fork: {orfaos}")

    for origem, saidas in workflow["connections"].items():
        if origem not in nomes:
            sys.exit(f"ERRO: conexão sai de nó inexistente: {origem}")
        for ramos in saidas.values():
            for ramo in ramos:
                for c in ramo:
                    if c["node"] not in nomes:
                        sys.exit(f"ERRO: conexão entra em nó inexistente: {c['node']}")


if __name__ == "__main__":
    main()
