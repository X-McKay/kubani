from __future__ import annotations

import json
import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "infrastructure/gitops/apps/starbase-phase5-preview"
SESSION_REPAIR = (
    ROOT / "infrastructure/gitops/apps/starbase-phase5-session-repair"
)
FOUNDATION_FLUX = (
    ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
)


class StarbasePhase5PreviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rendered = subprocess.run(
            ["kubectl", "kustomize", str(PREVIEW)],
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

    def test_preview_activates_only_core_and_dedicated_fixture(self) -> None:
        core = self.object("Deployment", "starbase-system", "starbase-core")
        self.assertEqual(core["spec"]["replicas"], 1)
        self.assertEqual(
            core["spec"]["template"]["metadata"]["annotations"]
            ["starbase.io/activation-state"],
            "authorized-rc5-synthetic-preview",
        )
        core_pod = core["spec"]["template"]["spec"]
        self.assertEqual(
            core_pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        core_env = {
            item["name"]: item.get("value")
            for item in core_pod["containers"][0]["env"]
        }
        self.assertEqual(
            json.loads(core_env["STARBASE_EXPECTED_SOURCES"]),
            {"github:starbase-preview/synthetic-observation": "github"},
        )
        self.assertEqual(
            json.loads(core_env["STARBASE_CONNECTOR_IDENTITIES"]),
            {
                "system:serviceaccount:starbase-connectors:starbase-preview-fixture": [
                    "github"
                ]
            },
        )
        self.assertEqual(
            core_env["STARBASE_WORKLOAD_OIDC_JWKS_URL"],
            "https://100.92.107.71:6443/openid/v1/jwks",
        )
        self.assertNotIn("STARBASE_WORKLOAD_OIDC_TOKEN_FILE", core_env)
        self.assertNotIn("STARBASE_WORKLOAD_OIDC_TOKEN_FILE", self.rendered)
        self.assertEqual(
            json.loads(core_env["STARBASE_OIDC_REQUIRED_GROUPS"]),
            ["starbase-operators"],
        )
        runtime = self.object("ConfigMap", "starbase-system", "starbase-runtime")
        self.assertEqual(
            runtime["data"]["STARBASE_WORKLOAD_IDENTITY_FILE"],
            "/var/run/secrets/starbase.io/workload-issuer-identity/token",
        )
        self.assertNotIn("STARBASE_WORKLOAD_OIDC_TOKEN_FILE", runtime["data"])

        issuer_identity = next(
            volume
            for volume in core_pod["volumes"]
            if volume["name"] == "workload-issuer-identity"
        )
        issuer_token = issuer_identity["projected"]["sources"][0][
            "serviceAccountToken"
        ]
        self.assertEqual(
            issuer_token["audience"], "https://kubernetes.default.svc.cluster.local"
        )
        self.assertEqual(issuer_token["expirationSeconds"], 600)
        self.assertEqual(issuer_token["path"], "token")

        for name in ("starbase-github-connector", "starbase-kubernetes-connector"):
            self.assertEqual(
                self.object("Deployment", "starbase-connectors", name)["spec"]
                ["replicas"],
                0,
            )

        fixture = self.object(
            "Deployment", "starbase-connectors", "starbase-preview-fixture"
        )
        self.assertEqual(fixture["spec"]["replicas"], 1)
        fixture_pod = fixture["spec"]["template"]["spec"]
        self.assertEqual(fixture_pod["serviceAccountName"], "starbase-preview-fixture")
        self.assertFalse(fixture_pod["automountServiceAccountToken"])
        self.assertEqual(
            fixture_pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        container = fixture_pod["containers"][0]
        release_lock = json.loads(
            (ROOT / "infrastructure/gitops/apps/starbase/promotion-lock.json").read_text()
        )
        self.assertEqual(
            container["image"], release_lock["release"]["images"]["github-connector"]
        )
        env = {item["name"]: item.get("value") for item in container["env"]}
        self.assertEqual(env["STARBASE_CONNECTOR_MODE"], "fixture")
        self.assertEqual(
            env["STARBASE_FIXTURE_PATH"],
            "/var/run/starbase-preview/repository.json",
        )
        self.assertNotIn("STARBASE_GITHUB_REPOSITORY", env)
        self.assertFalse(any("secretRef" in item for item in container["envFrom"]))
        token = next(
            source["serviceAccountToken"]
            for volume in fixture_pod["volumes"]
            if volume["name"] == "core-workload-identity"
            for source in volume["projected"]["sources"]
            if "serviceAccountToken" in source
        )
        self.assertEqual(token["audience"], "starbase-core")
        self.assertEqual(token["expirationSeconds"], 600)
        self.assertNotIn(
            ("ClusterRoleBinding", "", "starbase-preview-fixture"), self.by_identity
        )
        self.assertNotIn(
            ("RoleBinding", "starbase-connectors", "starbase-preview-fixture"),
            self.by_identity,
        )

        contract = self.object(
            "ConfigMap", "starbase-system", "starbase-secret-contracts"
        )
        self.assertEqual(
            contract["metadata"]["annotations"],
            {
                "starbase.io/activation-state": (
                    "runtime-authorized-rc5-synthetic-preview"
                ),
                "starbase.io/blocker": "provider-connectors-separately-authorized",
            },
        )
        for name in ("starbase-core-runtime", "starbase-gateway-runtime"):
            runtime_secret = self.object("Secret", "starbase-system", name)
            self.assertEqual(
                runtime_secret["metadata"]["annotations"][
                    "starbase.io/activation-state"
                ],
                "authorized-rc5-synthetic-preview",
            )

    def test_fixture_is_immutable_content_bound_and_visibly_synthetic(self) -> None:
        fixture = self.object(
            "ConfigMap", "starbase-connectors", "starbase-preview-fixture-v1"
        )
        self.assertTrue(fixture["immutable"])
        content = fixture["data"]["repository.json"]
        self.assertEqual(
            fixture["metadata"]["annotations"]["starbase.io/content-digest"],
            f"sha256:{sha256(content.encode()).hexdigest()}",
        )
        repository = json.loads(content)
        self.assertEqual(
            (repository["owner"], repository["name"]),
            ("starbase-preview", "synthetic-observation"),
        )
        self.assertEqual(
            sum(
                len(repository[key])
                for key in ("issues", "pull_requests", "workflow_runs", "branches")
            ),
            4,
        )
        self.assertTrue(
            all(
                "SYNTHETIC PREVIEW" in item.get("title", item.get("name", ""))
                for key in ("issues", "pull_requests", "workflow_runs", "branches")
                for item in repository[key]
            )
        )

        egress = self.object(
            "NetworkPolicy", "starbase-connectors", "allow-preview-fixture-to-core"
        )
        self.assertEqual(egress["spec"]["policyTypes"], ["Egress"])
        self.assertEqual(len(egress["spec"]["egress"]), 1)
        self.assertEqual(
            egress["spec"]["egress"][0]["ports"],
            [{"protocol": "TCP", "port": 8081}],
        )

    def test_flux_fails_closed_on_preview_workloads(self) -> None:
        flux = yaml.safe_load(FOUNDATION_FLUX.read_text())
        self.assertEqual(
            flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase5-session-repair",
        )
        checks = {
            (item["kind"], item["namespace"], item["name"])
            for item in flux["spec"]["healthChecks"]
        }
        self.assertIn(("Deployment", "starbase-system", "starbase-core"), checks)
        self.assertIn(
            ("Deployment", "starbase-connectors", "starbase-preview-fixture"),
            checks,
        )


class StarbasePhase5SessionRepairContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        preview_rendered = subprocess.run(
            ["kubectl", "kustomize", str(PREVIEW)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        repair_rendered = subprocess.run(
            ["kubectl", "kustomize", str(SESSION_REPAIR)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        cls.preview_documents = [
            doc for doc in yaml.safe_load_all(preview_rendered) if doc
        ]
        cls.repair_documents = [
            doc for doc in yaml.safe_load_all(repair_rendered) if doc
        ]
        cls.by_identity = {
            (
                doc["kind"],
                doc.get("metadata", {}).get("namespace", ""),
                doc["metadata"]["name"],
            ): doc
            for doc in cls.repair_documents
        }

    def object(self, kind: str, namespace: str, name: str) -> dict:
        return self.by_identity[(kind, namespace, name)]

    def test_repair_changes_only_core_runtime_identity(self) -> None:
        preview_identities = {
            (
                doc["kind"],
                doc.get("metadata", {}).get("namespace", ""),
                doc["metadata"]["name"],
            )
            for doc in self.preview_documents
        }
        self.assertEqual(set(self.by_identity), preview_identities)

        lock = json.loads(
            (ROOT / "infrastructure/gitops/apps/starbase/promotion-lock.json").read_text()
        )
        core = self.object("Deployment", "starbase-system", "starbase-core")
        self.assertEqual(core["spec"]["replicas"], 1)
        self.assertEqual(
            core["metadata"]["annotations"]["starbase.io/activation-stage"],
            "phase5-preproduction-native-observatory",
        )
        self.assertEqual(
            core["spec"]["template"]["metadata"]["annotations"]
            ["starbase.io/source-revision"],
            "b3d54bc875c176dba766682a55d3bb2ca2801819",  # pragma: allowlist secret
        )
        containers = {
            item["name"]: item["image"]
            for item in core["spec"]["template"]["spec"]["containers"]
        }
        self.assertEqual(
            containers["core"],
            "ghcr.io/x-mckay/starbase/core@"
            "sha256:68385b100f24f5a28738799bc3712d6322226760a75ded14c947afbc36533345",  # pragma: allowlist secret
        )
        self.assertEqual(containers["web"], lock["release"]["images"]["web"])

        fixture = self.object(
            "Deployment", "starbase-connectors", "starbase-preview-fixture"
        )
        self.assertEqual(
            fixture["spec"]["template"]["spec"]["containers"][0]["image"],
            lock["release"]["images"]["github-connector"],
        )
        for name in ("starbase-github-connector", "starbase-kubernetes-connector"):
            self.assertEqual(
                self.object("Deployment", "starbase-connectors", name)["spec"]
                ["replicas"],
                0,
            )
        for name in (
            "starbase-core-migrate-0da307f3148a",
            "starbase-gateway-migrate-f2fa2f551602",
        ):
            self.assertTrue(self.object("Job", "starbase-system", name)["spec"]["suspend"])


if __name__ == "__main__":
    unittest.main()
