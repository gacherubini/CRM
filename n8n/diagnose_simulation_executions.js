#!/usr/bin/env node
/**
 * Diagnóstico read-only das tools de simulação no SQLite do n8n.
 * Execute dentro do container oficial do n8n, onde sqlite3 já está instalado.
 * A saída não contém telefone, CPF, texto da conversa, token ou payload bruto.
 */
const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/sqlite3');

function argument(name, fallback) {
  const prefix = `--${name}=`;
  const found = process.argv.find((value) => value.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

function decodeFlatted(text) {
  const input = JSON.parse(text);
  const memo = new Map();
  function at(index) {
    if (memo.has(index)) return memo.get(index);
    const raw = input[index];
    if (raw === null || typeof raw !== 'object') return raw;
    const output = Array.isArray(raw) ? [] : {};
    memo.set(index, output);
    for (const [key, value] of Object.entries(raw)) {
      output[key] = typeof value === 'string' && /^\d+$/.test(value)
        ? at(Number(value))
        : value;
    }
    return output;
  }
  return at(0);
}

function classifyError(message) {
  const text = String(message || '');
  if (text.includes('Received tool input did not match expected schema')) {
    return 'schema_mismatch_extra_keys';
  }
  return text ? 'other' : null;
}

const dbPath = argument('db', '/home/node/.n8n/database.sqlite');
const workflowId = argument('workflow', 'wAiNaoSalvos0001');
const since = argument('since', '1970-01-01T00:00:00.000Z')
  .replace('T', ' ')
  .replace(/Z$/, '');
const db = new sqlite3.Database(dbPath, sqlite3.OPEN_READONLY);

const sql = `SELECT d.executionId, e.startedAt, e.status, d.data
  FROM execution_data d
  JOIN execution_entity e ON e.id = d.executionId
  WHERE e.workflowId = ? AND e.startedAt >= ?
  ORDER BY d.executionId`;

db.all(sql, [workflowId, since], (error, rows) => {
  if (error) throw error;
  const totals = {
    executions_scanned: rows.length,
    temp_success: 0,
    temp_error: 0,
    normal_success: 0,
    normal_error: 0,
  };
  for (const row of rows) {
    const runData = decodeFlatted(row.data)?.resultData?.runData || {};
    for (const nodeName of ['TEMP continuar sem estoque1', 'simular1']) {
      for (const run of runData[nodeName] || []) {
        const kind = nodeName === 'simular1' ? 'normal' : 'temp';
        const status = run.executionStatus === 'success' ? 'success' : 'error';
        totals[`${kind}_${status}`] += 1;
        console.log(JSON.stringify({
          execution_id: row.executionId,
          started_at_utc: row.startedAt,
          execution_status: row.status,
          tool: nodeName,
          tool_status: run.executionStatus || null,
          error_code: classifyError(run.error?.message),
        }));
      }
    }
  }
  console.log(JSON.stringify({ summary: totals }));
  db.close();
});
