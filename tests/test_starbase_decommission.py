"""Guard the first, non-data-destructive decommission stage."""
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class DecommissionTests(unittest.TestCase):
    def test_live_targets_are_quiescent_and_keep_owned_data(self):
        documents = []
        for name in ("starbase-foundation", "starbase-dojo"):
            flux = yaml.safe_load(
                (ROOT / f"infrastructure/gitops/flux-system/{name}-kustomization.yaml").read_text()
            )
            result = subprocess.run(
                ["kubectl", "kustomize", str(ROOT / flux["spec"]["path"])],
                capture_output=True, text=True, check=True,
            )
            documents.extend(item for item in yaml.safe_load_all(result.stdout) if item)
        deployments = [item for item in documents if item["kind"] == "Deployment"]
        self.assertEqual(len(deployments), 6)
        for deployment in deployments:
            self.assertEqual(deployment["spec"].get("replicas", 1), 0, deployment["metadata"]["name"])
        runtime = next(item for item in documents if item["metadata"]["name"] == "starbase-runtime")
        for key in ("STARBASE_BOUNTY_AUTOMATION_ENABLED", "STARBASE_BOUNTY_AUTOMATION_DISPATCH_ENABLED", "STARBASE_MUTATION_ENABLED"):
            self.assertEqual(runtime["data"][key], "false")
        names = {item["metadata"]["name"] for item in documents}
        self.assertIn("starbase-core-runtime", names)
        self.assertIn("starbase-dojo-runtime", names)
        self.assertNotIn("starbase-autonomous-route-fixture-v2", names)


if __name__ == "__main__":
    unittest.main()
