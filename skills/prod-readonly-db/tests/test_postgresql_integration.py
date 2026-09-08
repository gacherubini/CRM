"""Contract test against a disposable PostgreSQL fixture.

Runs only with RUN_POSTGRES_INTEGRATION=1 and the fixture up::

    docker compose -f skills/prod-readonly-db/tests/docker-compose.yml up -d --wait
    RUN_POSTGRES_INTEGRATION=1 python3 -m unittest discover \\
        -s skills/prod-readonly-db/tests -p 'test_postgresql_integration.py' -v
    docker compose -f skills/prod-readonly-db/tests/docker-compose.yml down -v

Everything here is fake: loopback only, password ``integration-only``,
three invented order rows. No production host is ever accepted.
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
)

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "readonly_psql.py"
)

HOST = "127.0.0.1"
PORT = "55432"
DATABASE = "fixturedb"
FAKE_PASSWORD = "integration-only"

RUN_INTEGRATION = os.environ.get("RUN_POSTGRES_INTEGRATION") == "1"


def alias_env(alias, user):
    key = alias.strip().upper().replace("-", "_")
    url = (
        f"postgresql://{user}:{FAKE_PASSWORD}@{HOST}:{PORT}/{DATABASE}"
    )
    assert HOST in url and "55432" in url
    return {
        f"PROD_READONLY_DB_{key}_URL": url,
        f"PROD_READONLY_DB_{key}_EXPECTED_DATABASE": DATABASE,
        f"PROD_READONLY_DB_{key}_EXPECTED_ROLE": user,
        f"PROD_READONLY_DB_{key}_ALLOWED_SCHEMAS": "reporting",
        f"PROD_READONLY_DB_{key}_TRANSPORT": "tunnel",
    }


def run_cli(alias, sql, extra_env, *args):
    env = dict(os.environ)
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, SCRIPT, "--alias", alias, "--allow-url-env", *args],
        input=sql,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def require_integration(test):
    if RUN_INTEGRATION:
        return test
    return unittest.skip("needs RUN_POSTGRES_INTEGRATION=1 with the fixture up")(
        test
    )


class FixtureContractTest(unittest.TestCase):
    @require_integration
    def test_safe_role_reads_limited_rows(self):
        proc = run_cli(
            "fixture-ok",
            "SELECT id, status FROM reporting.orders ORDER BY id",
            alias_env("fixture-ok", "readonly_ok"),
            "--max-rows",
            "2",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["alias"], "fixture-ok")
        self.assertEqual(payload["columns"], ["id", "status"])
        self.assertEqual(len(payload["rows"]), 2)
        self.assertTrue(payload["truncated"])

    @require_integration
    def test_bad_role_is_rejected_before_user_query(self):
        proc = run_cli(
            "fixture-bad",
            "SELECT id FROM reporting.orders",
            alias_env("fixture-bad", "readonly_bad"),
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertNotIn("codex_readonly_result", proc.stdout + proc.stderr)

    @require_integration
    def test_safe_role_cannot_insert_even_outside_wrapper(self):
        if shutil.which("psql") is None:
            self.skipTest("psql client not installed")
        extra = alias_env("fixture-ok", "readonly_ok")
        before = run_cli(
            "fixture-ok",
            "SELECT count(*) AS n FROM reporting.orders",
            extra,
        )
        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertEqual(json.loads(before.stdout)["rows"], [["3"]])

        direct_env = dict(os.environ)
        direct_env["PGPASSWORD"] = FAKE_PASSWORD
        direct = subprocess.run(
            [
                "psql",
                f"postgresql://readonly_ok@{HOST}:{PORT}/{DATABASE}",
                "-X",
                "--no-password",
                "-c",
                "INSERT INTO reporting.orders (id, status) VALUES (4242, 'hack')",
            ],
            env=direct_env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertNotEqual(direct.returncode, 0)

        after = run_cli(
            "fixture-ok",
            "SELECT count(*) AS n FROM reporting.orders",
            extra,
        )
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual(json.loads(after.stdout)["rows"], [["3"]])

    def test_zero_one_two_and_many_aliases_have_no_registry_limit(self):
        from readonly_psql import ConfigError, resolve_target

        with self.assertRaises(ConfigError):
            resolve_target("nothing-configured", {})
        for count in (1, 2, 12):
            env = {}
            for i in range(count):
                env.update(
                    {
                        f"PROD_READONLY_DB_F{i}_SERVICE": f"svc-{i}",
                        f"PROD_READONLY_DB_F{i}_EXPECTED_DATABASE": f"db-{i}",
                        f"PROD_READONLY_DB_F{i}_EXPECTED_ROLE": "reader",
                        f"PROD_READONLY_DB_F{i}_ALLOWED_SCHEMAS": "reporting",
                        f"PROD_READONLY_DB_F{i}_TRANSPORT": "tunnel",
                    }
                )
            targets = [resolve_target(f"f{i}", env) for i in range(count)]
            self.assertEqual(
                [t.service for t in targets], [f"svc-{i}" for i in range(count)]
            )


if __name__ == "__main__":
    unittest.main()
