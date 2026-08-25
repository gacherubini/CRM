#!/usr/bin/env node
/*
 * Roda a expressão que higieniza a resposta antes de ela sair, nos três lugares
 * onde ela vive: Modo 1, Modo 2 e preview.
 *
 * Ela deixou de ser incondicional quando `escrita` e `emoji` viraram campos da
 * loja — se voltasse a ser, os dois campos seriam decorativos: o lojista
 * escolheria "pontuação normal" na tela e o WhatsApp continuaria em minúsculas,
 * sem erro e sem log. E o caminho do menu da equipe, que não passa pelo gate de
 * config, não pode quebrar por causa disso.
 *
 * `node n8n/test_higienizacao_saida.js`
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

function corpoDe(arquivo, no, campo) {
  const wf = JSON.parse(fs.readFileSync(path.join(__dirname, arquivo), 'utf8'));
  const node = wf.nodes.find((n) => n.name === no);
  assert(node, `${no} não existe em ${arquivo}`);
  const bruto = node.parameters[campo];
  assert(bruto.startsWith('={{ ') && bruto.endsWith(' }}'), `${no}.${campo} não é expressão`);
  return bruto.slice(4, -3);
}

// Avalia a expressão com os nós de mentira que ela cita. `ausentes` simula o nó
// que não rodou nesta execução — em n8n, $('Nó') levanta nesse caso.
function avaliar(expr, { json, nos, ausentes = [] }) {
  const $ = (nome) => {
    if (ausentes.includes(nome)) throw new Error(`nó ${nome} não executou`);
    assert(nome in nos, `nó inesperado: ${nome}`);
    return { first: () => ({ json: nos[nome] }) };
  };
  // eslint-disable-next-line no-new-func
  return new Function('$json', '$', `return (${expr});`)(json, $);
}

const EXTRAIR = { destino: '5519999999999', telefone: '5519999999999', instance: 'inst-a' };
const CRU = 'Beleza! Temos essa moto sim 😀 me conta, o que você prefere?';

// --- Modo 1 -----------------------------------------------------------------
{
  const expr = corpoDe('workflow-ai-nao-salvos.json', 'Responder WhatsApp1', 'jsonBody');

  const higienizada = avaliar(expr, {
    json: { output: CRU, __delayAntiBan: 1200 },
    nos: {
      'Gate somente nao salvos1': { acao: 'cliente' },
      'Gate config do agente1': { saidaMinusculas: true, saidaSemEmoji: true },
      Extrair1: EXTRAIR,
    },
  });
  assert.strictEqual(higienizada.text, 'beleza. temos essa moto sim o que você prefere?');
  assert.strictEqual(higienizada.delay, 1200, 'o atraso anti-ban tem que continuar chegando');
  assert.strictEqual(higienizada.number, EXTRAIR.destino);

  const solta = avaliar(expr, {
    json: { output: CRU, __delayAntiBan: 0 },
    nos: {
      'Gate somente nao salvos1': { acao: 'cliente' },
      'Gate config do agente1': { saidaMinusculas: false, saidaSemEmoji: false },
      Extrair1: EXTRAIR,
    },
  });
  assert.match(solta.text, /^Beleza!/, 'loja com pontuação normal perdeu a maiúscula e o "!"');
  assert.match(solta.text, /😀/, 'loja com emoji à vontade perdeu o emoji');
  assert(!solta.text.includes('me conta'), 'o bordão recusado sai em qualquer loja');

  // O menu da equipe não passa pelo gate de config. Antes desta feature o nó nem
  // citava o gate; agora cita, e ali ele não executou.
  const menu = avaliar(expr, {
    json: { output: 'MENU\n1 - Cadastrar', __delayAntiBan: 0 },
    nos: { 'Gate somente nao salvos1': { acao: 'cadastro_controle' }, Extrair1: EXTRAIR },
    ausentes: ['Gate config do agente1'],
  });
  assert.strictEqual(menu.text, 'MENU\n1 - Cadastrar', 'menu da equipe sai cru, e não pode quebrar');
}

// --- Modo 2 -----------------------------------------------------------------
{
  const expr = corpoDe('workflow-cloud.json', 'Responder WhatsApp1', 'jsonBody');
  const saida = avaliar(expr, {
    json: { output: CRU },
    nos: {
      'Gate config do agente1': { saidaMinusculas: false, saidaSemEmoji: false },
      Extrair1: EXTRAIR,
    },
  });
  assert.match(saida.texto, /^Beleza!/);
  assert.match(saida.texto, /😀/);
  assert.strictEqual(saida.instance, EXTRAIR.instance, 'sem instance a resposta sai pelo número errado');
}

// --- preview ----------------------------------------------------------------
{
  const expr = corpoDe('workflow-preview.json', 'Responder preview', 'responseBody');
  const saida = avaliar(expr, {
    json: { output: CRU },
    nos: { 'Gate config do agente1': { saidaMinusculas: true, saidaSemEmoji: true } },
  });
  assert.strictEqual(
    saida.texto,
    'beleza. temos essa moto sim o que você prefere?',
    'o preview tem que mostrar o que o cliente leria, não o cru do modelo',
  );
}

console.log('higienização OK: obedece a loja nos 3 modos, e o menu da equipe sai cru');
