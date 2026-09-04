from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PREPARED = (
    ROOT / "infrastructure/gitops/apps/starbase-phase6-github-canary-prepared"
)
FOUNDATION_FLUX = (
    ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
)
IMAGE = (
    "ghcr.io/x-mckay/starbase/github-connector@"
    "sha256:cdec332a5c181a0038373c1c9d3b4ac4f6eff480b51ffca67c786be2b89d93c8"
)
SOURCE_REVISION = (
    "3f1a5962090e7cb54caaf213d343d1906997f017"  # pragma: allowlist secret
)


class StarbasePhase6GitHubCanaryPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rendered = subprocess.run(
            ["kubectl", "kustomize", str(PREPARED)],
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

    def test_prepares_exact_image_but_remains_inactive(self) -> None:
        deployment = self.object(
            "Deployment", "starbase-connectors", "starbase-github-connector"
        )
        self.assertEqual(deployment["spec"]["replicas"], 0)
        self.assertEqual(
            deployment["metadata"]["annotations"],
            {
                "starbase.io/activation-state": "prepared-inactive-github-canary",
                "starbase.io/activation-stage": "phase6-github-observation",
            },
        )
        template = deployment["spec"]["template"]
        self.assertEqual(
            template["metadata"]["annotations"],
            {
                "starbase.io/activation-state": "prepared-inactive-github-canary",
                "starbase.io/activation-stage": "phase6-github-observation",
                "starbase.io/source-revision": SOURCE_REVISION,
                "starbase.io/artifact-class": "owner-local-preproduction",
                "starbase.io/blocker": "github-app-installation-and-secret",
            },
        )
        pod = template["spec"]
        connector = next(
            item for item in pod["containers"] if item["name"] == "connector"
        )
        self.assertEqual(connector["image"], IMAGE)
        self.assertEqual(connector["imagePullPolicy"], "IfNotPresent")
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0],
            {
                "key": "kubernetes.io/hostname",
                "operator": "In",
                "values": ["asio", "strix"],
            },
        )

    def test_uses_only_the_reviewed_secret_file_contract(self) -> None:
        deployment = self.object(
            "Deployment", "starbase-connectors", "starbase-github-connector"
        )
        pod = deployment["spec"]["template"]["spec"]
        connector = next(
            item for item in pod["containers"] if item["name"] == "connector"
        )
        env = {item["name"]: item for item in connector["env"]}
        self.assertEqual(
            env["STARBASE_GITHUB_APP_ID"]["valueFrom"]["secretKeyRef"],
            {"name": "starbase-github-app", "key": "app-id"},
        )
        self.assertEqual(
            env["STARBASE_GITHUB_INSTALLATION_ID"]["valueFrom"]["secretKeyRef"],
            {"name": "starbase-github-app", "key": "installation-id"},
        )
        self.assertEqual(
            env["STARBASE_GITHUB_PRIVATE_KEY_FILE"]["value"],
            "/var/run/secrets/starbase.io/github/private-key.pem",
        )
        volume = next(
            item
            for item in pod["volumes"]
            if item["name"] == "github-app-identity"
        )
        self.assertEqual(
            volume["secret"],
            {
                "secretName": "starbase-github-app",  # pragma: allowlist secret
                "defaultMode": 0o440,
                "items": [{"key": "private-key.pem", "path": "private-key.pem"}],
            },
        )
        self.assertIn(
            {
                "name": "github-app-identity",
                "mountPath": "/var/run/secrets/starbase.io/github",
                "readOnly": True,
            },
            connector["volumeMounts"],
        )

    def test_does_not_add_secret_or_live_source(self) -> None:
        self.assertNotIn(
            ("Secret", "starbase-connectors", "starbase-github-app"),
            self.by_identity,
        )
        core = self.object("Deployment", "starbase-system", "starbase-core")
        core_container = next(
            item
            for item in core["spec"]["template"]["spec"]["containers"]
            if item["name"] == "core"
        )
        expected_sources = next(
            item["value"]
            for item in core_container["env"]
            if item["name"] == "STARBASE_EXPECTED_SOURCES"
        )
        self.assertNotIn("github:X-McKay/Starbase", expected_sources)

    def test_public_https_exception_selects_only_the_github_connector(self) -> None:
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
        self.assertEqual(policy["spec"]["policyTypes"], ["Egress"])
        self.assertEqual(
            policy["spec"]["egress"],
            [
                {
                    "to": [
                        {
                            "ipBlock": {
                                "cidr": "0.0.0.0/0",
                                "except": [
                                    "0.0.0.0/8",
                                    "10.0.0.0/8",
                                    "100.64.0.0/10",
                                    "127.0.0.0/8",
                                    "169.254.0.0/16",
                                    "172.16.0.0/12",
                                    "192.0.0.0/24",
                                    "192.0.2.0/24",
                                    "192.88.99.0/24",
                                    "192.168.0.0/16",
                                    "198.18.0.0/15",
                                    "198.51.100.0/24",
                                    "203.0.113.0/24",
                                    "224.0.0.0/4",
                                    "240.0.0.0/4",
                                ],
                            }
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 443}],
                }
            ],
        )

    def test_flux_activates_the_corrected_phase7_overlay(self) -> None:
        foundation = yaml.safe_load(FOUNDATION_FLUX.read_text())
        self.assertEqual(
            foundation["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase10-autonomous-crew-prepared",
        )


if __name__ == "__main__":
    unittest.main()
