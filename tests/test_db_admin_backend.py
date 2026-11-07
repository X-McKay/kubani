"""Dedicated DB monitor manifests and optional real isolated PostgreSQL checks.

DB_ADMIN_TEST_CONTAINER must name an explicitly owned, network-none local test
container. These checks never discover/connect to a cluster or production DB.
"""

import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "infrastructure/gitops/apps/mcp"
SQL = MCP / "postgres-admin-monitor.sql"
VIEWS = ("instance_health", "connection_summary", "database_stats", "blocking_summary")


class BackendManifests(unittest.TestCase):
    def test_bootstrap_contract_exists(self):
        text = SQL.read_text()
        self.assertIn("SECURITY DEFINER", text)
        self.assertIn("pg_read_all_stats", text)
        self.assertNotRegex(text, r"GRANT\s+pg_monitor\b")
        self.assertIn("\\getenv monitor_password MCP_PASSWORD", text)
        self.assertIn("SET search_path = pg_catalog, pg_temp", text)

    def test_dedicated_instance_is_digest_pinned_restricted_and_credential_isolated(
        self,
    ):
        docs = list(yaml.safe_load_all((MCP / "postgres-admin-mcp.yaml").read_text()))
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        spec = deployment["spec"]["template"]["spec"]
        self.assertFalse(spec["automountServiceAccountToken"])
        container = spec["containers"][0]
        self.assertEqual(
            container["image"],
            "docker.io/crystaldba/postgres-mcp@sha256:dbbd346860d29f1543e991f30f3284bf4ab5f096d049ecc3426528f20b1b6e6b",
        )
        self.assertIn("--access-mode=restricted", container["args"])
        self.assertEqual(
            container["env"],
            [
                {
                    "name": "DATABASE_URI",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "postgres-admin-mcp",
                            "key": "DATABASE_URI",
                        }
                    },
                }
            ],
        )
        job = next(
            d
            for d in yaml.safe_load_all(
                (MCP / "postgres-admin-role-job.yaml").read_text()
            )
            if d["kind"] == "Job"
        )
        command = job["spec"]["template"]["spec"]["containers"][0]["command"]
        self.assertNotIn("-v pw=", str(command))
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 300)


@unittest.skipUnless(
    os.environ.get("DB_ADMIN_TEST_CONTAINER"),
    "explicit owned local PostgreSQL container required",
)
class RealPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = os.environ["DB_ADMIN_TEST_CONTAINER"]
        if not re.fullmatch("[a-f0-9]{64}", cls.container):
            raise ValueError("exact owned container ID required")
        value = json.loads(
            subprocess.check_output(["docker", "inspect", cls.container], text=True)
        )[0]
        if (
            value["Config"].get("Labels", {}).get("kubani.db-admin-test") != "true"
            or value["HostConfig"]["NetworkMode"] != "none"
            or value["HostConfig"].get("Privileged")
            or value.get("Mounts")
            and any(m["Type"] == "bind" for m in value["Mounts"])
        ):
            raise ValueError(
                "isolated owned network-none/no-host-bind container required"
            )
        cls.password = secrets.token_urlsafe(24)
        cls.psql(
            "CREATE SCHEMA IF NOT EXISTS private_app; CREATE TABLE IF NOT EXISTS private_app.rows(value text); INSERT INTO private_app.rows VALUES ('PRIVATE_APP_ROW');"
        )

    @classmethod
    def psql(cls, sql, user="postgres", expect_success=True):
        env = dict(os.environ, MCP_PASSWORD=cls.password)
        value = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "-e",
                "MCP_PASSWORD",
                cls.container,
                "psql",
                "-X",
                "-q",
                "-A",
                "-t",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-U",
                user,
                "-d",
                "postgres",
            ],
            input=sql,
            text=True,
            capture_output=True,
            env=env,
            timeout=30,
        )
        if expect_success and value.returncode:
            raise AssertionError("local PostgreSQL rejected SQL: " + value.stderr)
        if not expect_success and not value.returncode:
            raise AssertionError("forbidden local SQL unexpectedly allowed")
        return value

    def bootstrap(self):
        self.psql(SQL.read_text())

    def test_bootstrap_idempotence_and_four_safe_view_outputs(self):
        self.bootstrap()
        self.bootstrap()
        for name in VIEWS:
            raw = self.psql(
                f"SELECT row_to_json(result)::text AS payload FROM db_admin_monitor.{name} AS result LIMIT 16;",
                user="db_admin_monitor",
            ).stdout
            rows = [json.loads(line) for line in raw.splitlines()]
            self.assertTrue(rows)
            self.assertLessEqual(len(rows), 16)
            for row in rows:
                self.assertNotIn("PRIVATE_APP_ROW", json.dumps(row))
                self.assertFalse(
                    set(row)
                    & {"query", "pid", "usename", "client_addr", "application_name"}
                )
        row = json.loads(
            self.psql(
                "SELECT row_to_json(x) FROM db_admin_monitor.instance_health x;",
                user="db_admin_monitor",
            ).stdout
        )
        self.assertGreaterEqual(row["database_count"], 1)

    def test_login_cannot_read_app_rows_write_or_become_monitor_owner(self):
        self.bootstrap()
        for sql in (
            "SELECT * FROM private_app.rows;",
            "CREATE TABLE public.unauthorized(x int);",
            "SET ROLE db_admin_monitor_owner;",
            "SET ROLE pg_read_all_stats;",
            "SELECT pg_catalog.pg_read_file('/etc/passwd');",
        ):
            with self.subTest(sql=sql):
                self.psql(
                    "SET default_transaction_read_only=off; " + sql,
                    user="db_admin_monitor",
                    expect_success=False,
                )
        flags = self.psql(
            "SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname='db_admin_monitor';"
        ).stdout.strip()
        self.assertEqual(flags, "db_admin_monitor|f|f|f|f|f")
        self.assertEqual(
            self.psql(
                "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname='db_admin_monitor';"
            ).stdout.strip(),
            "0",
        )

    def test_public_cannot_execute_safe_functions(self):
        self.bootstrap()
        self.psql(
            "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='db_admin_unrelated') THEN CREATE ROLE db_admin_unrelated LOGIN; END IF; END $$;"
        )
        self.psql(
            "SELECT * FROM db_admin_monitor.instance_health_fn();",
            user="db_admin_unrelated",
            expect_success=False,
        )

    @classmethod
    def session(cls, sql):
        value = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                cls.container,
                "psql",
                "-X",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-U",
                "postgres",
                "-d",
                "postgres",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        value.stdin.write(sql + "\n")
        value.stdin.flush()
        return value

    def wait_sql(self, sql):
        until = time.monotonic() + 5
        while time.monotonic() < until:
            if self.psql(sql).stdout.strip() == "t":
                return
            time.sleep(0.05)
        self.fail("synthetic local session never reached expected state")

    def test_other_session_raw_query_text_is_not_visible_to_login(self):
        self.bootstrap()
        active = self.session("SELECT 'PRIVATE_QUERY_MARKER', pg_sleep(8);")
        try:
            self.wait_sql(
                "SELECT EXISTS(SELECT FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND query LIKE '%PRIVATE_QUERY_MARKER%' AND state='active');"
            )
            raw = self.psql(
                "SELECT query FROM pg_catalog.pg_stat_activity WHERE pid<>pg_backend_pid() AND usename='postgres';",
                user="db_admin_monitor",
            ).stdout
            self.assertNotIn("PRIVATE_QUERY_MARKER", raw)
            self.assertIn("<insufficient privilege>", raw)
            groups = [
                json.loads(line)
                for line in self.psql(
                    "SELECT row_to_json(x) FROM db_admin_monitor.connection_summary x;",
                    user="db_admin_monitor",
                ).stdout.splitlines()
            ]
            self.assertTrue(
                any(
                    r["state"] == "active" and r["wait_event_type"] == "Timeout"
                    for r in groups
                )
            )
            self.assertGreaterEqual(groups[0]["total_connections"], 2)
        finally:
            active.communicate(input="\\q\n", timeout=12)

    def test_real_blocked_lock_reports_waitstart_without_raw_identifiers(self):
        self.bootstrap()
        locker = self.session(
            "BEGIN; LOCK TABLE private_app.rows IN ACCESS EXCLUSIVE MODE;"
        )
        waiter = None
        try:
            self.wait_sql(
                "SELECT EXISTS(SELECT FROM pg_locks l JOIN pg_class c ON c.oid=l.relation WHERE c.relname='rows' AND l.mode='AccessExclusiveLock' AND l.granted);"
            )
            waiter = self.session("SELECT count(*) FROM private_app.rows;")
            self.wait_sql(
                "SELECT EXISTS(SELECT FROM pg_locks l JOIN pg_class c ON c.oid=l.relation WHERE c.relname='rows' AND NOT l.granted AND l.waitstart IS NOT NULL);"
            )
            row = json.loads(
                self.psql(
                    "SELECT row_to_json(x) FROM db_admin_monitor.blocking_summary x;",
                    user="db_admin_monitor",
                ).stdout
            )
            self.assertGreaterEqual(row["blocked_connections"], 1)
            self.assertGreaterEqual(row["blocking_edges"], 1)
            self.assertIsInstance(row["oldest_wait_seconds"], int)
            self.assertGreaterEqual(row["oldest_wait_seconds"], 0)
            self.assertFalse(set(row) & {"pid", "query", "usename", "client_addr"})
        finally:
            locker.communicate(input="ROLLBACK;\n\\q\n", timeout=10)
            if waiter:
                waiter.communicate(input="\\q\n", timeout=10)

    def test_database_sizes_need_no_extra_owner_grant_and_top16_coverage_is_explicit(
        self,
    ):
        self.bootstrap()
        for index in range(17):
            name = "monitor_cap_" + str(index)
            if (
                self.psql(
                    f"SELECT NOT EXISTS(SELECT FROM pg_database WHERE datname='{name}');"
                ).stdout.strip()
                == "t"
            ):
                self.psql(f"CREATE DATABASE {name};")
        self.psql("REVOKE CONNECT ON DATABASE monitor_cap_0 FROM PUBLIC;")
        self.psql(
            "SELECT pg_database_size('monitor_cap_0');",
            user="db_admin_monitor",
            expect_success=False,
        )
        rows = [
            json.loads(line)
            for line in self.psql(
                "SELECT row_to_json(x) FROM db_admin_monitor.database_stats x;",
                user="db_admin_monitor",
            ).stdout.splitlines()
        ]
        self.assertEqual(len(rows), 16)
        self.assertTrue(
            all(
                isinstance(row["size_bytes"], int) and row["size_bytes"] >= 0
                for row in rows
            )
        )
        count = json.loads(
            self.psql(
                "SELECT row_to_json(x) FROM db_admin_monitor.instance_health x;",
                user="db_admin_monitor",
            ).stdout
        )["database_count"]
        self.assertGreater(count, len(rows))
        self.assertEqual(
            self.psql(
                "SELECT string_agg(parent.rolname,',') FROM pg_auth_members m JOIN pg_roles member ON member.oid=m.member JOIN pg_roles parent ON parent.oid=m.roleid WHERE member.rolname='db_admin_monitor_owner';"
            ).stdout.strip(),
            "pg_read_all_stats",
        )

    def test_privileged_role_collision_fails_without_silent_demotion(self):
        self.bootstrap()
        self.psql("ALTER ROLE db_admin_monitor CREATEDB;")
        try:
            self.psql(SQL.read_text(), expect_success=False)
            self.assertEqual(
                self.psql(
                    "SELECT rolcreatedb FROM pg_roles WHERE rolname='db_admin_monitor';"
                ).stdout.strip(),
                "t",
            )
        finally:
            self.psql("ALTER ROLE db_admin_monitor NOCREATEDB;")

    def test_direct_or_public_app_privileges_and_reverse_membership_fail_closed(self):
        self.bootstrap()
        cases = [
            (
                "GRANT SELECT ON private_app.rows TO db_admin_monitor;",
                "REVOKE SELECT ON private_app.rows FROM db_admin_monitor;",
            ),
            (
                "CREATE TABLE public.monitor_public_fixture(x int); GRANT SELECT ON public.monitor_public_fixture TO PUBLIC;",
                "DROP TABLE public.monitor_public_fixture;",
            ),
            (
                "GRANT db_admin_monitor_owner TO db_admin_unrelated;",
                "REVOKE db_admin_monitor_owner FROM db_admin_unrelated;",
            ),
            (
                "CREATE FUNCTION public.monitor_leaky_fn() RETURNS SETOF private_app.rows LANGUAGE sql SECURITY DEFINER AS $$ SELECT * FROM private_app.rows $$;",
                "DROP FUNCTION public.monitor_leaky_fn();",
            ),
        ]
        self.psql(
            "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='db_admin_unrelated') THEN CREATE ROLE db_admin_unrelated LOGIN; END IF; END $$;"
        )
        for grant, revoke in cases:
            with self.subTest(grant=grant):
                self.psql(grant)
                try:
                    self.psql(SQL.read_text(), expect_success=False)
                finally:
                    self.psql(revoke)
        self.bootstrap()
