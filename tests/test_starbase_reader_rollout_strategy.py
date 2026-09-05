from pathlib import Path
import subprocess
import unittest

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
READER_OVERLAY = (
    REPOSITORY_ROOT
    / "infrastructure/gitops/apps/starbase-phase10-autonomous-reader-prepared"
)
RECREATE_WORKLOADS = {
    "starbase-core",
    "starbase-preview-fixture",
}
NO_SURGE_WORKLOADS = {
    "starbase-github-connector",
    "starbase-kubernetes-connector",
}


class ReaderRolloutStrategyTests(unittest.TestCase):
    def test_reader_rollout_strategies_are_api_safe_and_quota_bounded(self) -> None:
        rendered = subprocess.run(
            ["kubectl", "kustomize", str(READER_OVERLAY)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        documents = list(yaml.safe_load_all(rendered))
        deployments = {
            document["metadata"]["name"]: document
            for document in documents
            if document and document.get("kind") == "Deployment"
        }

        self.assertLessEqual(RECREATE_WORKLOADS | NO_SURGE_WORKLOADS, deployments.keys())
        for workload in RECREATE_WORKLOADS:
            self.assertEqual(
                deployments[workload]["spec"]["strategy"],
                {"type": "Recreate"},
            )
        for workload in NO_SURGE_WORKLOADS:
            self.assertEqual(
                deployments[workload]["spec"]["strategy"],
                {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1},
                },
            )
