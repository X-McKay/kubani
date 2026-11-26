"""An Agent's model budgets must admit at least one call: the policy service reserves the backend's whole context length.

The reservations are the `APS_BACKEND_CATALOGUE` of the policy service's own manifest in the repository being operated on.
Offline fixtures only; the catalogue-wide checks read the committed manifests.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
from agent_ops import layout, register, sync  # noqa: E402
from test_agent_ops import AGENT_BODY, ROOT, FakeGit, make_root, synced_root  # noqa: E402

CATALOGUE = {"llm-main": {"maxModelLen": 131072}, "llm-fast": {"maxModelLen": 32768}, "llm-budget-conformance": {"maxModelLen": 300}}
WITH_MODEL = AGENT_BODY.replace("    models: []\n", "    models:\n      - backend: llm-fast\n        models: [fast]\n        budget:\n          tokensPerSession: 20000\n          tokensPerDay: 200000\n")
MESSAGE = (
    "sample: tokensPerSession 20000 is below the 32768 tokens reserved for each call to llm-fast (APS_BACKEND_CATALOGUE); "
    "no call would be admitted. Raise the budget in the agent's source and release a new version"
)


def write_policy_service(root: Path, catalogue=CATALOGUE) -> None:
    path = root / layout.POLICY_SERVICE
    path.parent.mkdir(parents=True, exist_ok=True)
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "agent-policy-service"},
        "spec": {"template": {"spec": {"containers": [{"name": "aps", "env": [{"name": "OTHER", "value": "x"}, {"name": "APS_BACKEND_CATALOGUE", "value": json.dumps(catalogue)}]}]}}},
    }
    path.write_text(yaml.safe_dump_all([{"kind": "Service"}, deployment]), encoding="utf-8")


def agent(models) -> dict:
    return {"metadata": {"name": "sample"}, "spec": {"capabilities": {"models": models}}}


def grant(backend="llm-fast", **budget) -> dict:
    return {"backend": backend, "models": ["fast"], **({"budget": budget} if budget else {})}


class BudgetProblems(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        write_policy_service(self.root)

    def test_reads_the_catalogue_from_the_manifest_of_the_repository_operated_on(self):
        self.assertEqual(layout.backend_reservations(self.root), {"llm-main": 131072, "llm-fast": 32768, "llm-budget-conformance": 300})
        other = self.root / "other"
        write_policy_service(other, {"llm-fast": {"maxModelLen": 10}})
        self.assertEqual(layout.backend_reservations(other), {"llm-fast": 10})

    def test_budgets_at_or_above_the_reservation_are_fine(self):
        self.assertEqual(layout.budget_problems(self.root, agent([grant(tokensPerSession=32768, tokensPerDay=32768)])), [])
        self.assertEqual(layout.budget_problems(self.root, agent([grant("llm-main", tokensPerSession=131072, tokensPerDay=500000), grant(tokensPerSession=40000, tokensPerDay=40000)])), [])

    def test_a_session_budget_below_the_reservation_names_agent_field_number_backend_and_reservation(self):
        problems = layout.budget_problems(self.root, agent([grant(tokensPerSession=20000, tokensPerDay=200000)]))
        self.assertEqual(problems, [MESSAGE])

    def test_the_day_budget_is_checked_too_and_every_problem_is_listed(self):
        problems = layout.budget_problems(self.root, agent([grant("llm-main", tokensPerSession=1, tokensPerDay=2), grant(tokensPerSession=32768, tokensPerDay=100)]))
        self.assertEqual(len(problems), 3)
        self.assertIn("tokensPerDay 2 is below the 131072 tokens reserved for each call to llm-main", problems[1])
        self.assertIn("tokensPerDay 100 is below the 32768 tokens reserved for each call to llm-fast", problems[2])

    def test_a_backend_missing_from_the_catalogue_is_a_problem(self):
        problems = layout.budget_problems(self.root, agent([grant("llm-huge", tokensPerSession=10**9, tokensPerDay=10**9)]))
        self.assertEqual(len(problems), 1)
        self.assertIn("sample: model grant names backend llm-huge, which is not in APS_BACKEND_CATALOGUE", problems[0])

    def test_a_grant_with_no_budget_and_an_agent_with_no_models_are_skipped(self):
        self.assertEqual(layout.budget_problems(self.root, agent([grant()])), [])
        self.assertEqual(layout.budget_problems(self.root, agent([])), [])
        self.assertEqual(layout.budget_problems(self.root, {"metadata": {"name": "sample"}, "spec": {}}), [])
        self.assertEqual(layout.budget_problems(self.root, agent([grant(tokensPerSession=5)])), [MESSAGE.replace("20000", "5")])  # only the field that is declared

    def test_an_unreadable_catalogue_is_a_layout_error(self):
        (self.root / layout.POLICY_SERVICE).write_text("kind: Service\n", encoding="utf-8")
        with self.assertRaisesRegex(layout.LayoutError, "APS_BACKEND_CATALOGUE"):
            layout.budget_problems(self.root, agent([grant(tokensPerSession=1)]))
        (self.root / layout.POLICY_SERVICE).unlink()
        with self.assertRaises(layout.LayoutError):
            layout.budget_problems(self.root, agent([grant(tokensPerSession=1)]))


class VerbsRefuse(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def test_sync_refuses_before_writing(self):
        root = synced_root(self.tmp)
        write_policy_service(root)
        file = root / layout.AGENTS_DIR / "tenant-test/sample/agent.yaml"
        before = file.read_bytes()
        git = FakeGit({"b" * 40: {"agents/sample/deploy/agent.yaml": WITH_MODEL}}, "b" * 40)
        with patch.object(sync, "_git", git), self.assertRaises(sync.SyncError) as caught:
            sync.sync(root, "sample", Path("/src"))
        self.assertEqual((str(caught.exception), caught.exception.code), (MESSAGE, "validation-failed"))
        self.assertEqual(file.read_bytes(), before)

    def test_check_sync_fails_the_row(self):
        root = make_root(self.tmp, release_text=None)
        write_policy_service(root)
        (root / layout.AGENTS_DIR / "tenant-test/sample/agent.yaml").write_text(sync.header("example/agents", "sample", "a" * 40, WITH_MODEL) + WITH_MODEL, encoding="utf-8")
        row = sync.check(root)["agents"][0]
        self.assertEqual((row["state"], row["detail"]), ("fail", MESSAGE))
        self.assertFalse(sync.check(root)["ok"])

    def test_register_refuses_and_leaves_nothing_behind(self):
        root = synced_root(self.tmp)
        write_policy_service(root)
        body = WITH_MODEL.replace("name: sample", "name: new-agent")
        git = FakeGit({"b" * 40: {"agents/new-agent/deploy/agent.yaml": body}}, "b" * 40)
        watched = [root / layout.AGENTS_DIR / "kustomization.yaml", root / layout.SIGNERS, root / register.NAMESPACES]
        before = [p.read_bytes() for p in watched]
        with patch.object(sync, "_git", git), self.assertRaises(sync.SyncError) as caught:
            register.register(root, "tenant-test", "example/my-agent", ["new-agent"], Path("/src"))
        self.assertEqual(str(caught.exception), MESSAGE.replace("sample:", "new-agent:"))
        self.assertFalse((root / layout.AGENTS_DIR / "tenant-test/new-agent").exists())
        self.assertEqual([p.read_bytes() for p in watched], before)

    def test_a_budget_that_fits_is_accepted_by_all_three(self):
        root = synced_root(self.tmp)
        write_policy_service(root)
        fits = WITH_MODEL.replace("tokensPerSession: 20000", "tokensPerSession: 32768")
        git = FakeGit({"a" * 40: {"agents/sample/deploy/agent.yaml": fits}, "b" * 40: {"agents/sample/deploy/agent.yaml": fits, "agents/new-agent/deploy/agent.yaml": fits.replace("name: sample", "name: new-agent")}}, "b" * 40)
        with patch.object(sync, "_git", git):
            self.assertEqual(sync.sync(root, "sample", Path("/src"))["source"]["commit"], "b" * 40)
            self.assertEqual(register.register(root, "tenant-test", "example/my-agent", ["new-agent"], Path("/src"))["added"], ["new-agent"])
            self.assertTrue(sync.check(root)["ok"])


class CommittedRepository(unittest.TestCase):
    def test_every_committed_agent_budget_admits_a_call_on_each_backend_it_names(self):
        failures = []
        for d in layout.agent_dirs(ROOT):
            failures += layout.budget_problems(ROOT, layout.committed_agent(d))
        self.assertEqual(failures, [])

    def test_the_catalogue_figures_for_the_engines_equal_the_engines_real_context_lengths(self):
        config = yaml.safe_load((ROOT / "infrastructure/gitops/apps/vllm/model-config.yaml").read_text())["data"]
        reserved = layout.backend_reservations(ROOT)
        self.assertEqual(reserved["llm-main"], int(config["LLM_MAX_MODEL_LEN"]))
        self.assertEqual(reserved["llm-fast"], int(config["FAST_MAX_MODEL_LEN"]))


if __name__ == "__main__":
    unittest.main()
