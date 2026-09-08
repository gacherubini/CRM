"""Unit tests for Task 1: alias resolution, config and the SQL safety gate.

No network, no subprocess, no production. All values are fake.
"""

import csv
import io
import json
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
)

from readonly_psql import (
    ConfigError,
    OutputLimitError,
    PreflightRefusedError,
    PreflightResult,
    PsqlError,
    QueryResult,
    TargetConfig,
    UnsafeQueryError,
    assess_preflight,
    build_limited_query,
    build_psql_env,
    execute_readonly,
    normalize_alias,
    resolve_target,
    run_preflight,
    validate_sql,
)

SAFE_ENV = {
    "PROD_READONLY_DB_BILLING_PROD_SERVICE": "billing-ro",
    "PROD_READONLY_DB_BILLING_PROD_EXPECTED_DATABASE": "billing",
    "PROD_READONLY_DB_BILLING_PROD_EXPECTED_ROLE": "codex_reader",
    "PROD_READONLY_DB_BILLING_PROD_ALLOWED_SCHEMAS": "reporting,public_read",
    "PROD_READONLY_DB_BILLING_PROD_TRANSPORT": "tls",
}

SAFE_SQL = (
    "SELECT id, status FROM reporting.orders WHERE id = 7",
    "WITH recent AS (SELECT id FROM reporting.orders) SELECT id FROM recent",
    "SELECT 'delete; \\copy' AS harmless_text",
)

UNSAFE_SQL = (
    "SELECT 1; SELECT 2",
    "WITH changed AS (DELETE FROM reporting.orders RETURNING id) SELECT * FROM changed",
    "SELECT * FROM reporting.orders FOR UPDATE",
    "EXPLAIN ANALYZE SELECT * FROM reporting.orders",
    "\\copy reporting.orders TO 'dump.csv'",
    "SET ROLE postgres",
)


class NormalizeAliasTest(unittest.TestCase):
    def test_accepts_simple_alias(self):
        self.assertEqual(normalize_alias("billing-prod"), "billing-prod")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(normalize_alias("  billing-prod  "), "billing-prod")

    def test_rejects_empty_alias(self):
        for bad in ("", "   "):
            with self.assertRaises(ConfigError):
                normalize_alias(bad)

    def test_rejects_alias_with_spaces_or_specials(self):
        for bad in ("billing prod", "billing/prod", "billing;prod", "a'b"):
            with self.assertRaises(ConfigError):
                normalize_alias(bad)

    def test_rejects_non_string_alias(self):
        with self.assertRaises(ConfigError):
            normalize_alias(None)


class ResolveTargetTest(unittest.TestCase):
    def test_resolve_service_target(self):
        target = resolve_target("billing-prod", SAFE_ENV)
        self.assertEqual(target.service, "billing-ro")
        self.assertEqual(target.expected_database, "billing")
        self.assertEqual(target.allowed_schemas, ("reporting", "public_read"))

    def test_alias_lookup_is_case_and_dash_insensitive(self):
        target = resolve_target("Billing-Prod", SAFE_ENV)
        self.assertEqual(target.service, "billing-ro")

    def test_url_requires_explicit_opt_in(self):
        env = dict(SAFE_ENV)
        env.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
        env["PROD_READONLY_DB_BILLING_PROD_URL"] = "postgresql://fake.invalid/db"
        with self.assertRaises(ConfigError):
            resolve_target("billing-prod", env, allow_url_env=False)

    def test_url_resolves_with_opt_in(self):
        env = dict(SAFE_ENV)
        env.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
        env["PROD_READONLY_DB_BILLING_PROD_URL"] = "postgresql://fake.invalid/db"
        target = resolve_target("billing-prod", env, allow_url_env=True)
        self.assertIsNone(target.service)
        self.assertEqual(target.url, "postgresql://fake.invalid/db")

    def test_url_value_never_leaks_into_error(self):
        env = dict(SAFE_ENV)
        env["PROD_READONLY_DB_BILLING_PROD_URL"] = "postgresql://secret.invalid/db"
        try:
            resolve_target("billing-prod", env, allow_url_env=False)
        except ConfigError as exc:
            self.assertNotIn("secret.invalid", str(exc))
        else:
            self.fail("expected ConfigError")

    def test_service_and_url_together_is_rejected(self):
        env = dict(SAFE_ENV)
        env["PROD_READONLY_DB_BILLING_PROD_URL"] = "postgresql://fake.invalid/db"
        with self.assertRaises(ConfigError):
            resolve_target("billing-prod", env, allow_url_env=True)

    def test_missing_credential_is_rejected(self):
        env = dict(SAFE_ENV)
        env.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
        with self.assertRaises(ConfigError):
            resolve_target("billing-prod", env)

    def test_missing_required_fields_are_rejected(self):
        for key in (
            "PROD_READONLY_DB_BILLING_PROD_EXPECTED_DATABASE",
            "PROD_READONLY_DB_BILLING_PROD_EXPECTED_ROLE",
            "PROD_READONLY_DB_BILLING_PROD_ALLOWED_SCHEMAS",
            "PROD_READONLY_DB_BILLING_PROD_TRANSPORT",
        ):
            env = dict(SAFE_ENV)
            env.pop(key)
            with self.assertRaises(ConfigError, msg=key):
                resolve_target("billing-prod", env)

    def test_transport_outside_tls_or_tunnel_is_rejected(self):
        for bad in ("ssl", "none", "disable", "", "TLS "):
            if bad.strip().lower() in ("tls", "tunnel"):
                continue
            env = dict(SAFE_ENV)
            env["PROD_READONLY_DB_BILLING_PROD_TRANSPORT"] = bad
            with self.assertRaises(ConfigError, msg=bad):
                resolve_target("billing-prod", env)

    def test_empty_schemas_are_rejected(self):
        for bad in ("", "  ", " , , "):
            env = dict(SAFE_ENV)
            env["PROD_READONLY_DB_BILLING_PROD_ALLOWED_SCHEMAS"] = bad
            with self.assertRaises(ConfigError, msg=repr(bad)):
                resolve_target("billing-prod", env)

    def test_unknown_alias_is_rejected(self):
        with self.assertRaises(ConfigError):
            resolve_target("no-such-alias", SAFE_ENV)

    def test_target_is_immutable(self):
        target = resolve_target("billing-prod", SAFE_ENV)
        self.assertIsInstance(target, TargetConfig)
        with self.assertRaises(AttributeError):
            target.service = "other"


class ValidateSqlTest(unittest.TestCase):
    def test_safe_queries_pass(self):
        for sql in SAFE_SQL:
            self.assertTrue(validate_sql(sql))

    def test_unsafe_queries_fail(self):
        for sql in UNSAFE_SQL:
            with self.assertRaises(UnsafeQueryError, msg=sql):
                validate_sql(sql)

    def test_error_never_repeats_the_query(self):
        for sql in UNSAFE_SQL:
            try:
                validate_sql(sql)
            except UnsafeQueryError as exc:
                for token in ("SELECT 1", "reporting.orders", "postgres", "\\copy"):
                    if token in sql:
                        self.assertNotIn(token, str(exc), msg=sql)
            else:
                self.fail(f"expected UnsafeQueryError: {sql!r}")

    def test_comments_and_strings_do_not_cause_false_positives(self):
        valid = (
            "-- leading comment\nSELECT id FROM reporting.orders",
            "SELECT id FROM reporting.orders -- trailing comment",
            "SELECT id /* inline ; comment */ FROM reporting.orders",
            "SELECT 'it''s; -- fine' AS note FROM reporting.orders",
            'SELECT "weird;col" FROM reporting.orders',
            "SELECT $tag$; -- not a terminator$tag$ AS x FROM reporting.orders",
        )
        for sql in valid:
            self.assertTrue(validate_sql(sql), msg=sql)

    def test_only_one_final_semicolon_is_tolerated(self):
        self.assertTrue(validate_sql("SELECT 1;"))
        self.assertTrue(validate_sql("SELECT 1 ;  \n"))
        for bad in ("SELECT 1;;", ";SELECT 1", "SELECT 1; SELECT 2", "SELECT 1;--x\nSELECT 2"):
            with self.assertRaises(UnsafeQueryError, msg=bad):
                validate_sql(bad)

    def test_only_select_or_with_select(self):
        for bad in (
            "UPDATE reporting.orders SET status = 1",
            "DELETE FROM reporting.orders",
            "INSERT INTO reporting.orders SELECT * FROM reporting.orders",
            "TABLE reporting.orders",
            "SHOW server_version",
            "SELECT",
            "WITH x AS (SELECT 1) TABLE x",
        ):
            with self.assertRaises(UnsafeQueryError, msg=bad):
                validate_sql(bad)

    def test_data_modifying_cte_is_rejected(self):
        for bad in (
            "WITH moved AS (UPDATE reporting.orders SET s = 1 RETURNING id) SELECT * FROM moved",
            "WITH added AS (INSERT INTO reporting.orders SELECT * FROM reporting.orders) SELECT 1",
            "WITH gone AS (DELETE FROM reporting.orders RETURNING id) SELECT * FROM gone",
        ):
            with self.assertRaises(UnsafeQueryError, msg=bad):
                validate_sql(bad)


class BuildLimitedQueryTest(unittest.TestCase):
    def test_wraps_query_with_limit_plus_one(self):
        out = build_limited_query("SELECT id FROM reporting.orders", max_rows=2)
        self.assertIn("LIMIT 3", out)
        self.assertIn("codex_readonly_result", out)

    def test_default_limit_is_201(self):
        out = build_limited_query("SELECT id FROM reporting.orders")
        self.assertIn("LIMIT 201", out)

    def test_strips_only_the_final_semicolon(self):
        out = build_limited_query("SELECT 1;", max_rows=10)
        self.assertIn("SELECT 1", out)
        self.assertNotIn(";;", out)

    def test_max_rows_above_1000_is_rejected(self):
        with self.assertRaises(ValueError):
            build_limited_query("SELECT 1", max_rows=1001)

    def test_max_rows_below_1_is_rejected(self):
        with self.assertRaises(ValueError):
            build_limited_query("SELECT 1", max_rows=0)

    def test_unsafe_query_is_rejected_before_wrapping(self):
        with self.assertRaises(UnsafeQueryError):
            build_limited_query("DELETE FROM reporting.orders")


def clean_preflight_payload(version=140000, **overrides):
    payload = {
        "database": "billing",
        "role": "codex_reader",
        "transaction_read_only": True,
        "default_transaction_read_only": True,
        "server_version_num": version,
        "administrative_attributes": [],
        "memberships": [],
        "owned_objects": [],
        "forbidden_privileges": [],
        "forbidden_parameter_privileges": [],
        "unexpected_connect_databases": [],
        "unexpected_schemas": [],
        "unsafe_routines": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


def csv_text(columns, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    return buf.getvalue()


def data_output(columns, rows):
    """Mirror real psql --csv output: two set_config framing lines first."""
    return "set_config\ncodex-prod-readonly\n" + csv_text(columns, rows)


class FakeRunner:
    """Injectable psql stand-in. Records argv/env/stdin, replays outputs."""

    def __init__(self, outputs=None, error=None):
        self.calls = []
        self.outputs = list(outputs or [])
        self.error = error

    def __call__(self, argv, env, stdin_text):
        self.calls.append(
            SimpleNamespace(argv=list(argv), env=dict(env), stdin_text=stdin_text)
        )
        if self.error is not None:
            raise self.error
        if self.outputs:
            return self.outputs.pop(0)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def user_query_calls(self):
        return [c for c in self.calls if "codex_readonly_result" in c.stdin_text]


def ok_result(stdout="", returncode=0):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def billing_target(transport="tls"):
    env = dict(SAFE_ENV)
    env["PROD_READONLY_DB_BILLING_PROD_TRANSPORT"] = transport
    return resolve_target("billing-prod", env)


class BuildPsqlEnvTest(unittest.TestCase):
    def test_service_mode_sets_pgservice_and_tls(self):
        env = build_psql_env(billing_target())
        self.assertEqual(env["PGSERVICE"], "billing-ro")
        self.assertEqual(env["PGSSLMODE"], "verify-full")
        self.assertNotIn("PGDATABASE", env)

    def test_url_mode_sets_pgdatabase_not_pgservice(self):
        env_vars = dict(SAFE_ENV)
        env_vars.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
        env_vars["PROD_READONLY_DB_BILLING_PROD_URL"] = "postgresql://fake.invalid/db"
        target = resolve_target("billing-prod", env_vars, allow_url_env=True)
        env = build_psql_env(target, allow_url_env=True)
        self.assertEqual(env["PGDATABASE"], "billing")
        self.assertNotIn("PGSERVICE", env)

    def test_tunnel_mode_sets_no_sslmode(self):
        env = build_psql_env(billing_target(transport="tunnel"))
        self.assertNotIn("PGSSLMODE", env)

    def test_url_with_downgraded_tls_is_rejected(self):
        for sslmode in ("disable", "allow", "prefer", "require", "verify-ca", "weird"):
            env_vars = dict(SAFE_ENV)
            env_vars.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
            env_vars["PROD_READONLY_DB_BILLING_PROD_URL"] = (
                f"postgresql://fake.invalid/db?sslmode={sslmode}"
            )
            target = resolve_target("billing-prod", env_vars, allow_url_env=True)
            with self.assertRaises(ConfigError, msg=sslmode):
                build_psql_env(target, allow_url_env=True)

    def test_url_mode_hands_psql_the_connection_via_libpq_vars(self):
        # libpq reads no URL from the environment: without these variables the
        # session silently aims at the local default socket.
        env_vars = dict(SAFE_ENV)
        env_vars.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
        env_vars["PROD_READONLY_DB_BILLING_PROD_URL"] = (
            "postgresql://reader:fake-pass@fake.invalid:6543/billing"
        )
        target = resolve_target("billing-prod", env_vars, allow_url_env=True)
        env = build_psql_env(target, allow_url_env=True)
        self.assertEqual(env["PGHOST"], "fake.invalid")
        self.assertEqual(env["PGPORT"], "6543")
        self.assertEqual(env["PGUSER"], "reader")
        self.assertEqual(env["PGPASSWORD"], "fake-pass")

    def test_url_without_host_is_rejected(self):
        env_vars = dict(SAFE_ENV)
        env_vars.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
        env_vars["PROD_READONLY_DB_BILLING_PROD_URL"] = "postgresql:///billing"
        target = resolve_target("billing-prod", env_vars, allow_url_env=True)
        with self.assertRaises(ConfigError):
            build_psql_env(target, allow_url_env=True)

    def test_url_without_opt_in_is_rejected_at_build(self):
        env_vars = dict(SAFE_ENV)
        env_vars.pop("PROD_READONLY_DB_BILLING_PROD_SERVICE")
        env_vars["PROD_READONLY_DB_BILLING_PROD_URL"] = "postgresql://fake.invalid/db"
        target = resolve_target("billing-prod", env_vars, allow_url_env=True)
        with self.assertRaises(ConfigError):
            build_psql_env(target, allow_url_env=False)


class ExecuteReadonlyTest(unittest.TestCase):
    def test_psql_receives_no_secret_or_query_in_argv(self):
        runner = FakeRunner(
            outputs=[
                ok_result(clean_preflight_payload()),
                ok_result(data_output(("id",), [("1",)])),
            ]
        )
        result = execute_readonly(
            billing_target(), "SELECT id FROM reporting.orders", runner=runner
        )
        self.assertEqual(result.columns, ("id",))
        for call in runner.calls:
            argv = " ".join(call.argv)
            self.assertNotIn("postgresql://", argv)
            self.assertNotIn("SELECT id", argv)
            self.assertNotIn("billing-ro", argv)
            self.assertTrue(
                call.stdin_text.startswith("BEGIN READ ONLY;"), call.stdin_text[:40]
            )
            self.assertIn("ROLLBACK;", call.stdin_text)
            # Unterminated payload turns the ROLLBACK into a column alias.
            self.assertIn(";\nROLLBACK;\n", call.stdin_text)

    def test_argv_uses_hardened_psql_flags(self):
        runner = FakeRunner(
            outputs=[
                ok_result(clean_preflight_payload()),
                ok_result(data_output(("id",), [("1",)])),
            ]
        )
        execute_readonly(
            billing_target(), "SELECT id FROM reporting.orders", runner=runner
        )
        argv = runner.calls[0].argv
        self.assertEqual(argv[0], "psql")
        for flag in ("-X", "--no-password", "-v", "ON_ERROR_STOP=1"):
            self.assertIn(flag, argv)

    def test_session_pins_timeouts_search_path_and_app_name(self):
        runner = FakeRunner(
            outputs=[
                ok_result(clean_preflight_payload()),
                ok_result(data_output(("id",), [("1",)])),
            ]
        )
        execute_readonly(
            billing_target(), "SELECT id FROM reporting.orders", runner=runner
        )
        for call in runner.calls:
            self.assertIn("SET LOCAL statement_timeout", call.stdin_text)
            self.assertIn("SET LOCAL lock_timeout", call.stdin_text)
            self.assertIn("SET LOCAL idle_in_transaction_session_timeout", call.stdin_text)
            self.assertIn("SET LOCAL search_path = pg_catalog", call.stdin_text)
            self.assertIn("codex-prod-readonly", call.stdin_text)

    def test_psql_error_carries_no_secret_values(self):
        runner = FakeRunner(
            outputs=[
                ok_result(
                    "",
                    returncode=2,
                )
            ]
        )
        runner.outputs[0].stderr = (
            "connection to server at secret.invalid failed: FATAL: oops"
        )
        with self.assertRaises(PsqlError) as ctx:
            execute_readonly(
                billing_target(), "SELECT id FROM reporting.orders", runner=runner
            )
        self.assertNotIn("secret.invalid", str(ctx.exception))

    def test_missing_psql_binary_is_a_clean_error(self):
        runner = FakeRunner(error=FileNotFoundError("psql"))
        with self.assertRaises(PsqlError):
            execute_readonly(
                billing_target(), "SELECT id FROM reporting.orders", runner=runner
            )

    def test_truncation_flag_on_limit_plus_one(self):
        runner = FakeRunner(
            outputs=[
                ok_result(clean_preflight_payload()),
                ok_result(data_output(("id",), [("1",), ("2",), ("3",)])),
            ]
        )
        result = execute_readonly(
            billing_target(),
            "SELECT id FROM reporting.orders",
            runner=runner,
            max_rows=2,
        )
        self.assertTrue(result.truncated)
        self.assertEqual(len(result.rows), 2)

    def test_exact_rows_are_not_truncated(self):
        runner = FakeRunner(
            outputs=[
                ok_result(clean_preflight_payload()),
                ok_result(data_output(("id",), [("1",), ("2",)])),
            ]
        )
        result = execute_readonly(
            billing_target(),
            "SELECT id FROM reporting.orders",
            runner=runner,
            max_rows=2,
        )
        self.assertFalse(result.truncated)
        self.assertEqual(result.rows, (("1",), ("2",)))

    def test_oversized_output_is_rejected(self):
        big = "id\n" + "x" * (1024 * 1024 + 8) + "\n"
        runner = FakeRunner(
            outputs=[ok_result(clean_preflight_payload()), ok_result(big)]
        )
        with self.assertRaises(OutputLimitError):
            execute_readonly(
                billing_target(), "SELECT id FROM reporting.orders", runner=runner
            )


class PreflightTest(unittest.TestCase):
    def refused(self, **overrides):
        runner = FakeRunner(outputs=[ok_result(clean_preflight_payload(**overrides))])
        with self.assertRaises(PreflightRefusedError):
            execute_readonly(
                billing_target(), "SELECT id FROM reporting.orders", runner=runner
            )
        return runner

    def test_divergent_database_is_refused_before_user_query(self):
        runner = self.refused(database="other")
        self.assertEqual(runner.user_query_calls(), [])

    def test_divergent_role_is_refused(self):
        self.refused(role="postgres")

    def test_writable_transaction_is_refused(self):
        self.refused(transaction_read_only=False)

    def test_writable_default_is_refused(self):
        self.refused(default_transaction_read_only=False)

    def test_administrative_attribute_is_refused(self):
        self.refused(administrative_attributes=["superuser"])

    def test_membership_is_refused(self):
        self.refused(memberships=["pg_read_all_data"])

    def test_ownership_is_refused(self):
        self.refused(owned_objects=["reporting.orders"])

    def test_forbidden_privilege_is_refused(self):
        self.refused(forbidden_privileges=["TEMPORARY ON DATABASE billing"])

    def test_parameter_privilege_is_refused(self):
        self.refused(forbidden_parameter_privileges=["SET ON PARAMETER idle_in_transaction_session_timeout"])

    def test_unexpected_connect_is_refused(self):
        self.refused(unexpected_connect_databases=["postgres"])

    def test_unexpected_schema_is_refused(self):
        self.refused(unexpected_schemas=["scratch"])

    def test_unsafe_routine_is_refused(self):
        self.refused(unsafe_routines=["reporting.unsafe_touch()"])

    def test_refusal_reports_categories_with_capped_sanitized_ids(self):
        runner = FakeRunner(
            outputs=[
                ok_result(
                    clean_preflight_payload(
                        owned_objects=[
                            "reporting.t1",
                            "reporting.t2",
                            "reporting.t3",
                            "reporting.t4",
                            "reporting.t5",
                            "reporting.t6",
                            "evil; DROP TABLE x",
                        ]
                    )
                )
            ]
        )
        with self.assertRaises(PreflightRefusedError) as ctx:
            execute_readonly(
                billing_target(), "SELECT id FROM reporting.orders", runner=runner
            )
        message = str(ctx.exception)
        self.assertIn("owned-objects", message)
        self.assertNotIn("evil;", message)
        self.assertNotIn("reporting.t6", message)

    def test_malformed_preflight_output_fails_closed(self):
        runner = FakeRunner(outputs=[ok_result("not json")])
        with self.assertRaises(PsqlError):
            run_preflight(billing_target(), runner=runner)

    def test_version_gates_extra_privilege_checks(self):
        runner = FakeRunner(
            outputs=[
                ok_result(clean_preflight_payload(version=170013)),
                ok_result("[]"),
                ok_result("[]"),
            ]
        )
        run_preflight(billing_target(), runner=runner)
        stdin_all = "\n".join(c.stdin_text for c in runner.calls)
        self.assertEqual(len(runner.calls), 3)
        self.assertIn("MAINTAIN", stdin_all)
        self.assertIn("has_parameter_privilege", stdin_all)

    def test_old_server_skips_unknown_privilege_names(self):
        runner = FakeRunner(outputs=[ok_result(clean_preflight_payload(version=140000))])
        result = run_preflight(billing_target(), runner=runner)
        self.assertEqual(len(runner.calls), 1)
        stdin_all = runner.calls[0].stdin_text
        self.assertNotIn("MAINTAIN", stdin_all)
        self.assertNotIn("has_parameter_privilege", stdin_all)
        self.assertIsInstance(result, PreflightResult)

    def test_assess_returns_empty_for_clean_preflight(self):
        target = billing_target()
        result = run_preflight(
            target,
            runner=FakeRunner(outputs=[ok_result(clean_preflight_payload())]),
        )
        self.assertEqual(assess_preflight(target, result), ())


if __name__ == "__main__":
    unittest.main()
