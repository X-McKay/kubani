"""Tenants: `just agent tenant add|check|sync` and a tenant's first registration.

Everything runs on a copy of the committed pieces in a temporary directory: no cluster, no network, no credentials. No
Secret is read, copied or written; a payload key is an empty file here, because the tool looks only at whether it exists.
"""

from __future__ import annotations

import contextlib
import difflib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from test_agent_ops import AGENT_BODY, PIN, REPO, FakeGit, FakeKube, cli, synced_root

from agent_ops import layout, register, state, sync, tenant
import registry_feed

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = tenant.REFERENCE
# The tenants this repository has today. The tests add two more, under names no real tenant will take, so they hold
# whichever tenants are committed.
EXISTING = tenant.tenants(ROOT)
NEW, SECOND = "tenant-added-in-a-test", "tenant-second-in-a-test"
OTHERS = [t for t in sorted([*EXISTING, NEW]) if t != REFERENCE]
SHARED = sorted({tenant.RBAC, tenant.MTLS, register.NAMESPACES, *(path for path, _ in tenant.entries(REFERENCE))})


def copied(tmp: Path) -> Path:
    """The files the committed tenants are made of, and their Agents. Each payload key is an empty file."""
    root = tmp / "repo"
    for path in [*SHARED, layout.SIGNERS, *(path for name in EXISTING for path in tenant.files(name))]:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, root / path)
    for d in layout.agent_dirs(ROOT):
        target = root / d.agent_file.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(d.agent_file, target)
    for name in EXISTING:
        (root / tenant.payload_key(name)).touch()
    return root


def tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@contextlib.contextmanager
def restored(root: Path):
    """Put the tree back as it was, so one added tenant serves many cases."""
    before = tree(root)
    try:
        yield
    finally:
        for path in set(tree(root)) - set(before):
            (root / path).unlink()
        for path, content in before.items():
            (root / path).write_bytes(content)


def row(result: dict, name: str) -> dict:
    return next(r for r in result["tenants"] if r["tenant"] == name)


def edit(root: Path, path: Path, old: str, new: str, count: int = 1) -> None:
    text = (root / path).read_text()
    assert text.count(old) >= 1, (path, old)
    (root / path).write_text(text.replace(old, new, count))


def edit_document(root: Path, path: Path, kind: str, name: str, change) -> None:
    """Rewrite one document of a shared file through `change(text) -> text | None`; None removes the document."""
    text = (root / path).read_text()
    chunks = tenant._chunks(text)
    i = tenant._chunk(text, kind, name, path)
    changed = change(chunks[i])
    if changed is None:
        del chunks[i]
    else:
        assert changed != chunks[i], (path, kind, name)
        chunks[i] = changed
    (root / path).write_text("---\n".join(chunks))


class CommittedTenantsTests(unittest.TestCase):
    def test_every_tenant_of_this_repository_has_every_piece(self):
        result = tenant.check(ROOT)
        self.assertTrue(result["ok"], result)
        self.assertIn(REFERENCE, [r["tenant"] for r in result["tenants"]])

    def test_the_copy_these_tests_use_passes_as_the_repository_does(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = tenant.check(copied(Path(tmp)))
        self.assertEqual([(r["tenant"], r["state"]) for r in result["tenants"]], [(name, "ok") for name in EXISTING])


class AddTests(unittest.TestCase):
    def test_add_writes_every_piece_and_leaves_only_the_payload_key_to_a_person(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copied(Path(tmp))
            before = tree(root)
            result = tenant.add(root, NEW)
            after = tree(root)

            self.assertEqual(result["files"], sorted(str(p) for p in [*SHARED, *tenant.files(NEW)]))
            self.assertEqual(result["missing"], [str(tenant.payload_key(NEW))])
            self.assertEqual(sorted(set(after) - set(before)), sorted(str(p) for p in tenant.files(NEW)))
            self.assertFalse([p for p in after if "payload-key" in p and NEW in p], "add writes no Secret")
            # Nothing of the reference or of the platform is rewritten: shared files only gain lines.
            for path, content in before.items():
                if Path(path) in SHARED:
                    removed = [line for line in difflib.ndiff(content.decode().split("\n"), after[path].decode().split("\n")) if line.startswith("- ")]
                    self.assertEqual(removed, [], path)
                else:
                    self.assertEqual(after[path], content, path)
            for path in tenant.files(NEW):
                self.assertNotIn(REFERENCE, "\n".join((root / path).read_text().split("\n")[4:]), path)

            checked = tenant.check(root)
            self.assertFalse(checked["ok"])
            self.assertEqual(row(checked, NEW), {"tenant": NEW, "agents": 0, "state": "fail", "problems": [tenant._no_key(NEW)]})
            self.assertEqual(row(checked, REFERENCE)["state"], "ok")
            (root / tenant.payload_key(NEW)).touch()
            self.assertTrue(tenant.check(root)["ok"])

    def test_a_new_tenant_trusts_no_one_and_grants_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copied(Path(tmp))
            pins = (root / layout.SIGNERS).read_bytes()
            tenant.add(root, NEW)
            self.assertEqual((root / layout.SIGNERS).read_bytes(), pins)
            self.assertEqual(register.pinned_tenants(root), register.pinned_tenants(ROOT))
            declared = register.declared_tenants(root)
            self.assertNotIn("annotations", declared[NEW])
            self.assertEqual(declared[NEW]["labels"], {k: v.replace(REFERENCE, NEW) for k, v in declared[REFERENCE]["labels"].items()})
            pin_row = row(register.check(root), NEW)
            self.assertEqual((pin_row["state"], pin_row["sources"]), ("ok", {}))
            self.assertTrue(register.check(root)["ok"])

    def test_add_refuses_a_name_that_is_not_a_new_tenant(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copied(Path(tmp))
            before = tree(root)
            for name in ("ops", "tenant-", "tenant-Ops", "tenant_ops", "tenant-" + "a" * 60, ""):
                with self.subTest(name=name), self.assertRaises(tenant.TenantError) as caught:
                    tenant.add(root, name)
                self.assertEqual(caught.exception.code, "invalid-arguments")
            with self.assertRaises(tenant.TenantError) as caught:
                tenant.add(root, REFERENCE)
            self.assertEqual(caught.exception.code, "conflict")
            self.assertEqual(tree(root), before)
            tenant.add(root, NEW)
            added = tree(root)
            with self.assertRaises(tenant.TenantError) as caught:
                tenant.add(root, NEW)
            self.assertEqual(caught.exception.code, "conflict")
            self.assertEqual(tree(root), added)

    def test_add_keeps_nothing_when_the_reference_cannot_be_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copied(Path(tmp))
            # The reference's entry is gone from one kustomization, so there is no line to list the new tenant after.
            edit(root, tenant.NETPOL / "kustomization.yaml", f"  - {REFERENCE}.yaml\n", "")
            before = tree(root)
            with self.assertRaises(tenant.TenantError):
                tenant.add(root, NEW)
            self.assertEqual(tree(root), before)
            self.assertFalse((root / layout.AGENTS_DIR / NEW).exists())

    def test_a_second_tenant_is_added_beside_the_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copied(Path(tmp))
            tenant.add(root, NEW)
            tenant.add(root, SECOND)
            for name in (NEW, SECOND):
                (root / tenant.payload_key(name)).touch()
            result = tenant.check(root)
            self.assertTrue(result["ok"], result)
            self.assertEqual([r["tenant"] for r in result["tenants"]], sorted([*EXISTING, NEW, SECOND]))


class CheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = copied(Path(cls.tmp.name))
        tenant.add(cls.root, NEW)
        (cls.root / tenant.payload_key(NEW)).touch()

    def problems(self) -> list[str]:
        result = tenant.check(self.root)
        self.assertEqual(row(result, REFERENCE)["state"], "ok")
        return row(result, NEW)["problems"]

    def test_the_added_tenant_passes(self):
        self.assertEqual(self.problems(), [])

    def test_each_missing_file_is_named(self):
        for path in [*tenant.files(NEW), tenant.payload_key(NEW)]:
            with self.subTest(path=str(path)), restored(self.root):
                (self.root / path).unlink()
                found = self.problems()
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0].startswith(f"{path} is missing"), found)

    def test_each_altered_file_is_named(self):
        for path in tenant.files(NEW):
            with self.subTest(path=str(path)), restored(self.root):
                docs = [d for d in yaml.safe_load_all((self.root / path).read_text()) if d]
                docs[-1]["metadata"].setdefault("labels", {})["added-by-hand"] = "yes"
                (self.root / path).write_text(yaml.safe_dump_all(docs, sort_keys=False))
                self.assertEqual(self.problems(), [f"{path} differs from the reference's; run `just agent tenant sync`"])

    def test_a_comment_is_not_a_difference(self):
        path = next(iter(tenant.files(NEW)))
        with restored(self.root):
            (self.root / path).write_text((self.root / path).read_text() + "# a note someone added\n")
            self.assertEqual(self.problems(), [])

    def test_each_unlisted_entry_is_named(self):
        for path, entry in tenant.entries(NEW):
            with self.subTest(entry=entry), restored(self.root):
                edit(self.root, path, f"  - {entry}\n", "")
                self.assertEqual(self.problems(), [f"{path}: {entry} is not listed"])

    def test_each_missing_or_altered_document_is_named(self):
        for path, kind, name in tenant.documents(NEW):
            with self.subTest(kind=kind, gone=True), restored(self.root):
                edit_document(self.root, path, kind, name, lambda text: None)
                self.assertEqual(self.problems(), [f"{path}: no {kind} {name}"])
            with self.subTest(kind=kind, gone=False), restored(self.root):
                edit_document(self.root, path, kind, name, lambda text: text.replace("metadata:\n", "metadata:\n  annotations: {added-by-hand: 'yes'}\n", 1))
                self.assertEqual(self.problems(), [f"{path}: {kind} {name} differs from the reference's; run `just agent tenant sync`"])

    def test_a_session_interface_the_temporal_endpoint_does_not_admit_is_named(self):
        with restored(self.root):
            edit(self.root, tenant.MTLS, f"{tenant.SAN}{NEW}", f"{tenant.SAN}tenant-ghost")
            result = tenant.check(self.root)
            self.assertEqual(row(result, NEW)["problems"], [f"{tenant.MTLS}: the Temporal endpoint does not admit {tenant.SAN}{NEW}"])
            # ... and an identity of no tenant is admitted, which no tenant's row would show.
            self.assertEqual(row(result, "*")["problems"], [f"{tenant.MTLS}: the Temporal endpoint admits a session interface of no tenant: tenant-ghost"])

    def test_the_namespace_is_held_to_the_reference(self):
        with restored(self.root):
            edit(self.root, register.NAMESPACES, f"  name: {NEW}\n  labels:\n", f"  name: {NEW}\n  labels:\n    pod-security.kubernetes.io/enforce: privileged\n")
            edit_document(self.root, register.NAMESPACES, "Namespace", NEW, lambda text: text.replace("    pod-security.kubernetes.io/enforce: restricted\n", "", 1))
            self.assertEqual(self.problems(), [f"{register.NAMESPACES}: Namespace {NEW} does not carry the reference's labels"])
        with restored(self.root):
            edit(self.root, register.NAMESPACES, f"  name: {NEW}\n", f"  name: {NEW}\n  annotations:\n    {register.ANNOTATION}: '{PIN}'\n")
            self.assertEqual(self.problems(), [f"{register.NAMESPACES}: Namespace {NEW} carries a signer pin and has no committed Agents"])
            self.assertEqual(row(register.check(self.root), NEW)["state"], "fail")
        with restored(self.root):
            edit_document(self.root, register.NAMESPACES, "Namespace", NEW, lambda text: None)
            found = self.problems()
            self.assertEqual(found, [f"{register.NAMESPACES}: no Namespace {NEW} with the label agentplatform.io/tenant"])

    def test_a_tenant_that_is_only_a_file_is_still_checked(self):
        """A piece left behind (or written by hand) makes a tenant the check looks at, so a half-removed tenant is seen."""
        with restored(self.root):
            (self.root / tenant.NETPOL / "tenant-left.yaml").write_text("{}\n")
            result = tenant.check(self.root)
            self.assertEqual(row(result, "tenant-left")["state"], "fail")
            self.assertGreater(len(row(result, "tenant-left")["problems"]), 5)


class SyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = copied(Path(tmp.name))
        tenant.add(self.root, NEW)
        (self.root / tenant.payload_key(NEW)).touch()

    def test_sync_changes_nothing_after_add(self):
        before = tree(self.root)
        self.assertEqual(tenant.sync(self.root), {"tenants": OTHERS, "files": [], "next": "`just agent tenant check`, then commit"})
        self.assertEqual(tree(self.root), before)

    def test_a_change_to_the_reference_fails_the_check_until_sync(self):
        runner = tenant.WORKLOADS / f"session-runner-{REFERENCE}.yaml"
        edit(self.root, runner, "platform/session-runner:", "platform/session-runner-next:")
        kind, name = "Certificate", tenant.REFERENCE_CERTIFICATE
        edit_document(self.root, tenant.MTLS, kind, name, lambda text: text.replace("duration: 2160h", "duration: 100h", 1))
        own = tenant.WORKLOADS / f"session-runner-{NEW}.yaml"
        self.assertEqual(
            row(tenant.check(self.root), NEW)["problems"],
            [
                f"{own} differs from the reference's; run `just agent tenant sync`",
                f"{tenant.MTLS}: {kind} session-api-{NEW}-temporal-tls differs from the reference's; run `just agent tenant sync`",
            ],
        )
        reference = {path: (self.root / path).read_bytes() for path in tenant.files(REFERENCE)}
        result = tenant.sync(self.root, NEW)
        self.assertEqual(result["files"], sorted([str(own), str(tenant.MTLS)]))
        self.assertEqual(row(tenant.check(self.root), NEW)["state"], "ok")
        self.assertIn("platform/session-runner-next:", (self.root / own).read_text())
        self.assertEqual({path: (self.root / path).read_bytes() for path in reference}, reference)
        certificates = [d for d in yaml.safe_load_all((self.root / tenant.MTLS).read_text()) if d and d["kind"] == "Certificate"]
        durations = {d["metadata"]["name"]: d["spec"]["duration"] for d in certificates}
        self.assertEqual((durations[name], durations[f"session-api-{NEW}-temporal-tls"]), ("100h", "100h"))
        self.assertEqual({n for n, d in durations.items() if d == "100h"}, {name, f"session-api-{NEW}-temporal-tls"}, "no other certificate is touched")

    def test_sync_restores_a_piece_that_was_removed(self):
        (self.root / tenant.NETPOL / f"{NEW}.yaml").unlink()
        edit_document(self.root, tenant.RBAC, "ServiceAccount", f"session-api-{NEW}", lambda text: None)
        edit(self.root, tenant.MTLS, f"                        - san_type: URI\n                          matcher: {{exact: {tenant.SAN}{NEW}}}\n", "")
        self.assertEqual(len(row(tenant.check(self.root), NEW)["problems"]), 3)
        tenant.sync(self.root, NEW)
        self.assertTrue(tenant.check(self.root)["ok"])

    def test_sync_takes_only_an_added_tenant(self):
        for name, code in ((REFERENCE, "not-found"), ("tenant-nope", "not-found"), ("ops", "invalid-arguments")):
            with self.subTest(name=name), self.assertRaises(tenant.TenantError) as caught:
                tenant.sync(self.root, name)
            self.assertEqual(caught.exception.code, code)


class FirstRegistrationTests(unittest.TestCase):
    """`just agent register` writes a tenant's pin with its first agent; until then the tenant has none."""

    NEW_BODY = AGENT_BODY.replace("name: sample", "name: new-agent").replace("namespace: tenant-test", f"namespace: {NEW}")
    GIT = FakeGit({"b" * 40: {"agents/new-agent/deploy/agent.yaml": NEW_BODY}}, "b" * 40)

    def root(self, tmp: str) -> Path:
        root = synced_root(Path(tmp))
        path = root / register.NAMESPACES
        path.write_text(path.read_text() + f"---\napiVersion: v1\nkind: Namespace\nmetadata:\n  name: {NEW}\n  labels:\n    agentplatform.io/tenant: {NEW}\n")
        return root

    def test_an_empty_declared_tenant_is_in_order_and_is_not_in_the_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            result = register.check(root)
            self.assertEqual(row(result, NEW), {"tenant": NEW, "sources": {}, "state": "ok", "detail": "no committed Agents and no pin: the tenant trusts no one"})
            self.assertTrue(register.unpinned(root, NEW))
            self.assertFalse(register.unpinned(root, REFERENCE))
            self.assertFalse(register.unpinned(root, "tenant-other"))
            self.assertNotIn(NEW, json.dumps(registry_feed.render(root)))

    def test_the_first_registration_writes_the_pin_in_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            reference = register.committed_pins(root, REFERENCE)
            with patch.object(sync, "_git", self.GIT):
                result = register.register(root, NEW, "example/my-agent", ["new-agent"], Path("/src"))
            self.assertEqual(result["added"], ["new-agent"])
            self.assertEqual(result["pinFiles"], [str(layout.SIGNERS), str(register.NAMESPACES)])
            pin = register.subject_regexp({"example/my-agent": ("new-agent",)})
            self.assertEqual(register.committed_pins(root, NEW), {"configmap": pin, "namespace": pin})
            self.assertEqual(register.committed_pins(root, REFERENCE), reference)
            self.assertEqual(register.declared_tenants(root)[NEW]["annotations"], {register.ISSUER_ANNOTATION: layout.ISSUER, register.ANNOTATION: pin})
            entry = json.loads(yaml.safe_load((root / layout.SIGNERS).read_text())["data"][NEW])
            self.assertEqual(entry, {"issuer": layout.ISSUER, "subjectRegExp": pin, "vulnExceptions": []})
            self.assertEqual(row(register.check(root), NEW)["state"], "ok")
            self.assertFalse(register.unpinned(root, NEW))
            self.assertEqual((root / registry_feed.FEED).read_bytes(), registry_feed.feed_bytes(registry_feed.render(root)))
            self.assertIn(NEW, json.dumps(registry_feed.render(root)))
            # The tenant's own repository is trusted for this tenant's agent only.
            self.assertFalse(layout.subject_matches({"subjectRegExp": reference["configmap"]}, layout.expected_subject("example/my-agent", "new-agent/v1.0.0")))
            self.assertFalse(layout.subject_matches({"subjectRegExp": pin}, layout.expected_subject(REPO, "sample/v1.0.0")))

    def test_a_second_registration_rewrites_the_pin_as_for_any_tenant(self):
        other = self.NEW_BODY.replace("name: new-agent", "name: other-agent")
        git = FakeGit({"b" * 40: {"agents/new-agent/deploy/agent.yaml": self.NEW_BODY, "agents/other-agent/deploy/agent.yaml": other}}, "b" * 40)
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            with patch.object(sync, "_git", git):
                register.register(root, NEW, "example/my-agent", ["new-agent"], Path("/src"))
                register.register(root, NEW, "example/my-agent", ["other-agent"], Path("/src"))
            pin = register.subject_regexp({"example/my-agent": ("new-agent", "other-agent")})
            self.assertEqual(register.committed_pins(root, NEW), {"configmap": pin, "namespace": pin})
            self.assertEqual(row(register.check(root), NEW)["state"], "ok")

    def test_a_tenant_that_is_not_declared_is_still_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            before = tree(root)
            with patch.object(sync, "_git", self.GIT), self.assertRaises(register.RegisterError):
                register.register(root, "tenant-other", "example/my-agent", ["new-agent"], Path("/src"))
            self.assertEqual(tree(root), before)

    def test_a_first_pin_that_would_not_read_back_changes_neither_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            before = tree(root)
            for pattern in ("^it's$", "^a\nb$"):
                with self.subTest(pattern=pattern), self.assertRaises(register.RegisterError):
                    register.create_pins(root, NEW, pattern)
            with self.assertRaises(register.RegisterError):  # no Namespace to annotate
                register.create_pins(root, "tenant-other", "^a$")
            self.assertEqual(tree(root), before)

    def test_state_shows_a_tenant_before_its_first_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.root(tmp)
            empty = {"items": []}
            objects = {("kustomizations.kustomize.toolkit.fluxcd.io", None, "flux-system"): empty, ("pods", None, "agent-platform"): empty}
            for name in (REFERENCE, NEW):
                objects.update({("pods", None, name): empty, ("agents", None, name): empty, ("agentreleases", None, name): empty})
            snap = state.snapshot(root, FakeKube(objects), prs=False)
        self.assertEqual(list(snap["tenants"]), [NEW, REFERENCE])
        self.assertEqual(snap["tenants"][NEW]["agents"]["total"], 0)
        self.assertIn(f"TENANT {NEW}", state.format_snapshot(snap))


class CommandLineTests(unittest.TestCase):
    def call(self, root: Path, *argv: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(root), "tenant", *argv])
        return code, json.loads(out.getvalue())

    def test_add_check_and_sync_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copied(Path(tmp))
            code, doc = self.call(root, "check")
            self.assertEqual((code, doc["ok"], [r["tenant"] for r in doc["tenants"]]), (0, True, EXISTING))

            code, doc = self.call(root, "add", "ops")
            self.assertEqual((code != 0, doc["ok"], doc["error"]["code"]), (True, False, "invalid-arguments"))

            code, doc = self.call(root, "add", NEW)
            self.assertEqual((code, doc["ok"], doc["tenant"], doc["missing"]), (0, True, NEW, [str(tenant.payload_key(NEW))]))
            self.assertEqual(len(doc["next"]), 4)

            code, doc = self.call(root, "check")
            self.assertEqual((code, doc["ok"], doc["error"]["code"]), (1, False, "check-failed"))
            self.assertEqual(doc["error"]["message"], f"1 of {len(EXISTING) + 1} tenants miss a piece or differ from the reference; see proofs")
            self.assertEqual({(p["check"], p["tenant"], p["state"]) for p in doc["error"]["proofs"]}, {("tenant-pieces", NEW, "fail"), *(("tenant-pieces", name, "ok") for name in EXISTING)})

            (root / tenant.payload_key(NEW)).touch()
            self.assertEqual(self.call(root, "check")[0], 0)
            code, doc = self.call(root, "sync")
            self.assertEqual((code, doc["tenants"], doc["files"]), (0, OTHERS, []))
            code, doc = self.call(root, "sync", REFERENCE)
            self.assertEqual((code != 0, doc["error"]["code"]), (True, "not-found"))


if __name__ == "__main__":
    unittest.main()
