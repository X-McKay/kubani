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

    def test_lifecycle_permission_is_separate_and_single_actor(self):
        actor = "agent-tenant-test-conformance-lifecycle"
        policy, permission = fixture.delegation_permission(
            "lifecycle-id", "alice-id", actor_name=actor
        )
        self.assertEqual(policy["name"], "conformance-lifecycle-alice-actor")
        self.assertEqual(policy["clients"], ["lifecycle-id"])
        self.assertEqual(permission["name"], "conformance-lifecycle-alice-delegate")
        self.assertEqual(permission["resources"], ["alice-id"])
        self.assertEqual(permission["policies"], [policy["name"]])
        self.assertEqual(permission["scopes"], ["delegate"])
        self.assertTrue(fixture.consent_scopes(actor).endswith("delegation:client:" + actor))
        for unknown in ("agent-tenant-test-conformance-b", "agent-tenant-prod-investigator"):
            with self.assertRaises(ValueError):
                fixture.delegation_permission("actor-id", "alice-id", actor_name=unknown)

    def test_unknown_actor_rejected_before_admin_credentials(self):
        with patch.object(fixture, "Admin") as admin:
            with self.assertRaises(ValueError):
                fixture.configure(actor_name="agent-tenant-prod-investigator")
            with self.assertRaises(ValueError):
                fixture.mint(Path("unused.enc.yaml"), actor_name="agent-tenant-prod-investigator")
            admin.assert_not_called()

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

    def test_scope_matches_keycloak_26_8_1_effective_userinfo_defaults(self):
        # Safe mapper shape observed by read-only GET of the approved scope.
        actual = fixture.delegation_scope()
        for mapper in actual["protocolMappers"]:
            mapper["id"] = "server-assigned"
            if mapper["name"] in {"client may_act sub", "client may_act client_id"}:
                mapper["config"]["userinfo.token.claim"] = "true"
        fixture.assert_exact(
            fixture.scope_view(actual), fixture.scope_view(fixture.delegation_scope())
        )

    def test_scope_rejects_changed_or_extra_mapper_configuration(self):
        import copy

        expected = fixture.scope_view(fixture.delegation_scope())
        for field, value in (
            ("userinfo.token.claim", "false"),
            ("claim.name", "may_act.other"),
            ("access.token.claim", "false"),
            ("unexpected.config", "true"),
        ):
            with self.subTest(field=field):
                actual = copy.deepcopy(fixture.delegation_scope())
                actual["protocolMappers"][0]["config"][field] = value
                with self.assertRaises(ValueError):
                    fixture.assert_exact(fixture.scope_view(actual), expected)
        actual = copy.deepcopy(fixture.delegation_scope())
        actual["protocolMappers"].append(copy.deepcopy(actual["protocolMappers"][0]))
        with self.assertRaises(ValueError):
            fixture.assert_exact(fixture.scope_view(actual), expected)

    def test_permission_hydrates_pinned_reference_endpoints_strictly(self):
        import copy

        _, expected = fixture.delegation_permission("actor-id", "alice-id")
        actual = {k: v for k, v in expected.items() if k not in {"resources", "scopes", "policies"}}
        actual["id"] = "permission-id"
        refs = {
            "resources": [{"_id": "resource-id", "name": "alice-id"}],
            "scopes": [{"id": "scope-id", "name": "delegate"}],
            "associatedPolicies": [{"id": "policy-id", "name": fixture.POLICY, "type": "client"}],
        }

        class API:
            def call(self, path):
                return copy.deepcopy(refs[path.rsplit("/", 1)[1]])

        fixture.assert_exact(fixture.permission_view(API(), "base/", actual), expected)
        for field in ("resources", "scopes", "policies"):
            with self.subTest(inline=field), self.assertRaises(ValueError):
                fixture.permission_view(API(), "base/", dict(actual, **{field: ["unexpected-id"]}))
        for endpoint, replacement in (
            ("resources", []),
            ("resources", [{"_id": "other-id", "name": "bob-id"}]),
            ("resources", refs["resources"] * 2),
            ("scopes", refs["scopes"] + [{"id": "manage-id", "name": "manage"}]),
            ("associatedPolicies", refs["associatedPolicies"] + [{"id": "other-id", "name": "other", "type": "client"}]),
            ("associatedPolicies", [{"id": "policy-id", "name": fixture.POLICY, "type": "role"}]),
        ):
            saved = refs[endpoint]
            refs[endpoint] = replacement
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                fixture.assert_exact(fixture.permission_view(API(), "base/", actual), expected)
            refs[endpoint] = saved

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
