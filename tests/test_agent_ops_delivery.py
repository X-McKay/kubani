"""Operator commands for the delivery path: sessions over HTTP, release changes and revocation files.

A fake registry on loopback records every request, the sign-in is replaced by a fake that hands out a marked token, and the
cluster is a fake that refuses `exec`. No real credential, cluster or network.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
import registry_feed  # noqa: E402
from agent_ops import delivery, layout  # noqa: E402

import test_agent_ops as base  # noqa: E402
from test_agent_ops_outcomes import ACCEPTED, DONE, RUNNING  # noqa: E402
from test_agent_ops_registry import DEP, DEP_ID, RegistryCase, error  # noqa: E402
from test_registry_feed import build_tree  # noqa: E402

SESSIONS = "/v1/tenants/tenant-test/sessions"
OLD = "sample-2026-11-01-aaaa1111"
NEW = "sample-2026-11-09-abcdef12"
BEARER = "Bearer person-token"


def owned_agent(current: str | None = NEW) -> dict:
    annotations = {delivery.OWNER_ANNOTATION: DEP_ID}
    if current:
        annotations[delivery.CURRENT_ANNOTATION] = current
    return {"metadata": {"name": "sample", "namespace": "tenant-test", "annotations": annotations}, "spec": {}}


class SessionKube:
    """Reads the live Agent only. `exec` is what the old path uses, so it fails the test."""

    def __init__(self, agent: dict):
        self.agent, self.calls = agent, []

    def get(self, kind, name, namespace, *, selector=None):
        self.calls.append((kind, name, namespace))
        if kind == "agents":
            return {"items": [self.agent]}
        raise AssertionError(f"the delivery path read {kind}")

    def exec(self, *args, **kwargs):
        raise AssertionError("the delivery path used kubectl exec")


class DeliveryCase(RegistryCase):
    def setUp(self):
        super().setUp()
        self.root = base.make_root(self.tmp)
        self.out = self.tmp / "run"
        self.kube = SessionKube(owned_agent())

    def serve_session(self, *polls: dict, accepted: dict | None = None) -> None:
        """POST answers 202 for the id it was sent; each GET of that session answers the next of `polls`, the last one for ever."""
        remaining = list(polls)

        def start(request):
            body = request["body"]
            sid = body["sessionId"]

            def read(_):
                return 200, remaining.pop(0) if len(remaining) > 1 else remaining[0]

            self.registry.routes[("GET", f"{SESSIONS}/sample/{sid}")] = read
            self.registry.routes[("POST", f"{SESSIONS}/sample/{sid}/cancel")] = (200, {"sessionId": sid, "cancelRequested": True})
            return 202, {"sessionId": sid, "agent": "sample", "release": NEW, "workflowId": f"session:tenant-test:sample:{sid}", "state": "running", "created": True, **(accepted or {})}

        self.registry.routes[("POST", SESSIONS)] = start

    def run_new(self, *extra):
        return self.document(["run", "sample", "--task", "go", "--out", str(self.out), "--poll-interval", "0.01", *extra])


FINISHED = {"state": "finished", "outcome": "completed", "startedAt": "t0", "finishedAt": "t1", "progress": None, "report": "# Done\n", "reportProblem": None}
STILL = {"state": "running", "outcome": None, "progress": {"state": "RUNNING"}, "report": None}


class OldPath(DeliveryCase):
    def test_an_agent_without_the_registrys_annotations_runs_exactly_as_before(self):
        plain = {"metadata": {"name": "sample", "annotations": {"other": "x"}}}
        self.kube = base_kube = base.kube_for_run([ACCEPTED, DONE, {"report": "# r", "workspace": []}])
        base_kube.objects[("agents", None, "tenant-test")] = {"items": [plain]}
        code, doc, _ = self.run_new()
        self.assertEqual((code, doc["ok"], doc["status"]), (0, True, "COMPLETED"), doc)
        self.assertEqual([c["action"] for c in base_kube.exec_calls], ["submit", "status", "report"])
        self.assertEqual((self.registry.requests, self.signins), ([], []))
        self.assertNotIn("path", json.loads((self.out / "receipt.json").read_text()))

    def test_the_decision_reads_the_annotation_only(self):
        self.assertFalse(delivery.registry_owned(None))
        self.assertFalse(delivery.registry_owned({"metadata": {"annotations": {delivery.CURRENT_ANNOTATION: "x"}}}))
        self.assertTrue(delivery.registry_owned(owned_agent()))


class RunOnTheSessionInterface(DeliveryCase):
    def test_a_run_starts_the_session_with_the_persons_token_follows_it_and_writes_the_report(self):
        self.serve_session(STILL, FINISHED)
        code, doc, _ = self.run_new()
        self.assertEqual((code, doc["ok"], doc["status"]), (0, True, "COMPLETED"), doc)
        start = self.registry.posts()[0]
        self.assertEqual((start["path"], start["auth"]), (SESSIONS, BEARER))
        sid = start["body"]["sessionId"]
        self.assertEqual(str(uuid.UUID(sid)), sid)
        self.assertEqual(start["body"], {"agent": "sample", "task": {"request": "go"}, "release": None, "sessionId": sid, "purpose": "task"})
        self.assertEqual(len([r for r in self.registry.requests if r["method"] == "GET"]), 2)
        receipt = json.loads((self.out / "receipt.json").read_text())
        self.assertEqual((receipt["path"], receipt["sessionInterface"], receipt["sessionId"], receipt["release"]), ("session-interface", self.registry.url + SESSIONS, sid, NEW))
        self.assertEqual((self.out / "report.md").read_text(), "# Done\n")
        self.assertEqual(self.signins, ["person"])
        self.assertTrue(all("person-token" not in p.read_text() for p in self.out.iterdir()))
        self.assertNotIn("exec", [c[0] for c in self.kube.calls])

    def test_no_wait_prints_the_receipt_and_follows_nothing(self):
        self.serve_session(FINISHED)
        code, doc, _ = self.run_new("--no-wait")
        self.assertEqual((code, doc["status"], doc["receipt"]["path"]), (0, "SUBMITTED", "session-interface"))
        self.assertEqual([r["method"] for r in self.registry.requests], ["POST"])

    def test_a_wait_that_passes_first_is_not_confirmed_and_can_cancel(self):
        self.serve_session(STILL)
        code, doc, _ = self.run_new("--wait-timeout", "0.05", "--cancel-on-timeout")
        self.assertEqual((code, doc["error"]["code"]), (124, "not-confirmed"), doc)
        self.assertTrue(doc["receiptPath"].endswith("receipt.json"))
        self.assertTrue(self.registry.posts()[-1]["path"].endswith("/cancel"))

    def test_a_session_that_did_not_complete_ends_failed_and_writes_no_report(self):
        self.serve_session({**FINISHED, "outcome": "failed", "report": None})
        code, doc, _ = self.run_new()
        self.assertEqual((code, doc["status"], doc["error"]["code"]), (1, "FAILED", "failed"))
        self.assertFalse((self.out / "report.md").exists())

    def test_a_service_refusal_is_shown_with_its_message_and_code(self):
        message = "this agent acts for a person and needs that person's consent; it cannot be started here"
        for code_name in ("refused", "wrong-path", "not-found"):
            with self.subTest(code_name):
                self.registry.routes[("POST", SESSIONS)] = (409, error(code_name, message))
                out = self.tmp / f"run-{code_name}"
                code, doc, _ = self.document(["run", "sample", "--task", "go", "--out", str(out)])
                self.assertEqual((code, doc["ok"], doc["error"]["code"], doc["error"]["message"]), (2, False, code_name, message), doc)
                self.assertEqual((doc["status"], doc["reason"]), ("NOT_SUBMITTED", message))
                self.assertFalse((out / "receipt.json").exists())

    def test_a_token_the_registry_stops_accepting_asks_the_person_to_sign_in_once_more(self):
        self.serve_session(FINISHED)
        start = self.registry.routes[("POST", SESSIONS)]
        expired = [True, False]

        def first_read_is_refused(request):
            status, doc = start(request)
            read = self.registry.routes[("GET", f"{SESSIONS}/sample/{request['body']['sessionId']}")]
            self.registry.routes[("GET", f"{SESSIONS}/sample/{request['body']['sessionId']}")] = lambda r: (401, b"") if expired.pop(0) else read(r)
            return status, doc

        self.registry.routes[("POST", SESSIONS)] = first_read_is_refused
        code, doc, _ = self.run_new()
        self.assertEqual((code, self.signins), (0, ["person", "person"]), doc)

    def test_a_registry_that_does_not_answer_is_not_confirmed(self):
        self.registry.routes[("POST", SESSIONS)] = (502, b"<html>bad gateway</html>")
        code, doc, _ = self.run_new()
        self.assertEqual((code, doc["status"], doc["error"]["code"]), (2, "SUBMIT_UNCONFIRMED", "not-confirmed"))
        self.assertIn("do not repeat this command", doc["error"]["message"])

    def test_a_grant_handle_is_refused_before_any_request(self):
        self.serve_session(FINISHED)
        code, doc, _ = self.run_new("--grant-handle", "h")
        self.assertEqual((code, doc["error"]["code"]), (2, "invalid-arguments"))
        self.assertEqual((self.registry.requests, self.signins), ([], []))
        self.assertFalse(self.out.exists())

    def test_a_release_other_than_the_current_is_refused_before_any_request(self):
        code, doc, _ = self.run_new("--release", OLD)
        self.assertEqual((code, doc["error"]["code"], self.registry.requests, self.signins), (2, "refused", [], []))
        self.serve_session(FINISHED)
        code, doc, _ = self.run_new("--release", NEW)
        self.assertEqual(code, 0)
        self.assertEqual(self.registry.posts()[0]["body"]["release"], NEW)


class ReceiptCommands(DeliveryCase):
    def new_receipt(self) -> Path:
        self.serve_session(FINISHED)
        self.assertEqual(self.run_new("--no-wait")[0], 0)
        self.registry.requests.clear()
        self.signins.clear()
        return self.out / "receipt.json"

    def test_wait_status_and_cancel_call_the_session_interface(self):
        receipt = self.new_receipt()
        sid = json.loads(receipt.read_text())["sessionId"]
        session = f"{SESSIONS}/sample/{sid}"
        self.registry.routes[("GET", session)] = (200, STILL)
        code, doc, _ = self.document(["status", "--receipt", str(receipt)])
        self.assertEqual((code, doc["status"]), (0, "RUNNING"))
        self.registry.routes[("GET", session)] = (200, FINISHED)
        code, doc, _ = self.document(["wait", "--receipt", str(receipt), "--poll-interval", "0.01"])
        self.assertEqual((code, doc["status"], (self.out / "report.md").read_text()), (0, "COMPLETED", "# Done\n"))
        self.registry.routes[("POST", session + "/cancel")] = (200, {"sessionId": sid, "cancelRequested": True})
        code, doc, _ = self.document(["cancel", "--receipt", str(receipt)])
        self.assertEqual((code, doc["cancel"]["cancelRequested"]), (0, True))
        cancel = self.registry.posts()[-1]
        self.assertEqual((cancel["path"], cancel["auth"], list(cancel["body"])), (session + "/cancel", BEARER, ["reason"]))
        self.assertEqual(self.signins, ["person"] * 3)
        self.registry.routes[("POST", session + "/cancel")] = (200, {"sessionId": sid, "cancelRequested": False})
        code, doc, _ = self.document(["cancel", "--receipt", str(receipt)])
        self.assertEqual((code, doc["error"]["code"]), (1, "failed"))

    def test_a_receipt_of_the_old_path_still_goes_to_the_runner(self):
        self.kube = kube = base.kube_for_run([ACCEPTED, RUNNING, DONE, {"report": "# r", "workspace": []}])
        code, doc, _ = self.run_new("--no-wait")
        self.assertEqual(code, 0)
        receipt = self.out / "receipt.json"
        self.assertEqual(self.document(["status", "--receipt", str(receipt)])[1]["status"], "RUNNING")
        code, doc, _ = self.document(["wait", "--receipt", str(receipt), "--poll-interval", "0.01"])
        self.assertEqual((code, doc["status"]), (0, "COMPLETED"))
        self.assertEqual([c["action"] for c in kube.exec_calls], ["submit", "status", "status", "report"])
        self.assertEqual((self.registry.requests, self.signins), ([], []))


def status_document() -> dict:
    owned = {
        "agent": "sample",
        "tenant": "tenant-test",
        "authority": "registry",
        "currentRelease": OLD,
        "newestRelease": NEW,
        "phase": "refused",
        "ready": True,
        "blockers": [f"release {NEW} was refused: evaluation failed: 1 of 2 cases passed"],
        "nextActions": ["release a fixed version or ask for another evaluation"],
        "current": {"release": OLD, "revision": 1, "since": "2026-11-09T00:00:00Z", "admittedBy": None},
        "candidate": {"release": "sample-2026-11-12-cafe0001", "revision": 3, "phase": "evaluating", "reason": "waiting for evaluation", "evaluation": {"attempt": 1, "state": "pending"}},
        "lastRefused": {"release": NEW, "revision": 2, "reason": "evaluation failed: 1 of 2 cases passed", "at": "2026-11-10T00:00:00Z", "evaluation": {"verdict": "failed", "summary": "1 of 2 cases passed"}},
        "acknowledged": False,
        "pinned": 1,
        "revoked": [{"id": "2026-11-11-sample-0badf00d", "release": "sample-2026-11-11-0badf00d", "reason": "security", "at": "2026-11-11T00:00:00Z"}],
        "observation": {"state": "fresh"},
    }
    other = {"agent": "plain", "tenant": "tenant-test", "authority": "pull-request", "currentRelease": "plain-1", "newestRelease": "plain-1", "phase": None, "ready": True, "blockers": [], "nextActions": [], "observation": {"state": "fresh"}}
    return {"cluster": "kubani", "mode": "normal", "generation": 4, "agents": [owned, other], "toolServers": [], "models": []}


class StatusText(DeliveryCase):
    def test_the_view_shows_in_use_candidate_refusal_pin_revocation_and_acknowledgement(self):
        self.registry.routes[("GET", "/v1/status")] = (200, status_document())
        code, text, _ = self.run_cli(["status"])
        self.assertEqual(code, 0)
        for line in (
            f"in use: {OLD} (revision 1)",
            "candidate: sample-2026-11-12-cafe0001 (revision 3) evaluating: waiting for evaluation; evaluation attempt 1 pending",
            f"last refused: {NEW} (revision 2): evaluation failed: 1 of 2 cases passed; evaluation failed: 1 of 2 cases passed",
            "pinned: revision 1",
            "revoked: sample-2026-11-11-0badf00d (security, 2026-11-11-sample-0badf00d)",
            "cluster: has not taken the last change yet",
            "next: release a fixed version or ask for another evaluation",
        ):
            self.assertIn(line, text)
        plain = text.split("plain (tenant-test)")[1]
        self.assertNotIn("in use:", plain)

    def test_json_is_the_registrys_document_unchanged(self):
        doc = status_document()
        self.registry.routes[("GET", "/v1/status")] = (200, doc)
        code, out, _ = self.document(["status", "--json"])
        self.assertEqual({k: v for k, v in out.items() if k != "ok"}, doc)


REVISIONS = {"deployment": {"id": DEP_ID, "currentRevision": 2, "pinnedRevision": None}, "revisions": [{"number": 1, "releaseId": f"agent:sample:{OLD}"}, {"number": 2, "releaseId": f"agent:sample:{NEW}"}], "approvals": []}


class ReleaseCommands(DeliveryCase):
    CASES = (
        ("rollback", ["rollback", "sample", "--reason", "bad release"], "/rollback", {"revision": None, "reason": "bad release"}),
        ("rollback-to", ["rollback", "sample", "--to", OLD], "/rollback", {"revision": 1, "reason": "rolled back with `just agent rollback`"}),
        ("pin-release", ["pin", "sample", "--release", OLD], "/pin", {"revision": 1}),
        ("pin-current", ["pin", "sample"], "/pin", {"revision": 2}),
        ("unpin", ["unpin", "sample"], "/pin", {"revision": None}),
        ("disable", ["disable", "sample", "--reason", "incident"], "/enabled", {"enabled": False, "reason": "incident"}),
        ("enable", ["enable", "sample"], "/enabled", {"enabled": True, "reason": "enabled with `just agent enable`"}),
        ("evaluate", ["evaluate", "sample", "--reason", "flaky model"], "/revisions/2/evaluations", {"reason": "flaky model"}),
    )

    def test_each_command_sends_its_route_and_body_with_the_persons_token(self):
        self.registry.routes[("GET", DEP)] = (200, REVISIONS)
        for name, argv, suffix, body in self.CASES:
            with self.subTest(name):
                self.registry.requests.clear()
                answer = {"evaluation": {"attempt": 2, "state": "pending"}, "revision": {}} if name == "evaluate" else {"changed": True, "deployment": {}}
                self.registry.routes[("POST", DEP + suffix)] = (200, answer)
                code, doc, _ = self.document(argv)
                self.assertEqual((code, doc["ok"], doc["agent"], doc["deployment"]), (0, True, "sample", DEP_ID), doc)
                post = self.registry.posts()
                self.assertEqual([(r["path"], r["body"], r["auth"]) for r in post], [(DEP + suffix, body, BEARER)])

    def test_a_registry_refusal_is_passed_on_with_its_code(self):
        self.registry.routes[("GET", DEP)] = (200, REVISIONS)
        for name, argv, suffix, _ in self.CASES:
            with self.subTest(name):
                self.registry.routes[("POST", DEP + suffix)] = (409, error("refused", "revision 1 has not been activated"))
                code, doc, _ = self.document(argv)
                self.assertEqual((code, doc["ok"], doc["error"]["code"], doc["error"]["message"]), (2, False, "refused", "revision 1 has not been activated"))

    def test_a_release_the_registry_does_not_hold_is_not_found_and_nothing_is_posted(self):
        self.registry.routes[("GET", DEP)] = (200, REVISIONS)
        code, doc, _ = self.document(["pin", "sample", "--release", "sample-2026-01-01-00000000"])
        self.assertEqual((code, doc["error"]["code"], self.registry.posts()), (2, "not-found", []))


class Revoke(unittest.TestCase):
    RELEASE = "sample-2026-11-20-1a2b3c4d"
    ARGV = ["revoke", "sample", RELEASE, "--reason", "security", "--summary", "The release leaks query text into its report.", "--by", "al"]

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        build_tree(self.root)
        self.file = self.root / "infrastructure/registry/revocations/2026-11-20-sample-1a2b3c4d.yaml"

    def revoke(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = base.cli.main(["--root", str(self.root), *argv])
        return code, json.loads(out.getvalue())

    def test_the_file_is_accepted_by_the_renderer_and_the_feed_lists_it(self):
        code, doc = self.revoke(*self.ARGV)
        self.assertEqual((code, doc["ok"], doc["id"], doc["sessions"]), (0, True, "2026-11-20-sample-1a2b3c4d", "cancel"), doc)
        self.assertEqual(doc["files"], [str(self.file.relative_to(self.root)), str(registry_feed.FEED)])
        self.assertIn("pull request", doc["next"])
        listed = registry_feed.render(self.root)["revocations"]
        self.assertEqual([(r["id"], r["item"], r["release"], r["reason"], r["sessions"], r["revokedBy"]) for r in listed], [("2026-11-20-sample-1a2b3c4d", "sample", self.RELEASE, "security", "cancel", "al")])
        self.assertRegex(listed[0]["revokedAt"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual((self.root / registry_feed.FEED).read_bytes(), registry_feed.feed_bytes(registry_feed.render(self.root)))
        self.assertEqual(registry_feed.main(["--root", str(self.root), "render", "--check"]), 0)

    def test_quality_defaults_to_finish_and_sessions_can_be_named(self):
        argv = [*self.ARGV]
        argv[argv.index("security")] = "quality"
        self.assertEqual(self.revoke(*argv)[1]["sessions"], "finish")
        self.file.unlink()
        self.assertEqual(self.revoke(*argv, "--sessions", "cancel")[1]["sessions"], "cancel")

    def test_a_second_run_with_the_same_id_is_refused_and_changes_nothing(self):
        self.revoke(*self.ARGV)
        before = (self.file.read_bytes(), (self.root / registry_feed.FEED).read_bytes())
        code, doc = self.revoke(*self.ARGV)
        self.assertEqual((code, doc["error"]["code"]), (2, "conflict"))
        self.assertEqual(before, (self.file.read_bytes(), (self.root / registry_feed.FEED).read_bytes()))

    def test_a_bad_reason_is_refused_by_the_parser_and_a_foreign_release_by_the_command(self):
        bad = [*self.ARGV]
        bad[bad.index("security")] = "boredom"
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            base.cli.main(["--root", str(self.root), *bad])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], "invalid-arguments")
        code, doc = self.revoke("revoke", "sample", "other-2026-11-20-1a2b3c4d", *self.ARGV[3:])
        self.assertEqual((code, doc["error"]["code"]), (2, "invalid-arguments"))
        self.assertFalse(self.file.exists())


if __name__ == "__main__":
    unittest.main()
