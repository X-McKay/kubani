#!/usr/bin/env python3
"""Prepare the exact Keycloak 26.8.1 Alice/conformance delegation fixture.

Default is read-only planning. Apply creates missing objects only; existing
configuration must match, and conflicting objects are never overwritten.
Credentials come from local SOPS files and never enter output. No pod exec.

Sources: Keycloak tag 26.8.1 OIDCLoginProtocolFactory.addClientDelegationClientScope,
ClientDelegationTest.delegationRestrictedToSpecificUser, PermissionTestUtils.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keycloak_admin import Admin  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "human_fixture", Path(__file__).with_name("conformance-human-token.py")
)
human = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(human)
ACTOR = "agent-tenant-test-conformance"
POLICY = "conformance-alice-actor"
PERMISSION = "conformance-alice-delegate"
FIXTURES = {
    ACTOR: (POLICY, PERMISSION),
    "agent-tenant-test-conformance-lifecycle": (
        "conformance-lifecycle-alice-actor",
        "conformance-lifecycle-alice-delegate",
    ),
}


def fixture_names(actor):
    if actor not in FIXTURES:
        raise ValueError(
            "only the exact conformance and lifecycle actors can be granted"
        )
    return FIXTURES[actor]


def delegation_scope():
    def mapper(name, provider, claim=None, *, identity=True):
        config = {"access.token.claim": "true", "introspection.token.claim": "true"}
        if identity:
            config["id.token.claim"] = "true"
            # Keycloak 26.8.1 AbstractOIDCProtocolMapper.getEffectiveModel
            # materializes UserInfo's default from id.token.claim on reads.
            # State that existing effective value explicitly; compare all keys.
            config["userinfo.token.claim"] = "true"
        if claim:
            config.update({"claim.name": claim, "jsonType.label": "String"})
        return {
            "name": name,
            "protocol": "openid-connect",
            "protocolMapper": provider,
            "config": config,
        }

    return {
        "name": "delegation:client",
        "description": "OpenID Connect scope for agent/client token exchange delegation",
        "protocol": "openid-connect",
        "attributes": {
            "is.parameterized.scope": "true",
            "parameterized.scope.type": "client-delegation",
            "always.display.consent": "true",
            "display.on.consent.screen": "true",
            "include.in.token.scope": "true",
            "consent.screen.text": "${clientDelegationScopeConsentText}",
        },
        "protocolMappers": [
            mapper(
                "client may_act sub",
                "oidc-parameterized-scope-client-sub-mapper",
                "may_act.sub",
            ),
            mapper(
                "client may_act client_id",
                "oidc-parameterized-scope-mapper",
                "may_act.client_id",
            ),
            mapper(
                "client delegation audience",
                "oidc-parameterized-scope-audience-mapper",
                identity=False,
            ),
        ],
    }


def delegation_permission(actor_id, alice_id, *, actor_name=ACTOR):
    policy_name, permission_name = fixture_names(actor_name)
    if not actor_id or not alice_id:
        raise ValueError("exact actor and user IDs are required")
    return (
        {"name": policy_name, "clients": [actor_id], "logic": "POSITIVE"},
        {
            "name": permission_name,
            "resourceType": "Users",
            "resources": [alice_id],
            "scopes": ["delegate"],
            "policies": [policy_name],
            "logic": "POSITIVE",
            "decisionStrategy": "UNANIMOUS",
        },
    )


def assert_exact(actual, expected):
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ValueError("existing fixture configuration differs: " + key)


def consent_scopes(actor, *, refresh_mode="offline"):
    if actor not in {*FIXTURES, "agent-tenant-test-conformance-b"}:
        raise ValueError("only the exact conformance fixture actors are allowed")
    if refresh_mode not in {"offline", "online"}:
        raise ValueError("only explicit offline or online refresh modes are allowed")
    prefix = "openid profile "
    if refresh_mode == "offline":
        prefix += "offline_access "
    return prefix + "agent-policy-service delegation:client:" + actor


def scope_view(scope):
    view = {k: scope.get(k) for k in ("name", "description", "protocol", "attributes")}
    view["protocolMappers"] = sorted(
        (
            {k: m.get(k) for k in ("name", "protocol", "protocolMapper", "config")}
            for m in scope.get("protocolMappers", [])
        ),
        key=lambda m: m["name"],
    )
    return view


def permission_view(api, base, permission, *, policy_count=1):
    # Keycloak 26.8.1 PolicyResourceService's default GET omits references.
    # These endpoints return the actual associated sets, not name-search hits.
    view = dict(permission)
    path = base + "policy/" + permission["id"] + "/"
    for field, endpoint, id_key in (
        ("resources", "resources", "_id"),
        ("scopes", "scopes", "id"),
        ("policies", "associatedPolicies", "id"),
    ):
        rows = api.call(path + endpoint)
        if (
            not isinstance(rows, list)
            or len(rows) != (policy_count if field == "policies" else 1)
            or any(
                not isinstance(row, dict)
                or not isinstance(row.get(id_key), str)
                or not row[id_key]
                or not isinstance(row.get("name"), str)
                or not row["name"]
                or (field == "policies" and row.get("type") != "client")
                for row in rows
            )
            or len({row[id_key] for row in rows}) != len(rows)
            or len({row["name"] for row in rows}) != len(rows)
        ):
            raise ValueError("fixture permission references differ: " + field)
        ids = [row[id_key] for row in rows]
        if field in permission and sorted(permission[field]) != sorted(ids):
            raise ValueError("fixture permission reference IDs differ: " + field)
        view[field] = sorted(row["name"] for row in rows)
    return view


def consolidation_state(api, alice_id):
    """Read only the exact two approved actors and Alice/delegate permissions."""
    if not isinstance(alice_id, str) or not alice_id:
        raise ValueError("exact Alice identity required")
    base = (
        "clients/"
        + api.unique_client("admin-permissions")["id"]
        + "/authz/resource-server/"
    )
    if api.call(base).get("decisionStrategy") != "UNANIMOUS":
        raise ValueError("unexpected global authorization strategy; never modify it")

    def named(kind, name, *, optional=False):
        rows = api.call(base + kind + "?name=" + urllib.parse.quote(name, safe=""))
        rows = [row for row in rows if row.get("name") == name]
        if not rows and optional:
            return None
        if len(rows) != 1 or not rows[0].get("id"):
            raise ValueError("missing or duplicate exact permission/policy")
        return api.call(base + kind + "/" + rows[0]["id"])

    expected = {}
    for actor_name in FIXTURES:
        actor = api.unique_client(actor_name)
        policy, permission = delegation_permission(
            actor["id"], alice_id, actor_name=actor_name
        )
        actual = named("policy/client", policy["name"])
        assert_exact(actual, policy)
        expected[permission["name"]] = permission
    primary = named("permission/scope", PERMISSION)
    secondary_name = FIXTURES["agent-tenant-test-conformance-lifecycle"][1]
    secondary = named("permission/scope", secondary_name, optional=True)
    combined = dict(
        expected[PERMISSION],
        decisionStrategy="AFFIRMATIVE",
        policies=sorted(names[0] for names in FIXTURES.values()),
    )
    # A missing secondary is valid only after exact primary consolidation.
    primary_view = permission_view(
        api,
        base,
        primary,
        policy_count=2 if primary.get("decisionStrategy") == "AFFIRMATIVE" else 1,
    )
    if primary.get("decisionStrategy") == "AFFIRMATIVE":
        assert_exact(primary_view, combined)
        state = "expanded" if secondary else "consolidated"
    else:
        assert_exact(primary_view, expected[PERMISSION])
        if secondary is None:
            raise ValueError("partial legacy permission state")
        state = "legacy"
    if secondary is not None:
        assert_exact(permission_view(api, base, secondary), expected[secondary_name])
    return {
        "state": state,
        "base": base,
        "primary": primary,
        "secondary": secondary,
        "combined": combined,
    }


def consolidate_permissions(api, alice_id, *, apply=False):
    """Explicit separately approved migration; ordinary configure never invokes writes."""
    state = consolidation_state(api, alice_id)
    operations = []
    if state["state"] == "legacy":
        operations.append(
            {
                "method": "PUT",
                "path": state["base"] + "permission/scope/" + state["primary"]["id"],
                "payload": state["combined"],
            }
        )
    if state["secondary"] is not None:
        operations.append(
            {
                "method": "DELETE",
                "path": state["base"] + "permission/scope/" + state["secondary"]["id"],
            }
        )
    if not apply:
        return {"state": state["state"], "operations": operations}
    if state["state"] == "legacy":
        operation = operations[0]
        # Fresh strict reads before each mutation. Keycloak has no revision/CAS
        # for these endpoints: root must exclude other authorization writers.
        fresh = consolidation_state(api, alice_id)
        if fresh != state:
            raise ValueError("permission state changed before consolidation")
        api.call(operation["path"], method="PUT", payload=operation["payload"])
        state = consolidation_state(api, alice_id)
        if state["state"] != "expanded":
            raise ValueError("combined permission was not verified; retain secondary")
    if state["state"] == "expanded":
        fresh = consolidation_state(api, alice_id)
        if fresh != state:
            raise ValueError(
                "permission state changed before exact superseded deletion"
            )
        api.call(
            state["base"] + "permission/scope/" + state["secondary"]["id"],
            method="DELETE",
        )
    final = consolidation_state(api, alice_id)
    if final["state"] != "consolidated":
        raise ValueError("permission consolidation did not converge")
    return {"state": "consolidated", "operations": [], "verified": True}


def configure(apply_scope=False, apply_permission=False, *, actor_name=ACTOR):
    policy_name, _ = fixture_names(actor_name)
    api = Admin()
    credentials = human.decrypt(human.CREDENTIALS)
    users = api.call("users?username=conformance-alice&exact=true")
    if len(users) != 1 or users[0]["id"] != credentials["subject"]:
        raise ValueError("Alice does not match the SOPS fixture identity")
    human.assert_unprivileged(api.call, credentials["subject"])
    actor = api.unique_client(actor_name)
    cli = api.unique_client("agent-cli")
    permission_state = consolidation_state(api, credentials["subject"])
    if permission_state["state"] == "expanded":
        raise ValueError(
            "partial consolidation; resume explicit migration, never recreate grants"
        )
    if (
        not cli.get("consentRequired")
        or actor.get("attributes", {}).get("standard.token.exchange.enabled") != "true"
    ):
        raise ValueError("consent or standard token exchange is not enabled")
    scope = delegation_scope()
    matches = [s for s in api.call("client-scopes") if s["name"] == scope["name"]]
    if len(matches) > 1:
        raise ValueError("duplicate delegation scopes")
    operations = []
    if not matches:
        operations.append({"method": "POST", "path": "client-scopes", "payload": scope})
        if apply_scope:
            api.call("client-scopes", method="POST", payload=scope)
            matches = [
                s for s in api.call("client-scopes") if s["name"] == scope["name"]
            ]
    if matches:
        assert_exact(scope_view(matches[0]), scope_view(scope))
        attached = api.call("clients/" + cli["id"] + "/optional-client-scopes")
        if not any(s["id"] == matches[0]["id"] for s in attached):
            path = (
                "clients/" + cli["id"] + "/optional-client-scopes/" + matches[0]["id"]
            )
            operations.append({"method": "PUT", "path": path})
            if apply_scope:
                api.call(path, method="PUT")
    else:
        operations.append(
            {
                "method": "PUT",
                "path": "clients/"
                + cli["id"]
                + "/optional-client-scopes/<created-scope-id>",
            }
        )

    result = {
        "scope_applied": apply_scope,
        "permission_applied": apply_permission,
        "actor": actor_name,
        "alice_subject": credentials["subject"],
        "permission_layout": permission_state["state"],
        "operations": operations,
    }
    if apply_scope or apply_permission:
        # Repeat all reads and strict comparisons after server normalization.
        # A partial failure is visible and safely recoverable by rerunning.
        verified = configure(actor_name=actor_name)
        result["remaining_operations"] = verified["operations"]
        if any(
            (apply_scope and "/authz/" not in op["path"])
            or (apply_permission and "/authz/" in op["path"])
            for op in verified["operations"]
        ):
            raise ValueError("requested fixture changes were not verified")
    return result


def mint(output, *, actor_name=ACTOR, refresh_mode="offline"):
    fixture_names(actor_name)
    scopes = consent_scopes(actor_name, refresh_mode=refresh_mode)
    api = Admin()
    actor = api.unique_client(actor_name)
    service_account = api.call("clients/" + actor["id"] + "/service-account-user")
    tokens, claims = human.mint_tokens(scopes)
    audience = claims.get("aud", [])
    if isinstance(audience, str):
        audience = [audience]
    if not {actor_name, "agent-policy-service"}.issubset(audience):
        raise ValueError("delegation subject token lacks required audiences")
    if claims.get("may_act") != {"sub": service_account["id"], "client_id": actor_name}:
        raise ValueError("delegation subject token has unexpected may_act")
    if "delegation:client:" + actor_name not in claims.get("scope", "").split():
        raise ValueError("delegation consent scope missing")
    if ("offline_access" in claims.get("scope", "").split()) != (
        refresh_mode == "offline"
    ):
        raise ValueError(
            "issued offline access scope differs from requested refresh mode"
        )
    if not isinstance(tokens.get("refresh_token"), str) or not tokens["refresh_token"]:
        raise ValueError("refresh token missing")
    human.encrypt(
        output,
        {
            "fixture": "agent-platform synthetic Alice delegation",
            "stringData": {
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
            },
        },
    )
    return {
        "status": "minted via PKCE with delegation consent",
        "refresh_mode": refresh_mode,
        "refresh_lifetime_seconds": (
            tokens.get("refresh_expires_in")
            if type(tokens.get("refresh_expires_in")) is int
            and tokens["refresh_expires_in"] >= 0
            else None
        ),
        "session_limit": (
            "online SSO/client session limits apply; not an offline grant"
            if refresh_mode == "online"
            else "offline session limits apply"
        ),
        "claims": {
            k: claims.get(k)
            for k in ("iss", "sub", "azp", "aud", "scope", "may_act", "iat", "exp")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actor", choices=sorted(FIXTURES), default=ACTOR)
    parser.add_argument("--apply-scope", action="store_true")
    parser.add_argument("--apply-permission", action="store_true")
    parser.add_argument(
        "--mint",
        type=Path,
        help="Mint Alice's consented tokens to a SOPS .enc.yaml file",
    )
    parser.add_argument(
        "--refresh-mode",
        choices=("offline", "online"),
        default="offline",
        help="Explicit online refresh for bounded tests; default offline keeps offline_access",
    )
    parser.add_argument(
        "--consolidate-alice-permissions",
        action="store_true",
        help="Plan separately approved Alice-only shared delegate permission",
    )
    parser.add_argument(
        "--apply-consolidation",
        action="store_true",
        help="Apply reviewed exact consolidation plan; requires new user approval",
    )
    args = parser.parse_args()
    if args.apply_consolidation and not args.consolidate_alice_permissions:
        parser.error("--apply-consolidation requires explicit consolidation selection")
    if args.consolidate_alice_permissions:
        if (
            args.mint
            or args.apply_scope
            or args.apply_permission
            or args.actor != ACTOR
            or args.refresh_mode != "offline"
        ):
            parser.error(
                "consolidation is separate from configuration, actor selection and minting"
            )
        api = Admin()
        credentials = human.decrypt(human.CREDENTIALS)
        users = api.call("users?username=conformance-alice&exact=true")
        if len(users) != 1 or users[0]["id"] != credentials["subject"]:
            raise ValueError("Alice does not match the SOPS fixture identity")
        human.assert_unprivileged(api.call, credentials["subject"])
        result = consolidate_permissions(
            api, credentials["subject"], apply=args.apply_consolidation
        )
        print(json.dumps(result, indent=2))
        return 0
    if args.refresh_mode != "offline" and not args.mint:
        parser.error("refresh mode applies only to minting")
    if args.mint and (args.apply_scope or args.apply_permission):
        parser.error("configuration and consent are separate operations")
    result = (
        mint(args.mint, actor_name=args.actor, refresh_mode=args.refresh_mode)
        if args.mint
        else configure(args.apply_scope, args.apply_permission, actor_name=args.actor)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            f"Delegation fixture failed ({type(exc).__name__}); sensitive details omitted",
            file=sys.stderr,
        )
        sys.exit(1)
