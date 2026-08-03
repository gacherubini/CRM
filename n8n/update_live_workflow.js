#!/usr/bin/env node
/*
 * Atualiza o workflow canônico diretamente no SQLite do n8n self-hosted.
 *
 * Uso dentro do container n8n:
 *   node update_live_workflow.js canonical.json /home/node/.n8n/database.sqlite
 *   node update_live_workflow.js canonical.json /home/node/.n8n/database.sqlite \
 *     --instance=loja1 \
 *     --chatbot-base-url=http://chatbot2037.flycast:8000 \
 *     --evolution-base-url=http://evolution2037.flycast:8080 \
 *     --apply
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
const argValue = (prefix) =>
  process.argv.find((value) => value.startsWith(prefix))?.slice(prefix.length);
const instanceArg = argValue("--instance=");
const chatbotBaseArg = argValue("--chatbot-base-url=");
const evolutionBaseArg = argValue("--evolution-base-url=");
const workflowName = "WhatsApp IA - Somente Nao Salvos";
const canonicalChatbotBase = "http://chatbot-api:8000";
const canonicalEvolutionBase = "http://evolution:8080";

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

function tryExtractFromTemplate(template, actual, placeholder) {
  const parts = template.split(placeholder);
  if (parts.length !== 2 || !actual.startsWith(parts[0]) || !actual.endsWith(parts[1])) {
    return "";
  }
  return actual.slice(parts[0].length, actual.length - parts[1].length);
}

function normalizeBaseUrl(name, value, fallback) {
  const candidate = value || fallback;
  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error(`${name} inválida`);
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    !parsed.hostname ||
    !["", "/"].includes(parsed.pathname)
  ) {
    throw new Error(`${name} deve conter somente protocolo, host e porta opcional`);
  }
  return `${parsed.protocol}//${parsed.host}`;
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
  const targetVersionId = workflow.activeVersionId || workflow.versionId;
  if (!targetVersionId) throw new Error("workflow sem versão editável");

  const existingNodes = JSON.parse(workflow.nodes);
  const canonicalNodes = canonical.nodes;

  const existingEvolution = nodeByName(existingNodes, "Consultar contato na Evolution1");
  const canonicalEvolution = nodeByName(canonicalNodes, "Consultar contato na Evolution1");
  const existingWebhook = nodeByName(
    existingNodes,
    "Registrar mensagem e ler handoff1",
  );
  const existingInventory = nodeByName(existingNodes, "consultar_estoque1");

  // multi-WA: instance is dynamic from Evolution webhook body.instance.
  // --instance= is accepted for CLI compatibility but never baked into URLs.
  if (instanceArg) {
    console.error(
      "aviso: --instance ignorado (workflow multi-WA usa body.instance por evento)",
    );
  }
  const chatbotBase = normalizeBaseUrl(
    "chatbot-base-url",
    chatbotBaseArg,
    canonicalChatbotBase,
  );
  const evolutionBase = normalizeBaseUrl(
    "evolution-base-url",
    evolutionBaseArg,
    canonicalEvolutionBase,
  );
  const evolutionKey = headerValue(existingEvolution, "apikey");
  const webhookToken = headerValue(existingWebhook, "X-Webhook-Token");
  const inventoryCode = String(existingInventory?.parameters?.jsCode || "");
  const chatbotMatch = inventoryCode.match(/Authorization:\s*'Bearer ([^']+)'/);
  const chatbotToken = chatbotMatch ? chatbotMatch[1] : "";

  const replacements = {
    __EVOLUTION_KEY__: evolutionKey,
    __CHATBOT_WEBHOOK_TOKEN__: webhookToken,
    __CHATBOT_TOKEN__: chatbotToken,
  };
  for (const [name, value] of Object.entries(replacements)) assertSecret(name, value);
  if (JSON.stringify(canonicalNodes).includes("__INSTANCE__")) {
    throw new Error(
      "canonical workflow still has __INSTANCE__; expect dynamic body.instance only",
    );
  }

  let serialized = JSON.stringify({
    nodes: canonical.nodes,
    connections: canonical.connections,
  });
  serialized = serialized.split(canonicalChatbotBase).join(chatbotBase);
  serialized = serialized.split(canonicalEvolutionBase).join(evolutionBase);
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
    versionSource: workflow.activeVersionId ? "published" : "draft",
    previousNodes: existingNodes.length,
    canonicalNodes: merged.nodes.length,
    chatbotBaseCustomized: chatbotBase !== canonicalChatbotBase,
    evolutionBaseCustomized: evolutionBase !== canonicalEvolutionBase,
    mode: apply ? "apply" : "preview",
  };
  if (!apply) {
    console.log(JSON.stringify(summary));
    return;
  }

  // Backup leve: só o JSON do workflow (VACUUM INTO no volume de 1GB enche o disco).
  const stamp = new Date().toISOString().replace(/[-:.TZ]/g, "");
  const backupPath = path.join(
    path.dirname(databasePath),
    `workflow.before-${stamp}.json`,
  );
  fs.writeFileSync(
    backupPath,
    JSON.stringify(
      {
        id: workflow.id,
        name: workflow.name,
        nodes: existingNodes,
        connections: JSON.parse(workflow.connections || "{}"),
      },
      null,
      2,
    ),
  );
  // Remove backups de workflow antigos (mantém os 3 mais recentes).
  try {
    const dir = path.dirname(databasePath);
    const old = fs
      .readdirSync(dir)
      .filter(
        (f) =>
          f.startsWith("workflow.before-") ||
          f.startsWith("database.before-workflow-"),
      )
      .map((f) => ({ f, t: fs.statSync(path.join(dir, f)).mtimeMs }))
      .sort((a, b) => b.t - a.t);
    for (const item of old.slice(3)) {
      fs.unlinkSync(path.join(dir, item.f));
    }
  } catch {
    /* best-effort */
  }

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
        targetVersionId,
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
    [targetVersionId],
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
