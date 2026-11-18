"""The feed's `configDigest` and `contract` keys on a synthetic tree (contract section 2.2)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
import registry_feed  # noqa: E402
from mcp_registry import contract  # noqa: E402
from test_registry_feed import build_tree, deployment, write_docs  # noqa: E402

MANIFEST = "infrastructure/gitops/apps/mcp/kubernetes-mcp.yaml"
FILE = "infrastructure/mcp/contracts/kubernetes-mcp.json"
IMAGE = "quay.io/example/server:v1@sha256:" + "a" * 64


class FeedContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        build_tree(self.root)
        self.container = {"name": "kubernetes-mcp", "image": IMAGE, "args": ["--read-only"]}
        write_docs(self.root, MANIFEST, deployment("kubernetes-mcp", "mcp", "kubernetes-mcp") | {"spec": {"template": {"spec": {"containers": [self.container]}}}})

    def contract_file(self, **changes):
        document = {
            "schemaVersion": 1,
            "server": "kubernetes-mcp",
            "backend": "kubernetes",
            "image": IMAGE,
            "configDigest": contract.config_digest(self.container),
            "tools": [{"name": "pods_list", "description": "d", "effect": "remote_read", "inputSchema": {"type": "object"}, "outputSchema": None}],
        } | changes
        (self.root / FILE).parent.mkdir(parents=True, exist_ok=True)
        (self.root / FILE).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        return document

    def tool_server(self):
        return registry_feed.render(self.root)["toolServers"][0]

    def test_feed_carries_the_digest_and_the_contract(self):
        document = self.contract_file()
        entry = self.tool_server()
        self.assertEqual(entry["configDigest"], contract.config_digest(self.container))
        self.assertEqual(entry["contract"], document)

    def test_without_a_file_the_contract_is_null_and_the_digest_is_still_there(self):
        entry = self.tool_server()
        self.assertIsNone(entry["contract"])
        self.assertTrue(entry["configDigest"].startswith("sha256:"))

    def test_a_flag_changed_without_a_new_capture_does_not_render(self):
        self.contract_file()
        self.container["args"] = ["--read-only", "--new"]
        write_docs(self.root, MANIFEST, deployment("kubernetes-mcp", "mcp", "kubernetes-mcp") | {"spec": {"template": {"spec": {"containers": [self.container]}}}})
        with self.assertRaisesRegex(ValueError, "kubernetes-mcp.*configDigest"):
            registry_feed.render(self.root)

    def test_an_image_with_another_digest_does_not_render(self):
        self.contract_file(image="quay.io/example/server:v1@sha256:" + "b" * 64)
        with self.assertRaisesRegex(ValueError, "kubernetes-mcp.*captured from image"):
            registry_feed.render(self.root)

    def test_another_server_or_backend_does_not_render(self):
        self.contract_file(server="graphiti-mcp")
        with self.assertRaisesRegex(ValueError, "kubernetes-mcp.*contract of server"):
            registry_feed.render(self.root)
        self.contract_file(backend=None)
        with self.assertRaisesRegex(ValueError, "kubernetes-mcp.*names backend"):
            registry_feed.render(self.root)


if __name__ == "__main__":
    unittest.main()
