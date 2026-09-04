from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

import yaml

from infrastructure.scripts import starbase_promotion


ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "infrastructure/gitops/apps/starbase-phase5-preview"
ROLLBACK = ROOT / "infrastructure/gitops/apps/starbase-phase5-rc4-runtime-rollback"
FOUNDATION_FLUX = (
    ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
)

RC4_IMAGES = {
    ("Deployment", "starbase-system", "starbase-core", "core"): (
        "ghcr.io/x-mckay/starbase/core@"
        "sha256:61a0fe54fd5903f5afb9bbae254c794e590444611fdf089308b5a9f70e1e4054"
    ),
    ("Deployment", "starbase-system", "starbase-core", "web"): (
        "ghcr.io/x-mckay/starbase/web@"
        "sha256:ab5e5aa20e7c318f38bbfb8c20c739bfa10b5b4888ef152623367dbc24ed9baf"
    ),
    (
        "Deployment",
        "starbase-connectors",
        "starbase-preview-fixture",
        "connector",
    ): (
        "ghcr.io/x-mckay/starbase/github-connector@"
        "sha256:6a3a5324fb965d0b179f093606747f925f17ff9c2acf35847c2b07b1cd2dab06"
    ),
}


def render(path: Path) -> list[dict]:
    rendered = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [document for document in yaml.safe_load_all(rendered) if document]


def by_identity(documents: list[dict]) -> dict[tuple[str, str, str], dict]:
    return {
        (
            document["kind"],
            document.get("metadata", {}).get("namespace", ""),
            document["metadata"]["name"],
        ): document
        for document in documents
    }


class StarbasePhase5RuntimeRollbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preview = by_identity(render(PREVIEW))
        cls.rollback = by_identity(render(ROLLBACK))

    def test_rollback_changes_only_active_runtime_images_and_annotations(self) -> None:
        self.assertEqual(set(self.rollback), set(self.preview))
        changed = {
            ("Deployment", "starbase-system", "starbase-core"),
            ("Deployment", "starbase-connectors", "starbase-preview-fixture"),
        }
        for identity in self.preview:
            if identity not in changed:
                self.assertEqual(
                    self.rollback[identity],
                    self.preview[identity],
                    f"rollback changed unexpected object {identity}",
                )

        for identity in changed:
            expected = copy.deepcopy(self.preview[identity])
            expected["metadata"]["annotations"].update(
                {
                    "starbase.io/activation-state": "authorized-rc4-runtime-rollback",
                    "starbase.io/activation-stage": "phase5-rc4-runtime-rollback",
                }
            )
            expected["spec"]["template"]["metadata"]["annotations"].update(
                {
                    "starbase.io/activation-state": "authorized-rc4-runtime-rollback",
                    "starbase.io/activation-stage": "phase5-rc4-runtime-rollback",
                }
            )
            for container in expected["spec"]["template"]["spec"]["containers"]:
                image_key = (*identity, container["name"])
                if image_key in RC4_IMAGES:
                    container["image"] = RC4_IMAGES[image_key]
            self.assertEqual(self.rollback[identity], expected)

    def test_rollback_preserves_suspended_rc5_migration_identities(self) -> None:
        jobs = {
            identity[2]: document
            for identity, document in self.rollback.items()
            if identity[0] == "Job" and identity[1] == "starbase-system"
        }
        for name in (
            "starbase-core-migrate-0da307f3148a",
            "starbase-gateway-migrate-f2fa2f551602",
        ):
            self.assertTrue(jobs[name]["spec"]["suspend"])
            self.assertEqual(
                jobs[name]["metadata"]["annotations"][
                    "starbase.io/activation-state"
                ],
                "blocked",
            )
        self.assertNotIn("starbase-core-migrate-67c24a8df537", jobs)
        self.assertNotIn("starbase-gateway-migrate-c5de66b03eaf", jobs)

    def test_rollback_is_prepared_but_not_active(self) -> None:
        flux = yaml.safe_load(FOUNDATION_FLUX.read_text())
        self.assertEqual(
            flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase10-autonomous-reader-prepared",
        )
        starbase_promotion.assert_phase5_runtime_rollback_is_bounded(ROOT)

    def test_policy_rejects_runtime_image_substitution(self) -> None:
        documents = copy.deepcopy(list(self.rollback.values()))
        core = next(
            document
            for document in documents
            if document["kind"] == "Deployment"
            and document["metadata"].get("namespace") == "starbase-system"
            and document["metadata"]["name"] == "starbase-core"
        )
        core["spec"]["template"]["spec"]["containers"][0]["image"] += "-changed"
        with self.assertRaisesRegex(ValueError, "rollback-approved"):
            self._assert_rollback_documents(documents)

    def test_policy_rejects_unsuspended_migration(self) -> None:
        documents = copy.deepcopy(list(self.rollback.values()))
        migration = next(
            document
            for document in documents
            if document["kind"] == "Job"
            and document["metadata"]["name"]
            == "starbase-core-migrate-0da307f3148a"
        )
        migration["spec"]["suspend"] = False
        with self.assertRaisesRegex(ValueError, "retained Job definitions"):
            self._assert_rollback_documents(documents)

    @staticmethod
    def _assert_rollback_documents(documents: list[dict]) -> None:
        lock = json.loads(
            (
                ROOT / "infrastructure/gitops/apps/starbase/promotion-lock.json"
            ).read_text()
        )["release"]["images"]
        retained_jobs = [
            document
            for document in render(
                ROOT / "infrastructure/gitops/apps/starbase-phase4a-foundation"
            )
            if document["kind"] == "Job"
        ]
        starbase_promotion.assert_phase5_preview_deployments(
            documents,
            lock,
            retained_jobs,
            active_images=starbase_promotion.RC4_RUNTIME_ROLLBACK_IMAGES,
        )


if __name__ == "__main__":
    unittest.main()
