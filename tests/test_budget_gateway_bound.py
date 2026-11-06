"""Run the budget route/body rules in the same pinned gateway as production bounds."""
import copy
from pathlib import Path

import test_inference_completion_bound as completion
import yaml

POLICIES = Path(__file__).resolve().parents[1] / "infrastructure/gitops/apps/ai-gateway/agents/budget-conformance.yaml"


def resources():
    return {d["metadata"]["name"]: d for d in yaml.safe_load_all(POLICIES.read_text())}


class BudgetGatewayTests(completion.CompletionGatewayTests):
    models = {"llm-budget-conformance": "conformance-byte-v1"}

    def authorization(self, backend):
        auth = copy.deepcopy(resources()["agents-inference-budget-bounds"]["spec"]["traffic"]["authorization"])
        # The local stub has no issuer or credentials. Isolate body rules; the
        # manifest regression checks strict JWT attachment and exact identities.
        identity = 'jwt.agent_id in ["tenant-test/conformance-budget-day", "tenant-test/conformance-budget-day-retry", "tenant-test/conformance-budget-session"]'
        self.assertIn(identity, auth["policy"]["matchExpressions"])
        auth["policy"]["matchExpressions"].remove(identity)
        return auth

    def route(self, backend):
        return resources()["agents-inference-llm-budget-conformance"]["spec"]["rules"][0]

    def additional_cases(self, base):
        return [
            ("max-output", {**base, "max_tokens": 101}, False),
            ("stream", {**base, "stream": True}, False),
            ("extra", {**base, "extra": 1}, False),
            ("temperature", {**base, "temperature": 1}, False),
            ("beam-field", {**base, "use_beam_search": False}, False),
        ]
