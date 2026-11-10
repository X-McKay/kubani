"""What `remote_session.py` does with a person's token and a grant, run the way agent-ops runs it.

The real script is started as a subprocess through the same bootstrap and standard input `run.Runner` uses, against
an in-process stand-in for the Agent Policy Service. `temporalio` and the `runner` package are small stand-ins written
to a temporary directory: the script's use of the real ones is read, not exercised here.
"""

from __future__ import annotations

import http.server
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
from agent_ops import run  # noqa: E402

SESSION = "6b1f2f0e-3c1c-4f65-9d0a-5b0e2c7a9d41"
ACCESS = "eyJhY2Nlc3M.cGF5bG9hZC1vZi1hLXBlcnNvbg.c2lnbmF0dXJlLXZhbHVl"
REFRESH = "refresh-token-value-0123456789"
RUNNER_TOKEN = "runner-projected-token-abcdef"
HANDLE = "gh_0123456789abcdef0123456789abcdef"
EXPIRES = "2026-11-10T20:00:00Z"
RELEASE = "sample-2026-11-10-0123abcd"
GENERIC = "operation failed; retain the receipt and inspect the exact session"
REMOVE = "DELETE"

STUBS = {
    "temporalio/__init__.py": "",
    "temporalio/common.py": """
        class WorkflowIDReusePolicy:
            REJECT_DUPLICATE = "REJECT_DUPLICATE"
    """,
    "temporalio/service.py": """
        class RPCStatusCode:
            NOT_FOUND = "NOT_FOUND"
            UNAVAILABLE = "UNAVAILABLE"

        class RPCError(Exception):
            def __init__(self, message, status):
                super().__init__(message)
                self.status = status
    """,
    "runner/__init__.py": "",
    "runner/types.py": """
        import dataclasses
        import re

        @dataclasses.dataclass
        class SessionInput:
            tenant: str
            agent: str
            release: str
            session_id: str
            grant_handle: str | None
            task: object
            max_boundaries: int
            worker_pool: str

            def validate(self):
                if self.grant_handle is not None and not re.fullmatch("[A-Za-z0-9_-]{1,128}", self.grant_handle):
                    raise ValueError("grant_handle")
                if not isinstance(self.task, dict) or not 1 <= self.max_boundaries <= 1024:
                    raise ValueError("task or bound")

            @property
            def task_queue(self):
                return "sessions-" + self.tenant
    """,
    "runner/workflow.py": """
        from datetime import timedelta

        EXECUTION_TIMEOUT = timedelta(hours=1)

        class SessionWorkflow:
            def run(self, inp): ...
            def status(self): ...
    """,
    "runner/worker.py": """
        import dataclasses
        import json
        import os

        from temporalio.service import RPCError, RPCStatusCode

        PLAN = json.loads(os.environ["FAKE_TEMPORAL"])

        def note(**entry):
            with open(PLAN["log"], "a", encoding="utf-8") as out:
                out.write(json.dumps(entry, sort_keys=True) + "\\n")

        class Described:
            def __init__(self, workflow_id):
                self.workflow_id = workflow_id

            async def describe(self, rpc_timeout):
                answer = PLAN["exists"].pop(0) if PLAN["exists"] else False
                note(describe=self.workflow_id, exists=answer)
                if answer == "unavailable":
                    raise RPCError("unavailable", RPCStatusCode.UNAVAILABLE)
                if not answer:
                    raise RPCError("not found", RPCStatusCode.NOT_FOUND)

        class Started:
            first_execution_run_id = "0f8fad5b-d9cb-469f-a165-70867728950e"

        class Client:
            namespace = PLAN.get("namespace", "agents-tenant-test")

            def get_workflow_handle(self, workflow_id):
                return Described(workflow_id)

            async def start_workflow(self, fn, inp, **options):
                note(start=dataclasses.asdict(inp), id=options["id"], task_queue=options["task_queue"], reuse=options["id_reuse_policy"])
                if PLAN.get("start") == "fail":
                    raise RuntimeError("start failed for " + str(inp.grant_handle))
                return Started()

        async def connect(tenant):
            note(connect=tenant)
            return Client()
    """,
}


class Aps(http.server.ThreadingHTTPServer):
    """A stand-in for the Agent Policy Service: answers from `routes` and records every request it receives."""

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.seen: list[dict] = []
        self.routes: dict = {}
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class Handler(http.server.BaseHTTPRequestHandler):
    def answer(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self.server.seen.append({"method": self.command, "path": self.path, "authorization": self.headers.get("Authorization"), "body": json.loads(raw) if raw else None})
        status, doc, *rest = self.server.routes.get((self.command, self.path.split("?")[0]), (404, {"error": "not_found"}))
        body = doc if isinstance(doc, bytes) else json.dumps(doc).encode()
        self.send_response(status)
        for name, value in (rest[0] if rest else {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_DELETE = answer

    def log_message(self, *args):
        pass


class Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stubs_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.stubs_dir.cleanup)
        for name, text in STUBS.items():
            path = Path(cls.stubs_dir.name) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text))
        cls.code = run.REMOTE.read_bytes()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.aps = Aps()
        self.addCleanup(self.aps.server_close)
        self.addCleanup(self.aps.shutdown)
        self.token_path = self.tmp / "token"
        self.token_path.write_text(RUNNER_TOKEN + "\n")
        self.log = self.tmp / "temporal.log"
        self.aps.routes[("POST", "/v1/grants")] = (201, {"grant_handle": HANDLE})
        self.aps.routes[(REMOVE, "/v1/grants/" + HANDLE)] = (204, b"")

    def request(self, **changes) -> dict:
        request = {"action": "submit", "tenant": "tenant-test", "agent": "sample", "release": RELEASE, "session_id": SESSION, "task": {"request": "go"}, "max_boundaries": 64, "grant_handle": None}
        request.update(changes)
        return {k: v for k, v in request.items() if v is not ...}

    def deposit(self, **changes) -> dict:
        return dict({"access_token": ACCESS, "refresh_token": REFRESH, "expires_at": EXPIRES}, **changes)

    def call(self, request, *, exists=(), start="ok", namespace="agents-tenant-test", aps_url=None, token_path=None):
        """Run the script as `Runner.remote` does. Returns (exit code, the one JSON line it printed)."""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": self.stubs_dir.name,
            "PYTHONDONTWRITEBYTECODE": "1",
            "APS_URL": aps_url or self.aps.url,
            "APS_TOKEN_PATH": str(token_path or self.token_path),
            "FAKE_TEMPORAL": json.dumps({"exists": list(exists), "start": start, "namespace": namespace, "log": str(self.log)}),
            # A proxy in the pod environment must not be given the person's token.
            "http_proxy": "http://127.0.0.1:1",
            "HTTP_PROXY": "http://127.0.0.1:1",
            "all_proxy": "http://127.0.0.1:1",
        }
        done = subprocess.run([sys.executable, "-c", run.BOOTSTRAP, str(len(self.code))], input=self.code + json.dumps(request, sort_keys=True).encode(), capture_output=True, env=env, timeout=60, check=False)
        lines = done.stdout.decode().splitlines()
        self.assertEqual(len(lines), 1, done.stderr.decode())
        # Whatever happened, the pod's output carries no token and no handle. agent-ops saves this stderr to a file.
        for stream in (done.stdout.decode(), done.stderr.decode()):
            for secret in (ACCESS, *ACCESS.split("."), REFRESH, RUNNER_TOKEN, HANDLE):
                self.assertNotIn(secret, stream)
        self.assertEqual(done.stderr, b"")
        return done.returncode, json.loads(lines[0])

    def refused(self, request, **kwargs) -> str:
        code, doc = self.call(request, **kwargs)
        self.assertEqual((code, set(doc)), (2, {"error", "error_type"}))
        return doc["error"]

    def temporal(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def started(self) -> list[dict]:
        return [entry for entry in self.temporal() if "start" in entry]

    def requests(self, method=None) -> list[dict]:
        return [seen for seen in self.aps.seen if method in (None, seen["method"])]

    def grant_held(self, tenant="tenant-test", agent="sample", session=SESSION):
        self.aps.routes[("GET", "/v1/sessions")] = (200, {"sessions": [
            {"session_id": "11111111-2222-4333-8444-555555555555", "tenant": "tenant-test", "agent": "sample", "generation": 1, "grant_handle": "gh_another"},
            {"session_id": SESSION, "tenant": tenant, "agent": agent, "generation": 0, "grant_handle": HANDLE},
        ]})
        self.aps.routes[("GET", "/v1/grants/" + HANDLE)] = (200, {"session_id": session, "tenant": tenant, "agent": agent, "expires_at": EXPIRES})


class DepositTests(Case):
    def test_submit_with_a_token_deposits_it_then_starts_the_workflow_with_the_handle(self):
        code, doc = self.call(self.request(deposit=self.deposit()))
        self.assertEqual(code, 0)
        self.assertEqual(doc, {"workflow_id": f"session:tenant-test:sample:{SESSION}", "run_id": "0f8fad5b-d9cb-469f-a165-70867728950e", "namespace": "agents-tenant-test", "task_queue": "sessions-tenant-test"})
        self.assertEqual(self.requests(), [{"method": "POST", "path": "/v1/grants", "authorization": "Bearer " + ACCESS, "body": {"session_id": SESSION, "tenant": "tenant-test", "agent": "sample", "refresh_token": REFRESH, "expires_at": EXPIRES}}])
        (start,) = self.started()
        self.assertEqual(start["start"], {"tenant": "tenant-test", "agent": "sample", "release": RELEASE, "session_id": SESSION, "grant_handle": HANDLE, "task": {"request": "go"}, "max_boundaries": 64, "worker_pool": "legacy"})
        self.assertEqual((start["id"], start["task_queue"], start["reuse"]), (f"session:tenant-test:sample:{SESSION}", "sessions-tenant-test", "REJECT_DUPLICATE"))

    def test_no_refresh_token_is_sent_as_null(self):
        self.assertEqual(self.call(self.request(deposit=self.deposit(refresh_token=None)))[0], 0)
        self.assertIsNone(self.requests("POST")[0]["body"]["refresh_token"])
        self.assertEqual(set(self.requests("POST")[0]["body"]), {"session_id", "tenant", "agent", "refresh_token", "expires_at"})

    def test_deposit_action_leaves_a_grant_and_starts_nothing(self):
        request = {"action": "deposit", "tenant": "tenant-test", "agent": "sample", "session_id": SESSION, "deposit": self.deposit()}
        self.assertEqual(self.call(request), (0, {"deposited": True, "session_id": SESSION}))
        self.assertEqual([(seen["method"], seen["path"], seen["authorization"]) for seen in self.requests()], [("POST", "/v1/grants", "Bearer " + ACCESS)])
        self.assertEqual(self.started(), [])

    def test_deposit_action_refuses_a_session_that_already_runs_and_anything_extra(self):
        request = {"action": "deposit", "tenant": "tenant-test", "agent": "sample", "session_id": SESSION, "deposit": self.deposit()}
        self.assertEqual(self.refused(request, exists=[True]), "session identity already exists")
        self.assertEqual(self.refused(dict(request, grant_handle="h-1")), "invalid request")
        self.assertEqual(self.refused(dict(request, release=RELEASE)), "invalid request")
        self.assertEqual(self.refused({k: v for k, v in request.items() if k != "deposit"}), "invalid request")
        self.assertEqual(self.refused(dict(request, session_id=SESSION.upper())), "session must be a canonical UUIDv4")
        self.assertEqual((self.requests(), self.started()), ([], []))

    def test_refusals_of_the_policy_service_become_fixed_messages(self):
        answers = [
            (401, {"error": "invalid_token"}, "deposit refused: the policy service did not accept the token"),
            (403, {"error": "forbidden", "reason": "subject_not_user"}, "deposit refused: the token belongs to an agent, not a person"),
            (403, {"error": "forbidden", "reason": "scope"}, "deposit refused: the token lacks this agent's delegation scope"),
            (403, {"error": "forbidden", "reason": "may_act"}, "deposit refused: the token names no agent allowed to act for the person"),
            (403, {"error": "forbidden", "reason": "something " + ACCESS}, "grant deposit failed"),
            (403, b"not json " + ACCESS.encode(), "grant deposit failed"),
            (409, {"error": "conflict"}, "deposit refused: this session already has a grant"),
            (400, {"error": "invalid_request"}, "deposit refused: the policy service rejected the request"),
            (500, {"error": "server_error"}, "grant deposit failed"),
            (200, {"grant_handle": HANDLE}, "grant deposit failed"),
            (201, {"grant_handle": "not a handle"}, "grant deposit failed"),
            (201, {"grant_handle": None}, "grant deposit failed"),
            (201, ["gh_x"], "grant deposit failed"),
        ]
        for action in ("submit", "deposit"):
            for index, (status, doc, expected) in enumerate(answers):
                with self.subTest(action=action, status=status, index=index):
                    self.aps.routes[("POST", "/v1/grants")] = (status, doc)
                    request = self.request(deposit=self.deposit()) if action == "submit" else {"action": "deposit", "tenant": "tenant-test", "agent": "sample", "session_id": SESSION, "deposit": self.deposit()}
                    self.assertEqual(self.refused(request), expected)
        self.assertEqual(self.started(), [], "no workflow starts without a grant")
        self.assertEqual(self.requests(REMOVE), [], "nothing was deposited, so nothing is removed")

    def test_an_unreachable_policy_service_is_one_fixed_message(self):
        closed = Aps()
        url = closed.url
        closed.shutdown()
        closed.server_close()
        self.assertEqual(self.refused(self.request(deposit=self.deposit()), aps_url=url), "policy service unreachable")
        self.assertEqual(self.refused(self.request(deposited_grant=True), aps_url=url), "policy service unreachable")
        self.assertEqual(self.refused(self.request(deposited_grant=True), token_path=self.tmp / "absent"), "policy service unreachable")
        self.assertEqual((self.requests(), self.started()), ([], []))

    def test_a_redirect_is_not_followed(self):
        self.aps.routes[("POST", "/v1/grants")] = (307, {}, {"Location": self.aps.url + "/elsewhere"})
        self.aps.routes[("POST", "/elsewhere")] = (201, {"grant_handle": HANDLE})
        self.assertEqual(self.refused(self.request(deposit=self.deposit())), "grant deposit failed")
        self.assertEqual([seen["path"] for seen in self.requests()], ["/v1/grants"])
        self.assertEqual(self.started(), [])

    def test_malformed_requests_are_refused_before_a_token_leaves_the_pod(self):
        bad = {
            "two grant sources": self.request(deposit=self.deposit(), grant_handle="h-1"),
            "token and deposited": self.request(deposit=self.deposit(), deposited_grant=True),
            "handle and deposited": self.request(grant_handle="h-1", deposited_grant=True),
            "deposited not a boolean": self.request(deposited_grant="yes"),
            "deposit not an object": self.request(deposit=ACCESS),
            "extra deposit key": self.request(deposit=self.deposit(session_id=SESSION)),
            "missing deposit key": self.request(deposit={"access_token": ACCESS, "expires_at": EXPIRES}),
            "token with a space": self.request(deposit=self.deposit(access_token=ACCESS + " x")),
            "token with a line break": self.request(deposit=self.deposit(access_token=ACCESS + "\r\nX-Other: 1")),
            "empty token": self.request(deposit=self.deposit(access_token="")),
            "token not a string": self.request(deposit=self.deposit(access_token=None)),
            "empty refresh token": self.request(deposit=self.deposit(refresh_token="")),
            "refresh token not a string": self.request(deposit=self.deposit(refresh_token=7)),
            "expiry not a string": self.request(deposit=self.deposit(expires_at=None)),
            "release of another agent": self.request(deposit=self.deposit(), release="other-2026-11-10-0123abcd"),
            "tenant": self.request(deposit=self.deposit(), tenant="Tenant_Test"),
        }
        for name, request in bad.items():
            with self.subTest(name):
                self.assertEqual(self.refused(request), "invalid request")
        # The session input is validated before the deposit, so a bad task or bound costs the person no grant.
        self.assertEqual(self.refused(self.request(deposit=self.deposit(), task="go")), GENERIC)
        self.assertEqual(self.refused(self.request(deposit=self.deposit(), max_boundaries=0)), GENERIC)
        self.assertEqual(self.refused(self.request(deposit=self.deposit()), namespace="agents-other"), "invalid request")
        self.assertEqual(self.refused(self.request(deposit=self.deposit()), exists=[True]), "session identity already exists")
        self.assertEqual(self.refused(self.request(deposit=self.deposit()), exists=["unavailable"]), GENERIC)
        self.assertEqual((self.requests(), self.started()), ([], []))


class DepositedGrantTests(Case):
    def test_the_grant_deposited_for_the_session_is_found_with_the_runners_own_token(self):
        self.grant_held()
        code, doc = self.call(self.request(deposited_grant=True))
        self.assertEqual((code, doc["workflow_id"]), (0, f"session:tenant-test:sample:{SESSION}"))
        self.assertEqual(self.requests(), [
            {"method": "GET", "path": "/v1/sessions", "authorization": "Bearer " + RUNNER_TOKEN, "body": None},
            {"method": "GET", "path": "/v1/grants/" + HANDLE, "authorization": "Bearer " + RUNNER_TOKEN, "body": None},
        ])
        (start,) = self.started()
        self.assertEqual((start["start"]["grant_handle"], start["start"]["session_id"]), (HANDLE, SESSION))

    def test_no_grant_for_the_session_is_an_answer_and_starts_nothing(self):
        other = {"session_id": "11111111-2222-4333-8444-555555555555", "tenant": "tenant-test", "agent": "sample", "generation": 1, "grant_handle": "gh_another"}
        listings = {
            "no session": [],
            "another session only": [other],
            "a session without a grant": [other, {"session_id": SESSION, "tenant": "tenant-test", "agent": "sample", "generation": 1, "grant_handle": None}],
        }
        for name, rows in listings.items():
            with self.subTest(name):
                self.aps.routes[("GET", "/v1/sessions")] = (200, {"sessions": rows})
                self.assertEqual(self.call(self.request(deposited_grant=True)), (0, {"granted": False, "session_id": SESSION}))
        self.grant_held()
        self.aps.routes[("GET", "/v1/grants/" + HANDLE)] = (404, {"error": "not_found"})
        self.assertEqual(self.call(self.request(deposited_grant=True)), (0, {"granted": False, "session_id": SESSION}), "the record is listed but the token is gone")
        self.assertEqual((self.started(), self.requests("POST"), self.requests(REMOVE)), ([], [], []))

    def test_a_grant_that_names_another_tenant_agent_or_session_is_refused(self):
        expected = "the session's grant names another tenant or agent"
        self.grant_held(agent="other")
        self.assertEqual(self.refused(self.request(deposited_grant=True)), expected)
        self.grant_held(tenant="tenant-other")
        self.assertEqual(self.refused(self.request(deposited_grant=True)), expected)
        self.assertEqual(self.requests("GET")[-1]["path"], "/v1/sessions", "the listing already disagreed; the grant was not read")
        for field, value in (("session_id", "11111111-2222-4333-8444-555555555555"), ("tenant", "tenant-other"), ("agent", "other")):
            self.grant_held()
            status, doc = self.aps.routes[("GET", "/v1/grants/" + HANDLE)]
            self.aps.routes[("GET", "/v1/grants/" + HANDLE)] = (status, dict(doc, **{field: value}))
            self.assertEqual(self.refused(self.request(deposited_grant=True)), expected, field)
        row = {"session_id": SESSION, "tenant": "tenant-test", "agent": "sample", "generation": 0}
        for rows in ([dict(row, grant_handle=HANDLE), dict(row, grant_handle=HANDLE)], [dict(row, grant_handle="../sessions")], [dict(row, grant_handle=7)]):
            self.aps.routes[("GET", "/v1/sessions")] = (200, {"sessions": rows})
            before = len(self.requests())
            self.assertEqual(self.refused(self.request(deposited_grant=True)), expected)
            self.assertEqual(len(self.requests()) - before, 1, "a handle that is not a handle is never placed in a path")
        self.assertEqual((self.started(), self.requests(REMOVE)), ([], []))

    def test_a_listing_or_read_that_fails_is_refused(self):
        expected = "policy service session listing failed"
        for answer in ((500, {"error": "server_error"}), (403, {"error": "forbidden"}), (200, {"sessions": None}), (200, ["x"]), (200, b"not json")):
            self.aps.routes[("GET", "/v1/sessions")] = answer
            self.assertEqual(self.refused(self.request(deposited_grant=True)), expected)
        self.grant_held()
        self.aps.routes[("GET", "/v1/grants/" + HANDLE)] = (500, {"error": "server_error"})
        self.assertEqual(self.refused(self.request(deposited_grant=True)), expected)
        self.assertEqual(self.started(), [])


class ReleaseTests(Case):
    """A grant this call holds is removed when no workflow took it over, and only then."""

    def removal(self) -> list[dict]:
        return [{k: seen[k] for k in ("path", "authorization")} for seen in self.requests(REMOVE)]

    def test_a_start_that_fails_after_the_deposit_removes_the_grant_for_this_session(self):
        self.assertEqual(self.refused(self.request(deposit=self.deposit()), start="fail"), GENERIC)
        self.assertEqual(self.removal(), [{"path": f"/v1/grants/{HANDLE}?session_id={SESSION}", "authorization": "Bearer " + RUNNER_TOKEN}])
        self.assertEqual([entry["exists"] for entry in self.temporal() if "describe" in entry], [False, False])

    def test_a_start_that_fails_after_an_awaited_grant_was_found_removes_it_too(self):
        self.grant_held()
        self.assertEqual(self.refused(self.request(deposited_grant=True), start="fail"), GENERIC)
        self.assertEqual(self.removal(), [{"path": f"/v1/grants/{HANDLE}?session_id={SESSION}", "authorization": "Bearer " + RUNNER_TOKEN}])

    def test_nothing_is_removed_when_the_workflow_exists_after_all_or_cannot_be_checked(self):
        self.assertEqual(self.refused(self.request(deposit=self.deposit()), start="fail", exists=[False, True]), GENERIC)
        self.assertEqual(self.refused(self.request(deposit=self.deposit()), start="fail", exists=[False, "unavailable"]), GENERIC)
        self.assertEqual(self.removal(), [])
        self.assertEqual(len(self.requests("POST")), 2)

    def test_a_removal_that_fails_does_not_change_the_answer(self):
        self.aps.routes[(REMOVE, "/v1/grants/" + HANDLE)] = (403, {"error": "forbidden", "reason": "session"})
        self.assertEqual(self.refused(self.request(deposit=self.deposit()), start="fail"), GENERIC)
        self.assertEqual(len(self.removal()), 1)

    def test_a_handle_given_by_the_submitter_is_never_removed_and_needs_no_policy_service(self):
        closed = Aps()
        url = closed.url
        closed.shutdown()
        closed.server_close()
        self.assertEqual(self.call(self.request(grant_handle="h-1"), aps_url=url)[0], 0)
        self.assertEqual(self.call(self.request(), aps_url=url)[0], 0)
        self.assertEqual([start["start"]["grant_handle"] for start in self.started()], ["h-1", None])
        self.assertEqual(self.refused(self.request(grant_handle="h-1"), start="fail"), GENERIC)
        self.assertEqual(self.refused(self.request(), start="fail"), GENERIC)
        self.assertEqual(self.requests(), [])


if __name__ == "__main__":
    unittest.main()
