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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

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
        raise ValueError("only the exact conformance and lifecycle actors can be granted")
    return FIXTURES[actor]


def delegation_scope():
    def mapper(name, provider, claim=None, *, identity=True):
        config = {"access.token.claim": "true", "introspection.token.claim": "true"}
        if identity:
            config["id.token.claim"] = "true"
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


def consent_scopes(actor):
    if actor not in {*FIXTURES, "agent-tenant-test-conformance-b"}:
        raise ValueError("only the exact conformance fixture actors are allowed")
    return (
        "openid profile offline_access agent-policy-service delegation:client:" + actor
    )


class Admin:
    def __init__(self):
        self.client, self.bearer = human.admin_client()

    def call(self, path, *, method="GET", payload=None):
        if path.startswith("/") or ".." in path or "#" in path:
            raise ValueError("invalid admin path")
        url = human.ORIGIN + "/admin/realms/agents/" + path
        headers = {"Authorization": "Bearer " + self.bearer}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            response = self.client.open(req, timeout=30)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Keycloak admin HTTP {exc.code}; response omitted"
            ) from None
        with response:
            raw = response.read(2 * 1024 * 1024)
            return json.loads(raw) if raw else None

    def unique_client(self, name):
        rows = self.call("clients?clientId=" + urllib.parse.quote(name, safe=""))
        if len(rows) != 1 or rows[0]["clientId"] != name:
            raise ValueError("client not unique: " + name)
        return rows[0]


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

    admin_id = api.unique_client("admin-permissions")["id"]
    base = "clients/" + admin_id + "/authz/resource-server/"
    policy, permission = delegation_permission(
        actor["id"], credentials["subject"], actor_name=actor_name
    )
    for kind, payload in (("policy/client", policy), ("permission/scope", permission)):
        rows = api.call(
            base + kind + "?name=" + urllib.parse.quote(payload["name"], safe="")
        )
        rows = [row for row in rows if row["name"] == payload["name"]]
        if len(rows) > 1:
            raise ValueError("duplicate fixture permission/policy")
        if rows:
            actual = api.call(base + kind + "/" + rows[0]["id"])
            # Typed endpoints return client/resource/scope/policy references as IDs.
            # Resolve only the exact references, never accept an unbounded resource list.
            if kind == "permission/scope":
                policy_ids = {
                    r["id"]
                    for r in api.call(base + "policy?name=" + policy_name)
                    if r["name"] == policy_name
                }
                scope_ids = {
                    r["id"]
                    for r in api.call(base + "scope?name=delegate")
                    if r["name"] == "delegate"
                }
                actual["policies"] = [
                    policy_name if x in policy_ids else x for x in actual.get("policies", [])
                ]
                actual["scopes"] = [
                    "delegate" if x in scope_ids else x
                    for x in actual.get("scopes", [])
                ]
            assert_exact(actual, payload)
        else:
            operations.append(
                {"method": "POST", "path": base + kind, "payload": payload}
            )
            if apply_permission:
                api.call(base + kind, method="POST", payload=payload)
    result = {
        "scope_applied": apply_scope,
        "permission_applied": apply_permission,
        "actor": actor_name,
        "alice_subject": credentials["subject"],
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


def mint(output, *, actor_name=ACTOR):
    fixture_names(actor_name)
    api = Admin()
    actor = api.unique_client(actor_name)
    service_account = api.call("clients/" + actor["id"] + "/service-account-user")
    tokens, claims = human.mint_tokens(consent_scopes(actor_name))
    audience = claims.get("aud", [])
    if isinstance(audience, str):
        audience = [audience]
    if not {actor_name, "agent-policy-service"}.issubset(audience):
        raise ValueError("delegation subject token lacks required audiences")
    if claims.get("may_act") != {"sub": service_account["id"], "client_id": actor_name}:
        raise ValueError("delegation subject token has unexpected may_act")
    if "delegation:client:" + actor_name not in claims.get("scope", "").split():
        raise ValueError("delegation consent scope missing")
    if not tokens.get("refresh_token"):
        raise ValueError("offline refresh token missing")
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
    args = parser.parse_args()
    if args.mint and (args.apply_scope or args.apply_permission):
        parser.error("configuration and consent are separate operations")
    result = (
        mint(args.mint, actor_name=args.actor)
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
