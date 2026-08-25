#!/usr/bin/env node
/*
 * Roda o jsCode do `Gate config do agente1` fora do n8n, com $input e $() de
 * mentira. Ele decide três coisas que só se veem em produção, e cada uma erra
 * de um jeito caro:
 *
 *   200 -> prompt da loja        (errar = todas as lojas falando igual)
 *   423 -> PARA                  (errar = loja suspensa sendo atendida pelo bot)
 *   resto -> padrão Revy         (errar = bot mudo quando a rota pisca)
 *
 * `node n8n/test_gate_config_agente.js`
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

function jsCodeDe(arquivo, no) {
  const wf = JSON.parse(fs.readFileSync(path.join(__dirname, arquivo), 'utf8'));
  const node = wf.nodes.find((n) => n.name === no);
  assert(node, `${no} não existe em ${arquivo}`);
  return node.parameters.jsCode;
}

const ORIGEM = {
  telefone: '5519999999999',
  instance: 'inst-a',
  pushName: 'Ana',
  primeiraMensagem: true,
  veioDeAnuncio: false,
};

function rodar(codigo, respostaHttp) {
  const $input = { first: () => ({ json: respostaHttp }) };
  const $ = (nome) => {
    if (nome === 'Gate resposta mais recente1') return { first: () => ({ json: ORIGEM }) };
    throw new Error(`nó inesperado: ${nome}`);
  };
  // eslint-disable-next-line no-new-func
  return new Function('$input', '$', `${codigo}`)($input, $);
}

const codigo = jsCodeDe('workflow-ai-nao-salvos.json', 'Gate config do agente1');

// --- 200: usa o prompt da loja ---------------------------------------------
{
  const saida = rodar(codigo, {
    statusCode: 200,
    body: {
      prompt: '[IDENTIDADE]\nvocê atende os clientes da motos do léo pelo whatsapp.',
      saida: { minusculas: false, sem_emoji: false },
    },
  });
  assert.strictEqual(saida.length, 1);
  assert.match(saida[0].json.promptAgente, /motos do léo/);
  assert.strictEqual(saida[0].json.configDaLoja, true);
  assert.strictEqual(saida[0].json.saidaMinusculas, false, 'escrita normal tem que chegar ao envio');
  assert.strictEqual(saida[0].json.saidaSemEmoji, false, 'emoji à vontade tem que chegar ao envio');
  assert.strictEqual(saida[0].json.telefone, ORIGEM.telefone, 'o item do turno tem que seguir adiante');
  assert.strictEqual(saida[0].json.pushName, 'Ana');
}

// --- 423: loja suspensa PARA o fluxo ---------------------------------------
{
  const saida = rodar(codigo, { statusCode: 423, body: { detail: 'loja não operacional' } });
  assert.deepStrictEqual(
    saida,
    [],
    '423 caindo no fallback deixaria loja suspensa sendo atendida pelo bot',
  );
}

// --- falha técnica: padrão Revy, o bot nunca fica sem prompt ----------------
for (const falha of [
  { statusCode: 500, body: {} },
  { statusCode: 502, body: 'gateway' },
  { error: 'ECONNREFUSED' },
  { statusCode: 200, body: { prompt: '   ' } },
]) {
  const saida = rodar(codigo, falha);
  assert.strictEqual(saida.length, 1, `falha ${JSON.stringify(falha)} não pode parar o bot`);
  assert.match(saida[0].json.promptAgente, /REGRAS DO REVY/);
  assert.strictEqual(saida[0].json.configDaLoja, false);
  assert.strictEqual(saida[0].json.saidaMinusculas, true, 'default conservador');
  assert.strictEqual(saida[0].json.saidaSemEmoji, true, 'default conservador');
}

// --- o núcleo é o último bloco do fallback ---------------------------------
{
  const saida = rodar(codigo, { statusCode: 500, body: {} });
  const prompt = saida[0].json.promptAgente.trimEnd();
  const nucleo = prompt.indexOf('[REGRAS DO REVY');
  assert(nucleo !== -1, 'fallback sem núcleo');
  assert(
    !prompt.slice(nucleo).includes('[IDENTIDADE]'),
    'algo foi colado depois do núcleo — ele para de prevalecer',
  );
}

// --- o Modo 2 herda o mesmo nó, byte a byte --------------------------------
assert.strictEqual(
  jsCodeDe('workflow-cloud.json', 'Gate config do agente1'),
  codigo,
  'o fork do Modo 2 divergiu do Modo 1: rode `python n8n/fork_cloud_workflow.py`',
);

console.log('gate da config do agente OK: 200 usa a loja, 423 para, falha cai no padrão');
