"""model_release.py new: the manifest of a new release, from the committed state of an engine."""

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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_release  # noqa: E402
import registry_feed  # noqa: E402
from test_registry_feed_models import IMAGE, MANIFEST, build_tree, catalog, write_docs  # noqa: E402


def run(root: Path, *argv: str):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = model_release.main(["--root", str(root), "new", *argv])
        except SystemExit as exc:
            code = exc.code
    return code, json.loads(out.getvalue())


class New(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        build_tree(self.root, with_manifest=False, release=None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_a_manifest_from_the_tree_that_renders_once_the_catalog_names_it(self):
        code, doc = run(self.root, "--engine", "main", "--name", "Qwen-Main")
        self.assertEqual((code, doc["ok"], doc["file"]), (0, True, MANIFEST))
        written = yaml.safe_load((self.root / MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(written["engineImage"], IMAGE)
        self.assertEqual(written["servedName"], "Qwen/Main")
        self.assertEqual(written["weights"], {"source": "hf://org/main-weights", "revision": None, "files": None})
        self.assertEqual(written["serving"], {"chatTemplate": None, "toolCallParser": "qwen3_xml", "contextLength": 4096})
        self.assertIs(written["offers"]["toolCalling"], True)
        self.assertTrue(any("just agent alias plan" in step for step in doc["next"]))
        write_docs(self.root, "infrastructure/registry/catalog.yaml", catalog("Qwen-Main"))
        self.assertEqual([m["name"] for m in registry_feed.render(self.root)["modelReleases"]], ["Qwen-Main"])

    def test_operator_statements_are_written(self):
        (self.root / "evidence.json").write_text("{}", encoding="utf-8")
        code, _ = run(self.root, "--engine", "main", "--name", "Qwen-Main", "--weights-revision", "abc123", "--benchmark", "evidence.json", "--tool-calling", "false")
        self.assertEqual(code, 0)
        written = yaml.safe_load((self.root / MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(written["weights"]["revision"], "abc123")
        self.assertEqual(written["evidence"]["benchmark"], "evidence.json")
        self.assertIs(written["offers"]["toolCalling"], False)

    def test_refuses_to_overwrite_and_leaves_the_file_alone(self):
        self.assertEqual(run(self.root, "--engine", "main", "--name", "Qwen-Main")[0], 0)
        before = (self.root / MANIFEST).read_text(encoding="utf-8")
        code, doc = run(self.root, "--engine", "main", "--name", "Qwen-Main", "--weights-revision", "other")
        self.assertEqual((code, doc["error"]["code"]), (1, "conflict"))
        self.assertEqual((self.root / MANIFEST).read_text(encoding="utf-8"), before)

    def test_refuses_a_name_that_is_not_its_own_slug_and_an_engine_without_a_manifest(self):
        code, doc = run(self.root, "--engine", "main", "--name", "Qwen/Main")
        self.assertEqual((code, doc["error"]["code"]), (1, "validation-failed"))
        code, doc = run(self.root, "--engine", "nope", "--name", "x")
        self.assertEqual((code, doc["error"]["code"]), (1, "not-found"))
        self.assertFalse((self.root / "infrastructure/registry/models").exists())


if __name__ == "__main__":
    unittest.main()
