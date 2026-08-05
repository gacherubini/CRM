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
assert.ok(
  /simulacao_humana_solicitada/i.test(prompt) || /ok:true/i.test(prompt),
  "prompt deve proibir confirmação de simulação sem sucesso da tool"
);

// n8n ToolCode injeta o item pai no argumento. additionalProperties:false quebra em runtime.
const schemaRaw = String(node.parameters.inputSchema || "");
const schema = JSON.parse(schemaRaw);
assert.strictEqual(
  schema.additionalProperties,
  true,
  "schema TEMP deve tolerar contexto do webhook (instance, telefone, providerMessageId…)"
);
const enrichedLikeProd = {
  interesse: "Honda CG Fan 160 2024",
  confirmar_simulacao: true,
  cpf: "11144477735",
  nascimento: "10/02/1995",
  entrada: 5000,
  // Campos que o n8n anexa e que quebravam com additionalProperties:false (exec 12413).
  instance: "loja-teste",
  remoteJid: "5511999999999@s.whatsapp.net",
  telefone: "5511999999999",
  providerMessageId: "TEMP-MSG-ENRICHED",
  toolCallId: "call_synthetic_1",
  pushName: "Cliente",
};
for (const key of Object.keys(enrichedLikeProd)) {
  if (schema.properties && schema.properties[key]) continue;
  assert.notStrictEqual(
    schema.additionalProperties,
    false,
    `campo extra '${key}' seria rejeitado com additionalProperties false`
  );
}

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
    if (
      request.method === "POST" &&
      String(request.url || "").includes("/solicitacoes-simulacao-humana")
    ) {
      return {
        ok: true,
        simulacao_humana_solicitada: true,
        mensagem: "certinho. vou preparar a simulação pra você.",
      };
    }
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
  assert.deepStrictEqual(missing.faltando, ["cpf", "data de nascimento"]);
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
  assert.strictEqual(completed.ok, true);
  assert.strictEqual(completed.simulacao_humana_solicitada, true);
  assert.strictEqual(completed.mensagem, "certinho. vou preparar a simulação pra você.");
  assert.ok(
    requests.some(
      (request) =>
        request.method === "POST" &&
        String(request.url).includes("/solicitacoes-simulacao-humana")
    ),
    "deve chamar o endpoint canônico de simulação humana"
  );
  assert.ok(
    requests.every((request) => !String(request.url).includes("/v1/simulacoes/solicitar")),
    "sem preço/placa do estoque não pode disparar o motor"
  );
  assert.ok(
    requests.every((request) => !String(request.url).includes("/message/sendText/")),
    "envio ao grupo fica no Chatbot, não na tool"
  );

  // Objeto enriquecido como na execução real (schema + jsCode).
  requests.length = 0;
  const enriched = JSON.parse(
    await runTool(
      {
        confirmar_simulacao: true,
        cpf: "11144477735",
        nascimento: "10/02/1995",
        entrada: 5000,
        instance: "loja-teste",
        remoteJid: "5511999999999@s.whatsapp.net",
        telefone: "5511999999999",
        providerMessageId: "TEMP-MSG-ENRICHED",
        toolCallId: "call_synthetic_1",
      },
      helpers,
      $,
      staticData
    )
  );
  assert.strictEqual(enriched.ok, true);
  assert.strictEqual(enriched.simulacao_humana_solicitada, true);

  console.log("ok - fallback temporário oferece simulação sem foto e conclui em handoff");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
