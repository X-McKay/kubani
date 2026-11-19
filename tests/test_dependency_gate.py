"""The dependency gate for pull requests: fake registry client, fake or real renderer, no network."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dependency_gate  # noqa: E402
import outcome  # noqa: E402
import registry_feed  # noqa: E402
from agent_ops import registry_client  # noqa: E402
from test_registry_feed import build_tree  # noqa: E402


def contract(*tools: str) -> dict:
    return {"server": "postgres-admin-mcp", "backend": "postgres-admin", "tools": [{"name": t, "effect": "remote_read"} for t in tools]}


def feed(*, tool_contract="unset", engines=None, aliases=None) -> dict:
    server = {"name": "postgres-admin-mcp", "cluster": "kubani", "backend": "postgres-admin"}
    if tool_contract != "unset":
        server["contract"] = tool_contract
    return {
        "clusters": [{"name": "kubani"}],
        "toolServers": [server],
        "modelEngines": engines if engines is not None else [{"name": "fast", "cluster": "kubani", "servedName": "Qwen3.5-0.8B"}, {"name": "main", "cluster": "kubani", "servedName": "Qwen Main", "release": "main-r1"}],
        "aliases": aliases if aliases is not None else [{"cluster": "kubani", "alias": "fast", "engine": "fast"}],
    }


BLOCKED = {
    "server": "postgres-admin-mcp",
    "backend": "postgres-admin",
    "blocked": True,
    "findings": [{"deployment": "agent:kubani:tenant-test:db-admin", "agent": "db-admin", "tenant": "tenant-test", "authority": "pull-request", "tool": "execute_sql", "finding": "tool-removed", "blocks": True, "action": "keep execute_sql on postgres-admin, or release db-admin without it first"}],
    "reevaluated": [],
    "users": 1,
}
CLEAR = {"server": "postgres-admin-mcp", "backend": "postgres-admin", "blocked": False, "findings": [{"agent": "notes", "tenant": "tenant-test", "tool": "list_tables", "finding": "description-changed", "blocks": False, "action": "evaluated again after the change"}], "reevaluated": [{"deployment": "agent:kubani:tenant-test:notes", "agent": "notes", "tenant": "tenant-test"}], "users": 1}


class Fake:
    """A registry client: answers by path, records every call."""

    def __init__(self, answers=None, error=None):
        self.answers, self.error, self.calls = answers or {}, error, []

    def post(self, path, body):
        self.calls.append((path, body))
        if self.error is not None:
            raise self.error
        answer = self.answers[path]
        return answer(body) if callable(answer) else answer


def run(base, head, fake, *extra):
    """The gate's main with a fake renderer keyed by root name; returns (status, stdout)."""

    def render(root):
        value = {"base": base, "head": head}[Path(root).name]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = dependency_gate.main(["--base-root", "base", "--head-root", "head", *extra], client_factory=lambda: fake, render=render)
    return status, out.getvalue()


class ToolContracts(unittest.TestCase):
    def test_removed_tool_is_blocked_and_named(self):
        fake = Fake({"/v1/checks/tool-contract": BLOCKED})
        status, text = run(feed(tool_contract=contract("execute_sql", "list_tables")), feed(tool_contract=contract("list_tables")), fake)
        self.assertEqual(status, 1)
        for word in ("db-admin", "tenant-test", "execute_sql", "tool-removed", "keep execute_sql on postgres-admin, or release db-admin without it first"):
            self.assertIn(word, text)
        self.assertEqual(fake.calls, [("/v1/checks/tool-contract", {"cluster": "kubani", "server": "postgres-admin-mcp", "contract": contract("list_tables")})])

    def test_identical_feeds_make_no_call(self):
        fake = Fake()
        status, text = run(feed(tool_contract=contract("a")), feed(tool_contract=contract("a")), fake)
        self.assertEqual((status, fake.calls), (0, []))
        self.assertIn("gate passed", text)

    def test_changed_contract_not_blocked_names_reevaluated_agents(self):
        fake = Fake({"/v1/checks/tool-contract": CLEAR})
        status, text = run(feed(tool_contract=contract("a")), feed(tool_contract=contract("a", "b")), fake)
        self.assertEqual(status, 0)
        self.assertIn("re-evaluated: notes (tenant-test)", text)
        self.assertEqual(len(fake.calls), 1)

    def test_new_contract_is_asked_about(self):
        fake = Fake({"/v1/checks/tool-contract": CLEAR})
        status, _ = run(feed(), feed(tool_contract=contract("a")), fake)
        self.assertEqual((status, len(fake.calls)), (0, 1))

    def test_removed_contract_fails_without_a_call(self):
        fake = Fake()
        status, text = run(feed(tool_contract=contract("a")), feed(tool_contract=None), fake)
        self.assertEqual((status, fake.calls), (1, []))
        self.assertIn("the recorded contract of postgres-admin-mcp was removed", text)


class Aliases(unittest.TestCase):
    ANSWER = "/v1/checks/alias"

    def moved(self, release_a=None, release_b=None, served_b="Qwen3.5-0.8B-r2", engine="fast"):
        base = feed(engines=[{"name": "fast", "cluster": "kubani", "servedName": "Qwen3.5-0.8B", **({"release": release_a} if release_a else {})}])
        head = feed(
            engines=[{"name": "fast", "cluster": "kubani", "servedName": served_b, **({"release": release_b} if release_b else {})}, {"name": "main", "cluster": "kubani", "servedName": "Qwen Main", "release": "main-r1"}],
            aliases=[{"cluster": "kubani", "alias": "fast", "engine": engine, "move": "mv-1"}],
        )
        return base, head

    def test_release_change_not_allowed_fails_with_reason(self):
        fake = Fake({self.ANSWER: {"allowed": False, "move": "", "assessment": "", "reason": "the move is still holding"}})
        status, text = run(*self.moved("r1", "r2"), fake)
        self.assertEqual(status, 1)
        self.assertIn("the move is still holding", text)
        self.assertEqual(fake.calls, [(self.ANSWER, {"cluster": "kubani", "alias": "fast", "candidate": {"engine": "fast", "release": "r2"}})])

    def test_release_change_allowed_passes(self):
        fake = Fake({self.ANSWER: {"allowed": True, "move": "mv-1", "assessment": "asm-1", "reason": ""}})
        status, text = run(*self.moved("r1", "r2"), fake)
        self.assertEqual(status, 0)
        self.assertIn("move mv-1", text)

    def test_engine_without_release_is_compared_by_slug_of_served_name(self):
        fake = Fake({self.ANSWER: {"allowed": True, "reason": ""}})
        status, _ = run(*self.moved(served_b="Qwen 3.5/r2"), fake)
        self.assertEqual(status, 0)
        self.assertEqual(fake.calls[0][1]["candidate"], {"engine": "fast", "release": "Qwen-3.5-r2"})
        self.assertEqual(dependency_gate.release_slug("--"), "unnamed")

    def test_alias_pointing_at_another_engine_is_checked(self):
        fake = Fake({self.ANSWER: {"allowed": False, "reason": "no move for this candidate"}})
        base, head = self.moved(engine="main")
        status, text = run(base, head, fake)
        self.assertEqual(status, 1)
        self.assertEqual(fake.calls[0][1]["candidate"], {"engine": "main", "release": "main-r1"})
        self.assertIn("fast/Qwen3.5-0.8B -> main/main-r1", text)

    def test_new_alias_makes_no_call_and_removed_alias_is_a_note(self):
        fake = Fake()
        base = feed()
        added = feed(aliases=[{"cluster": "kubani", "alias": "fast", "engine": "fast"}, {"cluster": "kubani", "alias": "big", "engine": "main"}])
        self.assertEqual((run(base, added, fake)[0], fake.calls), (0, []))
        status, text = run(base, feed(aliases=[]), fake)
        self.assertEqual((status, fake.calls), (0, []))
        self.assertIn("alias fast is only in the base; this check does not cover removals", text)


class Failures(unittest.TestCase):
    def test_unreachable_registry_fails_with_its_code_even_after_a_pass(self):
        fake = Fake({"/v1/checks/tool-contract": CLEAR})
        calls = fake.post

        def post(path, body):
            if path == "/v1/checks/alias":
                raise registry_client.RegistryError("down", "unavailable")
            return calls(path, body)

        fake.post = post
        base = feed(tool_contract=contract("a"))
        head = feed(tool_contract=contract("a", "b"), engines=[{"name": "fast", "cluster": "kubani", "servedName": "Other"}])
        status, text = run(base, head, fake, "--json")
        doc = json.loads(text)
        self.assertEqual((status, doc["ok"], doc["error"]["code"]), (1, False, "unavailable"))

    def test_head_that_does_not_render_is_check_failed(self):
        status, text = run(feed(), ValueError("catalog.yaml: version must be 1"), Fake(), "--json")
        doc = json.loads(text)
        self.assertEqual((status, doc["error"]["code"]), (1, "check-failed"))
        self.assertIn("version must be 1", doc["error"]["message"])

    def test_base_that_does_not_render_is_failed(self):
        status, text = run(ValueError("broken"), feed(), Fake(), "--json")
        self.assertEqual((status, json.loads(text)["error"]["code"]), (1, "failed"))

    def test_several_clusters_need_a_choice(self):
        two = feed()
        two["clusters"].append({"name": "other"})
        status, text = run(two, two, Fake(), "--json")
        self.assertEqual((status, json.loads(text)["error"]["code"]), (1, "invalid-arguments"))
        self.assertEqual(run(two, two, Fake(), "--cluster", "kubani")[0], 0)


class JsonOutput(unittest.TestCase):
    def test_json_carries_the_same_verdict(self):
        status, text = run(feed(tool_contract=contract("execute_sql")), feed(tool_contract=contract("x")), Fake({"/v1/checks/tool-contract": BLOCKED}), "--json")
        doc = json.loads(text)
        self.assertEqual((status, doc["ok"], doc["error"]["code"]), (1, False, "check-failed"))
        self.assertEqual(doc["toolContracts"][0]["findings"][0]["agent"], "db-admin")
        status, text = run(feed(), feed(), Fake(), "--json")
        self.assertEqual((status, json.loads(text)["ok"]), (0, True))


class SplitRun(unittest.TestCase):
    """The run as the workflow splits it: compare without the registry, hand the two feeds over, then ask."""

    BASE = staticmethod(lambda: feed(tool_contract=contract("execute_sql", "list_tables"), engines=[{"name": "fast", "cluster": "kubani", "servedName": "A", "release": "r1"}]))
    HEAD = staticmethod(lambda: feed(tool_contract=contract("list_tables"), engines=[{"name": "fast", "cluster": "kubani", "servedName": "B", "release": "r2"}]))

    def unreachable(self):
        self.fail("an offline run built a registry client")

    def offline(self, base, head, *extra):
        def render(root):
            return copy.deepcopy({"base": base, "head": head}[Path(root).name])

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = dependency_gate.main(["--base-root", "base", "--head-root", "head", "--offline", *extra], client_factory=self.unreachable, render=render)
        return status, out.getvalue()

    def from_files(self, directory, fake, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = dependency_gate.main(["--base-feed", str(Path(directory, "base.json")), "--head-feed", str(Path(directory, "head.json")), *extra], client_factory=lambda: fake, render=self.unreachable)
        return status, out.getvalue()

    def test_offline_lists_the_questions_and_is_not_a_pass(self):
        status, text = self.offline(self.BASE(), self.HEAD())
        self.assertEqual(status, 3)
        for line in ("to ask   contract of postgres-admin-mcp", "to ask   alias fast: fast/r1 -> fast/r2", "not decided: 2 question(s) for the registry were not asked"):
            self.assertIn(line, text)
        self.assertNotIn("gate passed", text)
        status, text = self.offline(self.BASE(), self.HEAD(), "--json")
        doc = json.loads(text)
        self.assertEqual((status, doc["ok"], doc["error"]["code"]), (3, False, "failed"))
        self.assertEqual(doc["unasked"], [{"path": "/v1/checks/tool-contract", "about": "contract of postgres-admin-mcp"}, {"path": "/v1/checks/alias", "about": "alias fast: fast/r1 -> fast/r2"}])

    def test_offline_with_nothing_to_ask_passes_and_a_removed_contract_still_fails(self):
        status, text = self.offline(self.BASE(), self.BASE(), "--json")
        self.assertEqual((status, json.loads(text)["ok"], json.loads(text)["unasked"]), (0, True, []))
        gone = self.HEAD()
        gone["toolServers"][0]["contract"] = None
        status, text = self.offline(self.BASE(), gone)
        self.assertEqual(status, 1)
        self.assertIn("gate failed: 1 check(s)", text)
        self.assertIn("to ask   alias fast", text)

    def test_the_feeds_written_offline_give_the_second_run_the_same_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.offline(self.BASE(), self.HEAD(), "--feeds-out", tmp)[0], 3)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["base.json", "head.json"])
            self.assertEqual(json.loads(Path(tmp, "head.json").read_text()), self.HEAD())
            fake = Fake({"/v1/checks/tool-contract": BLOCKED, "/v1/checks/alias": {"allowed": True, "move": "mv-1", "assessment": "asm-1", "reason": ""}})
            status, text = self.from_files(tmp, fake)
            self.assertEqual(status, 1)
            self.assertEqual(
                fake.calls,
                [
                    ("/v1/checks/tool-contract", {"cluster": "kubani", "server": "postgres-admin-mcp", "contract": contract("list_tables")}),
                    ("/v1/checks/alias", {"cluster": "kubani", "alias": "fast", "candidate": {"engine": "fast", "release": "r2"}}),
                ],
            )
            self.assertIn("BLOCKED  contract of postgres-admin-mcp", text)
            self.assertIn("ok       alias fast: fast/r1 -> fast/r2", text)
            fake = Fake({"/v1/checks/tool-contract": CLEAR, "/v1/checks/alias": {"allowed": True, "reason": ""}})
            self.assertEqual(self.from_files(tmp, fake)[0], 0)

    def test_a_feed_file_that_is_not_a_feed_ends_the_run_without_asking(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = json.dumps(self.BASE())
            bad = {
                "not JSON": "{",
                "not an object": "[]",
                "a tool server without a name": json.dumps({**self.HEAD(), "toolServers": [{"contract": contract("a")}]}),
                "an alias that is not an object": json.dumps({**self.HEAD(), "aliases": ["fast"]}),
                "a served name that is not text": json.dumps({**self.HEAD(), "modelEngines": [{"name": "fast", "servedName": ["x"]}]}),
            }
            for why, text in bad.items():
                with self.subTest(why):
                    Path(tmp, "base.json").write_text(good)
                    Path(tmp, "head.json").write_text(text)
                    fake = Fake()
                    status, out = self.from_files(tmp, fake, "--json")
                    self.assertEqual((status, json.loads(out)["error"]["code"], fake.calls), (1, "check-failed", []))
            Path(tmp, "head.json").write_text(good)
            Path(tmp, "base.json").unlink()
            status, out = self.from_files(tmp, Fake(), "--json")
            self.assertEqual((status, json.loads(out)["error"]["code"]), (1, "failed"))

    def test_the_two_ways_to_name_the_feeds_do_not_mix(self):
        for argv in ([], ["--base-root", "a"], ["--base-root", "a", "--head-feed", "b"], ["--base-root", "a", "--head-root", "b", "--base-feed", "c"], ["--base-feed", "a", "--head-feed", "b", "--feeds-out", "c"]):
            with self.subTest(argv), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                dependency_gate.main(argv, client_factory=self.unreachable, render=self.unreachable)
            self.assertEqual((raised.exception.code, json.loads(out.getvalue())["error"]["code"]), (2, "invalid-arguments"))


class HeadIsData(unittest.TestCase):
    def test_nothing_in_the_head_tree_is_imported_or_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, head = Path(tmp, "base"), Path(tmp, "head")
            marker = Path(tmp, "marker")
            for root in (base, head):
                root.mkdir()
                build_tree(root)
            planted = head / "infrastructure/scripts/ops"
            planted.mkdir(parents=True)
            for name in ("registry_feed.py", "outcome.py", "sitecustomize.py"):
                (planted / name).write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = dependency_gate.main(["--base-root", str(base), "--head-root", str(head)], client_factory=lambda: Fake())
            self.assertEqual(status, 0, out.getvalue())
            self.assertFalse(marker.exists())
            self.assertIs(dependency_gate.registry_feed, registry_feed)


if __name__ == "__main__":
    unittest.main()
