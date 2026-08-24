from __future__ import annotations

import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "infrastructure/gitops/infrastructure/storage"
DATABASES = ROOT / "infrastructure/gitops/apps/databases"


def render(path: Path) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class PostgresBackupRecoveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = render(STORAGE) + render(DATABASES)
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

    def test_rig0_backup_volume_is_retained_and_late_bound(self) -> None:
        storage_class = self.object("StorageClass", "", "local-path-retain")
        self.assertEqual(storage_class["provisioner"], "rancher.io/local-path")
        self.assertEqual(storage_class["volumeBindingMode"], "WaitForFirstConsumer")
        self.assertEqual(storage_class["reclaimPolicy"], "Retain")

        claim = self.object(
            "PersistentVolumeClaim", "database", "postgres-backup-rig0"
        )
        self.assertEqual(claim["spec"]["storageClassName"], "local-path-retain")
        self.assertEqual(claim["spec"]["accessModes"], ["ReadWriteOnce"])
        self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], "2Gi")

        legacy_claim = self.object(
            "PersistentVolumeClaim", "database", "postgres-backup"
        )
        self.assertEqual(
            legacy_claim["metadata"]["annotations"]["kubani.io/removal-condition"],
            "rig0-backup-and-isolated-restore-verified",
        )

    def test_backup_is_encrypted_atomic_and_pinned_to_rig0(self) -> None:
        service_account = self.object(
            "ServiceAccount", "database", "postgres-backup"
        )
        self.assertFalse(service_account["automountServiceAccountToken"])
        cronjob = self.object("CronJob", "database", "postgres-backup")
        self.assertFalse(cronjob["spec"]["suspend"])
        self.assertEqual(cronjob["spec"]["concurrencyPolicy"], "Forbid")
        self.assertEqual(cronjob["spec"]["startingDeadlineSeconds"], 1800)

        job = cronjob["spec"]["jobTemplate"]["spec"]
        self.assertEqual(job["activeDeadlineSeconds"], 900)
        self.assertEqual(job["backoffLimit"], 1)
        pod = job["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "postgres-backup")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertEqual(
            pod["securityContext"]["seccompProfile"], {"type": "RuntimeDefault"}
        )
        requirement = pod["affinity"]["nodeAffinity"][
            "requiredDuringSchedulingIgnoredDuringExecution"
        ]["nodeSelectorTerms"][0]["matchExpressions"][0]
        self.assertEqual(requirement["key"], "kubernetes.io/hostname")
        self.assertEqual(requirement["operator"], "In")
        self.assertEqual(requirement["values"], ["rig0"])
        self.assertEqual(
            pod["volumes"][0]["persistentVolumeClaim"]["claimName"],
            "postgres-backup-rig0",
        )

        container = pod["containers"][0]
        self.assertEqual(container["env"][1], {"name": "RETENTION", "value": "14"})
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertIn("ephemeral-storage", container["resources"]["requests"])
        self.assertIn("ephemeral-storage", container["resources"]["limits"])

        script = container["command"][2]
        subprocess.run(["bash", "-n"], input=script, check=True, text=True)
        self.assertIn("umask 077", script)
        self.assertIn("/backups/postgresql", script)
        self.assertIn("openssl enc -aes-256-cbc -salt -pbkdf2", script)
        self.assertIn("-pass env:POSTGRES_PASSWORD", script)
        self.assertIn("gzip -t", script)
        self.assertIn("sha256sum", script)
        self.assertIn(".partial", script)
        self.assertNotIn("echo $POSTGRES_PASSWORD", script)

    def test_restore_verifier_is_suspended_isolated_and_content_bound(self) -> None:
        config = self.object(
            "ConfigMap", "database", "postgres-backup-restore-verification-v1"
        )
        script = config["data"]["verify-restore.sh"]
        digest = sha256(script.encode()).hexdigest()
        job = self.object(
            "Job",
            "database",
            f"postgres-backup-restore-verification-v1-{digest[:12]}",
        )
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/restore-contract-digest"],
            f"sha256:{digest}",
        )
        self.assertTrue(job["spec"]["suspend"])
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 1200)
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertNotIn("ttlSecondsAfterFinished", job["spec"])

        pod = job["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "postgres-backup")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["rig0"],
        )
        backup_volume = next(
            volume for volume in pod["volumes"] if volume["name"] == "backups"
        )
        self.assertEqual(
            backup_volume["persistentVolumeClaim"],
            {"claimName": "postgres-backup-rig0", "readOnly": True},
        )
        container = pod["containers"][0]
        backup_mount = next(
            mount for mount in container["volumeMounts"] if mount["name"] == "backups"
        )
        self.assertTrue(backup_mount["readOnly"])
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])

        subprocess.run(["bash", "-n"], input=script, check=True, text=True)
        for required in (
            "sha256sum --check",
            "openssl enc -d -aes-256-cbc",
            "gzip -t",
            "initdb",
            "pg_ctl",
            "log_statement=none",
            "log_min_error_statement=panic",
            "ON_ERROR_STOP=1",
        ):
            self.assertIn(required, script)
        self.assertNotIn("postgresql.database.svc.cluster.local", script)

        # pg_dumpall --clean emits DROP ROLE for dumped roles, including
        # postgres. Restoring as that same role fails under ON_ERROR_STOP, so
        # the ephemeral verifier must use an identity absent from the dump.
        self.assertIn("restore_verifier_$(openssl rand -hex 12)", script)
        self.assertIn(
            'initdb --pgdata="${PGDATA}" --username="${restore_role}"', script
        )
        self.assertGreaterEqual(script.count('--username="${restore_role}"'), 6)
        self.assertNotIn("--username=postgres", script)

        # Counts from a fresh initdb cluster are not restore evidence. Require
        # known source-owned catalog and schema objects instead.
        self.assertIn("datname = 'authentik'", script)
        self.assertIn("rolname = 'postgres'", script)
        self.assertIn("authentik_table_count", script)


if __name__ == "__main__":
    unittest.main()
