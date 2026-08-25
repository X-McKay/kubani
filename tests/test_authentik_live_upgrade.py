from __future__ import annotations

import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DATABASES = ROOT / "infrastructure/gitops/apps/databases"
AUTHENTIK = ROOT / "infrastructure/gitops/apps/authentik"
AUTHENTIK_HELMRELEASE = (
    ROOT / "infrastructure/gitops/apps/authentik/helmrelease.yaml"
)
APPS_KUSTOMIZATION = (
    ROOT / "infrastructure/gitops/flux-system/apps-kustomization.yaml"
)
DATABASES_KUSTOMIZATION = (
    ROOT / "infrastructure/gitops/flux-system/databases-kustomization.yaml"
)
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
        cls.auth_documents = render(AUTHENTIK)
        cls.auth_by_identity = {
            (
                document["kind"],
                document.get("metadata", {}).get("namespace", ""),
                document["metadata"]["name"],
            ): document
            for document in cls.auth_documents
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

    def test_live_alignment_is_activated_and_blocks_apps_until_complete(self) -> None:
        job = self.object("Job", "database", "authentik-live-alignment-v1")
        self.assertFalse(job["spec"]["suspend"])
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 900)
        self.assertNotIn("ttlSecondsAfterFinished", job["spec"])
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/activation-gate"],
            "merge-authorizes-reviewed-live-alignment",
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

        databases = yaml.safe_load(DATABASES_KUSTOMIZATION.read_text())
        self.assertIn(
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "name": "authentik-live-alignment-v1",
                "namespace": "database",
            },
            databases["spec"]["healthChecks"],
        )

    def test_maintenance_drain_stops_authentik_before_alignment(self) -> None:
        helmrelease = yaml.safe_load(AUTHENTIK_HELMRELEASE.read_text())
        values = helmrelease["spec"]["values"]
        self.assertEqual(values["server"]["replicas"], 0)
        self.assertEqual(values["worker"]["replicas"], 0)
        self.assertEqual(
            helmrelease["spec"]["chart"]["spec"]["version"], "2026.5.6"
        )
        self.assertEqual(values["global"]["image"]["tag"], "2026.5.6")
        self.assertEqual(
            values["global"]["image"]["digest"],
            "sha256:ed120caf710ccf82ef0026f0bc74e51615bc95ebff228a7a2d6fc60c441c3868",
        )

        alignment = self.object("Job", "database", "authentik-live-alignment-v1")
        self.assertFalse(alignment["spec"]["suspend"])

    def test_live_ladder_is_sequential_bounded_and_flux_gated(self) -> None:
        job = self.auth_by_identity[
            ("Job", "auth", "authentik-live-upgrade-ladder-v1")
        ]
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 3600)
        self.assertNotIn("ttlSecondsAfterFinished", job["spec"])
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/activation-gate"],
            "merge-authorizes-reviewed-sequential-live-migration",
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
        expected = [
            (
                "upgrade-2025-10-4",
                "ghcr.io/goauthentik/server:2025.10.4@sha256:4b4f9ae106dbda902b836aa7a79d2f456b8302f090b862f7ad1bf268402730b2",
            ),
            (
                "upgrade-2025-12-0",
                "ghcr.io/goauthentik/server:2025.12.0@sha256:c4b55bec00d0872ffe7beac401b747eaf6f48bdf5e9be1500a23bf962226fc2e",
            ),
            (
                "upgrade-2025-12-6",
                "ghcr.io/goauthentik/server:2025.12.6@sha256:d4c1750e26bb7faa4d09e23305d75b54957ce4b81cee8e3acf4cc4bb8635d705",
            ),
            (
                "upgrade-2026-2-6",
                "ghcr.io/goauthentik/server:2026.2.6@sha256:49d30c0e511668329e2a3083e6a4ed16ba5ef072880df46794668587464d31f7",
            ),
            (
                "upgrade-2026-5-6",
                "ghcr.io/goauthentik/server:2026.5.6@sha256:ed120caf710ccf82ef0026f0bc74e51615bc95ebff228a7a2d6fc60c441c3868",
            ),
        ]
        actual = [
            (container["name"], container["image"])
            for container in pod["initContainers"]
            if container["name"].startswith("upgrade-")
        ]
        self.assertEqual(actual, expected)

        apps = yaml.safe_load(APPS_KUSTOMIZATION.read_text())
        self.assertIn(
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "name": "authentik-live-upgrade-ladder-v1",
                "namespace": "auth",
            },
            apps["spec"]["healthChecks"],
        )

    def test_live_ladder_credentials_and_network_are_least_privilege(self) -> None:
        job = self.auth_by_identity[
            ("Job", "auth", "authentik-live-upgrade-ladder-v1")
        ]
        pod = job["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "authentik-live-upgrade")
        serialized = yaml.safe_dump(job)
        self.assertNotIn("bootstrap-token", serialized)
        self.assertNotIn("bootstrap-password", serialized)
        self.assertNotIn("AUTHENTIK_BOOTSTRAP", serialized)
        self.assertNotIn("RoleBinding", serialized)
        for container in pod["initContainers"]:
            if container["name"].startswith("upgrade-"):
                refs = {
                    item["valueFrom"]["secretKeyRef"]["key"]
                    for item in container["env"]
                    if "valueFrom" in item
                }
                self.assertEqual(refs, {"secret-key", "postgres-password"})

        policy = self.auth_by_identity[
            ("NetworkPolicy", "auth", "allow-authentik-live-upgrade-postgresql")
        ]
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress", "Egress"])
        self.assertEqual(policy["spec"]["ingress"], [])
        ports = {
            (port["port"], port["protocol"])
            for rule in policy["spec"]["egress"]
            for port in rule["ports"]
        }
        self.assertEqual(ports, {(53, "UDP"), (53, "TCP"), (5432, "TCP")})

    def test_live_ladder_scripts_fail_closed_on_drift(self) -> None:
        config = self.auth_by_identity[
            ("ConfigMap", "auth", "authentik-live-upgrade-ladder-v1")
        ]
        baseline = config["data"]["capture-baseline.sh"]
        lifecycle = config["data"]["run-version.sh"]
        verifier = config["data"]["verify-upgrade.sh"]
        for script in (baseline, lifecycle, verifier):
            subprocess.run(["bash", "-n"], input=script, check=True, text=True)
            self.assertNotIn("set -x", script)
        for required in (
            "2025.10.3",
            "authentik sessions are not fully drained",
            "pre_alignment_fingerprint",
            "post_alignment_fingerprint",
            "seq 1 180",
            "did not complete within the bounded wait",
            'chgrp 2000 "${shared_dir}"',
            'chmod 2770 "${shared_dir}"',
            "0056_user_roles",
            "0010_remove_role_group_alter_role_name",
            "waiting locks",
        ):
            self.assertIn(required, baseline)
        for required in (
            "AUTHENTIK_DISABLE_UPDATE_CHECK",
            "127.0.0.1:9000",
            "gunicorn failed to start",
            "migrate --check",
        ):
            self.assertIn(required, lifecycle)
        for required in (
            "2026.5.6",
            "identity or provider object counts changed",
            "1|1|0",
            "waiting locks",
            "PASS: live Authentik upgrade reached",
        ):
            self.assertIn(required, verifier)
        job = self.auth_by_identity[
            ("Job", "auth", "authentik-live-upgrade-ladder-v1")
        ]
        digest = sha256((baseline + lifecycle + verifier).encode()).hexdigest()
        self.assertEqual(
            job["metadata"]["annotations"]["kubani.io/ladder-contract-digest"],
            f"sha256:{digest}",
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
