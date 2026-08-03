#!/usr/bin/env node
/*
 * Testa o nó "Gate somente nao salvos1" do workflow canônico rodando o jsCode
 * real extraído do JSON. Regra: atende só lead virgem (não salvo na agenda E
 * sem histórico), respeita handoff, fail-open na dúvida.
 * Sem segredos, sem rede: só lógica pura do gate.
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const wf = JSON.parse(
  fs.readFileSync(path.join(__dirname, "workflow-ai-nao-salvos.json"), "utf8")
);
const gateNode = wf.nodes.find((n) => n.name === "Gate somente nao salvos1");
if (!gateNode) throw new Error("nó 'Gate somente nao salvos1' não encontrado");
const gateFn = new Function("$", "$input", gateNode.parameters.jsCode);

function runGate({ chat = {}, origem = {}, estado = {}, rot = {} }) {
  const nodes = {
    "Normalizar isSaved Evolution1": chat,
    Extrair1: origem,
    "Registrar mensagem e ler handoff1": estado,
  };
  const $ = (name) => ({ first: () => ({ json: nodes[name] }) });
  const $input = { first: () => ({ json: rot }) };
  const out = gateFn($, $input);
  return Array.isArray(out) ? out : [];
}
const atende = (r) => r.length === 1 && r[0].json.acao === "cliente";

const casos = [
  {
    nome: "S1 salvo na agenda -> silêncio",
    entrada: {
      chat: { isSaved: true, chatFound: true },
      estado: { primeira_mensagem: false, bot_ativo: true },
      origem: { ehGrupo: false },
    },
    esperado: false,
  },
  {
    nome: "S2 não salvo COM histórico -> silêncio (incômodo principal)",
    entrada: {
      chat: { isSaved: false, chatFound: true },
      estado: { primeira_mensagem: false, bot_ativo: true },
      origem: { ehGrupo: false },
    },
    esperado: false,
  },
  {
    nome: "S3 virgem (findChats vazio) -> atende",
    entrada: {
      chat: { isSaved: null, chatFound: false },
      estado: { primeira_mensagem: true, bot_ativo: true },
      origem: { ehGrupo: false, veioDeAnuncio: false },
    },
    esperado: true,
  },
  {
    nome: "S4 virgem de anúncio -> atende (fail-open)",
    entrada: {
      chat: { isSaved: null, chatFound: false },
      estado: { primeira_mensagem: true, bot_ativo: true },
      origem: { ehGrupo: false, veioDeAnuncio: true },
    },
    esperado: true,
  },
  {
    nome: "S5 handoff sobre não-salvo -> silêncio (bug de handoff)",
    entrada: {
      chat: { isSaved: false, chatFound: true },
      estado: { primeira_mensagem: false, bot_ativo: false },
      origem: { ehGrupo: false },
    },
    esperado: false,
  },
  {
    nome: "S6 handoff no 2º passe (acao=cliente) -> silêncio",
    entrada: {
      chat: {},
      estado: { bot_ativo: false },
      origem: { ehGrupo: false },
      rot: { acao: "cliente" },
    },
    esperado: false,
  },
  {
    nome: "S7 bot já falou (Evolution cega, primeira_mensagem false) -> silêncio",
    entrada: {
      chat: { isSaved: null, chatFound: false },
      estado: { primeira_mensagem: false, bot_ativo: true },
      origem: { ehGrupo: false },
    },
    esperado: false,
  },
  {
    nome: "S8 grupo -> silêncio",
    entrada: {
      chat: { isSaved: null, chatFound: false },
      estado: { primeira_mensagem: true, bot_ativo: true },
      origem: { ehGrupo: true },
    },
    esperado: false,
  },
];

let falhas = 0;
for (const c of casos) {
  const got = atende(runGate(c.entrada));
  try {
    assert.strictEqual(got, c.esperado);
    console.log("ok  -", c.nome);
  } catch (_) {
    falhas++;
    console.error(`FALHOU - ${c.nome} (esperado atende=${c.esperado}, obtido=${got})`);
  }
}
if (falhas) {
  console.error(`\n${falhas} cenário(s) falharam`);
  process.exit(1);
}
console.log(`\n${casos.length} cenários passaram`);
