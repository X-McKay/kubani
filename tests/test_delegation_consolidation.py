"""Alice-only permission consolidation; no global strategy or actor-policy changes."""

import copy
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

path = (
    Path(__file__).parents[1] / "infrastructure/scripts/ops/conformance-delegation.py"
)
spec = importlib.util.spec_from_file_location("consolidation", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class API:
    def __init__(self):
        self.writes = []
        self.server = {"decisionStrategy": "UNANIMOUS"}
        self.policies = {}
        self.permissions = {}
        for index, actor in enumerate(m.FIXTURES):
            policy, permission = m.delegation_permission(
                "client-" + str(index), "alice", actor_name=actor
            )
            policy["id"] = "policy-" + str(index)
            permission["id"] = "permission-" + str(index)
            self.policies[policy["name"]] = policy
            self.permissions[permission["name"]] = permission

    def unique_client(self, name):
        if name == "admin-permissions":
            return {"id": "admin"}
        return {"id": "client-" + str(list(m.FIXTURES).index(name))}

    def call(self, path, *, method="GET", payload=None):
        if method != "GET":
            self.writes.append((method, path, copy.deepcopy(payload)))
            name = next(
                n
                for n, p in self.permissions.items()
                if p["id"] == path.rsplit("/", 1)[-1]
            )
            if method == "PUT":
                self.permissions[name] = {
                    "id": self.permissions[name]["id"],
                    **copy.deepcopy(payload),
                }
            elif method == "DELETE":
                del self.permissions[name]
            else:
                raise AssertionError(method)
            return None
        if path.endswith("resource-server/"):
            return copy.deepcopy(self.server)
        if "?" in path:
            kind, query = path.split("?", 1)
            name = query.split("name=", 1)[-1]
            rows = self.policies if kind.endswith("policy/client") else self.permissions
            return [copy.deepcopy(p) for p in rows.values() if p["name"] == name]
        last = path.rsplit("/", 1)[-1]
        if last in {"resources", "scopes", "associatedPolicies"}:
            pid = path.split("/")[-2]
            p = next(p for p in self.permissions.values() if p["id"] == pid)
            if last == "resources":
                return [{"_id": "resource-alice", "name": u} for u in p["resources"]]
            if last == "scopes":
                return [{"id": "scope-" + s, "name": s} for s in p["scopes"]]
            return [
                {"id": self.policies[n]["id"], "name": n, "type": "client"}
                for n in p["policies"]
            ]
        for rows in (self.policies, self.permissions):
            for p in rows.values():
                if p["id"] == last:
                    result = copy.deepcopy(p)
                    if rows is self.permissions:
                        for key in ("resources", "scopes", "policies"):
                            result.pop(key)
                    return result
        raise AssertionError(path)


def test_exact_plan_retains_actor_policies_and_global_strategy():
    api = API()
    result = m.consolidate_permissions(api, "alice")
    assert result["state"] == "legacy"
    assert [o["method"] for o in result["operations"]] == ["PUT", "DELETE"]
    body = result["operations"][0]["payload"]
    assert body["resources"] == ["alice"] and body["scopes"] == ["delegate"]
    assert body["policies"] == [
        "conformance-alice-actor",
        "conformance-lifecycle-alice-actor",
    ]
    assert body["decisionStrategy"] == "AFFIRMATIVE"
    assert not api.writes


def test_apply_is_idempotent_and_verifies_before_removing_superseded_permission():
    api = API()
    policies = copy.deepcopy(api.policies)
    report = m.consolidate_permissions(api, "alice", apply=True)
    assert report["state"] == "consolidated" and report["operations"] == []
    assert api.policies == policies and api.server == {"decisionStrategy": "UNANIMOUS"}
    assert len(api.writes) == 2
    assert m.consolidate_permissions(api, "alice", apply=True)["operations"] == []
    assert len(api.writes) == 2


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_user",
        "extra_actor",
        "extra_scope",
        "negative_logic",
        "unknown_strategy",
        "missing_primary",
        "missing_secondary",
        "wrong_policy",
    ],
)
def test_unknown_or_broader_state_is_refused_before_any_write(fault):
    api = API()
    p = api.permissions[m.PERMISSION]
    if fault == "wrong_user":
        p["resources"].append("bob")
    elif fault == "extra_actor":
        p["policies"].append("unapproved")
    elif fault == "extra_scope":
        p["scopes"].append("manage")
    elif fault == "negative_logic":
        p["logic"] = "NEGATIVE"
    elif fault == "unknown_strategy":
        api.server["decisionStrategy"] = "AFFIRMATIVE"
    elif fault == "missing_primary":
        del api.permissions[m.PERMISSION]
    elif fault == "missing_secondary":
        del api.permissions["conformance-lifecycle-alice-delegate"]
    elif fault == "wrong_policy":
        api.policies[m.POLICY]["clients"] = ["unapproved"]
    with pytest.raises((ValueError, KeyError)):
        m.consolidate_permissions(api, "alice", apply=True)
    assert not api.writes


def test_interrupted_after_verified_put_resumes_only_exact_delete():
    api = API()
    plan = m.consolidate_permissions(api, "alice")["operations"]
    api.call(plan[0]["path"], method="PUT", payload=plan[0]["payload"])
    assert m.consolidate_permissions(api, "alice")["state"] == "expanded"
    m.consolidate_permissions(api, "alice", apply=True)
    assert [w[0] for w in api.writes] == ["PUT", "DELETE"]


def test_existing_configure_recognizes_consolidated_state_without_recreating_secondary():
    api = API()
    m.consolidate_permissions(api, "alice", apply=True)
    api.writes.clear()
    old_call = api.call
    scope = dict(m.delegation_scope(), id="scope")

    def call(path, **kwargs):
        if path.startswith("users?"):
            return [{"id": "alice"}]
        if path == "client-scopes" or path.endswith("/optional-client-scopes"):
            return [scope]
        return old_call(path, **kwargs)

    api.call = call
    old_unique = api.unique_client
    api.unique_client = (
        lambda name: {"id": "cli", "consentRequired": True}
        if name == "agent-cli"
        else dict(
            old_unique(name), attributes={"standard.token.exchange.enabled": "true"}
        )
    )
    with (
        patch.object(m, "Admin", return_value=api),
        patch.object(m.human, "decrypt", return_value={"subject": "alice"}),
        patch.object(m.human, "assert_unprivileged"),
    ):
        report = m.configure(
            apply_permission=True, actor_name="agent-tenant-test-conformance-lifecycle"
        )
    assert report["permission_layout"] == "consolidated"
    assert report["operations"] == [] and not api.writes


def test_put_must_be_verified_before_superseded_permission_is_deleted():
    api = API()
    original = api.call

    def call(path, *, method="GET", payload=None):
        result = original(path, method=method, payload=payload)
        if method == "PUT":
            api.permissions[m.PERMISSION]["resources"] = ["other-user"]
        return result

    api.call = call
    with pytest.raises(ValueError):
        m.consolidate_permissions(api, "alice", apply=True)
    assert [w[0] for w in api.writes] == ["PUT"]
    assert "conformance-lifecycle-alice-delegate" in api.permissions
