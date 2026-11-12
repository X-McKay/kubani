"""keycloak_admin: the shared Keycloak admin REST client, with a stub opener and no network or SOPS."""

from __future__ import annotations

import http.client
import io
import json
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
import keycloak_admin  # noqa: E402

BODY_MARKER = "RESPONSE-BODY-MARKER-do-not-show"
ADMIN_BASE = keycloak_admin.ORIGIN + "/admin/realms/agents/"


class Response:
    """What `opener.open` returns: a context manager with a size-limited read."""

    def __init__(self, raw=b"{}", code=200, headers=None):
        self.raw, self.code, self.headers = raw, code, headers or {}
        self.limits = []

    def read(self, limit=-1):
        self.limits.append(limit)
        return self.raw if limit < 0 else self.raw[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Client:
    """A stub opener that records every request and answers from a queue (an exception is raised, a Response returned)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append((req, timeout))
        answer = self.answers.pop(0) if self.answers else Response()
        if isinstance(answer, BaseException):
            raise answer
        return answer


def http_error(code, url="https://idp.almckay.io/x"):
    return urllib.error.HTTPError(url, code, "REASON-MARKER-do-not-show", {}, io.BytesIO(BODY_MARKER.encode()))


def admin(client, **kwargs):
    with patch.object(keycloak_admin, "admin_client", return_value=(client, "bearer-token")):
        return keycloak_admin.Admin(**kwargs)


class AdminCall(unittest.TestCase):
    def test_a_get_goes_to_the_agents_realm_with_the_bearer_and_the_timeout(self):
        client = Client(Response(b'[{"clientId": "a"}]'))
        result = admin(client, timeout=7).call("clients?clientId=a")
        self.assertEqual(result, [{"clientId": "a"}])
        ((req, timeout),) = client.requests
        self.assertEqual((req.full_url, req.get_method(), timeout), (ADMIN_BASE + "clients?clientId=a", "GET", 7))
        self.assertEqual(req.get_header("Authorization"), "Bearer bearer-token")
        self.assertIsNone(req.data)

    def test_server_info_is_the_one_other_destination(self):
        client = Client()
        admin(client).call("ignored", server=True)
        self.assertEqual(client.requests[0][0].full_url, keycloak_admin.ORIGIN + "/admin/serverinfo")

    def test_allowed_methods_are_exactly_get_put_and_post(self):
        self.assertEqual(keycloak_admin.METHODS, frozenset({"GET", "PUT", "POST"}))
        for method in ("GET", "PUT", "POST"):
            with self.subTest(method=method):
                client = Client(Response(b""))
                payload = {"enabled": True} if method != "GET" else None
                self.assertIsNone(admin(client).call("clients/1", method, payload))
                req = client.requests[0][0]
                self.assertEqual(req.get_method(), method)
                if payload:
                    self.assertEqual((json.loads(req.data), req.get_header("Content-type")), (payload, "application/json"))
        for method in ("DELETE", "PATCH", "HEAD", "get", "", None):
            with self.subTest(method=method):
                client = Client()
                api = admin(client)
                with self.assertRaisesRegex(ValueError, "invalid admin request"):
                    api.call("clients/1", method)
                self.assertEqual((client.requests, api.count), ([], 0), "a refused request is neither sent nor counted")

    def test_path_validation(self):
        for path in ("/admin/realms/master", "/x", "a/../../master", "..", "clients#fragment"):
            with self.subTest(path=path):
                client = Client()
                with self.assertRaisesRegex(ValueError, "invalid admin request"):
                    admin(client).call(path)
                self.assertEqual(client.requests, [])
        # Whatever the path holds, the request stays under the realm prefix on the identity provider's origin.
        for path in ("@evil.example/x", "x?next=https://evil.example/", "x/%2e%2e"):
            with self.subTest(path=path):
                client = Client()
                admin(client).call(path)
                url = client.requests[0][0].full_url
                self.assertTrue(url.startswith(ADMIN_BASE), url)
                self.assertEqual(urllib.parse.urlsplit(url).netloc, "idp.almckay.io")

    def test_request_budget_counts_each_call_and_refuses_the_one_past_it(self):
        client = Client()
        api = admin(client, budget=2)
        api.call("a")
        api.call("b")
        with self.assertRaisesRegex(ValueError, "admin request budget exhausted"):
            api.call("c")
        self.assertEqual(len(client.requests), 2)
        unlimited = admin(Client(), budget=None)
        for _ in range(5):
            unlimited.call("a")
        self.assertEqual(unlimited.count, 5)

    def test_response_is_read_with_a_cap_and_one_byte_over_is_refused(self):
        cap = keycloak_admin.MAX_RESPONSE
        exact = Response(b" " * (cap - 2) + b"{}")
        self.assertEqual(admin(Client(exact)).call("a"), {})
        self.assertEqual(exact.limits, [cap + 1], "the read asks for at most one byte more than the cap")
        over = Response(b" " * cap + b"{}")
        with self.assertRaisesRegex(ValueError, "size budget exhausted"):
            admin(Client(over)).call("a")
        self.assertEqual(over.limits, [cap + 1])

    def test_http_error_carries_the_status_and_never_the_response(self):
        for code in (400, 403, 409, 500, 503):
            with self.subTest(code=code):
                with self.assertRaises(keycloak_admin.KeycloakHTTPError) as caught:
                    admin(Client(http_error(code))).call("a")
                exc = caught.exception
                self.assertIsInstance(exc, RuntimeError)
                self.assertEqual((exc.status, str(exc)), (code, f"Keycloak admin HTTP {code}; response omitted"))
                for hidden in (BODY_MARKER, "REASON-MARKER"):
                    self.assertNotIn(hidden, str(exc) + repr(exc) + repr(exc.args))
                self.assertTrue(exc.__suppress_context__, "the original error is not chained into a traceback")

    def test_redirects_are_not_followed(self):
        with self.assertRaises(keycloak_admin.KeycloakHTTPError) as caught:
            admin(Client(http_error(302))).call("a")
        self.assertEqual(caught.exception.status, 302)


class Request(unittest.TestCase):
    def test_only_the_identity_providers_https_origin_is_a_destination(self):
        for url in (
            "http://idp.almckay.io/realms/master",
            "https://idp.almckay.io.evil.example/realms/master",
            "https://evil.example/realms/master",
            "https://idp.almckay.io@evil.example/realms/master",
            "https://idp.almckay.io:8443/realms/master",
            "ftp://idp.almckay.io/x",
            "//idp.almckay.io/x",
            "file:///etc/passwd",
            "",
        ):
            with self.subTest(url=url):
                client = Client()
                with self.assertRaisesRegex(ValueError, "untrusted HTTP destination"):
                    keycloak_admin.request(client, url)
                self.assertEqual(client.requests, [])
        client = Client(Response(b"ok", code=200))
        code, _, raw = keycloak_admin.request(client, keycloak_admin.ORIGIN + "/realms/master", {"a": "b"}, bearer="t")
        self.assertEqual((code, raw), (200, b"ok"))
        req = client.requests[0][0]
        self.assertEqual((req.data, req.get_header("Authorization")), (b"a=b", "Bearer t"))

    def test_http_error_carries_the_status_and_never_the_response(self):
        for code in (401, 403, 404, 500):
            with self.subTest(code=code):
                with self.assertRaises(keycloak_admin.KeycloakHTTPError) as caught:
                    keycloak_admin.request(Client(http_error(code)), keycloak_admin.ORIGIN + "/x")
                exc = caught.exception
                self.assertEqual((exc.status, str(exc)), (code, f"Keycloak HTTP {code}; response omitted"))
                self.assertNotIn(BODY_MARKER, str(exc) + repr(exc))
                self.assertNotIn("REASON-MARKER", str(exc) + repr(exc))

    def test_a_login_redirect_is_an_answer_not_an_error(self):
        for code in (302, 303):
            with self.subTest(code=code):
                answer = http_error(code)
                got, _, raw = keycloak_admin.request(Client(answer), keycloak_admin.ORIGIN + "/x")
                self.assertEqual((got, raw), (code, BODY_MARKER.encode()))


class Opener(unittest.TestCase):
    """The real opener, over a fake transport: a redirect is handed back, never followed."""

    def test_redirect_handler_refuses_to_build_a_second_request(self):
        self.assertIsNone(keycloak_admin.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.example/"))

    def test_opener_does_not_follow_a_redirect_to_another_host(self):
        seen = []

        class Transport(urllib.request.HTTPSHandler):
            def https_open(self, req):
                seen.append(req.full_url)
                raw = b"HTTP/1.1 302 Found\r\nLocation: https://evil.example/steal\r\nContent-Length: 0\r\n\r\n"

                class Sock:
                    def makefile(self, *args, **kwargs):
                        return io.BytesIO(raw)

                response = http.client.HTTPResponse(Sock())
                response.begin()
                response.msg = response.reason
                return response

        with patch.object(urllib.request, "HTTPSHandler", Transport):
            client = keycloak_admin.opener()
            code, headers, _ = keycloak_admin.request(client, keycloak_admin.ORIGIN + "/realms/master/login")
        self.assertEqual((code, seen), (302, [keycloak_admin.ORIGIN + "/realms/master/login"]))
        self.assertEqual(headers["Location"], "https://evil.example/steal")

    def test_the_opener_has_no_redirect_following_and_keeps_cookies(self):
        client = keycloak_admin.opener()
        handlers = [type(h) for h in client.handlers]
        self.assertIn(keycloak_admin.NoRedirect, handlers)
        self.assertNotIn(urllib.request.HTTPRedirectHandler, handlers)
        self.assertIn(urllib.request.HTTPCookieProcessor, handlers)


if __name__ == "__main__":
    unittest.main()
