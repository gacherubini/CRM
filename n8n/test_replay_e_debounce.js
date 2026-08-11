#!/usr/bin/env node
/* Regressão do incidente de 04/08: replay antigo e rajada multi-mensagem. */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const workflow = JSON.parse(
  fs.readFileSync(path.join(__dirname, "workflow-ai-nao-salvos.json"), "utf8")
);
const byName = Object.fromEntries(workflow.nodes.map((node) => [node.name, node]));

function runExtract(messageTimestamp, overrides = {}) {
  const code = byName.Extrair1.parameters.jsCode;
  const run = new Function("$input", code);
  const key = {
    remoteJid: overrides.remoteJid || "5511999999999@s.whatsapp.net",
    fromMe: overrides.fromMe === true,
    id: overrides.id || "MSG-IDADE-1",
    participant: overrides.participant,
  };
  return run({
    first: () => ({
      json: {
        body: {
          event: "messages.upsert",
          instance: "loja-teste",
          data: {
            key,
            messageTimestamp,
            message: { conversation: overrides.texto || "oi" },
          },
        },
      },
    }),
  });
}

const nowSeconds = Math.floor(Date.now() / 1000);
assert.deepStrictEqual(
  runExtract(nowSeconds - 3600),
  [],
  "mensagem de uma hora atrás não pode entrar no fluxo"
);
assert.deepStrictEqual(
  runExtract(undefined),
  [],
  "evento sem timestamp deve falhar fechado"
);
assert.strictEqual(runExtract(nowSeconds - 10).length, 1, "mensagem fresca deve entrar");
assert.strictEqual(
  runExtract({ low: nowSeconds - 10, high: 0, unsigned: true }).length,
  1,
  "timestamp protobuf da Evolution deve ser aceito"
);
assert.deepStrictEqual(
  runExtract(nowSeconds + 180),
  [],
  "timestamp muito no futuro deve ser rejeitado"
);
assert.deepStrictEqual(
  runExtract(nowSeconds - 5, {
    fromMe: true,
    remoteJid: "120363001@g.us",
    participant: "5511999990001@s.whatsapp.net",
  }),
  [],
  "eco fromMe no grupo de estoque não pode reentrar (anti-loop de menu)"
);
assert.strictEqual(
  runExtract(nowSeconds - 5, {
    remoteJid: "120363001@g.us",
    participant: "5511999990001@s.whatsapp.net",
    texto: "menu",
  }).length,
  1,
  "mensagem fresca da equipe no grupo deve entrar"
);
// fromMe privado ainda entra (Registrar handoff humano); o Gate handoff corta a IA.
assert.strictEqual(
  runExtract(nowSeconds - 5, { fromMe: true }).length,
  1,
  "fromMe privado deve passar pelo Extrair para registrar saída humana"
);

const waitName = "Aguardar 40s cliente1";
const checkName = "Verificar mensagem mais recente1";
const gateName = "Gate resposta mais recente1";
assert.ok(byName[checkName], `nó '${checkName}' ausente`);
assert.ok(byName[gateName], `nó '${gateName}' ausente`);

const next = (name, branch = 0) =>
  workflow.connections[name]?.main?.[branch]?.[0]?.node || null;
assert.strictEqual(next("Se resposta controle1", 1), waitName);
assert.strictEqual(next(waitName), checkName);
assert.strictEqual(next(checkName), gateName);
assert.strictEqual(next(gateName), "AI Agent1");
// AI Agent passa pelo atraso anti-ban (typing + throttle) antes do envio.
assert.strictEqual(next("AI Agent1"), "Atraso anti-ban1");
assert.strictEqual(next("Atraso anti-ban1"), "Responder WhatsApp1");

const checkJson = JSON.stringify(byName[checkName]);
assert.ok(checkJson.includes("/pode-responder"));
assert.ok(checkJson.includes("providerMessageId"));
assert.ok(checkJson.includes("Extrair1"));

const gateCode = byName[gateName].parameters.jsCode;
const gateFn = new Function("$", "$input", gateCode);
const origem = { telefone: "5511999999999", texto: "última mensagem", acao: "cliente" };
const $ = (name) => ({ first: () => ({ json: name === "Gate somente nao salvos1" ? origem : {} }) });
assert.deepStrictEqual(
  gateFn($, { first: () => ({ json: { pode_responder: false } }) }),
  [],
  "mensagem superada não pode chegar à IA"
);
assert.deepStrictEqual(
  gateFn($, { first: () => ({ json: { pode_responder: true } }) }),
  [{ json: origem }],
  "somente a mensagem mais recente deve chegar à IA"
);

console.log("ok - replay antigo bloqueado e rajada reduzida à mensagem mais recente");
