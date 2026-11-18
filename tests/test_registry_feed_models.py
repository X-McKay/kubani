"""Model release manifests in the catalog feed: the repository as committed, and small synthetic trees."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
import registry_feed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "vllm/vllm-openai:v1.0.0-aarch64"
DEPLOYMENT = "infrastructure/gitops/apps/vllm/deployment.yaml"
CONFIG = "infrastructure/gitops/apps/vllm/model-config.yaml"
MANIFEST = "infrastructure/registry/models/main/Qwen-Main.yaml"


def write_docs(root: Path, rel: str, docs) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump_all(docs if isinstance(docs, list) else [docs], sort_keys=False), encoding="utf-8")


def catalog(release: str | None = "Qwen-Main", **alias) -> dict:
    engine = {
        "name": "main",
        "namespace": "vllm",
        "owner": "platform",
        "description": "Main model engine",
        "source": "vllm-project/vllm",
        "workload": "vllm",
        "manifest": DEPLOYMENT,
        "container": "vllm",
        "servedNameFrom": {"configMap": "model-config", "key": "LLM_MODEL_NAME"},
        "backend": "llm-main",
    }
    if release is not None:
        engine["release"] = release
    return {
        "version": 1,
        "cluster": {"name": "kubani", "trustDomain": "cluster.local", "gateway": "http://gw", "fluxInventories": [{"namespace": "flux-system", "name": "apps"}]},
        "toolServers": [],
        "modelEngines": [engine],
        "aliases": [{"alias": "main", "engine": "main", **alias}],
    }


def deployment(image: str = IMAGE) -> dict:
    script = (
        'exec vllm serve "$LLM_MODEL_PATH" \\\n  --served-model-name "$LLM_MODEL_NAME" \\\n  --max-model-len "$LLM_MAX_MODEL_LEN" \\\n'
        "  --enable-auto-tool-choice \\\n  --tool-call-parser qwen3_xml \\\n  --enable-sleep-mode"
    )
    container = {"name": "vllm", "image": image, "envFrom": [{"configMapRef": {"name": "model-config"}}], "command": ["sh", "-c"], "args": [script]}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "vllm", "namespace": "vllm"},
        "spec": {"template": {"spec": {"containers": [container]}}},
    }


def model_config(served: str = "Qwen/Main") -> dict:
    data = {"LLM_MODEL_NAME": served, "LLM_MODEL_PATH": "org/main-weights", "LLM_MAX_MODEL_LEN": "4096"}
    return {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "model-config", "namespace": "vllm"}, "data": data}


def manifest(**changes) -> dict:
    doc = {
        "schemaVersion": 1,
        "engine": "main",
        "name": "Qwen-Main",
        "servedName": "Qwen/Main",
        "weights": {"source": "hf://org/main-weights", "revision": None, "files": None},
        "format": None,
        "quantisation": None,
        "engineImage": IMAGE,
        "serving": {"chatTemplate": None, "toolCallParser": "qwen3_xml", "contextLength": 4096},
        "offers": {"contextLength": None, "toolCalling": True, "structuredOutput": None, "embeddingSize": None},
        "evidence": {"benchmark": None, "changeRecord": None},
    }
    doc.update(changes)
    return doc


def build_tree(root: Path, *, with_manifest: bool = True, release: str | None = "Qwen-Main", **alias) -> None:
    write_docs(root, "infrastructure/registry/catalog.yaml", catalog(release, **alias))
    write_docs(root, DEPLOYMENT, deployment())
    write_docs(root, CONFIG, model_config())
    write_docs(
        root,
        "infrastructure/gitops/apps/ai-gateway/agents/backends.yaml",
        {
            "apiVersion": "agentgateway.dev/v1alpha1",
            "kind": "AgentgatewayBackend",
            "metadata": {"name": "agents-llm-main", "namespace": "ai-gateway"},
            "spec": {"ai": {"provider": {"openai": {"model": "Qwen/Main"}}}},
        },
    )
    write_docs(
        root,
        "infrastructure/gitops/infrastructure/kyverno/tenant-signers.yaml",
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "tenant-signers", "namespace": "kyverno"}, "data": {}},
    )
    if with_manifest:
        write_docs(root, MANIFEST, manifest())


class RepositoryModels(unittest.TestCase):
    def test_both_engines_state_their_release_and_the_feed_carries_the_manifests(self):
        feed = registry_feed.render(ROOT)
        self.assertEqual([(m["engine"], m["name"], m["servedName"]) for m in feed["modelReleases"]], [("fast", "Qwen-Qwen3.5-0.8B", "Qwen/Qwen3.5-0.8B"), ("main", "Qwen3.6-35B-A3B-NVFP4", "Qwen3.6-35B-A3B-NVFP4")])
        engines = {e["name"]: e for e in feed["modelEngines"]}
        self.assertEqual({n: e.get("release") for n, e in engines.items()}, {"main": "Qwen3.6-35B-A3B-NVFP4", "fast": "Qwen-Qwen3.5-0.8B", "embeddings": None})
        for m in feed["modelReleases"]:
            self.assertEqual(m["name"], registry_feed.release_slug(m["servedName"]))
            self.assertNotIn("cluster", m)


class SyntheticModels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        build_tree(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def assertRefused(self, *words: str) -> None:
        with self.assertRaises(ValueError) as caught:
            registry_feed.render(self.root)
        for word in words:
            self.assertIn(word, str(caught.exception))

    def test_a_valid_tree_renders_with_release_on_the_engine(self):
        feed = registry_feed.render(self.root)
        self.assertEqual(feed["modelEngines"][0]["release"], "Qwen-Main")
        self.assertEqual([m["name"] for m in feed["modelReleases"]], ["Qwen-Main"])

    def test_a_manifest_that_links_out_of_the_repository_is_refused_unread(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "other.yaml"
            target.write_text("outsideKey: outside-value\n", encoding="utf-8")
            (self.root / "infrastructure/registry/models/main/Linked.yaml").symlink_to(target)
            with self.assertRaises(ValueError) as caught:
                registry_feed.render(self.root)
        self.assertIn("leaves the repository root", str(caught.exception))
        self.assertNotIn("outside", str(caught.exception))

    def test_a_changed_engine_image_without_a_new_manifest_fails_naming_the_engine(self):
        write_docs(self.root, DEPLOYMENT, deployment("vllm/vllm-openai:v2.0.0-aarch64"))
        self.assertRefused("'main'", "engineImage", "v2.0.0")

    def test_a_changed_served_name_without_a_new_manifest_fails_naming_the_engine(self):
        write_docs(self.root, CONFIG, model_config("Qwen/Renamed"))
        write_docs(
            self.root,
            "infrastructure/gitops/apps/ai-gateway/agents/backends.yaml",
            {"kind": "AgentgatewayBackend", "metadata": {"name": "agents-llm-main"}, "spec": {"ai": {"provider": {"openai": {"model": "Qwen/Renamed"}}}}},
        )
        self.assertRefused("'main'", "serves 'Qwen/Main'", "Qwen/Renamed")

    def test_a_manifest_in_the_wrong_engine_directory_fails(self):
        (self.root / MANIFEST).rename(self.root / "infrastructure/registry/models/Qwen-Main.yaml")
        self.assertRefused("<engine>/<name>.yaml")
        (self.root / "infrastructure/registry/models/Qwen-Main.yaml").unlink()
        write_docs(self.root, "infrastructure/registry/models/fast/Qwen-Main.yaml", manifest())
        self.assertRefused("engine 'main' must equal its directory 'fast'")

    def test_a_manifest_whose_name_is_not_its_file_name_fails(self):
        write_docs(self.root, MANIFEST, manifest(name="Other"))
        self.assertRefused("name 'Other'")

    def test_a_manifest_missing_a_required_key_fails(self):
        doc = manifest()
        del doc["offers"]
        write_docs(self.root, MANIFEST, doc)
        self.assertRefused("missing key offers")

    def test_a_release_naming_no_manifest_or_one_of_another_engine_fails(self):
        write_docs(self.root, "infrastructure/registry/catalog.yaml", catalog("Nope"))
        self.assertRefused("'main'", "names no manifest")
        (self.root / MANIFEST).unlink()
        write_docs(self.root, "infrastructure/registry/models/fast/Qwen-Main.yaml", manifest(engine="fast"))
        write_docs(self.root, "infrastructure/registry/catalog.yaml", catalog("Qwen-Main"))
        self.assertRefused("'main'", "manifest of engine 'fast'")

    def test_an_engine_with_no_release_renders_as_before(self):
        write_docs(self.root, "infrastructure/registry/catalog.yaml", catalog(None))
        engine = registry_feed.render(self.root)["modelEngines"][0]
        self.assertNotIn("release", engine)

    def test_a_tree_with_no_models_directory_renders_as_before(self):
        (self.root / MANIFEST).unlink()
        (self.root / MANIFEST).parent.rmdir()
        (self.root / MANIFEST).parent.parent.rmdir()
        write_docs(self.root, "infrastructure/registry/catalog.yaml", catalog(None))
        feed = registry_feed.render(self.root)
        self.assertEqual(feed["modelReleases"], [])
        self.assertNotIn("release", feed["modelEngines"][0])

    def test_an_alias_move_passes_through(self):
        self.assertNotIn("move", registry_feed.render(self.root)["aliases"][0])
        write_docs(self.root, "infrastructure/registry/catalog.yaml", catalog(move="mv-2026-11-20-a"))
        self.assertEqual(registry_feed.render(self.root)["aliases"][0]["move"], "mv-2026-11-20-a")


if __name__ == "__main__":
    unittest.main()
