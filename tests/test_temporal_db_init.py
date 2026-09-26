from __future__ import annotations

import json
import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
TEMPORAL = ROOT / "infrastructure/gitops/apps/temporal"


def render(path: Path) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def template_digest(job: dict) -> str:
    canonical = json.dumps(
        job["spec"]["template"], sort_keys=True, separators=(",", ":")
    )
    return sha256(canonical.encode()).hexdigest()


class TemporalDbInitContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jobs = [
            document
            for document in render(TEMPORAL)
            if document["kind"] == "Job"
            and document["metadata"].get("labels", {}).get("app.kubernetes.io/name")
            == "temporal-db-init"
        ]

    def test_exactly_one_db_init_job(self) -> None:
        self.assertEqual(len(self.jobs), 1)

    def test_name_is_bound_to_pod_template(self) -> None:
        # A definition change must produce a new name so Flux runs it once
        # and prunes the old Job; an unchanged definition must keep its name.
        job = self.jobs[0]
        digest = template_digest(job)
        self.assertEqual(
            job["metadata"]["name"],
            f"temporal-db-init-v1-{digest[:12]}",
            "pod template changed: rename the Job and update its digest annotation",
        )
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/db-init-digest"],
            f"sha256:{digest}",
        )

    def test_completed_job_is_retained(self) -> None:
        # A TTL deletes the finished Job, and Flux then re-creates and re-runs
        # it on every reconcile interval.
        self.assertNotIn("ttlSecondsAfterFinished", self.jobs[0]["spec"])

    def test_waits_for_postgresql_before_connecting(self) -> None:
        # New pods have connections refused until their egress rule is programmed.
        script = self.jobs[0]["spec"]["template"]["spec"]["containers"][0]["command"][2]
        self.assertLess(script.index("pg_isready"), script.index("psql -h"))


if __name__ == "__main__":
    unittest.main()
