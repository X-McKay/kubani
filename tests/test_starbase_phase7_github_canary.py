from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "infrastructure/gitops/apps/starbase-phase7-github-canary"
FOUNDATION_FLUX = (
    ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
)
SECRET = ACTIVE / "github-app-secret.enc.yaml"
GITHUB_IMAGE = (
    "ghcr.io/x-mckay/starbase/github-connector@"
    "sha256:cdec332a5c181a0038373c1c9d3b4ac4f6eff480b51ffca67c786be2b89d93c8"
)


class StarbasePhase7GitHubCanaryTests(unittest.TestCase):
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

    def test_activates_only_the_read_only_github_canary(self) -> None:
        expected_replicas = {
            ("starbase-system", "starbase-core"): 1,
            ("starbase-connectors", "starbase-preview-fixture"): 1,
            ("starbase-connectors", "starbase-kubernetes-connector"): 1,
            ("starbase-connectors", "starbase-github-connector"): 1,
        }
        observed = {
            (
                doc["metadata"].get("namespace", ""),
                doc["metadata"]["name"],
            ): doc["spec"]["replicas"]
            for doc in self.documents
            if doc["kind"] == "Deployment"
        }
        self.assertEqual(observed, expected_replicas)

        deployment = self.object(
            "Deployment", "starbase-connectors", "starbase-github-connector"
        )
        self.assertEqual(
            deployment["metadata"]["annotations"],
            {
                "starbase.io/activation-state": (
                    "authorized-preproduction-github-canary"
                ),
                "starbase.io/activation-stage": "phase7-github-observation",
            },
        )
        template = deployment["spec"]["template"]
        self.assertIsNone(
            template["metadata"]["annotations"].get("starbase.io/blocker")
        )
        pod = template["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        connector = next(
            item for item in pod["containers"] if item["name"] == "connector"
        )
        self.assertEqual(connector["image"], GITHUB_IMAGE)
        self.assertEqual(connector["imagePullPolicy"], "IfNotPresent")
        environment = {item["name"]: item for item in connector["env"]}
        self.assertEqual(environment["STARBASE_CONNECTOR_MODE"]["value"], "github")
        self.assertEqual(
            environment["STARBASE_GITHUB_REPOSITORY"]["value"], "X-McKay/Starbase"
        )

    def test_core_requires_and_authorizes_each_exact_canary_source(self) -> None:
        core = self.object("Deployment", "starbase-system", "starbase-core")
        container = next(
            item
            for item in core["spec"]["template"]["spec"]["containers"]
            if item["name"] == "core"
        )
        environment = {
            item["name"]: item["value"]
            for item in container["env"]
            if "value" in item
        }
        self.assertEqual(
            environment["STARBASE_EXPECTED_SOURCES"],
            '{"github:X-McKay/Starbase":"github",'
            '"github:starbase-preview/synthetic-observation":"github",'
            '"kubernetes:kubani:starbase-namespaces-v1":"kubernetes"}',
        )
        self.assertEqual(
            environment["STARBASE_CONNECTOR_IDENTITIES"],
            '{"system:serviceaccount:starbase-connectors:'
            'starbase-github-connector":["github"],'
            '"system:serviceaccount:starbase-connectors:'
            'starbase-kubernetes-connector":["kubernetes"],'
            '"system:serviceaccount:starbase-connectors:'
            'starbase-preview-fixture":["github"]}',
        )

    def test_github_identity_is_exact_and_encrypted_at_rest(self) -> None:
        encrypted = yaml.safe_load(SECRET.read_text())
        self.assertEqual(encrypted["apiVersion"], "v1")
        self.assertEqual(encrypted["kind"], "Secret")
        self.assertEqual(encrypted["metadata"], {
            "name": "starbase-github-app",
            "namespace": "starbase-connectors",
        })
        self.assertEqual(
            set(encrypted["data"]),
            {"app-id", "installation-id", "private-key.pem"},
        )
        self.assertTrue(
            all(
                isinstance(value, str) and value.startswith("ENC[AES256_GCM,")
                for value in encrypted["data"].values()
            )
        )
        self.assertEqual(encrypted["sops"]["encrypted_regex"], "^(data|stringData)$")

        rendered = self.object(
            "Secret", "starbase-connectors", "starbase-github-app"
        )
        self.assertEqual(
            set(rendered["data"]),
            {"app-id", "installation-id", "private-key.pem"},
        )

    def test_public_https_exception_stays_connector_only(self) -> None:
        policy = self.object(
            "NetworkPolicy",
            "starbase-connectors",
            "allow-github-connector-public-https",
        )
        self.assertEqual(
            policy["spec"]["podSelector"],
            {
                "matchLabels": {
                    "app.kubernetes.io/name": "starbase-github-connector"
                }
            },
        )
        self.assertEqual(
            policy["spec"]["egress"][0]["ports"],
            [{"protocol": "TCP", "port": 443}],
        )
        exclusions = set(policy["spec"]["egress"][0]["to"][0]["ipBlock"]["except"])
        for network in (
            "10.0.0.0/8",
            "100.64.0.0/10",
            "127.0.0.0/8",
            "169.254.0.0/16",
            "172.16.0.0/12",
            "192.168.0.0/16",
        ):
            self.assertIn(network, exclusions)

    def test_flux_activates_and_health_gates_every_canary(self) -> None:
        flux = yaml.safe_load(FOUNDATION_FLUX.read_text())
        self.assertEqual(
            flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase7-github-canary",
        )
        checks = {
            (item["kind"], item["namespace"], item["name"])
            for item in flux["spec"]["healthChecks"]
        }
        for identity in (
            ("Deployment", "starbase-system", "starbase-core"),
            ("Deployment", "starbase-connectors", "starbase-preview-fixture"),
            ("Deployment", "starbase-connectors", "starbase-kubernetes-connector"),
            ("Deployment", "starbase-connectors", "starbase-github-connector"),
        ):
            self.assertIn(identity, checks)


if __name__ == "__main__":
    unittest.main()
