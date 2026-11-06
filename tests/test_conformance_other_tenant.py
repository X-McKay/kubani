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
