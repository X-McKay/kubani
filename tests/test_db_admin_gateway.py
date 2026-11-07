"""The monitoring backend is authenticated, authorized and separately scoped."""

import json
import sys
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GITOPS = ROOT / "infrastructure/gitops"
GATEWAY = GITOPS / "apps/ai-gateway/agents"
sys.path.insert(0, str(ROOT / "infrastructure/scripts/ops"))
from mcp_registry.render import build


def documents(path):
    return [item for item in yaml.safe_load_all(path.read_text()) if item]


class DbAdminGatewayTest(unittest.TestCase):
    def test_route_has_all_authorization_layers(self):
        docs = documents(GATEWAY / "registry-generated/backends.yaml")
        by_name = {doc["metadata"]["name"]: doc for doc in docs}
        route = next(doc for doc in docs if doc["kind"] == "HTTPRoute")
        self.assertEqual(route["spec"]["hostnames"], ["mcp.agents.internal"])
        self.assertEqual(route["spec"]["rules"][0]["matches"][0]["path"]["value"], "/postgres-admin/mcp")
        backend = next(doc for doc in docs if doc["kind"] == "AgentgatewayBackend")
        self.assertEqual(backend["spec"]["mcp"]["failureMode"], "FailClosed")
        self.assertEqual(backend["spec"]["mcp"]["targets"][0]["static"]["host"], "postgres-admin-mcp.mcp.svc.cluster.local")
        auth = build(ROOT)
        for name in ("agents-jwt", "agents-only"):
            policy = next(doc for doc in auth if doc["metadata"]["name"] == name)
            self.assertIn("agents-mcp-postgres-admin", [ref["name"] for ref in policy["spec"]["targetRefs"]])
        extauth = by_name["agents-extauth-mcp-postgres-admin"]["spec"]["traffic"]["extAuth"]
        self.assertEqual(extauth["failureMode"], "FailClosed")
        self.assertEqual(extauth["grpc"]["contextExtensions"], {"route": "mcp", "backend": "postgres-admin"})
        policy = by_name["agents-mcp-postgres-admin-tools"]["spec"]["backend"]["mcp"]["authorization"]["policy"]["matchExpressions"]
        self.assertEqual(len(policy), 1)
        self.assertIn('"agent-role-postgres-admin-read" in jwt.realm_access.roles', policy[0])
        self.assertIn('mcp.tool.name == "execute_sql"', policy[0])
        self.assertIn('jwt.client_type == "agent"', policy[0])

    def test_new_signer_is_exact_and_shared(self):
        docs = documents(GITOPS / "infrastructure/namespace-policy/agent-platform-namespaces.yaml")
        namespace = next(d for d in docs if d["metadata"]["name"] == "tenant-test")
        pattern = namespace["metadata"]["annotations"]["agentplatform.io/signer-subject-regexp"]
        pins = documents(GITOPS / "infrastructure/kyverno/tenant-signers.yaml")[0]
        self.assertEqual(json.loads(pins["data"]["tenant-test"])["subjectRegExp"], pattern)
        prefix = "https://github.com/X-McKay/zetra-agents/.github/workflows/release.yml@refs/"
        self.assertRegex(prefix + "tags/db-admin/v0.1.0", pattern)
        for suffix in ("tags/db-admin-other/v0.1.0", "heads/db-admin/v0.1.0", "tags/db-admin/v"):
            self.assertIsNone(re.fullmatch(pattern, prefix + suffix))

    def test_bootstrap_audience_is_not_a_login_client(self):
        delta = json.loads((GITOPS / "apps/keycloak/db-admin-backend.json").read_text())
        resource = delta["resource"]
        self.assertEqual(resource["clientId"], "https://mcp.almckay.io/postgres-admin/mcp")
        self.assertTrue(resource["bearerOnly"])
        for key in ("standardFlowEnabled", "directAccessGrantsEnabled", "serviceAccountsEnabled"):
            self.assertFalse(resource[key])
        self.assertEqual(delta["scope"]["name"], "mcp:postgres-admin")
        self.assertEqual(delta["requester"], "agent-policy-service")
        self.assertEqual(delta["attachment"], "optional")


if __name__ == "__main__":
    unittest.main()
