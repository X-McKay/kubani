"""T10a verdicts require authentic refusals and exact issuer-verified claims."""

import importlib.util
import unittest
from pathlib import Path

PATH = (
    Path(__file__).resolve().parents[1]
    / "infrastructure/scripts/ops/conformance-delegation-contract.py"
)
SPEC = importlib.util.spec_from_file_location("contract", PATH)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


class ContractTests(unittest.TestCase):
    def test_exact_delegated_claims_and_no_extra_resource(self):
        claims = {
            "sub": "alice",
            "act": {"sub": "agent-sub", "client_id": contract.ACTOR},
            "aud": [contract.RESOURCE],
            "azp": contract.ACTOR,
            "scope": "mcp:kubernetes",
        }
        self.assertTrue(
            all(contract.claim_checks(claims, "alice", "agent-sub").values())
        )
        for field, value in [
            ("sub", "bob"),
            ("act", {"sub": "wrong"}),
            ("aud", [contract.RESOURCE, "other"]),
            ("azp", "other"),
            ("scope", "mcp:kubernetes mcp:other"),
            ("act", {"sub": "agent-sub"}),
        ]:
            with self.subTest(field=field):
                self.assertFalse(
                    all(
                        contract.claim_checks(
                            dict(claims, **{field: value}), "alice", "agent-sub"
                        ).values()
                    )
                )

    def test_refusal_requires_oauth_4xx_not_transport_or_local_exception(self):
        self.assertEqual(
            contract.refusal_reason(
                "wrong_audience",
                400,
                {"error": "invalid_client", "error_description": "Audience not found"},
            ),
            "audience_not_found",
        )
        for status, body in [
            (200, {}),
            (500, {"error": "server_error"}),
            (401, {}),
            (0, {"error": "transport"}),
            (302, {"error": "invalid_request"}),
        ]:
            self.assertIsNone(contract.refusal_reason("wrong_audience", status, body))

    def test_wrong_audience_is_not_a_local_jwt_edit(self):
        form = contract.exchange_form("assertion", "actor-token", "subject-token")
        self.assertEqual(form["client_id"], contract.ACTOR)
        self.assertEqual(form["actor_token"], "actor-token")
        self.assertEqual(form["subject_token"], "subject-token")
        self.assertNotIn("audience", form)
        self.assertEqual(form["scope"], "mcp:kubernetes")

    def test_missing_case_cannot_qualify(self):
        self.assertFalse(contract.qualified({"positive": True, "wrong_user": False}))
        self.assertFalse(contract.qualified({}))

    def test_jwks_verification_rejects_tampered_expired_and_wrong_issuer(self):
        import time
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = contract.human.jwt.algorithms.RSAAlgorithm.to_jwk(
            key.public_key(), as_dict=True
        )
        public.update(kid="test-key", alg="RS256")
        op = contract.Operator.__new__(contract.Operator)
        op.keys = contract.human.jwt.PyJWKSet.from_dict({"keys": [public]})
        claims = {
            "iss": contract.human.ISSUER,
            "sub": "alice",
            "iat": int(time.time()) - 5,
            "exp": int(time.time()) + 60,
        }

        def signed(payload):
            return contract.human.jwt.encode(
                payload, key, algorithm="RS256", headers={"kid": "test-key"}
            )

        self.assertEqual(op.verify(signed(claims))["sub"], "alice")
        for bad in [
            dict(claims, iss="https://other.invalid"),
            dict(claims, exp=int(time.time()) - 1),
        ]:
            with self.assertRaises(contract.human.jwt.InvalidTokenError):
                op.verify(signed(bad))
        parts = signed(claims).split(".")
        import base64
        import json

        parts[1] = (
            base64.urlsafe_b64encode(json.dumps(dict(claims, sub="bob")).encode())
            .rstrip(b"=")
            .decode()
        )
        with self.assertRaises(contract.human.jwt.InvalidSignatureError):
            op.verify(".".join(parts))

    def test_missing_authentic_inputs_and_export_keep_report_unqualified(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        class API:
            def unique_client(self, name):
                return {"id": "client-id"}

            def call(self, path):
                return {"id": "actor-sub"}

        class Operator:
            api = API()
            calls = []

            def subject(self, path, subject):
                if path == "positive":
                    return "positive-subject", {
                        "aud": [contract.ACTOR, "agent-policy-service"],
                        "may_act": {"sub": "actor-sub", "client_id": contract.ACTOR},
                        "scope": "agent-policy-service delegation:client:"
                        + contract.ACTOR,
                    }
                return "ordinary-subject", {"scope": "openid profile"}

            def actor(self, *args):
                return (
                    "bound-assertion",
                    "actor-token",
                    "actor-sub",
                    {
                        "uid": "exact-uid",
                        "assertion_expires_at": __import__("time").time() + 300,
                    },
                )

            def post(self, form):
                self.calls.append(form)
                if (
                    form.get("subject_token") == "ordinary-subject"
                    or "audience" in form
                ):
                    return 400, {
                        "error": "invalid_client"
                        if "audience" in form
                        else "invalid_request",
                        "error_description": "Audience not found"
                        if "audience" in form
                        else "Invalid may_act claim in the subject_token",
                    }
                return 200, {"access_token": "issued-token"}

            def current(self, token):
                return self.verify(token)

            def verify(self, token):
                return {
                    "sub": "alice",
                    "act": {"sub": "actor-sub", "client_id": contract.ACTOR},
                    "aud": [contract.RESOURCE],
                    "azp": contract.ACTOR,
                    "scope": "mcp:kubernetes",
                }

        op = Operator()
        args = SimpleNamespace(
            subject="positive",
            wrong_consent="ordinary",
            pod="pod",
            pod_uid="uid",
            wrong_actor_pod=None,
            wrong_actor_pod_uid=None,
            other_user=None,
            other_user_sub=None,
            other_tenant=None,
            realm_export=None,
        )
        with patch.object(contract.human, "decrypt", return_value={"subject": "alice"}):
            report = contract.run(args, op)
        self.assertFalse(report["qualified"])
        self.assertTrue(report["checks"]["positive_idp_exchange"])
        self.assertFalse(report["checks"]["wrong_user"])
        self.assertFalse(report["checks"]["wrong_actor"])
        self.assertFalse(report["checks"]["authoritative_realm_export"])
        self.assertEqual(op.calls[0]["actor_token"], "actor-token")
        self.assertEqual(op.calls[2]["subject_token"], "ordinary-subject")
        self.assertIn("audience", op.calls[5])
        import json

        rendered = json.dumps(report)
        for secret in (
            "bound-assertion",
            "actor-token",
            "positive-subject",
            "issued-token",
        ):
            self.assertNotIn(secret, rendered)
