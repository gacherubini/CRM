#!/usr/bin/env node
/*
 * Passa TODA expressão dos quatro workflows pelo motor que o n8n usa de verdade
 * (`@n8n/tournament`).
 *
 * Existe por causa do agente por loja: o `systemMessage` do `AI Agent1` deixou de
 * ser texto e virou uma expressão de ~17 mil caracteres, com chaves soltas,
 * aspas tipográficas e um `{{ }}` no fim. Nenhum validador de forma diz se isso
 * *parseia* — e o sintoma de não parsear é o bot mudo em produção, depois de um
 * import que o n8n aceitou sem reclamar.
 *
 * O que ele prova, e o resto não prova:
 *   - as 46 expressões compilam no parser do n8n;
 *   - o slot do prompt da loja resolve;
 *   - o texto resolvido **termina** no prompt da loja (o núcleo continua sendo o
 *     último bloco, que é o mecanismo de segurança inteiro).
 *
 * Precisa de uma dependência que o repo não carrega. Sem ela, o teste **pula**:
 *
 *     npm install --no-save @n8n/tournament
 *     node n8n/test_expressoes.js
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

let Tournament;
try {
  ({ Tournament } = require('@n8n/tournament'));
} catch (e) {
  console.log(
    'pulado: @n8n/tournament não está instalado.\n' +
      '  npm install --no-save @n8n/tournament && node n8n/test_expressoes.js',
  );
  process.exit(0);
}

const WORKFLOWS = [
  'workflow-ai-nao-salvos.json',
  'workflow-cloud.json',
  'workflow-preview.json',
  'workflow-teste-numero-autorizado.json',
];

const SLOT = "{{ $('Gate config do agente1').first().json.promptAgente }}";
const PROMPT_DA_LOJA =
  '[IDENTIDADE]\nvocê atende os clientes da motos do léo pelo whatsapp.';

const NOS = {
  'Gate config do agente1': {
    promptAgente: PROMPT_DA_LOJA,
    saidaMinusculas: true,
    saidaSemEmoji: true,
  },
  'Gate somente nao salvos1': { acao: 'cliente' },
  Extrair1: { destino: '5519999999999', telefone: '5519999999999', instance: 'inst-a' },
  'Registrar mensagem e ler handoff1': { historico_recente: '- [entrada] oi' },
  'Webhook preview': { body: { prompt: PROMPT_DA_LOJA, saida_minusculas: true } },
};

const ESCOPO = {
  $json: { output: 'Beleza! 😀', telefone: '5519999999999', texto: 'oi', __delayAntiBan: 900 },
  $: (nome) => ({ first: () => ({ json: NOS[nome] }), item: { json: NOS[nome] } }),
  // O sandbox não herda os globais do node; o n8n injeta os dele.
  String, Number, Boolean, Array, Object, JSON, Math, encodeURIComponent, RegExp, Date,
};

const tournament = new Tournament((e) => {
  throw e;
});

let total = 0;
let comSlot = 0;
for (const arquivo of WORKFLOWS) {
  const wf = JSON.parse(fs.readFileSync(path.join(__dirname, arquivo), 'utf8'));
  for (const no of wf.nodes) {
    const p = no.parameters || {};
    for (const [campo, valor] of Object.entries({ ...p, ...(p.options || {}) })) {
      if (typeof valor !== 'string' || !valor.startsWith('=') || !valor.includes('{{')) continue;
      total++;
      let resolvido;
      try {
        resolvido = tournament.execute(valor.slice(1), ESCOPO);
      } catch (e) {
        assert.fail(`${arquivo} / ${no.name} / ${campo} não compila: ${e.message}`);
      }
      if (!valor.includes(SLOT)) continue;
      comSlot++;
      const texto = String(resolvido);
      assert(!texto.includes('{{'), `${arquivo}: sobrou {{ no ${campo} resolvido`);
      assert(
        texto.includes('motos do léo'),
        `${arquivo}: o prompt da loja não entrou no ${campo}`,
      );
      assert(
        texto.trimEnd().endsWith(PROMPT_DA_LOJA.trimEnd()),
        `${arquivo}: algo foi colado depois do prompt da loja — o núcleo Revy deixa ` +
          'de ser o último bloco e para de prevalecer',
      );
    }
  }
}

assert.strictEqual(comSlot, WORKFLOWS.length, 'todo workflow com agente tem que trazer o slot');
console.log(
  `expressões OK: ${total} compilam no motor do n8n, e nos ${comSlot} workflows com ` +
    'agente o prompt da loja é a última coisa da system message',
);
