# PostgreSQL read-only aliases — local setup and DBA review

This skill never creates roles, applies grants, or opens tunnels. The DBA
runs the provisioning below; the user opens the tunnel when needed. All
values here are fake.

## Alias variables (five per alias)

For an alias `billing-prod`, with `BILLING_PROD` as the uppercased,
dash-to-underscore key:

| Variable suffix | Meaning |
|---|---|
| `SERVICE` **or** `URL` | libpq service name **or** full URL (never both) |
| `EXPECTED_DATABASE` | database the wrapper pins before every session |
| `EXPECTED_ROLE` | role the wrapper pins before every session |
| `ALLOWED_SCHEMAS` | comma-separated schemas the role may touch |
| `TRANSPORT` | `tls` (verify-full) or `tunnel` (already open) |

Service mode is the default. URL mode additionally requires the
`--allow-url-env` flag on every call and never falls back to an application
credential.

POSIX shell, one alias:

```bash
export PROD_READONLY_DB_BILLING_PROD_SERVICE=billing-ro
export PROD_READONLY_DB_BILLING_PROD_EXPECTED_DATABASE=billing
export PROD_READONLY_DB_BILLING_PROD_EXPECTED_ROLE=codex_reader
export PROD_READONLY_DB_BILLING_PROD_ALLOWED_SCHEMAS=reporting,public_read
export PROD_READONLY_DB_BILLING_PROD_TRANSPORT=tls
```

POSIX shell, two aliases (sequential runs, separate results):

```bash
export PROD_READONLY_DB_CRM_PROD_SERVICE=crm-ro
export PROD_READONLY_DB_CRM_PROD_EXPECTED_DATABASE=crm
export PROD_READONLY_DB_CRM_PROD_EXPECTED_ROLE=codex_reader
export PROD_READONLY_DB_CRM_PROD_ALLOWED_SCHEMAS=reporting
export PROD_READONLY_DB_CRM_PROD_TRANSPORT=tunnel
```

PowerShell, N aliases share the same five-key shape:

```powershell
$env:PROD_READONLY_DB_BILLING_PROD_SERVICE = 'billing-ro'
$env:PROD_READONLY_DB_BILLING_PROD_EXPECTED_DATABASE = 'billing'
$env:PROD_READONLY_DB_BILLING_PROD_EXPECTED_ROLE = 'codex_reader'
$env:PROD_READONLY_DB_BILLING_PROD_ALLOWED_SCHEMAS = 'reporting,public_read'
$env:PROD_READONLY_DB_BILLING_PROD_TRANSPORT = 'tls'
```

## Service file and password file locations

Service mode reads the libpq service definition and password outside the
environment:

| OS | `pg_service.conf` / `pg_service.conf` | password file |
|---|---|---|
| Linux | `~/.pg_service.conf` | `~/.pgpass` (mode `0600`) |
| macOS | `~/.pg_service.conf` | `~/.pgpass` (mode `0600`) |
| Windows | `%APPDATA%\postgresql\pg_service.conf` | `%APPDATA%\postgresql\pgpass.conf` |

Example service entry (fake host):

```ini
[billing-ro]
host=db-read-replica.example
port=5432
dbname=billing
user=codex_reader
sslmode=verify-full
sslrootcert=/path/to/ca.pem
```

## Manual role template (DBA runs this, not the skill)

```sql
CREATE ROLE codex_reader LOGIN PASSWORD '<from-vault>'
  NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- Revoke insecure defaults first.
REVOKE ALL ON DATABASE billing FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

GRANT CONNECT ON DATABASE billing TO codex_reader;
GRANT USAGE ON SCHEMA reporting TO codex_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO codex_reader;

-- Repeat for every creating role: covers future objects only.
ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA reporting
  GRANT SELECT ON TABLES TO codex_reader;

ALTER ROLE codex_reader SET default_transaction_read_only = on;
```

The provisioning SQL above is a reference: the skill never executes it.

## Transport choice

- `tls`: direct connection with `sslmode=verify-full`. The wrapper refuses
  URLs that downgrade to `disable`, `allow`, `prefer`, `require`,
  `verify-ca`, or anything unknown.
- `tunnel`: the user opens an SSH/port-forward tunnel first and points the
  service or URL at it. The wrapper does not open tunnels.

## DBA checklist before first use

1. Ownership: the role owns no tables, views, sequences, functions, or schemas.
2. Memberships: the role is a member of nothing (`NOINHERIT` alone is not proof).
3. `PUBLIC`: no `CONNECT`/`TEMPORARY` on other databases, no `USAGE`/`CREATE`
   on unexpected schemas, no `EXECUTE` on user routines.
4. `TEMPORARY` and `CREATE`: absent on every database and allowed schema.
5. `MAINTAIN` (PostgreSQL 17+): absent.
6. `EXECUTE`: absent on every user routine in allowed schemas.
7. Writable schemas: nothing outside the allowlist is `USAGE`- or
   `CREATE`-visible to the role.
8. `SET` / `ALTER SYSTEM` on parameters (PostgreSQL 15+): no grants.
9. The preflight (`BEGIN READ ONLY` session) returns empty violation lists;
   run it once per alias after provisioning and after every grant change.
