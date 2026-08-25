from __future__ import annotations

import json
import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "infrastructure/gitops/apps/starbase-phase4a"
FOUNDATION_OVERLAY = ROOT / "infrastructure/gitops/apps/starbase-phase4a-foundation"
APPS_KUSTOMIZATION = ROOT / "infrastructure/gitops/apps/kustomization.yaml"
FOUNDATION_FLUX = (
    ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
)
FLUX_AGGREGATE = ROOT / "infrastructure/gitops/flux-system/kustomization.yaml"
PROMOTION_INPUT = ROOT / "infrastructure/gitops/apps/starbase/promotion-input.json"
PROMOTION_LOCK = ROOT / "infrastructure/gitops/apps/starbase/promotion-lock.json"


def render_documents(path: Path) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


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

    def test_only_fail_closed_foundation_is_flux_activated(self) -> None:
        aggregate = yaml.safe_load(APPS_KUSTOMIZATION.read_text())
        self.assertNotIn("starbase-phase4a-foundation/", aggregate["resources"])
        self.assertNotIn("starbase-phase4a/", aggregate["resources"])
        self.assertNotIn("starbase/", aggregate["resources"])

        foundation_flux = yaml.safe_load(FOUNDATION_FLUX.read_text())
        flux_aggregate = yaml.safe_load(FLUX_AGGREGATE.read_text())
        self.assertIn(
            "starbase-foundation-kustomization.yaml", flux_aggregate["resources"]
        )
        self.assertEqual(foundation_flux["metadata"]["name"], "starbase-foundation")
        self.assertEqual(
            foundation_flux["metadata"]["labels"]["starbase.io/activation-wave"],
            "phase4a-restore-v1",
        )
        self.assertEqual(
            foundation_flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase4a-foundation",
        )
        dependency = foundation_flux["spec"]["dependsOn"][0]
        self.assertEqual(dependency["name"], "databases")
        for requirement in (
            "starbase.io/activation-wave",
            "exists(e, e.type == 'Ready' && e.status == 'True')",
            "dep.metadata.generation == dep.status.observedGeneration",
        ):
            self.assertIn(requirement, dependency["readyExpr"])
        self.assertNotIn(".all(", dependency["readyExpr"])

        expected_activation = {
            "bundle": "flux-referenced-inert-foundation",
            "core": "flux-referenced-zero-replicas",
            "github_connector": "intentionally-disabled-zero-replicas",
            "kubernetes_connector": "flux-referenced-zero-replicas",
            "migrations": "flux-referenced-suspended",
        }
        self.assertEqual(
            json.loads(PROMOTION_INPUT.read_text())["expected_activation"],
            expected_activation,
        )
        self.assertEqual(
            json.loads(PROMOTION_LOCK.read_text())["activation"],
            expected_activation,
        )

        foundation = render_documents(FOUNDATION_OVERLAY)
        kinds = {document["kind"] for document in foundation}
        self.assertNotIn("Secret", kinds)
        self.assertNotIn("Ingress", kinds)
        self.assertNotIn("Certificate", kinds)
        self.assertFalse(
            any(
                document["kind"] == "ConfigMap"
                and document["metadata"]["name"] == "starbase-authentik-blueprint"
                for document in foundation
            )
        )
        self.assertTrue(
            any(document["kind"] == "ResourceQuota" for document in foundation)
        )
        self.assertTrue(
            any(document["kind"] == "NetworkPolicy" for document in foundation)
        )
        for document in foundation:
            if document["kind"] == "Deployment":
                self.assertEqual(document["spec"]["replicas"], 0)
            if document["kind"] == "Job":
                self.assertTrue(document["spec"]["suspend"])

    def test_contract_contains_no_secret_or_mutable_image(self) -> None:
        self.assertEqual(len(self.documents), 48)
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
        self.assertNotIn("--set=password=", script)
        self.assertIn(r"\getenv role STARBASE_BOOTSTRAP_ROLE", script)
        self.assertIn(r"\getenv credential STARBASE_BOOTSTRAP_CREDENTIAL", script)
        self.assertIn("SET log_statement = 'none';", script)

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
        self.assertEqual(core["spec"]["replicas"], 0)

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
        self.assertIn("id: starbase-operators-group", blueprint)
        self.assertIn("id: starbase-application", blueprint)
        self.assertIn("model: authentik_policies.policybinding", blueprint)
        self.assertIn("target: !KeyOf starbase-application", blueprint)
        self.assertIn("group: !KeyOf starbase-operators-group", blueprint)
        self.assertIn("policy_engine_mode: all", blueprint)

    def test_ingress_exposes_only_the_browser_service(self) -> None:
        ingress = self.object("Ingress", "starbase-system", "starbase")
        backend = ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]
        self.assertEqual(backend["name"], "starbase-core")
        self.assertEqual(backend["port"]["number"], 80)
        self.assertNotIn("starbase-core-api", str(ingress))
        self.assertNotIn(
            "cert-manager.io/cluster-issuer",
            ingress["metadata"].get("annotations", {}),
        )
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

        connector_api_egress = self.object(
            "NetworkPolicy", "starbase-connectors", "allow-kubernetes-connector-to-api"
        )
        self.assertEqual(
            connector_api_egress["spec"]["podSelector"]["matchLabels"],
            {"app.kubernetes.io/name": "starbase-kubernetes-connector"},
        )
        connector_paths = {
            (rule["to"][0]["ipBlock"]["cidr"], rule["ports"][0]["port"])
            for rule in connector_api_egress["spec"]["egress"]
        }
        self.assertEqual(
            connector_paths, {("10.43.0.1/32", 443), ("100.92.107.71/32", 6443)}
        )

        kubernetes_connector = self.object(
            "Deployment", "starbase-connectors", "starbase-kubernetes-connector"
        )
        self.assertEqual(kubernetes_connector["spec"]["replicas"], 0)

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
