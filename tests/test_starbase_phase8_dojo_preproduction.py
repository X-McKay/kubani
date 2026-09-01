from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "infrastructure/gitops/apps/starbase-phase8-dojo-preproduction"
FLUX = ROOT / "infrastructure/gitops/flux-system/starbase-dojo-kustomization.yaml"
FLUX_AGGREGATE = ROOT / "infrastructure/gitops/flux-system/kustomization.yaml"
TEMPORAL_POLICY = (
    ROOT / "infrastructure/gitops/infrastructure/networking/netpol-temporal.yaml"
)
DOJO_IMAGE = (
    "ghcr.io/x-mckay/starbase/dojo-runtime@"
    "sha256:5d13884264d9b93e0c2bee80ee9ea06a1fdb547a5efa810eff1e6179cb38b74d"
)
SOURCE_REVISION = "66e2d87ac4a2cd7ae8719b05bbdd89a7215dad15"


class StarbasePhase8DojoPreproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rendered = subprocess.run(
            ["kubectl", "kustomize", str(ACTIVE)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        cls.documents = [doc for doc in yaml.safe_load_all(rendered) if doc]
        cls.by_identity = {
            (
                doc["kind"],
                doc.get("metadata", {}).get("namespace", ""),
                doc["metadata"]["name"],
            ): doc
            for doc in cls.documents
        }

    def object(self, kind: str, namespace: str, name: str) -> dict:
        return self.by_identity[(kind, namespace, name)]

    @staticmethod
    def container(deployment: dict, name: str) -> dict:
        return next(
            item
            for item in deployment["spec"]["template"]["spec"]["containers"]
            if item["name"] == name
        )

    @staticmethod
    def environment(container: dict) -> dict[str, dict]:
        return {item["name"]: item for item in container["env"]}

    def test_uses_exact_signed_successor_release(self) -> None:
        image_users = []
        for document in self.documents:
            pod_spec = None
            if document["kind"] == "Deployment":
                pod_spec = document["spec"]["template"]["spec"]
            if document["kind"] == "Job" and document["metadata"]["namespace"] == "starbase-execution":
                pod_spec = document["spec"]["template"]["spec"]
            if pod_spec:
                image_users.extend(
                    container["image"]
                    for container in pod_spec["containers"]
                    if container["image"].startswith("ghcr.io/x-mckay/starbase/")
                )
        self.assertEqual(len(image_users), 6)
        self.assertEqual(set(image_users), {DOJO_IMAGE})

        for name in ("starbase-dojo-runtime", "starbase-dojo-workflow-worker"):
            deployment = self.object("Deployment", "starbase-execution", name)
            annotations = deployment["spec"]["template"]["metadata"]["annotations"]
            self.assertEqual(annotations["starbase.io/release"], "0.1.0-rc.6")
            self.assertEqual(annotations["starbase.io/source-revision"], SOURCE_REVISION)

    def test_runtime_is_non_authoritative_and_not_exposed(self) -> None:
        kinds = {doc["kind"] for doc in self.documents}
        self.assertNotIn("Service", kinds)
        self.assertNotIn("Ingress", kinds)

        runtime = self.object("Deployment", "starbase-execution", "starbase-dojo-runtime")
        self.assertEqual(runtime["metadata"]["annotations"]["starbase.io/external-authority"], "false")
        names = {
            item["name"]
            for item in runtime["spec"]["template"]["spec"]["containers"]
        }
        self.assertEqual(
            names,
            {"dojo-server", "sandbox-fixture", "advisory-fixture", "evaluation-activity-worker"},
        )

        activity = self.container(runtime, "evaluation-activity-worker")
        env = self.environment(activity)
        self.assertEqual(env["STARBASE_EVALUATION_RUNTIME_MODE"]["value"], "local-fixture")
        self.assertEqual(env["STARBASE_EVALUATION_MODEL_ALLOWED_HOSTS"]["value"], "127.0.0.1")
        self.assertEqual(env["STARBASE_EVALUATION_SANDBOX_ALLOWED_HOSTS"]["value"], "127.0.0.1")
        self.assertEqual(env["STARBASE_EVALUATION_DOJO_ALLOWED_HOSTS"]["value"], "127.0.0.1")
        self.assertEqual(env["STARBASE_EVALUATION_ALLOWED_CLASSIFICATIONS"]["value"], "internal")

        advisory = self.container(runtime, "advisory-fixture")
        advisory_env = self.environment(advisory)
        self.assertEqual(
            advisory_env["STARBASE_ADVISORY_FIXTURE_MODEL"]["value"],
            "starbase-no-change-fixture-v1",
        )

        environment = self.object(
            "ConfigMap", "starbase-execution", "starbase-dojo-evaluation-environment-v1"
        )
        chamber = json.loads(environment["data"]["environment.json"])
        self.assertEqual(chamber["provider"], "fixture")
        self.assertEqual(chamber["network"], {"default": "deny", "allow": []})

    def test_temporal_exception_is_exact_and_internal(self) -> None:
        for deployment_name, container_name in (
            ("starbase-dojo-runtime", "evaluation-activity-worker"),
            ("starbase-dojo-workflow-worker", "workflow-worker"),
        ):
            deployment = self.object("Deployment", "starbase-execution", deployment_name)
            env = self.environment(self.container(deployment, container_name))
            self.assertEqual(env["STARBASE_TEMPORAL_MODE"]["value"], "kubani-internal-preproduction")
            self.assertEqual(
                env["STARBASE_TEMPORAL_ADDRESS"]["value"],
                "temporal-frontend.temporal.svc.cluster.local:7233",
            )
            self.assertEqual(env["STARBASE_TEMPORAL_NAMESPACE"]["value"], "default")
            self.assertEqual(env["STARBASE_TEMPORAL_INTERNAL_ACK"]["value"], "adr-0016")

        temporal_documents = [
            doc for doc in yaml.safe_load_all(TEMPORAL_POLICY.read_text()) if doc
        ]
        ingress = next(
            doc
            for doc in temporal_documents
            if doc["kind"] == "NetworkPolicy"
            and doc["metadata"]["name"] == "allow-worker-ingress"
        )
        self.assertEqual(
            ingress["spec"]["podSelector"]["matchLabels"],
            {
                "app.kubernetes.io/name": "temporal",
                "app.kubernetes.io/instance": "temporal",
                "app.kubernetes.io/component": "frontend",
            },
        )
        source = ingress["spec"]["ingress"][0]["from"][0]
        self.assertEqual(
            source["namespaceSelector"]["matchLabels"],
            {"kubernetes.io/metadata.name": "starbase-execution"},
        )
        self.assertEqual(
            source["podSelector"]["matchLabels"],
            {"starbase.io/temporal-client": "true"},
        )
        self.assertEqual(
            ingress["spec"]["ingress"][0]["ports"],
            [{"port": 7233, "protocol": "TCP"}],
        )

    def test_identity_placement_and_container_hardening(self) -> None:
        expected_accounts = {
            "starbase-dojo-database-bootstrap",
            "starbase-dojo-migrator",
            "starbase-dojo-runtime",
            "starbase-dojo-workflow-worker",
        }
        accounts = {
            doc["metadata"]["name"]
            for doc in self.documents
            if doc["kind"] == "ServiceAccount"
        }
        self.assertEqual(accounts, expected_accounts)
        for account in expected_accounts:
            namespace = "database" if account.endswith("bootstrap") else "starbase-execution"
            self.assertFalse(self.object("ServiceAccount", namespace, account)["automountServiceAccountToken"])

        for document in self.documents:
            if document["kind"] not in {"Deployment", "Job"}:
                continue
            pod = document["spec"]["template"]["spec"]
            self.assertFalse(pod["automountServiceAccountToken"])
            values = pod["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"][0]["matchExpressions"][0]["values"]
            self.assertEqual(values, ["asio", "strix"])
            for container in pod["containers"]:
                security = container["securityContext"]
                self.assertFalse(security["allowPrivilegeEscalation"])
                self.assertTrue(security["readOnlyRootFilesystem"])
                self.assertEqual(security["capabilities"]["drop"], ["ALL"])

    def test_database_roles_and_migration_are_separated(self) -> None:
        bootstrap = self.object(
            "ConfigMap", "database", "starbase-dojo-database-bootstrap-v1"
        )["data"]["bootstrap.sh"]
        self.assertIn("starbase_dojo_runtime", bootstrap)
        self.assertIn("starbase_dojo_migrator", bootstrap)
        self.assertIn("REVOKE ALL ON DATABASE starbase_dojo FROM PUBLIC", bootstrap)
        self.assertNotIn("CREATE ROLE starbase_dojo_runtime SUPERUSER", bootstrap)

        digest = hashlib.sha256(bootstrap.encode()).hexdigest()
        job = self.object(
            "Job", "database", "starbase-dojo-database-bootstrap-v1-66e26e025d98"
        )
        self.assertEqual(
            job["metadata"]["annotations"]["starbase.io/bootstrap-contract-digest"],
            f"sha256:{digest}",
        )

        migration = self.object(
            "Job", "starbase-execution", "starbase-dojo-migrate-rc6-5d13884264d9"
        )
        container = migration["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["command"], ["/usr/local/bin/dojo-migrator"])
        self.assertEqual(
            container["env"][0]["valueFrom"]["secretKeyRef"],
            {"name": "starbase-dojo-migration", "key": "database-url"},
        )

    def test_all_secret_values_are_sops_encrypted(self) -> None:
        expected = {
            "dojo-bootstrap-secret.enc.yaml": {"runtime-password", "migrator-password"},
            "dojo-runtime-secret.enc.yaml": {"database-url", "read-token", "write-token", "sandbox-token"},
            "dojo-migration-secret.enc.yaml": {"database-url"},
            "ghcr-pull-secret.enc.yaml": {".dockerconfigjson"},
        }
        for filename, keys in expected.items():
            document = yaml.safe_load((ACTIVE / filename).read_text())
            values = document.get("stringData", document.get("data"))
            self.assertEqual(set(values), keys)
            self.assertTrue(
                all(value.startswith("ENC[AES256_GCM,") for value in values.values())
            )
            self.assertEqual(document["sops"]["encrypted_regex"], "^(data|stringData)$")

    def test_network_reach_is_only_database_and_temporal(self) -> None:
        policies = {
            doc["metadata"]["name"]: doc
            for doc in self.documents
            if doc["kind"] == "NetworkPolicy"
        }
        self.assertEqual(
            set(policies),
            {
                "allow-dojo-to-postgresql",
                "allow-dojo-to-temporal",
                "allow-dojo-from-execution",
                "allow-dojo-bootstrap-to-postgresql",
            },
        )
        temporal = policies["allow-dojo-to-temporal"]
        self.assertEqual(temporal["spec"]["egress"][0]["ports"], [{"protocol": "TCP", "port": 7233}])
        database = policies["allow-dojo-to-postgresql"]
        self.assertEqual(database["spec"]["egress"][0]["ports"], [{"protocol": "TCP", "port": 5432}])

    def test_separate_flux_controller_preserves_phase7(self) -> None:
        flux = yaml.safe_load(FLUX.read_text())
        self.assertEqual(
            flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase8-dojo-preproduction",
        )
        self.assertTrue(flux["spec"]["prune"])
        self.assertEqual(
            [item["name"] for item in flux["spec"]["dependsOn"]],
            ["starbase-foundation", "databases"],
        )
        checks = {
            (item["kind"], item["namespace"], item["name"])
            for item in flux["spec"]["healthChecks"]
        }
        self.assertEqual(
            checks,
            {
                ("Job", "database", "starbase-dojo-database-bootstrap-v1-66e26e025d98"),
                ("Job", "starbase-execution", "starbase-dojo-migrate-rc6-5d13884264d9"),
                ("Deployment", "starbase-execution", "starbase-dojo-runtime"),
                ("Deployment", "starbase-execution", "starbase-dojo-workflow-worker"),
            },
        )
        aggregate = yaml.safe_load(FLUX_AGGREGATE.read_text())
        self.assertIn("starbase-dojo-kustomization.yaml", aggregate["resources"])


if __name__ == "__main__":
    unittest.main()
