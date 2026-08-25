from __future__ import annotations

import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATABASES = ROOT / "infrastructure/gitops/apps/databases"
BACKUP_NAME = "authentik-live-alignment-v1-20260825.sql.gz.enc"


def render(path: Path) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class AuthentikLiveUpgradeContractTests(unittest.TestCase):
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

    def test_preflight_is_one_shot_bounded_and_merge_activated(self) -> None:
        job = self.object("Job", "database", "authentik-live-preflight-v2")
        self.assertNotIn(
            ("Job", "database", "authentik-live-preflight-v1"), self.by_identity
        )
        self.assertFalse(job["spec"]["suspend"])
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 1200)
        self.assertNotIn("ttlSecondsAfterFinished", job["spec"])
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/activation-gate"],
            "merge-creates-recovery-evidence-only",
        )
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/recovery-backup"],
            BACKUP_NAME,
        )

        pod = job["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "authentik-live-upgrade")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["rig0"],
        )
        container = pod["containers"][0]
        self.assertIn("@sha256:", container["image"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])

    def test_preflight_creates_and_restores_exact_encrypted_backup(self) -> None:
        job = self.object("Job", "database", "authentik-live-preflight-v2")
        config = self.object("ConfigMap", "database", "authentik-live-preflight-v2")
        script = config["data"]["preflight.sh"]
        subprocess.run(["bash", "-n"], input=script, check=True, text=True)
        for required in (
            BACKUP_NAME,
            "readonly work_dir=/work/runtime",
            "reviewed backup target already exists",
            "pg_dumpall",
            "openssl enc -aes-256-cbc",
            "sha256sum --check",
            "initdb",
            "listen_addresses=''",
            "ON_ERROR_STOP=1",
            "authentik_rbac_role",
            "0008_alter_role_group",
            "0009_remove_initialpermissions_mode",
            "0010_remove_role_group_alter_role_name",
            "0056_user_roles",
            "authentik_core_user_roles",
            "waiting_locks",
            "PASS: fresh encrypted backup restored and live-alignment fingerprint verified",
        ):
            self.assertIn(required, script)
        self.assertNotIn("set -x", script)
        self.assertNotIn("authentik-credentials", script)
        self.assertNotIn("AUTHENTIK_SECRET_KEY", script)
        self.assertNotIn("ALTER TABLE", script)
        self.assertNotIn("DELETE FROM django_migrations", script)
        self.assertFalse(BACKUP_NAME.startswith("postgres-"))

        digest = sha256(script.encode()).hexdigest()
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/preflight-contract-digest"],
            f"sha256:{digest}",
        )
        backup = next(
            volume
            for volume in job["spec"]["template"]["spec"]["volumes"]
            if volume["name"] == "backups"
        )
        self.assertEqual(
            backup["persistentVolumeClaim"], {"claimName": "postgres-backup-rig0"}
        )

    def test_live_alignment_is_staged_but_suspended(self) -> None:
        job = self.object("Job", "database", "authentik-live-alignment-v1")
        self.assertTrue(job["spec"]["suspend"])
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 900)
        self.assertNotIn("ttlSecondsAfterFinished", job["spec"])
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/activation-gate"],
            "separate-review-scales-authentik-to-zero-and-unsuspends",
        )
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/recovery-backup"],
            BACKUP_NAME,
        )
        pod = job["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "authentik-live-upgrade")
        self.assertFalse(pod["automountServiceAccountToken"])
        backup = next(volume for volume in pod["volumes"] if volume["name"] == "backups")
        self.assertEqual(
            backup["persistentVolumeClaim"],
            {"claimName": "postgres-backup-rig0", "readOnly": True},
        )

    def test_alignment_is_exact_transactional_and_fails_closed(self) -> None:
        job = self.object("Job", "database", "authentik-live-alignment-v1")
        config = self.object("ConfigMap", "database", "authentik-live-alignment-v1")
        script = config["data"]["align.sh"]
        subprocess.run(["bash", "-n"], input=script, check=True, text=True)
        for required in (
            BACKUP_NAME,
            "sha256sum --check",
            "authentik sessions did not drain",
            "pg_advisory_xact_lock",
            "lock_timeout",
            "statement_timeout",
            "ALTER COLUMN group_id DROP NOT NULL",
            "authentik_rbac_initialpermissions DROP COLUMN mode",
            "0010_remove_role_group_alter_role_name",
            "GET DIAGNOSTICS",
            "BEGIN",
            "COMMIT",
            "PostgreSQL rolled back",
            "PASS: live Authentik migration state aligned",
        ):
            self.assertIn(required, script)
        self.assertNotIn("set -x", script)
        self.assertNotIn("authentik-credentials", script)
        self.assertNotIn("usename = 'authentik'", script)
        digest = sha256(script.encode()).hexdigest()
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/alignment-contract-digest"],
            f"sha256:{digest}",
        )

    def test_network_access_is_only_postgresql_plus_existing_dns_policy(self) -> None:
        policy = self.object(
            "NetworkPolicy", "database", "allow-authentik-live-upgrade-postgresql"
        )
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(policy["spec"]["ingress"], [])
        self.assertEqual(
            policy["spec"]["podSelector"]["matchLabels"],
            {"app.kubernetes.io/part-of": "authentik-live-upgrade"},
        )
        self.assertEqual(len(policy["spec"]["egress"]), 1)
        self.assertEqual(
            policy["spec"]["egress"][0],
            {
                "to": [
                    {
                        "podSelector": {
                            "matchLabels": {"app.kubernetes.io/name": "postgresql"}
                        }
                    }
                ],
                "ports": [{"port": 5432, "protocol": "TCP"}],
            },
        )

    def test_service_account_has_no_rbac_binding(self) -> None:
        service_account = self.object(
            "ServiceAccount", "database", "authentik-live-upgrade"
        )
        self.assertFalse(service_account["automountServiceAccountToken"])
        bindings = [
            document
            for document in self.documents
            if document["kind"] in {"RoleBinding", "ClusterRoleBinding"}
        ]
        for binding in bindings:
            for subject in binding.get("subjects", []):
                self.assertNotEqual(subject.get("name"), "authentik-live-upgrade")


if __name__ == "__main__":
    unittest.main()
