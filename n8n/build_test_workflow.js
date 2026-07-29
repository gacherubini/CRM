#!/usr/bin/env node
/*
 * Gera uma copia do workflow canonico para testes isolados no WhatsApp.
 *
 * O fluxo gerado:
 * - usa ID, nome e webhook proprios;
 * - ignora mensagens enviadas pelo proprio bot;
 * - ignora grupos e áudios;
 * - aceita somente o numero TEST_PHONE.
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

// Experimento exclusivo do teste: a conversa apresenta catálogo e fotos antes
// de oferecer a simulação. O workflow canônico não é alterado.
const agent = nodeByName('AI Agent1');
const testCatalogJourney = `2. jornada de catálogo antes da simulação:
- enquanto estiver apresentando, listando, filtrando ou confirmando motos, não fale em simular, simulação, financiamento, cpf, nascimento ou entrada.
- quando a consulta retornar mais de uma opção, mostre as opções de forma curta e pergunte somente “qual delas você quer conhecer melhor?”.
- quando a busca do cliente retornar uma única moto, apresente os dados disponíveis e pergunte “quer que eu mande as fotos do catálogo?”. não ofereça simulação nessa resposta.
- se o cliente aceitar as fotos, chame enviar_foto_veiculo. a ferramenta recupera a última moto única consultada, então não peça modelo, id ou placa novamente.
- depois que as fotos forem enviadas com sucesso, responda somente “gostou dessa? se quiser, posso fazer uma simulação pra você.”. este é o primeiro momento do fluxo de catálogo em que você pode oferecer simulação.
- se o cliente recusar as fotos e pedir diretamente a simulação, pode seguir. se pedir simulação antes de escolher uma moto específica, consulte e apresente o catálogo, depois pergunte “qual delas você quer conhecer melhor?”.
- só depois de uma moto específica estar escolhida e o cliente confirmar que quer simular, peça uma única vez o que faltar entre cpf, data de nascimento e entrada. se a mensagem atual trouxer 11 dígitos de cpf, uma data e um valor de entrada, considere os três recebidos, normalize a data e chame simular no mesmo atendimento.
- nunca repita a solicitação de dados já recebidos. se os dados internos da moto não estiverem mais no contexto, consulte o estoque novamente usando a moto escolhida no histórico e então chame simular. nunca peça placa ao cliente nem peça que ele confirme uma placa. telefone_cliente já vem na mensagem. não peça renda nem prazo.`;
agent.parameters.options.systemMessage = replaceRegexRequired(
  String(agent.parameters.options.systemMessage || ''),
  /2\. simulação e escolha obrigatória:[\s\S]*?\n3\. privacidade do resultado:/,
  testCatalogJourney + '\n3. privacidade do resultado:',
  'AI Agent1',
);
agent.parameters.options.systemMessage = replaceRequired(
  agent.parameters.options.systemMessage,
  '9. foto de veículo: use enviar_foto_veiculo com o id confiável retornado pela consulta. envie no próprio whatsapp e nunca forneça url de mídia.',
  '9. foto de veículo: depois que o cliente aceitar a oferta de fotos, use enviar_foto_veiculo. passe o id confiável retornado pela consulta quando estiver disponível; em uma mensagem seguinte, a ferramenta recupera a última moto única consultada. envie no próprio whatsapp e nunca forneça url de mídia.',
  'AI Agent1',
);

const inventory = nodeByName('consultar_estoque1');
inventory.parameters.description =
  'Consulta o estoque real da loja. Use para perguntas sobre veículos, marcas, modelos ou faixa de preço. Quando houver mais de uma opção, ajude o cliente a escolher qual quer conhecer melhor. Uma busca específica com resultado único preserva a moto para oferecer fotos do catálogo. Nunca invente disponibilidade e nunca peça ou revele a placa.';
inventory.parameters.jsCode = replaceRequired(
  String(inventory.parameters.jsCode || ''),
  'return JSON.stringify(resp);',
  `// No teste, uma listagem ampla ou ambígua invalida uma seleção anterior.
// Assim, um “sim” posterior nunca envia fotos da moto errada.
try {
  const veiculosTeste = Array.isArray(resp?.veiculos) ? resp.veiculos : [];
  const origemTeste = $('Extrair1').first().json;
  const telefoneTeste = String(origemTeste.telefone || '').replace(/\\D/g, '');
  if (telefoneTeste && !(termo && veiculosTeste.length === 1)) {
    const estadoTeste = $getWorkflowStaticData('global');
    delete estadoTeste['moto-escolhida:' + telefoneTeste];
  }
} catch (_) {}

return JSON.stringify(resp);`,
  'consultar_estoque1',
);

const photoTool = nodeByName('enviar_foto_veiculo1');
photoTool.parameters.description =
  'Envia no WhatsApp até 4 fotos do catálogo. No fluxo normal, use depois que o cliente aceitar a oferta de fotos da última moto única consultada; o veiculo_id é opcional nesse caso. Em mensagem de anúncio, use automaticamente após uma correspondência clara e passe o ID retornado. Nunca passe URL.';
photoTool.parameters.jsCode = replaceRequired(
  String(photoTool.parameters.jsCode || ''),
  `const input = typeof query === 'string' ? { veiculo_id: query } : (query || {});
const veiculoId = String(input.veiculo_id || '').trim();
if (!/^[A-Za-z0-9-]{1,120}$/.test(veiculoId)) {
  return JSON.stringify({ ok: false, mensagem: 'veiculo_id invalido' });
}

const origem = $('Extrair1').first().json || {};`,
  `const input = typeof query === 'string' ? { veiculo_id: query } : (query || {});
const origem = $('Extrair1').first().json || {};
const telefone = String(origem.telefone || '').replace(/\\D/g, '');
let veiculoId = String(input.veiculo_id || '').trim();
if (!veiculoId && telefone) {
  try {
    const estado = $getWorkflowStaticData('global');
    veiculoId = String(estado['moto-escolhida:' + telefone]?.id || '').trim();
  } catch (_) {}
}
if (!/^[A-Za-z0-9-]{1,120}$/.test(veiculoId)) {
  return JSON.stringify({
    ok: false,
    sem_veiculo_escolhido: true,
    mensagem: 'escolha uma moto específica antes de pedir as fotos',
  });
}`,
  'enviar_foto_veiculo1',
);
photoTool.parameters.inputSchema = JSON.stringify({
  type: 'object',
  properties: {
    veiculo_id: {
      type: 'string',
      description:
        'ID retornado pela consulta; opcional quando o cliente aceitou as fotos da última moto única consultada',
    },
  },
  additionalProperties: true,
});

const simulationTool = nodeByName('simular1');
simulationTool.parameters.description =
  'Use somente no fim da jornada: depois que o cliente escolher uma moto específica, receber ou recusar as fotos do catálogo, confirmar que quer simular e enviar CPF, nascimento e entrada. Recupera os dados internos da última moto única consultada, cria o lead qualificado, mantém o bot ativo e avisa o vendedor. Nunca use esta ferramenta durante a apresentação ou escolha do catálogo.';
simulationTool.parameters.jsCode = replaceRequired(
  String(simulationTool.parameters.jsCode || ''),
  'a moto ainda não foi escolhida. pergunte somente qual moto o cliente quer simular. não peça cpf, nascimento, entrada ou placa agora e não repita dados que ele já enviou.',
  'a moto ainda não foi escolhida. volte ao catálogo e pergunte somente qual moto o cliente quer conhecer melhor. não fale em simulação e não peça cpf, nascimento, entrada ou placa agora.',
  'simular1',
);

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
