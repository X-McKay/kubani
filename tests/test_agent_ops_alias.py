"""`just agent alias ...`: a fake registry on loopback, a fake sign-in and fake tokens; no real credential, cluster or network."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
import outcome  # noqa: E402
from agent_ops import registry_client  # noqa: E402

import test_agent_ops as base  # noqa: E402
from test_agent_ops_registry import RegistryCase, error  # noqa: E402

MOVES = "/v1/alias-moves"
ASSESSMENT = {
    "id": "asm-1",
    "cluster": "kubani",
    "alias": "fast",
    "from": {"engine": "fast", "release": "Qwen-Qwen3.5-0.8B"},
    "candidate": {"engine": "fast", "release": "Qwen3.5-0.8B-r2"},
    "dependants": [
        {"deployment": "agent:kubani:tenant-test:held-one", "agent": "held-one", "tenant": "tenant-test", "authority": "registry", "enabled": True, "release": "held-one-2026-11-19-0a1b2c3d", "held": True, "evaluation": "required", "needs": [{"need": "toolCalling", "met": True}, {"need": "vision", "met": None}]},
        {"deployment": "agent:kubani:tenant-test:git-one", "agent": "git-one", "tenant": "tenant-test", "authority": "pull-request", "enabled": True, "release": None, "held": False, "evaluation": "none", "needs": []},
    ],
    "blocked": False,
    "digest": "sha256:x",
}
BLOCKED = {**ASSESSMENT, "id": "asm-2", "blocked": True, "dependants": [{**ASSESSMENT["dependants"][0], "needs": [{"need": "toolCalling", "met": False}]}]}
MOVE = {
    "id": "mv-1",
    "alias": "fast",
    "state": "holding",
    "candidate": {"engine": "fast", "release": "Qwen3.5-0.8B-r2"},
    "holds": [{"agent": "held-one", "state": "holding", "running": 2, "reason": None}],
    "next": "waiting for 1 agent(s) to stop: held-one",
}


class AliasCase(RegistryCase):
    def setUp(self):
        super().setUp()
        self.root = base.make_root(self.tmp)

    def alias(self, *argv):
        return self.document(["alias", *argv])

    def plan_args(self):
        return ["plan", "fast", "--engine", "fast", "--release", "Qwen3.5-0.8B-r2"]


class PlanTests(AliasCase):
    def test_posts_the_body_and_prints_every_dependant_and_the_unheld_ones_apart(self):
        self.registry.routes[("POST", "/v1/assessments")] = (200, ASSESSMENT)
        code, out, err = self.run_cli(["alias", *self.plan_args()])
        self.assertEqual(code, 0, err)
        post = self.registry.posts()[0]
        self.assertEqual(post["body"], {"cluster": "kubani", "alias": "fast", "candidate": {"engine": "fast", "release": "Qwen3.5-0.8B-r2"}})
        self.assertEqual(post["auth"], "Bearer person-token")
        before, _, after = out.partition("Not held")
        self.assertIn("held-one", before)
        self.assertIn("will be held", before)
        self.assertIn("toolCalling met", before)
        self.assertIn("vision not recorded", before)
        self.assertIn("git-one", before)
        self.assertIn("git-one", after)
        self.assertNotIn("held-one", after.split("assessment asm-1")[0])
        self.assertIn("next: just agent alias move asm-1", out)

    def test_blocked_assessment_is_printed_and_ends_refused(self):
        self.registry.routes[("POST", "/v1/assessments")] = (200, BLOCKED)
        code, out, err = self.run_cli(["alias", *self.plan_args()])
        self.assertEqual(code, 2)
        self.assertIn("needs toolCalling: the candidate does not offer it", err)
        self.assertIn("BLOCKED", err)
        doc = json.loads(out)
        self.assertEqual((doc["ok"], doc["error"]["code"], doc["id"]), (False, "refused", "asm-2"))
        self.assertIn("toolCalling", doc["error"]["message"])


class MoveTests(AliasCase):
    def test_posts_the_assessment_sessions_and_seconds(self):
        self.registry.routes[("POST", MOVES)] = (200, MOVE)
        code, out, err = self.run_cli(["alias", "move", "asm-1", "--sessions", "cancel", "--evaluation-seconds", "120"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.registry.posts()[0]["body"], {"assessment": "asm-1", "sessions": "cancel", "evaluationSeconds": 120})
        self.assertIn("move mv-1", out)
        self.assertIn("state holding", out)
        self.assertIn("next: waiting for 1 agent(s) to stop: held-one", out)
        self.assertIn("running sessions 2", out)

    def test_sessions_default_to_finish(self):
        self.registry.routes[("POST", MOVES)] = (200, MOVE)
        self.run_cli(["alias", "move", "asm-1"])
        self.assertEqual(self.registry.posts()[0]["body"], {"assessment": "asm-1", "sessions": "finish"})

    def test_stale_assessment_ends_with_its_own_code(self):
        self.registry.routes[("POST", MOVES)] = (409, error("stale-assessment", "the alias changed since the assessment"))
        code, doc, _ = self.alias("move", "asm-1")
        self.assertEqual((code, doc["ok"], doc["error"]["code"], doc["error"]["retryable"]), (2, False, "stale-assessment", False))
        self.assertIn("the alias changed", doc["error"]["message"])

    def test_an_open_move_is_a_conflict(self):
        self.registry.routes[("POST", MOVES)] = (409, error("conflict", "the alias has an open move"))
        code, doc, _ = self.alias("move", "asm-1")
        self.assertEqual((code, doc["error"]["code"]), (2, "conflict"))


class StatusTests(AliasCase):
    def test_one_move_by_id_uses_the_reader_and_prints_holds_and_next(self):
        self.registry.routes[("GET", f"{MOVES}/mv-1")] = (200, MOVE)
        code, out, err = self.run_cli(["alias", "status", "mv-1"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.registry.requests[0]["auth"], "Bearer reader-token")
        self.assertIn("hold held-one: holding", out)
        self.assertIn("next: waiting for 1 agent(s) to stop: held-one", out)
        self.assertEqual(self.signins, [])

    def test_open_moves_of_an_alias(self):
        self.registry.routes[("GET", MOVES)] = (200, {"moves": [MOVE]})
        code, out, _ = self.run_cli(["alias", "status", "--alias", "fast"])
        self.assertEqual(code, 0)
        self.assertEqual(self.registry.requests[0]["query"], {"cluster": ["kubani"], "alias": ["fast"], "open": ["true"]})
        self.assertIn("move mv-1", out)
        self.assertIn("next:", out)

    def test_no_move_lists_every_open_move_of_the_cluster(self):
        self.registry.routes[("GET", MOVES)] = (200, {"moves": []})
        code, out, _ = self.run_cli(["alias", "status"])
        self.assertEqual((code, self.registry.requests[0]["query"]), (0, {"cluster": ["kubani"], "open": ["true"]}))
        self.assertIn("no open alias moves", out)


class EvaluateCancelTests(AliasCase):
    def test_evaluate_refused_prints_what_is_missing(self):
        self.registry.routes[("POST", f"{MOVES}/mv-1/evaluate")] = (409, error("refused", "the newest observation of fast is stale and does not show readyReplicas of 1"))
        code, doc, err = self.alias("evaluate", "mv-1")
        self.assertEqual((code, doc["error"]["code"]), (2, "refused"))
        self.assertIn("does not show readyReplicas", doc["error"]["message"])
        self.assertIn("does not show readyReplicas", err)

    def test_evaluate_prints_the_move(self):
        self.registry.routes[("POST", f"{MOVES}/mv-1/evaluate")] = (200, {**MOVE, "state": "evaluating", "next": "evaluating 1 agent(s) until later"})
        code, out, _ = self.run_cli(["alias", "evaluate", "mv-1"])
        self.assertEqual(code, 0)
        self.assertIn("state evaluating", out)

    def test_cancel_sends_the_reason(self):
        self.registry.routes[("POST", f"{MOVES}/mv-1/cancel")] = (200, {**MOVE, "state": "cancelled", "next": "done"})
        code, out, _ = self.run_cli(["alias", "cancel", "mv-1", "--reason", "wrong candidate"])
        self.assertEqual(code, 0)
        self.assertEqual(self.registry.posts()[0]["body"], {"reason": "wrong candidate"})
        self.assertIn("state cancelled", out)


class JsonAndFailureTests(AliasCase):
    def test_json_prints_the_registrys_document_unchanged_for_each_command(self):
        self.registry.routes[("POST", "/v1/assessments")] = (200, ASSESSMENT)
        self.registry.routes[("POST", MOVES)] = (200, MOVE)
        self.registry.routes[("GET", f"{MOVES}/mv-1")] = (200, MOVE)
        self.registry.routes[("GET", MOVES)] = (200, {"moves": [MOVE]})
        self.registry.routes[("POST", f"{MOVES}/mv-1/evaluate")] = (200, MOVE)
        self.registry.routes[("POST", f"{MOVES}/mv-1/cancel")] = (200, MOVE)
        cases = [
            (self.plan_args(), ASSESSMENT),
            (["move", "asm-1"], MOVE),
            (["status", "mv-1"], MOVE),
            (["status"], {"moves": [MOVE]}),
            (["evaluate", "mv-1"], MOVE),
            (["cancel", "mv-1", "--reason", "r"], MOVE),
        ]
        for argv, document in cases:
            with self.subTest(argv=argv):
                code, doc, _ = self.alias(*argv, "--json")
                self.assertEqual(code, 0)
                self.assertEqual(doc, {**document, "ok": True})

    def test_json_of_a_blocked_assessment_carries_the_document_and_the_refusal(self):
        self.registry.routes[("POST", "/v1/assessments")] = (200, BLOCKED)
        code, doc, _ = self.alias(*self.plan_args(), "--json")
        self.assertEqual((code, doc["error"]["code"]), (2, "refused"))
        self.assertEqual({k: v for k, v in doc.items() if k not in ("ok", "error")}, BLOCKED)

    def test_a_registry_that_says_it_is_unavailable_ends_unavailable(self):
        self.registry.routes[("POST", "/v1/assessments")] = (503, error("unavailable", "the registry's database is down", retryable=True))
        code, doc, _ = self.alias(*self.plan_args())
        self.assertEqual((code, doc["error"]["code"], doc["error"]["retryable"]), (2, "unavailable", True))

    def test_evaluation_seconds_outside_the_range_are_refused_before_any_call(self):
        with self.assertRaises(SystemExit) as raised:
            self.run_cli(["alias", "move", "asm-1", "--evaluation-seconds", "59"])
        self.assertEqual((raised.exception.code, self.registry.requests), (2, []))


class FormatStatusTests(unittest.TestCase):
    BASE = {"cluster": "kubani", "mode": "x", "generation": 3, "agents": [{"agent": "a", "tenant": "t", "authority": "pull-request"}], "toolServers": [], "models": []}

    def test_open_moves_and_a_held_agent_are_printed(self):
        doc = {**self.BASE, "agents": [{**self.BASE["agents"][0], "held": {"move": "mv-1", "state": "suspended", "reason": "evaluation did not finish"}}], "aliasMoves": [{"id": "mv-1", "alias": "fast", "state": "evaluating", "next": "evaluating 1 agent(s)"}]}
        text = registry_client.format_status(doc)
        self.assertIn("held: alias move mv-1 suspended: evaluation did not finish", text)
        self.assertIn("Alias moves", text)
        self.assertIn("mv-1  alias fast  evaluating  next: evaluating 1 agent(s)", text)

    def test_a_document_without_those_keys_prints_as_before(self):
        text = registry_client.format_status({**self.BASE, "held": None, "aliasMoves": []})
        self.assertEqual(text, registry_client.format_status(self.BASE))
        self.assertNotIn("Alias moves", text)
        self.assertNotIn("held:", registry_client.format_status({**self.BASE, "agents": [{**self.BASE["agents"][0], "held": None}]}))


class CodeTests(unittest.TestCase):
    def test_stale_assessment_is_a_terminal_code(self):
        self.assertIs(outcome.CODES["stale-assessment"], False)


if __name__ == "__main__":
    unittest.main()
