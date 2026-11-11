#!/usr/bin/env python3
"""Explicit approved Bob fixture operations; imported only by execute/mint modes.

Never invoke without separate user approval. No retries of ambiguous mutations,
no adoption, password resets, delegation, role assignment, rollback or kube calls.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import UUID


def load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), Path(__file__).with_name(name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(Path(__file__).resolve().parent))
import keycloak_admin  # noqa: E402

planner = load("conformance-other-tenant")
human = load("conformance-human-token")
DIRECTORY = human.ROOT / "infrastructure/gitops/apps/agent-platform/conformance/human"
CREDENTIALS = DIRECTORY / "bob-tenant-other-credentials.enc.yaml"
TOKEN = DIRECTORY / "bob-tenant-other-token.enc.yaml"
MINT_SCOPE = "openid profile " + planner.SCOPE


class Admin(keycloak_admin.Admin):
    """The Bob fixture's bounded administrator: 500 calls, 10-second timeout."""

    def __init__(self):
        super().__init__(budget=500, timeout=10)


def collect(api):
    """Same safe projection as reviewed root preflight, bounded pages/associated reads."""
    get = api.call

    def rows(path, limit=200):
        result = get(path)
        if not isinstance(result, list) or len(result) > limit:
            raise ValueError("invalid associated read")
        return result

    def pages(path):
        result = []
        for offset in range(0, 1000, 100):
            page = rows(
                path + ("&" if "?" in path else "?") + f"first={offset}&max=100", 100
            )
            if not page:
                return result
            result.extend(page)
        raise ValueError("pagination cap exhausted")

    def mappers(path):
        return [
            {
                **{k: r.get(k) for k in ("id", "name", "protocol", "protocolMapper")},
                "config": {
                    k: r.get("config", {}).get(k)
                    for k in ("claim.name", "user.attribute")
                    if k in r.get("config", {})
                },
            }
            for r in rows(path)
        ]

    def scopes(path):
        return [{k: r.get(k) for k in ("id", "name", "protocol")} for r in rows(path)]

    def roleview(r):
        return {
            k: r.get(k)
            for k in ("id", "name", "composite", "clientRole", "containerId")
        }

    version = get("", server=True)["systemInfo"]["version"]
    profile = get("users/profile")
    clients = pages("clients")
    cli = [c for c in clients if c["clientId"] == "agent-cli"]
    account = [c for c in clients if c["clientId"] == "account"]
    if len(cli) != 1 or len(account) != 1:
        raise ValueError("ambiguous fixed clients")
    cli, account = cli[0], account[0]
    cli_view = {
        k: cli.get(k)
        for k in (
            "id",
            "clientId",
            "publicClient",
            "standardFlowEnabled",
            "directAccessGrantsEnabled",
            "redirectUris",
        )
    }
    cli_view["attributes"] = {
        k: v
        for k, v in cli.get("attributes", {}).items()
        if "pkce" in k.lower() or "challenge" in k.lower()
    }
    scope_rows = scopes("client-scopes")
    for scope in scope_rows:
        scope["mappers"] = mappers(
            "client-scopes/" + scope["id"] + "/protocol-mappers/models"
        )
    client_rows = []
    for client in clients:
        prefix = "clients/" + client["id"]
        client_rows.append(
            {
                "id": client["id"],
                "clientId": client["clientId"],
                "default_scopes": scopes(prefix + "/default-client-scopes"),
                "optional_scopes": scopes(prefix + "/optional-client-scopes"),
                "mappers": mappers(prefix + "/protocol-mappers/models"),
            }
        )
    bob = rows("users?username=" + planner.USERNAME + "&exact=true")
    users = pages("users?briefRepresentation=false")
    user_checks = [
        {
            "id": u["id"],
            "conformance_tenant_present": "conformance_tenant"
            in get("users/" + u["id"]).get("attributes", {}),
        }
        for u in users
    ]
    realm = get("")
    groups = rows("default-groups")
    roles, todo = {}, [realm["defaultRole"]["id"]]
    while todo:
        rid = todo.pop()
        if rid in roles:
            continue
        if len(roles) >= 100:
            raise ValueError("role graph cap exhausted")
        role = roleview(get("roles-by-id/" + rid))
        children = [
            roleview(r) for r in rows("roles-by-id/" + rid + "/composites", 100)
        ]
        roles[rid] = {"role": role, "composites": children}
        todo.extend(r["id"] for r in children)
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "profile": profile,
        "agent_cli": cli_view,
        "account_client": {"id": account["id"], "clientId": "account"},
        "scopes": scope_rows,
        "clients": client_rows,
        "desired_bob_username_exists": bool(bob),
        "agent_cli_optional_scope_names": [
            s["name"]
            for c in client_rows
            if c["id"] == cli["id"]
            for s in c["optional_scopes"]
        ],
        "users": user_checks,
        "realm": {
            k: realm.get(k)
            for k in ("defaultRole", "registrationEnabled", "userManagedAccessAllowed")
        },
        "default_group_count": len(groups),
        "default_roles": roles,
        "complete_client_pagination": True,
        "complete_user_pagination": True,
        "read_request_count": api.count,
        "mapper_projection": "id/name/protocol/provider/claim.name/user.attribute only; no other config values persisted",
    }


def write_receipt(path, receipt, *, create=False):
    """Durable nonsecret owned state; exclusive create and atomic replacements."""
    path = Path(path)
    target = path if create else path.with_name(path.name + ".pending")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(receipt, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    if not create:
        target.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def scope_exact(api, sid):
    actual = api.call("client-scopes/" + sid)
    if actual.get("id") != sid:
        raise ValueError("scope readback identity mismatch")
    actual["protocolMappers"] = api.call(
        "client-scopes/" + sid + "/protocol-mappers/models"
    )
    for mapper in actual["protocolMappers"]:
        UUID(mapper["id"])
        mapper.pop("id")
    view = {k: actual.get(k) for k in planner.SCOPE_BODY}
    if view != planner.SCOPE_BODY:
        raise ValueError("new scope readback differs from approved exact semantics")


def verify_user(api, subject):
    if str(UUID(subject)) != subject:
        raise ValueError("invalid provisioned subject")
    user = api.call("users/" + subject)
    expected = planner.plan_user()
    if user.get("id") != subject or any(user.get(k) != v for k, v in expected.items()):
        raise ValueError("new user readback differs from approved exact semantics")
    human.assert_unprivileged(api.call, subject)
    return user


def execute(
    approved, approved_digest, receipt_path, *, exclusive_writer=False, api=None
):
    # Validate authorization inputs before any admin login/decrypt/read.
    if (
        not exclusive_writer
        or not approved.get("approval_ready")
        or approved_digest != approved.get("plan_sha256")
    ):
        raise ValueError(
            "explicit approved plan digest and exclusive profile writer required"
        )
    unsigned = {k: v for k, v in approved.items() if k != "plan_sha256"}
    if (
        planner.digest(unsigned) != approved_digest
        or Path(receipt_path).exists()
        or CREDENTIALS.exists()
    ):
        raise ValueError("changed plan or pre-existing custody/receipt; no adoption")
    api = api or Admin()
    fresh = collect(api)
    current = planner.plan(fresh)
    if current != approved:
        raise ValueError("fresh read-only preflight differs from approved plan")
    receipt = {
        "version": 1,
        "state": "started",
        "approved_plan_sha256": approved_digest,
        "username": planner.USERNAME,
        "tenant": planner.TENANT,
        "agent_cli_uuid": fresh["agent_cli"]["id"],
        "agent_cli_view": fresh["agent_cli"],
        "optional_scope_ids_before": [
            s["id"]
            for c in fresh["clients"]
            if c["id"] == fresh["agent_cli"]["id"]
            for s in c["optional_scopes"]
        ],
        "profile_preimage_sha256": approved["profile_preimage_sha256"],
        "profile_postimage_sha256": approved["profile_postimage_sha256"],
        "completed": [],
        "preexisting_user_uuids": [u["id"] for u in fresh["users"]],
        "default_scope_names": [
            s["name"]
            for c in fresh["clients"]
            if c["id"] == fresh["agent_cli"]["id"]
            for s in c["default_scopes"]
        ],
    }
    write_receipt(receipt_path, receipt, create=True)

    def attempt(stage, method, path):
        receipt["uncertain_stage"] = stage
        receipt["attempted_operation"] = {"method": method, "path": path}
        write_receipt(receipt_path, receipt)

    def confirmed(stage):
        receipt["completed"].append(stage)
        receipt.pop("uncertain_stage")
        write_receipt(receipt_path, receipt)

    try:
        if (
            planner.digest(api.call("users/profile"))
            != approved["profile_preimage_sha256"]
        ):
            raise ValueError("profile preimage changed before write")
        attempt("profile", "PUT", "users/profile")
        api.call("users/profile", "PUT", approved["operations"][0]["body"])
        if api.call("users/profile") != approved["operations"][0]["body"]:
            raise ValueError("profile readback mismatch")
        confirmed("profile")
        attempt("scope", "POST", "client-scopes")
        api.call("client-scopes", "POST", deepcopy(planner.SCOPE_BODY))
        matches = [s for s in api.call("client-scopes") if s["name"] == planner.SCOPE]
        if len(matches) != 1:
            raise ValueError("created scope not unique")
        sid = matches[0]["id"]
        UUID(sid)
        receipt["new_scope_uuid"] = sid
        write_receipt(receipt_path, receipt)
        scope_exact(api, sid)
        confirmed("scope")
        cli = fresh["agent_cli"]["id"]
        prefix = "clients/" + cli
        before = next(c for c in fresh["clients"] if c["id"] == cli)
        attempt("optional_attachment", "PUT", prefix + "/optional-client-scopes/" + sid)
        api.call(prefix + "/optional-client-scopes/" + sid, "PUT")
        optional = api.call(prefix + "/optional-client-scopes")
        if {s["id"] for s in optional} != {
            s["id"] for s in before["optional_scopes"]
        } | {sid}:
            raise ValueError("optional attachment readback mismatch")
        if {s["id"] for s in api.call(prefix + "/default-client-scopes")} != {
            s["id"] for s in before["default_scopes"]
        }:
            raise ValueError("default attachments changed")
        confirmed("optional_attachment")
        if api.call("users?username=" + planner.USERNAME + "&exact=true"):
            raise ValueError("Bob appeared before creation; no adoption")
        credentials = {
            "username": planner.USERNAME,
            "password": secrets.token_urlsafe(48),
        }
        human.encrypt(
            CREDENTIALS, {"fixture": "T10a other-tenant Bob", "stringData": credentials}
        )
        user = planner.plan_user()
        user["credentials"] = [
            {"type": "password", "temporary": False, "value": credentials["password"]}
        ]
        attempt("user", "POST", "users")
        api.call("users", "POST", user)
        matches = api.call("users?username=" + planner.USERNAME + "&exact=true")
        if len(matches) != 1:
            raise ValueError("created Bob not unique")
        subject = matches[0]["id"]
        if subject in {u["id"] for u in fresh["users"]}:
            raise ValueError("Bob subject is not new")
        receipt["new_user_uuid"] = subject
        write_receipt(receipt_path, receipt)
        verify_user(api, subject)
        credentials["subject"] = subject
        human.encrypt(
            CREDENTIALS, {"fixture": "T10a other-tenant Bob", "stringData": credentials}
        )
        receipt["state"] = "provisioned"
        confirmed("user")
        return receipt
    except Exception as exc:
        receipt["state"] = "failed"
        receipt["error_type"] = type(exc).__name__
        write_receipt(receipt_path, receipt)
        raise RuntimeError(
            "Bob provisioning failed; exact partial-state receipt retained; no automatic retry"
        ) from None


def mint(receipt, approved_digest, *, api=None):
    if (
        receipt.get("state") != "provisioned"
        or receipt.get("approved_plan_sha256") != approved_digest
        or receipt.get("username") != planner.USERNAME
    ):
        raise ValueError("approved provision receipt required before mint")
    required = {
        "new_user_uuid",
        "preexisting_user_uuids",
        "default_scope_names",
        "agent_cli_uuid",
        "agent_cli_view",
        "optional_scope_ids_before",
        "new_scope_uuid",
        "profile_postimage_sha256",
    }
    if not required <= set(receipt):
        raise ValueError("provision receipt is incomplete")
    for key in ("new_user_uuid", "agent_cli_uuid", "new_scope_uuid"):
        if str(UUID(receipt[key])) != receipt[key]:
            raise ValueError("provision receipt UUID mismatch")
    if receipt.get("completed") != ["profile", "scope", "optional_attachment", "user"]:
        raise ValueError("provision receipt does not confirm all operations")
    api = api or Admin()
    subject = receipt["new_user_uuid"]
    if subject in receipt["preexisting_user_uuids"]:
        raise ValueError("Bob subject is not fresh")
    verify_user(api, subject)
    scope_exact(api, receipt["new_scope_uuid"])
    profile = api.call("users/profile")
    if planner.digest(profile) != receipt["profile_postimage_sha256"]:
        raise ValueError("protected profile changed")
    cli = api.call("clients/" + receipt["agent_cli_uuid"])
    expected_cli = receipt["agent_cli_view"]
    for key, value in expected_cli.items():
        actual = cli.get(key)
        if key == "attributes":
            actual = {
                k: v
                for k, v in (actual or {}).items()
                if "pkce" in k.lower() or "challenge" in k.lower()
            }
        if actual != value:
            raise ValueError("PKCE client changed since approval")
    prefix = "clients/" + receipt["agent_cli_uuid"]
    if {s["name"] for s in api.call(prefix + "/default-client-scopes")} != set(
        receipt["default_scope_names"]
    ):
        raise ValueError("default scopes changed")
    if {s["id"] for s in api.call(prefix + "/optional-client-scopes")} != set(
        receipt["optional_scope_ids_before"]
    ) | {receipt["new_scope_uuid"]}:
        raise ValueError("optional scopes changed")
    credentials = human.decrypt(CREDENTIALS)
    if (
        credentials.get("username") != planner.USERNAME
        or credentials.get("subject") != subject
    ):
        raise ValueError("SOPS custody identity mismatch")
    tokens, access = human.pkce_tokens(credentials, MINT_SCOPE, planner.USERNAME)
    verify_access(access, receipt)
    verify_user(api, subject)
    human.encrypt(
        TOKEN,
        {
            "fixture": "T10a ordinary other-tenant access token",
            "stringData": {"token": tokens["access_token"]},
        },
    )
    return {
        "subject": subject,
        "tenant": planner.TENANT,
        "issuer": access["iss"],
        "expires_at": access["exp"],
        "state": "minted-SOPS-only",
    }


def verify_access(access, receipt):
    allowed_claims = {
        "iss",
        "sub",
        "aud",
        "exp",
        "iat",
        "nbf",
        "jti",
        "auth_time",
        "nonce",
        "sid",
        "session_state",
        "acr",
        "scope",
        "azp",
        "typ",
        "preferred_username",
        "name",
        "given_name",
        "family_name",
        "email",
        "email_verified",
        "tenant",
        "realm_access",
        "resource_access",
    }
    if set(access) - allowed_claims:
        raise ValueError("unexpected access token claims")
    forbidden = {"act", "may_act", "agent_id", "authorization", "permissions"}
    if (
        access.get("tenant") != planner.TENANT
        or type(access.get("tenant")) is not str
        or access.get("sub") != receipt["new_user_uuid"]
        or any(k in access for k in forbidden)
        or access.get("client_type") == "agent"
        or not set(MINT_SCOPE.split()) <= set(access.get("scope", "").split())
        or set(access.get("scope", "").split())
        - set(MINT_SCOPE.split())
        - set(receipt["default_scope_names"])
    ):
        raise ValueError("Bob access token provenance or scope mismatch")
    audience = access.get("aud", [])
    audience = [audience] if isinstance(audience, str) else audience
    if not isinstance(audience, list) or set(audience) - {"account", "agent-cli"}:
        raise ValueError("unexpected access token audience")
    realm_roles = set(access.get("realm_access", {}).get("roles", []))
    if realm_roles - {"default-roles-agents", "offline_access", "uma_authorization"}:
        raise ValueError("unexpected access token realm privilege")
    for name, resource in access.get("resource_access", {}).items():
        if name != "account" or set(resource.get("roles", [])) - {
            "manage-account",
            "manage-account-links",
            "view-profile",
        }:
            raise ValueError("unexpected access token client privilege")
