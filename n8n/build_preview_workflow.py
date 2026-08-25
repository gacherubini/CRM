#!/usr/bin/env python3
"""Gera `workflow-preview.json`: o agente da loja rodando sem WhatsApp no meio.

O lojista escreve a configuração na Revy Loja, clica em **Testar** e conversa com
o agente do **rascunho** antes de publicar. É a rede de segurança do campo livre
(spec §4.5): ele escreve, testa, vê o agente estranho e corrige.

Rode da raiz do repo:

    python n8n/build_preview_workflow.py

## Por que gerado, e não escrito à mão

O mesmo motivo do fork do Modo 2: agente, modelo, memória e ferramentas saem
daqui **byte a byte** iguais aos do Modo 1. Preview que diverge do bot real não é
preview — é um segundo bot que dá uma opinião sobre o primeiro.

## Por que no mesmo n8n2037, e não num n8n novo

O canônico se chama `workflow-ai-**nao-salvos**` porque já roda sem gravar
execução, e o preview herda isso — foi volume de SQLite que deixou o bot mudo em
08/08. Subir workflow novo é import + `update:workflow --active=true`, sem
restart; **reiniciar** o n8n2037 é que custa ~6 min de webhook 404. E o n8n não
dorme: outra VM 24 h por um lojista clicando numa tela não se paga.

## As três coisas que este gerador existe para acertar

1. **Nó-ponte `Extrair1`.** As ferramentas não são nós HTTP: são `toolCode` que
   leem `$('Extrair1').first().json` para achar `instance` e `telefone`. Um
   workflow de entrada HTTP não tem esse nó, e ferramenta que referencia nó
   inexistente falha. O fork do Modo 2 cometeu esse erro calado; a correção lá
   foi criar nós-ponte de mesmo nome, e aqui é a mesma. A ponte **não** replica
   o parsing do corpo da Evolution nem a trava de 300 s de idade da mensagem,
   que descartaria toda mensagem de teste.

2. **Telefone sintético.** `consultar_estoque1` **não é só leitura**: com
   resultado único ela grava a moto escolhida (`POST /v1/operacao/moto-escolhida`),
   chaveada por telefone + instance. O lojista vai testar com o próprio número,
   que é um número real, com conversa real — sem freio ele sobrescreve o estado
   de uma conversa de verdade. Quem escolhe o telefone é o `chatbot-api`, e ele
   manda um fora da faixa de número real.

3. **Modo seco.** As ferramentas têm efeito no mundo: `simular1` cria lead no
   portal, avisa a equipe no WhatsApp e pausa o bot. Sem freio, o lojista testa
   digitando um CPF e toca o celular do vendedor num sábado.

O modo seco é **injeção cirúrgica**, não reescrita: a validação inteira continua
rodando (falta CPF ainda pede CPF, menor de idade ainda bloqueia) e o que fica de
fora é só a chamada que causa efeito. Cada injeção afirma **uma** ocorrência do
trecho — se o Modo 1 mudar de forma, este gerador **para** em vez de produzir um
preview que cria lead de verdade.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BASE = RAIZ / "workflow-ai-nao-salvos.json"
SAIDA = RAIZ / "workflow-preview.json"

WORKFLOW_ID = "wAiPreviewLoja01"
WEBHOOK_PATH = "whatsapp-ai-preview"
CHATBOT = "http://chatbot-api:8000"

# Herdados byte a byte. Fora da lista, com motivo:
#   Webhook1/Extrair1        — entrada é HTTP do chatbot, não Evolution
#   grupo de estoque (7 nós) — não há grupo num preview de conversa de cliente
#   debounce (Wait + juiz)   — 40 s de espera numa tela é a tela travada
#   Buscar/Gate config       — o preview usa o RASCUNHO, que vem no corpo
#   Atraso anti-ban1         — não há Evolution para honrar o delay
#   Responder WhatsApp1      — a resposta volta pelo próprio webhook
#   Registrar saida do bot1  — a conversa de teste não entra no CRM
HERDADOS = [
    "AI Agent1",
    "Google Gemini Chat Model1",
    "Memoria da conversa1",
    "consultar_estoque1",
    "enviar_link_catalogo1",
    "simular1",
    "TEMP continuar sem estoque1",
    "solicitar_handoff1",
    "enviar_foto_veiculo1",
    "cadastrar_veiculo1",
]

FERRAMENTAS = [
    "consultar_estoque1",
    "enviar_link_catalogo1",
    "simular1",
    "TEMP continuar sem estoque1",
    "solicitar_handoff1",
    "enviar_foto_veiculo1",
    "cadastrar_veiculo1",
]

# --- modo seco ---------------------------------------------------------------
# (nome da tool, trecho que existe hoje, o que passa a vir no lugar dele).
# `enviar_link_catalogo1` não aparece aqui: ela só lê.

_MSG_SIMULACAO = (
    "certo, já tenho seus dados. vou encaminhar pro setor de simulação e te "
    "retorno por aqui. atendemos das 8h30 às 18h; fora desse horário, respondo "
    "no próximo dia útil."
)

# `consultar_estoque1` é um caso à parte, e o mais sutil: a **busca** roda de
# verdade (é ela que faz o teste valer) mas a **gravação** não pode. Com resultado
# único ela grava a moto escolhida no CRM, e essa gravação CRIA uma `Conversa` —
# o preview apareceria em Conversas com o telefone sintético, contra a promessa
# de a conversa de teste ser efêmera. O estado continua vivo no static data deste
# workflow, que é escopado por workflow e não colide com o do bot real.
_CRM_MOTO_ESCOLHIDA_UNICA = """    // Persistência no CRM (fonte de verdade se static data sumir).
    try {
      await helpers.httpRequest({
        method: 'POST',
        url: 'http://chatbot-api:8000/v1/operacao/moto-escolhida',
        headers: {
          Authorization: 'Bearer __CHATBOT_TOKEN__',
          'Content-Type': 'application/json',
        },
        body: { telefone, instance: instance || null, ...escolhida },
        json: true,
        timeout: 8000,
      });
    } catch (_) {}
"""

_CRM_MOTO_ESCOLHIDA_LIMPEZA = """    try {
      await helpers.httpRequest({
        method: 'POST',
        url: 'http://chatbot-api:8000/v1/operacao/moto-escolhida',
        headers: {
          Authorization: 'Bearer __CHATBOT_TOKEN__',
          'Content-Type': 'application/json',
        },
        body: { telefone: telefoneTeste, instance: instanceTeste || null },
        json: true,
        timeout: 8000,
      });
    } catch (_) {}
"""

INJECOES_SECO: dict[str, list[tuple[str, str]]] = {
    "consultar_estoque1": [
        (
            _CRM_MOTO_ESCOLHIDA_UNICA,
            "    // MODO SECO (preview): a busca no estoque acima roda de verdade;\n"
            "    // esta gravação não. Ela cria `Conversa` para o telefone sintético, e\n"
            "    // a conversa de teste não pode aparecer em Conversas. A moto escolhida\n"
            "    // segue guardada no static data deste workflow.\n",
        ),
        (
            _CRM_MOTO_ESCOLHIDA_LIMPEZA,
            "    // MODO SECO (preview): idem — a limpeza da seleção também cria\n"
            "    // `Conversa`. O static data acima já foi limpo.\n",
        ),
    ],
    # Toda a validação já rodou aqui: falta de CPF, CNH ambígua e menor de idade
    # respondem como no bot real. O que some são as duas chamadas seguintes —
    # a do Motor e a que cria o lead, avisa a equipe e pausa o bot.
    "simular1": [
        (
            "headers['Idempotency-Key'] = mensagemId;",
            "headers['Idempotency-Key'] = mensagemId;\n"
            "\n"
            "// MODO SECO (preview): daqui para baixo o bot real cria lead no portal,\n"
            "// avisa a equipe no WhatsApp e pausa o bot. Num teste isso toca o celular\n"
            "// do vendedor num sábado por causa de um CPF digitado numa tela.\n"
            "return JSON.stringify({\n"
            "  ok: true,\n"
            "  simulacao_humana_solicitada: true,\n"
            f"  mensagem: '{_MSG_SIMULACAO}',\n"
            "});",
        )
    ],
    "TEMP continuar sem estoque1": [
        (
            "const headers = {\n  Authorization: 'Bearer __CHATBOT_TOKEN__',",
            "// MODO SECO (preview): mesma razão do simular1 — a chamada seguinte cria\n"
            "// lead e avisa a equipe.\n"
            "return JSON.stringify({\n"
            "  ok: true,\n"
            "  fallback_temporario: true,\n"
            "  simulacao_humana_solicitada: true,\n"
            "  pode_oferecer_fotos: false,\n"
            f"  mensagem: '{_MSG_SIMULACAO}',\n"
            "});\n"
            "\n"
            "const headers = {\n  Authorization: 'Bearer __CHATBOT_TOKEN__',",
        )
    ],
    # Handoff inteiro é efeito: pausa o bot de uma conversa e avisa o vendedor.
    # A frase de retorno é fixa no bot real, então o preview a devolve igual.
    "solicitar_handoff1": [
        (
            "if (!instance) return JSON.stringify({ mensagem: 'não consegui identificar o canal whatsapp da conversa.' });",
            "if (!instance) return JSON.stringify({ mensagem: 'não consegui identificar o canal whatsapp da conversa.' });\n"
            "\n"
            "// MODO SECO (preview): o handoff real pausa o bot da conversa e chama o\n"
            "// vendedor. A frase devolvida ao cliente é fixa, então o teste mostra a\n"
            "// mesma coisa sem acordar ninguém.\n"
            "return JSON.stringify({ mensagem: 'certo. vou encaminhar seu atendimento.' });",
        )
    ],
    # Foto: o id já foi validado acima, então o agente ainda é cobrado por
    # escolher uma moto antes de pedir fotos. O que não acontece é o envio.
    "enviar_foto_veiculo1": [
        (
            "const instance = String(origem.instance || '').trim();",
            "// MODO SECO (preview): não há WhatsApp para receber mídia. O agente responde\n"
            "// como se tivesse mandado, que é o que o lojista precisa ler.\n"
            "return JSON.stringify({ ok: true, fotos_enviadas: 4, veiculo: {} });\n"
            "\n"
            "const instance = String(origem.instance || '').trim();",
        )
    ],
    # Cadastro cria veículo no Estoque. Num preview isso é estoque falso na loja.
    "cadastrar_veiculo1": [
        (
            "if (!telefone_solicitante) return JSON.stringify({ erro: 'telefone_solicitante obrigatorio' });",
            "if (!telefone_solicitante) return JSON.stringify({ erro: 'telefone_solicitante obrigatorio' });\n"
            "\n"
            "// MODO SECO (preview): o cadastro real põe veículo no Estoque da loja.\n"
            "return JSON.stringify({ ok: true, veiculo: {} });",
        )
    ],
}


def _injetar_seco(no: dict) -> None:
    trocas = INJECOES_SECO.get(no["name"])
    if not trocas:
        return
    codigo = no["parameters"]["jsCode"]
    for antigo, novo in trocas:
        if codigo.count(antigo) != 1:
            sys.exit(
                f"ERRO: {no['name']} mudou de forma no Modo 1 -- esperava uma "
                f"ocorrencia de {antigo!r}, achei {codigo.count(antigo)}. "
                "Ajuste INJECOES_SECO antes de gerar: sem a injecao o preview "
                "cria lead, avisa a equipe e pausa o bot de verdade."
            )
        codigo = codigo.replace(antigo, novo, 1)
    no["parameters"]["jsCode"] = codigo


# --- nós novos ---------------------------------------------------------------

EXTRAIR_JS = """
// Ponte de nome. As ferramentas leem $('Extrair1').first().json para achar
// instance e telefone, entao o preview precisa de um no com este nome exato e
// este formato -- reescrever as ferramentas e o que transformaria copia em
// outro bot.
//
// Duas diferencas deliberadas em relacao ao Extrair1 real: nao ha corpo da
// Evolution para parsear, e nao ha a trava de 300 s de idade da mensagem, que
// descartaria toda mensagem de teste.
const b = ($input.first().json || {}).body || $input.first().json || {};
const telefone = String(b.telefone || '').replace(/\\D/g, '');
const instance = String(b.instance || '').trim();
// Fail-closed: sem loja nao ha estoque para consultar nem prompt para aplicar.
if (!telefone || !instance) return [];
return [{
  json: {
    instance,
    telefone,
    destino: telefone,
    texto: String(b.texto || ''),
    providerMessageId: 'preview:' + telefone + ':' + String(b.turno || '1'),
    pushName: String(b.nome || ''),
    fromMe: false,
    ehGrupo: false,
    grupoJid: null,
    primeiraMensagem: Boolean(b.primeira_mensagem),
    veioDeAnuncio: false,
    anuncioTitulo: '',
    anuncioDescricao: '',
    historicoRecente: String(b.historico || ''),
    historico_recente: String(b.historico || ''),
    preview: true,
  },
}];
""".strip()

PONTE_REGISTRO_JS = """
// Ponte de nome: o AI Agent1, herdado byte a byte, le
// $('Registrar mensagem e ler handoff1').first().json.historico_recente. No
// preview a conversa e efemera e o historico vem no corpo -- nada e gravado no
// CRM, que e o ponto: a conversa de teste nao vira lead nem aparece em Conversas.
const e = $('Extrair1').first().json || {};
return [{ json: { historico_recente: e.historico_recente || '', bot_ativo: true } }];
""".strip()

PONTE_GATE_JS = """
// Ponte de nome: o Gate somente nao salvos1 do Modo 1 decide se a mensagem e de
// cliente. Num preview toda mensagem e de cliente, por definicao.
const e = $('Extrair1').first().json || {};
return [{ json: { ...e, acao: 'cliente' } }];
""".strip()

PONTE_CONFIG_JS = """
// Ponte de nome, e a diferenca que faz o preview existir: o AI Agent1 le
// $('Gate config do agente1').first().json.promptAgente, e aqui esse prompt e o
// do RASCUNHO -- montado pelo chatbot a partir do que o lojista acabou de
// digitar, ainda nao publicado. No Modo 1 e no Modo 2 o mesmo slot traz o
// publicado, buscado por HTTP.
//
// O prompt chega pronto de proposito: montar texto aqui seria um segundo gerador
// divergindo do primeiro na primeira mudanca de campo.
const b = ($('Webhook preview').first().json || {}).body || {};
const prompt = String(b.prompt || '').trim();
if (!prompt) throw new Error('preview sem prompt: o chatbot precisa mandar o rascunho');
return [{
  json: {
    ...($('Extrair1').first().json || {}),
    promptAgente: prompt,
    configDaLoja: true,
    // Mesmas chaves do gate real: e o que faz o preview mostrar o efeito das
    // escolhas de escrita e emoji, em vez de higienizar todo mundo igual.
    saidaMinusculas: b.saida_minusculas !== false,
    saidaSemEmoji: b.saida_sem_emoji !== false,
  },
}];
""".strip()


def novos_nos() -> list[dict]:
    return [
        {
            "parameters": {
                "httpMethod": "POST",
                "path": WEBHOOK_PATH,
                # responseNode: quem responde é o nó final, com o texto do agente.
                "responseMode": "responseNode",
                "options": {},
            },
            "id": "preview-webhook",
            "name": "Webhook preview",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [-460, 40],
            "webhookId": WEBHOOK_PATH,
        },
        {
            "parameters": {"jsCode": EXTRAIR_JS},
            "id": "preview-extrair",
            "name": "Extrair1",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-240, 40],
        },
        {
            "parameters": {"jsCode": PONTE_REGISTRO_JS},
            "id": "preview-registro",
            "name": "Registrar mensagem e ler handoff1",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-240, 220],
        },
        {
            "parameters": {"jsCode": PONTE_GATE_JS},
            "id": "preview-gate",
            "name": "Gate somente nao salvos1",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-240, 400],
        },
        {
            "parameters": {"jsCode": PONTE_CONFIG_JS},
            "id": "preview-config",
            "name": "Gate config do agente1",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-20, 40],
        },
        {
            "parameters": {
                "respondWith": "json",
                # Mesma higienização do envio real (condicionada à loja): o
                # lojista precisa ler o que o cliente leria, não o cru do modelo.
                "responseBody": (
                    "={{ (() => { const cfg = $('Gate config do agente1').first().json || {}; "
                    "const texto = String($json.output || ''); "
                    "let limpo = texto; "
                    "if (cfg.saidaSemEmoji !== false) limpo = limpo"
                    ".replace(/[\\p{Extended_Pictographic}\\uFE0F\\u200D]/gu, ''); "
                    "if (cfg.saidaMinusculas !== false) limpo = limpo"
                    ".toLocaleLowerCase('pt-BR').replace(/!+/g, '.'); "
                    "limpo = limpo.replace(/\\bme conta[:,]?\\s*/g, '')"
                    ".replace(/\\s{2,}/g, ' ')"
                    ".replace(/\\s+([.,?])/g, '$1').trim(); "
                    "return { texto: limpo, preview: true }; })() }}"
                ),
                "options": {},
            },
            "id": "preview-responder",
            "name": "Responder preview",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1.1,
            "position": [860, 40],
        },
    ]


CONEXOES = {
    "Webhook preview": {"main": [[{"node": "Extrair1", "type": "main", "index": 0}]]},
    "Extrair1": {
        "main": [[{"node": "Registrar mensagem e ler handoff1", "type": "main", "index": 0}]]
    },
    "Registrar mensagem e ler handoff1": {
        "main": [[{"node": "Gate somente nao salvos1", "type": "main", "index": 0}]]
    },
    "Gate somente nao salvos1": {
        "main": [[{"node": "Gate config do agente1", "type": "main", "index": 0}]]
    },
    "Gate config do agente1": {"main": [[{"node": "AI Agent1", "type": "main", "index": 0}]]},
    "AI Agent1": {"main": [[{"node": "Responder preview", "type": "main", "index": 0}]]},
    "Google Gemini Chat Model1": {
        "ai_languageModel": [[{"node": "AI Agent1", "type": "ai_languageModel", "index": 0}]]
    },
    "Memoria da conversa1": {
        "ai_memory": [[{"node": "AI Agent1", "type": "ai_memory", "index": 0}]]
    },
    **{
        tool: {"ai_tool": [[{"node": "AI Agent1", "type": "ai_tool", "index": 0}]]}
        for tool in FERRAMENTAS
    },
}


def main() -> None:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    por_nome = {n["name"]: n for n in base["nodes"]}

    faltando = [n for n in HERDADOS if n not in por_nome]
    if faltando:
        sys.exit(f"ERRO: o Modo 1 não tem mais estes nós (renomeados?): {faltando}")

    nos = [json.loads(json.dumps(por_nome[n])) for n in HERDADOS]
    for n in nos:
        if n.get("parameters", {}).get("jsCode"):
            _injetar_seco(n)

    # Sub-nó do Agent não preserva o pareamento de itens depois de uma chamada de
    # ferramenta; o preview processa uma mensagem por execução, então `.first()`.
    memoria = next(n for n in nos if n["name"] == "Memoria da conversa1")
    memoria["parameters"]["sessionKey"] = (
        "={{ 'preview:' + $('Extrair1').first().json.instance + ':' "
        "+ $('Extrair1').first().json.telefone }}"
    )

    nos.extend(novos_nos())

    trilha = ["Gate config do agente1", "AI Agent1", "Responder preview"]
    for i, nome in enumerate(trilha):
        for n in nos:
            if n["name"] == nome:
                n["position"] = [-20 + i * 220, 40]

    workflow = {
        "id": WORKFLOW_ID,
        "name": "WhatsApp IA - PREVIEW (config do agente)",
        "description": (
            "Gerado por n8n/build_preview_workflow.py. Roda o agente do RASCUNHO "
            "da loja, com as ferramentas em modo seco e telefone sintético. Não "
            "cria lead, não avisa a equipe, não pausa bot e não grava no CRM."
        ),
        "nodes": nos,
        "connections": CONEXOES,
        "settings": base.get("settings", {}),
        "active": False,
    }

    _conferir_referencias(workflow)

    SAIDA.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"gerado {SAIDA.name}: {len(nos)} nós, webhook={WEBHOOK_PATH}")
    print(f"  herdados do Modo 1 : {len(HERDADOS)}")
    print(f"  em modo seco       : {len(INJECOES_SECO)}")
    print(f"  novos              : {len(novos_nos())}")


def _conferir_referencias(workflow: dict) -> None:
    """Recusa `$('Nó')` apontando para nó que não veio no preview.

    É o erro que um recorte comete calado: a ferramenta continua citando um nó do
    Modo 1 que ficou para trás, e só quebra quando o lojista clica em Testar.
    """
    nomes = {n["name"] for n in workflow["nodes"]}
    texto = json.dumps(workflow, ensure_ascii=False)
    orfaos = sorted(set(re.findall(r"\$\('([^']+)'\)", texto)) - nomes)
    if orfaos:
        sys.exit(f"ERRO: referência a nó que não existe no preview: {orfaos}")

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
