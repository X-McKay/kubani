"""Synthetic approved execution only: no network, SOPS or genuine mint."""

import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from test_conformance_other_tenant import complete_snapshot

PATH = (
    Path(__file__).resolve().parents[1]
    / "infrastructure/scripts/ops/conformance-other-tenant-execution.py"
)
SPEC = importlib.util.spec_from_file_location("bob_exec", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class FakeAdmin:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.profile = copy.deepcopy(snapshot["profile"])
        self.created_scope = False
        self.created_user = False
        self.attached = False
        self.mutations = []
        self.sid, self.subject = str(UUID(int=50)), str(UUID(int=51))
        self.fail = None

    def call(self, path, method="GET", body=None):
        if method != "GET":
            self.mutations.append((method, path))
            if self.fail == path:
                raise TimeoutError("SENSITIVE_REMOTE_BODY")
            if path == "users/profile":
                self.profile = copy.deepcopy(body)
            elif path == "client-scopes":
                self.created_scope = True
            elif "/optional-client-scopes/" in path:
                self.attached = True
            elif path == "users":
                self.created_user = True
            else:
                raise AssertionError(path)
            return None
        if path == "users/profile":
            return copy.deepcopy(self.profile)
        if path == "client-scopes":
            return (
                [{"id": self.sid, "name": module.planner.SCOPE}]
                if self.created_scope
                else []
            )
        if path == "client-scopes/" + self.sid:
            return {**copy.deepcopy(module.planner.SCOPE_BODY), "id": self.sid}
        if path == "client-scopes/" + self.sid + "/protocol-mappers/models":
            return [
                {
                    **copy.deepcopy(module.planner.SCOPE_BODY["protocolMappers"][0]),
                    "id": str(UUID(int=52)),
                }
            ]
        if path.endswith("/optional-client-scopes"):
            return (
                [{"id": self.sid, "name": module.planner.SCOPE}]
                if self.attached
                else []
            )
        if path.endswith("/default-client-scopes"):
            return copy.deepcopy(self.snapshot["clients"][0]["default_scopes"])
        if path.startswith("users?username="):
            return [{"id": self.subject}] if self.created_user else []
        if path == "users/" + self.subject:
            return {**copy.deepcopy(module.planner.plan_user()), "id": self.subject}
        if path.endswith("/groups"):
            return []
        if path == "clients?clientId=account":
            return [self.snapshot["account_client"]]
        if path.endswith("/role-mappings"):
            return {}
        raise AssertionError(path)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = complete_snapshot()
        self.approved = module.planner.plan(self.snapshot)
        self.api = FakeAdmin(self.snapshot)

    def test_wrong_digest_or_missing_ack_refused_before_admin(self):
        with patch.object(module, "Admin", side_effect=AssertionError("admin")):
            for digest, ack in [("wrong", True), (self.approved["plan_sha256"], False)]:
                with self.assertRaises(ValueError):
                    module.execute(
                        self.approved, digest, "/unused", exclusive_writer=ack
                    )

    def execute(self, directory):
        return module.execute(
            self.approved,
            self.approved["plan_sha256"],
            Path(directory) / "receipt.json",
            exclusive_writer=True,
            api=self.api,
        )

    def test_only_four_approved_mutations_and_no_plaintext_custody(self):
        encrypted = []
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(module, "CREDENTIALS", Path(directory) / "encrypted.enc.yaml"),
            patch.object(module, "collect", return_value=self.snapshot),
            patch.object(
                module.human,
                "encrypt",
                side_effect=lambda path, doc: encrypted.append(copy.deepcopy(doc)),
            ),
        ):
            receipt = self.execute(directory)
            self.assertEqual(receipt["state"], "provisioned")
            self.assertEqual(
                [m[0] for m in self.api.mutations], ["PUT", "POST", "PUT", "POST"]
            )
            text = (Path(directory) / "receipt.json").read_text()
            self.assertNotIn(encrypted[0]["stringData"]["password"], text)
            self.assertEqual(encrypted[-1]["stringData"]["subject"], self.api.subject)
            with self.assertRaises(ValueError):
                self.execute(directory)

    def test_fresh_read_mismatch_refuses_all_mutations(self):
        changed = copy.deepcopy(self.snapshot)
        changed["profile"]["groups"].append({"name": "concurrent"})
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(module, "CREDENTIALS", Path(directory) / "encrypted.enc.yaml"),
            patch.object(module, "collect", return_value=changed),
        ):
            with self.assertRaises(ValueError):
                self.execute(directory)
        self.assertEqual(self.api.mutations, [])

    def test_ambiguous_mutation_retains_failed_receipt_and_never_retries(self):
        self.api.fail = "client-scopes"
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(module, "CREDENTIALS", Path(directory) / "encrypted.enc.yaml"),
            patch.object(module, "collect", return_value=self.snapshot),
        ):
            with self.assertRaises(RuntimeError) as error:
                self.execute(directory)
            text = (Path(directory) / "receipt.json").read_text()
            self.assertIn("TimeoutError", text)
            self.assertNotIn("SENSITIVE_REMOTE_BODY", text + str(error.exception))
            self.assertEqual(len(self.api.mutations), 2)

    def test_mint_missing_provenance_refused_before_admin(self):
        with patch.object(module, "Admin", side_effect=AssertionError("admin")):
            with self.assertRaises(ValueError):
                module.mint({}, "wrong")

    def test_access_claims_reject_privilege_identity_and_scope_variants(self):
        baseline = {
            "sub": str(UUID(int=51)),
            "tenant": "tenant-other",
            "scope": module.MINT_SCOPE,
            "aud": ["account"],
            "realm_access": {"roles": ["default-roles-agents"]},
        }
        receipt = {
            "new_user_uuid": baseline["sub"],
            "default_scope_names": ["email", "roles"],
        }
        module.verify_access(baseline, receipt)
        for field, value in [
            ("tenant", ["tenant-other"]),
            ("tenant", "tenant-test"),
            ("sub", str(UUID(int=6))),
            ("may_act", {}),
            ("act", {}),
            ("scope", module.MINT_SCOPE + " delegation:client:actor"),
            ("scope", "openid profile"),
            ("aud", ["backend"]),
            ("realm_access", {"roles": ["realm-admin"]}),
            ("resource_access", {"backend": {"roles": ["read"]}}),
            ("unexpected_admin_claim", True),
        ]:
            access = copy.deepcopy(baseline)
            access[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                module.verify_access(access, receipt)
        baseline["scope"] += " email roles"
        module.verify_access(baseline, receipt)

    def test_real_signed_pkce_transport_checks_state_nonce_subject_expiry_and_signature(
        self,
    ):
        import base64
        import json
        import time
        from urllib.parse import parse_qs, urlsplit
        from cryptography.hazmat.primitives.asymmetric import rsa

        human = module.human
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = key.public_key().public_numbers()

        def encoded(number):
            return (
                base64.urlsafe_b64encode(
                    number.to_bytes((number.bit_length() + 7) // 8, "big")
                )
                .rstrip(b"=")
                .decode()
            )

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "synthetic",
                    "alg": "RS256",
                    "use": "sig",
                    "n": encoded(public.n),
                    "e": encoded(public.e),
                }
            ]
        }
        subject = str(UUID(int=51))
        credentials = {
            "subject": subject,
            "username": module.planner.USERNAME,
            "password": "synthetic-never-live",
        }
        for fault in (
            None,
            "state",
            "nonce",
            "subject",
            "expiry",
            "signature",
            "username",
            "azp",
            "type",
        ):
            observed = {}

            def request(client, url, fields=None, **kwargs):
                if "/auth?" in url:
                    query = parse_qs(urlsplit(url).query)
                    observed.update({k: v[0] for k, v in query.items()})
                    self.assertEqual(observed["scope"], module.MINT_SCOPE)
                    self.assertEqual(observed["code_challenge_method"], "S256")
                    return (
                        200,
                        {},
                        b'<form id="kc-form-login" action="/realms/agents/login-actions/authenticate"></form>',
                    )
                if "/login-actions/authenticate" in url:
                    self.assertEqual(fields["username"], module.planner.USERNAME)
                    state = "wrong" if fault == "state" else observed["state"]
                    return (
                        302,
                        {
                            "Location": human.CALLBACK
                            + "?state="
                            + state
                            + "&code=synthetic"
                        },
                        b"",
                    )
                if url.endswith("/token"):
                    self.assertEqual(
                        human.pkce_challenge(fields["code_verifier"]),
                        observed["code_challenge"],
                    )
                    now = int(time.time())
                    claims = {
                        "iss": human.ISSUER,
                        "sub": str(UUID(int=52)) if fault == "subject" else subject,
                        "iat": now - 5,
                        "exp": now - 1 if fault == "expiry" else now + 300,
                    }
                    access = {
                        **claims,
                        "azp": "wrong" if fault == "azp" else "agent-cli",
                        "preferred_username": "wrong"
                        if fault == "username"
                        else module.planner.USERNAME,
                        "typ": "wrong" if fault == "type" else "Bearer",
                    }
                    identity = {
                        **claims,
                        "aud": "agent-cli",
                        "nonce": "wrong" if fault == "nonce" else observed["nonce"],
                    }
                    signer = wrong_key if fault == "signature" else key
                    tokens = {
                        name: human.jwt.encode(
                            value,
                            signer,
                            algorithm="RS256",
                            headers={"kid": "synthetic"},
                        )
                        for name, value in [
                            ("access_token", access),
                            ("id_token", identity),
                        ]
                    }
                    return 200, {}, json.dumps(tokens).encode()
                if url.endswith("/certs"):
                    return 200, {}, json.dumps(jwks).encode()
                raise AssertionError("unexpected fixed transport destination")

            with (
                self.subTest(fault=fault),
                patch.object(human, "request", side_effect=request),
            ):
                if fault:
                    with self.assertRaises((ValueError, human.jwt.PyJWTError)):
                        human.pkce_tokens(
                            credentials, module.MINT_SCOPE, module.planner.USERNAME
                        )
                else:
                    tokens, claims = human.pkce_tokens(
                        credentials, module.MINT_SCOPE, module.planner.USERNAME
                    )
                    self.assertEqual(claims["sub"], subject)

    def test_bounded_collector_reads_associations_and_matches_safe_projection(self):
        source = self.snapshot

        class ReadOnlyApi:
            count = 0

            def call(self, path, method="GET", body=None, server=False):
                self.count += 1
                if method != "GET" or body is not None:
                    raise AssertionError("mutation")
                if server:
                    return {"systemInfo": {"version": source["version"]}}
                if path == "users/profile":
                    return source["profile"]
                if path == "":
                    return source["realm"]
                if path.startswith("clients?first="):
                    return (
                        [source["agent_cli"], source["account_client"]]
                        if "first=0&" in path
                        else []
                    )
                if path == "client-scopes":
                    return source["scopes"]
                if path.startswith("users?username="):
                    return []
                if path.startswith("users?briefRepresentation=false&"):
                    return source["users"] if "first=0&" in path else []
                if path.startswith("users/"):
                    return {"attributes": {}}
                if path == "default-groups":
                    return []
                for scope in source["scopes"]:
                    if (
                        path
                        == "client-scopes/" + scope["id"] + "/protocol-mappers/models"
                    ):
                        return scope["mappers"]
                for client in source["clients"]:
                    prefix = "clients/" + client["id"]
                    for suffix, field in [
                        ("/default-client-scopes", "default_scopes"),
                        ("/optional-client-scopes", "optional_scopes"),
                        ("/protocol-mappers/models", "mappers"),
                    ]:
                        if path == prefix + suffix:
                            return client[field]
                for rid, node in source["default_roles"].items():
                    if path == "roles-by-id/" + rid:
                        return node["role"]
                    if path == "roles-by-id/" + rid + "/composites":
                        return node["composites"]
                raise AssertionError(path)

        api = ReadOnlyApi()
        collected = module.collect(api)
        self.assertTrue(module.planner.plan(collected)["approval_ready"])
        self.assertEqual(collected["profile"], source["profile"])
        self.assertEqual(collected["default_roles"], source["default_roles"])
        self.assertEqual(collected["clients"], source["clients"])
        self.assertGreater(api.count, 10)
