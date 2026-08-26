from __future__ import annotations

import json
import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "infrastructure/gitops/apps/starbase-phase5-preview"
FOUNDATION_FLUX = (
    ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
)
HEARTBEAT_WORKFLOW = ROOT / ".github/workflows/starbase-preview-heartbeat.yml"
OSPREY_OBSERVER = ROOT / "infrastructure/observers/starbase-preview"
OSPREY_SCRIPT = ROOT / "infrastructure/scripts/starbase_preview_heartbeat.py"


class StarbasePhase5PreviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rendered = subprocess.run(
            ["kubectl", "kustomize", str(PREVIEW)],
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

    def test_preview_activates_only_core_and_dedicated_fixture_identity(self) -> None:
        core = self.object("Deployment", "starbase-system", "starbase-core")
        self.assertEqual(core["spec"]["replicas"], 1)
        self.assertEqual(
            core["spec"]["template"]["metadata"]["annotations"]
            ["starbase.io/activation-state"],
            "authorized-synthetic-preview",
        )
        core_env = {
            item["name"]: item.get("value")
            for item in core["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        self.assertEqual(
            json.loads(core_env["STARBASE_EXPECTED_SOURCES"]),
            {"github:starbase-preview/synthetic-observation": "github"},
        )
        self.assertEqual(
            core_env["STARBASE_WORKLOAD_OIDC_TOKEN_FILE"],
            "/var/run/secrets/starbase.io/workload-issuer-identity/token",
        )
        core_pod = core["spec"]["template"]["spec"]
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
        self.assertEqual(
            json.loads(core_env["STARBASE_CONNECTOR_IDENTITIES"]),
            {
                "system:serviceaccount:starbase-connectors:starbase-preview-fixture": [
                    "github"
                ]
            },
        )
        required_groups = core_env["STARBASE_OIDC_REQUIRED_GROUPS"]
        self.assertEqual(required_groups, '["starbase-operators"]')
        self.assertEqual(json.loads(required_groups), ["starbase-operators"])

        for name in (
            "starbase-github-connector",
            "starbase-kubernetes-connector",
        ):
            self.assertEqual(
                self.object("Deployment", "starbase-connectors", name)["spec"]
                ["replicas"],
                0,
            )

        preview = self.object(
            "Deployment", "starbase-connectors", "starbase-preview-fixture"
        )
        self.assertEqual(preview["spec"]["replicas"], 1)
        pod = preview["spec"]["template"]["spec"]
        self.assertEqual(pod["serviceAccountName"], "starbase-preview-fixture")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        container = pod["containers"][0]
        self.assertEqual(
            container["image"],
            "ghcr.io/x-mckay/starbase/github-connector@sha256:"
            "620598782059ba89241db920200ce0f7210f9ec9e45909bb90f7c2d9740f3c5e",  # pragma: allowlist secret
        )
        release_lock = json.loads(
            (ROOT / "infrastructure/gitops/apps/starbase/promotion-lock.json").read_text()
        )
        self.assertEqual(
            container["image"], release_lock["release"]["images"]["github-connector"]
        )
        env = {item["name"]: item.get("value") for item in container["env"]}
        self.assertEqual(env["STARBASE_CONNECTOR_MODE"], "fixture")
        self.assertEqual(
            env["STARBASE_FIXTURE_PATH"], "/var/run/starbase-preview/repository.json"
        )
        self.assertNotIn("STARBASE_GITHUB_REPOSITORY", env)
        self.assertFalse(any("secretRef" in item for item in container["envFrom"]))
        token = next(
            source["serviceAccountToken"]
            for volume in pod["volumes"]
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
        self.assertEqual(repository["owner"], "starbase-preview")
        self.assertEqual(repository["name"], "synthetic-observation")
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

        policy = self.object(
            "NetworkPolicy", "starbase-connectors", "allow-preview-fixture-to-core"
        )
        self.assertEqual(
            policy["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/name"],
            "starbase-preview-fixture",
        )
        self.assertEqual(policy["spec"]["policyTypes"], ["Egress"])
        egress = policy["spec"]["egress"]
        self.assertEqual(len(egress), 1)
        self.assertEqual(egress[0]["ports"], [{"protocol": "TCP", "port": 8081}])

    def test_flux_fails_closed_on_preview_workloads(self) -> None:
        flux = yaml.safe_load(FOUNDATION_FLUX.read_text())
        self.assertEqual(
            flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase5-preview",
        )
        checks = {
            (item["kind"], item["namespace"], item["name"])
            for item in flux["spec"]["healthChecks"]
        }
        self.assertIn(("Deployment", "starbase-system", "starbase-core"), checks)
        self.assertIn(
            (
                "Deployment",
                "starbase-connectors",
                "starbase-preview-fixture",
            ),
            checks,
        )

    def test_supervised_observer_is_owned_by_osprey_without_credentials(self) -> None:
        self.assertFalse(HEARTBEAT_WORKFLOW.exists())
        self.assertTrue(OSPREY_SCRIPT.exists())

        service = (OSPREY_OBSERVER / "starbase-preview-heartbeat.service").read_text()
        timer = (OSPREY_OBSERVER / "starbase-preview-heartbeat.timer").read_text()
        runbook = (OSPREY_OBSERVER / "README.md").read_text()
        normalized_runbook = " ".join(runbook.split())
        install_section = runbook.split("## Install without activating", 1)[1].split(
            "## Activate after merge", 1
        )[0]
        activation_section = runbook.split("## Activate after merge", 1)[1].split(
            "##", 1
        )[0]
        script = OSPREY_SCRIPT.read_text()

        self.assertIn("DynamicUser=yes", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("ProtectHome=yes", service)
        self.assertIn("PrivateTmp=yes", service)
        self.assertIn("--require-hostname osprey", service)
        self.assertNotIn("LoadCredential", service)
        self.assertNotIn("--push", service)
        self.assertNotIn("hc-ping.com", service)
        self.assertNotIn("kubectl", service)
        self.assertNotIn("GITHUB_TOKEN", service)
        self.assertNotIn("TS_", service)

        self.assertIn("OnCalendar=*-*-* *:0/5:00", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("RandomizedDelaySec=0", timer)
        self.assertIn("anti-footgun", script)
        self.assertNotIn("send_success", script)
        self.assertNotIn("validate_push_url", script)
        self.assertIn("journalctl", runbook)
        self.assertIn("sha256sum", runbook)
        self.assertIn("--verify-journal", runbook)
        self.assertIn("starbase-preview-heartbeat-verification.json", runbook)
        self.assertIn("every six hours", runbook)
        self.assertIn("systemctl disable starbase-preview-heartbeat.timer", install_section)
        self.assertNotIn("systemctl enable", install_section)
        self.assertIn("systemctl enable --now", activation_section)
        self.assertIn(
            "does not provide automatic off-host notification", normalized_runbook
        )
        self.assertIn(
            "before production or unattended operation", normalized_runbook
        )
        self.assertNotIn("Healthchecks.io", runbook)


if __name__ == "__main__":
    unittest.main()
