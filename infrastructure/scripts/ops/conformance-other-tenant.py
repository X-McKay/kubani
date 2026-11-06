#!/usr/bin/env python3
"""Fixed-identity T10a planner; default mode is strictly local and read-only."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

USERNAME = "conformance-bob-tenant-other"
TENANT = "tenant-other"
SCOPE = "conformance:t10a:tenant-provenance"
ATTRIBUTE = {
    "name": "conformance_tenant",
    "displayName": "T10a synthetic tenant provenance",
    "multivalued": False,
    "permissions": {"view": ["admin"], "edit": ["admin"]},
    "validations": {"pattern": {"pattern": "^tenant-other$"}},
}
SCOPE_BODY = {
    "name": SCOPE,
    "description": "T10a admin-controlled synthetic tenant provenance only",
    "protocol": "openid-connect",
    "attributes": {
        "display.on.consent.screen": "true",
        "include.in.token.scope": "true",
        "consent.screen.text": "T10a synthetic tenant provenance",
    },
    "protocolMappers": [
        {
            "name": "conformance-t10a-tenant",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {
                "user.attribute": "conformance_tenant",
                "claim.name": "tenant",
                "jsonType.label": "String",
                "multivalued": "false",
                "aggregate.attrs": "false",
                "access.token.claim": "true",
                "id.token.claim": "false",
                "userinfo.token.claim": "false",
                "introspection.token.claim": "false",
            },
        }
    ],
}
# These are request templates, never URLs to be fetched by this program.
READS = [
    {"endpoint": "/admin/serverinfo", "projection": "systemInfo.version == 26.8.1"},
    {
        "endpoint": "/admin/realms/agents/users/profile",
        "projection": "complete profile preserving all fields; canonical SHA256 preimage",
    },
    {
        "endpoint": "/admin/realms/agents/clients?clientId=agent-cli",
        "projection": "exactly one id/clientId; publicClient, standardFlowEnabled, directAccessGrantsEnabled, attributes PKCE settings, redirectUris; no secrets",
    },
    {
        "endpoint": "/admin/realms/agents/client-scopes",
        "projection": "all scope ids/names/protocols; reject proposed name already present",
    },
    {
        "endpoint": "/admin/realms/agents/client-scopes/{each-scope-id}/protocol-mappers/models",
        "projection": "all mapper names/providers/config; detect any existing tenant claim or conformance_tenant mapper",
    },
    {
        "endpoint": "/admin/realms/agents/clients?first={offset}&max=100",
        "projection": "page to empty with finite cap; each id/clientId only",
    },
    {
        "endpoint": "/admin/realms/agents/clients/{each-client-id}/default-client-scopes",
        "projection": "all scope ids/names; preserve attachments exactly",
    },
    {
        "endpoint": "/admin/realms/agents/clients/{each-client-id}/optional-client-scopes",
        "projection": "all scope ids/names; preserve attachments exactly",
    },
    {
        "endpoint": "/admin/realms/agents/clients/{each-client-id}/protocol-mappers/models",
        "projection": "all mapper names/providers/config; detect tenant claim conflicts",
    },
    {
        "endpoint": "/admin/realms/agents/users?username=conformance-bob-tenant-other&exact=true",
        "projection": "count == 0 only; never adopt existing user",
    },
    {
        "endpoint": "/admin/realms/agents/users?first={offset}&max=100&briefRepresentation=false",
        "projection": "bounded page to empty, ids only; full associated reads below; never export personal data",
    },
    {
        "endpoint": "/admin/realms/agents/users/{each-user-id}",
        "projection": "boolean conformance_tenant attribute present; reject any present; discard other user fields",
    },
    {
        "endpoint": "/admin/realms/agents",
        "projection": "defaultRole id/name; registrationEnabled; userManagedAccessAllowed; no full realm export",
    },
    {
        "endpoint": "/admin/realms/agents/default-groups",
        "projection": "count == 0 required; otherwise stop before user creation",
    },
    {
        "endpoint": "/admin/realms/agents/roles-by-id/{default-role-and-recursive-composite-id}",
        "projection": "id/name/composite/clientRole/containerId; bind every recursive role node",
    },
    {
        "endpoint": "/admin/realms/agents/roles-by-id/{default-role-and-recursive-composite-id}/composites",
        "projection": "id/name/composite/clientRole/containerId; recursively prove only existing assert_unprivileged baseline realm/account roles",
    },
    {
        "endpoint": "/admin/realms/agents/clients?clientId=account",
        "projection": "unique account id/clientId to bind allowed account role container",
    },
    {
        "endpoint": "/admin/realms/agents/groups/{each-default-group-id}",
        "projection": "default groups must be empty; otherwise stop without creating Bob",
    },
]


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def semantic_snapshot(snapshot):
    return {
        key: value
        for key, value in snapshot.items()
        if key not in {"observed_at", "read_request_count"}
    }


def validate_complete(snapshot):
    """Reject missing associated reads and any privilege/provenance collision."""
    from datetime import datetime, timezone
    from uuid import UUID

    def ident(value):
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError("invalid object UUID")
        return value

    def unique(rows, field):
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ValueError("invalid bounded associated read")
        values = [row[field] for row in rows]
        if len(set(values)) != len(values):
            raise ValueError("ambiguous associated read")
        return rows

    if snapshot["version"] != "26.8.1" or any(
        snapshot.get(key) is not True
        for key in ("complete_client_pagination", "complete_user_pagination")
    ):
        raise ValueError("incomplete or incompatible preflight")
    observed = datetime.fromisoformat(snapshot["observed_at"])
    age = (datetime.now(timezone.utc) - observed).total_seconds()
    if observed.tzinfo is None or not 0 <= age <= 3600:
        raise ValueError("preflight older than one hour; refresh before planning")
    if (
        not 1 <= snapshot["read_request_count"] <= 500
        or snapshot["default_group_count"] != 0
    ):
        raise ValueError("unsafe or incomplete defaults")
    cli, account = snapshot["agent_cli"], snapshot["account_client"]
    ident(cli["id"])
    ident(account["id"])
    if (
        cli["clientId"] != "agent-cli"
        or account["clientId"] != "account"
        or cli["publicClient"] is not True
        or cli["standardFlowEnabled"] is not True
        or cli["directAccessGrantsEnabled"] is not False
        or cli["attributes"] != {"pkce.code.challenge.method": "S256"}
        or cli["redirectUris"] != ["http://localhost/*", "http://127.0.0.1/*"]
    ):
        raise ValueError("public PKCE client differs from reviewed settings")
    clients = unique(snapshot["clients"], "id")
    unique(clients, "clientId")
    if (
        len(
            [c for c in clients if (c["id"], c["clientId"]) == (cli["id"], "agent-cli")]
        )
        != 1
    ):
        raise ValueError("agent-cli binding missing")
    if (
        len(
            [
                c
                for c in clients
                if (c["id"], c["clientId"]) == (account["id"], "account")
            ]
        )
        != 1
    ):
        raise ValueError("account binding missing")
    scopes = unique(snapshot["scopes"], "id")
    unique(scopes, "name")
    if any(s["name"] == SCOPE for s in scopes):
        raise ValueError("scope already exists; no adoption")
    known = {s["id"]: {k: s[k] for k in ("id", "name", "protocol")} for s in scopes}
    cli_row = next(c for c in clients if c["id"] == cli["id"])
    effective_scope_ids = {
        s["id"] for key in ("default_scopes", "optional_scopes") for s in cli_row[key]
    }
    for owner in scopes + clients:
        ident(owner["id"])
        mappers = unique(owner["mappers"], "id")
        for mapper in mappers:
            ident(mapper["id"])
            if any(
                not isinstance(mapper.get(key), str) or not mapper[key]
                for key in ("name", "protocol", "protocolMapper")
            ) or not isinstance(mapper.get("config"), dict):
                raise ValueError("incomplete mapper projection")
            effective = owner["id"] == cli["id"] or owner["id"] in effective_scope_ids
            known_effective_providers = {
                "oidc-acr-mapper",
                "oidc-audience-mapper",
                "oidc-usermodel-attribute-mapper",
                "oidc-usermodel-property-mapper",
                "oidc-sub-mapper",
                "oidc-usersessionmodel-note-mapper",
                "oidc-parameterized-scope-audience-mapper",
                "oidc-parameterized-scope-mapper",
                "oidc-parameterized-scope-client-sub-mapper",
                "oidc-usermodel-client-role-mapper",
                "oidc-usermodel-realm-role-mapper",
                "oidc-audience-resolve-mapper",
                "oidc-full-name-mapper",
            }
            if effective and (
                mapper["protocol"] != "openid-connect"
                or mapper["protocolMapper"] not in known_effective_providers
            ):
                raise ValueError("opaque or unreviewed effective mapper")
            if (
                (owner["id"] == cli["id"] or owner["id"] in effective_scope_ids)
                and str(mapper["config"].get("claim.name", "")).split(".")[0]
                == "tenant"
            ) or mapper["config"].get("user.attribute") == "conformance_tenant":
                raise ValueError("existing provenance mapper collision")
            if set(mapper["config"]) - {"claim.name", "user.attribute"}:
                raise ValueError("unexpected mapper projection")
        if owner in clients:
            for key in ("default_scopes", "optional_scopes"):
                for scope in unique(owner[key], "id"):
                    # Built-in default scopes may not appear in realm client-scopes.
                    ident(scope["id"])
                    if (
                        scope["id"] not in known
                        or scope["name"] != known[scope["id"]]["name"]
                        or scope.get("protocol")
                        not in (None, known[scope["id"]]["protocol"])
                    ):
                        raise ValueError("scope association mismatch")
                    if scope["name"] == SCOPE:
                        raise ValueError("provenance scope attachment already exists")
    cli_row = next(c for c in clients if c["id"] == cli["id"])
    if snapshot["agent_cli_optional_scope_names"] != [
        s["name"] for s in cli_row["optional_scopes"]
    ]:
        raise ValueError("optional scope summary mismatch")
    users = unique(snapshot["users"], "id")
    for user in users:
        ident(user["id"])
        if user["conformance_tenant_present"] is not False:
            raise ValueError("existing provenance user collision")
    if not users:
        raise ValueError("recorded Alice subject missing")
    roles = snapshot["default_roles"]
    pending = [snapshot["realm"]["defaultRole"]["id"]]
    visited = set()
    while pending:
        rid = pending.pop()
        if rid in visited:
            continue
        ident(rid)
        visited.add(rid)
        node = roles[rid]
        role = node["role"]
        if (
            role["id"] != rid
            or type(role["composite"]) is not bool
            or type(role["clientRole"]) is not bool
        ):
            raise ValueError("invalid default role node")
        allowed = (
            (
                role["containerId"] == account["id"]
                and role["name"]
                in {"manage-account", "manage-account-links", "view-profile"}
            )
            if role["clientRole"]
            else role["name"]
            in {"default-roles-agents", "offline_access", "uma_authorization"}
        )
        if not allowed:
            raise ValueError("privileged default role")
        for child in unique(node["composites"], "id"):
            if roles[child["id"]]["role"] != child or not role["composite"]:
                raise ValueError("incomplete default role graph")
            pending.append(child["id"])
    if set(roles) != visited or len(roles) > 100:
        raise ValueError("unrelated or truncated default role graph")
    return cli["id"]


def plan_user():
    return {
        "username": USERNAME,
        "enabled": True,
        "firstName": "Bob",
        "lastName": "Conformance",
        "email": "bob.tenant-other@conformance.invalid",
        "emailVerified": True,
        "requiredActions": [],
        "attributes": {"conformance_tenant": [TENANT]},
    }


def plan(snapshot):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("profile"), dict):
        raise ValueError("profile snapshot required")
    profile = deepcopy(snapshot["profile"])
    attributes = profile.get("attributes")
    if not isinstance(attributes, list) or not attributes:
        raise ValueError("complete profile attributes required")
    names = [a.get("name") if isinstance(a, dict) else None for a in attributes]
    if any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(
        names
    ):
        raise ValueError("unique named profile attributes required")
    if ATTRIBUTE["name"] in names:
        raise ValueError("existing managed provenance attribute requires new review")
    if snapshot.get("desired_bob_username_exists") is not False:
        raise ValueError("explicit absent Bob precondition required")
    optional = snapshot.get("agent_cli_optional_scope_names")
    if not isinstance(optional, list) or any(not isinstance(n, str) for n in optional):
        raise ValueError("optional scope names snapshot required")
    if SCOPE in optional or len(set(optional)) != len(optional):
        raise ValueError("existing or ambiguous scope requires new review")
    attributes.append(deepcopy(ATTRIBUTE))
    result = {
        "version": 1,
        "mode": "offline-plan",
        "approval_ready": False,
        "apply_authorized": False,
        "mint_authorized": False,
        "issuer": "https://idp.almckay.io/realms/agents",
        "client": "agent-cli",
        "profile_preimage_sha256": digest(snapshot["profile"]),
        "profile_postimage_sha256": digest(profile),
        "operations": [
            {"method": "PUT", "path": "users/profile", "body": profile},
            {"method": "POST", "path": "client-scopes", "body": deepcopy(SCOPE_BODY)},
            {
                "method": "PUT",
                "path": "clients/{verified-agent-cli-id}/optional-client-scopes/{new-scope-id}",
                "body": None,
            },
            {
                "method": "POST",
                "path": "users",
                "body": {
                    "username": USERNAME,
                    "enabled": True,
                    "firstName": "Bob",
                    "lastName": "Conformance",
                    "email": "bob.tenant-other@conformance.invalid",
                    "emailVerified": True,
                    "requiredActions": [],
                    "attributes": {"conformance_tenant": [TENANT]},
                },
            },
        ],
        "required_readonly_inputs": deepcopy(READS),
        "blockers": [
            "Saved partial snapshot is not a complete current read-only preflight.",
            "No separately approved apply or mint implementation is included.",
            "Re-read exact profile preimage immediately before PUT under exclusive writer ownership; no server CAS exists.",
            "Prove defaults and all associated mapper/attachment/user reads; missing, truncated or ambiguous reads fail closed.",
            "No delegated consent, actor policy, role, group, backend/admin grant or client workload is permitted.",
        ],
        "future_provision_receipt": {
            "required": [
                "new_user_uuid",
                "exact_username",
                "managed_attribute",
                "new_scope_uuid",
                "verified_agent_cli_uuid",
                "profile_preimage_sha256",
                "profile_postimage_sha256",
                "approved_plan_sha256",
            ],
            "identity": "server-assigned new UUID plus exact username and admin-managed conformance_tenant",
        },
        "future_credentials": "Generate only after approval; in-memory creation request and fixed SOPS credentials path only; never plaintext artifact/argv/log.",
        "future_mint": {
            "scope": "openid profile " + SCOPE,
            "flow": "ordinary PKCE S256 with state/nonce",
            "output": "bob-tenant-other-token.enc.yaml access token only via SOPS",
            "requirements": [
                "verified RS256 pinned issuer/JWKS, expiry, azp=agent-cli, typ=Bearer",
                "exact recorded Bob sub distinct from Alice and exact preferred_username",
                "scalar tenant-other; reject act/may_act/agent_id/agent client_type/delegation/backend/admin claims",
                "assert_unprivileged direct/composite roles and no groups before and after mint",
                "no offline scope; discard ID and refresh tokens in memory",
            ],
        },
    }
    if "version" in snapshot:
        cli_id = validate_complete(snapshot)
        result["approval_ready"] = True
        result["preflight_sha256"] = digest(semantic_snapshot(snapshot))
        result["operations"][2]["path"] = (
            f"clients/{cli_id}/optional-client-scopes/{{new-scope-id}}"
        )
        result["required_readonly_inputs"] = []
        result["blockers"] = [
            "User approval and exclusive profile writer ownership required before execution."
        ]
    result["plan_sha256"] = digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "execute", "mint"), default="plan")
    parser.add_argument("--snapshot", type=Path, help="local safe read-only snapshot")
    parser.add_argument("--approved-plan", type=Path)
    parser.add_argument("--approved-plan-sha256")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--exclusive-profile-writer", action="store_true")
    args = parser.parse_args()

    def read_json(path):
        if path is None:
            raise ValueError("required local input missing")
        raw = path.read_bytes()
        if len(raw) > 2 << 20:
            raise ValueError("input too large")
        return json.loads(raw)

    try:
        if args.mode == "plan":
            if (
                args.approved_plan
                or args.approved_plan_sha256
                or args.receipt
                or args.exclusive_profile_writer
            ):
                raise ValueError("execution arguments forbidden in default plan mode")
            result = plan(read_json(args.snapshot))
        else:
            approved = read_json(args.approved_plan)
            if (
                not approved.get("approval_ready")
                or approved.get("plan_sha256") != args.approved_plan_sha256
                or digest({k: v for k, v in approved.items() if k != "plan_sha256"})
                != args.approved_plan_sha256
                or not args.receipt
                or args.snapshot
            ):
                raise ValueError("exact approved plan/digest/receipt required")
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "bob_execution",
                Path(__file__).with_name("conformance-other-tenant-execution.py"),
            )
            execution = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(execution)
            if args.mode == "execute":
                result = execution.execute(
                    approved,
                    args.approved_plan_sha256,
                    args.receipt,
                    exclusive_writer=args.exclusive_profile_writer,
                )
            else:
                result = execution.mint(
                    read_json(args.receipt), args.approved_plan_sha256
                )
    except Exception as exc:
        # Never interpolate remote exceptions, raw documents, passwords or tokens.
        parser.exit(
            1, "Bob fixture refused: " + type(exc).__name__ + "; details omitted\n"
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
