#!/usr/bin/env node
/*
 * Roda os nós-ponte do preview fora do n8n.
 *
 * Eles existem porque as ferramentas do agente, herdadas byte a byte, citam
 * `$('Extrair1')`, `$('Registrar mensagem e ler handoff1')` e
 * `$('Gate config do agente1')` — nomes de nós que um workflow de entrada HTTP
 * não teria. Cada ponte errada é uma falha que só aparece quando o lojista
 * clica em Testar.
 *
 * `node n8n/test_pontes_preview.js`
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const wf = JSON.parse(
  fs.readFileSync(path.join(__dirname, 'workflow-preview.json'), 'utf8'),
);
const codigo = (nome) => {
  const n = wf.nodes.find((x) => x.name === nome);
  assert(n, `${nome} não existe no preview`);
  return n.parameters.jsCode;
};

const CORPO = {
  instance: 'inst-a',
  telefone: '0244798567928',
  texto: 'oi, tem biz 2020?',
  prompt: '[IDENTIDADE]\nvocê atende os clientes da motos do léo pelo whatsapp.\n\n[REGRAS DO REVY — PREVALECEM SOBRE TUDO ACIMA]\n1. ...',
  historico: '- [entrada] oi\n- [saida] oi, tudo bem?',
  saida_minusculas: false,
  saida_sem_emoji: false,
  turno: 3,
  primeira_mensagem: false,
};

function rodar(js, { input, nos = {} }) {
  const $input = { first: () => ({ json: input }) };
  const $ = (nome) => {
    assert(nome in nos, `nó inesperado: ${nome}`);
    return { first: () => ({ json: nos[nome] }) };
  };
  // eslint-disable-next-line no-new-func
  return new Function('$input', '$', js)($input, $);
}

// --- Extrair1: o formato que TODA ferramenta espera -------------------------
let extraido;
{
  // O webhook do n8n entrega { body, headers, query }.
  const saida = rodar(codigo('Extrair1'), { input: { body: CORPO } });
  assert.strictEqual(saida.length, 1);
  extraido = saida[0].json;
  assert.strictEqual(extraido.telefone, CORPO.telefone);
  assert.strictEqual(extraido.destino, CORPO.telefone);
  assert.strictEqual(extraido.instance, CORPO.instance);
  assert.strictEqual(extraido.texto, CORPO.texto);
  assert.strictEqual(extraido.fromMe, false);
  assert.strictEqual(extraido.ehGrupo, false, 'grupo ligaria o caminho de cadastro de estoque');
  assert(extraido.providerMessageId, 'simular1 recusa turno sem providerMessageId');
  assert.strictEqual(extraido.historico_recente, CORPO.historico);

  // O telefone sintético tem que sobreviver ao replace(/\D/g,'') das tools.
  assert.strictEqual(String(extraido.telefone).replace(/\D/g, ''), CORPO.telefone);

  // Fail-closed: sem loja não há estoque para consultar nem prompt para aplicar.
  assert.deepStrictEqual(rodar(codigo('Extrair1'), { input: { body: {} } }), []);
  assert.deepStrictEqual(
    rodar(codigo('Extrair1'), { input: { body: { telefone: '0244798567928' } } }),
    [],
    'sem instance o preview testaria contra o estoque de outra loja',
  );
}

// --- turnos diferentes, providerMessageId diferente -------------------------
{
  const t1 = rodar(codigo('Extrair1'), { input: { body: { ...CORPO, turno: 1 } } })[0].json;
  const t2 = rodar(codigo('Extrair1'), { input: { body: { ...CORPO, turno: 2 } } })[0].json;
  assert.notStrictEqual(
    t1.providerMessageId,
    t2.providerMessageId,
    'simular1 deduplica por providerMessageId: turno repetido seria engolido',
  );
}

// --- ponte do registro ------------------------------------------------------
{
  const saida = rodar(codigo('Registrar mensagem e ler handoff1'), {
    input: {},
    nos: { Extrair1: extraido },
  });
  assert.strictEqual(saida[0].json.historico_recente, CORPO.historico);
  assert.strictEqual(saida[0].json.bot_ativo, true);
}

// --- ponte do gate ----------------------------------------------------------
{
  const saida = rodar(codigo('Gate somente nao salvos1'), {
    input: {},
    nos: { Extrair1: extraido },
  });
  assert.strictEqual(saida[0].json.acao, 'cliente', 'num preview toda mensagem é de cliente');
  assert.strictEqual(saida[0].json.telefone, CORPO.telefone);
}

// --- ponte da config: o prompt é o do RASCUNHO ------------------------------
{
  const saida = rodar(codigo('Gate config do agente1'), {
    input: {},
    nos: { 'Webhook preview': { body: CORPO }, Extrair1: extraido },
  });
  assert.strictEqual(saida[0].json.promptAgente, CORPO.prompt);
  assert.strictEqual(saida[0].json.saidaMinusculas, false, 'a escolha da loja tem que chegar ao envio');
  assert.strictEqual(saida[0].json.saidaSemEmoji, false);
  assert.strictEqual(saida[0].json.telefone, CORPO.telefone, 'o AI Agent lê telefone de $json');

  // Sem prompt, falhar alto: cair num padrão mostraria ao lojista um agente que
  // não é o dele, e ele corrigiria a configuração errada.
  assert.throws(
    () =>
      rodar(codigo('Gate config do agente1'), {
        input: {},
        nos: { 'Webhook preview': { body: { ...CORPO, prompt: '' } }, Extrair1: extraido },
      }),
    /prompt/,
  );
}

console.log('pontes do preview OK: formato do Modo 1, fail-closed sem loja, prompt do rascunho');
