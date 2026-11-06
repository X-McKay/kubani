import importlib.util
from pathlib import Path

import pytest

path = (
    Path(__file__).parents[1]
    / "infrastructure/scripts/ops/conformance-delegation-contract.py"
)
spec = importlib.util.spec_from_file_location("strict_contract", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.mark.parametrize(
    "case", ["wrong_consent", "wrong_actor", "wrong_audience", "wrong_user"]
)
@pytest.mark.parametrize(
    "status,body",
    [
        (
            400,
            {
                "error": "invalid_client",
                "error_description": "Invalid client credentials",
            },
        ),
        (400, {"error": "invalid_request", "error_description": "Invalid actor token"}),
        (400, {"error": "invalid_request", "error_description": "Invalid token"}),
        (429, {"error": "invalid_request"}),
        (400, {"error": "invalid_scope"}),
    ],
)
def test_generic_auth_expiry_rate_limit_or_unclassified_error_is_not_negative_evidence(
    case, status, body
):
    assert m.refusal_reason(case, status, body) is None


def test_pinned_wrong_audience_reason_does_not_confuse_invalid_client_auth():
    assert (
        m.refusal_reason(
            "wrong_audience",
            400,
            {"error": "invalid_client", "error_description": "Audience not found"},
        )
        == "audience_not_found"
    )
    assert (
        m.refusal_reason(
            "wrong_consent",
            400,
            {"error": "invalid_client", "error_description": "Audience not found"},
        )
        is None
    )


def test_pinned_may_act_and_requester_audience_refusals_are_exact():
    assert (
        m.refusal_reason(
            "wrong_consent",
            400,
            {
                "error": "invalid_request",
                "error_description": "Invalid may_act claim in the subject_token",
            },
        )
        == "missing_consent"
    )
    assert (
        m.refusal_reason(
            "wrong_actor",
            400,
            {
                "error": "invalid_request",
                "error_description": "Actor user is not allowed by the may_act claim inside the subject_token",
            },
        )
        == "actor_not_consented"
    )
    assert (
        m.refusal_reason(
            "wrong_user",
            403,
            {
                "error": "access_denied",
                "error_description": "Client is not within the token audience",
            },
        )
        == "requester_not_audience"
    )


@pytest.mark.parametrize("bad_auth", [False, True, "control"])
def test_each_negative_gets_fresh_auth_and_bracketed_positive_controls(
    monkeypatch, bad_auth
):
    import json
    import time
    from types import SimpleNamespace as NS

    class API:
        def unique_client(self, name):
            return {"id": "client"}

        def call(self, path):
            return {"id": "actor-sub"}

    class Op:
        api = API()

        def __init__(self):
            self.auth = 0
            self.calls = []

        def subject(self, path, sub):
            if path == "positive":
                return "positive", {
                    "aud": [m.ACTOR, "agent-policy-service"],
                    "may_act": {"sub": "actor-sub", "client_id": m.ACTOR},
                    "scope": "agent-policy-service delegation:client:" + m.ACTOR,
                }
            return path, {"scope": "openid profile", "tenant": "tenant-other"}

        def actor(self, agent, *args):
            self.auth += 1
            return (
                "assertion-" + str(self.auth),
                "actor-" + str(self.auth),
                "actor-sub",
                {
                    "client_id": "agent-tenant-test-" + agent,
                    "assertion_expires_at": int(time.time()) + 300,
                },
            )

        def verify(self, token):
            return {
                "sub": "alice",
                "act": {"sub": "actor-sub", "client_id": m.ACTOR},
                "aud": [m.RESOURCE],
                "azp": m.ACTOR,
                "scope": "mcp:kubernetes",
            }

        current = verify

        def post(self, form):
            self.calls.append(dict(form))
            negative = (
                form.get("subject_token") in {"ordinary", "other"}
                or "audience" in form
                or form.get("client_id") != m.ACTOR
            )
            if not negative:
                if bad_auth == "control" and len(self.calls) > 1:
                    return 401, {"error": "invalid_client"}
                return 200, {"access_token": "issued"}
            if bad_auth:
                return 400, {
                    "error": "invalid_client",
                    "error_description": "Invalid client credentials",
                }
            if "audience" in form:
                return 400, {
                    "error": "invalid_client",
                    "error_description": "Audience not found",
                }
            if form["client_id"] != m.ACTOR:
                return 400, {
                    "error": "invalid_request",
                    "error_description": "Actor user is not allowed by the may_act claim inside the subject_token",
                }
            return 400, {
                "error": "invalid_request",
                "error_description": "Invalid may_act claim in the subject_token",
            }

    monkeypatch.setattr(m.human, "decrypt", lambda path: {"subject": "alice"})
    op = Op()
    args = NS(
        subject="positive",
        wrong_consent="ordinary",
        pod="pod",
        pod_uid="uid",
        wrong_actor_pod="otherpod",
        wrong_actor_pod_uid="otheruid",
        other_user="other",
        other_user_sub="bob",
        other_tenant="tenant-other",
        realm_export=None,
    )
    report = m.run(args, op)
    assert op.auth == (
        5 if bad_auth == "control" else 6
    )  # initial positive + four per-case controls + genuine other actor
    for case in ["wrong_consent", "wrong_actor", "wrong_audience", "wrong_user"]:
        assert report["checks"][case] is (not bad_auth)
        if bad_auth == "control":
            assert report["evidence"][case]["negative_sent"] is False
        else:
            assert (
                report["evidence"][case]["positive_before"]
                and report["evidence"][case]["positive_after"]
            )
    assert len(op.calls) == (5 if bad_auth == "control" else 13)
    if bad_auth != "control":
        assert len({op.calls[i]["client_assertion"] for i in [1, 4, 7, 10]}) == 4
    rendered = json.dumps(report)
    assert (
        "assertion-" not in rendered
        and "actor-1" not in rendered
        and "issued" not in rendered.replace("issued_claims", "claims")
    )


def test_actual_urlencoded_transport_preserves_each_request_variant():
    import json
    import urllib.parse

    class Response:
        code = 400

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, bound):
            return json.dumps({"error": "invalid_request"}).encode()

    class Client:
        def __init__(self):
            self.requests = []

        def open(self, request, timeout):
            self.requests.append(request)
            return Response()

    op = m.Operator.__new__(m.Operator)
    op.client = Client()
    base = m.exchange_form("assertion", "actor-token", "subject-token")
    for form in [
        base,
        dict(base, subject_token="ordinary"),
        dict(base, audience=m.BAD_AUDIENCE),
        m.exchange_form(
            "other-assertion",
            "other-actor",
            "subject-token",
            actor="agent-tenant-test-conformance-b",
        ),
    ]:
        op.post(form)
        request = op.client.requests[-1]
        actual = {
            k: v[0]
            for k, v in urllib.parse.parse_qs(
                request.data.decode(), strict_parsing=True
            ).items()
        }
        assert actual == form
        assert request.full_url == m.human.ISSUER + "/protocol/openid-connect/token"
