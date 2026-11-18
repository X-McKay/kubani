"""The catalog feed renderer: offline, against the repository and against small synthetic trees."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
import registry_feed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FEED = registry_feed.FEED


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = registry_feed.main(argv)
    return code, json.loads(out.getvalue())


def write_docs(root: Path, rel: str, docs) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump_all(docs if isinstance(docs, list) else [docs], sort_keys=False), encoding="utf-8")


def synthetic_catalog() -> dict:
    return {
        "version": 1,
        "cluster": {
            "name": "kubani",
            "trustDomain": "cluster.local",
            "gateway": "http://ai.ai-gateway.svc.cluster.local",
            "fluxInventories": [{"namespace": "flux-system", "name": "apps"}],
        },
        "toolServers": [
            {
                "name": "kubernetes-mcp",
                "namespace": "mcp",
                "owner": "platform",
                "description": "Read-only Kubernetes tools",
                "source": "containers/kubernetes-mcp-server",
                "manifest": "infrastructure/gitops/apps/mcp/kubernetes-mcp.yaml",
                "container": "kubernetes-mcp",
                "backend": "kubernetes",
            }
        ],
        "modelEngines": [
            {
                "name": "main",
                "namespace": "vllm",
                "owner": "platform",
                "description": "Main model engine",
                "source": "vllm-project/vllm",
                "workload": "vllm",
                "servedNameFrom": {"configMap": "model-config", "key": "LLM_MODEL_NAME"},
                "backend": "llm-main",
            }
        ],
        "aliases": [{"alias": "main", "engine": "main"}],
    }


def deployment(name: str, namespace: str, container: str) -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {"template": {"spec": {"containers": [{"name": container, "image": "quay.io/example/server:v1@sha256:" + "a" * 64}]}}},
    }


def build_tree(root: Path) -> None:
    """The files the renderer reads, and nothing else: one valid tool server, one engine, one alias, no tenants."""
    write_docs(root, "infrastructure/registry/catalog.yaml", synthetic_catalog())
    write_docs(root, "infrastructure/gitops/apps/mcp/kubernetes-mcp.yaml", deployment("kubernetes-mcp", "mcp", "kubernetes-mcp"))
    write_docs(root, "infrastructure/mcp/backends/kubernetes.yaml", {"name": "kubernetes"})
    write_docs(
        root,
        "infrastructure/gitops/apps/vllm/model-config.yaml",
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "model-config", "namespace": "vllm"}, "data": {"LLM_MODEL_NAME": "Qwen-Main"}},
    )
    write_docs(
        root,
        "infrastructure/gitops/apps/ai-gateway/agents/backends.yaml",
        {
            "apiVersion": "agentgateway.dev/v1alpha1",
            "kind": "AgentgatewayBackend",
            "metadata": {"name": "agents-llm-main", "namespace": "ai-gateway"},
            "spec": {"ai": {"provider": {"openai": {"model": "Qwen-Main"}}}},
        },
    )
    write_docs(
        root,
        "infrastructure/gitops/infrastructure/kyverno/tenant-signers.yaml",
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "tenant-signers", "namespace": "kyverno"}, "data": {}},
    )


def revocation(rid: str, **changes) -> dict:
    doc = {
        "schemaVersion": 1,
        "id": rid,
        "kind": "agent",
        "item": "db-admin",
        "release": "db-admin-2026-11-20-1a2b3c4d",
        "reason": "security",
        "sessions": "cancel",
        "summary": "A test revocation.",
        "revokedBy": "al",
        "revokedAt": "2026-11-20T10:00:00Z",
    }
    doc.update(changes)
    return doc


class RepositoryFeed(unittest.TestCase):
    def setUp(self):
        self.feed = registry_feed.render(ROOT)

    def test_tool_servers(self):
        tools = {t["name"]: t for t in self.feed["toolServers"]}
        self.assertEqual(len(tools), 5)
        self.assertEqual({name for name, t in tools.items() if not t["registered"]}, {"github-mcp", "graphiti-mcp", "postgres-mcp"})
        self.assertEqual(tools["kubernetes-mcp"]["backend"], "kubernetes")
        self.assertEqual(tools["postgres-admin-mcp"]["backend"], "postgres-admin")
        self.assertIs(tools["postgres-admin-mcp"]["pinnedByDigest"], True)

    def test_model_engines_and_aliases(self):
        engines = {e["name"]: e for e in self.feed["modelEngines"]}
        self.assertEqual(len(engines), 3)
        self.assertIsNone(engines["embeddings"]["backend"])
        aliases = {a["alias"]: a["backend"] for a in self.feed["aliases"]}
        self.assertEqual(aliases, {"main": "llm-main", "fast": "llm-fast"})

    def test_tenant_and_trusted_repository(self):
        self.assertEqual([t["name"] for t in self.feed["tenants"]], ["tenant-test"])
        self.assertEqual(len(self.feed["trustedRepositories"]), 1)
        repo = self.feed["trustedRepositories"][0]
        tenant = self.feed["tenants"][0]
        self.assertEqual(repo["subjectRegExp"], tenant["policy"]["signer"]["subjectRegExp"])
        agents_dir = ROOT / "infrastructure/gitops/apps/agents/tenant-test"
        self.assertEqual(repo["agents"], sorted(p.name for p in agents_dir.iterdir() if p.is_dir()))

    def test_revocations_are_a_list(self):
        self.assertIsInstance(self.feed["revocations"], list)

    def test_render_is_deterministic_and_committed_file_is_current(self):
        self.assertEqual(registry_feed.feed_bytes(registry_feed.render(ROOT)), registry_feed.feed_bytes(self.feed))
        code, doc = run(["render", "--check"])
        self.assertEqual(code, 0)
        self.assertEqual(doc, {"ok": True, "status": "current"})


class SyntheticTree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        build_tree(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def assertFailure(self, error_code: str):
        status, doc = run(["--root", str(self.root), "render", "--check"])
        self.assertEqual(status, 1)
        self.assertEqual(doc["ok"], False)
        self.assertEqual(doc["error"]["code"], error_code)
        return doc

    def test_check_fails_when_feed_missing_or_different(self):
        self.assertFailure("check-failed")
        status, doc = run(["--root", str(self.root), "render", "--write"])
        self.assertEqual((status, doc["status"]), (0, "rendered"))
        self.assertEqual(run(["--root", str(self.root), "render", "--check"]), (0, {"ok": True, "status": "current"}))
        (self.root / FEED).write_text("{}\n", encoding="utf-8")
        self.assertFailure("check-failed")

    def test_tool_server_deployment_missing_from_manifest(self):
        write_docs(self.root, "infrastructure/gitops/apps/mcp/kubernetes-mcp.yaml", deployment("other-name", "mcp", "kubernetes-mcp"))
        self.assertFailure("validation-failed")

    def test_backend_file_named_by_no_tool_server(self):
        write_docs(self.root, "infrastructure/mcp/backends/orphan.yaml", {"name": "orphan"})
        self.assertFailure("validation-failed")

    def test_gateway_model_differs_from_served_name(self):
        write_docs(
            self.root,
            "infrastructure/gitops/apps/ai-gateway/agents/backends.yaml",
            {
                "apiVersion": "agentgateway.dev/v1alpha1",
                "kind": "AgentgatewayBackend",
                "metadata": {"name": "agents-llm-main", "namespace": "ai-gateway"},
                "spec": {"ai": {"provider": {"openai": {"model": "Renamed-Model"}}}},
            },
        )
        self.assertFailure("validation-failed")

    def test_alias_naming_unknown_engine(self):
        catalog = synthetic_catalog()
        catalog["aliases"] = [{"alias": "main", "engine": "nonexistent"}]
        write_docs(self.root, "infrastructure/registry/catalog.yaml", catalog)
        self.assertFailure("validation-failed")

    def test_synthetic_tree_renders_when_valid(self):
        feed = registry_feed.render(self.root)
        self.assertEqual([t["name"] for t in feed["toolServers"]], ["kubernetes-mcp"])
        self.assertEqual(feed["aliases"], [{"cluster": "kubani", "alias": "main", "engine": "main", "backend": "llm-main"}])
        self.assertEqual(feed["tenants"], [])


if __name__ == "__main__":
    unittest.main()

    def test_no_revocations_directory_gives_an_empty_list(self):
        self.assertEqual(registry_feed.render(self.root)["revocations"], [])

    def test_revocations_come_in_id_order_with_the_text_written(self):
        for rid in ("2026-11-21-b", "2026-11-20-a"):
            write_docs(self.root, f"infrastructure/registry/revocations/{rid}.yaml", revocation(rid))
        found = registry_feed.render(self.root)["revocations"]
        self.assertEqual([r["id"] for r in found], ["2026-11-20-a", "2026-11-21-b"])
        self.assertEqual(found[0]["revokedAt"], "2026-11-20T10:00:00Z")

    def test_revocation_id_must_equal_the_file_name(self):
        write_docs(self.root, "infrastructure/registry/revocations/2026-11-20-a.yaml", revocation("other"))
        self.assertFailure("validation-failed")

    def test_revocation_with_a_missing_key_is_refused(self):
        doc = revocation("2026-11-20-a")
        del doc["release"]
        write_docs(self.root, "infrastructure/registry/revocations/2026-11-20-a.yaml", doc)
        self.assertFailure("validation-failed")
