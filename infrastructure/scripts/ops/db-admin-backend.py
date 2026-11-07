#!/usr/bin/env python3
"""Exact postgres-admin resource/scope bootstrap. Default is read-only planning.

Only --apply creates missing exact objects (including one noncomposite realm
role) or attaches the scope optionally to
APS. Conflicting existing configuration is never overwritten. Root runs this
with the existing SOPS admin helper; no credentials or raw responses are printed.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import quote

RESOURCE = "https://mcp.almckay.io/postgres-admin/mcp"
SCOPE = "mcp:postgres-admin"
REQUESTER = "agent-policy-service"
ROLE = "agent-role-postgres-admin-read"


def resource_body():
    return {
        "clientId": RESOURCE,
        "name": "MCP resource: postgres-admin",
        "description": "Spec 7.7. Target of audience= in exchanges for the postgres-admin backend.",
        "enabled": True,
        "protocol": "openid-connect",
        "bearerOnly": True,
        "publicClient": False,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
    }


def scope_body():
    return {
        "name": SCOPE,
        "protocol": "openid-connect",
        "attributes": {"include.in.token.scope": "true"},
        "protocolMappers": [
            {
                "name": "aud-mcp:postgres-admin",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "config": {
                    "included.custom.audience": RESOURCE,
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                    "introspection.token.claim": "true",
                },
            }
        ],
    }


def rows(value):
    if (
        not isinstance(value, list)
        or len(value) > 1000
        or any(not isinstance(v, dict) for v in value)
    ):
        raise ValueError("invalid bounded associated read")
    return value


def object_id(value):
    ident = value.get("id")
    if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ident):
        raise ValueError("invalid object identity")
    return ident


def find_client(api, client_id):
    found = rows(api.call("clients?clientId=" + quote(client_id, safe="")))
    if len(found) > 1 or any(v.get("clientId") != client_id for v in found):
        raise ValueError("client identity is ambiguous")
    if not found:
        return None
    ident = object_id(found[0])
    actual = api.call("clients/" + ident)
    if (
        not isinstance(actual, dict)
        or actual.get("clientId") != client_id
        or object_id(actual) != ident
    ):
        raise ValueError("associated client read differs")
    return actual


def verify_resource(api, actual):
    for key, value in resource_body().items():
        if key not in {"name", "description"} and actual.get(key) != value:
            raise ValueError("existing resource client conflicts")
    if actual.get("implicitFlowEnabled", False) is not False:
        raise ValueError("resource permits implicit flow")
    if rows(api.call("clients/" + object_id(actual) + "/protocol-mappers/models")):
        raise ValueError("resource has unexpected mappers")


def verify_scope(api, summary):
    ident = object_id(summary)
    actual = api.call("client-scopes/" + ident)
    if (
        not isinstance(actual, dict)
        or object_id(actual) != ident
        or actual.get("name") != SCOPE
        or actual.get("protocol") != "openid-connect"
    ):
        raise ValueError("existing scope identity/protocol conflicts")
    attributes = deepcopy(actual.get("attributes", {}))
    # Keycloak's UI can materialize the false consent-screen default. It does
    # not broaden the scope or change the controller's audience semantics.
    if attributes.get("display.on.consent.screen") == "false":
        attributes.pop("display.on.consent.screen")
    if attributes != scope_body()["attributes"]:
        raise ValueError("existing scope attributes conflict")
    mappers = deepcopy(
        rows(api.call("client-scopes/" + ident + "/protocol-mappers/models"))
    )
    if len(mappers) != 1:
        raise ValueError("scope must contain exactly one mapper")
    mapper = mappers[0]
    mapper.pop("id", None)
    if mapper.get("consentRequired") is False:
        mapper.pop("consentRequired")
    config = mapper.get("config")
    if not isinstance(config, dict):
        raise ValueError("mapper config missing")
    # AbstractOIDCProtocolMapper may expose userinfo's id-token=false default;
    # an empty optional client audience is equivalent to it being absent.
    if config.get("userinfo.token.claim") == "false":
        config.pop("userinfo.token.claim")
    if config.get("included.client.audience") == "":
        config.pop("included.client.audience")
    if mapper != scope_body()["protocolMappers"][0]:
        raise ValueError("existing mapper conflicts with exact controller audience")
    return ident


def find_role(api):
    # New realm roles cannot be created by the controller's current narrow admin
    # grants (Keycloak26.8.1 RoleContainerResource -> requireManage(RealmModel)).
    found = [
        role
        for role in rows(
            api.call("roles?search=" + ROLE + "&briefRepresentation=false")
        )
        if role.get("name") == ROLE
    ]
    if len(found) > 1:
        raise ValueError("realm role identity is ambiguous")
    if not found:
        return None
    ident = object_id(found[0])
    actual = api.call("roles/" + ROLE)
    if (
        not isinstance(actual, dict)
        or object_id(actual) != ident
        or actual.get("name") != ROLE
        or actual.get("clientRole") is not False
        or actual.get("composite") is not False
        or actual.get("attributes", {})
    ):
        raise ValueError(
            "existing realm role conflicts with exact noncomposite backend role"
        )
    if rows(api.call("roles-by-id/" + ident + "/composites")):
        raise ValueError("backend realm role has unexpected composites")
    return ident


def role_body():
    return {
        "name": ROLE,
        "description": "MCP backend postgres-admin, read tools",
        "composite": False,
        "clientRole": False,
        "attributes": {},
    }


def inspect(api):
    role_id = find_role(api)
    resource = find_client(api, RESOURCE)
    if resource is not None:
        verify_resource(api, resource)
    found = [s for s in rows(api.call("client-scopes")) if s.get("name") == SCOPE]
    if len(found) > 1:
        raise ValueError("scope name is ambiguous")
    sid = verify_scope(api, found[0]) if found else None
    requester = find_client(api, REQUESTER)
    if (
        requester is None
        or any(
            requester.get(key) != value
            for key, value in {
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": False,
                "serviceAccountsEnabled": True,
            }.items()
        )
        or requester.get("attributes", {}).get("standard.token.exchange.enabled")
        != "true"
    ):
        raise ValueError("exact enabled APS exchange requester required")
    if any(
        requester.get(key, False) is not False
        for key in (
            "bearerOnly",
            "standardFlowEnabled",
            "implicitFlowEnabled",
            "directAccessGrantsEnabled",
        )
    ):
        raise ValueError("APS requester flow settings conflict")
    rid = object_id(requester)
    attachments = {}
    attachment_ids = {}
    for kind in ("default", "optional"):
        values = rows(api.call(f"clients/{rid}/{kind}-client-scopes"))
        if len({v.get("name") for v in values}) != len(values) or len(
            {object_id(v) for v in values}
        ) != len(values):
            raise ValueError("ambiguous scope attachments")
        matched = [
            v
            for v in values
            if v.get("name") == SCOPE or (sid is not None and v["id"] == sid)
        ]
        if any(v.get("name") != SCOPE or v["id"] != sid for v in matched):
            raise ValueError("scope attachment identity conflicts")
        attachments[kind] = matched
        attachment_ids[kind] = {v["id"] for v in values}
    if attachments["default"]:
        raise ValueError("backend scope must remain optional on APS")
    planned = []
    if role_id is None:
        planned.append("create_role")
    if resource is None:
        planned.append("create_resource")
    if sid is None:
        planned.append("create_scope")
    if not attachments["optional"]:
        planned.append("attach_aps_optional")
    return {
        "role_id": role_id,
        "resource_id": object_id(resource) if resource else None,
        "scope_id": sid,
        "requester_id": rid,
        "planned": planned,
        "attachment_ids": attachment_ids,
    }


def configure(api, *, apply=False):
    before = inspect(api)  # Validate ALL existing semantics before ANY mutation.
    changed = []
    current = before
    if apply:
        for operation in before["planned"]:
            if operation == "create_role":
                api.call("roles", method="POST", payload=role_body())
            elif operation == "create_resource":
                api.call("clients", method="POST", payload=resource_body())
            elif operation == "create_scope":
                api.call("client-scopes", method="POST", payload=scope_body())
            else:
                if current["scope_id"] is None:
                    raise ValueError("created scope identity not confirmed")
                api.call(
                    f"clients/{current['requester_id']}/optional-client-scopes/{current['scope_id']}",
                    method="PUT",
                )
            previous = current
            current = inspect(
                api
            )  # Exact associated readbacks; never repair conflicts.
            expected_optional = previous["attachment_ids"]["optional"] | (
                {previous["scope_id"]} if operation == "attach_aps_optional" else set()
            )
            if (
                current["attachment_ids"]["default"]
                != previous["attachment_ids"]["default"]
                or current["attachment_ids"]["optional"] != expected_optional
            ):
                raise ValueError(
                    "unrelated APS scope attachment changed during mutation"
                )
            if operation in current["planned"]:
                raise ValueError(
                    "mutation readback did not confirm requested operation"
                )
            changed.append(operation)
        if current["planned"]:
            raise ValueError("backend bootstrap remains incomplete")
    return {
        "mode": "apply" if apply else "read-only-plan",
        "resource": RESOURCE,
        "scope": SCOPE,
        "requester": REQUESTER,
        "planned": before["planned"],
        "changed": changed,
        "role": ROLE,
        "role_id": current["role_id"],
        "resource_id": current["resource_id"],
        "scope_id": current["scope_id"],
    }


def admin():
    spec = importlib.util.spec_from_file_location(
        "db_admin_delegation_auth",
        Path(__file__).with_name("conformance-delegation.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Admin()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="explicitly create/attach exact missing backend objects",
    )
    args = parser.parse_args()
    try:
        result = configure(admin(), apply=args.apply)
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "error_type": type(error).__name__,
                    "note": "No conflicting object is overwritten; reconcile any ambiguous partial write before retry.",
                }
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
