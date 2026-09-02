from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "infrastructure/gitops/apps/starbase-phase9-foundation"
DOJO = ROOT / "infrastructure/gitops/apps/starbase-phase9-dojo"
FOUNDATION_FLUX = ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
DOJO_FLUX = ROOT / "infrastructure/gitops/flux-system/starbase-dojo-kustomization.yaml"
SOURCE_REVISION = (
    "d688bec5f85795cbb6e16beaf92ef29247875f10"  # pragma: allowlist secret
)
IMAGES = {
    "core": "ghcr.io/x-mckay/starbase/core@sha256:97eb49b3c43ad3ffe3308ce510088e54270d7b3dfcc08e313ff0021eb34cff88",
    "web": "ghcr.io/x-mckay/starbase/web@sha256:9d2388029599ac045992ffe76fd40145c50e31419fa7d356158da6a04c49f568",
    "github": "ghcr.io/x-mckay/starbase/github-connector@sha256:854b8970bc2ca5c5f09e2644574fcf769defa49e78751e6cc7d7e0cc09211215",
    "kubernetes": "ghcr.io/x-mckay/starbase/kubernetes-connector@sha256:26ed29b950e3fe87dd199496924432b7b71692918ce5b1d1dbf248db48599c08",
    "dojo": "ghcr.io/x-mckay/starbase/dojo-runtime@sha256:7030dc8fd186875cd1ff1136ef56148ad5af5bdc1682452d4c8194b02ed62d32",
}


def render(path: Path) -> list[dict]:
    content = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [document for document in yaml.safe_load_all(content) if document]


class StarbasePhase9GovernedProposalUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.foundation = render(FOUNDATION)
        cls.dojo = render(DOJO)
        cls.documents = cls.foundation + cls.dojo
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

    def test_preserves_phase7_and_phase8_as_explicit_lineage(self) -> None:
        foundation = yaml.safe_load((FOUNDATION / "kustomization.yaml").read_text())
        dojo = yaml.safe_load((DOJO / "kustomization.yaml").read_text())
        self.assertIn("../starbase-phase7-github-canary", foundation["resources"])
        self.assertIn("../starbase-phase8-dojo-preproduction", dojo["resources"])

    def test_all_active_workloads_use_one_signed_successor(self) -> None:
        expected = {
            ("starbase-system", "starbase-core", "core"): IMAGES["core"],
            ("starbase-system", "starbase-core", "web"): IMAGES["web"],
            ("starbase-connectors", "starbase-preview-fixture", "connector"): IMAGES["github"],
            ("starbase-connectors", "starbase-github-connector", "connector"): IMAGES["github"],
            ("starbase-connectors", "starbase-kubernetes-connector", "connector"): IMAGES["kubernetes"],
        }
        for (namespace, deployment_name, container_name), image in expected.items():
            deployment = self.object("Deployment", namespace, deployment_name)
            self.assertEqual(self.container(deployment, container_name)["image"], image)
            annotations = deployment["spec"]["template"]["metadata"]["annotations"]
            self.assertEqual(annotations["starbase.io/release"], "0.1.0-rc.8")
            self.assertEqual(annotations["starbase.io/source-revision"], SOURCE_REVISION)

        for deployment_name, names in {
            "starbase-dojo-runtime": (
                "dojo-server",
                "sandbox-fixture",
                "advisory-fixture",
                "evaluation-activity-worker",
            ),
            "starbase-dojo-workflow-worker": ("workflow-worker",),
        }.items():
            deployment = self.object("Deployment", "starbase-execution", deployment_name)
            for name in names:
                self.assertEqual(self.container(deployment, name)["image"], IMAGES["dojo"])
            annotations = deployment["spec"]["template"]["metadata"]["annotations"]
            self.assertEqual(annotations["starbase.io/release"], "0.1.0-rc.8")
            self.assertEqual(annotations["starbase.io/source-revision"], SOURCE_REVISION)

        migration = self.object(
            "Job", "starbase-execution", "starbase-dojo-migrate-rc6-5d13884264d9"
        )
        self.assertIn("@sha256:5d13884264d9", migration["spec"]["template"]["spec"]["containers"][0]["image"])

    def test_dojo_is_tls_only_across_namespaces_and_not_ingressed(self) -> None:
        service = self.object("Service", "starbase-execution", "starbase-dojo")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            service["spec"]["ports"],
            [{"name": "https", "port": 8443, "protocol": "TCP", "targetPort": "dojo-tls"}],
        )
        self.assertFalse(
            any(
                document["kind"] == "Ingress"
                and document["metadata"].get("namespace") == "starbase-execution"
                for document in self.dojo
            )
        )

        certificate = self.object("Certificate", "starbase-execution", "starbase-dojo-tls")
        self.assertEqual(
            certificate["spec"]["dnsNames"],
            ["starbase-dojo.starbase-execution.svc.cluster.local"],
        )
        self.assertEqual(certificate["spec"]["duration"], "2160h")
        self.assertEqual(certificate["spec"]["renewBefore"], "360h")
        self.assertEqual(certificate["spec"]["privateKey"]["rotationPolicy"], "Always")

        core = self.object("Deployment", "starbase-system", "starbase-core")
        core_env = self.environment(self.container(core, "core"))
        self.assertEqual(
            core_env["STARBASE_DOJO_URL"]["value"],
            "https://starbase-dojo.starbase-execution.svc.cluster.local:8443",
        )
        self.assertEqual(
            core_env["STARBASE_DOJO_READ_TOKEN"]["valueFrom"]["secretKeyRef"],
            {"name": "starbase-dojo-reader", "key": "read-token"},
        )
        self.assertEqual(
            core_env["STARBASE_DOJO_CA_FILE"]["value"],
            "/var/run/secrets/starbase.io/dojo/ca.crt",
        )

        runtime = self.object("Deployment", "starbase-execution", "starbase-dojo-runtime")
        server = self.container(runtime, "dojo-server")
        server_env = self.environment(server)
        self.assertEqual(server_env["STARBASE_DOJO_ADDRESS"]["value"], "127.0.0.1:8090")
        self.assertEqual(server_env["STARBASE_DOJO_TLS_ADDRESS"]["value"], "0.0.0.0:8443")
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertEqual(server[probe]["httpGet"]["scheme"], "HTTPS")
            self.assertEqual(server[probe]["httpGet"]["port"], "dojo-tls")

        source = self.object("NetworkPolicy", "starbase-system", "allow-core-to-dojo-tls")
        destination = self.object("NetworkPolicy", "starbase-execution", "allow-dojo-tls-from-core")
        self.assertEqual(source["spec"]["egress"][0]["ports"], [{"protocol": "TCP", "port": 8443}])
        self.assertEqual(destination["spec"]["ingress"][0]["ports"], [{"protocol": "TCP", "port": 8443}])

    def test_proposal_remains_fixture_only_and_non_authoritative(self) -> None:
        runtime = self.object("Deployment", "starbase-execution", "starbase-dojo-runtime")
        self.assertEqual(runtime["metadata"]["annotations"]["starbase.io/external-authority"], "false")
        advisory = self.environment(self.container(runtime, "advisory-fixture"))
        activity = self.environment(self.container(runtime, "evaluation-activity-worker"))
        self.assertEqual(advisory["STARBASE_ADVISORY_FIXTURE_OUTCOME"]["value"], "propose")
        self.assertEqual(advisory["STARBASE_ADVISORY_FIXTURE_MODEL"]["value"], "starbase-proposal-fixture-v1")
        self.assertEqual(activity["STARBASE_EVALUATION_MODEL"]["value"], "starbase-proposal-fixture-v1")
        self.assertEqual(activity["STARBASE_EVALUATION_RUNTIME_MODE"]["value"], "local-fixture")

        environment = self.object("ConfigMap", "starbase-execution", "starbase-dojo-evaluation-environment-v1")
        self.assertIn('"network": {"default": "deny", "allow": []}', environment["data"]["environment.json"])

    def test_secret_and_ca_contracts_are_encrypted_and_owned(self) -> None:
        for path, keys in (
            (FOUNDATION / "dojo-reader-secret.enc.yaml", {"read-token"}),
            (DOJO / "dojo-ca-secret.enc.yaml", {"tls.crt", "tls.key"}),
        ):
            document = yaml.safe_load(path.read_text())
            values = document.get("data", document.get("stringData"))
            self.assertEqual(set(values), keys)
            self.assertTrue(all(value.startswith("ENC[AES256_GCM,") for value in values.values()))
            self.assertEqual(document["sops"]["encrypted_regex"], "^(data|stringData)$")

        public_ca = self.object("ConfigMap", "starbase-system", "starbase-dojo-ca")
        self.assertTrue(public_ca["data"]["ca.crt"].startswith("-----BEGIN CERTIFICATE-----"))
        self.assertEqual(public_ca["metadata"]["annotations"]["starbase.io/rotation-owner"], "Al-McKay")
        self.assertEqual(public_ca["metadata"]["annotations"]["starbase.io/rotate-before"], "2027-09-03T22:26:07Z")

    def test_flux_avoids_dependency_cycle_and_health_gates_tls(self) -> None:
        foundation = yaml.safe_load(FOUNDATION_FLUX.read_text())
        dojo = yaml.safe_load(DOJO_FLUX.read_text())
        self.assertEqual(foundation["spec"]["path"], "./infrastructure/gitops/apps/starbase-phase9-foundation")
        self.assertEqual(dojo["spec"]["path"], "./infrastructure/gitops/apps/starbase-phase9-dojo")
        self.assertEqual([item["name"] for item in dojo["spec"]["dependsOn"]], ["databases"])
        checks = {
            (item["kind"], item["namespace"], item["name"])
            for item in dojo["spec"]["healthChecks"]
        }
        self.assertIn(("Certificate", "starbase-execution", "starbase-dojo-tls"), checks)
        self.assertIn(("Deployment", "starbase-execution", "starbase-dojo-runtime"), checks)


if __name__ == "__main__":
    unittest.main()
