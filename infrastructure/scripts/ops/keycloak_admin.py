"""Keycloak admin REST access with the SOPS-held bootstrap administrator.

Shared by the production identity commands and the conformance fixtures. No
token, password, cookie or response body is placed in any exception message.
Importing this module decrypts nothing and contacts nothing; only `Admin()` and
`admin_client()` do, and only when called.
"""

from __future__ import annotations

import http.cookiejar
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = "https://idp.almckay.io"
BOOTSTRAP = ROOT / "infrastructure/gitops/apps/keycloak/keycloak-bootstrap-admin.enc.yaml"
MAX_RESPONSE = 2 * 1024 * 1024
METHODS = frozenset({"GET", "PUT", "POST"})


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


def admin_client():
    admin = decrypt(BOOTSTRAP)
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


class Admin:
    """Admin calls on the `agents` realm.

    `budget` caps how many calls one instance makes (None: unlimited);
    `timeout` is the per-call socket timeout in seconds.
    """

    def __init__(self, *, budget=None, timeout=30):
        self.client, self.bearer = admin_client()
        self.budget, self.timeout, self.count = budget, timeout, 0

    def call(self, path, method="GET", payload=None, *, server=False):
        if path.startswith("/") or ".." in path or "#" in path or method not in METHODS:
            raise ValueError("invalid admin request")
        self.count += 1
        if self.budget is not None and self.count > self.budget:
            raise ValueError("admin request budget exhausted")
        url = ORIGIN + ("/admin/serverinfo" if server else "/admin/realms/agents/" + path)
        headers = {"Authorization": "Bearer " + self.bearer}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.client.open(req, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Keycloak admin HTTP {exc.code}; response omitted") from None
        if len(raw) > MAX_RESPONSE:
            raise ValueError("admin response size budget exhausted")
        return json.loads(raw) if raw else None

    def unique_client(self, name):
        rows = self.call("clients?clientId=" + urllib.parse.quote(name, safe=""))
        if len(rows) != 1 or rows[0]["clientId"] != name:
            raise ValueError("client not unique: " + name)
        return rows[0]
