"""Offline registry contracts: fail closed and preserve the migrated workload."""

import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infrastructure/scripts/ops"))


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "infrastructure", self.root / "infrastructure")
        self.model = importlib.import_module("mcp_registry.model")
        self.render = importlib.import_module("mcp_registry.render")
        self.check = importlib.import_module("mcp_registry.check")
        self.path = self.root / "infrastructure/mcp/backends/postgres-admin.yaml"

    def edit(self, mutate):
        value = yaml.safe_load(self.path.read_text())
        mutate(value)
        self.path.write_text(yaml.safe_dump(value))

    def test_baseline_and_determinism(self):
        entries = self.model.load_registry(self.root)
        a = self.render.render(self.root, entries)
        self.assertEqual(a, self.render.render(self.root, entries))
        docs = self.render.objects(self.root, "postgres-admin")
        baseline = json.loads(
            (ROOT / "infrastructure/mcp/baseline/postgres-admin.json").read_text()
        )
        for expected in baseline:
            actual = next(
                d
                for d in docs
                if d["kind"] == expected["kind"]
                and d["metadata"] == expected["metadata"]
            )
            self.assertEqual(actual, expected)
        self.assertEqual(
            self.model.descriptor(entries[0]),
            json.loads(
                (ROOT / "infrastructure/mcp/baseline/descriptor.json").read_text()
            ),
        )

    def test_reference_and_digest_formats_are_explicit(self):
        import hashlib

        entry = self.model.load_registry(self.root)[0]
        env = entry["workload"]["secretEnv"][0]
        self.assertEqual(
            env["secretKeyRef"], {"name": "postgres-admin-mcp", "key": "DATABASE_URI"}
        )
        self.assertNotIn("secret", env)
        self.assertEqual(
            entry["bootstrap"]["sqlSha256"],
            "sha256:"
            + hashlib.sha256(
                (self.root / entry["bootstrap"]["sql"]).read_bytes()
            ).hexdigest(),
        )
        inventory = json.loads(
            (self.root / "infrastructure/mcp/inventory.json").read_text()
        )
        for relative, digest in inventory["files"].items():
            self.assertEqual(
                digest,
                "sha256:"
                + hashlib.sha256((self.root / relative).read_bytes()).hexdigest(),
            )

    def test_strict_invalid_definitions(self):
        original = self.path.read_text()
        changes = [
            lambda d: d.update(version=2),
            lambda d: d.update(profile="stdio"),
            lambda d: d.update(unknown=True),
            lambda d: d.pop("authorization"),
            lambda d: d["authorization"].update(tools=["*"]),
            lambda d: d["workload"].update(port=True),
            lambda d: d["workload"].update(image="latest"),
            lambda d: d["bootstrap"].update(sqlSha256="sha256:" + "0" * 64),
            lambda d: d["bootstrap"].update(sqlSha256="0" * 64),
            lambda d: d["workload"]["secretEnv"][0].update(secret="legacy-field"),
            lambda d: d["workload"]["secretEnv"][0]["secretKeyRef"].update(
                value="not-a-reference"
            ),
            lambda d: d["bootstrap"].update(revision="v2"),
            lambda d: d["secrets"].append("../unsafe.yaml"),
        ]
        for change in changes:
            with self.subTest(change=change):
                self.path.write_text(original)
                self.edit(change)
                with self.assertRaises(ValueError):
                    self.model.load_registry(self.root)
        self.path.write_text(original + "\nname: duplicate\n")
        with self.assertRaises(ValueError):
            self.model.load_registry(self.root)

    def test_role_must_be_namespaced_to_its_backend(self):
        self.edit(lambda d: d["authorization"].update(role="agent-role-other-read"))
        with self.assertRaises(ValueError):
            self.model.load_registry(self.root)

    def test_duplicate_name_and_inventory_removal(self):
        other = self.path.with_name("duplicate.yaml")
        other.write_text(self.path.read_text())
        with self.assertRaises(ValueError):
            self.model.load_registry(self.root)
        other.unlink()
        self.render.write(self.root)
        self.path.unlink()
        with self.assertRaises(ValueError):
            self.render.write(self.root)

    def test_incremental_supported_backend_receives_every_layer(self):
        before = self.render.objects(self.root, "postgres-admin")
        original = self.model.descriptor(self.model.load_registry(self.root)[0])
        entry = yaml.safe_load(self.model.scaffold("example"))
        entry["workload"].update(
            image="example/server@sha256:" + "a" * 64,
            args=["--transport=sse"],
            port=9000,
        )
        entry["upstreams"] = [
            {
                "name": "catalog",
                "namespace": "database",
                "selector": {"app": "catalog"},
                "port": 7777,
            }
        ]
        entry["authorization"].update(role="agent-role-example-read", tools=["inspect"])
        self.path.with_name("example.yaml").write_text(yaml.safe_dump(entry))
        self.render.write(self.root)
        self.assertEqual(
            [
                d
                for d in before
                if d["metadata"]["name"] not in ("agents-jwt", "agents-only")
            ],
            [
                d
                for d in self.render.objects(self.root, "postgres-admin")
                if d["metadata"]["name"] not in ("agents-jwt", "agents-only")
            ],
        )
        entries = self.model.load_registry(self.root)
        self.assertEqual(
            original,
            self.model.descriptor(
                next(e for e in entries if e["name"] == "postgres-admin")
            ),
        )
        docs = self.render.objects(self.root, "example")
        kinds = {d["kind"] for d in docs}
        self.assertTrue(
            {
                "Deployment",
                "Service",
                "HTTPRoute",
                "AgentgatewayBackend",
                "AgentgatewayPolicy",
                "NetworkPolicy",
            }
            <= kinds
        )
        route = next(d for d in docs if d["kind"] == "HTTPRoute")
        self.assertEqual(
            route["spec"]["rules"][0]["matches"][0]["path"]["value"], "/example/mcp"
        )
        policies = [d for d in docs if d["kind"] == "AgentgatewayPolicy"]
        self.assertTrue(
            any(
                d["spec"].get("traffic", {}).get("jwtAuthentication", {}).get("mode")
                == "Strict"
                for d in policies
            )
        )
        self.assertTrue(
            any("authorization" in d["spec"].get("traffic", {}) for d in policies)
        )
        ext = next(
            d["spec"]["traffic"]["extAuth"]
            for d in policies
            if "extAuth" in d["spec"].get("traffic", {})
        )
        self.assertEqual(ext["failureMode"], "FailClosed")
        self.assertEqual(ext["grpc"]["contextExtensions"]["backend"], "example")
        self.assertIn("inspect", str(policies))
        networks = [d for d in docs if d["kind"] == "NetworkPolicy"]
        for name in (
            "allow-example-mcp-catalog-egress",
            "allow-example-mcp-catalog",
            "allow-agents-example-mcp-ingress",
            "allow-agents-example-mcp-egress",
        ):
            self.assertTrue(any(d["metadata"]["name"] == name for d in networks))
        identity = self.model.descriptor(
            next(e for e in entries if e["name"] == "example")
        )
        self.assertEqual(
            identity["resource"]["clientId"], "https://mcp.almckay.io/example/mcp"
        )
        self.assertEqual(identity["scope"]["name"], "mcp:example")
        self.assertEqual(identity["role"]["name"], "agent-role-example-read")
        self.assertEqual(identity["requester"], "agent-policy-service")
        self.assertEqual(identity["attachment"], "optional")
        self.assertEqual(self.check.check(self.root), [])

    def test_stale_output_and_symlink_refused_before_writing(self):
        self.render.write(self.root)
        output = (
            self.root
            / "infrastructure/gitops/apps/mcp/registry-generated/backends.yaml"
        )
        output.write_text("stale")
        self.assertTrue(self.check.check(self.root))
        output.unlink()
        outside = self.root / "untouched"
        outside.write_text("safe")
        output.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.render.write(self.root)
        self.assertEqual(outside.read_text(), "safe")

    def test_legacy_collision_and_additive_network_overlap_fail_closed(self):
        self.edit(
            lambda d: (
                d.update(name="postgres"),
                d["authorization"].update(role="agent-role-postgres-read"),
            )
        )
        self.path.rename(self.path.with_name("postgres.yaml"))
        with self.assertRaises(ValueError):
            self.render.write(self.root)

    def test_unexplained_broad_policy_rejected(self):
        p = self.root / "infrastructure/gitops/apps/mcp/netpol.yaml"
        with p.open("a") as f:
            yaml.safe_dump_all(
                [
                    {
                        "apiVersion": "networking.k8s.io/v1",
                        "kind": "NetworkPolicy",
                        "metadata": {"name": "oops", "namespace": "mcp"},
                        "spec": {
                            "podSelector": {},
                            "policyTypes": ["Egress"],
                            "egress": [{}],
                        },
                    }
                ],
                f,
                explicit_start=True,
            )
        with self.assertRaises(ValueError):
            self.render.write(self.root)

    def test_changed_sql_hash_cannot_reuse_completed_revision(self):
        self.render.write(self.root)
        sql = self.root / "infrastructure/gitops/apps/mcp/postgres-admin-monitor.sql"
        sql.write_text(sql.read_text() + "\n-- reviewed change\n")
        import hashlib

        self.edit(
            lambda d: d["bootstrap"].update(
                sqlSha256="sha256:" + hashlib.sha256(sql.read_bytes()).hexdigest()
            )
        )
        with self.assertRaises(ValueError):
            self.render.write(self.root)

    def test_preexisting_unowned_output_cannot_be_overwritten(self):
        inventory = self.root / "infrastructure/mcp/inventory.json"
        inventory.unlink(missing_ok=True)
        with self.assertRaises(ValueError):
            self.render.write(self.root)

    def test_effective_policy_patch_cannot_widen_access(self):
        p = self.root / "infrastructure/gitops/apps/mcp/kustomization.yaml"
        with p.open("a") as f:
            f.write(
                "  - target:\n      kind: NetworkPolicy\n      name: allow-dns-egress\n    patch: |-\n      - op: replace\n        path: /spec/egress\n        value: [{}]\n"
            )
        self.assertTrue(self.check.check(self.root))
        inventory = (self.root / "infrastructure/mcp/inventory.json").read_bytes()
        with self.assertRaises(ValueError):
            self.render.write(self.root)
        self.assertEqual(
            (self.root / "infrastructure/mcp/inventory.json").read_bytes(), inventory
        )

    def test_included_unexpected_policy_rejected_regardless_of_extension(self):
        directory = self.root / "infrastructure/gitops/apps/mcp"
        kustomization = directory / "kustomization.yaml"
        original = kustomization.read_text()
        policy = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": "unexpected-allow-all", "namespace": "mcp"},
            "spec": {
                "podSelector": {},
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [{}],
                "egress": [{}],
            },
        }
        for filename in ("unexpected.yml", "unexpected-policy"):
            with self.subTest(filename=filename):
                resource = directory / filename
                resource.write_text(yaml.safe_dump(policy))
                definition = yaml.safe_load(original)
                definition["resources"].append(filename)
                kustomization.write_text(yaml.safe_dump(definition))
                findings = self.check.check(self.root)
                self.assertTrue(findings, "included additive allow-all policy accepted")
                self.assertIn("unexpected-allow-all", str(findings))
                inventory = (
                    self.root / "infrastructure/mcp/inventory.json"
                ).read_bytes()
                with self.assertRaises(ValueError):
                    self.render.write(self.root)
                self.assertEqual(
                    (self.root / "infrastructure/mcp/inventory.json").read_bytes(),
                    inventory,
                )
                resource.unlink()
                kustomization.write_text(original)

    def test_removed_kustomization_inclusion_is_detected(self):
        p = self.root / "infrastructure/gitops/apps/mcp/kustomization.yaml"
        p.write_text(p.read_text().replace("  - registry-generated/\n", ""))
        self.assertTrue(self.check.check(self.root))

    def test_unsafe_inventory_path_is_rejected(self):
        p = self.root / "infrastructure/mcp/inventory.json"
        inventory = json.loads(p.read_text())
        inventory["files"]["../escape"] = "0" * 64
        p.write_text(json.dumps(inventory))
        with self.assertRaises(ValueError):
            self.render.write(self.root)

    def test_effective_platform_dependencies_are_required(self):
        paths = [
            (
                "infrastructure/gitops/apps/keycloak/kustomization.yaml",
                "  - referencegrant.yaml\n",
            ),
            (
                "infrastructure/gitops/apps/agent-platform/kustomization.yaml",
                "  - referencegrant.yaml\n",
            ),
            (
                "infrastructure/gitops/apps/agent-platform/workloads/kustomization.yaml",
                "  - agent-policy-service.yaml\n",
            ),
        ]
        for relative, line in paths:
            with self.subTest(path=relative):
                p = self.root / relative
                before = p.read_text()
                self.assertIn(line, before)
                p.write_text(before.replace(line, ""))
                self.assertTrue(self.check.check(self.root))
                p.write_text(before)
        p = self.root / "infrastructure/gitops/apps/ai-gateway/agents/gateway.yaml"
        p.write_text(
            p.read_text().replace("name: agents-https", "name: missing-listener")
        )
        self.assertTrue(self.check.check(self.root))


if __name__ == "__main__":
    unittest.main()
