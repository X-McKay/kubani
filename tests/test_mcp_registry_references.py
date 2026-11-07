"""Bounded public references preserve existing Kubernetes MCP ownership."""

import copy
import importlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infrastructure/scripts/ops"))
model = importlib.import_module("mcp_registry.model")
render = importlib.import_module("mcp_registry.render")


class ReferencesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "infrastructure", self.root / "infrastructure")
        self.entry = yaml.safe_load(
            (self.root / "infrastructure/mcp/backends/kubernetes.yaml").read_text()
        )

    def test_exact_references_and_external_projection(self):
        model.validate(self.entry, self.root)
        objects = model.referenced_objects(self.root, self.entry)
        self.assertEqual(len(objects), 10)
        self.assertEqual(
            {o["kind"] for o in objects},
            {
                "ServiceAccount",
                "ClusterRoleBinding",
                "ConfigMap",
                "Deployment",
                "Service",
                "NetworkPolicy",
                "AgentgatewayBackend",
                "HTTPRoute",
                "AgentgatewayPolicy",
            },
        )
        external = model.referenced_objects(self.root, self.entry, external=True)
        self.assertEqual(len(external), 1)
        self.assertEqual(
            set(external[0]),
            {"apiVersion", "kind", "metadata", "rules", "aggregationRule"},
        )
        self.assertEqual(external[0]["metadata"], {"name": "view"})
        self.assertEqual(
            model.descriptor(self.entry)["scope"]["name"], "mcp:kubernetes"
        )

    def test_changed_sources_and_extra_workload_documents_fail(self):
        for ref in self.entry["references"]:
            with self.subTest(ref=ref["name"]):
                path = self.root / ref["path"]
                original = path.read_text()
                docs = list(yaml.safe_load_all(original))
                obj = next(
                    o
                    for o in docs
                    if o
                    and o.get("kind") == ref["kind"]
                    and o.get("metadata", {}).get("name") == ref["name"]
                )
                obj["metadata"]["annotations"] = {"unexpected": "changed"}
                path.write_text(yaml.safe_dump_all(docs))
                with self.assertRaises(ValueError):
                    model.validate(self.entry, self.root)
                path.write_text(original)
        path = self.root / self.entry["references"][0]["path"]
        path.write_text(
            path.read_text()
            + "\n---\napiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: extra\n  namespace: mcp\n"
        )
        with self.assertRaises(ValueError):
            model.validate(self.entry, self.root)

    def test_invalid_reference_and_profile_fields_fail(self):
        for mutate in [
            lambda e: e["references"].append(copy.deepcopy(e["references"][0])),
            lambda e: e["references"].pop(),
            lambda e: e["references"][0].update(path="infrastructure/../escape.yaml"),
            lambda e: e["references"][0].update(canonicalSHA256="sha256:no"),
            lambda e: e.update(bootstrap={}),
            lambda e: e.update(provision={}),
            lambda e: e["workload"].update(protocol="SSE"),
        ]:
            entry = copy.deepcopy(self.entry)
            mutate(entry)
            with self.assertRaises(ValueError):
                model.validate(entry, self.root)

    def test_symlink_and_external_snapshot_hash_fail(self):
        ref = self.entry["externalReferences"][0]
        path = self.root / ref["path"]
        original = path.read_text()
        path.write_text(original.replace("certificates", "secrets"))
        with self.assertRaises(ValueError):
            model.validate(self.entry, self.root)
        path.unlink()
        path.symlink_to(ROOT / ref["path"])
        with self.assertRaises(ValueError):
            model.validate(self.entry, self.root)

    def test_rehashed_security_broadening_fails(self):
        ref = next(r for r in self.entry["references"] if r["kind"] == "ConfigMap")
        path = self.root / ref["path"]
        docs = list(yaml.safe_load_all(path.read_text()))
        obj = next(o for o in docs if o and o["kind"] == "ConfigMap")
        obj["data"]["config.toml"] = obj["data"]["config.toml"].replace(
            "read_only = true", "read_only = false"
        )
        ref["canonicalSHA256"] = model.canonical_sha256(obj)
        path.write_text(yaml.safe_dump_all(docs))
        with self.assertRaises(ValueError):
            model.validate(self.entry, self.root)

    def test_render_retains_runtime_bytes_and_referenced_status(self):
        entries = model.load_registry(self.root)
        output = render.render(self.root, entries)
        for path, data in output.items():
            if path.endswith(
                (
                    ".yaml",
                    "-targets.json",
                    "human-exclusions.json",
                    "postgres-admin.json",
                )
            ):
                self.assertEqual(data, (self.root / path).read_bytes(), path)
        self.assertEqual(render._backend_objects(self.root, self.entry), [])
        expected = render.objects(self.root, "kubernetes")
        ids = [render.identity(o) for o in expected]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(("rbac.authorization.k8s.io/v1", "ClusterRole", "", "view"), ids)
        inventory = json.loads(output[render.INVENTORY])
        self.assertFalse(
            any(o["name"] == "kubernetes-mcp" for o in inventory["objects"])
        )
        self.assertEqual(
            inventory["backends"]["kubernetes"]["references"], self.entry["references"]
        )

    def test_effective_objects_cannot_be_changed_omitted_or_duplicated(self):
        entries = model.load_registry(self.root)
        docs = render.build(self.root)
        render.validate_effective(self.root, entries, docs)
        selected = {
            render.identity(o) for o in model.referenced_objects(self.root, self.entry)
        }
        for identity in selected:
            with self.subTest(identity=identity):
                omitted = [o for o in docs if render.identity(o) != identity]
                with self.assertRaises(ValueError):
                    render.validate_effective(self.root, entries, omitted)
                changed = copy.deepcopy(docs)
                obj = next(o for o in changed if render.identity(o) == identity)
                obj["metadata"]["annotations"] = {"changed": "true"}
                with self.assertRaises(ValueError):
                    render.validate_effective(self.root, entries, changed)
        with self.assertRaises(ValueError):
            render.validate_effective(
                self.root, entries, docs + [copy.deepcopy(docs[0])]
            )

    def test_rehashed_binding_transport_and_tool_broadenings_fail(self):
        cases = [
            ("ClusterRoleBinding", lambda o: o["roleRef"].update(name="cluster-admin")),
            (
                "AgentgatewayBackend",
                lambda o: o["spec"]["mcp"]["targets"][0]["static"].update(
                    protocol="SSE"
                ),
            ),
            (
                "AgentgatewayPolicy",
                lambda o: o["spec"]["backend"]["mcp"]["authorization"]["policy"].update(
                    matchExpressions=["true"]
                ),
            ),
        ]
        for kind, mutate in cases:
            with self.subTest(kind=kind):
                entry = copy.deepcopy(self.entry)
                ref = next(
                    r
                    for r in entry["references"]
                    if r["kind"] == kind
                    and (kind != "AgentgatewayPolicy" or r["name"].endswith("-tools"))
                )
                path = self.root / ref["path"]
                original = path.read_text()
                docs = list(yaml.safe_load_all(original))
                obj = next(
                    o
                    for o in docs
                    if o and o["kind"] == kind and o["metadata"]["name"] == ref["name"]
                )
                mutate(obj)
                ref["canonicalSHA256"] = model.canonical_sha256(obj)
                path.write_text(yaml.safe_dump_all(docs))
                with self.assertRaises(ValueError):
                    model.validate(entry, self.root)
                path.write_text(original)

    def test_duplicate_selected_document_fails(self):
        ref = self.entry["references"][0]
        path = self.root / ref["path"]
        obj = model.referenced_objects(self.root, self.entry)[0]
        path.write_text(
            path.read_text() + "\n" + yaml.safe_dump_all([obj], explicit_start=True)
        )
        with self.assertRaises(ValueError):
            model.validate(self.entry, self.root)
