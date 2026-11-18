"""The agent registry's HTTP interface, as the operator commands call it.

An agent is owned either by the pull request path (files in git, applied by Flux) or by the registry. This module is
the registry side: settings from the environment, a small JSON client, the read token (a service client's secret read
from a private file) and the person token (a browser sign-in with PKCE, built from the pieces of `delegation`).

No token, secret, authorization code or raw response body reaches a message, a log line or the output. Tokens live in
memory only. Only a registry's own error body is passed on, cut to a fixed length.
"""

from __future__ import annotations

import http.client
import json
import os
import secrets
import socket
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import outcome

from . import delegation

DEFAULT_URL = "https://agents.almckay.io"
DEFAULT_CLUSTER = "kubani"
DEFAULT_SECRET_FILE = "~/.config/kubani/registry-reader.secret"
READER_CLIENT = "registry-reader"
AUDIENCE = "agent-registry"
OPERATOR_ROLE = "registry-operator"
HTTP_TIMEOUT = 30
MAX_RESPONSE = 4 * 1024 * 1024
MAX_MESSAGE = 500


class RegistryError(outcome.Coded):
    """The registry refused, or could not be reached. A registry's own code is passed on; the default is that it did not answer."""

    default_code = "registry-unreachable"


@dataclass(frozen=True)
class Settings:
    url: str
    cluster: str
    secret_file: Path


def settings(env=None) -> Settings:
    env = os.environ if env is None else env
    url = (env.get("KUBANI_REGISTRY_URL") or DEFAULT_URL).rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" and (parsed.scheme, parsed.hostname) != ("http", "127.0.0.1"):
        raise RegistryError("KUBANI_REGISTRY_URL must be an https URL", "invalid-arguments")
    return Settings(url, env.get("KUBANI_REGISTRY_CLUSTER") or DEFAULT_CLUSTER, Path(env.get("KUBANI_REGISTRY_READER_SECRET_FILE") or DEFAULT_SECRET_FILE).expanduser())


def deployment_id(cfg: Settings, tenant: str, agent: str) -> str:
    return f"agent:{cfg.cluster}:{tenant}:{agent}"


def segment(value: str) -> str:
    """One path segment: a deployment id contains colons, which are encoded."""
    return urllib.parse.quote(value, safe="")


def deployment_path(cfg: Settings, tenant: str, agent: str) -> str:
    return f"/v1/deployments/{segment(deployment_id(cfg, tenant, agent))}"


def _cut(text: str) -> str:
    return text if len(text) <= MAX_MESSAGE else text[: MAX_MESSAGE - 3] + "..."


def _registry_error(raw: bytes) -> RegistryError | None:
    """The registry's own error body, or None when the answer is anything else."""
    try:
        doc = json.loads(raw)
    except ValueError:
        return None
    error = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str) or not error["message"]:
        return None
    code = error["code"] if error["code"] in outcome.CODES else "failed"
    return RegistryError(_cut(error["message"]), code)


class Client:
    """JSON over HTTP to the registry with one bearer token. Follows no redirect; every read is bounded."""

    def __init__(self, cfg: Settings, token: str):
        self.cfg, self._token = cfg, token

    def get(self, path: str) -> dict:
        return self._call("GET", path, None)

    def post(self, path: str, body: dict) -> dict:
        return self._call("POST", path, body)

    def _call(self, method: str, path: str, body: dict | None) -> dict:
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self._token}"}
        data = None
        if body is not None:
            data = json.dumps(body, allow_nan=False).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.cfg.url + path, data=data, headers=headers, method=method)
        unreachable = RegistryError(f"the registry at {self.cfg.url} could not be reached or did not answer as expected")
        try:
            with urllib.request.build_opener(delegation._NoRedirect()).open(request, timeout=HTTP_TIMEOUT) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read(MAX_RESPONSE)
            except (OSError, http.client.HTTPException):
                raw = b""
            passed = _registry_error(raw)
            if passed is not None:
                raise passed from None
            if exc.code == 401:
                raise RegistryError("the registry did not accept the sign-in (HTTP 401)", "not-signed-in") from None
            raise RegistryError(f"the registry answered HTTP {exc.code} without an error of its own") from None
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise RegistryError(f"{unreachable} ({type(exc).__name__})") from None
        if len(raw) > MAX_RESPONSE:
            raise unreachable
        try:
            doc = json.loads(raw)
        except ValueError:
            doc = None
        if not isinstance(doc, dict):
            raise unreachable
        return doc


def reader_token(cfg: Settings | None = None, issuer: str | None = None) -> str:
    """A read token from the `registry-reader` client's secret, read from a private file. The secret is never shown."""
    cfg = cfg or settings()
    path = cfg.secret_file
    hint = f"the operator (Al) creates {path} with the registry-reader client secret, readable by its owner only (mode 0600)"
    try:
        info = os.stat(path)
    except OSError:
        raise RegistryError(f"no registry read secret at {path}: {hint}", "not-signed-in") from None
    if not stat.S_ISREG(info.st_mode):
        raise RegistryError(f"{path} is not a regular file: {hint}", "not-signed-in")
    if info.st_mode & 0o077:
        raise RegistryError(f"{path} is readable by group or others: {hint}", "not-signed-in")
    try:
        secret = path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        raise RegistryError(f"{path} could not be read: {hint}", "not-signed-in") from None
    if not secret:
        raise RegistryError(f"{path} is empty: {hint}", "not-signed-in")
    try:
        doc = delegation._json(delegation._fetch((issuer or delegation.ISSUER) + delegation.TOKEN_PATH, "token endpoint", {"grant_type": "client_credentials", "client_id": READER_CLIENT, "client_secret": secret}), "token endpoint")
    except delegation.ConsentError as exc:
        raise RegistryError(f"could not get a registry read token: {exc}", "not-signed-in" if exc.code == "failed" else exc.code) from None
    token = doc.get("access_token")
    if not isinstance(token, str) or not token:
        raise RegistryError("the token endpoint returned no access token for the registry-reader client", "not-signed-in")
    return token


def authorization_url(issuer: str, *, redirect_uri: str, state: str, nonce: str, challenge: str) -> str:
    query = {
        "response_type": "code",
        "client_id": delegation.CLIENT,
        "redirect_uri": redirect_uri,
        "scope": f"openid {AUDIENCE}",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return issuer + delegation.AUTH_PATH + "?" + urllib.parse.urlencode(query)


def check_claims(claims: dict) -> None:
    """The access token must be for the registry and carry the operator role; otherwise no request is made with it."""
    aud = claims.get("aud")
    audiences = [aud] if isinstance(aud, str) else [a for a in (aud if isinstance(aud, list) else []) if isinstance(a, str)]
    access = claims.get("realm_access")
    roles = access.get("roles") if isinstance(access, dict) else None
    problems = []
    if AUDIENCE not in audiences:
        problems.append(f"its audience does not include {AUDIENCE}")
    if not isinstance(roles, list) or OPERATOR_ROLE not in roles:
        problems.append(f"it does not carry the realm role {OPERATOR_ROLE}")
    if problems:
        raise RegistryError("the signed-in token cannot be used for registry changes: " + " and ".join(problems) + "; the operator (Al) grants access in Keycloak", "refused")


def person_tokens(*, timeout: float = delegation.DEFAULT_TIMEOUT, browser: bool = False, issuer: str | None = None, say=None, open_url=None, clock=time.monotonic) -> dict:
    """Take the person at this terminal through a browser sign-in. Returns `access`, their access token, and `refresh`,
    the refresh token Keycloak issued with it or None. Both are held in memory only."""
    if not delegation.interactive():
        raise RegistryError("this command needs a person signed in at a terminal: stdin and stderr must both be a TTY", "not-signed-in")
    delegation.require_pyjwt()
    issuer = issuer or delegation.ISSUER
    parsed = urllib.parse.urlsplit(issuer)
    if parsed.scheme != "https" and (parsed.scheme, parsed.hostname) != ("http", "127.0.0.1"):
        raise RegistryError("the issuer must be reached over https", "invalid-arguments")
    say = say or (lambda line: print(line, file=sys.stderr, flush=True))
    verifier, challenge = delegation.pkce_pair()
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    try:
        listener = socket.create_server(("127.0.0.1", 0), backlog=8)
    except OSError as exc:
        raise RegistryError(f"could not listen on 127.0.0.1 ({type(exc).__name__})", "unavailable") from None
    with listener:
        redirect_uri = f"http://127.0.0.1:{listener.getsockname()[1]}{delegation.CALLBACK_PATH}"
        url = authorization_url(issuer, redirect_uri=redirect_uri, state=state, nonce=nonce, challenge=challenge)
        say("Sign in as yourself to change the agent registry; open this URL:")
        say(url)
        if browser:
            (open_url or webbrowser.open)(url)
        try:
            request_line = delegation.await_callback(listener, timeout, clock)
        except delegation.ConsentTimeout:
            raise RegistryError("nobody signed in before the timeout; nothing was sent to the registry", "timeout") from None
    code = delegation.callback_code(delegation.callback_query(request_line), state)
    tokens = delegation.exchange(issuer, code, verifier, redirect_uri)
    claims = delegation.verified_claims(issuer, tokens, nonce)
    check_claims(claims)
    return {"access": tokens["access"], "refresh": tokens["refresh"]}


def person_token(**kwargs) -> str:
    """The access token of `person_tokens`, for a command that makes its calls at once."""
    return person_tokens(**kwargs)["access"]


def renewed(refresh: str, *, issuer: str | None = None) -> dict | None:
    """Tokens for the refresh token of this command's own sign-in, so that a command that follows a session for longer
    than an access token lasts does not send the person to the browser again. None when Keycloak gives none (the
    person's session ended, or the token was used up): the caller then asks the person to sign in."""
    fields = {"grant_type": "refresh_token", "client_id": delegation.CLIENT, "refresh_token": refresh}
    try:
        doc = delegation._json(delegation._fetch((issuer or delegation.ISSUER) + delegation.TOKEN_PATH, "token endpoint", fields), "token endpoint")
    except delegation.ConsentError:
        return None
    access, newer = doc.get("access_token"), doc.get("refresh_token")
    if not isinstance(access, str) or not access:
        return None
    return {"access": access, "refresh": newer if isinstance(newer, str) and newer else refresh}


def read_client(cfg: Settings | None = None) -> Client:
    cfg = cfg or settings()
    return Client(cfg, reader_token(cfg))


def write_client(cfg: Settings | None = None) -> Client:
    cfg = cfg or settings()
    return Client(cfg, person_token())


# ---- status ------------------------------------------------------------------------------


def status(cfg: Settings | None = None) -> dict:
    """The registry's StatusOut for this cluster, read with the reader token."""
    cfg = cfg or settings()
    return Client(cfg, reader_token(cfg)).get("/v1/status?" + urllib.parse.urlencode({"cluster": cfg.cluster}))


def _age(seconds) -> str:
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return "never"
    seconds = int(seconds)
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def _unknown(row: dict) -> str:
    observation = row.get("observation") or {}
    if observation.get("state") == "fresh":
        return ""
    return f"  unknown (last seen {_age(observation.get('ageSeconds'))})"


def _delivery_lines(a: dict) -> list[str]:
    """What the registry says of a release it delivers: in use, waiting, refused, pinned, revoked and whether the cluster has the last change."""
    current, candidate, refused = a.get("current"), a.get("candidate"), a.get("lastRefused")
    lines = [f"      in use: {current['release']} (revision {current.get('revision')}){' admitted by ' + current['admittedBy'] if current.get('admittedBy') else ''}" if current else "      in use: no current release"]
    if candidate:
        evaluation = candidate.get("evaluation")
        lines.append(f"      candidate: {candidate.get('release')} (revision {candidate.get('revision')}) {candidate.get('phase')}: {candidate.get('reason') or 'no reason given'}" + (f"; evaluation attempt {evaluation.get('attempt')} {evaluation.get('state')}" if evaluation else ""))
    if refused:
        verdict = refused.get("evaluation")
        lines.append(f"      last refused: {refused.get('release')} (revision {refused.get('revision')}): {refused.get('reason')}" + (f"; evaluation {verdict.get('verdict')}: {verdict.get('summary')}" if verdict else ""))
    if a.get("pinned") is not None:
        lines.append(f"      pinned: revision {a['pinned']}")
    lines += [f"      revoked: {r.get('release')} ({r.get('reason')}, {r.get('id')})" for r in a.get("revoked") or []]
    acknowledged = a.get("acknowledged")
    lines.append("      cluster: " + {True: "has taken the last change", False: "has not taken the last change yet"}.get(acknowledged, "not known"))
    return lines


def format_status(doc: dict) -> str:
    lines = [f"cluster {doc.get('cluster')}  mode {doc.get('mode')}  generation {doc.get('generation')}", "", "Agents"]
    for a in doc.get("agents") or []:
        ready = {True: "ready", False: "not ready"}.get(a.get("ready"), "ready unknown")
        lines.append(f"  {a.get('agent')} ({a.get('tenant')})  {a.get('authority')}  current {a.get('currentRelease') or '-'}  newest {a.get('newestRelease') or '-'}  phase {a.get('phase') or '-'}  {ready}{_unknown(a)}")
        if a.get("authority") == "registry":
            lines += _delivery_lines(a)
        lines += [f"      blocker: {b}" for b in a.get("blockers") or []]
        lines += [f"      next: {n}" for n in a.get("nextActions") or []]
    if not doc.get("agents"):
        lines.append("  none")
    lines += ["", "Tool servers"]
    for t in doc.get("toolServers") or []:
        lines.append(f"  {t.get('name')}  {'registered' if t.get('registered') else 'unregistered'}  {t.get('declaredImage')}  {'pinned' if t.get('pinnedByDigest') else 'not pinned'}{_unknown(t)}")
    if not doc.get("toolServers"):
        lines.append("  none")
    lines += ["", "Models"]
    for m in doc.get("models") or []:
        lines.append(f"  {m.get('name')}  {', '.join(m.get('aliases') or []) or '-'}  serves {m.get('observedServedName') or m.get('declaredServedName')}{_unknown(m)}")
    if not doc.get("models"):
        lines.append("  none")
    return "\n".join(lines)
