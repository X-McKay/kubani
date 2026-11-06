"""The delegation fixture must never turn a single-user grant into realm access."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


PATH = (
    Path(__file__).resolve().parents[1]
    / "infrastructure/scripts/ops/conformance-delegation.py"
)
SPEC = importlib.util.spec_from_file_location("delegation_fixture", PATH)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class DelegationTests(unittest.TestCase):
    def test_mint_rejects_wrong_actor_audience_scope_or_missing_refresh_before_writing(
        self,
    ):
        class FakeAdmin:
            def unique_client(self, name):
                return {"id": "actor-id"}

            def call(self, path):
                return {"id": "actor-sub"}

        claims = {
            "aud": [fixture.ACTOR, "agent-policy-service"],
            "may_act": {"sub": "actor-sub", "client_id": fixture.ACTOR},
            "scope": fixture.consent_scopes(fixture.ACTOR),
        }
        for changes, refresh in (
            ({"aud": [fixture.ACTOR]}, True),
            ({"may_act": {"sub": "wrong-sub", "client_id": fixture.ACTOR}}, True),
            ({"scope": "openid"}, True),
            ({}, False),
        ):
            tokens = {"access_token": "synthetic"}
            if refresh:
                tokens["refresh_token"] = "synthetic-refresh"
            with (
                self.subTest(changes=changes, refresh=refresh),
                patch.object(fixture, "Admin", FakeAdmin),
                patch.object(
                    fixture.human,
                    "mint_tokens",
                    return_value=(tokens, dict(claims, **changes)),
                ),
                patch.object(fixture.human, "encrypt") as encrypt,
                self.assertRaises(ValueError),
            ):
                fixture.mint(Path("unused.enc.yaml"))
            encrypt.assert_not_called()

    def test_scope_uses_pinned_parameterized_scope_and_all_three_mappers(self):
        scope = fixture.delegation_scope()
        self.assertEqual(scope["name"], "delegation:client")
        self.assertEqual(scope["attributes"]["is.parameterized.scope"], "true")
        self.assertEqual(
            scope["attributes"]["parameterized.scope.type"], "client-delegation"
        )
        self.assertEqual(scope["attributes"]["always.display.consent"], "true")
        self.assertFalse(any("dynamic" in key for key in scope["attributes"]))
        mappers = scope["protocolMappers"]
        self.assertEqual(len(mappers), 3)
        self.assertEqual(
            {m["protocolMapper"] for m in mappers},
            {
                "oidc-parameterized-scope-client-sub-mapper",
                "oidc-parameterized-scope-mapper",
                "oidc-parameterized-scope-audience-mapper",
            },
        )

    def test_only_exact_alice_and_actor_can_be_granted(self):
        policy, permission = fixture.delegation_permission("actor-id", "alice-id")
        self.assertEqual(policy["clients"], ["actor-id"])
        self.assertEqual(permission["resourceType"], "Users")
        self.assertEqual(permission["resources"], ["alice-id"])
        self.assertEqual(permission["scopes"], ["delegate"])
        self.assertEqual(permission["policies"], [policy["name"]])
        for actor, user in (("", "alice-id"), ("actor-id", "")):
            with self.assertRaises(ValueError):
                fixture.delegation_permission(actor, user)

    def test_existing_broader_permission_is_rejected(self):
        _, desired = fixture.delegation_permission("actor-id", "alice-id")
        actual = dict(desired, id="server-assigned")
        fixture.assert_exact(actual, desired)
        for field, value in (
            ("resources", []),
            ("resources", ["alice-id", "bob-id"]),
            ("scopes", ["delegate", "manage"]),
            ("logic", "NEGATIVE"),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                fixture.assert_exact(dict(actual, **{field: value}), desired)

    def test_only_allowed_consent_scopes_can_be_requested(self):
        self.assertEqual(
            fixture.consent_scopes("agent-tenant-test-conformance"),
            "openid profile offline_access agent-policy-service delegation:client:agent-tenant-test-conformance",
        )
        with self.assertRaises(ValueError):
            fixture.consent_scopes("agent-tenant-prod-investigator")


if __name__ == "__main__":
    unittest.main()
