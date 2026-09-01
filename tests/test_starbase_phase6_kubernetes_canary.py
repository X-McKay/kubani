from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANARY = ROOT / "infrastructure/gitops/apps/starbase-phase6-kubernetes-canary"
FOUNDATION_FLUX = (
    ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
)
CONNECTOR_IMAGE = (
    "ghcr.io/x-mckay/starbase/kubernetes-connector@"
    "sha256:70595d0171b481ae78b221e52b11f38a67aedf6768974fb77b19a875c42ae7c5"
)
CORE_IMAGE = (
    "ghcr.io/x-mckay/starbase/core@"
    "sha256:b906d2d2d3e2aff743974cd829b548932101615f9f10ca2ad3c5413b84eb4809"
)
SOURCE_REVISION = (
    "400711d9fbb3e068f6dff274e58db26bcae934e3"  # pragma: allowlist secret
)


class StarbasePhase6KubernetesCanaryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rendered = subprocess.run(
            ["kubectl", "kustomize", str(CANARY)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        cls.rendered = rendered
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

    def test_activates_only_the_bounded_kubernetes_canary(self) -> None:
        expected_replicas = {
            "starbase-core": 1,
            "starbase-preview-fixture": 1,
            "starbase-kubernetes-connector": 1,
            "starbase-github-connector": 0,
        }
        for name, replicas in expected_replicas.items():
            namespace = (
                "starbase-system" if name == "starbase-core" else "starbase-connectors"
            )
            self.assertEqual(
                self.object("Deployment", namespace, name)["spec"]["replicas"],
                replicas,
            )

        for name in (
            "starbase-core-migrate-0da307f3148a",
            "starbase-gateway-migrate-f2fa2f551602",
        ):
            self.assertTrue(self.object("Job", "starbase-system", name)["spec"]["suspend"])

    def test_core_requires_only_the_fixture_and_kubernetes_sources(self) -> None:
        core = self.object("Deployment", "starbase-system", "starbase-core")
        self.assertEqual(
            core["metadata"]["annotations"],
            {
                "starbase.io/activation-state": (
                    "authorized-preproduction-kubernetes-canary"
                ),
                "starbase.io/activation-stage": "phase6-kubernetes-observation",
            },
        )
        pod = core["spec"]["template"]
        self.assertEqual(
            pod["metadata"]["annotations"]["starbase.io/activation-state"],
            "authorized-preproduction-kubernetes-canary",
        )
        env = {
            item["name"]: item.get("value")
            for item in next(
                item for item in pod["spec"]["containers"] if item["name"] == "core"
            )["env"]
        }
        core_container = next(
            item for item in pod["spec"]["containers"] if item["name"] == "core"
        )
        self.assertEqual(core_container["image"], CORE_IMAGE)
        self.assertEqual(
            pod["metadata"]["annotations"]["starbase.io/source-revision"],
            SOURCE_REVISION,
        )
        self.assertEqual(
            pod["metadata"]["annotations"]["starbase.io/artifact-class"],
            "owner-local-preproduction",
        )
        self.assertEqual(
            json.loads(env["STARBASE_EXPECTED_SOURCES"]),
            {
                "github:starbase-preview/synthetic-observation": "github",
                "kubernetes:kubani:starbase-namespaces-v1": "kubernetes",
            },
        )
        self.assertEqual(
            json.loads(env["STARBASE_CONNECTOR_IDENTITIES"]),
            {
                "system:serviceaccount:starbase-connectors:starbase-preview-fixture": [
                    "github"
                ],
                "system:serviceaccount:starbase-connectors:starbase-kubernetes-connector": [
                    "kubernetes"
                ],
            },
        )

    def test_connector_is_exact_bounded_and_preferred_node_only(self) -> None:
        deployment = self.object(
            "Deployment", "starbase-connectors", "starbase-kubernetes-connector"
        )
        self.assertEqual(
            deployment["metadata"]["annotations"],
            {
                "starbase.io/activation-state": (
                    "authorized-preproduction-kubernetes-canary"
                ),
                "starbase.io/activation-stage": "phase6-kubernetes-observation",
            },
        )
        template = deployment["spec"]["template"]
        self.assertEqual(
            template["metadata"]["annotations"],
            {
                "starbase.io/activation-state": (
                    "authorized-preproduction-kubernetes-canary"
                ),
                "starbase.io/activation-stage": "phase6-kubernetes-observation",
                "starbase.io/source-revision": SOURCE_REVISION,
                "starbase.io/artifact-class": "owner-local-preproduction",
            },
        )
        pod = template["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["serviceAccountName"], "starbase-kubernetes-connector")
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
        self.assertNotIn(
            "preferredDuringSchedulingIgnoredDuringExecution",
            pod["affinity"]["nodeAffinity"],
        )
        container = next(item for item in pod["containers"] if item["name"] == "connector")
        self.assertEqual(container["image"], CONNECTOR_IMAGE)
        self.assertEqual(container["imagePullPolicy"], "IfNotPresent")
        self.assertEqual(
            container["resources"],
            {
                "requests": {"cpu": "50m", "memory": "64Mi"},
                "limits": {"cpu": "500m", "memory": "256Mi"},
            },
        )
        self.assertEqual(
            container["securityContext"],
            {
                "allowPrivilegeEscalation": False,
                "capabilities": {"drop": ["ALL"]},
                "readOnlyRootFilesystem": True,
            },
        )
        scope = json.loads(
            next(
                item["value"]
                for item in container["env"]
                if item["name"] == "STARBASE_KUBERNETES_SCOPE"
            )
        )
        self.assertEqual(
            scope,
            {
                "id": "starbase-namespaces-v1",
                "namespaces": [
                    "starbase-connectors",
                    "starbase-execution",
                    "starbase-system",
                ],
                "include_nodes": False,
                "flux_namespaces": [],
            },
        )
        tokens = {
            source["serviceAccountToken"].get("audience", "kubernetes-api"):
            source["serviceAccountToken"]
            for volume in pod["volumes"]
            for source in volume.get("projected", {}).get("sources", [])
            if "serviceAccountToken" in source
        }
        self.assertEqual(tokens["kubernetes-api"]["expirationSeconds"], 600)
        self.assertEqual(tokens["starbase-core"]["expirationSeconds"], 600)

    def test_rbac_is_namespace_scoped_and_list_only(self) -> None:
        expected_rules = [
            {"apiGroups": [""], "resources": ["pods"], "verbs": ["list"]},
            {
                "apiGroups": ["apps"],
                "resources": ["daemonsets", "deployments", "statefulsets"],
                "verbs": ["list"],
            },
        ]
        for namespace in (
            "starbase-connectors",
            "starbase-execution",
            "starbase-system",
        ):
            role = self.object("Role", namespace, "starbase-kubernetes-observer")
            self.assertEqual(role["rules"], expected_rules)
            binding = self.object(
                "RoleBinding", namespace, "starbase-kubernetes-observer"
            )
            self.assertEqual(
                binding["subjects"],
                [
                    {
                        "kind": "ServiceAccount",
                        "name": "starbase-kubernetes-connector",
                        "namespace": "starbase-connectors",
                    }
                ],
            )
        self.assertNotIn(
            ("ClusterRole", "", "starbase-kubernetes-observer"), self.by_identity
        )
        self.assertNotIn(
            ("ClusterRoleBinding", "", "starbase-kubernetes-observer"),
            self.by_identity,
        )

    def test_connector_egress_is_dns_core_and_exact_api_only(self) -> None:
        policy_names = {
            "default-deny",
            "allow-dns",
            "allow-readonly-connectors-to-core",
            "allow-kubernetes-connector-to-api",
        }
        connector_labels = {
            "app.kubernetes.io/component": "readonly-connector",
            "app.kubernetes.io/name": "starbase-kubernetes-connector",
            "starbase.io/access-core": "true",
        }
        matching = set()
        for document in self.documents:
            if (
                document.get("kind") != "NetworkPolicy"
                or document.get("metadata", {}).get("namespace")
                != "starbase-connectors"
            ):
                continue
            labels = document["spec"].get("podSelector", {}).get("matchLabels", {})
            if all(connector_labels.get(key) == value for key, value in labels.items()):
                matching.add(document["metadata"]["name"])
        self.assertEqual(matching, policy_names)
        api = self.object(
            "NetworkPolicy",
            "starbase-connectors",
            "allow-kubernetes-connector-to-api",
        )
        self.assertEqual(
            api["spec"]["egress"],
            [
                {
                    "to": [{"ipBlock": {"cidr": "10.43.0.1/32"}}],
                    "ports": [{"protocol": "TCP", "port": 443}],
                },
                {
                    "to": [{"ipBlock": {"cidr": "100.92.107.71/32"}}],
                    "ports": [{"protocol": "TCP", "port": 6443}],
                },
            ],
        )

    def test_flux_health_gate_includes_every_active_deployment(self) -> None:
        flux = yaml.safe_load(FOUNDATION_FLUX.read_text())
        self.assertEqual(
            flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase9-foundation",
        )
        checks = {
            (item["kind"], item["namespace"], item["name"])
            for item in flux["spec"]["healthChecks"]
        }
        for identity in (
            ("Deployment", "starbase-system", "starbase-core"),
            ("Deployment", "starbase-connectors", "starbase-preview-fixture"),
            (
                "Deployment",
                "starbase-connectors",
                "starbase-kubernetes-connector",
            ),
            (
                "Deployment",
                "starbase-connectors",
                "starbase-github-connector",
            ),
        ):
            self.assertIn(identity, checks)


if __name__ == "__main__":
    unittest.main()
