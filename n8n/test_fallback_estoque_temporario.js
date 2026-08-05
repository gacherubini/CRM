#!/usr/bin/env node
/* Contrato removível do fallback enquanto o estoque digital está incompleto. */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const workflow = JSON.parse(
  fs.readFileSync(path.join(__dirname, "workflow-ai-nao-salvos.json"), "utf8")
);
const name = "TEMP continuar sem estoque1";
const node = workflow.nodes.find((candidate) => candidate.name === name);
assert.ok(node, `nó temporário '${name}' ausente`);
assert.strictEqual(node.type, "@n8n/n8n-nodes-langchain.toolCode");
assert.ok(node.parameters.description.includes("TEMPORÁRIO"));
assert.ok(node.parameters.description.toLowerCase().includes("não oferece fotos"));

const toolConnections = workflow.connections[name]?.ai_tool || [];
assert.ok(
  toolConnections.flat().some((edge) => edge.node === "AI Agent1"),
  "nó temporário não está conectado ao Agent"
);

const inventory = workflow.nodes.find((candidate) => candidate.name === "consultar_estoque1");
assert.ok(inventory.parameters.description.includes(name));
const prompt = workflow.nodes.find((candidate) => candidate.name === "AI Agent1")
  .parameters.options.systemMessage;
assert.ok(prompt.includes("[TEMP_ESTOQUE_INCOMPLETO_INICIO]"));
assert.ok(prompt.includes("[TEMP_ESTOQUE_INCOMPLETO_FIM]"));
assert.ok(prompt.includes(name));

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const runTool = new AsyncFunction(
  "query",
  "helpers",
  "$",
  "$getWorkflowStaticData",
  node.parameters.jsCode
);
const state = {};
const requests = [];
const helpers = {
  httpRequest: async (request) => {
    requests.push(request);
    if (request.method === "GET") return { numeros: [] };
    return { ok: true };
  },
};
const origin = {
  instance: "loja-teste",
  telefone: "5511999999999",
  providerMessageId: "TEMP-MSG-1",
  pushName: "Cliente",
  anuncioDescricao: "Honda CG Fan 160 2024",
};
const $ = (nodeName) => ({
  first: () => ({ json: nodeName === "Extrair1" ? origin : {} }),
});
const staticData = () => state;

(async () => {
  const offer = JSON.parse(
    await runTool(
      { interesse: "Honda CG Fan 160 2024" },
      helpers,
      $,
      staticData
    )
  );
  assert.strictEqual(offer.fallback_temporario, true);
  assert.strictEqual(offer.pode_oferecer_fotos, false);
  assert.strictEqual(offer.pode_oferecer_simulacao, true);
  assert.ok(offer.mensagem.includes("quer que eu simule"));
  assert.deepStrictEqual(requests, [], "oferta não deve criar lead nem chamar motor");

  const missing = JSON.parse(
    await runTool(
      { confirmar_simulacao: true },
      helpers,
      $,
      staticData
    )
  );
  assert.deepStrictEqual(missing.faltando, ["cpf", "data de nascimento", "valor de entrada"]);
  assert.strictEqual(missing.pode_oferecer_fotos, false);
  assert.deepStrictEqual(requests, [], "dados incompletos não devem produzir efeitos");

  const completed = JSON.parse(
    await runTool(
      {
        confirmar_simulacao: true,
        cpf: "11144477735",
        nascimento: "10/02/1995",
        entrada: 5000,
      },
      helpers,
      $,
      staticData
    )
  );
  assert.strictEqual(completed.simulacao_humana_solicitada, true);
  assert.strictEqual(completed.mensagem, "certinho. vou preparar a simulação pra você.");
  assert.ok(requests.some((request) => request.method === "POST" && request.url.endsWith("/v1/leads")));
  assert.ok(requests.some((request) => request.method === "PATCH" && request.url.includes("/estado")));
  assert.ok(
    requests.every((request) => !request.url.includes("/v1/simulacoes/solicitar")),
    "sem preço/placa do estoque não pode disparar o motor"
  );

  console.log("ok - fallback temporário oferece simulação sem foto e conclui em handoff");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
