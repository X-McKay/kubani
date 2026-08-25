from __future__ import annotations

import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATABASES = ROOT / "infrastructure/gitops/apps/databases"


def render(path: Path) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class AuthentikUpgradeRehearsalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(DATABASES)
        cls.by_identity = {
            (
                document["kind"],
                document.get("metadata", {}).get("namespace", ""),
                document["metadata"]["name"],
            ): document
            for document in cls.documents
        }

    def object(self, kind: str, namespace: str, name: str) -> dict:
        return self.by_identity[(kind, namespace, name)]

    def test_rehearsal_is_exact_bounded_and_merge_activated(self) -> None:
        jobs = [
            document
            for document in self.documents
            if document["kind"] == "Job"
            and document.get("metadata", {}).get("labels", {}).get(
                "app.kubernetes.io/name"
            )
            == "authentik-upgrade-rehearsal"
        ]
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(
            job["metadata"]["name"],
            "authentik-upgrade-rehearsal-v1-fedac5358865",
        )
        self.assertFalse(job["spec"]["suspend"])
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 3600)
        self.assertNotIn("ttlSecondsAfterFinished", job["spec"])
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/activation-gate"],
            "merge-is-exact-revision-authorization",
        )
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/source-backup"],
            "postgres-20260825-020000.sql.gz.enc",
        )

        pod = job["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["rig0"],
        )

        backup = next(volume for volume in pod["volumes"] if volume["name"] == "backups")
        self.assertEqual(
            backup["persistentVolumeClaim"],
            {"claimName": "postgres-backup-rig0", "readOnly": True},
        )

    def test_rehearsal_uses_one_isolated_restore_and_ordered_digest_images(self) -> None:
        job = next(
            document
            for document in self.documents
            if document["kind"] == "Job"
            and document.get("metadata", {}).get("labels", {}).get(
                "app.kubernetes.io/name"
            )
            == "authentik-upgrade-rehearsal"
        )
        pod = job["spec"]["template"]["spec"]
        init = pod["initContainers"]
        self.assertEqual(init[0]["name"], "restore-postgres")
        self.assertEqual(init[0]["restartPolicy"], "Always")
        self.assertIn("@sha256:", init[0]["image"])

        expected = [
            (
                "upgrade-2025-10-4",
                "2025.10.4",
                "ghcr.io/goauthentik/server:2025.10.4@sha256:4b4f9ae106dbda902b836aa7a79d2f456b8302f090b862f7ad1bf268402730b2",
            ),
            (
                "upgrade-2025-12-0",
                "2025.12.0",
                "ghcr.io/goauthentik/server:2025.12.0@sha256:c4b55bec00d0872ffe7beac401b747eaf6f48bdf5e9be1500a23bf962226fc2e",
            ),
            (
                "upgrade-2025-12-6",
                "2025.12.6",
                "ghcr.io/goauthentik/server:2025.12.6@sha256:d4c1750e26bb7faa4d09e23305d75b54957ce4b81cee8e3acf4cc4bb8635d705",
            ),
            (
                "upgrade-2026-2-6",
                "2026.2.6",
                "ghcr.io/goauthentik/server:2026.2.6@sha256:49d30c0e511668329e2a3083e6a4ed16ba5ef072880df46794668587464d31f7",
            ),
            (
                "upgrade-2026-5-6",
                "2026.5.6",
                "ghcr.io/goauthentik/server:2026.5.6@sha256:ed120caf710ccf82ef0026f0bc74e51615bc95ebff228a7a2d6fc60c441c3868",
            ),
        ]
        actual = []
        for container in init[1:]:
            self.assertIn("@sha256:", container["image"])
            self.assertNotIn(":latest", container["image"])
            self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
            self.assertFalse(
                container["securityContext"]["allowPrivilegeEscalation"]
            )
            self.assertEqual(
                {mount["mountPath"] for mount in container["volumeMounts"]},
                {"/opt/kubani/run-version.sh", "/work", "/tmp", "/certs", "/media", "/run"},
            )
            actual.append(
                (container["name"], container["args"][-1], container["image"])
            )
        self.assertEqual(actual, expected)

        verifier = pod["containers"]
        self.assertEqual(len(verifier), 1)
        self.assertEqual(verifier[0]["name"], "verify-upgrade")
        self.assertIn("@sha256:", verifier[0]["image"])

    def test_rehearsal_has_no_route_to_live_services_or_external_network(self) -> None:
        policy = self.object(
            "NetworkPolicy", "database", "deny-authentik-upgrade-rehearsal-network"
        )
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(policy["spec"]["ingress"], [])
        self.assertEqual(policy["spec"]["egress"], [])

        config = self.object(
            "ConfigMap", "database", "authentik-upgrade-rehearsal-v1-fedac5358865"
        )
        scripts = "\n".join(config["data"].values())
        canonical_scripts = "\n---\n".join(
            config["data"][name] for name in sorted(config["data"])
        )
        digest = sha256(canonical_scripts.encode()).hexdigest()
        self.assertEqual(
            digest,
            "fedac53588658f12e544ac9230df9b7a87f3a0a2c8695e086ab88c6e6c87579d",  # pragma: allowlist secret
        )
        subprocess.run(
            ["bash", "-n"],
            input=scripts,
            check=True,
            text=True,
        )
        self.assertIn("postgres-20260825-020000.sql.gz.enc", scripts)
        self.assertIn("listen_addresses=127.0.0.1", scripts)
        self.assertIn("AUTHENTIK_DISABLE_UPDATE_CHECK=true", scripts)
        self.assertIn("authentik_version_history", scripts)
        self.assertIn("2026.5.6", scripts)
        self.assertNotIn("postgresql.database.svc.cluster.local", scripts)
        self.assertNotIn("authentik-credentials", scripts)

        job = next(
            document
            for document in self.documents
            if document["kind"] == "Job"
            and document.get("metadata", {}).get("labels", {}).get(
                "app.kubernetes.io/name"
            )
            == "authentik-upgrade-rehearsal"
        )
        pod_text = yaml.safe_dump(job["spec"]["template"]["spec"])
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/rehearsal-contract-digest"],
            f"sha256:{digest}",
        )
        self.assertNotIn("authentik-credentials", pod_text)
        self.assertNotIn("postgresql.database.svc.cluster.local", pod_text)


if __name__ == "__main__":
    unittest.main()
