"""Retirement must remove the newer application without pruning Lite support."""
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = {
    ("Namespace", "", "starbase-system"),
    ("Secret", "starbase-system", "starbase-ghcr-pull"),
    ("ResourceQuota", "starbase-system", "starbase-system"),
    ("LimitRange", "starbase-system", "starbase-system"),
    ("NetworkPolicy", "starbase-system", "default-deny"),
    ("NetworkPolicy", "starbase-system", "allow-dns"),
}


class DecommissionTests(unittest.TestCase):
    def test_controllers_retain_only_exact_lite_support(self):
        for controller, expected in (("starbase-foundation", SUPPORT), ("starbase-dojo", set())):
            flux = yaml.safe_load(
                (ROOT / f"infrastructure/gitops/flux-system/{controller}-kustomization.yaml").read_text()
            )
            self.assertTrue(flux["spec"]["prune"])
            self.assertFalse(flux["spec"].get("force", False))
            self.assertFalse(flux["spec"].get("suspend", False))
            result = subprocess.run(
                ["kubectl", "kustomize", str(ROOT / flux["spec"]["path"])],
                capture_output=True, text=True, check=True,
            )
            documents = [item for item in yaml.safe_load_all(result.stdout) if item]
            identities = {
                (item["kind"], item["metadata"].get("namespace", ""), item["metadata"]["name"])
                for item in documents
            }
            self.assertEqual(identities, expected)
            self.assertEqual(len(documents), len(expected))
            for item in documents:
                if item["kind"] == "Secret":
                    self.assertIn("sops", item)
                    self.assertNotIn("stringData", item)
                    self.assertTrue(all(value.startswith("ENC[") for value in item["data"].values()))

    def test_no_newer_starbase_overlay_or_promotion_tool_remains(self):
        apps = ROOT / "infrastructure/gitops/apps"
        self.assertEqual(list(apps.glob("starbase-phase*")), [])
        self.assertFalse((apps / "starbase").exists())
        self.assertFalse((ROOT / "infrastructure/scripts/starbase_promotion.py").exists())


if __name__ == "__main__":
    unittest.main()
