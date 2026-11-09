"""Agent operations tooling: offline fixtures only; no credentials, network or cluster."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
from agent_ops import approve, layout, live, run, stage, sync  # noqa: E402

REPO = "example/agents"
TAG = "sample/v0.2.0"
RELEASE = "sample-2026-11-09-abcdef12"
IMAGE = "registry.almckay.io/agents/sample@sha256:" + "ab" * 32
SUBJECT = f"https://github.com/{REPO}/.github/workflows/release.yml@refs/tags/{TAG}"
AGENT_BODY = """apiVersion: agentplatform.io/v1alpha1
kind: Agent
metadata:
  name: sample
  namespace: tenant-test
spec:
  owner: owner@example.invalid
  description: Sample
  identity:
    mode: agent
  capabilities:
    models: []
    mcp: []
  runtime:
    cpu: '1'
    memory: 1Gi
    ttlSeconds: 600
"""
RELEASE_DOC = {
    "apiVersion": "agentplatform.io/v1alpha1",
    "kind": "AgentRelease",
    "metadata": {"name": RELEASE, "namespace": "tenant-test"},
    "spec": {
        "agent": "sample",
        "image": IMAGE,
        "manifestSha256": "11" * 32,
        "policySha256": "22" * 32,
        "lockSha256": "33" * 32,
        "buildRevision": "c" * 40,
        "approval": {"approved": False},
    },
}
RELEASE_TEXT = yaml.safe_dump(RELEASE_DOC, sort_keys=False)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_root(tmp: Path, *, release_text: str | None = RELEASE_TEXT, agent_body: str = AGENT_BODY) -> Path:
    root = tmp / "repo"
    d = root / layout.AGENTS_DIR / "tenant-test/sample"
    write(d / "agent.yaml", agent_body)
    resources = ["agent.yaml"]
    if release_text is not None:
        write(d / "agentrelease.yaml", release_text)
        resources.append("agentrelease.yaml")
    write(d / "kustomization.yaml", "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n" + "".join(f"  - {r}\n" for r in resources))
    pin = {
        "issuer": layout.ISSUER,
        "subjectRegExp": "^https://github\\.com/example/agents/\\.github/workflows/release\\.yml@refs/tags/(?:sample|other)/v[0-9][A-Za-z0-9.+-]*$",
        "vulnExceptions": [],
    }
    write(root / layout.SIGNERS, yaml.safe_dump({"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "tenant-signers", "namespace": "kyverno"}, "data": {"tenant-test": json.dumps(pin)}}))
    return root


class FakeGit:
    """Serves `git show`, `rev-parse HEAD` and `status --porcelain` for a fake source checkout."""

    def __init__(self, files: dict[str, dict[str, str]], head: str, dirty: bool = False):
        self.files, self.head, self.dirty = files, head, dirty

    def __call__(self, source, *args):
        if args[:2] == ("rev-parse", "HEAD"):
            return self.head + "\n"
        if args[0] == "status":
            return " M agents/sample/deploy/agent.yaml\n" if self.dirty else ""
        if args[0] == "show":
            commit, path = args[1].split(":", 1)
            try:
                return self.files[commit][path]
            except KeyError:
                raise sync.SyncError("missing") from None
        raise AssertionError(args)


class LayoutTests(unittest.TestCase):
    def test_discovers_agent_and_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            dirs = layout.agent_dirs(root)
            self.assertEqual([(d.tenant, d.agent) for d in dirs], [("tenant-test", "sample")])
            d, file, doc = layout.find_release(root, RELEASE)
            self.assertEqual(file.name, "agentrelease.yaml")
            self.assertEqual(doc["spec"]["image"], IMAGE)
            with self.assertRaises(layout.LayoutError):
                layout.find_release(root, "missing")

    def test_append_resource_refuses_duplicates_and_odd_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            d = layout.find_agent(root, "sample")
            layout.append_resource(d, "agentrelease-v0.2.0.yaml")
            self.assertEqual(layout.kustomization_resources(d)[-1], "agentrelease-v0.2.0.yaml")
            with self.assertRaises(layout.LayoutError):
                layout.append_resource(d, "agentrelease-v0.2.0.yaml")
            d.kustomization.write_text(d.kustomization.read_text() + "commonLabels: {}\n")
            with self.assertRaises(layout.LayoutError):
                layout.append_resource(d, "x.yaml")

    def test_signer_pin_must_be_anchored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            pin = layout.signer_pin(root, "tenant-test")
            self.assertTrue(layout.subject_matches(pin, SUBJECT))
            self.assertFalse(layout.subject_matches(pin, SUBJECT.replace("sample/", "evil/")))
            with self.assertRaises(layout.LayoutError):
                layout.signer_pin(root, "tenant-none")


class SyncTests(unittest.TestCase):
    def test_sync_writes_header_and_exact_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp), agent_body=AGENT_BODY.replace("Sample", "Sample  "))
            git = FakeGit({"a" * 40: {"agents/sample/deploy/agent.yaml": AGENT_BODY}}, "a" * 40)
            with patch.object(sync, "_git", git):
                result = sync.sync(root, "sample", Path("/src"), repo=REPO)
            self.assertFalse(result["specChanged"])
            text = (root / layout.AGENTS_DIR / "tenant-test/sample/agent.yaml").read_text()
            meta, body = sync.split(text)
            self.assertEqual(body, AGENT_BODY)
            self.assertEqual(meta["commit"], "a" * 40)
            self.assertEqual(meta["sha"], hashlib.sha256(AGENT_BODY.encode()).hexdigest())
            with patch.object(sync, "_git", git):
                check = sync.check(root)
            self.assertTrue(check["ok"])
            self.assertEqual(check["agents"][0]["state"], "ok")

    def test_sync_refuses_dirty_source_and_wrong_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            with patch.object(sync, "_git", FakeGit({}, "a" * 40, dirty=True)):
                with self.assertRaises(sync.SyncError):
                    sync.sync(root, "sample", Path("/src"))
            wrong = AGENT_BODY.replace("namespace: tenant-test", "namespace: tenant-other")
            with patch.object(sync, "_git", FakeGit({"a" * 40: {"agents/sample/deploy/agent.yaml": wrong}}, "a" * 40)):
                with self.assertRaises(sync.SyncError):
                    sync.sync(root, "sample", Path("/src"))

    def test_check_detects_unsynced_tampered_and_source_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            self.assertEqual(sync.check(root)["agents"][0]["state"], "unsynced")
            self.assertFalse(sync.check(root)["ok"])
            file = root / layout.AGENTS_DIR / "tenant-test/sample/agent.yaml"
            file.write_text(sync.header(REPO, "sample", "a" * 40, AGENT_BODY) + AGENT_BODY.replace("1Gi", "2Gi"))
            row = sync.check(root)["agents"][0]
            self.assertEqual(row["state"], "fail")
            self.assertIn("sha256", row["detail"])
            file.write_text(sync.header(REPO, "sample", "a" * 40, AGENT_BODY) + AGENT_BODY)
            git = FakeGit({"a" * 40: {"agents/sample/deploy/agent.yaml": AGENT_BODY.replace("1Gi", "3Gi")}}, "a" * 40)
            with patch.object(sync, "_git", git):
                row = sync.check(root, source=Path("/src"))["agents"][0]
            self.assertEqual(row["state"], "fail")
            newer = AGENT_BODY.replace("1Gi", "4Gi")
            git = FakeGit({"a" * 40: {"agents/sample/deploy/agent.yaml": AGENT_BODY}, "b" * 40: {"agents/sample/deploy/agent.yaml": newer}}, "b" * 40)
            with patch.object(sync, "_git", git):
                row = sync.check(root, source=Path("/src"))["agents"][0]
            self.assertEqual(row["state"], "ok")
            self.assertTrue(row["stale"])


def assets(dest: Path, **overrides) -> None:
    files = {
        "agent.yaml": AGENT_BODY,
        "agentrelease.yaml": RELEASE_TEXT,
        "policy-bundle.json": json.dumps({"agent": "sample", "tenant": "tenant-test", "release": RELEASE, "image": IMAGE}),
        "predicate.json": json.dumps({"release": RELEASE, "buildRevision": "c" * 40, "lockSha256": "33" * 32, "manifestSha256": "11" * 32, "policySha256": "22" * 32}),
        "image": IMAGE + "\n",
    }
    files.update(overrides)
    for name, text in files.items():
        write(dest / name, text)
    if "SHA256SUMS" not in overrides:
        sums = "".join(f"{hashlib.sha256((dest / n).read_bytes()).hexdigest()}  {n}\n" for n in stage.SUMMED)
        write(dest / "SHA256SUMS", sums)


class StageTests(unittest.TestCase):
    def stage(self, root, **overrides):
        def fake_download(repo, tag, dest):
            assets(dest, **overrides)

        with patch.object(stage, "download", fake_download):
            return stage.stage(root, "sample", TAG, repo=REPO)

    def test_stage_writes_verified_release_and_lists_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp), release_text=None)
            result = self.stage(root)
            file = root / layout.AGENTS_DIR / "tenant-test/sample/agentrelease-v0.2.0.yaml"
            self.assertEqual(result["release"], RELEASE)
            self.assertEqual(yaml.safe_load(file.read_text()), RELEASE_DOC)
            text = file.read_text()
            self.assertTrue(text.startswith("# yamllint disable rule:line-length\n"))
            self.assertEqual(text.count("pragma: allowlist secret"), 5)
            self.assertIn("agentrelease-v0.2.0.yaml", layout.kustomization_resources(layout.find_agent(root, "sample")))
            self.assertEqual(result["expectedSigner"], SUBJECT)

    def test_stage_refusals(self):
        approved = RELEASE_TEXT.replace("approved: false", "approved: true")
        other_image = IMAGE.replace("ab" * 32, "cd" * 32)
        cases = {
            "approved": {"agentrelease.yaml": approved},
            "image asset": {"image": other_image},
            "predicate": {"predicate.json": json.dumps({"release": RELEASE, "buildRevision": "d" * 40, "lockSha256": "33" * 32, "manifestSha256": "11" * 32, "policySha256": "22" * 32})},
            "agent differs": {"agent.yaml": AGENT_BODY.replace("1Gi", "9Gi")},
            "bundle": {"policy-bundle.json": json.dumps({"agent": "other", "tenant": "tenant-test", "release": RELEASE, "image": IMAGE})},
            "sums": {"SHA256SUMS": "0" * 64 + "  agent.yaml\n"},
        }
        for label, overrides in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as tmp:
                root = make_root(Path(tmp), release_text=None)
                with self.assertRaises(stage.StageError):
                    self.stage(root, **overrides)
                self.assertEqual(layout.kustomization_resources(layout.find_agent(root, "sample")), ["agent.yaml"])

    def test_stage_refuses_duplicates_bad_tags_and_unpinned_signers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            with self.assertRaises(stage.StageError):
                self.stage(root)  # RELEASE is already staged in agentrelease.yaml
            with self.assertRaises(stage.StageError):
                stage.stage(root, "sample", "other/v1.0.0", repo=REPO)
            pin_file = root / layout.SIGNERS
            pin_file.write_text(pin_file.read_text().replace("sample|other", "other"))
            root2 = make_root(Path(tmp) / "two", release_text=None)
            (root2 / layout.SIGNERS).write_text(pin_file.read_text())
            with self.assertRaises(stage.StageError):
                self.stage(root2)


def live_release(**changes) -> dict:
    obj = {
        "metadata": {"name": RELEASE, "namespace": "tenant-test", "uid": "u-1"},
        "spec": json.loads(json.dumps(RELEASE_DOC["spec"])),
        "status": {
            "conditions": [
                {"type": "PolicyDrift", "status": "False", "reason": "NoDrift"},
                {"type": "Ready", "status": "False", "reason": "NotApproved"},
                {"type": "SignatureVerified", "status": "True", "reason": "Verified"},
            ],
            "policyDigest": "sha256:" + "22" * 32,
            "policyDrift": False,
            "ready": False,
            "signatureVerified": True,
            "verifiedSigner": {"issuer": layout.ISSUER, "subject": SUBJECT, "attestations": sorted(layout.ATTESTATIONS)},
        },
    }
    for path, value in changes.items():
        node = obj
        keys = path.split(".")
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
    return obj


class FakeKube:
    def __init__(self, objects: dict | None = None, exec_results: list | None = None):
        self.objects = objects or {}
        self.exec_results = list(exec_results or [])
        self.exec_calls = []

    def get(self, kind, name, namespace, *, selector=None):
        return self.objects[(kind, name, namespace)]

    def exec(self, pod, namespace, container, argv, stdin, timeout):
        self.exec_calls.append(json.loads(argv[-1]))
        payload = self.exec_results.pop(0)
        code = 2 if "error" in payload else 0
        return subprocess.CompletedProcess(argv, code, stdout=json.dumps(payload).encode(), stderr=b"")


class ApproveTests(unittest.TestCase):
    def test_gates_pass_and_each_failure_is_refused(self):
        committed = json.loads(json.dumps(RELEASE_DOC))
        pin = {"issuer": layout.ISSUER, "subjectRegExp": "^" + SUBJECT.replace(".", "\\.") + "$"}
        evidence = approve.gates(committed, live_release(), pin, REPO)
        self.assertEqual(evidence["signer"], SUBJECT)
        self.assertEqual(len(evidence["attestations"]), 5)
        failures = {
            "spec drift": {"spec.image": IMAGE.replace("ab" * 32, "cd" * 32)},
            "already approved": {"spec.approval": {"approved": True}},
            "unsigned": {"status.signatureVerified": False},
            "wrong signer": {"status.verifiedSigner.subject": SUBJECT.replace("sample/", "other/")},
            "four attestations": {"status.verifiedSigner.attestations": sorted(layout.ATTESTATIONS)[:4]},
            "drift": {"status.policyDrift": True},
            "digest": {"status.policyDigest": "sha256:" + "99" * 32},
            "ready for another reason": {"status.conditions": [
                {"type": "PolicyDrift", "status": "False", "reason": "NoDrift"},
                {"type": "Ready", "status": "False", "reason": "AgentNotReady"},
                {"type": "SignatureVerified", "status": "True", "reason": "Verified"},
            ]},
            "other object": {"metadata.name": "sample-2026-11-09-00000000"},
        }
        for label, changes in failures.items():
            with self.subTest(label), self.assertRaises(approve.ApproveError):
                approve.gates(committed, live_release(**changes), pin, REPO)

    def test_approve_edits_only_the_approval_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            kube = FakeKube({("agentrelease", RELEASE, "tenant-test"): live_release()})
            when = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
            result = approve.approve(root, RELEASE, ticket="https://example.invalid/pr/1", repo=REPO, kube=kube, now=when)
            self.assertEqual(result["approvedBy"], "owner@example.invalid")
            doc = yaml.safe_load((root / result["file"]).read_text())
            self.assertEqual(doc["spec"]["approval"], {"approved": True, "approvedBy": "owner@example.invalid", "approvedAt": "2026-11-09T12:00:00Z", "ticket": "https://example.invalid/pr/1"})
            del doc["spec"]["approval"]
            expected = json.loads(json.dumps(RELEASE_DOC))
            del expected["spec"]["approval"]
            self.assertEqual(doc, expected)
            with self.assertRaises(approve.ApproveError):
                approve.approve(root, RELEASE, repo=REPO, kube=kube)  # now committed as approved


def view(name, agent="sample", **kw):
    base = dict(name=name, agent=agent, approved=True, ready=True, signature=True, drift=False, identity_mode="agent", delegation_required=False, ready_reason="Ready")
    base.update(kw)
    return live.ReleaseView(**base)


class LiveTests(unittest.TestCase):
    def test_release_resolution(self):
        views = [view("sample-1"), view("sample-2", approved=False), view("sample-3", drift=True), view("other-1", agent="other")]
        self.assertEqual(live.resolve_release(views, "sample", None).name, "sample-1")
        with self.assertRaises(live.LiveError):
            live.resolve_release(views, "sample", "sample-2")
        with self.assertRaises(live.LiveError):
            live.resolve_release(views, "missing", None)
        views.append(view("sample-4"))
        with self.assertRaises(live.LiveError):
            live.resolve_release(views, "sample", None)
        self.assertEqual(live.resolve_release(views, "sample", "sample-4").name, "sample-4")

    def test_runner_pod_requires_exactly_one_ready_pod(self):
        def pod(name, ready=True, phase="Running"):
            return {"metadata": {"name": name, "uid": "uid-" + name}, "status": {"phase": phase, "containerStatuses": [{"name": "runner", "ready": ready, "containerID": "c", "imageID": "i", "restartCount": 0}]}}

        kube = FakeKube({("pods", None, "agent-platform"): {"items": [pod("a"), pod("b", ready=False)]}})
        self.assertEqual(live.runner_pod(kube, "tenant-test")["name"], "a")
        kube = FakeKube({("pods", None, "agent-platform"): {"items": [pod("a"), pod("b")]}})
        with self.assertRaises(live.LiveError):
            live.runner_pod(kube, "tenant-test")

    def test_format_listing_marks_ambiguous_and_none(self):
        rows = [
            {"agent": "a", "identity": "agent", "live": True, "ready": True, "releases": 2, "readyReleases": ["a-1", "a-2"], "runnable": None},
            {"agent": "b", "identity": None, "live": False, "ready": False, "releases": 0, "readyReleases": [], "runnable": None},
        ]
        text = live.format_listing(rows)
        self.assertIn("ambiguous (2 Ready; pass --release)", text)
        self.assertIn("absent", text)
        self.assertIn("none", text)


def kube_for_run(exec_results, identity_mode="agent"):
    pod = {"metadata": {"name": "runner-1", "uid": "uid-1"}, "status": {"phase": "Running", "containerStatuses": [{"name": "runner", "ready": True, "containerID": "c", "imageID": "i", "restartCount": 0}]}}
    release = {"metadata": {"name": RELEASE}, "spec": {"agent": "sample", "approval": {"approved": True}}, "status": {"ready": True, "signatureVerified": True, "policyDrift": False, "identityMode": identity_mode, "conditions": [{"type": "Ready", "status": "True", "reason": "Ready"}]}}
    return FakeKube({("agentreleases", None, "tenant-test"): {"items": [release]}, ("pods", None, "agent-platform"): {"items": [pod]}, ("agents", None, "tenant-test"): {"items": []}}, exec_results)


class RunTests(unittest.TestCase):
    def test_plan_enforces_identity_mode_grant_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            with self.assertRaises(run.RunError):
                run.plan(root, kube_for_run([]), "sample", release=None, grant_handle="h", task={"request": "x"})
            with self.assertRaises(run.RunError):
                run.plan(root, kube_for_run([], "on-behalf-of"), "sample", release=None, grant_handle=None, task={"request": "x"})
            p = run.plan(root, kube_for_run([], "on-behalf-of"), "sample", release=None, grant_handle="h", task={"request": "x"})
            self.assertEqual(p["release"], RELEASE)
            with self.assertRaises(run.RunError):
                run.plan(root, kube_for_run([]), "sample", release=None, grant_handle=None, task={"request": "x" * 20000})

    def test_submit_waits_and_writes_private_report(self):
        accepted = {"workflow_id": "session:tenant-test:sample:s", "run_id": "r", "namespace": "agents-tenant-test", "task_queue": "sessions-tenant-test"}
        running = {"workflow_id": "w", "run_id": "r", "status": "RUNNING", "query": {"state": "RUNNING"}}
        done = {"workflow_id": "w", "run_id": "r", "status": "COMPLETED", "query": {"state": "CLEANED"}, "result": {"outcome": "COMPLETED"}, "confirmed": True}
        report = dict(done, report="# Report\n", workspace=["workspace/report.md"])
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            kube = kube_for_run([accepted, running, done, report])
            out = Path(tmp) / "run"
            code, envelope = run.submit(root, "sample", {"request": "go"}, out=out, kube=kube, sleep=lambda s: None, clock=iter(range(0, 1000, 1)).__next__)
            self.assertEqual(code, 0)
            self.assertEqual(envelope["cleanup"], "CONFIRMED")
            self.assertEqual((out / "report.md").read_text(), "# Report\n")
            self.assertEqual(oct(os.stat(out / "report.md").st_mode & 0o777), "0o600")
            receipt = json.loads((out / "receipt.json").read_text())
            self.assertEqual(receipt["release"], RELEASE)
            self.assertNotIn("grant_handle", (out / "request.json").read_text())
            self.assertEqual([c["action"] for c in kube.exec_calls], ["submit", "status", "status", "report"])
            self.assertEqual(kube.exec_calls[0]["grant_handle"], None)

    def test_submit_reports_timeout_and_unconfirmed_completion(self):
        accepted = {"workflow_id": "w", "run_id": "r", "namespace": "agents-tenant-test", "task_queue": "sessions-tenant-test"}
        running = {"workflow_id": "w", "run_id": "r", "status": "RUNNING", "query": {}}
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            clock = iter([0, 1000, 1000, 1000]).__next__
            code, envelope = run.submit(root, "sample", {"request": "go"}, out=Path(tmp) / "a", kube=kube_for_run([accepted, running]), wait_timeout=5, sleep=lambda s: None, clock=clock)
            self.assertEqual(code, 124)
            self.assertEqual(envelope["cleanup"], "NOT_CONFIRMED")
            failed = {"workflow_id": "w", "run_id": "r", "status": "COMPLETED", "query": {"state": "FAILED"}, "result": {"outcome": "FAILED"}, "confirmed": False}
            kube = kube_for_run([accepted, failed])
            code, envelope = run.submit(root, "sample", {"request": "go"}, out=Path(tmp) / "b", kube=kube, sleep=lambda s: None)
            self.assertEqual(code, 1)
            self.assertFalse((Path(tmp) / "b/report.md").exists())
            self.assertEqual([c["action"] for c in kube.exec_calls], ["submit", "status"])

    def test_remote_error_is_surfaced_without_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            with self.assertRaises(run.RunError):
                run.submit(root, "sample", {"request": "go"}, out=Path(tmp) / "a", kube=kube_for_run([{"error": "session identity already exists"}]))


class RemoteScriptTests(unittest.TestCase):
    def test_remote_script_compiles_and_stays_within_its_imports(self):
        path = OPS / "agent_ops/remote_session.py"
        py_compile.compile(str(path), doraise=True)
        tree = ast.parse(path.read_text())
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add((node.module or "").split(".")[0])
        self.assertTrue(modules <= {"asyncio", "dataclasses", "hashlib", "io", "json", "os", "re", "sys", "tarfile", "uuid", "datetime", "temporalio", "runner"}, modules)
        text = path.read_text()
        for forbidden in ("token.json", "state.json", "PAYLOAD_KEY_FILE", "TEMPORAL_TLS", "open(\"/etc"):
            self.assertNotIn(forbidden, text)
        self.assertIn('"workspace/report.md"', text)


if __name__ == "__main__":
    unittest.main()
