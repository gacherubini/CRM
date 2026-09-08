"""Resolve one local alias and run one conservative read-only query via psql.

Standard library only. No secret, DSN, password or SQL ever goes into argv:
credentials travel in the environment (libpq service file or an explicit
URL opt-in) and the query travels on stdin.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse


class ConfigError(Exception):
    """Alias configuration is missing, ambiguous or inconsistent."""


class UnsafeQueryError(Exception):
    """Query rejected by the conservative read-only allowlist."""


ENV_PREFIX = "PROD_READONLY_DB_"
RESULT_LABEL = "codex_readonly_result"
APP_NAME = "codex-prod-readonly"
MAX_ROWS_HARD_LIMIT = 1000


@dataclass(frozen=True)
class TargetConfig:
    alias: str
    service: str | None
    url: str | None
    expected_database: str
    expected_role: str
    allowed_schemas: tuple[str, ...]
    transport: Literal["tls", "tunnel"]


_ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def normalize_alias(alias: str) -> str:
    """Validate a user-supplied alias; return it stripped of whitespace."""
    if not isinstance(alias, str):
        raise ConfigError("invalid alias")
    text = alias.strip()
    if not text or _ALIAS_RE.fullmatch(text) is None:
        raise ConfigError("invalid alias")
    return text


def _env_key(alias: str) -> str:
    return normalize_alias(alias).upper().replace("-", "_")


def resolve_target(
    alias: str, env: Mapping[str, str], *, allow_url_env: bool = False
) -> TargetConfig:
    """Resolve exactly one alias from non-secret config keys.

    Never raises KeyError: every problem surfaces as ConfigError without
    echoing secret values (URL) in the message.
    """
    key = _env_key(alias)
    prefix = f"{ENV_PREFIX}{key}_"

    def get(name: str) -> str:
        value = env.get(prefix + name, "")
        return value.strip() if isinstance(value, str) else ""

    service = get("SERVICE") or None
    url = get("URL") or None
    expected_database = get("EXPECTED_DATABASE")
    expected_role = get("EXPECTED_ROLE")
    raw_schemas = get("ALLOWED_SCHEMAS")
    transport = get("TRANSPORT").lower()

    if service and url:
        raise ConfigError("ambiguous credential: SERVICE and URL are both set")
    if url is not None and not allow_url_env:
        raise ConfigError("URL credential requires explicit opt-in")
    if service is None and url is None:
        raise ConfigError("no credential configured for alias")
    if not expected_database:
        raise ConfigError("EXPECTED_DATABASE is required")
    if not expected_role:
        raise ConfigError("EXPECTED_ROLE is required")
    allowed_schemas = tuple(
        part.strip() for part in raw_schemas.split(",") if part.strip()
    )
    if not allowed_schemas:
        raise ConfigError("ALLOWED_SCHEMAS is required")
    if transport not in ("tls", "tunnel"):
        raise ConfigError("TRANSPORT must be tls or tunnel")

    return TargetConfig(
        alias=normalize_alias(alias),
        service=service,
        url=url,
        expected_database=expected_database,
        expected_role=expected_role,
        allowed_schemas=allowed_schemas,
        transport=transport,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# SQL safety gate: state-machine scanner + conservative allowlist.
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_DOLLAR_OPEN_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")

# Constructs that never appear in a plain SELECT/WITH...SELECT read.
# Case-insensitive: SQL keywords arrive in any case and the scanner above
# already blanked strings/comments, so a match here is always structural.
_FORBIDDEN_PATTERNS = (
    re.compile(
        r"\bfor\s+(update|share|no\s+key\s+update|key\s+share)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(insert|update|delete|merge|copy|explain|analyze|into"
        r"|create|alter|drop|truncate|grant|revoke|comment|vacuum|cluster"
        r"|begin|commit|rollback|abort|start|transaction|set|reset|show|lock"
        r"|listen|notify|unlisten|discard|checkpoint|prepare|execute|deallocate"
        r"|declare|fetch|close|move|do|call|handler|import|export)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(pg_terminate_backend|pg_cancel_backend|pg_reload_conf"
        r"|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_stat_file"
        r"|lo_import|lo_export|dblink)\b",
        re.IGNORECASE,
    ),
)


def _strip_to_code(sql: str) -> str:
    """Return *sql* with strings, quoted idents, dollar-quotes and comments
    blanked out (same length, spaces instead) so keyword checks below only
    see real SQL structure and tokens can never glue across a gap."""
    chars = list(sql)
    out = [" "] * len(chars)
    i = 0
    n = len(chars)
    while i < n:
        c = chars[i]
        two = sql[i : i + 2]
        if two == "--":
            j = sql.find("\n", i)
            i = n if j == -1 else j
        elif two == "/*":
            depth = 1
            i += 2
            while i < n and depth:
                if sql[i : i + 2] == "/*":
                    depth += 1
                    i += 2
                elif sql[i : i + 2] == "*/":
                    depth -= 1
                    i += 2
                else:
                    i += 1
        elif c == "'":
            i += 1
            while i < n:
                if chars[i] == "'" and sql[i : i + 2] != "''":
                    i += 1
                    break
                i += 2 if sql[i : i + 2] == "''" else 1
        elif c == '"':
            i += 1
            while i < n:
                if chars[i] == '"' and sql[i : i + 2] != '""':
                    i += 1
                    break
                i += 2 if sql[i : i + 2] == '""' else 1
        elif c == "$":
            match = _DOLLAR_OPEN_RE.match(sql, i)
            if match:
                tag = match.group(0)
                end = sql.find(tag, match.end())
                i = n if end == -1 else end + len(tag)
            else:
                out[i] = c  # e.g. $1 parameter
                i += 1
        else:
            out[i] = c
            i += 1
    return "".join(out)


def _first_word(code: str) -> str:
    match = _WORD_RE.search(code.lstrip(" \t\r\n\f\v("))
    return match.group(0).upper() if match else ""


def _strip_paren_groups(code: str) -> str:
    prev = None
    while prev != code:
        prev = code
        code = re.sub(r"\([^()]*\)", " ", code)
    return code


def validate_sql(sql: str) -> str:
    """Accept one SELECT or WITH...SELECT query; return it stripped.

    Raises UnsafeQueryError with a stable reason code and never repeats
    the query text in the message.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise UnsafeQueryError("rejected: empty-query")
    code = _strip_to_code(sql)
    if "\\" in code:
        raise UnsafeQueryError("rejected: backslash-command")
    body = code.strip()
    if body.startswith(";") or body.count(";") > 1:
        raise UnsafeQueryError("rejected: multiple-statements")
    if body.endswith(";"):
        body = body[:-1].strip()
    if ";" in body:
        raise UnsafeQueryError("rejected: multiple-statements")
    first = _first_word(body)
    if first == "SELECT":
        # A bare "SELECT" (or "(SELECT)") is not a query: require a remainder
        # after the leading keyword. Numeric literals are not words, so count
        # the raw remainder instead of word tokens.
        rest = re.sub(r"^[\s(]*SELECT\b", "", body, flags=re.IGNORECASE).strip()
        if not rest:
            raise UnsafeQueryError("rejected: not-select")
    elif first == "WITH":
        outer = _strip_paren_groups(body)
        if not re.search(r"^\s*WITH\s+.+\bSELECT\b", outer, re.DOTALL):
            raise UnsafeQueryError("rejected: not-select")
    else:
        raise UnsafeQueryError("rejected: not-select")
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(body):
            raise UnsafeQueryError("rejected: forbidden-construct")
    return sql.strip()


def build_limited_query(sql: str, max_rows: int = 200) -> str:
    """Wrap a validated query so at most ``max_rows`` rows come back.

    Fetches one extra row (LIMIT max_rows + 1) so the caller can report
    truncation. ``max_rows`` is clamped to 1..1000 and never raised above.
    """
    if not isinstance(max_rows, int) or not 1 <= max_rows <= MAX_ROWS_HARD_LIMIT:
        raise ValueError("max_rows must be an int in 1..1000")
    clean = validate_sql(sql)
    if clean.endswith(";"):
        clean = clean[:-1].rstrip()
    return (
        f"SELECT * FROM (\n{clean}\n) AS {RESULT_LABEL} LIMIT {max_rows + 1}"
    )


# ---------------------------------------------------------------------------
# Hardened execution: environment, preflight audit, two-stage sessions.
# ---------------------------------------------------------------------------


class PsqlError(Exception):
    """psql is missing, unreachable, or returned something unexpected.

    Messages are static categories: psql diagnostics may name hosts or
    credentials, so stdout/stderr content never enters the message.
    """


class OutputLimitError(Exception):
    """Non-tabular output exceeded the 1 MiB safety cap."""


_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.\-\" ]")


def sanitize_ident(value: object, limit: int = 64) -> str:
    """Reduce an identifier to a safe charset for error messages."""
    return _SANITIZE_RE.sub("?", str(value))[:limit]


class PreflightRefusedError(Exception):
    """Fail-closed refusal with violation categories and capped identifiers."""

    def __init__(self, violations: Mapping[str, Sequence[object]]) -> None:
        self.violations: dict[str, tuple[str, ...]] = {
            code: tuple(sanitize_ident(item) for item in items[:5])
            for code, items in violations.items()
        }
        parts = []
        for code in sorted(self.violations):
            shown = ",".join(self.violations[code])
            parts.append(code if not shown else f"{code}:{shown}")
        super().__init__("preflight refused: " + "; ".join(parts))


@dataclass(frozen=True)
class PreflightResult:
    database: str
    role: str
    transaction_read_only: bool
    default_transaction_read_only: bool
    administrative_attributes: tuple[str, ...]
    memberships: tuple[str, ...]
    owned_objects: tuple[str, ...]
    forbidden_privileges: tuple[str, ...]
    forbidden_parameter_privileges: tuple[str, ...]
    unexpected_connect_databases: tuple[str, ...]
    unexpected_schemas: tuple[str, ...]
    unsafe_routines: tuple[str, ...]


@dataclass(frozen=True)
class QueryResult:
    alias: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    truncated: bool


Runner = Callable[[Sequence[str], Mapping[str, str], str], object]


def _require_verify_full_tls(url: str) -> None:
    try:
        params = parse_qs(urlparse(url).query)
    except ValueError as exc:
        raise ConfigError("URL credential is malformed") from exc
    modes = params.get("sslmode", [])
    if not modes:
        return
    if len(modes) != 1 or modes[0] != "verify-full":
        raise ConfigError("URL credential must not downgrade TLS")


def _url_libpq_env(url: str) -> dict[str, str]:
    """Translate a URL credential into libpq variables.

    libpq reads no URL from the environment, so the URL has to become
    PGHOST/PGPORT/PGUSER/PGPASSWORD here. Putting it in argv instead would
    publish the password in the process list, which the whole wrapper exists
    to avoid.
    """
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ConfigError("URL credential is malformed") from exc
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ConfigError("URL credential must use the postgresql scheme")
    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ConfigError("URL credential is malformed") from exc
    if not host:
        raise ConfigError("URL credential has no host")
    env = {"PGHOST": host}
    if port is not None:
        env["PGPORT"] = str(port)
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    return env


def build_psql_env(
    target: TargetConfig, *, allow_url_env: bool = False
) -> dict[str, str]:
    """Build only the libpq variables for one target (never argv material)."""
    env: dict[str, str] = {}
    if target.url is not None:
        if not allow_url_env:
            raise ConfigError("URL credential requires explicit opt-in")
        if target.transport == "tls":
            _require_verify_full_tls(target.url)
        env.update(_url_libpq_env(target.url))
        env["PGDATABASE"] = target.expected_database
        if target.transport == "tls":
            env["PGSSLMODE"] = "verify-full"
    else:
        env["PGSERVICE"] = target.service or ""
        if target.transport == "tls":
            env["PGSSLMODE"] = "verify-full"
    return env


# Ambient libpq variables that would otherwise silently redirect the session
# to a host the alias never named. The alias alone decides where we connect.
_MANAGED_LIBPQ_VARS = (
    "PGSERVICE",
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGDATABASE",
    "PGSSLMODE",
    "PGOPTIONS",
)


def _merged_env(target: TargetConfig, *, allow_url_env: bool) -> dict[str, str]:
    merged = dict(os.environ)
    for name in _MANAGED_LIBPQ_VARS:
        merged.pop(name, None)
    merged.update(build_psql_env(target, allow_url_env=allow_url_env))
    return merged


_SESSION_PREAMBLE = (
    "BEGIN READ ONLY;\n"
    "SET LOCAL statement_timeout = '10s';\n"
    "SET LOCAL lock_timeout = '2s';\n"
    "SET LOCAL idle_in_transaction_session_timeout = '5s';\n"
    "SET LOCAL search_path = pg_catalog;\n"
    f"SELECT set_config('application_name', '{APP_NAME}', true);\n"
)

# -q keeps psql from printing a status line per statement (BEGIN, SET,
# ROLLBACK), which would otherwise sit around the result set.
_PSQL_ARGV = ("psql", "-X", "-q", "--no-password", "-v", "ON_ERROR_STOP=1")
_OUTPUT_CAP_BYTES = 1024 * 1024


def _session_sql(payload_sql: str) -> str:
    # The payload has to be terminated: without the semicolon psql parses the
    # ROLLBACK below as a column alias of the payload instead of running it.
    payload = payload_sql.rstrip().rstrip(";").rstrip()
    return _SESSION_PREAMBLE + payload + ";\nROLLBACK;\n"


def _default_runner(
    argv: Sequence[str], env: Mapping[str, str], stdin_text: str
) -> object:
    try:
        return subprocess.run(
            list(argv),
            env=dict(env),
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise PsqlError("psql executable not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise PsqlError("psql session timed out") from exc


def _run_session(
    argv_extra: Sequence[str],
    env: Mapping[str, str],
    payload_sql: str,
    runner: Runner | None,
) -> str:
    argv = [*_PSQL_ARGV, *argv_extra]
    invoke = runner if runner is not None else _default_runner
    try:
        completed = invoke(argv, env, _session_sql(payload_sql))
    except FileNotFoundError as exc:
        raise PsqlError("psql executable not found") from exc
    except OSError as exc:
        raise PsqlError("psql session failed to start") from exc
    if getattr(completed, "returncode", 1) != 0:
        raise PsqlError("psql session failed")
    stdout = getattr(completed, "stdout", "")
    return stdout if isinstance(stdout, str) else ""


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _preflight_sql(target: TargetConfig) -> str:
    allowed = ", ".join(_lit(schema) for schema in target.allowed_schemas)
    return f"""SELECT json_build_object(
  'database', current_database(),
  'role', current_user,
  'transaction_read_only',
    (SELECT setting = 'on' FROM pg_settings WHERE name = 'transaction_read_only'),
  'default_transaction_read_only',
    (SELECT setting = 'on' FROM pg_settings WHERE name = 'default_transaction_read_only'),
  'server_version_num',
    (SELECT setting::integer FROM pg_settings WHERE name = 'server_version_num'),
  'administrative_attributes',
    (SELECT COALESCE(json_agg(attr), '[]'::json) FROM (
      SELECT unnest(ARRAY[
        CASE WHEN rolsuper THEN 'superuser' END,
        CASE WHEN rolcreatedb THEN 'createdb' END,
        CASE WHEN rolcreaterole THEN 'createrole' END,
        CASE WHEN rolreplication THEN 'replication' END,
        CASE WHEN rolbypassrls THEN 'bypassrls' END
      ]) AS attr FROM pg_roles WHERE rolname = current_user
    ) s WHERE attr IS NOT NULL),
  'memberships',
    (SELECT COALESCE(json_agg(r.rolname ORDER BY r.rolname), '[]'::json)
     FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid
     WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = current_user)),
  'owned_objects',
    (SELECT COALESCE(json_agg(name), '[]'::json) FROM (
      SELECT quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS name
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
        AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        AND c.relkind IN ('r', 'v', 'm', 'S', 'f', 'p')
      LIMIT 50) s),
  'forbidden_privileges',
    (SELECT COALESCE(json_agg(priv), '[]'::json) FROM (
      SELECT 'TEMPORARY ON DATABASE ' || quote_ident(d.datname) AS priv
      FROM pg_database d
      WHERE d.datallowconn AND has_database_privilege(d.datname, 'TEMPORARY')
      UNION ALL
      SELECT 'CREATE ON DATABASE ' || quote_ident(d.datname)
      FROM pg_database d
      WHERE d.datallowconn AND has_database_privilege(d.datname, 'CREATE')
      UNION ALL
      SELECT 'CREATE ON SCHEMA ' || quote_ident(n.nspname)
      FROM pg_namespace n
      WHERE n.nspname IN ({allowed}) AND has_schema_privilege(n.nspname, 'CREATE')
      UNION ALL
      SELECT 'WRITE ON TABLE ' || quote_ident(n.nspname) || '.' || quote_ident(c.relname)
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname IN ({allowed}) AND c.relkind IN ('r', 'p', 'f')
        AND (has_table_privilege(c.oid, 'INSERT')
          OR has_table_privilege(c.oid, 'UPDATE')
          OR has_table_privilege(c.oid, 'DELETE')
          OR has_table_privilege(c.oid, 'TRUNCATE'))
      LIMIT 50) s),
  'forbidden_parameter_privileges', '[]'::json,
  'unexpected_connect_databases',
    (SELECT COALESCE(json_agg(d.datname ORDER BY d.datname), '[]'::json)
     FROM pg_database d
     WHERE d.datallowconn AND d.datname <> {_lit(target.expected_database)}
       AND has_database_privilege(d.datname, 'CONNECT')),
  'unexpected_schemas',
    (SELECT COALESCE(json_agg(n.nspname ORDER BY n.nspname), '[]'::json)
     FROM pg_namespace n
     WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', {allowed})
       AND (has_schema_privilege(n.nspname, 'USAGE')
         OR has_schema_privilege(n.nspname, 'CREATE'))),
  'unsafe_routines',
    (SELECT COALESCE(json_agg(s.name), '[]'::json)
     FROM (SELECT quote_ident(n.nspname) || '.' || quote_ident(p.proname) AS name
       FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
       WHERE n.nspname IN ({allowed}) AND has_function_privilege(p.oid, 'EXECUTE')
       LIMIT 50) s)
)::text"""


def _parameter_privileges_sql() -> str:
    # pg_settings shape is stable; has_parameter_privilege needs PG15+.
    return """SELECT COALESCE(json_agg('PARAMETER ' || s.name), '[]'::json)
FROM (SELECT s.name FROM pg_settings s
  WHERE has_parameter_privilege(s.name, 'SET')
     OR has_parameter_privilege(s.name, 'ALTER SYSTEM')
  LIMIT 5) s"""


def _maintain_privileges_sql(target: TargetConfig) -> str:
    # MAINTAIN exists only on PG17+; gated client-side by server_version_num.
    allowed = ", ".join(_lit(schema) for schema in target.allowed_schemas)
    return f"""SELECT COALESCE(json_agg(priv), '[]'::json) FROM (
  SELECT 'MAINTAIN ON TABLE ' || quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS priv
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname IN ({allowed}) AND c.relkind IN ('r', 'p', 'f')
    AND has_table_privilege(c.oid, 'MAINTAIN')
  LIMIT 50) s"""


def _parse_json_line(stdout: str, what: str) -> object:
    """Pick the JSON payload out of the session output.

    psql prints a status line for every statement (BEGIN, SET, ROLLBACK), so
    the payload is not the last line: scan backwards for the last line that
    actually parses.
    """
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise PsqlError(f"{what} returned no output")
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise PsqlError(f"{what} returned unexpected output")


def _require_str_list(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise PsqlError("preflight returned unexpected output")
    return tuple(value)


def run_preflight(
    target: TargetConfig,
    *,
    runner: Runner | None = None,
    allow_url_env: bool = False,
) -> PreflightResult:
    """Audit the role in one read-only transaction; fail closed on surprises."""
    env = _merged_env(target, allow_url_env=allow_url_env)
    payload = _parse_json_line(
        _run_session(("-t", "-A"), env, _preflight_sql(target), runner), "preflight"
    )
    if not isinstance(payload, dict):
        raise PsqlError("preflight returned unexpected output")
    try:
        database = payload["database"]
        role = payload["role"]
        transaction_read_only = payload["transaction_read_only"]
        default_read_only = payload["default_transaction_read_only"]
        version = payload["server_version_num"]
        lists = {
            key: _require_str_list(payload[key], "preflight")
            for key in (
                "administrative_attributes",
                "memberships",
                "owned_objects",
                "forbidden_privileges",
                "forbidden_parameter_privileges",
                "unexpected_connect_databases",
                "unexpected_schemas",
                "unsafe_routines",
            )
        }
    except KeyError as exc:
        raise PsqlError("preflight returned unexpected output") from exc
    if (
        not isinstance(database, str)
        or not isinstance(role, str)
        or not isinstance(transaction_read_only, bool)
        or not isinstance(default_read_only, bool)
        or type(version) is not int
    ):
        raise PsqlError("preflight returned unexpected output")

    forbidden_parameters = lists["forbidden_parameter_privileges"]
    forbidden_privileges = lists["forbidden_privileges"]
    if version >= 150000:
        extra = _parse_json_line(
            _run_session(("-t", "-A"), env, _parameter_privileges_sql(), runner),
            "preflight",
        )
        if not isinstance(extra, list):
            raise PsqlError("preflight returned unexpected output")
        forbidden_parameters = _require_str_list(extra, "preflight")
    if version >= 170000:
        extra = _parse_json_line(
            _run_session(
                ("-t", "-A"), env, _maintain_privileges_sql(target), runner
            ),
            "preflight",
        )
        if not isinstance(extra, list):
            raise PsqlError("preflight returned unexpected output")
        forbidden_privileges = forbidden_privileges + _require_str_list(
            extra, "preflight"
        )

    return PreflightResult(
        database=database,
        role=role,
        transaction_read_only=transaction_read_only,
        default_transaction_read_only=default_read_only,
        administrative_attributes=lists["administrative_attributes"],
        memberships=lists["memberships"],
        owned_objects=lists["owned_objects"],
        forbidden_privileges=forbidden_privileges,
        forbidden_parameter_privileges=forbidden_parameters,
        unexpected_connect_databases=lists["unexpected_connect_databases"],
        unexpected_schemas=lists["unexpected_schemas"],
        unsafe_routines=lists["unsafe_routines"],
    )


def assess_preflight(
    target: TargetConfig, result: PreflightResult
) -> tuple[str, ...]:
    """Return violation codes; empty means the role is safe to use."""
    violations = []
    if result.database != target.expected_database:
        violations.append("unexpected-database")
    if result.role != target.expected_role:
        violations.append("unexpected-role")
    if not result.transaction_read_only:
        violations.append("transaction-not-read-only")
    if not result.default_transaction_read_only:
        violations.append("default-not-read-only")
    if result.administrative_attributes:
        violations.append("administrative-attributes")
    if result.memberships:
        violations.append("role-membership")
    if result.owned_objects:
        violations.append("owned-objects")
    if result.forbidden_privileges:
        violations.append("forbidden-privileges")
    if result.forbidden_parameter_privileges:
        violations.append("parameter-privileges")
    if result.unexpected_connect_databases:
        violations.append("unexpected-connect")
    if result.unexpected_schemas:
        violations.append("unexpected-schemas")
    if result.unsafe_routines:
        violations.append("unsafe-routines")
    return tuple(violations)


def _refusal_detail(
    target: TargetConfig, result: PreflightResult, codes: Sequence[str]
) -> dict[str, tuple[str, ...]]:
    detail: dict[str, tuple[str, ...]] = {}
    lookup = {
        "unexpected-database": (result.database,),
        "unexpected-role": (result.role,),
        "administrative-attributes": result.administrative_attributes,
        "role-membership": result.memberships,
        "owned-objects": result.owned_objects,
        "forbidden-privileges": result.forbidden_privileges,
        "parameter-privileges": result.forbidden_parameter_privileges,
        "unexpected-connect": result.unexpected_connect_databases,
        "unexpected-schemas": result.unexpected_schemas,
        "unsafe-routines": result.unsafe_routines,
    }
    for code in codes:
        detail[code] = tuple(lookup.get(code, ()))
    return detail


def execute_readonly(
    target: TargetConfig,
    sql: str,
    *,
    runner: Runner | None = None,
    max_rows: int = 200,
    allow_url_env: bool = False,
) -> QueryResult:
    """Preflight the role, then run one limited query in a second session."""
    limited = build_limited_query(sql, max_rows)
    env = _merged_env(target, allow_url_env=allow_url_env)
    preflight = run_preflight(target, runner=runner, allow_url_env=allow_url_env)
    codes = assess_preflight(target, preflight)
    if codes:
        raise PreflightRefusedError(_refusal_detail(target, preflight, codes))
    stdout = _run_session(("--csv",), env, limited, runner)
    if len(stdout.encode("utf-8")) > _OUTPUT_CAP_BYTES:
        raise OutputLimitError("result exceeds output limit")
    lines = stdout.splitlines()
    # The hardened preamble prints exactly two framing lines (header + value
    # of the application_name probe) before the user result set.
    if (
        len(lines) < 2
        or lines[0].strip() != "set_config"
        or lines[1].strip() != APP_NAME
    ):
        raise PsqlError("query returned unexpected output")
    parsed = list(csv.reader(lines[2:]))
    if not parsed:
        return QueryResult(
            alias=target.alias, columns=(), rows=(), truncated=False
        )
    columns = tuple(parsed[0])
    rows = [tuple(row) for row in parsed[1:]]
    truncated = len(rows) == max_rows + 1
    if truncated:
        rows = rows[:max_rows]
    return QueryResult(
        alias=target.alias,
        columns=columns,
        rows=tuple(rows),
        truncated=truncated,
    )


EXIT_OK = 0
EXIT_CONFIG_OR_QUERY = 2
EXIT_PREFLIGHT_REFUSED = 3
EXIT_CONNECTION = 4
EXIT_OUTPUT_LIMIT = 5


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: ``readonly_psql.py --alias ALIAS [--allow-url-env] [--max-rows N]``.

    SQL comes exclusively from stdin. Success prints one JSON document on
    stdout; failures print only alias, category and exit code on stderr.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="readonly_psql.py",
        description="Run one read-only query against one preconfigured alias.",
    )
    parser.add_argument("--alias", required=True)
    parser.add_argument("--allow-url-env", action="store_true")
    parser.add_argument("--max-rows", type=int, default=200)
    args = parser.parse_args(argv)

    alias = args.alias if isinstance(args.alias, str) else ""
    import sys as _sys

    def fail(category: str, code: int) -> int:
        _sys.stderr.write(
            json.dumps({"alias": alias, "error": category, "exit": code}) + "\n"
        )
        return code

    try:
        target = resolve_target(
            alias, os.environ, allow_url_env=args.allow_url_env
        )
    except ConfigError:
        return fail("config", EXIT_CONFIG_OR_QUERY)
    try:
        query = _sys.stdin.read()
    except OSError:
        return fail("config", EXIT_CONFIG_OR_QUERY)
    if not query.strip():
        return fail("config", EXIT_CONFIG_OR_QUERY)
    try:
        result = execute_readonly(
            target,
            query,
            max_rows=args.max_rows,
            allow_url_env=args.allow_url_env,
        )
    except UnsafeQueryError:
        return fail("unsafe-query", EXIT_CONFIG_OR_QUERY)
    except (ConfigError, ValueError):
        return fail("config", EXIT_CONFIG_OR_QUERY)
    except PreflightRefusedError:
        return fail("preflight-refused", EXIT_PREFLIGHT_REFUSED)
    except OutputLimitError:
        return fail("output-limit", EXIT_OUTPUT_LIMIT)
    except (PsqlError, OSError):
        return fail("connection", EXIT_CONNECTION)
    _sys.stdout.write(
        json.dumps(
            {
                "alias": result.alias,
                "columns": list(result.columns),
                "rows": [list(row) for row in result.rows],
                "truncated": result.truncated,
            }
        )
        + "\n"
    )
    return EXIT_OK


if __name__ == "__main__":
    import sys

    sys.exit(main())
