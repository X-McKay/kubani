#!/usr/bin/env python3
"""Operator T10a: real requester=actor exchanges; no credentials enter reports.

Root supplies exact live signed-session Pods. This script creates only ephemeral
pod-bound TokenRequests and IdP tokens; it never creates/deletes Pods or grants.
Root owns ordinary session cleanup. Input/output credentials remain SOPS-only.
Missing authentic negative fixtures produce an incomplete, failing report.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import hashlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "delegation", Path(__file__).with_name("conformance-delegation.py")
)
delegation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(delegation)
human = delegation.human
ACTOR = delegation.ACTOR
RESOURCE = "https://mcp.almckay.io/kubernetes/mcp"
TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
ERRORS = {
    "invalid_request",
    "invalid_client",
    "unauthorized_client",
    "invalid_grant",
    "invalid_scope",
    "invalid_target",
    "access_denied",
    "unsupported_grant_type",
}


def qualified(checks):
    return bool(checks) and all(value is True for value in checks.values())


def refused(status, body):
    return 400 <= status < 500 and body.get("error") in ERRORS


def exchange_form(assertion, actor_token, subject_token, *, actor=ACTOR):
    return {
        "grant_type": GRANT,
        "client_id": actor,
        "client_assertion_type": ASSERTION_TYPE,
        "client_assertion": assertion,
        "subject_token": subject_token,
        "subject_token_type": TOKEN_TYPE,
        "actor_token": actor_token,
        "actor_token_type": TOKEN_TYPE,
        "scope": "mcp:kubernetes",
        "requested_token_type": TOKEN_TYPE,
    }


def claim_checks(claims, alice, actor_sub):
    audience = claims.get("aud")
    if isinstance(audience, str):
        audience = [audience]
    # Pinned delegation copies the exact consent may_act object into act.
    act = claims.get("act")
    return {
        "subject": claims.get("sub") == alice,
        "actor": act == {"sub": actor_sub, "client_id": ACTOR},
        "audience_narrowed": audience == [RESOURCE],
        "authorized_party": claims.get("azp") == ACTOR,
        "scope": claims.get("scope", "").split() == ["mcp:kubernetes"],
    }


class Operator:
    def __init__(self):
        self.api = delegation.Admin()
        self.client = human.opener()
        _, _, raw = human.request(
            self.client, human.ISSUER + "/protocol/openid-connect/certs"
        )
        self.keys = human.jwt.PyJWKSet.from_dict(json.loads(raw))

    def verify(self, token, *, allow_expired=False):
        key = self.keys[human.jwt.get_unverified_header(token)["kid"]].key
        return human.jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=human.ISSUER,
            options={
                "verify_aud": False,
                "verify_exp": not allow_expired,
                "require": ["iss", "sub", "exp", "iat"],
            },
        )

    def post(self, fields):
        req = urllib.request.Request(
            human.ISSUER + "/protocol/openid-connect/token",
            data=urllib.parse.urlencode(fields).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            response = self.client.open(req, timeout=15)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError("oversized IdP response")
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("invalid IdP response")
            return response.code, body

    def subject(self, path, expected_sub):
        stored = human.decrypt(path)
        token = stored.get("access_token", stored.get("token"))
        if not isinstance(token, str):
            raise ValueError("subject fixture lacks access token")
        claims = self.verify(token, allow_expired=True)
        if claims["sub"] != expected_sub or claims.get("azp") != "agent-cli":
            raise ValueError("unexpected subject fixture identity")
        if claims["exp"] <= time.time() + 30:
            if not stored.get("refresh_token"):
                raise ValueError("expired fixture lacks refresh token")
            status, fresh = self.post(
                {
                    "grant_type": "refresh_token",
                    "client_id": "agent-cli",
                    "refresh_token": stored["refresh_token"],
                }
            )
            if status != 200:
                raise ValueError("subject fixture refresh refused")
            token = fresh["access_token"]
            claims = self.verify(token)
            if claims["sub"] != expected_sub or claims.get("azp") != "agent-cli":
                raise ValueError("unexpected refreshed fixture identity")
            # Preserve rotated credentials only in encrypted output, never logs.
            stored.update(
                access_token=token,
                refresh_token=fresh.get("refresh_token", stored["refresh_token"]),
            )
            human.encrypt(
                path, {"fixture": "T10a subject fixture", "stringData": stored}
            )
        self.verify(token)
        return token, claims

    def kubectl(self, args, document=None):
        result = subprocess.run(
            ["kubectl", "--kubeconfig", "/home/al/.kube/config", *args],
            input=json.dumps(document) if document is not None else None,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode:
            raise ValueError("Kubernetes operation refused; details omitted")
        return json.loads(result.stdout)

    def actor(self, agent, pod_name, pod_uid):
        if not re.fullmatch(
            r"[a-z0-9]([-a-z0-9.]*[a-z0-9])?", pod_name
        ) or not re.fullmatch(r"[0-9a-f-]{36}", pod_uid):
            raise ValueError("invalid exact Pod identity")
        namespace = "tenant-test"
        pod = self.kubectl(["get", "pod", pod_name, "-n", namespace, "-o", "json"])
        meta, spec = pod["metadata"], pod["spec"]
        labels = meta.get("labels", {})
        if (
            meta["uid"] != pod_uid
            or meta.get("deletionTimestamp")
            or pod["status"]["phase"] != "Running"
            or spec.get("serviceAccountName") != "agent-" + agent
            or labels.get("agentplatform.io/sandbox") != "true"
            or labels.get("agentplatform.io/agent") != agent
            or not labels.get("agentplatform.io/session")
        ):
            raise ValueError("actor Pod is not the exact running session sandbox")
        assertion = self.kubectl(
            [
                "create",
                "--raw",
                "/api/v1/namespaces/"
                + namespace
                + "/serviceaccounts/agent-"
                + agent
                + "/token",
                "-f",
                "-",
            ],
            {
                "apiVersion": "authentication.k8s.io/v1",
                "kind": "TokenRequest",
                "spec": {
                    "audiences": [human.ISSUER],
                    "expirationSeconds": 300,
                    "boundObjectRef": {
                        "apiVersion": "v1",
                        "kind": "Pod",
                        "name": pod_name,
                        "uid": pod_uid,
                    },
                },
            },
        )["status"]["token"]
        client_id = "agent-" + namespace + "-" + agent
        status, response = self.post(
            {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_assertion_type": ASSERTION_TYPE,
                "client_assertion": assertion,
                "scope": "agent-gateway",
            }
        )
        if status != 200:
            raise ValueError("federated actor authentication refused")
        token = response["access_token"]
        claims = self.verify(token)
        client = self.api.unique_client(client_id)
        sub = self.api.call("clients/" + client["id"] + "/service-account-user")["id"]
        if (
            claims["sub"] != sub
            or claims.get("azp") != client_id
            or claims.get("agent_id") != namespace + "/" + agent
            or claims.get("tenant") != namespace
            or claims.get("client_type") != "agent"
        ):
            raise ValueError("unexpected authenticated actor claims")
        return (
            assertion,
            token,
            sub,
            {
                "namespace": namespace,
                "pod": pod_name,
                "uid": pod_uid,
                "session": labels["agentplatform.io/session"],
                "client_id": client_id,
            },
        )


def run(args, operator=None):
    op = operator or Operator()
    alice = human.decrypt(human.CREDENTIALS)["subject"]
    subject, subject_claims = op.subject(args.subject, alice)
    actor_client = op.api.unique_client(ACTOR)
    actor_sub = op.api.call("clients/" + actor_client["id"] + "/service-account-user")[
        "id"
    ]
    aud = subject_claims.get("aud", [])
    aud = [aud] if isinstance(aud, str) else aud
    if (
        subject_claims.get("may_act") != {"sub": actor_sub, "client_id": ACTOR}
        or ACTOR not in aud
        or "delegation:client:" + ACTOR not in subject_claims.get("scope", "").split()
    ):
        raise ValueError("positive subject lacks exact delegation consent")
    assertion, actor_token, sub, pod = op.actor("conformance", args.pod, args.pod_uid)
    form = exchange_form(assertion, actor_token, subject)
    status, result = op.post(form)
    checks = {"positive_idp_exchange": status == 200}
    evidence = {
        "contract": "revision3 requester=actor",
        "pod": pod,
        "positive_status": status,
    }
    if status == 200:
        claims = op.verify(result["access_token"])
        checks.update(claim_checks(claims, alice, sub))
        evidence["issued_claims"] = {
            k: claims.get(k)
            for k in ("iss", "sub", "act", "aud", "azp", "scope", "iat", "exp")
        }
    else:
        evidence["positive_error"] = (
            result.get("error") if result.get("error") in ERRORS else "unclassified"
        )

    def negative(name, request):
        status, result = op.post(request)
        checks[name] = refused(status, result)
        evidence[name] = {
            "status": status,
            "error": result.get("error")
            if result.get("error") in ERRORS
            else "unclassified",
        }

    ordinary, ordinary_claims = op.subject(args.wrong_consent, alice)
    if ordinary_claims.get("may_act") or any(
        s.startswith("delegation:client:")
        for s in ordinary_claims.get("scope", "").split()
    ):
        raise ValueError("wrong-consent fixture actually has delegation consent")
    negative("wrong_consent", dict(form, subject_token=ordinary))
    negative(
        "wrong_audience",
        dict(form, audience="https://invalid.example.test/t10a-unavailable"),
    )
    if args.wrong_actor_pod and args.wrong_actor_pod_uid:
        other_assertion, other_token, _, other_pod = op.actor(
            "conformance-b", args.wrong_actor_pod, args.wrong_actor_pod_uid
        )
        negative(
            "wrong_actor",
            exchange_form(
                other_assertion,
                other_token,
                subject,
                actor="agent-tenant-test-conformance-b",
            ),
        )
        evidence["wrong_actor_pod"] = other_pod
    else:
        checks["wrong_actor"] = False
        evidence["wrong_actor"] = {"missing": "genuine conformance-b Running sandbox"}
    if args.other_user and args.other_user_sub and args.other_tenant:
        other, other_claims = op.subject(args.other_user, args.other_user_sub)
        # Distinct subject alone is not proof of another tenant. Require signed
        # provenance; no token rewriting or operator assertion substitutes for it.
        if (
            args.other_user_sub == alice
            or args.other_tenant == "tenant-test"
            or other_claims.get("tenant") != args.other_tenant
        ):
            raise ValueError("other-tenant fixture lacks signed tenant provenance")
        negative("wrong_user", dict(form, subject_token=other))
    else:
        checks["wrong_user"] = False
        evidence["wrong_user"] = {
            "missing": "authentic signed other-tenant user fixture"
        }
    checks["authoritative_realm_export"] = False
    if args.realm_export:
        exported = op.api.call(
            "partial-export?exportClients=true&exportGroupsAndRoles=true",
            method="POST",
            payload={},
        )
        if exported.get("realm") != "agents":
            raise ValueError("unexpected exported realm")
        human.encrypt(args.realm_export, exported)
        checks["authoritative_realm_export"] = True
        evidence["realm_export"] = {
            "encrypted_path": str(args.realm_export),
            "sha256": hashlib.sha256(args.realm_export.read_bytes()).hexdigest(),
        }
    return {
        "test": "T10a",
        "qualified": qualified(checks),
        "checks": checks,
        "evidence": evidence,
        "cleanup": "root owns ordinary session cleanup; no sandbox or grant created by this operator",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("subject", "wrong-consent"):
        parser.add_argument(
            "--" + name,
            required=True,
            type=Path,
            help="SOPS .enc.yaml with stringData access_token (and refresh_token if needed)",
        )
    for name in ("pod", "pod-uid"):
        parser.add_argument("--" + name, required=True)
    for name in (
        "wrong-actor-pod",
        "wrong-actor-pod-uid",
        "other-user-sub",
        "other-tenant",
    ):
        parser.add_argument("--" + name)
    parser.add_argument("--other-user", type=Path)
    parser.add_argument(
        "--realm-export",
        type=Path,
        help="read-only realm partial export directly to SOPS ciphertext; required to qualify",
    )
    args = parser.parse_args()
    for path in (args.subject, args.wrong_consent, args.other_user, args.realm_export):
        if path and not str(path).endswith(".enc.yaml"):
            parser.error("credential fixtures must be SOPS .enc.yaml")
    result = run(args)
    print(json.dumps(result, indent=2))
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "test": "T10a",
                    "qualified": False,
                    "error": type(exc).__name__,
                    "details": "sensitive details omitted",
                }
            )
        )
        sys.exit(1)
