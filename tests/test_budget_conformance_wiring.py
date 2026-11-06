"""Cross-manifest invariants for the opt-in bounded budget qualification path."""
import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1] / "infrastructure/gitops"
AP = ROOT / "apps/agent-platform"
AG = ROOT / "apps/ai-gateway/agents"


def docs(path):
    return list(yaml.safe_load_all(path.read_text()))


def named(path, name, kind=None):
    return next(d for d in docs(path) if d["metadata"]["name"] == name and (kind is None or d["kind"] == kind))


class BudgetWiringTests(unittest.TestCase):
    def test_enforced_backend_matches_catalogue_without_lowering_production(self):
        deployment = named(AP / "workloads/budget-backend.yaml", "budget-backend")
        pod = deployment["spec"]["template"]["spec"]
        self.assertEqual(pod["nodeSelector"]["kubernetes.io/arch"], "amd64")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertIn("-amd64@sha256:", pod["containers"][0]["image"])
        aps = named(AP / "workloads/agent-policy-service.yaml", "agent-policy-service", "Deployment")
        env = {v["name"]: v.get("value") for v in aps["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(json.loads(env["APS_BACKEND_CATALOGUE"]), {
            "llm-main": {"maxModelLen": 131072}, "llm-fast": {"maxModelLen": 32768},
            "llm-budget-conformance": {"maxModelLen": 300},
        })
        self.assertEqual(env["APS_BUDGET_OBSERVER_SUBJECT"], "system:serviceaccount:agent-platform:conformance-harness")
        self.assertEqual(set(env["APS_BUDGET_OBSERVER_AGENTS"].split(",")),
                         {"conformance-budget-day", "conformance-budget-session"})

    def test_route_auth_and_concurrency_share_the_fixture_backend(self):
        resources = docs(AG / "budget-conformance.yaml")
        by_name = {d["metadata"]["name"]: d for d in resources}
        route = by_name["agents-inference-llm-budget-conformance"]
        self.assertEqual(route["spec"]["rules"][0]["matches"][0]["path"],
                         {"type": "Exact", "value": "/models/llm-budget-conformance/v1/chat/completions"})
        for policy in ("agents-jwt", "agents-only"):
            targets = named(AG / "policies-auth.yaml", policy)["spec"]["targetRefs"]
            self.assertIn(route["metadata"]["name"], [x["name"] for x in targets])
        ext = by_name["agents-extauth-inference-llm-budget-conformance"]["spec"]["traffic"]["extAuth"]
        self.assertEqual(ext["failureMode"], "FailClosed")
        self.assertEqual(ext["grpc"]["contextExtensions"], {"route": "inference", "backend": "llm-budget-conformance"})
        auth = by_name["agents-inference-budget-bounds"]["spec"]["traffic"]["authorization"]
        self.assertEqual(auth["action"], "Require")
        limit = by_name["agents-budget-conformance"]["spec"]["traffic"]["rateLimit"]
        self.assertGreaterEqual(limit["local"][0]["burst"], 10)
        self.assertEqual(limit["global"]["failureMode"], "FailClosed")

    def test_jobs_are_suspended_read_only_and_releases_bound_to_fixtures(self):
        workload_names = (AP / "workloads/kustomization.yaml").read_text()
        for case, selected in (("day", "T13"), ("session", "T13b")):
            fixture = "conformance-budget-" + case
            directory = ROOT / "apps/agents/tenant-test" / fixture
            release = docs(directory / "agentrelease.yaml")[0]
            self.assertEqual(release["spec"]["agent"], fixture)
            approval = release["spec"]["approval"]
            self.assertIsInstance(approval["approved"], bool)
            if approval["approved"]:
                self.assertTrue(all(approval.get(k) for k in ("approvedBy", "approvedAt", "ticket")))
            agent = docs(directory / "agent.yaml")[0]
            capability = agent["spec"]["capabilities"]["models"][0]
            self.assertEqual(capability["models"], ["conformance-byte-v1"])
            self.assertEqual(capability["budget"]["tokensPerDay" if case == "day" else "tokensPerSession"], 2000 if case == "day" else 1000)
            filename = f"conformance-budget-{case}-job.yaml"
            self.assertNotIn(filename, workload_names)
            job = docs(AP / "workloads" / filename)[0]
            self.assertIs(job["spec"]["suspend"], True)
            pod = job["spec"]["template"]["spec"]
            self.assertEqual(pod["serviceAccountName"], "conformance-harness")
            container = pod["containers"][0]
            self.assertIn(selected, container["args"])
            mounts = {m["name"]: m for m in container["volumeMounts"]}
            self.assertTrue(mounts["artifacts"]["readOnly"])
            self.assertNotIn("backend-key", mounts)
            for document in docs(directory / "harness-rbac.yaml"):
                for rule in document.get("rules", []):
                    self.assertLessEqual(set(rule["verbs"]), {"get", "list"})
                    self.assertNotIn("secrets", rule["resources"])
