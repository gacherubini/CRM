#!/usr/bin/env node
/*
 * Gera uma copia do workflow canonico para testes isolados no WhatsApp.
 *
 * O fluxo gerado:
 * - usa ID, nome e webhook proprios;
 * - ignora mensagens enviadas pelo proprio bot;
 * - ignora grupos e áudios;
 * - aceita somente o numero TEST_PHONE.
 * A jornada de catálogo (prompt/tools) já está no canônico oficial; aqui só há freios de lab.
 *
 * Nao ha segredos neste arquivo nem no JSON gerado. Os placeholders continuam
 * sendo preenchidos por deploy/fly/3vm/prepare-workflow.ps1 -Mode test.
 */
const fs = require("fs");
const path = require("path");

const TEST_PHONE = "5551980336365";
const TEST_PHONE_ALIASES = [TEST_PHONE, "555180336365"];
const TEST_WORKFLOW_ID = "wAiTesteRestrito01";
const TEST_WORKFLOW_NAME = "WhatsApp IA - TESTE " + TEST_PHONE;
const TEST_WEBHOOK_PATH = "whatsapp-ai-teste";
const TEST_VERSION_ID = "8f463988-e552-4a61-acee-555198033635";
const TEST_TIMESTAMP = "2026-07-27T12:00:00.000Z";

const canonicalPath = path.join(__dirname, "workflow-ai-nao-salvos.json");
const outputPath = path.join(__dirname, "workflow-teste-numero-autorizado.json");
const workflow = JSON.parse(fs.readFileSync(canonicalPath, "utf8"));

function nodeByName(name) {
  const node = workflow.nodes.find((candidate) => candidate.name === name);
  if (!node) throw new Error('node ' + name + ' nao encontrado');
  return node;
}

function replaceRequired(value, before, after, context) {
  if (!value.includes(before)) {
    throw new Error('trecho esperado nao encontrado em ' + context);
  }
  return value.replace(before, after);
}

function replaceRegexRequired(value, pattern, after, context) {
  if (!pattern.test(value)) {
    throw new Error('trecho esperado nao encontrado em ' + context);
  }
  return value.replace(pattern, after);
}

workflow.id = TEST_WORKFLOW_ID;
workflow.name = TEST_WORKFLOW_NAME;
workflow.description =
  "Copia de teste do workflow canonico. Processa somente mensagens privadas recebidas de " +
  TEST_PHONE +
  ".";
workflow.active = false;
workflow.createdAt = TEST_TIMESTAMP;
workflow.updatedAt = TEST_TIMESTAMP;
workflow.versionId = TEST_VERSION_ID;
workflow.activeVersionId = null;
workflow.versionCounter = 1;
workflow.triggerCount = 0;
workflow.sourceWorkflowId = null;

// A jornada de catálogo (prompt + tools) vive no canônico oficial desde 2026-08.
// Este gerador só aplica freios de lab: webhook próprio, 1 telefone, sem grupos.

const agent = nodeByName('AI Agent1');
const canonicalPrompt = String(agent.parameters.options.systemMessage || '');
if (!canonicalPrompt.includes('jornada de catálogo antes da simulação')) {
  throw new Error(
    'AI Agent1 no canônico deve ter a jornada de catálogo; rode a promoção teste→oficial antes',
  );
}

const webhook = workflow.nodes.find((node) => node.name === "Webhook1");
if (!webhook) throw new Error("node Webhook1 nao encontrado");
webhook.parameters.path = TEST_WEBHOOK_PATH;
webhook.webhookId = TEST_WEBHOOK_PATH;

const extractor = workflow.nodes.find((node) => node.name === "Extrair1");
if (!extractor) throw new Error("node Extrair1 nao encontrado");

const anchor =
  "const destino = ehGrupo ? jid : (jid.endsWith('@lid') ? jid : jid.split('@')[0]);\n";
const guard = [
  anchor.trimEnd(),
  "const telefonesTeste = " + JSON.stringify(TEST_PHONE_ALIASES) + ";",
  "const remetentesPossiveis = [jid, jidAlt, jidTelefone, telefone, ...participantes]",
  "  .map((value) => String(value || '').split('@')[0].replace(/\\D/g, ''))",
  "  .filter(Boolean);",
  "// Fail-closed: este workflow nao processa saidas do bot, grupos ou outro remetente.",
  "if (fromMe || ehGrupo || !remetentesPossiveis.some((numero) => telefonesTeste.includes(numero))) return [];",
  "",
].join("\n");

const extractCode = String(extractor.parameters.jsCode || "");
if (!extractCode.includes(anchor)) {
  throw new Error("ponto de insercao do filtro nao encontrado em Extrair1");
}
if (extractCode.includes("const telefonesTeste =")) {
  throw new Error("workflow canonico ja contem filtro de teste");
}
extractor.parameters.jsCode = extractCode.replace(anchor, guard);

const gate = workflow.nodes.find((node) => node.name === "Gate somente nao salvos1");
if (!gate) throw new Error("node Gate somente nao salvos1 nao encontrado");
const gateAnchor = "const botAtivo = origem.bot_ativo !== false;\n";
const testRouteOverride = [
  gateAnchor.trimEnd(),
  "const ehTelefoneTeste = " + JSON.stringify(TEST_PHONE_ALIASES) +
    ".includes(String(origem.telefone || '').replace(/\\D/g, ''));",
  "// No fluxo de teste, o numero permitido sempre entra como cliente da IA.",
  "if (ehTelefoneTeste && !origem.ehGrupo && botAtivo) {",
  "  // Permite testar uma vez o primeiro contato mesmo com conversa antiga no CRM.",
  "  let primeiraMensagemTeste = origem.primeiraMensagem === true;",
  "  try {",
  "    const estadoTeste = $getWorkflowStaticData('global');",
  "    const chavePrimeiroContato = 'vitorMotosFirstContact20260727v2';",
  "    if (!estadoTeste[chavePrimeiroContato]) {",
  "      primeiraMensagemTeste = true;",
  "      estadoTeste[chavePrimeiroContato] = true;",
  "    }",
  "  } catch (e) {}",
  "  return [{ json: { ...origem, acao: 'cliente', primeiraMensagem: primeiraMensagemTeste } }];",
  "}",
  "",
].join("\n");
const gateCode = String(gate.parameters.jsCode || "");
if (!gateCode.includes(gateAnchor)) {
  throw new Error("ponto de insercao nao encontrado em Gate somente nao salvos1");
}
gate.parameters.jsCode = gateCode.replace(gateAnchor, testRouteOverride);

// Sub-nos do AI Agent nao preservam sempre o pareamento de itens depois de uma
// chamada de ferramenta. Use o primeiro item do Extrair1, pois este webhook
// processa uma unica mensagem por execucao.
const memory = workflow.nodes.find((node) => node.name === "Memoria da conversa1");
if (!memory) throw new Error("node Memoria da conversa1 nao encontrado");
memory.parameters.sessionKey =
  "={{ $('Extrair1').first().json.instance + ':' + $('Extrair1').first().json.telefone }}";

for (const nodeName of ["Responder WhatsApp1", "Registrar saida do bot1"]) {
  const node = workflow.nodes.find((candidate) => candidate.name === nodeName);
  if (!node) throw new Error("node " + nodeName + " nao encontrado");
  const parameters = JSON.stringify(node.parameters);
  node.parameters = JSON.parse(
    parameters.replaceAll("$('Extrair1').item", "$('Extrair1').first()"),
  );
}

if (Array.isArray(workflow.shared)) {
  for (const share of workflow.shared) {
    share.workflowId = TEST_WORKFLOW_ID;
    share.createdAt = TEST_TIMESTAMP;
    share.updatedAt = TEST_TIMESTAMP;
  }
}
workflow.versionMetadata = {
  name: "Teste restrito 5551980336365",
  description: "Gerado de n8n/workflow-ai-nao-salvos.json",
};

fs.writeFileSync(
  outputPath,
  JSON.stringify(workflow, null, 2) + "\n",
  "utf8",
);
console.log(
  "workflow de teste gerado: " +
    path.relative(process.cwd(), outputPath) +
    " (id=" + TEST_WORKFLOW_ID +
    ", webhook=" + TEST_WEBHOOK_PATH +
    ", telefone=" + TEST_PHONE + ")",
);
