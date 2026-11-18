"""The agents gateway's model pin accepts exactly an engine's served name and its catalog aliases."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infrastructure/scripts/ops"))
import registry_feed  # noqa: E402

POLICIES = ROOT / "infrastructure/gitops/apps/ai-gateway/agents/policies-auth.yaml"
TERM = re.compile(r'llm\.requestModel == "([^"]+)"')


def accepted_models(policy: dict) -> set[str]:
    """The names the first Require expression allows; it must be nothing but `llm.requestModel == "x"` joined by ||."""
    expression = policy["spec"]["traffic"]["authorization"]["policy"]["matchExpressions"][0]
    names = TERM.findall(expression)
    if " || ".join(f'llm.requestModel == "{n}"' for n in names) != expression:
        raise AssertionError(f"not a plain list of model names: {expression}")
    return set(names)


class ModelPinAliases(unittest.TestCase):
    def test_each_pin_accepts_the_served_name_and_the_aliases_of_its_engine_only(self):
        feed = registry_feed.render(ROOT)
        policies = {doc["metadata"]["name"]: doc for doc in yaml.safe_load_all(POLICIES.read_text())}
        checked = 0
        for engine in feed["modelEngines"]:
            if engine["backend"] is None:
                continue
            aliases = {a["alias"] for a in feed["aliases"] if a["engine"] == engine["name"]}
            self.assertTrue(aliases, f"engine {engine['name']} has a backend but no alias")
            with self.subTest(backend=engine["backend"]):
                policy = policies[f"agents-inference-{engine['backend']}-model-pin"]
                self.assertEqual(accepted_models(policy), {engine["servedName"]} | aliases)
                checked += 1
        self.assertGreaterEqual(checked, 2)


if __name__ == "__main__":
    unittest.main()
