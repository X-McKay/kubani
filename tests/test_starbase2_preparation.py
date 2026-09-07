"""Verify the prepared boundary without activating a production installation."""

from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
GITOPS = ROOT / "infrastructure/gitops"


def render(path):
    output = subprocess.check_output(["kubectl", "kustomize", str(path)], text=True)
    return [item for item in yaml.safe_load_all(output) if item]


class Starbase2PreparationTests(unittest.TestCase):
    def test_preparation_is_unreachable_from_active_roots(self):
        for path in ("flux-system", "apps", "apps/databases", "infrastructure"):
            for item in render(GITOPS / path):
                self.assertNotIn("starbase2", yaml.safe_dump(item).lower(), path)
        flux = yaml.safe_load(
            (GITOPS / "flux-system/starbase2-kustomization.yaml").read_text()
        )
        self.assertIs(flux["spec"]["suspend"], True)
        self.assertIs(flux["spec"]["prune"], False)
        self.assertEqual(flux["spec"]["deletionPolicy"], "Orphan")
        self.assertEqual(
            flux["spec"]["path"], "./infrastructure/gitops/apps/starbase2"
        )

    def test_boundary_contains_no_workloads_credentials_or_authority(self):
        items = render(GITOPS / "apps/starbase2")
        self.assertEqual(len(items), 5)
        self.assertEqual(
            sorted(item["kind"] for item in items),
            ["Namespace", "NetworkPolicy", "NetworkPolicy", "NetworkPolicy", "ServiceAccount"],
        )
        for item in items:
            self.assertEqual(
                item["metadata"]["labels"]["starbase2.io/installation"],
                "starbase2-prod",
            )
            if item["kind"] == "ServiceAccount":
                self.assertIs(item["automountServiceAccountToken"], False)
            if item["kind"] == "Namespace":
                self.assertEqual(
                    item["metadata"]["labels"]["pod-security.kubernetes.io/enforce"],
                    "restricted",
                )

    def test_dependency_access_is_limited_to_installation_and_service_ports(self):
        policies = {
            item["metadata"]["namespace"]: item["spec"]
            for item in render(GITOPS / "apps/starbase2")
            if item["kind"] == "NetworkPolicy"
        }
        own = policies["starbase2-prod"]
        self.assertEqual(own["podSelector"], {})
        self.assertEqual(own["ingress"], [])
        self.assertEqual(set(own["policyTypes"]), {"Ingress", "Egress"})
        self.assertEqual(len(own["egress"]), 3)
        allowed = set()
        for rule in own["egress"]:
            self.assertEqual(len(rule["to"]), 1)
            namespace = rule["to"][0]["namespaceSelector"]["matchLabels"]
            for port in rule["ports"]:
                allowed.add((namespace["kubernetes.io/metadata.name"], port["port"], port["protocol"]))
        self.assertEqual(allowed, {
            ("kube-system", 53, "TCP"), ("kube-system", 53, "UDP"),
            ("database", 5432, "TCP"), ("temporal", 7233, "TCP"),
        })
        for namespace, port in (("database", 5432), ("temporal", 7233)):
            spec = policies[namespace]
            self.assertEqual(spec["policyTypes"], ["Ingress"])
            self.assertEqual(spec["ingress"], [{
                "from": [{
                    "namespaceSelector": {"matchLabels": {
                        "kubernetes.io/metadata.name": "starbase2-prod",
                    }},
                    "podSelector": {"matchLabels": {
                        "starbase2.io/installation": "starbase2-prod",
                        "app.kubernetes.io/name": "starbase2",
                    }},
                }],
                "ports": [{"protocol": "TCP", "port": port}],
            }])
        self.assertEqual(policies["database"]["podSelector"], {
            "matchLabels": {"app.kubernetes.io/name": "postgresql"},
        })
        self.assertEqual(policies["temporal"]["podSelector"], {"matchLabels": {
            "app.kubernetes.io/name": "temporal",
            "app.kubernetes.io/instance": "temporal",
            "app.kubernetes.io/component": "frontend",
        }})
