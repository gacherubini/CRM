#!/usr/bin/env node
/*
 * Atualiza o workflow canônico diretamente no SQLite do n8n self-hosted.
 *
 * Uso dentro do container n8n:
 *   node update_live_workflow.js canonical.json /home/node/.n8n/database.sqlite
 *   node update_live_workflow.js canonical.json /home/node/.n8n/database.sqlite --instance=loja1 --apply
 *
 * O modo padrão é somente leitura. No apply, cria backup consistente no mesmo
 * diretório do banco, preserva segredos/credenciais/IDs do workflow existente e
 * atualiza draft + versão ativa em uma transação. Nunca imprime credenciais.
 */
const fs = require("fs");
const path = require("path");

const canonicalPath = process.argv[2];
const databasePath = process.argv[3];
const apply = process.argv.includes("--apply");
const instanceArg = process.argv
  .find((value) => value.startsWith("--instance="))
  ?.slice("--instance=".length);
const workflowName = "WhatsApp IA - Somente Nao Salvos";

if (!canonicalPath || !databasePath) {
  console.error("uso: node update_live_workflow.js CANONICAL DB [--apply]");
  process.exit(2);
}

const sqliteModule = "/usr/local/lib/node_modules/n8n/node_modules/sqlite3";
const sqlite3 = require(sqliteModule);
const canonical = JSON.parse(fs.readFileSync(canonicalPath, "utf8"));
const db = new sqlite3.Database(databasePath);

const get = (sql, params = []) =>
  new Promise((resolve, reject) =>
    db.get(sql, params, (error, row) => (error ? reject(error) : resolve(row))),
  );
const run = (sql, params = []) =>
  new Promise((resolve, reject) =>
    db.run(sql, params, function done(error) {
      if (error) reject(error);
      else resolve(this.changes);
    }),
  );
const close = () => new Promise((resolve) => db.close(resolve));

function nodeByName(nodes, name) {
  return nodes.find((node) => node.name === name);
}

function headerValue(node, headerName) {
  const headers = node?.parameters?.headerParameters?.parameters || [];
  return String(
    headers.find((header) => header.name.toLowerCase() === headerName.toLowerCase())
      ?.value || "",
  );
}

function extractFromTemplate(template, actual, placeholder) {
  const parts = template.split(placeholder);
  if (parts.length !== 2 || !actual.startsWith(parts[0]) || !actual.endsWith(parts[1])) {
    throw new Error(`não foi possível preservar ${placeholder}`);
  }
  return actual.slice(parts[0].length, actual.length - parts[1].length);
}

function assertSecret(name, value) {
  if (!value || value.includes("__") || value.length > 4096) {
    throw new Error(`valor existente inválido para ${name}`);
  }
}

async function main() {
  const workflow = await get(
    "SELECT id,name,active,nodes,connections,versionId,activeVersionId " +
      "FROM workflow_entity WHERE name = ?",
    [workflowName],
  );
  if (!workflow) throw new Error("workflow ativo não encontrado");
  if (!workflow.activeVersionId) throw new Error("workflow sem versão ativa");

  const existingNodes = JSON.parse(workflow.nodes);
  const canonicalNodes = canonical.nodes;

  const existingEvolution = nodeByName(existingNodes, "Consultar contato na Evolution1");
  const canonicalEvolution = nodeByName(canonicalNodes, "Consultar contato na Evolution1");
  const existingWebhook = nodeByName(
    existingNodes,
    "Registrar mensagem e ler handoff1",
  );
  const existingInventory = nodeByName(existingNodes, "consultar_estoque1");

  const extractedInstance = extractFromTemplate(
    canonicalEvolution.parameters.url,
    existingEvolution.parameters.url,
    "__INSTANCE__",
  );
  const instance =
    extractedInstance && !extractedInstance.includes("__")
      ? extractedInstance
      : instanceArg;
  const evolutionKey = headerValue(existingEvolution, "apikey");
  const webhookToken = headerValue(existingWebhook, "X-Webhook-Token");
  const inventoryCode = String(existingInventory?.parameters?.jsCode || "");
  const chatbotMatch = inventoryCode.match(/Authorization:\s*'Bearer ([^']+)'/);
  const chatbotToken = chatbotMatch ? chatbotMatch[1] : "";

  const replacements = {
    __INSTANCE__: instance,
    __EVOLUTION_KEY__: evolutionKey,
    __CHATBOT_WEBHOOK_TOKEN__: webhookToken,
    __CHATBOT_TOKEN__: chatbotToken,
  };
  for (const [name, value] of Object.entries(replacements)) assertSecret(name, value);

  let serialized = JSON.stringify({
    nodes: canonical.nodes,
    connections: canonical.connections,
  });
  for (const [placeholder, value] of Object.entries(replacements)) {
    serialized = serialized.split(placeholder).join(value);
  }
  const merged = JSON.parse(serialized);
  const existingByName = new Map(existingNodes.map((node) => [node.name, node]));
  for (const node of merged.nodes) {
    const old = existingByName.get(node.name);
    if (!old) continue;
    node.id = old.id;
    if (old.webhookId) node.webhookId = old.webhookId;
    if (old.credentials) node.credentials = old.credentials;
  }

  const summary = {
    workflowId: workflow.id,
    active: Boolean(workflow.active),
    previousNodes: existingNodes.length,
    canonicalNodes: merged.nodes.length,
    mode: apply ? "apply" : "preview",
  };
  if (!apply) {
    console.log(JSON.stringify(summary));
    return;
  }

  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "");
  const backupPath = path.join(path.dirname(databasePath), `database.before-workflow-${stamp}.sqlite`);
  await run("VACUUM INTO ?", [backupPath]);

  const nodesJson = JSON.stringify(merged.nodes);
  const connectionsJson = JSON.stringify(merged.connections);
  await run("BEGIN IMMEDIATE");
  try {
    const workflowChanges = await run(
      "UPDATE workflow_entity SET nodes=?, connections=?, updatedAt=CURRENT_TIMESTAMP WHERE id=?",
      [nodesJson, connectionsJson, workflow.id],
    );
    const historyChanges = await run(
      "UPDATE workflow_history SET nodes=?, connections=?, updatedAt=CURRENT_TIMESTAMP " +
        "WHERE workflowId=? AND versionId IN (?,?)",
      [
        nodesJson,
        connectionsJson,
        workflow.id,
        workflow.versionId,
        workflow.activeVersionId,
      ],
    );
    if (workflowChanges !== 1 || historyChanges < 1) {
      throw new Error("linhas esperadas do workflow não foram atualizadas");
    }
    await run("COMMIT");
  } catch (error) {
    await run("ROLLBACK");
    throw error;
  }

  const verified = await get(
    "SELECT nodes FROM workflow_history WHERE versionId=?",
    [workflow.activeVersionId],
  );
  if (!verified || JSON.parse(verified.nodes).length !== merged.nodes.length) {
    throw new Error("verificação da versão ativa falhou");
  }
  console.log(JSON.stringify({ ...summary, backup: path.basename(backupPath) }));
}

main()
  .catch((error) => {
    console.error(`erro: ${error.message}`);
    process.exitCode = 1;
  })
  .finally(close);
