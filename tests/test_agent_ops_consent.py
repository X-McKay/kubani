"""`just agent consent --check`: an in-process fake IdP on loopback; no real IdP, credentials or cluster."""

from __future__ import annotations

import ast
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
from agent_ops import delegation, layout  # noqa: E402

_spec = importlib.util.spec_from_file_location("agent_ops_cli", OPS / "agent-ops.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

REALM = "/realms/agents"
# The command never calls this; the fake serves it so a call would be recorded.
REVOKE_PATH = "/protocol/openid-connect/revoke"
SCOPE = "delegation:client:agent-tenant-test-sample"
AGENT_TEXT = """apiVersion: agentplatform.io/v1alpha1
kind: Agent
metadata:
  name: sample
  namespace: tenant-test
spec:
  owner: owner@example.invalid
  description: Sample
  identity:
    mode: %s
"""
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_root(tmp: Path, mode: str = "on-behalf-of") -> Path:
    root = tmp / "repo"
    d = root / layout.AGENTS_DIR / "tenant-test/sample"
    d.mkdir(parents=True)
    (d / "agent.yaml").write_text(AGENT_TEXT % mode, encoding="utf-8")
    return root


class FakeIdp:
    """Token, JWKS and revocation endpoints of one realm; the test plays the authorization endpoint and the browser."""

    def __init__(self):
        idp = self
        self.calls: list[tuple[str, dict]] = []
        self.codes: dict[str, dict] = {}
        self.issued: list[str] = []
        self.verifiers: list[str] = []
        self.revoked: list[dict] = []
        self.mutate = lambda claims: None
        self.signing_key = KEY
        self.refresh = True
        self.revoke_status = 200

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status: int, doc: dict) -> None:
                body = json.dumps(doc).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                idp.calls.append((self.path, {}))
                if self.path != REALM + delegation.CERTS_PATH:
                    return self.reply(404, {"error": "not_found"})
                jwk = jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True)
                self.reply(200, {"keys": [dict(jwk, kid="k1", use="sig", alg="RS256")]})

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
                fields = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
                idp.calls.append((self.path, fields))
                if self.path == REALM + delegation.TOKEN_PATH:
                    return self.reply(*idp.token(fields))
                if self.path == REALM + REVOKE_PATH:
                    idp.revoked.append(fields)
                    return self.reply(idp.revoke_status, {})
                self.reply(404, {"error": "not_found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.issuer = f"http://127.0.0.1:{self.server.server_address[1]}{REALM}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def sign(self, claims: dict) -> str:
        token = jwt.encode(claims, self.signing_key, algorithm="RS256", headers={"kid": "k1"})
        self.issued.append(token)
        return token

    def authorize(self, params: dict) -> str:
        """What the authorization endpoint would do after sign-in and consent: bind a one-time code to the request."""
        code = "code-" + secrets.token_urlsafe(24)
        self.issued.append(code)
        self.codes[code] = params
        return code

    def token(self, fields: dict) -> tuple[int, dict]:
        bound = self.codes.pop(fields.get("code", ""), None)
        verifier = fields.get("code_verifier", "")
        self.verifiers.append(verifier)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if (
            bound is None
            or fields.get("grant_type") != "authorization_code"
            or fields.get("client_id") != delegation.CLIENT
            or fields.get("redirect_uri") != bound["redirect_uri"]
            or bound["code_challenge_method"] != "S256"
            or challenge != bound["code_challenge"]
        ):
            return 400, {"error": "invalid_grant", "error_description": "body that must not be echoed"}
        now = int(time.time())
        base = {"iss": self.issuer, "sub": "user-1", "exp": now + 300, "iat": now}
        access = dict(
            base,
            aud=["agent-policy-service"],
            azp=delegation.CLIENT,
            typ="Bearer",
            scope=bound["scope"],
            preferred_username="person",
            may_act={"sub": "service-account-agent-tenant-test-sample"},
        )
        identity = dict(base, aud=delegation.CLIENT, nonce=bound["nonce"])
        self.mutate({"access": access, "id": identity})
        doc = {"access_token": self.sign(access), "id_token": self.sign(identity), "token_type": "Bearer", "expires_in": 300}
        if self.refresh:
            doc["refresh_token"] = self.sign(dict(base, typ="Refresh", aud=self.issuer))
        return 200, doc


class Browser:
    """Stands in for the person's browser: reads the URL, asks the fake IdP for a code, follows the loopback redirect."""

    def __init__(self, idp: FakeIdp, *, state=None, error=None, target=None):
        self.idp, self.state, self.error, self.target = idp, state, error, target
        self.params: dict = {}
        self.sockets: list[socket.socket] = []
        self.opened = 0

    def __call__(self, url: str) -> None:
        self.opened += 1
        parsed = urllib.parse.urlsplit(url)
        assert url.startswith(self.idp.issuer + delegation.AUTH_PATH + "?"), url
        self.params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        redirect = urllib.parse.urlsplit(self.params["redirect_uri"])
        query = {"state": self.state or self.params["state"]}
        if self.error:
            query["error"] = self.error
        else:
            query["code"] = self.idp.authorize(self.params)
        target = self.target or f"{redirect.path}?{urllib.parse.urlencode(query)}"
        # The listener is already bound, so the request waits in its backlog until the command accepts it.
        conn = socket.create_connection((redirect.hostname, redirect.port), timeout=5)
        conn.sendall(f"GET {target} HTTP/1.1\r\nHost: {redirect.netloc}\r\n\r\n".encode())
        self.sockets.append(conn)

    def close(self) -> None:
        for conn in self.sockets:
            conn.close()


class ConsentCase(unittest.TestCase):
    def setUp(self):
        self.idp = FakeIdp()
        self.addCleanup(self.idp.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = make_root(self.tmp)
        self.said: list[str] = []

    def browser(self, **kwargs) -> Browser:
        browser = Browser(self.idp, **kwargs)
        self.addCleanup(browser.close)
        return browser

    def check(self, browser=None, **kwargs):
        kwargs.setdefault("is_tty", lambda: True)
        kwargs.setdefault("root", self.root)
        root = kwargs.pop("root")
        return delegation.check(root, "sample", issuer=self.idp.issuer, say=self.said.append, browser=browser is not None, open_url=browser, **kwargs)

    def paths(self) -> list[str]:
        return [path.removeprefix(REALM) for path, _ in self.idp.calls]


class VerdictTests(ConsentCase):
    def test_accepted_token_reports_metadata_and_revokes_nothing(self):
        browser = self.browser()
        code, report = self.check(browser)
        self.assertEqual(code, 0)
        self.assertEqual(
            report,
            {
                "agent": "sample",
                "tenant": "tenant-test",
                "issuer": self.idp.issuer,
                "subject": "user-1",
                "preferredUsername": "person",
                "audiences": ["agent-policy-service"],
                "hasPolicyServiceAudience": True,
                "requiredScope": SCOPE,
                "hasDelegationScope": True,
                "otherScopes": ["agent-policy-service", "openid"],
                "mayActSubPresent": True,
                "mayActSub": "service-account-agent-tenant-test-sample",
                "clientType": None,
                "undecodableClaims": [],
                "accessTokenExpiresInSeconds": report["accessTokenExpiresInSeconds"],
                "refreshTokenIssued": True,
                "wouldBeAcceptedForDeposit": True,
                "missing": [],
            },
        )
        self.assertTrue(290 <= report["accessTokenExpiresInSeconds"] <= 300)
        self.assertEqual(self.paths(), [delegation.TOKEN_PATH, delegation.CERTS_PATH])
        self.assertEqual(self.idp.revoked, [])

    def test_authorization_request_is_pkce_s256_with_fresh_login_and_consent_and_no_offline_access(self):
        browser = self.browser()
        self.check(browser)
        p = browser.params
        self.assertEqual(p["response_type"], "code")
        self.assertEqual(p["client_id"], "agent-cli")
        self.assertEqual(p["scope"].split(), ["openid", "agent-policy-service", SCOPE])
        self.assertEqual(p["code_challenge_method"], "S256")
        self.assertEqual(p["prompt"], delegation.PROMPT)
        self.assertEqual(delegation.PROMPT.split(), ["login", "consent"])
        self.assertRegex(p["redirect_uri"], r"^http://127\.0\.0\.1:\d+/callback$")
        self.assertGreaterEqual(len(p["state"]), 32)
        self.assertGreaterEqual(len(p["nonce"]), 32)
        self.assertNotEqual(p["state"], p["nonce"])
        self.assertEqual(len(self.said), 2)
        self.assertIn("agent sample in tenant tenant-test", self.said[0])
        self.assertEqual(urllib.parse.urlsplit(self.said[1]).query, urllib.parse.urlencode(p))

    def test_dropped_scope_exits_1_and_names_the_delegate_permission(self):
        self.idp.mutate = lambda t: t["access"].update(scope="openid agent-policy-service")
        code, report = self.check(self.browser())
        self.assertEqual(code, 1)
        self.assertFalse(report["hasDelegationScope"])
        self.assertFalse(report["wouldBeAcceptedForDeposit"])
        self.assertEqual(len(report["missing"]), 1)
        self.assertIn(SCOPE, report["missing"][0])
        self.assertIn("A likely cause is that the agent's service account has no delegate permission over this user", report["missing"][0])
        self.assertIn("the operator's step to grant", report["missing"][0])
        self.assertEqual(self.idp.revoked, [])

    def test_scope_must_match_a_whole_scope_name(self):
        for scope in (SCOPE + "-other", "x" + SCOPE, SCOPE.upper()):
            with self.subTest(scope=scope):
                self.idp.mutate = lambda t, s=scope: t["access"].update(scope=f"openid agent-policy-service {s}")
                code, report = self.check(self.browser())
                self.assertEqual(code, 1)
                self.assertFalse(report["hasDelegationScope"])

    def test_single_string_audience_is_accepted(self):
        self.idp.mutate = lambda t: t["access"].update(aud="agent-policy-service")
        code, report = self.check(self.browser())
        self.assertEqual(code, 0)
        self.assertEqual(report["audiences"], ["agent-policy-service"])
        self.assertTrue(report["hasPolicyServiceAudience"])

    def test_claim_of_a_type_the_aps_cannot_decode_exits_1(self):
        cases = {
            "client_type": ["agent"],
            "tenant": ["a", "b"],
            "agent_id": 7,
            "spiffe_id": {"x": 1},
            "azp": ["agent-cli"],
            "act": "someone",
            "aud": ["agent-policy-service", 7],
            "iat": "1700000000",
            "nbf": "1700000000",
        }
        for name, value in cases.items():
            with self.subTest(claim=name):
                self.idp.mutate = lambda t, n=name, v=value: t["access"].update({n: v})
                code, report = self.check(self.browser())
                self.assertEqual(code, 1)
                self.assertEqual(report["undecodableClaims"], [name])
                self.assertFalse(report["wouldBeAcceptedForDeposit"])
                self.assertEqual(len(report["missing"]), 1)
                self.assertIn(f"the access token's {name} is not of the JSON type the APS decodes", report["missing"][0])
        self.idp.mutate = lambda t: t["access"].update(may_act={"sub": 7}, scope=["openid"])
        code, report = self.check(self.browser())
        self.assertEqual((code, report["undecodableClaims"]), (1, ["may_act", "scope"]))
        self.idp.mutate = lambda t: t["access"].update(client_type=None, tenant=None, act=None, may_act={"sub": "s", "extra": 1})
        code, report = self.check(self.browser())
        self.assertEqual((code, report["undecodableClaims"]), (0, []), "the APS decodes a null as an absent claim")

    def test_expiry_that_is_not_a_json_number_exits_1_without_a_traceback(self):
        self.idp.mutate = lambda t: t["access"].update(exp=str(t["access"]["exp"]))
        code, report = self.check(self.browser())
        self.assertEqual((code, report["undecodableClaims"]), (1, ["exp"]))
        self.assertIsNone(report["accessTokenExpiresInSeconds"])
        self.assertFalse(report["wouldBeAcceptedForDeposit"])

    def test_null_audience_is_listed_as_undecodable(self):
        self.idp.mutate = lambda t: t["access"].update(aud=None)
        code, report = self.check(self.browser())
        self.assertEqual((code, report["undecodableClaims"], report["hasPolicyServiceAudience"]), (1, ["aud"], False))
        self.assertEqual(delegation.undecodable({"iat": None, "nbf": None, "exp": 1.5}), [])
        self.assertEqual(delegation.undecodable({"exp": True}), ["exp"])

    def test_missing_may_act_exits_1(self):
        for value in (None, {}, {"sub": ""}, {"sub": None}):
            with self.subTest(value=value):
                self.idp.mutate = (lambda t: t["access"].pop("may_act")) if value is None else (lambda t, v=value: t["access"].update(may_act=v))
                code, report = self.check(self.browser())
                self.assertEqual(code, 1)
                self.assertFalse(report["mayActSubPresent"])
                self.assertIsNone(report["mayActSub"])
                self.assertEqual(len(report["missing"]), 1)
                self.assertIn("may_act.sub", report["missing"][0])
                self.assertIn("no delegate permission over this user", report["missing"][0])

    def test_wrong_audience_exits_1(self):
        for aud in (["account"], "agent-gateway", None):
            with self.subTest(aud=aud):
                self.idp.mutate = lambda t, a=aud: t["access"].pop("aud") if a is None else t["access"].update(aud=a)
                code, report = self.check(self.browser())
                self.assertEqual(code, 1)
                self.assertFalse(report["hasPolicyServiceAudience"])
                self.assertEqual(len(report["missing"]), 1)
                self.assertIn("audience does not include agent-policy-service", report["missing"][0])

    def test_agent_client_type_exits_1(self):
        self.idp.mutate = lambda t: t["access"].update(client_type="agent")
        code, report = self.check(self.browser())
        self.assertEqual(code, 1)
        self.assertEqual(report["clientType"], "agent")
        self.assertEqual(len(report["missing"]), 1)
        self.assertIn("client_type agent", report["missing"][0])

    def test_every_missing_condition_is_listed(self):
        def strip(t):
            t["access"].update(aud="account", scope="openid", client_type="agent")
            t["access"].pop("may_act")

        self.idp.mutate = strip
        code, report = self.check(self.browser())
        self.assertEqual(code, 1)
        self.assertEqual(len(report["missing"]), 4)

    def test_absent_refresh_token_is_reported(self):
        self.idp.refresh = False
        code, report = self.check(self.browser())
        self.assertEqual(code, 0)
        self.assertFalse(report["refreshTokenIssued"])
        self.assertNotIn("refreshTokenRevoked", report)
        self.assertEqual(self.idp.revoked, [])

    def test_clock_difference_within_the_aps_leeway_is_accepted(self):
        self.assertEqual(delegation.LEEWAY_SECONDS, 5)
        self.idp.mutate = lambda t: t["access"].update(iat=int(time.time()) + 3)
        self.assertEqual(self.check(self.browser())[0], 0)
        self.idp.mutate = lambda t: t["access"].update(exp=int(time.time()) - 2)
        code, report = self.check(self.browser())
        self.assertEqual((code, report["accessTokenExpiresInSeconds"]), (0, 0))


class RefusalTests(ConsentCase):
    def refused(self, browser=None, **kwargs) -> str:
        with self.assertRaises(delegation.ConsentError) as caught:
            self.check(browser, **kwargs)
        return str(caught.exception)

    def test_bad_signature_is_refused_and_nothing_is_revoked(self):
        self.idp.signing_key = OTHER_KEY
        self.assertIn("access token failed verification", self.refused(self.browser()))
        self.assertEqual(self.idp.revoked, [])

    def test_only_the_realm_signing_algorithm_is_accepted(self):
        self.assertEqual(delegation.ALGORITHMS, ("RS256",))
        forged = {
            "HS256": lambda claims: jwt.encode(claims, "k" * 48, algorithm="HS256", headers={"kid": "k1"}),
            "none": lambda claims: jwt.encode(claims, None, algorithm="none", headers={"kid": "k1"}),
            "RS512": lambda claims: jwt.encode(claims, KEY, algorithm="RS512", headers={"kid": "k1"}),
        }
        for name, sign in forged.items():
            with self.subTest(alg=name), patch.object(self.idp, "sign", sign):
                message = self.refused(self.browser())
                self.assertIn("access token failed verification", message)
                self.assertIn("InvalidAlgorithmError", message)
        curve = ec.generate_private_key(ec.SECP256R1())
        jwk = dict(jwt.algorithms.ECAlgorithm.to_jwk(curve.public_key(), as_dict=True), kid="e1", use="sig", alg="ES256")
        token = jwt.encode({"iss": "https://idp.example.invalid/realms/agents", "sub": "u", "exp": int(time.time()) + 60}, curve, algorithm="ES256", headers={"kid": "e1"})
        with patch.object(delegation, "_fetch", lambda url, what, fields=None: json.dumps({"keys": [jwk]}).encode()), self.assertRaises(delegation.ConsentError) as caught:
            delegation.verified_claims("https://idp.example.invalid/realms/agents", {"access": token, "id": token, "refresh": None}, "n")
        self.assertIn("InvalidAlgorithmError", str(caught.exception))

    def test_token_without_an_expiry_or_a_subject_is_refused(self):
        for claim in ("exp", "sub", "iss"):
            with self.subTest(claim=claim):
                self.idp.mutate = lambda t, c=claim: t["access"].pop(c)
                self.assertIn("MissingRequiredClaimError", self.refused(self.browser()))
        self.idp.mutate = lambda t: t["access"].update(iat=int(time.time()) + 60)
        self.assertIn("ImmatureSignatureError", self.refused(self.browser()))

    def test_wrong_issuer_is_refused(self):
        self.idp.mutate = lambda t: t["access"].update(iss=self.idp.issuer.replace("agents", "other"))
        message = self.refused(self.browser())
        self.assertIn("access token failed verification", message)
        self.assertIn("InvalidIssuerError", message)
        self.assertEqual(self.idp.revoked, [])

    def test_expired_and_unknown_key_tokens_are_refused(self):
        self.idp.mutate = lambda t: t["access"].update(exp=int(time.time()) - 60)
        self.assertIn("ExpiredSignatureError", self.refused(self.browser()))
        self.idp.mutate = lambda t: None
        with patch.object(self.idp, "sign", lambda claims: jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "k2"})):
            self.assertIn("KeyError", self.refused(self.browser()))

    def test_id_token_from_another_sign_in_is_refused(self):
        self.idp.mutate = lambda t: t["id"].update(nonce="replayed")
        self.assertIn("ID token does not belong to this sign-in", self.refused(self.browser()))
        self.idp.mutate = lambda t: t["id"].update(sub="user-2")
        self.assertIn("ID token does not belong to this sign-in", self.refused(self.browser()))
        self.idp.mutate = lambda t: t["id"].update(aud="another-client")
        self.assertIn("ID token failed verification", self.refused(self.browser()))

    def test_state_mismatch_is_refused_before_any_exchange(self):
        for state in ("attacker-chosen", ""):
            with self.subTest(state=state):
                browser = self.browser(state=state or None)
                if not state:
                    browser.target = "/callback?code=x"
                self.assertIn("state does not match", self.refused(browser))
        self.assertEqual(self.idp.calls, [])

    def test_state_is_checked_before_anything_else_in_the_callback(self):
        cases = {
            "repeated": {"state": ["s", "s"], "code": ["c"]},
            "repeated with another": {"state": ["s", "t"], "code": ["c"]},
            "absent": {"code": ["c"]},
            "wrong beside an error": {"state": ["t"], "error": ["access_denied"]},
            "absent beside an error": {"error": ["access_denied"]},
        }
        for name, query in cases.items():
            with self.subTest(case=name), self.assertRaises(delegation.ConsentError) as caught:
                delegation.callback_code(query, "s")
            self.assertIn("state does not match", str(caught.exception), name)
        self.assertEqual(delegation.callback_code({"state": ["s"], "code": ["c"]}, "s"), "c")
        for query in ({"state": ["s"]}, {"state": ["s"], "code": [""]}, {"state": ["s"], "code": ["c", "d"]}):
            with self.assertRaises(delegation.ConsentError) as caught:
                delegation.callback_code(query, "s")
            self.assertIn("no authorization code", str(caught.exception))

    def test_error_callback_is_refused_naming_the_code(self):
        self.assertIn("returned the error access_denied", self.refused(self.browser(error="access_denied")))
        message = self.refused(self.browser(error="<script>alert(1)</script>"))
        self.assertIn("(unprintable)", message)
        self.assertNotIn("script", message)
        self.assertEqual(self.idp.calls, [])

    def test_anything_but_the_callback_is_refused(self):
        for target in ("/favicon.ico", "/callback/x?code=c&state=s", "//[x", "http://[::1/callback?code=c&state=s"):
            with self.subTest(target=target):
                self.assertIn("not the sign-in callback", self.refused(self.browser(target=target)))
        self.assertEqual(self.idp.calls, [])

    def test_token_endpoint_refusal_names_the_code_and_omits_the_body(self):
        browser = self.browser()
        with patch.object(self.idp, "authorize", lambda params: "code-unknown-to-the-idp"), self.assertRaises(delegation.ConsentError) as caught:
            self.check(browser)
        self.assertEqual(str(caught.exception), "the token endpoint answered HTTP 400 (invalid_grant)")
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__, "the HTTP error and its body are not chained to the refusal")
        self.assertEqual(self.idp.revoked, [])

    def test_unreachable_endpoint_is_refused_without_a_chained_error(self):
        with self.assertRaises(delegation.ConsentError) as caught:
            delegation._fetch("http://127.0.0.1:1/x", "token endpoint", {"code": "c"})
        self.assertIn("could not be reached", str(caught.exception))
        self.assertTrue(caught.exception.__cause__ is None and caught.exception.__suppress_context__)

    def test_listener_is_bound_to_loopback_only(self):
        bound = []
        real = socket.create_server

        def recording(address, **kwargs):
            bound.append(address)
            return real(address, **kwargs)

        with patch.object(delegation.socket, "create_server", recording):
            self.check(self.browser())
        self.assertEqual(bound, [("127.0.0.1", 0)])

    def test_connection_that_sends_nothing_is_skipped(self):
        with socket.create_server(("127.0.0.1", 0)) as listener:
            port = listener.getsockname()[1]

            def visit():
                socket.create_connection(("127.0.0.1", port)).close()
                with socket.create_connection(("127.0.0.1", port)) as conn:
                    conn.sendall(b"GET /callback?code=c&state=s HTTP/1.1\r\n\r\n")
                    conn.recv(65536)

            visitor = threading.Thread(target=visit)
            visitor.start()
            self.addCleanup(visitor.join)
            line = delegation.await_callback(listener, 10, time.monotonic)
        self.assertEqual(line, b"GET /callback?code=c&state=s HTTP/1.1")

    def test_listener_failure_is_a_refusal(self):
        class Broken:
            def settimeout(self, value):
                pass

            def accept(self):
                raise OSError("too many open files")

        with self.assertRaises(delegation.ConsentError) as caught:
            delegation.await_callback(Broken(), 5, time.monotonic)
        self.assertIn("loopback listener failed (OSError)", str(caught.exception))

    def test_timeout_exits_124_without_waiting_and_closes_the_listener(self):
        opened = []
        started = time.monotonic()
        code, report = delegation.check(self.root, "sample", issuer=self.idp.issuer, is_tty=lambda: True, say=self.said.append, open_url=opened.append, clock=iter([0, 1000]).__next__)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(code, 124)
        self.assertEqual(report, {"agent": "sample", "tenant": "tenant-test", "requiredScope": SCOPE, "timedOut": True, "timeoutSeconds": 300.0})
        self.assertEqual(opened, [], "the browser is not opened unless asked")
        self.assertEqual(self.idp.calls, [])
        redirect = urllib.parse.urlsplit(urllib.parse.parse_qs(urllib.parse.urlsplit(self.said[1]).query)["redirect_uri"][0])
        with self.assertRaises(OSError):
            socket.create_connection((redirect.hostname, redirect.port), timeout=2).close()

    def test_listener_is_closed_after_the_single_request(self):
        browser = self.browser()
        self.check(browser)
        redirect = urllib.parse.urlsplit(browser.params["redirect_uri"])
        with self.assertRaises(OSError):
            socket.create_connection((redirect.hostname, redirect.port), timeout=2).close()

    def test_without_a_tty_nothing_is_started(self):
        browser = self.browser()
        with patch.object(delegation.socket, "create_server", lambda *a, **k: self.fail("a listener was bound before the TTY check")):
            self.assertIn("must all be a TTY", self.refused(browser, is_tty=lambda: False))
        self.assertEqual((browser.opened, self.said, self.idp.calls), (0, [], []))
        for stream in ("stdin", "stdout", "stderr"):
            with self.subTest(stream=stream), patch.object(sys, stream, io.StringIO()):
                self.assertFalse(delegation.interactive())

    def test_agent_identity_mode_is_refused_before_the_tty_check(self):
        root = make_root(self.tmp / "other", mode="agent")
        browser = self.browser()
        message = self.refused(browser, root=root, is_tty=lambda: self.fail("the TTY check ran"))
        self.assertIn("declares identity mode 'agent'", message)
        self.assertEqual((browser.opened, self.said, self.idp.calls), (0, [], []))
        with self.assertRaises(layout.LayoutError):
            delegation.check(self.root, "absent", is_tty=lambda: True)

    def test_missing_pyjwt_is_refused_before_the_person_is_asked_to_sign_in(self):
        with patch.dict(sys.modules, {"jwt": None}):
            self.assertIn("PyJWT is not installed", self.refused(self.browser()))
        self.assertEqual((self.said, self.idp.calls), ([], []))

    def test_timeout_bounds_and_plain_http_issuers_are_refused(self):
        for timeout in (0, -1, delegation.MAX_TIMEOUT + 1):
            self.assertIn("--timeout", self.refused(timeout=timeout))
        with self.assertRaises(delegation.ConsentError):
            delegation.check(self.root, "sample", issuer="http://idp.example.invalid/realms/agents", is_tty=lambda: True, say=self.said.append)
        self.assertEqual(self.said, [])


class CommandTests(ConsentCase):
    """Through `agent-ops.py` itself, with the live issuer, the TTY check and the browser replaced."""

    def run_cli(self, argv, browser):
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(delegation, "ISSUER", self.idp.issuer),
            patch.object(delegation, "interactive", lambda: True),
            patch.object(delegation.webbrowser, "open", browser),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_exit_codes_and_one_json_document(self):
        code, out, err = self.run_cli(["consent", "--check", "sample", "--browser"], self.browser())
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["wouldBeAcceptedForDeposit"])
        self.assertIn(self.idp.issuer + delegation.AUTH_PATH, err)
        self.idp.mutate = lambda t: t["access"].update(scope="openid")
        code, out, _ = self.run_cli(["consent", "--check", "sample", "--browser"], self.browser())
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)["wouldBeAcceptedForDeposit"])
        code, out, err = self.run_cli(["consent", "--check", "sample", "--browser"], self.browser(error="access_denied"))
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err.splitlines()[-1], "refused: Keycloak returned the error access_denied instead of an authorization code")

    def test_without_check_the_command_refuses_and_starts_nothing(self):
        browser = self.browser()
        code, out, err = self.run_cli(["consent", "sample", "--browser"], browser)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("refused: depositing a consented token is not implemented", err)
        self.assertEqual((browser.opened, self.idp.calls), (0, []))

    def test_real_tty_check_refuses_under_a_test_runner(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(delegation, "ISSUER", self.idp.issuer), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--root", str(self.root), "consent", "--check", "sample", "--timeout", "1"])
        self.assertEqual((code, out.getvalue()), (2, ""))
        self.assertIn("must all be a TTY", err.getvalue())
        self.assertEqual(self.idp.calls, [])

    def test_nothing_secret_reaches_stdout_stderr_or_a_file(self):
        home = self.tmp / "home"
        home.mkdir()
        scenarios = {
            "accepted": {},
            "scope dropped": {"mutate": lambda t: t["access"].update(scope="openid")},
            "bad signature": {"key": OTHER_KEY},
            "wrong issuer": {"mutate": lambda t: t["access"].update(iss="https://other.invalid/realms/agents")},
            "state mismatch": {"browser": {"state": "attacker-chosen"}},
            "denied": {"browser": {"error": "access_denied"}},
            "unknown code": {"authorize": lambda params: "code-" + "u" * 32},
        }
        captured = []
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(home)
        with patch.dict(os.environ, {"HOME": str(home), "XDG_STATE_HOME": str(home / "state"), "XDG_CACHE_HOME": str(home / "cache"), "TMPDIR": str(home)}):
            for name, scenario in scenarios.items():
                self.idp.mutate = scenario.get("mutate", lambda t: None)
                self.idp.signing_key = scenario.get("key", KEY)
                browser = self.browser(**scenario.get("browser", {}))
                with patch.object(self.idp, "authorize", scenario.get("authorize", self.idp.authorize)):
                    code, out, err = self.run_cli(["consent", "--check", "sample", "--browser"], browser)
                captured.append((name, code, out, err))
        self.assertEqual([code for _, code, _, _ in captured], [0, 1, 2, 2, 2, 2, 2])
        secrets_seen = set(self.idp.issued) | set(self.idp.verifiers) | {"code-" + "u" * 32}
        for token in [t for t in self.idp.issued if t.count(".") == 2]:
            secrets_seen.update(token.split("."))
        secrets_seen.discard("")
        self.assertGreaterEqual(len(self.idp.verifiers), 3)
        self.assertGreaterEqual(len(secrets_seen), 20)
        files = [p for p in self.tmp.rglob("*") if p.is_file()]
        self.assertEqual([p.relative_to(self.tmp).as_posix() for p in files], ["repo/infrastructure/gitops/apps/agents/tenant-test/sample/agent.yaml"])
        haystacks = [(f"{name} {stream}", text) for name, _, out, err in captured for stream, text in (("stdout", out), ("stderr", err))]
        haystacks += [(str(p), p.read_bytes().decode("utf-8", "replace")) for p in files]
        for where, text in haystacks:
            for secret in secrets_seen:
                self.assertNotIn(secret, text, where)
        for name, code, out, _ in captured:
            if code in (0, 1):
                self.assertEqual(set(json.loads(out)) & {"scope", "token", "access_token", "id_token", "refresh_token", "code", "code_verifier", "state", "nonce"}, set(), name)


class ModuleShapeTests(unittest.TestCase):
    def test_module_needs_no_pyjwt_at_import_and_touches_no_cluster_or_aps(self):
        source = (OPS / "agent_ops/delegation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                top.add((node.module or ".").split(".")[0])
        self.assertNotIn("jwt", top)
        self.assertEqual(top & {"subprocess", "os", "shutil", "tempfile", "logging"}, set())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertEqual(names & {"open", "input", "live", "Kube"}, set(), "no file is opened, nothing is typed in, no cluster read")
        self.assertEqual(attributes & {"write_text", "write_bytes", "Kube", "getpass"}, set())
        strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n is not tree.body[0].value]
        self.assertFalse([s for s in strings if "/v1/grants" in s or "kubectl" in s or "offline_access" in s or "password" in s or "/revoke" in s])


if __name__ == "__main__":
    unittest.main()
