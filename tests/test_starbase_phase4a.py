from __future__ import annotations

import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "infrastructure/gitops/apps/starbase-phase4a"
APPS_KUSTOMIZATION = ROOT / "infrastructure/gitops/apps/kustomization.yaml"


class StarbasePhase4AContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["kubectl", "kustomize", str(OVERLAY)],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.rendered = result.stdout
        cls.documents = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
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

    def test_overlay_remains_outside_flux_activation(self) -> None:
        aggregate = APPS_KUSTOMIZATION.read_text()
        self.assertNotIn("starbase-phase4a", aggregate)
        self.assertNotIn("starbase/", aggregate)

    def test_contract_contains_no_secret_or_mutable_image(self) -> None:
        self.assertEqual(len(self.documents), 47)
        self.assertFalse(any(doc["kind"] == "Secret" for doc in self.documents))
        for doc in self.documents:
            pod = None
            if doc["kind"] == "Deployment":
                pod = doc["spec"]["template"]["spec"]
            elif doc["kind"] == "Job":
                pod = doc["spec"]["template"]["spec"]
            if pod is None:
                continue
            for container in pod.get("initContainers", []) + pod.get("containers", []):
                self.assertRegex(container["image"], r"@sha256:[0-9a-f]{64}$")

    def test_database_bootstrap_is_bounded_and_fail_closed(self) -> None:
        script = self.object(
            "ConfigMap", "database", "starbase-database-bootstrap-v1"
        )["data"]["bootstrap.sh"]
        expected_name = f"starbase-database-bootstrap-v1-{sha256(script.encode()).hexdigest()[:12]}"
        job = self.object("Job", "database", expected_name)
        self.assertEqual(
            job["metadata"]["annotations"]["starbase.io/bootstrap-contract-digest"],
            f"sha256:{sha256(script.encode()).hexdigest()}",
        )
        subprocess.run(["sh", "-n"], input=script, check=True, text=True)
        self.assertEqual(job["metadata"]["annotations"]["starbase.io/activation-state"], "blocked")
        self.assertEqual(job["spec"]["suspend"], True)
        self.assertEqual(job["spec"]["backoffLimit"], 1)
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 300)
        self.assertEqual(job["spec"]["ttlSecondsAfterFinished"], 86400)
        pod = job["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["serviceAccountName"], "starbase-database-bootstrap")
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"][0]
            ["preference"]["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        container = pod["containers"][0]
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertIn("requests", container["resources"])
        self.assertIn("limits", container["resources"])

        for database in ("starbase_core", "starbase_gateway"):
            self.assertIn(database, script)
        for role in (
            "starbase_core_migrator",
            "starbase_core_runtime",
            "starbase_gateway_migrator",
            "starbase_gateway_runtime",
        ):
            self.assertIn(role, script)
        self.assertIn(
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION", script
        )
        self.assertNotIn("SUPERUSER CREATEDB", script)
        self.assertNotIn("GRANT ALL ON DATABASE", script)

    def test_runtime_bindings_use_separate_secret_contracts(self) -> None:
        core = self.object("Deployment", "starbase-system", "starbase-core")
        container = next(
            container
            for container in core["spec"]["template"]["spec"]["containers"]
            if container["name"] == "core"
        )
        env = {entry["name"]: entry for entry in container["env"]}
        self.assertEqual(
            env["STARBASE_CORE_DATABASE_URL"]["valueFrom"]["secretKeyRef"],
            {"name": "starbase-core-runtime", "key": "database-url"},
        )
        self.assertNotIn("STARBASE_CORE_MIGRATION_DATABASE_URL", env)
        self.assertEqual(env["STARBASE_OIDC_CLIENT_ID"]["value"], "starbase-kubani")
        self.assertEqual(
            env["STARBASE_OIDC_ISSUER"]["value"],
            "https://auth.almckay.io/application/o/starbase/",
        )
        self.assertEqual(env["STARBASE_OIDC_REQUIRED_GROUPS"]["value"], "starbase-operators")
        self.assertEqual(env["STARBASE_EXTERNAL_URL"]["value"], "https://starbase.almckay.io")
        self.assertEqual(
            env["STARBASE_WORKLOAD_OIDC_ISSUER"]["value"],
            "https://kubernetes.default.svc.cluster.local",
        )

        mounts = {mount["name"]: mount for mount in container["volumeMounts"]}
        self.assertTrue(mounts["gateway-runtime"]["readOnly"])
        self.assertEqual(
            env["STARBASE_GATEWAY_DATABASE_URL_FILE"]["value"],
            "/var/run/secrets/starbase.io/gateway/database-url",
        )
        self.assertEqual(
            env["STARBASE_SESSION_ENCRYPTION_KEY_FILE"]["value"],
            "/var/run/secrets/starbase.io/gateway/session-encryption-key",
        )

        core_migration = self.object(
            "Job", "starbase-system", "starbase-core-migrate-22bfaa3b1e8f"
        )
        gateway_migration = self.object(
            "Job", "starbase-system", "starbase-gateway-migrate-38db19887578"
        )
        for job, secret_name in (
            (core_migration, "starbase-core-migration"),
            (gateway_migration, "starbase-gateway-migration"),
        ):
            self.assertTrue(job["spec"]["suspend"])
            migration_container = job["spec"]["template"]["spec"]["containers"][0]
            self.assertEqual(
                migration_container["env"][0]["valueFrom"]["secretKeyRef"],
                {"name": secret_name, "key": "database-url"},
            )

    def test_authentik_blueprint_is_public_pkce_and_group_bounded(self) -> None:
        blueprint = self.object(
            "ConfigMap", "auth", "starbase-authentik-blueprint"
        )["data"]["starbase.yaml"]
        self.assertIn("model: authentik_providers_oauth2.oauth2provider", blueprint)
        self.assertIn("client_type: public", blueprint)
        self.assertIn("client_id: starbase-kubani", blueprint)
        self.assertIn("grant_types:\n        - authorization_code", blueprint)
        self.assertNotIn("client_secret", blueprint)
        self.assertIn("https://starbase.almckay.io/api/v1/auth/callback", blueprint)
        self.assertIn("matching_mode: strict", blueprint)
        self.assertIn('"groups"', blueprint)
        self.assertIn("request.user.groups.all()", blueprint)

    def test_ingress_exposes_only_the_browser_service(self) -> None:
        ingress = self.object("Ingress", "starbase-system", "starbase")
        backend = ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]
        self.assertEqual(backend["name"], "starbase-core")
        self.assertEqual(backend["port"]["number"], 80)
        self.assertNotIn("starbase-core-api", str(ingress))
        certificate = self.object("Certificate", "starbase-system", "starbase-tls")
        self.assertEqual(certificate["spec"]["dnsNames"], ["starbase.almckay.io"])

    def test_network_policy_is_exact_and_github_stays_disabled(self) -> None:
        db_ingress = self.object(
            "NetworkPolicy", "database", "allow-starbase-postgresql"
        )
        source = db_ingress["spec"]["ingress"][0]["from"][0]
        self.assertEqual(
            source["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"],
            "starbase-system",
        )
        self.assertEqual(db_ingress["spec"]["ingress"][0]["ports"][0]["port"], 5432)

        api_egress = self.object(
            "NetworkPolicy", "starbase-system", "allow-core-to-workload-issuer"
        )
        paths = {
            (
                rule["to"][0]["ipBlock"]["cidr"],
                rule["ports"][0]["port"],
            )
            for rule in api_egress["spec"]["egress"]
        }
        self.assertEqual(paths, {("10.43.0.1/32", 443), ("100.92.107.71/32", 6443)})

        github = self.object(
            "Deployment", "starbase-connectors", "starbase-github-connector"
        )
        self.assertEqual(github["spec"]["replicas"], 0)
        self.assertFalse(
            any(
                doc["kind"] == "NetworkPolicy"
                and "github" in doc["metadata"]["name"].lower()
                for doc in self.documents
            )
        )

    def test_resource_governance_preserves_measured_headroom(self) -> None:
        quota = self.object("ResourceQuota", "starbase-system", "starbase-system")
        self.assertEqual(quota["spec"]["hard"]["requests.cpu"], "500m")
        self.assertEqual(quota["spec"]["hard"]["requests.memory"], "512Mi")
        self.assertEqual(quota["spec"]["hard"]["limits.cpu"], "3")
        self.assertEqual(quota["spec"]["hard"]["limits.memory"], "2Gi")


if __name__ == "__main__":
    unittest.main()
