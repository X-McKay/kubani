#!/usr/bin/env python3
"""Operator-only synthetic human fixture; SOPS at rest, PKCE login to agent-cli.

No token, password, cookie, authorization code or response body is logged. The
fixture user has no assigned agent/backend/admin roles. Never changes an existing
user's password. Requirements: sops, kubectl (with --apply), PyYAML, PyJWT[crypto].
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import jwt
import yaml

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = "https://idp.almckay.io"
ISSUER = ORIGIN + "/realms/agents"
CALLBACK = "http://127.0.0.1:8765/callback"
USERNAME = "conformance-alice"
CLIENT = "agent-cli"
CREDENTIALS = (
    ROOT
    / "infrastructure/gitops/apps/agent-platform/conformance/human/alice-credentials.enc.yaml"
)


def issuer_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme, parsed.netloc) != (
        "https",
        "idp.almckay.io",
    ) or not parsed.path.startswith("/realms/agents/"):
        raise ValueError("refusing non-issuer credential destination")
    return url


def callback_code(url: str, state: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (
        urllib.parse.urlunsplit(parsed._replace(query="", fragment="")) != CALLBACK
        or parsed.fragment
    ):
        raise ValueError("unexpected callback destination")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if (
        query.get("state") != [state]
        or "error" in query
        or len(query.get("code", [])) != 1
        or not query["code"][0]
    ):
        raise ValueError("callback state/code validation failed")
    return query["code"][0]


def pkce_challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.current = {
                "id": attrs.get("id"),
                "action": attrs.get("action", ""),
                "hidden": {},
            }
            self.forms.append(self.current)
        elif (
            tag == "input"
            and self.current is not None
            and attrs.get("type") == "hidden"
            and attrs.get("name")
        ):
            self.current["hidden"][attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def opener():
    return urllib.request.build_opener(
        NoRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def request(client, url, fields=None, *, bearer=None, payload=None):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme, parsed.netloc) != ("https", "idp.almckay.io"):
        raise ValueError("refusing untrusted HTTP destination")
    headers = {}
    data = None
    if fields is not None:
        data = urllib.parse.urlencode(fields).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        response = client.open(req, timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code not in (302, 303):
            raise RuntimeError(f"Keycloak HTTP {exc.code}; response omitted") from None
        response = exc
    with response:
        return response.code, response.headers, response.read(2 * 1024 * 1024)


def decrypt(path):
    result = subprocess.run(
        ["sops", "--decrypt", str(path)], check=True, capture_output=True, text=True
    )
    return yaml.safe_load(result.stdout)["stringData"]


def encrypt(path, document):
    if not str(path).endswith(".enc.yaml"):
        raise ValueError("encrypted output must end in .enc.yaml")
    result = subprocess.run(
        [
            "sops",
            "--encrypt",
            "--config",
            str(ROOT / ".sops.yaml"),
            "--filename-override",
            str(path),
            "--input-type",
            "yaml",
            "--output-type",
            "yaml",
            "/dev/stdin",
        ],
        input=yaml.safe_dump(document, sort_keys=False),
        check=True,
        capture_output=True,
        text=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.stdout)


def admin_client():
    admin = decrypt(
        ROOT / "infrastructure/gitops/apps/keycloak/keycloak-bootstrap-admin.enc.yaml"
    )
    client = opener()
    _, _, raw = request(
        client,
        ORIGIN + "/realms/master/protocol/openid-connect/token",
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            **admin,
        },
    )
    return client, json.loads(raw)["access_token"]


def admin_get(client, bearer, path):
    _, _, raw = request(client, ORIGIN + "/admin/realms/agents/" + path, bearer=bearer)
    return json.loads(raw)


def assert_unprivileged(get, subject):
    # Inspect direct assignments and recursively expand composites: a modified
    # default role must not hide administrative or backend privileges.
    if get("users/" + subject + "/groups"):
        raise ValueError("fixture has unexpected group membership")
    accounts = get("clients?clientId=account")
    if len(accounts) != 1:
        raise ValueError("account client is not unique")
    account_id = accounts[0]["id"]
    mappings = get("users/" + subject + "/role-mappings")
    pending = list(mappings.get("realmMappings", []))
    for mapping in mappings.get("clientMappings", {}).values():
        pending.extend(mapping["mappings"])
    visited = set()
    while pending:
        role = pending.pop()
        if role["id"] in visited:
            continue
        visited.add(role["id"])
        if role.get("clientRole"):
            allowed = role.get("containerId") == account_id and role["name"] in {
                "manage-account",
                "manage-account-links",
                "view-profile",
            }
        else:
            allowed = role["name"] in {
                "default-roles-agents",
                "offline_access",
                "uma_authorization",
            }
        if not allowed:
            raise ValueError("fixture has an unexpected role assignment")
        if role.get("composite"):
            pending.extend(get("roles-by-id/" + role["id"] + "/composites"))


def create_user():
    client, bearer = admin_client()
    url = ORIGIN + "/admin/realms/agents/users"
    _, _, raw = request(
        client, url + "?username=" + USERNAME + "&exact=true", bearer=bearer
    )
    users = json.loads(raw)
    if users:
        if (
            not CREDENTIALS.exists()
            or len(users) != 1
            or users[0]["id"] != decrypt(CREDENTIALS)["subject"]
        ):
            raise ValueError(
                "existing user is not the recorded fixture; no changes made"
            )
        assert_unprivileged(
            lambda path: admin_get(client, bearer, path), users[0]["id"]
        )
        print(
            json.dumps(
                {
                    "status": "existing fixture unchanged",
                    "subject": users[0]["id"],
                    "username": USERNAME,
                }
            )
        )
        return
    credentials = (
        decrypt(CREDENTIALS)
        if CREDENTIALS.exists()
        else {
            "username": USERNAME,
            "subject": "",  # Keycloak assigns the subject on creation.
            "password": secrets.token_urlsafe(48),
        }
    )
    if credentials["username"] != USERNAME:
        raise ValueError("unexpected fixture username")
    if not CREDENTIALS.exists():
        encrypt(
            CREDENTIALS,
            {"fixture": "agent-platform synthetic Alice", "stringData": credentials},
        )
    user = {
        "username": USERNAME,
        "enabled": True,
        "firstName": "Alice",
        "lastName": "Conformance",
        "email": "alice@conformance.invalid",
        "emailVerified": True,
        "requiredActions": [],
        "attributes": {"conformance_fixture": ["agent-platform"]},
        "credentials": [
            {"type": "password", "temporary": False, "value": credentials["password"]}
        ],
    }
    status, _, _ = request(client, url, bearer=bearer, payload=user)
    if status != 201:
        raise ValueError("fixture user creation did not return 201")
    _, _, raw = request(
        client, url + "?username=" + USERNAME + "&exact=true", bearer=bearer
    )
    created = json.loads(raw)
    if len(created) != 1 or created[0]["username"] != USERNAME:
        raise ValueError("created fixture identity could not be verified")
    credentials["subject"] = created[0]["id"]
    encrypt(
        CREDENTIALS,
        {"fixture": "agent-platform synthetic Alice", "stringData": credentials},
    )
    assert_unprivileged(
        lambda path: admin_get(client, bearer, path), credentials["subject"]
    )
    print(
        json.dumps(
            {
                "status": "created synthetic fixture",
                "subject": credentials["subject"],
                "username": USERNAME,
            }
        )
    )


def mint_tokens(scope="openid profile"):
    allowed_scopes = {
        "openid profile",
        "openid profile agent-policy-service delegation:client:agent-tenant-test-conformance",
        "openid profile agent-policy-service delegation:client:agent-tenant-test-conformance-b",
        "openid profile agent-policy-service delegation:client:agent-tenant-test-conformance-lifecycle",
        "openid profile offline_access agent-policy-service delegation:client:agent-tenant-test-conformance",
        "openid profile offline_access agent-policy-service delegation:client:agent-tenant-test-conformance-b",
        "openid profile offline_access agent-policy-service delegation:client:agent-tenant-test-conformance-lifecycle",
    }
    if scope not in allowed_scopes:
        raise ValueError("unexpected synthetic fixture consent scopes")
    credentials = decrypt(CREDENTIALS)
    admin, bearer = admin_client()
    assert_unprivileged(
        lambda path: admin_get(admin, bearer, path), credentials["subject"]
    )
    admin, bearer = None, None
    return pkce_tokens(credentials, scope, USERNAME)


def pkce_tokens(credentials, scope, expected_username):
    """Shared fixed-origin PKCE transport; callers validate their own fixed profile."""
    verifier, state, nonce = (secrets.token_urlsafe(48) for _ in range(3))
    client = opener()
    url = (
        ISSUER
        + "/protocol/openid-connect/auth?"
        + urllib.parse.urlencode(
            {
                "client_id": CLIENT,
                "redirect_uri": CALLBACK,
                "response_type": "code",
                "scope": scope,
                "code_challenge_method": "S256",
                "code_challenge": pkce_challenge(verifier),
                "state": state,
                "nonce": nonce,
                "kc_idp_hint": "",
                "prompt": "login",
            }
        )
    )
    fields = None
    code = None
    logged_in = False
    for _ in range(10):
        status, headers, raw = request(client, issuer_url(url), fields)
        fields = None
        if status in (302, 303):
            destination = urllib.parse.urljoin(url, headers["Location"])
            if destination.startswith(CALLBACK + "?"):
                code = callback_code(destination, state)
                break
            url = issuer_url(destination)
            continue
        parser = Forms()
        parser.feed(raw.decode())
        candidates = [
            f
            for f in parser.forms
            if f["id"] == "kc-form-login"
            or urllib.parse.urlsplit(urllib.parse.urljoin(url, f["action"])).path
            == "/realms/agents/login-actions/consent"
        ]
        if len(candidates) != 1:
            raise ValueError("expected login or consent form missing; response omitted")
        form = candidates[0]
        url = issuer_url(urllib.parse.urljoin(url, form["action"]))
        fields = dict(form["hidden"])
        if form["id"] == "kc-form-login":
            if logged_in:
                raise ValueError("login was rejected; no repeated password attempts")
            fields.update(
                username=credentials["username"], password=credentials["password"]
            )
            logged_in = True
        else:
            fields["accept"] = "Yes"
    if not code or not logged_in:
        raise ValueError("PKCE login did not complete")
    _, _, raw = request(
        client,
        ISSUER + "/protocol/openid-connect/token",
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT,
            "code": code,
            "redirect_uri": CALLBACK,
            "code_verifier": verifier,
        },
    )
    tokens = json.loads(raw)
    _, _, raw = request(client, ISSUER + "/protocol/openid-connect/certs")
    keys = jwt.PyJWKSet.from_dict(json.loads(raw))

    def claims(token, audience=None):
        kid = jwt.get_unverified_header(token)["kid"]
        key = keys[kid].key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=ISSUER,
            audience=audience,
            options={
                "verify_aud": audience is not None,
                "require": ["iss", "sub", "exp", "iat"],
            },
        )

    identity = claims(tokens["id_token"], CLIENT)
    access = claims(tokens["access_token"])
    if identity.get("nonce") != nonce or any(
        c["sub"] != credentials["subject"] for c in (identity, access)
    ):
        raise ValueError("token identity or nonce mismatch")
    if (
        access.get("preferred_username") != expected_username
        or access.get("azp") != CLIENT
        or access.get("typ") != "Bearer"
    ):
        raise ValueError("unexpected human access token claims")
    if (
        any(k in access for k in ("act", "agent_id"))
        or access.get("client_type") == "agent"
    ):
        raise ValueError("human fixture unexpectedly has agent/delegated identity")
    return tokens, access


def mint(output: Path, apply: bool):
    tokens, access = mint_tokens()
    encrypt(
        output,
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "type": "Opaque",
            "metadata": {
                "name": "conformance-human-token",
                "namespace": "agent-platform",
            },
            "stringData": {"token": tokens["access_token"]},
        },
    )
    if apply:
        plaintext = subprocess.run(
            ["sops", "--decrypt", str(output)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=plaintext,
            check=True,
            capture_output=True,
            text=True,
        )
    print(
        json.dumps(
            {
                "status": "minted via PKCE",
                "applied": apply,
                **{
                    k: access[k]
                    for k in ("iss", "sub", "preferred_username", "azp", "iat", "exp")
                },
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--create-user",
        action="store_true",
        help="Create the dedicated fixture if absent; never reset an existing user",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="SOPS token Secret output (.enc.yaml); mint immediately before the Job",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the encrypted token Secret via an in-memory decrypt",
    )
    args = parser.parse_args()
    if args.create_user:
        if args.output or args.apply:
            parser.error("user creation and token minting are separate operations")
        create_user()
    elif args.output:
        mint(args.output, args.apply)
    else:
        parser.error("choose --create-user or --output")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Third-party exceptions can include URLs, form fields or token material.
        print(
            f"Human fixture failed ({type(exc).__name__}); sensitive details omitted",
            file=sys.stderr,
        )
        sys.exit(1)
