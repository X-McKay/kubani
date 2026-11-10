"""Ask Keycloak whether it would issue the person at this terminal a depositable delegation token.

`consent --check` signs a person in at the `agents` realm's public `agent-cli`
client (authorization code, PKCE S256, loopback redirect), compares the access
token Keycloak returns with the four conditions the Agent Policy Service places
on a grant deposit, reports the verdict as metadata and discards the tokens.

It never calls the APS, deposits a token or creates a grant, and it reads
nothing from the cluster. The person signs in and consents in their own
browser; no form is scripted and no username or password is taken. No token,
authorization code or code verifier reaches argv, a file, a log line, an
exception message or the output.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from . import layout

ISSUER = "https://idp.almckay.io/realms/agents"
CLIENT = "agent-cli"
POLICY_AUDIENCE = "agent-policy-service"
# Always a fresh sign-in and a fresh consent screen: the answer must come from the person, not from a browser session.
PROMPT = "login consent"
AUTH_PATH = "/protocol/openid-connect/auth"
TOKEN_PATH = "/protocol/openid-connect/token"
CERTS_PATH = "/protocol/openid-connect/certs"
REVOKE_PATH = "/protocol/openid-connect/revoke"
CALLBACK_PATH = "/callback"
DEFAULT_TIMEOUT = 300.0
MAX_TIMEOUT = 900.0
HTTP_TIMEOUT = 30
READ_TIMEOUT = 5
MAX_HEAD = 16 * 1024
MAX_RESPONSE = 1024 * 1024
ERROR_CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}\Z")
PAGE = (
    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nCache-Control: no-store\r\n"
    b"Referrer-Policy: no-referrer\r\nConnection: close\r\n\r\n"
    b"The sign-in response reached the terminal. You can close this tab.\n"
)


class ConsentError(Exception):
    """The check was refused or could not reach a verdict."""


class ConsentTimeout(Exception):
    """No callback arrived within the wait."""


def interactive() -> bool:
    return all(stream is not None and stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr))


def required_scope(tenant: str, agent: str) -> str:
    return f"delegation:client:agent-{tenant}-{agent}"


def tenant_of(root: Path, agent: str) -> str:
    """The tenant of a committed on-behalf-of agent; any other identity mode is refused."""
    d = layout.find_agent(root, agent)
    mode = (layout.committed_agent(d)["spec"].get("identity") or {}).get("mode")
    if mode != "on-behalf-of":
        raise ConsentError(f"{agent} declares identity mode {mode!r} in its committed Agent; only an on-behalf-of agent takes a person's consent")
    return d.tenant


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorization_url(issuer: str, *, redirect_uri: str, scope: str, state: str, nonce: str, challenge: str) -> str:
    query = {
        "response_type": "code",
        "client_id": CLIENT,
        "redirect_uri": redirect_uri,
        "scope": f"openid {POLICY_AUDIENCE} {scope}",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": PROMPT,
    }
    return issuer + AUTH_PATH + "?" + urllib.parse.urlencode(query)


def _read_head(conn: socket.socket) -> bytes:
    data = b""
    try:
        while b"\r\n\r\n" not in data and len(data) < MAX_HEAD:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
    except OSError:
        return b""
    return data.split(b"\r\n", 1)[0]


def await_callback(listener: socket.socket, timeout: float, clock) -> bytes:
    """The request line of the one request the listener accepts; a connection that sends nothing is skipped."""
    deadline = clock() + timeout
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            raise ConsentTimeout
        listener.settimeout(min(remaining, 1.0))
        try:
            conn, _ = listener.accept()
        except TimeoutError:
            continue
        with conn:
            conn.settimeout(READ_TIMEOUT)
            line = _read_head(conn)
            if not line:
                continue
            try:
                conn.sendall(PAGE)
            except OSError:
                pass
            return line


def callback_query(request_line: bytes) -> dict[str, list[str]]:
    parts = request_line.decode("ascii", "replace").split(" ")
    target = urllib.parse.urlsplit(parts[1]) if len(parts) == 3 else None
    if target is None or parts[0] != "GET" or target.path != CALLBACK_PATH:
        raise ConsentError("the loopback listener received a request that is not the sign-in callback; nothing was exchanged")
    return urllib.parse.parse_qs(target.query, keep_blank_values=True)


def callback_code(query: dict[str, list[str]], state: str) -> str:
    got = query.get("state", [])
    if len(got) != 1 or not hmac.compare_digest(got[0].encode(), state.encode()):
        raise ConsentError("the callback's state does not match this sign-in; nothing was exchanged")
    if "error" in query:
        error = query["error"][0]
        named = error if ERROR_CODE.match(error) else "(unprintable)"
        raise ConsentError(f"Keycloak returned the error {named} instead of an authorization code")
    codes = query.get("code", [])
    if len(codes) != 1 or not codes[0]:
        raise ConsentError("the callback carried no authorization code")
    return codes[0]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _oauth_error(exc: urllib.error.HTTPError) -> str:
    try:
        error = json.loads(exc.read(4096)).get("error")
    except (OSError, ValueError, AttributeError):
        return ""
    return f" ({error})" if isinstance(error, str) and ERROR_CODE.match(error) else ""


def _fetch(url: str, what: str, fields: dict | None = None) -> bytes:
    """One bounded request that follows no redirect. Errors name the endpoint and a status or error code, never a body."""
    data = urllib.parse.urlencode(fields).encode() if fields is not None else None
    request = urllib.request.Request(url, data=data, headers={"Accept": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=HTTP_TIMEOUT) as response:
            return response.read(MAX_RESPONSE)
    except urllib.error.HTTPError as exc:
        raise ConsentError(f"the {what} answered HTTP {exc.code}{_oauth_error(exc)}") from None
    except (OSError, ValueError) as exc:
        raise ConsentError(f"the {what} could not be reached ({type(exc).__name__})") from None


def _json(raw: bytes, what: str) -> dict:
    try:
        doc = json.loads(raw)
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        raise ConsentError(f"the {what} did not return a JSON object")
    return doc


def exchange(issuer: str, code: str, verifier: str, redirect_uri: str) -> dict:
    fields = {"grant_type": "authorization_code", "client_id": CLIENT, "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier}
    doc = _json(_fetch(issuer + TOKEN_PATH, "token endpoint", fields), "token endpoint")
    for name in ("access_token", "id_token"):
        if not isinstance(doc.get(name), str) or not doc[name]:
            raise ConsentError(f"the token endpoint returned no {name}")
    refresh = doc.get("refresh_token")
    return {"access": doc["access_token"], "id": doc["id_token"], "refresh": refresh if isinstance(refresh, str) and refresh else None}


def _pyjwt():
    """PyJWT comes from the `agent` recipe; it is imported on use so the other subcommands run without it."""
    try:
        import jwt
    except ImportError:
        raise ConsentError("PyJWT is not installed; run this as `just agent consent --check AGENT`") from None
    return jwt


def verified_claims(issuer: str, tokens: dict, nonce: str) -> dict:
    """Access-token claims, after both tokens verify against the realm JWKS and the ID token carries this sign-in's nonce."""
    jwt = _pyjwt()
    try:
        keys = jwt.PyJWKSet.from_dict(_json(_fetch(issuer + CERTS_PATH, "JWKS endpoint"), "JWKS endpoint"))
    except jwt.PyJWTError as exc:
        raise ConsentError(f"the realm JWKS could not be used ({type(exc).__name__})") from None

    def decode(token: str, what: str, audience: str | None) -> dict:
        options = {"verify_signature": True, "verify_aud": audience is not None, "require": ["iss", "sub", "exp", "iat"]}
        try:
            key = keys[jwt.get_unverified_header(token)["kid"]].key
            return jwt.decode(token, key, algorithms=["RS256"], issuer=issuer, audience=audience, options=options)
        except (jwt.PyJWTError, KeyError) as exc:
            raise ConsentError(f"the {what} failed verification against the realm keys and issuer ({type(exc).__name__})") from None

    access = decode(tokens["access"], "access token", None)
    identity = decode(tokens["id"], "ID token", CLIENT)
    if not hmac.compare_digest(str(identity.get("nonce", "")).encode(), nonce.encode()) or identity["sub"] != access["sub"]:
        raise ConsentError("the ID token does not belong to this sign-in")
    return access


def assess(claims: dict, tenant: str, agent: str, *, now: float) -> dict:
    """The four conditions the APS deposit handler places on the bearer token, as metadata."""
    required = required_scope(tenant, agent)
    aud = claims.get("aud")
    audiences = [aud] if isinstance(aud, str) else [a for a in aud or [] if isinstance(a, str)]
    scopes = claims["scope"].split() if isinstance(claims.get("scope"), str) else []
    may_act = claims.get("may_act")
    may_act_sub = may_act.get("sub") if isinstance(may_act, dict) else None
    may_act_sub = may_act_sub if isinstance(may_act_sub, str) and may_act_sub else None
    client_type = claims.get("client_type")
    has_audience = POLICY_AUDIENCE in audiences
    has_scope = required in scopes
    missing = []
    if not has_audience:
        missing.append(f"the access token's audience does not include {POLICY_AUDIENCE}; the APS refuses a deposit without it")
    if client_type == "agent":
        missing.append("the access token carries client_type agent; the APS accepts a deposit only with a person's token")
    if not has_scope:
        missing.append(
            f"the access token's scope does not include {required}; Keycloak omits this scope when the agent's "
            "service account has no delegate permission over this user, and granting that permission is the operator's step"
        )
    if may_act_sub is None:
        missing.append("the access token has no may_act.sub; the APS refuses a deposit without it")
    report = {
        "agent": agent,
        "tenant": tenant,
        "issuer": claims["iss"],
        "subject": claims["sub"],
        "audiences": audiences,
        "hasPolicyServiceAudience": has_audience,
        "requiredScope": required,
        "hasDelegationScope": has_scope,
        "otherScopes": sorted(s for s in set(scopes) if s != required),
        "mayActSubPresent": may_act_sub is not None,
        "mayActSub": may_act_sub,
        "clientType": client_type if isinstance(client_type, str) else None,
        "accessTokenExpiresInSeconds": max(0, int(claims["exp"] - now)),
        "wouldBeAcceptedForDeposit": not missing,
        "missing": missing,
    }
    if isinstance(claims.get("preferred_username"), str):
        report["preferredUsername"] = claims["preferred_username"]
    return report


def revoke(issuer: str, refresh_token: str) -> bool:
    """Best effort: ask the realm to revoke the refresh token so the sign-in does not outlive the check."""
    try:
        _fetch(issuer + REVOKE_PATH, "revocation endpoint", {"client_id": CLIENT, "token": refresh_token, "token_type_hint": "refresh_token"})
    except ConsentError:
        return False
    return True


def check(
    root: Path,
    agent: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    browser: bool = False,
    issuer: str | None = None,
    is_tty=None,
    say=None,
    open_url=None,
    clock=time.monotonic,
    now=time.time,
) -> tuple[int, dict]:
    tenant = tenant_of(root, agent)
    if not (is_tty or interactive)():
        raise ConsentError("consent is given by a person at their own terminal: stdin, stdout and stderr must all be a TTY")
    if not 0 < timeout <= MAX_TIMEOUT:
        raise ConsentError(f"--timeout must be above 0 and at most {MAX_TIMEOUT:.0f} seconds")
    _pyjwt()  # before the person is asked to sign in, not after
    issuer = issuer or ISSUER
    parsed = urllib.parse.urlsplit(issuer)
    if parsed.scheme != "https" and (parsed.scheme, parsed.hostname) != ("http", "127.0.0.1"):
        raise ConsentError("the issuer must be reached over https")
    say = say or (lambda line: print(line, file=sys.stderr, flush=True))
    scope = required_scope(tenant, agent)
    verifier, challenge = pkce_pair()
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    try:
        listener = socket.create_server(("127.0.0.1", 0), backlog=8)
    except OSError as exc:
        raise ConsentError(f"could not listen on 127.0.0.1 ({type(exc).__name__})") from None
    with listener:
        redirect_uri = f"http://127.0.0.1:{listener.getsockname()[1]}{CALLBACK_PATH}"
        url = authorization_url(issuer, redirect_uri=redirect_uri, scope=scope, state=state, nonce=nonce, challenge=challenge)
        say(f"Consent check for agent {agent} in tenant {tenant}: open this URL, sign in as yourself and answer the consent screen. Nothing is deposited.")
        say(url)
        if browser:
            (open_url or webbrowser.open)(url)
        try:
            request_line = await_callback(listener, timeout, clock)
        except ConsentTimeout:
            return 124, {"agent": agent, "tenant": tenant, "requiredScope": scope, "timedOut": True, "timeoutSeconds": timeout}
    code = callback_code(callback_query(request_line), state)
    tokens = exchange(issuer, code, verifier, redirect_uri)
    try:
        report = assess(verified_claims(issuer, tokens, nonce), tenant, agent, now=now())
    finally:
        revoked = revoke(issuer, tokens["refresh"]) if tokens["refresh"] else None
    report["refreshTokenIssued"] = tokens["refresh"] is not None
    report["refreshTokenRevoked"] = revoked
    return (0 if report["wouldBeAcceptedForDeposit"] else 1), report
