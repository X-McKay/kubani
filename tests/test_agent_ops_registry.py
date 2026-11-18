"""Operator commands for agents the registry owns: a fake registry on loopback, a fake cluster and fake tokens; no real credential, cluster or network."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import jwt
import yaml

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
from agent_ops import approve, delegation, layout, live, registry_client, run, stage  # noqa: E402

import test_agent_ops as base  # noqa: E402
from test_agent_ops_consent import Browser, FakeIdp  # noqa: E402

cli = base.cli
PRUNE = "kustomize.toolkit.fluxcd.io/prune"
DEP = "/v1/deployments/agent:kubani:tenant-test:sample"
DEP_ID = "agent:kubani:tenant-test:sample"
LIST = layout.AGENTS_LIST
OPERATOR = {"aud": ["agent-registry"], "realm_access": {"roles": ["registry-operator"]}}


def error(code: str, message: str = "the registry says no", retryable: bool = False) -> dict:
    return {"error": {"code": code, "message": message, "retryable": retryable}}


class FakeRegistry:
    """A registry on 127.0.0.1 that records what it is sent. `routes` maps (method, unquoted path) to (status, document) or a callable."""

    def __init__(self):
        self.requests: list[dict] = []
        self.routes: dict = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self, method: str):
                parsed = urllib.parse.urlsplit(self.path)
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = None
                request = {"method": method, "raw_path": parsed.path, "path": urllib.parse.unquote(parsed.path), "query": urllib.parse.parse_qs(parsed.query), "auth": self.headers.get("Authorization"), "body": body, "raw": raw}
                outer.requests.append(request)
                answer = outer.routes.get((method, request["path"]), (404, error("not-found", "no such route")))
                status, doc = answer(request) if callable(answer) else answer
                payload = doc if isinstance(doc, bytes) else json.dumps(doc).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                self.handle_any("GET")

            def do_POST(self):
                self.handle_any("POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def posts(self) -> list[dict]:
        return [r for r in self.requests if r["method"] == "POST"]


class FakeKube:
    """Reads only: the live Agent and AgentReleases of one tenant."""

    def __init__(self, agent: dict | None = None, releases: list[dict] | None = None):
        self.agent, self.releases, self.calls = agent, releases or [], []

    def get(self, kind, name, namespace, *, selector=None):
        self.calls.append((kind, name, namespace))
        if kind == "agents":
            return self.agent
        return {"items": self.releases}


def live_object(name: str, agent: str | None = None, annotated: bool = True) -> dict:
    obj = {"metadata": {"name": name, "namespace": "tenant-test", "annotations": {PRUNE: "disabled"} if annotated else {}}, "spec": {}}
    if agent:
        obj["spec"]["agent"] = agent
    return obj


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def make_tree(tmp: Path, *, listed: bool, annotated: bool = True, release_text: str | None = base.RELEASE_TEXT) -> Path:
    root = base.make_root(tmp, release_text=release_text)
    if not listed:
        (root / LIST).write_text("apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - tenant-test/other/\n", encoding="utf-8")
    d = layout.find_agent(root, "sample")
    resources = layout.kustomization_resources(d)
    head = "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n" + (f"commonAnnotations:\n  {PRUNE}: disabled\n" if annotated else "")
    d.kustomization.write_text(head + "resources:\n" + "".join(f"  - {r}\n" for r in resources), encoding="utf-8")
    base.write(root / layout.AGENT_CRD, (base.ROOT / layout.AGENT_CRD).read_text(encoding="utf-8"))
    return root


def release_variant(name: str = "sample-2026-11-10-deadbeef", approved: bool = False) -> dict:
    doc = copy.deepcopy(base.RELEASE_DOC)
    doc["metadata"]["name"] = name
    if approved:
        doc["spec"]["approval"] = {"approved": True, "approvedBy": "al@example.invalid", "approvedAt": "2026-11-10T00:00:00Z"}
    return doc


class RegistryCase(unittest.TestCase):
    def setUp(self):
        self.registry = FakeRegistry()
        self.addCleanup(self.registry.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.signins: list[str] = []
        self.refresh_token: str | None = None  # what the fake sign-in hands out beside the access token
        self.kube = FakeKube()

        def person(*args, **kwargs):
            self.signins.append("person")
            return {"access": "person-token", "refresh": self.refresh_token}

        env = {"KUBANI_REGISTRY_URL": self.registry.url, "KUBANI_REGISTRY_CLUSTER": "kubani", "KUBANI_REGISTRY_READER_SECRET_FILE": str(self.tmp / "no-such-secret")}
        for patcher in (
            patch.dict(os.environ, env),
            patch.object(registry_client, "person_tokens", person),
            patch.object(registry_client, "reader_token", lambda *a, **k: "reader-token"),
            patch.object(live, "Kube", lambda *a, **k: self.kube),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, argv, *, root: Path | None = None, stdin: str = ""):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--root", str(root or self.root), "--repo", base.REPO, *argv])
        return code, out.getvalue(), err.getvalue()

    def document(self, argv, **kwargs):
        code, out, err = self.run_cli(argv, **kwargs)
        return code, json.loads(out), err

    def fake_download(self, **overrides):
        def download(repo, tag, dest):
            base.assets(dest, **overrides)

        return patch.object(stage, "download", download)


class StageTests(RegistryCase):
    def test_listed_agent_takes_the_pull_request_path_and_the_registry_hears_nothing(self):
        self.root = make_tree(self.tmp, listed=True, release_text=None)
        with self.fake_download():
            code, doc, _ = self.document(["stage", "sample", base.TAG])
        self.assertEqual(code, 0)
        self.assertEqual(doc["file"], "infrastructure/gitops/apps/agents/tenant-test/sample/agentrelease-v0.2.0.yaml")
        self.assertNotIn("path", doc)
        self.assertEqual((self.registry.requests, self.signins), ([], []))

    def test_listed_agent_approve_release_takes_the_pull_request_path(self):
        self.root = make_tree(self.tmp, listed=True)
        self.kube = base.FakeKube({("agentrelease", base.RELEASE, "tenant-test"): base.live_release()})
        code, doc, _ = self.document(["approve", base.RELEASE, "--by", "al@example.invalid"])
        self.assertEqual(code, 0)
        self.assertIn("approved: true", (self.root / doc["file"]).read_text())
        self.assertEqual((self.registry.requests, self.signins), ([], []))

    def test_unlisted_agent_records_the_release_and_writes_no_file(self):
        self.root = make_tree(self.tmp, listed=False, release_text=None)
        self.registry.routes[("POST", DEP + "/releases")] = (200, {"release": {}, "revision": {"number": 3}, "created": True})
        before = snapshot(self.root)
        with self.fake_download():
            code, doc, _ = self.document(["stage", "sample", base.TAG])
        self.assertEqual(code, 0, doc)
        self.assertEqual(snapshot(self.root), before)
        posts = self.registry.posts()
        self.assertEqual(len(posts), 1)
        self.assertIn("%3A", posts[0]["raw_path"])
        self.assertEqual(posts[0]["auth"], "Bearer person-token")
        self.assertEqual(set(posts[0]["body"]), {"agent", "agentRelease", "lineage"})
        self.assertEqual(posts[0]["body"]["agent"], yaml.safe_load(base.AGENT_BODY))
        self.assertEqual(posts[0]["body"]["agentRelease"], base.RELEASE_DOC)
        self.assertEqual(set(posts[0]["body"]["lineage"]), {"repository", "tag", "checksums"})
        self.assertEqual((doc["path"], doc["revision"], doc["created"], doc["release"]), ("registry", 3, True, base.RELEASE))
        self.assertNotIn("file", doc)
        self.assertIn("just agent approve sample", doc["next"])

    def test_unlisted_agent_does_not_compare_the_published_agent_with_the_committed_one(self):
        self.root = make_tree(self.tmp, listed=False, release_text=None)
        self.registry.routes[("POST", DEP + "/releases")] = (200, {"revision": {"number": 1}, "created": False})
        with self.fake_download(**{"agent.yaml": base.AGENT_BODY.replace("1Gi", "9Gi")}):
            code, doc, _ = self.document(["stage", "sample", base.TAG])
        self.assertEqual((code, doc["created"]), (0, False))
        self.assertEqual(self.registry.posts()[0]["body"]["agent"]["spec"]["runtime"]["memory"], "9Gi")

    def test_a_bad_checksum_fails_before_any_sign_in_and_any_request(self):
        self.root = make_tree(self.tmp, listed=False, release_text=None)
        with self.fake_download(**{"SHA256SUMS": "0" * 64 + "  agent.yaml\n"}):
            code, doc, _ = self.document(["stage", "sample", base.TAG])
        self.assertEqual((code, doc["error"]["code"]), (2, "validation-failed"))
        self.assertEqual((self.registry.requests, self.signins), ([], []))

    def test_a_registry_refusal_is_passed_on(self):
        self.root = make_tree(self.tmp, listed=False, release_text=None)
        self.registry.routes[("POST", DEP + "/releases")] = (409, error("wrong-path", "the registry does not own sample yet"))
        with self.fake_download():
            code, doc, _ = self.document(["stage", "sample", base.TAG])
        self.assertEqual((code, doc["error"]["code"], doc["error"]["message"]), (2, "wrong-path", "the registry does not own sample yet"))


PREVIEW = {
    "deployment": DEP_ID,
    "revision": 2,
    "release": base.RELEASE,
    "authorityDigest": "sha256:" + "aa" * 32,
    "baseAuthorityDigest": "sha256:" + "bb" * 32,
    "policyRevision": "policy-7",
    "changes": ["adds the tool backend db-write"],
    "gateFailures": [],
    "observation": {"state": "fresh", "ageSeconds": 3},
    "approved": False,
    "approvable": True,
}


class ApproveTests(RegistryCase):
    def setUp(self):
        super().setUp()
        self.root = make_tree(self.tmp, listed=False)
        self.registry.routes[("GET", DEP)] = (200, {"deployment": {}, "revisions": [{"number": 1}, {"number": 2}], "approvals": []})
        self.set_preview({})
        self.registry.routes[("POST", DEP + "/approvals")] = (200, {"approval": {"id": "x", "approvedBy": "al@example.invalid"}, "revision": {"number": 2}})

    def set_preview(self, changes: dict) -> None:
        self.registry.routes[("GET", DEP + "/revisions/2/approval")] = (200, {**PREVIEW, **changes})

    def test_confirmed_sends_the_four_binding_fields_and_the_ticket(self):
        before = snapshot(self.root)
        code, doc, err = self.document(["approve", "sample", "--ticket", "TICKET-1"], stdin="yes\n")
        self.assertEqual(code, 0, doc)
        body = self.registry.posts()[0]["body"]
        self.assertEqual({k: body[k] for k in ("revision", "authorityDigest", "baseAuthorityDigest", "policyRevision", "ticket")}, {"revision": 2, "authorityDigest": PREVIEW["authorityDigest"], "baseAuthorityDigest": PREVIEW["baseAuthorityDigest"], "policyRevision": "policy-7", "ticket": "TICKET-1"})
        self.assertRegex(body["approvalId"], r"^[0-9a-f]{32}$")
        self.assertIn("adds the tool backend db-write", err)
        self.assertIn("policy-7", err)
        self.assertEqual((doc["path"], doc["changed"], doc["approvedBy"], doc["revision"], doc["release"], doc["changes"]), ("registry", True, "al@example.invalid", 2, base.RELEASE, PREVIEW["changes"]))
        self.assertEqual((doc["agent"], doc["deployment"], doc["approvalId"]), ("sample", DEP_ID, "x"))
        self.assertEqual(snapshot(self.root), before)

    def test_a_narrow_authority_says_so(self):
        self.set_preview({"changes": []})
        code, _, err = self.run_cli(["approve", "sample"], stdin="yes\n")
        self.assertEqual(code, 0)
        self.assertIn("no wider than the current release", err)

    def test_declined_sends_nothing(self):
        for answer in ("no\n", "y\n", ""):
            with self.subTest(answer=answer):
                code, doc, _ = self.document(["approve", "sample"], stdin=answer)
                self.assertEqual((code, doc["error"]["code"]), (2, "not-confirmed"))
        self.assertEqual(self.registry.posts(), [])

    def test_not_approvable_is_refused_with_the_gate_failures(self):
        self.set_preview({"approvable": False, "gateFailures": ["the signature is not verified"], "observation": {"state": "old"}})
        code, doc, _ = self.document(["approve", "sample"], stdin="yes\n")
        self.assertEqual((code, doc["error"]["code"]), (2, "refused"))
        self.assertIn("the signature is not verified", doc["error"]["message"])
        self.assertIn("old", doc["error"]["message"])
        self.assertEqual(self.registry.posts(), [])

    def test_already_approved_is_not_a_change(self):
        self.set_preview({"approved": True, "approvable": False})
        code, doc, _ = self.document(["approve", "sample"])
        self.assertEqual((code, doc["changed"], doc["path"]), (0, False, "registry"))
        self.assertEqual(self.registry.posts(), [])

    def test_no_revision_is_refused(self):
        self.registry.routes[("GET", DEP)] = (200, {"deployment": {}, "revisions": [], "approvals": []})
        code, doc, _ = self.document(["approve", "sample"])
        self.assertEqual((code, doc["error"]["code"]), (2, "refused"))

    def test_registry_refusals_are_passed_on_unchanged(self):
        for code_name in ("stale-approval", "replayed-approval", "conflict", "in-recovery"):
            with self.subTest(code_name):
                self.registry.routes[("POST", DEP + "/approvals")] = (409, error(code_name, f"the registry said {code_name}", code_name == "in-recovery"))
                code, doc, _ = self.document(["approve", "sample"], stdin="yes\n")
                self.assertEqual((code, doc["error"]["code"], doc["error"]["message"], doc["error"]["retryable"]), (2, code_name, f"the registry said {code_name}", code_name == "in-recovery"))

    def test_by_is_refused_before_any_sign_in(self):
        code, doc, _ = self.document(["approve", "sample", "--by", "someone@example.invalid"], stdin="yes\n")
        self.assertEqual((code, doc["error"]["code"]), (2, "invalid-arguments"))
        self.assertEqual((self.registry.requests, self.signins), ([], []))

    def test_a_release_of_an_unlisted_agent_is_the_wrong_path(self):
        before = snapshot(self.root)
        code, doc, _ = self.document(["approve", base.RELEASE])
        self.assertEqual((code, doc["error"]["code"]), (2, "wrong-path"))
        self.assertIn("just agent approve sample", doc["error"]["message"])
        self.assertEqual((snapshot(self.root), self.registry.requests, self.signins), (before, [], []))

    def test_an_agent_on_the_pull_request_path_is_the_wrong_path(self):
        root = make_tree(self.tmp / "listed", listed=True)
        code, doc, _ = self.document(["approve", "sample"], root=root)
        self.assertEqual((code, doc["error"]["code"]), (2, "wrong-path"))
        self.assertIn("just agent approve <release>", doc["error"]["message"])
        self.assertEqual((self.registry.requests, self.signins), ([], []))


STATUS = {
    "cluster": "kubani",
    "mode": "normal",
    "generation": 41,
    "observationMaxAgeSeconds": 120,
    "agents": [
        {
            "deployment": DEP_ID,
            "agent": "sample",
            "tenant": "tenant-test",
            "namespace": "tenant-test",
            "authority": "registry",
            "enabled": True,
            "pinnedRevision": None,
            "currentRevision": 1,
            "currentRelease": "sample-2026-11-09-abcdef12",
            "newestRevision": 2,
            "newestRelease": "sample-2026-11-10-deadbeef",
            "phase": "awaiting-approval",
            "ready": True,
            "blockers": ["revision 2 waits for an approval"],
            "nextActions": ["just agent approve sample"],
            "observation": {"state": "fresh", "observedAt": "2026-11-17T10:00:00Z", "ageSeconds": 5},
        }
    ],
    "toolServers": [
        {
            "deployment": "tool-server:kubani:tools:db-write",
            "name": "db-write",
            "namespace": "tools",
            "registered": False,
            "backend": None,
            "declaredImage": "registry.almckay.io/tools/db-write:1",
            "pinnedByDigest": False,
            "observedImages": [],
            "readyReplicas": None,
            "observation": {"state": "old", "observedAt": "2026-11-17T08:00:00Z", "ageSeconds": 7300},
            "dependants": ["sample"],
        }
    ],
    "models": [
        {
            "deployment": "model:kubani:vllm:fast",
            "name": "fast",
            "namespace": "vllm",
            "aliases": ["fast-model"],
            "backend": "fast",
            "declaredServedName": "fast-served",
            "observedServedName": "fast-served",
            "observedImage": None,
            "observation": {"state": "fresh", "ageSeconds": 1},
            "dependants": [],
        }
    ],
}


class StatusTests(RegistryCase):
    def setUp(self):
        super().setUp()
        self.root = make_tree(self.tmp, listed=False)
        self.registry.routes[("GET", "/v1/status")] = (200, STATUS)

    def test_text_view(self):
        code, out, _ = self.run_cli(["status"])
        self.assertEqual(code, 0)
        request = self.registry.requests[0]
        self.assertEqual((request["query"], request["auth"]), ({"cluster": ["kubani"]}, "Bearer reader-token"))
        for text in ("Agents", "Tool servers", "Models", "sample", "registry", "sample-2026-11-09-abcdef12", "sample-2026-11-10-deadbeef", "awaiting-approval", "blocker: revision 2 waits for an approval", "next: just agent approve sample", "db-write", "unregistered", "not pinned", "unknown (last seen 2h)", "fast-model"):
            self.assertIn(text, out)
        self.assertEqual(self.signins, [])

    def test_json_view_is_the_status_with_ok(self):
        code, doc, _ = self.document(["status", "--json"])
        self.assertEqual((code, doc), (0, {**STATUS, "ok": True}))

    def test_registry_down_is_registry_unreachable(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with patch.dict(os.environ, {"KUBANI_REGISTRY_URL": f"http://127.0.0.1:{port}"}):
            code, doc, _ = self.document(["status", "--json"])
        self.assertEqual((code, doc["ok"], doc["error"]["code"], doc["error"]["retryable"]), (2, False, "registry-unreachable", True))

    def test_receipt_still_takes_the_run_path(self):
        with patch.object(run, "resume", return_value=(0, {"status": "COMPLETED", "confirmed": True})) as resume:
            code, doc, _ = self.document(["status", "--receipt", "r.json"])
        self.assertEqual((code, doc["status"]), (0, "COMPLETED"))
        resume.assert_called_once()
        self.assertEqual(self.registry.requests, [])

    def test_wait_and_cancel_still_need_a_receipt(self):
        for argv in (["wait"], ["cancel"]):
            with self.subTest(argv=argv):
                out = io.StringIO()
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
                    cli.main(["--root", str(self.root), *argv])
                self.assertEqual((caught.exception.code, json.loads(out.getvalue())["error"]["code"]), (2, "invalid-arguments"))
        self.assertEqual(self.registry.requests, [])


class ReaderTokenTests(RegistryCase):
    def settings(self, path: Path):
        return registry_client.Settings(self.registry.url, "kubani", path)

    def secret(self, text: str, mode: int) -> Path:
        path = self.tmp / "reader.secret"
        path.write_text(text, encoding="utf-8")
        path.chmod(mode)
        return path

    def test_missing_loose_and_empty_files_are_not_signed_in_and_name_the_path(self):
        cases = {"missing": self.tmp / "absent", "group readable": self.secret("a-secret-value\n", 0o640), "empty": None}
        cases["empty"] = self.tmp / "empty.secret"
        cases["empty"].write_text("\n")
        cases["empty"].chmod(0o600)
        for label, path in cases.items():
            with self.subTest(label), self.assertRaises(registry_client.RegistryError) as caught:
                self.original_reader_token(self.settings(path), issuer=self.registry.url + "/realms/agents")
            self.assertEqual(caught.exception.code, "not-signed-in")
            self.assertIn(str(path), str(caught.exception))
            self.assertNotIn("a-secret-value", str(caught.exception))
        self.assertEqual(self.registry.requests, [])

    def test_a_good_file_gives_a_token_and_the_secret_is_shown_nowhere(self):
        path = self.secret("reader-secret-value\n", 0o600)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.registry.routes[("POST", "/realms/agents/protocol/openid-connect/token")] = (200, {"access_token": "reader-access", "token_type": "Bearer"})
        self.registry.routes[("GET", "/v1/status")] = (200, STATUS)
        self.root = make_tree(self.tmp / "tree", listed=False)
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(registry_client, "reader_token", self.original_reader_token),
            patch.dict(os.environ, {"KUBANI_REGISTRY_READER_SECRET_FILE": str(path)}),
            patch.object(delegation, "ISSUER", self.registry.url + "/realms/agents"),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(["--root", str(self.root), "status", "--json"])
        self.assertEqual(code, 0)
        form = urllib.parse.parse_qs(self.registry.requests[0]["raw"])
        self.assertEqual((form["grant_type"], form["client_id"], form["client_secret"]), (["client_credentials"], ["registry-reader"], ["reader-secret-value"]))
        self.assertEqual(self.registry.requests[1]["auth"], "Bearer reader-access")
        self.assertNotIn("reader-secret-value", out.getvalue() + err.getvalue())
        self.assertNotIn("reader-access", out.getvalue() + err.getvalue())

    original_reader_token = staticmethod(registry_client.reader_token)


class PersonTokenTests(unittest.TestCase):
    def setUp(self):
        self.idp = FakeIdp()
        self.addCleanup(self.idp.close)
        self.said: list[str] = []

    def sign_in(self, mutate=None, **kwargs):
        browser = Browser(self.idp)
        self.addCleanup(browser.close)
        self.browser = browser
        self.idp.mutate = mutate or (lambda t: t["access"].update(OPERATOR))
        with patch.object(delegation, "interactive", lambda: True):
            return registry_client.person_token(issuer=self.idp.issuer, browser=True, open_url=browser, say=self.said.append, **kwargs)

    def test_no_person_at_the_terminal_is_not_signed_in_before_anything_else(self):
        with patch.object(delegation, "interactive", lambda: False), self.assertRaises(registry_client.RegistryError) as caught:
            registry_client.person_token(issuer=self.idp.issuer, say=self.said.append)
        self.assertEqual(caught.exception.code, "not-signed-in")
        self.assertIn("signed in at a terminal", str(caught.exception))
        self.assertEqual((self.idp.calls, self.said), ([], []))

    def test_a_good_sign_in_returns_the_access_token_and_asks_for_the_registry_scope_only(self):
        token = self.sign_in()
        self.assertEqual(jwt.decode(token, options={"verify_signature": False})["realm_access"]["roles"], ["registry-operator"])
        self.assertEqual(self.browser.params["scope"], "openid agent-registry")
        self.assertNotIn("prompt", self.browser.params)
        self.assertEqual(self.browser.params["code_challenge_method"], "S256")

    def test_a_token_without_the_audience_or_the_role_is_refused(self):
        cases = {
            "audience": (lambda t: t["access"].update(aud=["agent-policy-service"], realm_access={"roles": ["registry-operator"]}), "agent-registry"),
            "role": (lambda t: t["access"].update(aud=["agent-registry"], realm_access={"roles": ["registry-reader"]}), "registry-operator"),
            "no roles at all": (lambda t: t["access"].update(aud="agent-registry"), "registry-operator"),
        }
        for label, (mutate, named) in cases.items():
            with self.subTest(label), self.assertRaises(registry_client.RegistryError) as caught:
                self.sign_in(mutate)
            self.assertEqual(caught.exception.code, "refused")
            self.assertIn(named, str(caught.exception))
            self.assertIn("operator", str(caught.exception))

    def test_a_sign_in_nobody_completes_times_out(self):
        with patch.object(delegation, "interactive", lambda: True), self.assertRaises(registry_client.RegistryError) as caught:
            registry_client.person_token(issuer=self.idp.issuer, timeout=0.05, say=self.said.append)
        self.assertEqual(caught.exception.code, "timeout")


class AuthorityTakeTests(RegistryCase):
    def setUp(self):
        super().setUp()
        self.registry.routes[("POST", DEP + "/authority/take")] = (200, {"deployment": {}, "changed": True})
        self.kube = FakeKube(live_object("sample"), [live_object(base.RELEASE, "sample"), live_object("other-2026-11-09-00000000", "other", annotated=False)])

    def take(self, root: Path):
        self.root = root
        return self.document(["authority", "take", "sample"])

    def test_the_annotation_must_be_in_git_first(self):
        root = make_tree(self.tmp, listed=True, annotated=False)
        before = snapshot(root)
        code, doc, _ = self.take(root)
        self.assertEqual((code, doc["error"]["code"]), (2, "refused"))
        self.assertIn(PRUNE, doc["error"]["message"])
        self.assertEqual((snapshot(root), self.registry.requests, self.signins, self.kube.calls), (before, [], [], []))

    def test_a_live_object_without_the_annotation_is_refused_by_name(self):
        for label, kube in (
            ("release", FakeKube(live_object("sample"), [live_object(base.RELEASE, "sample", annotated=False)])),
            ("agent", FakeKube(live_object("sample", annotated=False), [])),
        ):
            with self.subTest(label):
                self.kube = kube
                root = make_tree(self.tmp / label, listed=True)
                before = snapshot(root)
                code, doc, _ = self.take(root)
                self.assertEqual((code, doc["error"]["code"]), (2, "refused"))
                self.assertIn(base.RELEASE if label == "release" else "Agent sample", doc["error"]["message"])
                self.assertNotIn("other-2026", doc["error"]["message"])
                self.assertEqual((snapshot(root), self.registry.requests, self.signins), (before, [], []))

    def test_an_unreadable_cluster_is_unavailable_and_writes_nothing(self):
        class Down:
            def get(self, *args, **kwargs):
                raise live.LiveError("kubectl get agents failed")

        self.kube = Down()
        root = make_tree(self.tmp, listed=True)
        before = snapshot(root)
        code, doc, _ = self.take(root)
        self.assertEqual((code, doc["error"]["code"]), (2, "unavailable"))
        self.assertEqual((snapshot(root), self.registry.requests), (before, []))

    def test_annotated_and_listed_removes_exactly_one_line_after_the_registry_accepted(self):
        root = make_tree(self.tmp, listed=True)
        before = (root / LIST).read_text().split("\n")
        code, doc, _ = self.take(root)
        self.assertEqual(code, 0, doc)
        after = (root / LIST).read_text().split("\n")
        self.assertEqual([line for line in before if line not in after], ["  - tenant-test/sample/"])
        self.assertEqual(len(before) - len(after), 1)
        self.assertEqual((doc["authority"], doc["changed"], doc["files"], doc["deployment"]), ("registry", True, [str(LIST)], DEP_ID))
        self.assertIn("pull request", doc["next"])
        self.assertEqual(len(self.registry.posts()), 1)
        self.assertEqual(self.registry.posts()[0]["auth"], "Bearer person-token")

    def test_a_registry_conflict_changes_no_file(self):
        self.registry.routes[("POST", DEP + "/authority/take")] = (409, error("conflict", "the agent is in recovery"))
        root = make_tree(self.tmp, listed=True)
        before = snapshot(root)
        code, doc, _ = self.take(root)
        self.assertEqual((code, doc["error"]["code"]), (2, "conflict"))
        self.assertEqual(snapshot(root), before)

    def test_already_unlisted_changes_no_file_and_reads_no_cluster(self):
        self.registry.routes[("POST", DEP + "/authority/take")] = (200, {"deployment": {}, "changed": False})
        root = make_tree(self.tmp, listed=False)
        before = snapshot(root)
        code, doc, _ = self.take(root)
        self.assertEqual(code, 0, doc)
        self.assertEqual((snapshot(root), doc["files"], doc["changed"], self.kube.calls), (before, [], False, []))
        self.assertIn("just agent status", doc["next"])


class AuthorityReturnTests(RegistryCase):
    def setUp(self):
        super().setUp()
        self.root = make_tree(self.tmp, listed=False)
        self.d = layout.find_agent(self.root, "sample")
        # What the cluster and the registry hold for agent.yaml: the same, with the Agent definition's defaults filled in.
        self.committed_agent = yaml.safe_load(base.AGENT_BODY)
        self.committed_agent["spec"]["enabled"] = True
        self.committed_agent["spec"]["runtime"] |= {"runtimeClass": "kata-qemu-runtime-rs", "maxBoundaries": 64}
        self.answer(releases=[base.RELEASE_DOC])

    def answer(self, *, releases, agent="same", changed=True):
        doc = {"deployment": {}, "changed": changed, "agent": copy.deepcopy(self.committed_agent) if agent == "same" else agent, "agentReleases": releases}
        self.registry.routes[("POST", DEP + "/authority/return")] = (200, doc)

    def give_back(self):
        return self.document(["authority", "return", "sample"])

    def listed(self) -> bool:
        return layout.is_listed(self.root, self.d)

    def test_a_release_recorded_meanwhile_is_written_listed_and_the_directory_returns(self):
        newer = release_variant()
        self.answer(releases=[base.RELEASE_DOC, newer])
        before = snapshot(self.root)
        code, doc, _ = self.give_back()
        self.assertEqual(code, 0, doc)
        written = self.d.path / "agentrelease-2026-11-10-deadbeef.yaml"
        text = written.read_text()
        self.assertEqual(yaml.safe_load(text), newer)
        self.assertEqual(text.count("pragma: allowlist secret"), 5)
        self.assertTrue(text.startswith("# yamllint disable rule:line-length\n# Written by `just agent authority return`"))
        self.assertIn("agentrelease-2026-11-10-deadbeef.yaml", layout.kustomization_resources(self.d))
        self.assertTrue(self.listed())
        self.assertEqual((doc["authority"], doc["agentInGit"], doc["listed"], doc["changed"], doc["deployment"]), ("pull-request", "same", True, True, DEP_ID))
        prefix = "infrastructure/gitops/apps/agents/"
        self.assertEqual(sorted(doc["files"]), sorted([prefix + "tenant-test/sample/agentrelease-2026-11-10-deadbeef.yaml", prefix + "tenant-test/sample/kustomization.yaml", str(LIST)]))
        changed = {k for k in snapshot(self.root) if before.get(k) != snapshot(self.root)[k]}
        self.assertEqual(changed, set(doc["files"]))
        self.assertEqual(snapshot(self.root)[str(self.d.agent_file.relative_to(self.root))], before[str(self.d.agent_file.relative_to(self.root))])

    def test_a_release_approved_meanwhile_is_rewritten(self):
        approved = release_variant(base.RELEASE, approved=True)
        self.answer(releases=[approved])
        code, doc, _ = self.give_back()
        self.assertEqual(code, 0, doc)
        file = self.d.path / "agentrelease.yaml"
        self.assertEqual(yaml.safe_load(file.read_text()), approved)
        self.assertEqual(file.read_text().count("pragma: allowlist secret"), 5)
        self.assertIn(str(file.relative_to(self.root)), doc["files"])
        self.assertEqual(layout.kustomization_resources(self.d), ["agent.yaml", "agentrelease.yaml"])

    def test_an_agent_that_differs_is_not_written_and_the_directory_stays_unlisted(self):
        changed = copy.deepcopy(self.committed_agent)
        changed["spec"]["description"] = "Changed while the registry owned it"
        self.answer(releases=[base.RELEASE_DOC, release_variant()], agent=changed)
        agent_before = self.d.agent_file.read_bytes()
        code, doc, _ = self.give_back()
        self.assertEqual(code, 0, doc)
        self.assertEqual((self.d.agent_file.read_bytes(), self.listed(), doc["agentInGit"], doc["listed"]), (agent_before, False, "differs", False))
        self.assertEqual(doc["agentDiffers"], ["spec.description"])
        self.assertIn("just agent sync sample --source <checkout>", doc["next"])
        self.assertIn("just agent authority return sample", doc["next"])
        self.assertTrue((self.d.path / "agentrelease-2026-11-10-deadbeef.yaml").is_file())

    def test_the_agent_without_the_defaults_the_cluster_fills_in_is_not_the_same(self):
        self.answer(releases=[base.RELEASE_DOC], agent=yaml.safe_load(base.AGENT_BODY))
        code, doc, _ = self.give_back()
        self.assertEqual((code, doc["agentInGit"], doc["agentDiffers"], doc["listed"]), (0, "differs", ["spec.enabled", "spec.runtime"], False))

    def test_an_agent_the_registry_holds_disabled_stays_unlisted_and_the_message_says_why(self):
        disabled = copy.deepcopy(self.committed_agent)
        disabled["spec"]["enabled"] = False
        self.answer(releases=[base.RELEASE_DOC], agent=disabled)
        before = snapshot(self.root)
        code, doc, _ = self.give_back()
        self.assertEqual((code, doc["agentInGit"], doc["agentDiffers"], doc["listed"], doc["files"]), (0, "differs", ["spec.enabled"], False, []))
        self.assertIn("The registry holds `enabled: false`", doc["next"])
        self.assertEqual(snapshot(self.root), before)

    def test_the_committed_db_admin_agent_is_filled_from_the_committed_definition(self):
        d = layout.find_agent(base.ROOT, "db-admin")
        applied, raw = layout.applied_agent(base.ROOT, d), layout.committed_agent(d)["spec"]
        self.assertEqual({k: v for k, v in applied.items() if k != "spec"}, {"apiVersion": "agentplatform.io/v1alpha1", "kind": "Agent", "metadata": {"name": "db-admin", "namespace": "tenant-test"}})
        self.assertEqual(applied["spec"]["enabled"], raw.get("enabled", True))
        self.assertEqual(applied["spec"]["runtime"], {"runtimeClass": "kata-qemu-runtime-rs", "maxBoundaries": 64, "cpu": "1", "memory": "2Gi", "ttlSeconds": 1800} | raw["runtime"])
        self.assertEqual([m["delegation"] for m in applied["spec"]["capabilities"]["mcp"]], [m.get("delegation", "inherit") for m in raw["capabilities"]["mcp"]])

    def test_running_it_twice_changes_nothing_the_second_time(self):
        self.answer(releases=[base.RELEASE_DOC, release_variant(), release_variant("sample-2026-11-11-cafecafe", approved=True)])
        self.assertEqual(self.give_back()[0], 0)
        after_first = snapshot(self.root)
        self.answer(releases=[base.RELEASE_DOC, release_variant(), release_variant("sample-2026-11-11-cafecafe", approved=True)], changed=False)
        code, doc, _ = self.give_back()
        self.assertEqual((code, doc["files"], doc["changed"], doc["listed"]), (0, [], False, True))
        self.assertEqual(snapshot(self.root), after_first)

    def test_a_registry_refusal_leaves_the_tree_untouched(self):
        self.registry.routes[("POST", DEP + "/authority/return")] = (409, error("in-recovery", "the registry is in recovery", True))
        before = snapshot(self.root)
        code, doc, _ = self.give_back()
        self.assertEqual((code, doc["error"]["code"], doc["error"]["retryable"]), (2, "in-recovery", True))
        self.assertEqual(snapshot(self.root), before)

    def test_a_kustomization_that_cannot_take_a_new_entry_is_refused_before_any_write(self):
        self.d.kustomization.write_text(self.d.kustomization.read_text() + "patches: []\n")
        self.answer(releases=[base.RELEASE_DOC, release_variant()])
        before = snapshot(self.root)
        code, doc, _ = self.give_back()
        self.assertEqual((code, doc["error"]["code"]), (2, "validation-failed"))
        self.assertEqual(snapshot(self.root), before)


class ClientMappingTests(RegistryCase):
    def call(self, answer):
        self.registry.routes[("GET", "/v1/anything")] = answer
        cfg = registry_client.Settings(self.registry.url, "kubani", self.tmp / "unused")
        with self.assertRaises(registry_client.RegistryError) as caught:
            registry_client.Client(cfg, "tok-value").get("/v1/anything")
        return caught.exception

    def test_a_401_without_a_body_is_not_signed_in(self):
        exc = self.call((401, b""))
        self.assertEqual(exc.code, "not-signed-in")

    def test_a_registry_error_body_is_passed_on(self):
        exc = self.call((503, error("unavailable", "the store is busy", True)))
        self.assertEqual((exc.code, str(exc)), ("unavailable", "the store is busy"))
        exc = self.call((400, error("a-new-code", "x" * 900)))
        self.assertEqual((exc.code, len(str(exc))), ("failed", 500))

    def test_anything_else_is_registry_unreachable_and_shows_no_body(self):
        for label, answer in {"html 500": (500, b"<html>SECRETBODY</html>"), "non-json 200": (200, b"SECRETBODY"), "json but not an object": (200, b"[1]"), "malformed error": (503, {"error": "SECRETBODY"})}.items():
            with self.subTest(label):
                exc = self.call(answer)
                self.assertEqual(exc.code, "registry-unreachable")
                self.assertNotIn("SECRETBODY", str(exc))
                self.assertNotIn("tok-value", str(exc))

    def test_a_refused_connection_is_registry_unreachable(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        cfg = registry_client.Settings(f"http://127.0.0.1:{port}", "kubani", self.tmp / "unused")
        with self.assertRaises(registry_client.RegistryError) as caught:
            registry_client.Client(cfg, "tok-value").get("/v1/status")
        self.assertEqual(caught.exception.code, "registry-unreachable")
        self.assertNotIn("tok-value", str(caught.exception))

    def test_the_url_must_be_https_or_loopback_http(self):
        for url in ("http://agents.example.invalid", "ftp://127.0.0.1", "agents.example.invalid"):
            with self.subTest(url), self.assertRaises(registry_client.RegistryError) as caught:
                registry_client.settings({"KUBANI_REGISTRY_URL": url})
            self.assertEqual(caught.exception.code, "invalid-arguments")
        self.assertEqual(registry_client.settings({}).url, "https://agents.almckay.io")
        self.assertEqual(registry_client.settings({"KUBANI_REGISTRY_URL": "http://127.0.0.1:9/"}).url, "http://127.0.0.1:9")


if __name__ == "__main__":
    unittest.main()
