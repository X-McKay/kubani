"""The rules that let the dependency gate use the self-hosted runner in a public repository, read from the workflow file.

A workflow cannot be run here, so these tests hold the file to the rules its header states. A change that fails one of
them is a change to who can run what on the runner host: treat the failure as a stop, not as a test to relax.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

FILE = Path(__file__).resolve().parents[1] / ".github/workflows/dependency-gate.yml"
EXPRESSION = re.compile(r"\$\{\{.*?\}\}", re.S)


def load() -> dict:
    return yaml.safe_load(FILE.read_text(encoding="utf-8"))


def steps(job: dict) -> list[dict]:
    return job.get("steps") or []


def hosted(job: dict) -> bool:
    return job["runs-on"] == "ubuntu-latest"


class Workflow(unittest.TestCase):
    def setUp(self):
        self.doc = load()
        self.jobs = self.doc["jobs"]
        self.text = FILE.read_text(encoding="utf-8")

    def test_it_runs_the_base_branch_copy_for_pull_requests_to_main_and_nothing_else(self):
        triggers = self.doc.get("on", self.doc.get(True))  # YAML 1.1 reads the bare key `on` as true
        self.assertEqual(triggers, {"pull_request_target": {"branches": ["main"]}})

    def test_the_token_can_only_read_and_no_secret_is_named(self):
        self.assertEqual(self.doc["permissions"], {"contents": "read"})
        for name, job in self.jobs.items():
            self.assertNotIn("permissions", job, name)
        self.assertNotIn("secrets.", self.text)

    def test_every_job_is_off_until_the_variable_enables_it(self):
        for name, job in self.jobs.items():
            self.assertIn("vars.DEPENDENCY_GATE == 'enabled'", job.get("if", ""), name)

    def test_no_checkout_keeps_a_credential_and_no_cache_is_written(self):
        for name, job in self.jobs.items():
            for step in steps(job):
                uses = step.get("uses", "")
                if uses.startswith("actions/checkout@"):
                    self.assertIs(step.get("with", {}).get("persist-credentials"), False, name)
                if uses.startswith("astral-sh/setup-uv@"):
                    self.assertIs(step["with"]["enable-cache"], False, name)
                self.assertFalse(uses.startswith("actions/cache"), name)

    def test_only_the_registry_job_leaves_the_hosted_runners(self):
        self.assertEqual({name for name, job in self.jobs.items() if not hosted(job)}, {"registry"})
        self.assertEqual(self.jobs["registry"]["runs-on"], ["self-hosted", "sparky"])

    def test_the_self_hosted_job_never_sees_the_pull_request_and_never_runs_for_a_fork(self):
        job = self.jobs["registry"]
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", job["if"])
        self.assertIn("needs.compare.outputs.ask == 'true'", job["if"])
        self.assertNotIn("||", job["if"])
        checkouts = [s for s in steps(job) if s.get("uses", "").startswith("actions/checkout@")]
        self.assertEqual(len(checkouts), 1)
        self.assertEqual(checkouts[0].get("with"), {"persist-credentials": False})  # no ref, no repository: the base branch
        for step in steps(job):
            for value in [step.get("run", ""), *map(str, (step.get("with") or {}).values()), *map(str, (step.get("env") or {}).values())]:
                for expression in EXPRESSION.findall(value):
                    self.assertNotIn("github.event", expression, step.get("name"))
                    self.assertNotIn("github.head_ref", expression, step.get("name"))
        ask = steps(job)[-1]["run"]
        self.assertIn("--base-feed", ask)
        self.assertIn("--head-feed", ask)
        self.assertNotIn("-root", ask)

    def test_no_shell_command_carries_an_expression(self):
        """Text from the pull request reaches a step through `env` only, so no `run` block has `${{ }}` in it at all."""
        for name, job in self.jobs.items():
            for step in steps(job):
                self.assertEqual(EXPRESSION.findall(step.get("run", "")), [], f"{name}: {step.get('name')}")

    def test_the_pull_request_is_checked_out_only_beside_the_code_and_read_offline(self):
        job = self.jobs["compare"]
        paths = [s["with"]["path"] for s in steps(job) if s.get("uses", "").startswith("actions/checkout@")]
        self.assertEqual(paths, ["code", "merge", "before"])
        for step in steps(job):
            if "run" in step and step.get("id") != "sides":
                self.assertEqual(step.get("working-directory"), "code", step.get("name"))
        compare = next(s for s in steps(job) if s.get("id") == "compare")["run"]
        self.assertIn("--offline", compare)
        self.assertIn('--head-root "$GITHUB_WORKSPACE/merge"', compare)
        self.assertIn("python infrastructure/scripts/ops/dependency_gate.py", compare)

    def test_output_that_may_carry_text_from_the_pull_request_is_fenced(self):
        for name in ("compare", "registry"):
            run = next(s["run"] for s in steps(self.jobs[name]) if "dependency_gate.py" in s.get("run", ""))
            start, gate, end = run.index('echo "::stop-commands::$marker"'), run.index("dependency_gate.py"), run.index('echo "::$marker::"')
            self.assertTrue(start < gate < end, name)

    def test_the_verdict_always_runs_and_passes_on_exactly_two_endings(self):
        job = self.jobs["verdict"]
        self.assertEqual(job["needs"], ["compare", "registry"])
        self.assertTrue(job["if"].startswith("always() && "))
        run = steps(job)[0]["run"]
        self.assertEqual(run.count("exit 0"), 2)
        self.assertIn('[ "$COMPARE" = success ] && [ "$ASK" = false ]', run)
        self.assertIn('[ "$COMPARE" = success ] && [ "$ASK" = true ] && [ "$REGISTRY" = success ]', run)
        self.assertTrue(run.rstrip().endswith("exit 1"))


if __name__ == "__main__":
    unittest.main()
