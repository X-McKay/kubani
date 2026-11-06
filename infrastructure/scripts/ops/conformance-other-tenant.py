#!/usr/bin/env python3
"""Offline, fixed-identity T10a change planner. Contains no live apply/mint path."""

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
    result["plan_sha256"] = digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        required=True,
        type=Path,
        help="local safe profile snapshot; never an issuer URL",
    )
    args = parser.parse_args()
    try:
        raw = args.snapshot.read_bytes()
        if len(raw) > 2 << 20:
            raise ValueError("snapshot too large")
        result = plan(json.loads(raw))
    except (ValueError, OSError, TypeError, KeyError):
        parser.exit(1, "offline plan refused: invalid or conflicting snapshot\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
