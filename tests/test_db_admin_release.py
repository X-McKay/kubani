"""Applied agent budgets must admit the gateway's actual reservation policy."""

import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1] / "infrastructure/gitops/apps"


class DbAdminReleaseTests(unittest.TestCase):
    def test_session_and_day_budget_fit_backend_reservation(self):
        agent = yaml.safe_load((ROOT / "agents/tenant-test/db-admin/agent.yaml").read_text())
        deployment = next(
            d for d in yaml.safe_load_all(
                (ROOT / "agent-platform/workloads/agent-policy-service.yaml").read_text()
            ) if d and d["kind"] == "Deployment"
        )
        env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        catalogue = json.loads(next(e["value"] for e in env if e["name"] == "APS_BACKEND_CATALOGUE"))
        for grant in agent["spec"]["capabilities"]["models"]:
            with self.subTest(backend=grant["backend"]):
                reservation = catalogue[grant["backend"]]["maxModelLen"]
                self.assertGreaterEqual(grant["budget"]["tokensPerSession"], reservation)
                self.assertGreaterEqual(grant["budget"]["tokensPerDay"], reservation)

    def test_agent_uses_only_the_dedicated_read_backend(self):
        agent = yaml.safe_load((ROOT / "agents/tenant-test/db-admin/agent.yaml").read_text())
        self.assertEqual(agent["spec"]["identity"], {"mode": "agent"})
        self.assertEqual(agent["spec"]["capabilities"]["mcp"], [{
            "backend": "postgres-admin", "effect": "remote_read", "tools": ["execute_sql"],
            "delegation": "inherit",
        }])


if __name__ == "__main__":
    unittest.main()
