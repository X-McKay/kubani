"""Exact backend bootstrap identity delta; synthetic admin transport only."""

import copy
import importlib.util
from pathlib import Path
import unittest

PATH = (
    Path(__file__).resolve().parents[1]
    / "infrastructure/scripts/ops/db-admin-backend.py"
)
SPEC = importlib.util.spec_from_file_location("db_admin_backend", PATH)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class Admin:
    def __init__(self):
        self.resource = None
        self.role = None
        self.scope = None
        self.optional = []
        self.defaults = [{"id": "basic", "name": "basic"}]
        self.resource_mappers = []
        self.calls = []
        self.requester = {
            "id": "aps-id",
            "clientId": "agent-policy-service",
            "enabled": True,
            "protocol": "openid-connect",
            "publicClient": False,
            "bearerOnly": False,
            "serviceAccountsEnabled": True,
            "attributes": {"standard.token.exchange.enabled": "true"},
        }

    def call(self, path, *, method="GET", payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        if method == "POST":
            if path == "roles":
                self.role = {**copy.deepcopy(payload), "id": "role-id"}
            elif path == "clients":
                self.resource = {**copy.deepcopy(payload), "id": "resource-id"}
            elif path == "client-scopes":
                self.scope = {**copy.deepcopy(payload), "id": "scope-id"}
            else:
                raise AssertionError(path)
            return None
        if method == "PUT":
            assert path == "clients/aps-id/optional-client-scopes/scope-id"
            self.optional.append({"id": "scope-id", "name": helper.SCOPE})
            return None
        if path.startswith("roles?search="):
            return [self.role] if self.role else []
        if path == "roles/" + helper.ROLE:
            return copy.deepcopy(self.role)
        if path == "roles-by-id/role-id/composites":
            return self.role.get("composites", [])
        if path.startswith("clients?clientId="):
            return (
                [self.requester]
                if "agent-policy-service" in path
                else ([self.resource] if self.resource else [])
            )
        if path == "clients/aps-id":
            return copy.deepcopy(self.requester)
        if path == "clients/resource-id":
            return copy.deepcopy(self.resource)
        if path == "clients/resource-id/protocol-mappers/models":
            return self.resource_mappers
        if path == "client-scopes":
            return [self.scope] if self.scope else []
        if path == "client-scopes/scope-id":
            return copy.deepcopy(self.scope)
        if path == "client-scopes/scope-id/protocol-mappers/models":
            return copy.deepcopy(self.scope["protocolMappers"])
        if path == "clients/aps-id/optional-client-scopes":
            return copy.deepcopy(self.optional)
        if path == "clients/aps-id/default-client-scopes":
            return copy.deepcopy(self.defaults)
        raise AssertionError(path)

    @property
    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]


class IdentityTests(unittest.TestCase):
    def test_default_is_readonly_plan_and_missing_objects_are_explicit(self):
        api = Admin()
        result = helper.configure(api)
        self.assertEqual(api.writes, [])
        self.assertEqual(
            result["planned"],
            ["create_role", "create_resource", "create_scope", "attach_aps_optional"],
        )

    def test_apply_creates_only_three_exact_operations_then_is_idempotent(self):
        api = Admin()
        result = helper.configure(api, apply=True)
        self.assertEqual(
            result["changed"],
            ["create_role", "create_resource", "create_scope", "attach_aps_optional"],
        )
        self.assertEqual(
            [(m, p) for m, p, _ in api.writes],
            [
                ("POST", "roles"),
                ("POST", "clients"),
                ("POST", "client-scopes"),
                ("PUT", "clients/aps-id/optional-client-scopes/scope-id"),
            ],
        )
        api.calls.clear()
        self.assertEqual(helper.configure(api, apply=True)["changed"], [])
        self.assertEqual(api.writes, [])

    def existing(self):
        api = Admin()
        helper.configure(api, apply=True)
        api.calls.clear()
        return api

    def test_existing_conflicts_refused_without_mutation(self):
        for fault in (
            "client",
            "mapper",
            "extra_mapper",
            "scope_attribute",
            "default_scope",
            "requester",
            "resource_mapper",
        ):
            api = self.existing()
            if fault == "client":
                api.resource["serviceAccountsEnabled"] = True
            elif fault == "mapper":
                api.scope["protocolMappers"][0]["config"][
                    "included.client.audience"
                ] = helper.RESOURCE
            elif fault == "extra_mapper":
                api.scope["protocolMappers"].append(
                    copy.deepcopy(api.scope["protocolMappers"][0])
                )
            elif fault == "scope_attribute":
                api.scope["attributes"]["is.parameterized.scope"] = "true"
            elif fault == "default_scope":
                api.defaults.append({"id": "scope-id", "name": helper.SCOPE})
            elif fault == "requester":
                api.requester["attributes"]["standard.token.exchange.enabled"] = "false"
            else:
                api.resource_mappers.append({"name": "unexpected"})
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                helper.configure(api, apply=True)
            self.assertEqual(api.writes, [])

    def test_known_mapper_defaults_and_seed_shape_are_semantically_idempotent(self):
        api = self.existing()
        mapper = api.scope["protocolMappers"][0]
        mapper["id"] = "generated"
        mapper["consentRequired"] = False
        mapper["config"]["userinfo.token.claim"] = "false"
        mapper["config"]["included.client.audience"] = ""
        api.scope["attributes"]["display.on.consent.screen"] = "false"
        self.assertEqual(helper.configure(api, apply=True)["changed"], [])
        self.assertEqual(api.writes, [])
        mapper["config"]["userinfo.token.claim"] = "true"
        with self.assertRaises(ValueError):
            helper.configure(api, apply=True)

    def test_conflict_is_detected_before_creating_other_missing_objects(self):
        api = Admin()
        api.scope = {**copy.deepcopy(helper.scope_body()), "id": "scope-id"}
        api.scope["protocolMappers"][0]["config"]["included.custom.audience"] = "wrong"
        with self.assertRaises(ValueError):
            helper.configure(api, apply=True)
        self.assertEqual(api.writes, [])

    def test_wrong_attachment_id_refused(self):
        api = self.existing()
        api.optional[0]["id"] = "wrong"
        with self.assertRaises(ValueError):
            helper.configure(api, apply=True)
        self.assertEqual(api.writes, [])

    def test_readback_conflict_is_refused_and_never_overwritten(self):
        api = Admin()
        call = api.call

        def changed(path, **kwargs):
            result = call(path, **kwargs)
            if path == "clients" and kwargs.get("method") == "POST":
                api.resource["publicClient"] = True
            return result

        api.call = changed
        with self.assertRaises(ValueError):
            helper.configure(api, apply=True)
        self.assertEqual(len(api.writes), 2)

    def test_inert_backend_descriptor_matches_helper_semantics(self):
        import json

        descriptor = json.loads(
            (PATH.parents[2] / "gitops/apps/keycloak/db-admin-backend.json").read_text()
        )
        self.assertEqual(
            set(descriptor), {"role", "resource", "scope", "requester", "attachment"}
        )
        self.assertEqual(descriptor["requester"], helper.REQUESTER)
        self.assertEqual(descriptor["attachment"], "optional")
        self.assertEqual(descriptor["role"], helper.role_body())
        self.assertEqual(descriptor["resource"], helper.resource_body())
        api = Admin()
        api.role = {**descriptor["role"], "id": "role-id"}
        api.resource = {**descriptor["resource"], "id": "resource-id"}
        api.scope = {**descriptor["scope"], "id": "scope-id"}
        result = helper.configure(api)
        self.assertEqual(result["planned"], ["attach_aps_optional"])
        self.assertEqual(api.writes, [])
        kustomization = (
            PATH.parents[2] / "gitops/apps/keycloak/kustomization.yaml"
        ).read_text()
        self.assertNotIn("db-admin-backend.json", kustomization)

    def test_unrelated_attachments_preserved_and_unexpected_readback_refused(self):
        api = Admin()
        api.optional = [{"id": "keep", "name": "keep"}]
        helper.configure(api, apply=True)
        self.assertIn({"id": "keep", "name": "keep"}, api.optional)
        api = Admin()
        api.optional = [{"id": "keep", "name": "keep"}]
        call = api.call

        def lost(path, **kwargs):
            result = call(path, **kwargs)
            if kwargs.get("method") == "PUT":
                api.optional = [v for v in api.optional if v["id"] != "keep"]
            return result

        api.call = lost
        with self.assertRaises(ValueError):
            helper.configure(api, apply=True)

    def test_missing_requester_refused_before_mutations(self):
        api = Admin()
        call = api.call

        def missing(path, **kwargs):
            if path == "clients?clientId=agent-policy-service":
                return []
            return call(path, **kwargs)

        api.call = missing
        with self.assertRaises(ValueError):
            helper.configure(api, apply=True)
        self.assertEqual(api.writes, [])

    def test_existing_role_must_be_exact_noncomposite_realm_role(self):
        for field, value in [
            ("clientRole", True),
            ("composite", True),
            ("attributes", {"unexpected": ["value"]}),
            ("composites", [{"name": "realm-admin", "id": "admin"}]),
        ]:
            api = self.existing()
            api.role[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                helper.configure(api, apply=True)
            self.assertEqual(api.writes, [])

    def test_role_readback_conflict_stops_before_other_creations(self):
        api = Admin()
        call = api.call

        def changed(path, **kwargs):
            result = call(path, **kwargs)
            if path == "roles" and kwargs.get("method") == "POST":
                api.role["composite"] = True
            return result

        api.call = changed
        with self.assertRaises(ValueError):
            helper.configure(api, apply=True)
        self.assertEqual(
            [(method, path) for method, path, _ in api.writes], [("POST", "roles")]
        )
