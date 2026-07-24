const fs = require('node:fs');
const path = require('node:path');

const workflowPath = path.join(__dirname, 'workflow-ai-nao-salvos.json');
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));

function node(name) {
  const found = workflow.nodes.find((item) => item.name === name);
  if (!found) throw new Error(`Node nao encontrado: ${name}`);
  return found;
}

function upsertNode(value) {
  const index = workflow.nodes.findIndex((item) => item.name === value.name);
  if (index >= 0) workflow.nodes[index] = value;
  else workflow.nodes.push(value);
}

node('Extrair1').parameters.jsCode = `// Extrai mensagens privadas de clientes e o grupo oficial de estoque.
// Imagem so entra no fluxo de estoque quando veio de um grupo; o backend valida o JID exato.
const root = $input.first().json;
const b = root.body || root || {};
const data = b.data || {};
const key = data.key || {};
const event = String(b.event || root.event || '').toLowerCase();
if (event && (event.includes('messages.update') || event.includes('message.ack') || event.includes('reaction'))) return [];
const jid = String(key.remoteJid || '').trim();
const jidAlt = String(key.remoteJidAlt || '').trim();
const instance = String(b.instance || '__INSTANCE__');
const msg = data.message || {};
if (msg.reactionMessage) return [];
const fromMe = Boolean(key.fromMe);
const privado = jid.endsWith('@s.whatsapp.net') || jid.endsWith('@lid');
const ehGrupo = jid.endsWith('@g.us');
if (!jid || (!privado && !ehGrupo) || (ehGrupo && fromMe)) return [];
const audio = msg.audioMessage || null;
const imagem = msg.imageMessage || null;
const ehAudio = Boolean(audio) && privado;
const ehImagem = Boolean(imagem) && !fromMe;
const ehImagemEstoque = ehImagem && ehGrupo;
const texto = msg.conversation || msg.extendedTextMessage?.text || (ehImagem ? String(imagem.caption || '') : '');
if (!texto && !ehAudio && !ehImagemEstoque) return [];
const participantes = [key.participantAlt, key.participant, data.participant, data.sender]
  .map((value) => String(value || '').trim());
const participante = participantes.find((value) => value.endsWith('@s.whatsapp.net'))
  || participantes.find((value) => value.endsWith('@lid'))
  || '';
const jidTelefone = ehGrupo ? participante : (jidAlt.endsWith('@s.whatsapp.net') ? jidAlt : jid);
if (ehGrupo && !jidTelefone) return [];
const telefone = jidTelefone.endsWith('@lid') ? jidTelefone : jidTelefone.split('@')[0];
const destino = ehGrupo ? jid : (jid.endsWith('@lid') ? jid : jid.split('@')[0]);
const ctx = msg.extendedTextMessage?.contextInfo
  || msg.imageMessage?.contextInfo
  || data.contextInfo
  || {};
const ad = ctx.externalAdReply || ctx.externalAdReplyInfo || {};
const referral = data.referral || msg.referral || ctx.referral || {};
const pick = (...vals) => {
  for (const v of vals) {
    const s = (v == null ? '' : String(v)).trim();
    if (s) return s;
  }
  return null;
};
const ctwa_clid = pick(
  ctx.ctwaClid, ctx.ctwa_clid, ad.ctwaClid, ad.ctwa_clid,
  referral.ctwa_clid, referral.ctwaClid, data.ctwaClid, data.ctwa_clid
);
const meta_ad_id = pick(
  ad.sourceId, ad.advertisementId, ad.adId, ctx.sourceId,
  referral.source_id, referral.ad_id, data.sourceId
);
const meta_campaign_id = pick(
  ad.campaignId, ctx.campaignId, referral.campaign_id, data.campaignId
);
const meta_adset_id = pick(ad.adsetId, ctx.adsetId, referral.adset_id);
const ctwa_source_type = pick(
  ctx.conversionSource, ctx.entryPointConversionSource,
  ad.sourceType, referral.source_type, data.conversionSource
);
return [{ json: {
  instance, remoteJid: jid, remoteJidAlt: jidAlt, telefone, destino, texto,
  ehGrupo, grupoJid: ehGrupo ? jid : null, ehAudio, ehImagem, ehImagemEstoque,
  audioMimeType: ehAudio ? String(audio.mimetype || '') : null,
  audioDurationSeconds: ehAudio ? Number(audio.seconds || 0) : null,
  imageMimeType: ehImagem ? String(imagem.mimetype || '') : null,
  imageCaption: ehImagem ? String(imagem.caption || '') : null,
  pushName: data.pushName || '', providerMessageId: String(key.id || ''),
  fromMe,
  ctwa_clid, meta_ad_id, meta_campaign_id, meta_adset_id, ctwa_source_type
} }];
`;

node('E imagem de estoque1').parameters.conditions.conditions[0].leftValue =
  '={{ $json.ehImagemEstoque }}';
node('Salvar foto no estoque1').parameters.jsonBody =
  '={{ { instance: $json.instance, telefone_solicitante: $json.telefone, grupo_jid: $json.grupoJid, provider_message_id: $json.providerMessageId, legenda: $json.imageCaption || null, mime_type: $json.imageMimeType || null } }}';

upsertNode({
  parameters: {
    jsCode: `const resultado = $input.first().json || {};
if (resultado.ignorar === true || !String(resultado.mensagem || '').trim()) return [];
return [{ json: resultado }];
`,
  },
  id: 'stock-photo-response-gate',
  name: 'Foto deve responder1',
  type: 'n8n-nodes-base.code',
  typeVersion: 2,
  position: [1808, 128],
});
node('Responder cadastro de foto1').position = [2016, 128];

upsertNode({
  parameters: {
    conditions: {
      options: {
        caseSensitive: true,
        leftValue: '',
        typeValidation: 'strict',
        version: 2,
      },
      conditions: [{
        id: 'stock-group-condition',
        leftValue: '={{ $json.ehGrupo }}',
        rightValue: true,
        operator: { type: 'boolean', operation: 'true', singleValue: true },
      }],
      combinator: 'and',
    },
    options: {},
  },
  id: 'stock-group-if',
  name: 'E grupo de estoque1',
  type: 'n8n-nodes-base.if',
  typeVersion: 2.2,
  position: [1584, 496],
});

upsertNode({
  parameters: {
    method: 'POST',
    url: 'http://chatbot-api:8000/v1/operacao/roteamento',
    sendHeaders: true,
    headerParameters: {
      parameters: [{ name: 'X-Webhook-Token', value: '__CHATBOT_WEBHOOK_TOKEN__' }],
    },
    sendBody: true,
    specifyBody: 'json',
    jsonBody: "={{ { instance: $json.instance, telefone: $json.telefone, texto: $json.texto, grupo_jid: $json.grupoJid, is_saved: null } }}",
    options: { timeout: 8000 },
  },
  id: 'stock-group-route',
  name: 'Rotear grupo de estoque1',
  type: 'n8n-nodes-base.httpRequest',
  typeVersion: 4.2,
  position: [2008, 544],
  continueOnFail: true,
});

node('Gate somente nao salvos1').parameters.jsCode = `let chat = {};
try { chat = $('Consultar contato na Evolution1').first().json || {}; } catch (e) {}
const extraida = $('Extrair1').first().json;
let origem = extraida;
if (extraida.ehAudio) {
  try { origem = $('Aplicar transcricao1').first().json; } catch (e) {}
}
const rot = $input.first().json || {};
const acao = rot.acao;
const botAtivo = origem.bot_ativo !== false;
if (!acao) {
  if (origem.ehGrupo) return [];
  return (chat.isSaved === false && botAtivo) ? [{ json: { ...origem, acao: 'cliente' } }] : [];
}
if (acao === 'cliente') {
  if (origem.ehGrupo || !botAtivo) return [];
  return [{ json: { ...origem, acao } }];
}
if (acao === 'cadastro') {
  return [{ json: { ...origem, acao } }];
}
if (acao === 'cadastro_controle' || acao === 'operacao_controle') {
  const resposta = String(rot.resposta || '').trim();
  if (!resposta) return [];
  return [{ json: { ...origem, acao, audioFallback: resposta, output: resposta } }];
}
return [];
`;

const cadastroTool = node('cadastrar_veiculo1');
cadastroTool.parameters.jsCode = cadastroTool.parameters.jsCode.replace(
  'const body = {\n  telefone_solicitante,',
  "const body = {\n  telefone_solicitante,\n  grupo_jid: origem.ehGrupo ? origem.grupoJid : null,",
);
node('AI Agent1').parameters.options.systemMessage = node('AI Agent1')
  .parameters.options.systemMessage
  .replace('Se retornar 403, diga que o número não está autorizado.', 'Se retornar 403, diga que o grupo não está autorizado.');

upsertNode({
  parameters: {
    conditions: {
      options: {
        caseSensitive: true,
        leftValue: '',
        typeValidation: 'strict',
        version: 2,
      },
      conditions: [{
        id: 'stock-group-output-condition',
        leftValue: "={{ $('Extrair1').first().json.ehGrupo }}",
        rightValue: true,
        operator: { type: 'boolean', operation: 'true', singleValue: true },
      }],
      combinator: 'and',
    },
    options: {},
  },
  id: 'stock-group-output-if',
  name: 'E resposta de grupo1',
  type: 'n8n-nodes-base.if',
  typeVersion: 2.2,
  position: [2912, 416],
});
node('Registrar saida do bot1').position = [3120, 496];

workflow.connections['Salvar foto no estoque1'] = {
  main: [[{ node: 'Foto deve responder1', type: 'main', index: 0 }]],
};
workflow.connections['Foto deve responder1'] = {
  main: [[{ node: 'Responder cadastro de foto1', type: 'main', index: 0 }]],
};
workflow.connections['E audio1'].main[1] = [
  { node: 'E grupo de estoque1', type: 'main', index: 0 },
];
workflow.connections['E grupo de estoque1'] = {
  main: [
    [{ node: 'Rotear grupo de estoque1', type: 'main', index: 0 }],
    [{ node: 'Registrar mensagem e ler handoff1', type: 'main', index: 0 }],
  ],
};
workflow.connections['Rotear grupo de estoque1'] = {
  main: [[{ node: 'Gate somente nao salvos1', type: 'main', index: 0 }]],
};
workflow.connections['Responder WhatsApp1'] = {
  main: [[{ node: 'E resposta de grupo1', type: 'main', index: 0 }]],
};
workflow.connections['E resposta de grupo1'] = {
  main: [[], [{ node: 'Registrar saida do bot1', type: 'main', index: 0 }]],
};

fs.writeFileSync(workflowPath, `${JSON.stringify(workflow, null, 2)}\n`, 'utf8');
