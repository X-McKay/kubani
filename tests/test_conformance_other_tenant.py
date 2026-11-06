"""The Bob planner never authorizes or contacts a live issuer."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

PATH = (
    Path(__file__).resolve().parents[1]
    / "infrastructure/scripts/ops/conformance-other-tenant.py"
)


class OtherTenantPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("other_tenant", PATH)
        cls.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.helper)

    def snapshot(self):
        return {
            "profile": {
                "attributes": [{"name": "username", "unknown": {"preserve": True}}],
                "groups": [{"name": "keep"}],
                "future": {"keep": [1]},
            },
            "desired_bob_username_exists": False,
            "agent_cli_optional_scope_names": ["offline_access"],
        }

    def test_profile_preserved_exactly_except_one_managed_attribute(self):
        source = self.snapshot()
        before = copy.deepcopy(source)
        plan = self.helper.plan(source)
        after = plan["operations"][0]["body"]
        self.assertEqual(after["attributes"][:-1], source["profile"]["attributes"])
        self.assertEqual(after["groups"], source["profile"]["groups"])
        self.assertEqual(after["future"], source["profile"]["future"])
        self.assertNotIn("unmanagedAttributePolicy", after)
        self.assertEqual(source, before)
        attr = after["attributes"][-1]
        self.assertEqual(attr["permissions"], {"view": ["admin"], "edit": ["admin"]})
        self.assertFalse(attr["multivalued"])

    def test_partial_snapshot_never_approval_ready(self):
        plan = self.helper.plan(self.snapshot())
        self.assertFalse(plan["approval_ready"])
        self.assertFalse(plan["apply_authorized"])
        self.assertGreater(len(plan["required_readonly_inputs"]), 5)

    def test_existing_bob_or_managed_field_refused(self):
        source = self.snapshot()
        source["desired_bob_username_exists"] = True
        with self.assertRaises(ValueError):
            self.helper.plan(source)
        source = self.snapshot()
        source["profile"]["attributes"].append({"name": "conformance_tenant"})
        with self.assertRaises(ValueError):
            self.helper.plan(source)

    def test_missing_or_duplicate_profile_refused(self):
        for source in ({}, {"profile": {"attributes": [{"name": "x"}, {"name": "x"}]}}):
            with self.assertRaises(ValueError):
                self.helper.plan(source)

    def test_no_secrets_network_randomness_or_subprocess(self):
        with (
            patch("subprocess.run", side_effect=AssertionError("subprocess")),
            patch("socket.socket", side_effect=AssertionError("network")),
            patch("secrets.token_urlsafe", side_effect=AssertionError("random")),
        ):
            plan = self.helper.plan(self.snapshot())
        text = json.dumps(plan)
        self.assertNotIn("conformance_fixture", text)
        self.assertNotIn("credentials", plan["operations"][-1]["body"])
        self.assertEqual(plan, self.helper.plan(self.snapshot()))

    def test_only_fixed_scope_and_user_operations(self):
        operations = self.helper.plan(self.snapshot())["operations"]
        self.assertEqual(
            [op["method"] for op in operations], ["PUT", "POST", "PUT", "POST"]
        )
        user = operations[-1]["body"]
        self.assertEqual(user["attributes"], {"conformance_tenant": ["tenant-other"]})
        self.assertNotIn("realmRoles", user)
        self.assertNotIn("groups", user)
        mapper = operations[1]["body"]["protocolMappers"][0]
        self.assertEqual(mapper["config"]["access.token.claim"], "true")
        for field in (
            "id.token.claim",
            "userinfo.token.claim",
            "introspection.token.claim",
        ):
            self.assertEqual(mapper["config"][field], "false")

    def test_cli_refuses_apply_and_never_echoes_input(self):
        result = subprocess.run(
            [sys.executable, str(PATH), "--apply"], capture_output=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"Traceback", result.stderr)


def complete_snapshot():
    from datetime import datetime, timezone
    from uuid import UUID

    def uid(number):
        return str(UUID(int=number))

    profile = {"attributes": [{"name": "username"}], "groups": []}
    scope = {"id": uid(3), "name": "profile", "protocol": "openid-connect"}
    realm_role = {
        "id": uid(4),
        "name": "default-roles-agents",
        "composite": False,
        "clientRole": False,
        "containerId": uid(5),
    }
    return {
        "version": "26.8.1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "desired_bob_username_exists": False,
        "agent_cli_optional_scope_names": [],
        "read_request_count": 20,
        "complete_client_pagination": True,
        "complete_user_pagination": True,
        "default_group_count": 0,
        "agent_cli": {
            "id": uid(1),
            "clientId": "agent-cli",
            "publicClient": True,
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": False,
            "attributes": {"pkce.code.challenge.method": "S256"},
            "redirectUris": ["http://localhost/*", "http://127.0.0.1/*"],
        },
        "account_client": {"id": uid(2), "clientId": "account"},
        "scopes": [{**scope, "mappers": []}],
        "clients": [
            {
                "id": uid(1),
                "clientId": "agent-cli",
                "mappers": [],
                "default_scopes": [scope],
                "optional_scopes": [],
            },
            {
                "id": uid(2),
                "clientId": "account",
                "mappers": [],
                "default_scopes": [],
                "optional_scopes": [],
            },
        ],
        "users": [{"id": uid(6), "conformance_tenant_present": False}],
        "realm": {
            "defaultRole": realm_role,
            "registrationEnabled": None,
            "userManagedAccessAllowed": False,
        },
        "default_roles": {uid(4): {"role": realm_role, "composites": []}},
        "mapper_projection": "synthetic bounded projection",
    }


class CompleteOtherTenantPlanTests(unittest.TestCase):
    setUpClass = OtherTenantPlanTests.__dict__["setUpClass"]

    def test_complete_plan_resolves_only_verified_client_and_requires_approval(self):
        source = complete_snapshot()
        result = self.helper.plan(source)
        self.assertTrue(result["approval_ready"])
        self.assertFalse(result["apply_authorized"])
        self.assertIn(source["agent_cli"]["id"], result["operations"][2]["path"])
        source["observed_at"] = source["observed_at"].replace("+00:00", "Z")
        source["read_request_count"] += 1
        self.assertEqual(result, self.helper.plan(source))

    def test_incomplete_associated_or_privileged_default_reads_refused(self):
        for fault in (
            "role",
            "pagination",
            "user",
            "groups",
            "pkce",
            "scope_mapper",
            "direct_mapper",
            "duplicate_client",
        ):
            source = complete_snapshot()
            if fault == "role":
                next(iter(source["default_roles"].values()))["role"]["name"] = (
                    "realm-admin"
                )
            elif fault == "pagination":
                source["complete_user_pagination"] = False
            elif fault == "user":
                source["users"][0]["conformance_tenant_present"] = True
            elif fault == "groups":
                source["default_group_count"] = 1
            elif fault == "pkce":
                source["agent_cli"]["attributes"] = {}
            elif fault in ("scope_mapper", "direct_mapper"):
                owner = (
                    source["scopes"][0]
                    if fault == "scope_mapper"
                    else source["clients"][0]
                )
                owner["mappers"] = [
                    {"id": source["users"][0]["id"], "config": {"claim.name": "tenant"}}
                ]
            else:
                source["clients"].append(copy.deepcopy(source["clients"][0]))
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.helper.plan(source)

    def test_unrelated_agent_tenant_scope_preserved_but_managed_attribute_collision_refused(
        self,
    ):
        source = complete_snapshot()
        from uuid import UUID

        scope = {
            "id": str(UUID(int=100)),
            "name": "agent-claims-existing",
            "protocol": "openid-connect",
            "mappers": [
                {
                    "id": str(UUID(int=101)),
                    "name": "tenant",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-hardcoded-claim-mapper",
                    "config": {"claim.name": "tenant"},
                }
            ],
        }
        source["scopes"].append(scope)
        self.assertTrue(self.helper.plan(source)["approval_ready"])
        scope["mappers"][0]["config"] = {"user.attribute": "conformance_tenant"}
        with self.assertRaises(ValueError):
            self.helper.plan(source)

    def test_default_mode_does_not_import_execution_module(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "safe.json"
            path.write_text(json.dumps(complete_snapshot()))
            result = subprocess.run(
                [sys.executable, str(PATH), "--snapshot", str(path)],
                capture_output=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["approval_ready"])
