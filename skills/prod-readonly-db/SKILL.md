---
name: prod-readonly-db
description: Inspect PostgreSQL production data through preconfigured read-only aliases when a user asks for diagnosis, schema inspection, counts, or limited queries. Do not use for migrations, mutations, administration, or credential discovery.
---

# Production DB (read-only)

Query PostgreSQL production data through named local aliases backed by a
dedicated read-only role. The wrapper (`scripts/readonly_psql.py`) resolves
exactly one alias per process, enforces a conservative single-`SELECT` gate,
audits the role with a fail-closed preflight, and runs the query in a
read-only transaction with timeouts.

## Authorize first

Connect only when the request authorizes the query **and** names the alias.
No alias in the request means no connection: ask which alias to use. Never
enumerate the environment looking for configured aliases, never fall back to
an application credential (`DATABASE_URL` or similar), and never compare
results across aliases unless the user explicitly asks.

## One alias per run

Each process queries exactly one alias. Several aliases run sequentially with
separate results:

```bash
echo "SELECT id FROM reporting.orders WHERE id = 7" \
  | python3 skills/prod-readonly-db/scripts/readonly_psql.py --alias billing-prod
```

Windows PowerShell:

```powershell
"SELECT id FROM reporting.orders WHERE id = 7" | python skills/prod-readonly-db/scripts/readonly_psql.py --alias billing-prod
```

SQL travels on stdin only. Exit codes: `0` success, `2` configuration or
rejected SQL, `3` preflight refusal, `4` connection/psql failure, `5` output
limit. `--max-rows 1..1000` caps returned rows (default 200).

## Configure and audit

Read `references/postgresql.md` only for local alias setup and DBA review:
service/URL variables per alias, `pg_service.conf` locations, the manual role
template, and the TLS/tunnel checklist. The skill never creates roles, grants,
or tunnels.

Keep projections minimal and filters explicit. When data is personal,
financial, or large, refine instead of dumping.
