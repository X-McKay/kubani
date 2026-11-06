"""T24 has no active fault controller, broad observer or human credential mount."""

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "infrastructure/gitops/apps/agent-platform/conformance/lifecycle"
IMAGE = "registry.almckay.io/platform/session-runner:test@sha256:" + "b4" * 32
RUN = "35b5254b-05fb-49dc-a98e-7cb27efaf5b5"
RELEASE = "conformance-lifecycle-2026-11-06-7c39c4a9"


def render(name):
    text = (DIRECTORY / name).read_text()
    for key, value in {
        "LIFECYCLE_RUN_ID": RUN,
        "LIFECYCLE_RELEASE": RELEASE,
        "LIFECYCLE_RUNNER_IMAGE": IMAGE,
    }.items():
        text = text.replace("${" + key + "}", value)
    assert "${" not in text
    return list(yaml.safe_load_all(text))


class LifecycleTemplates(unittest.TestCase):
    def test_workloads_are_inactive_and_keep_exact_worker_replacement_identity(self):
        worker = render("worker-deployment.yaml.in")[0]
        job = render("harness-job.yaml.in")[0]
        self.assertEqual(
            (worker["kind"], worker["spec"]["replicas"]), ("Deployment", 0)
        )
        self.assertIs(job["spec"]["suspend"], True)
        labels = worker["spec"]["template"]["metadata"]["labels"]
        self.assertEqual(worker["spec"]["selector"]["matchLabels"], labels)
        self.assertEqual(labels["agentplatform.io/lifecycle-run"], RUN)
        for obj, identity in ((worker, "session-runner"), (job, "conformance-harness")):
            pod = obj["spec"]["template"]["spec"]
            self.assertEqual(pod["serviceAccountName"], identity)
            self.assertEqual(pod["nodeSelector"]["topology.kubani.io/role"], "database")
            self.assertEqual(pod["containers"][0]["image"], IMAGE)
        container = worker["spec"]["template"]["spec"]["containers"][0]
        env = {e["name"]: e for e in container["env"]}
        self.assertEqual(env["LIFECYCLE_RUN_ID"]["value"], RUN)
        self.assertEqual(
            env["POD_UID"]["valueFrom"]["fieldRef"]["fieldPath"], "metadata.uid"
        )
        self.assertEqual(
            container["command"][-1], "runner.conformance_lifecycle_worker"
        )
        for path in (ROOT / "infrastructure/gitops").rglob("kustomization.yaml"):
            self.assertNotIn("conformance/lifecycle", path.read_text())

    def test_harness_has_only_observer_audience_and_no_human_or_backend_credentials(
        self,
    ):
        pod = render("harness-job.yaml.in")[0]["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertIn("T24", container["args"])
        self.assertIn("--observe-lifecycle-faults", container["args"])
        volumes = {v["name"]: v for v in pod["volumes"]}
        self.assertEqual(
            set(volumes), {"temporal-tls", "payload-key", "tmp", "aps-token"}
        )
        token = volumes["aps-token"]["projected"]["sources"][0]["serviceAccountToken"]
        self.assertEqual(token["audience"], "agent-policy-service")
        self.assertEqual(token["expirationSeconds"], 600)
        self.assertEqual(
            {v["secret"]["secretName"] for v in volumes.values() if "secret" in v},
            {"conformance-harness-temporal-tls", "session-payload-key-tenant-test"},
        )
        self.assertTrue(
            all(
                v.get("readOnly")
                for v in container["volumeMounts"]
                if v["name"] != "tmp"
            )
        )

    def test_control_and_observer_roles_are_read_only_and_exact(self):
        docs = render("rbac.yaml.in")
        self.assertEqual({d["kind"] for d in docs}, {"Role", "RoleBinding"})
        for role in (d for d in docs if d["kind"] == "Role"):
            for rule in role["rules"]:
                self.assertLessEqual(set(rule["verbs"]), {"get", "list"})
                self.assertFalse(
                    {"secrets", "pods/exec", "deployments/scale"}
                    & set(rule["resources"])
                )
                if rule["resources"] == ["pods"]:
                    self.assertEqual(role["metadata"]["namespace"], "tenant-test")
                else:
                    self.assertIn(
                        rule["resourceNames"],
                        [
                            ["conformance-lifecycle-control"],
                            ["agent-policy-service"],
                            ["conformance-lifecycle"],
                            [RELEASE],
                        ],
                    )

    def test_observer_activation_is_dormant_and_only_the_exact_fixture(self):
        patch = render("observer-env-patch.yaml.in")[0]
        container = patch["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["name"], "agent-policy-service")
        self.assertEqual(
            {e["name"]: e["value"] for e in container["env"]},
            {
                "APS_LIFECYCLE_OBSERVER_SUBJECT": "system:serviceaccount:agent-platform:conformance-harness",
                "APS_LIFECYCLE_OBSERVER_AGENTS": "conformance-lifecycle",
            },
        )
        self.assertEqual(set(container), {"name", "env"})
        self.assertEqual(
            patch["metadata"],
            {"name": "agent-policy-service", "namespace": "agent-platform"},
        )
