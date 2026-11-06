#!/usr/bin/env python3
"""Operator T10a: real requester=actor exchanges; no credentials enter reports.

Root supplies exact live signed-session Pods. This script creates only ephemeral
pod-bound TokenRequests and IdP tokens; it never creates/deletes Pods or grants.
Root owns ordinary session cleanup. Input/output credentials remain SOPS-only.
Missing authentic negative fixtures produce an incomplete, failing report.
"""

from __future__ import annotations

import argparse
import copy
import uuid
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


BAD_AUDIENCE = "https://invalid.example.test/t10a-unavailable"


def refusal_reason(case, status, body):
    """Exact pinned 26.8.1 branches; auth/expiry/rate limits never qualify."""
    if (
        type(status) is not int
        or not isinstance(body, dict)
        or not isinstance(body.get("error"), str)
        or not isinstance(body.get("error_description"), str)
    ):
        return None
    key = (status, body["error"], body["error_description"])
    common = {
        (
            400,
            "invalid_request",
            "Invalid may_act claim in the subject_token",
        ): "missing_consent",
        (
            403,
            "access_denied",
            "Client is not within the token audience",
        ): "requester_not_audience",
    }
    allowed = (
        dict(common) if case in {"wrong_consent", "wrong_user", "wrong_actor"} else {}
    )
    if case == "wrong_actor":
        allowed.update(
            {
                (
                    400,
                    "invalid_request",
                    "Actor user is not allowed by the may_act claim inside the subject_token",
                ): "actor_not_consented",
                (
                    400,
                    "invalid_request",
                    "Actor token client does not match the client_id in the may_act claim",
                ): "actor_client_not_consented",
                (
                    400,
                    "invalid_request",
                    "Requesting client does not match the client_id in the may_act claim",
                ): "requester_not_consented",
            }
        )
    if case == "wrong_audience":
        allowed = {
            (400, "invalid_client", "Audience not found"): "audience_not_found",
            (
                400,
                "invalid_request",
                "Requested audience not available: " + BAD_AUDIENCE,
            ): "audience_not_available",
        }
    return allowed.get(key)


def template_matches(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and template_matches(v, actual[k]) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(expected) == len(actual)
            and all(template_matches(a, b) for a, b in zip(expected, actual))
        )
    return expected == actual


def pod_provenance(agent, pod, release, configmap):
    """Match controller-verified signed release/template; allow API scalar defaults."""
    meta, spec = pod["metadata"], pod["spec"]
    labels = meta.get("labels") or {}
    session = labels.get("agentplatform.io/session", "")
    try:
        parsed = uuid.UUID(session)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid real session UUID") from None
    generation = labels.get("agentplatform.io/generation", "")
    if (
        parsed.version != 4
        or str(parsed) != session
        or not re.fullmatch(r"[1-9][0-9]{0,5}", generation)
    ):
        raise ValueError("invalid real session generation")
    expected_name = (
        "s-" + hashlib.sha256(session.encode()).hexdigest()[:16] + "-g" + generation
    )
    status, relspec = release.get("status") or {}, release.get("spec") or {}
    relmeta = release.get("metadata") or {}
    if (
        meta["name"] != expected_name
        or labels.get("agentplatform.io/tenant") != "tenant-test"
        or labels.get("agentplatform.io/release") != relmeta.get("name")
        or relspec.get("agent") != agent
        or relmeta.get("namespace") != "tenant-test"
        or relspec.get("approval", {}).get("approved") is not True
        or status.get("ready") is not True
        or status.get("signatureVerified") is not True
        or status.get("policyDrift") is not False
        or relmeta.get("deletionTimestamp")
        or status.get("podTemplateConfigMap")
        != configmap.get("metadata", {}).get("name")
        or not any(
            o.get("kind") == "AgentRelease"
            and o.get("uid") == relmeta.get("uid")
            and o.get("controller") is True
            for o in configmap.get("metadata", {}).get("ownerReferences", [])
        )
    ):
        raise ValueError("session does not match exact signed Ready release provenance")
    template = human.yaml.safe_load(configmap.get("data", {}).get("pod.yaml", ""))
    if not isinstance(template, dict) or template.get("kind") != "Pod":
        raise ValueError("invalid controller Pod template")
    expected = copy.deepcopy(template["spec"])
    for container in expected.get("containers", []):
        container["env"] = [
            e for e in container.get("env", []) if e.get("name") != "AGENT_SESSION_ID"
        ] + [{"name": "AGENT_SESSION_ID", "value": session}]
    annotations = template.get("metadata", {}).get("annotations") or {}
    if (
        [
            c.get("image")
            for c in expected.get("containers", [])
            if c.get("name") == "agent"
        ]
        != [relspec.get("image")]
        or not template_matches(expected, spec)
        or not template_matches(annotations, meta.get("annotations") or {})
    ):
        raise ValueError("session Pod differs from signed release template")
    return {
        "release": relmeta["name"],
        "release_uid": relmeta["uid"],
        "template_uid": configmap["metadata"]["uid"],
        "session": session,
        "generation": int(generation),
    }


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

    def current(self, token):
        claims = self.verify(token)
        if type(claims.get("exp")) is not int or claims["exp"] < time.time() + 30:
            raise ValueError("token too close to expiry for isolated variant")
        return claims

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
        if (
            claims["sub"] != expected_sub
            or claims.get("azp") != "agent-cli"
            or claims.get("typ") != "Bearer"
            or "act" in claims
            or claims.get("client_type") == "agent"
        ):
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
            if (
                claims["sub"] != expected_sub
                or claims.get("azp") != "agent-cli"
                or claims.get("typ") != "Bearer"
                or "act" in claims
                or claims.get("client_type") == "agent"
            ):
                raise ValueError("unexpected refreshed fixture identity")
            # Preserve rotated credentials only in encrypted output, never logs.
            stored.pop("token", None)
            stored.update(
                access_token=token,
                refresh_token=fresh.get("refresh_token", stored["refresh_token"]),
            )
            human.encrypt(
                path, {"fixture": "T10a subject fixture", "stringData": stored}
            )
        claims = self.current(token)
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
            or not pod["status"].get("containerStatuses")
            or not all(
                c.get("ready") is True for c in pod["status"]["containerStatuses"]
            )
            or spec.get("serviceAccountName") != "agent-" + agent
            or labels.get("agentplatform.io/sandbox") != "true"
            or labels.get("agentplatform.io/agent") != agent
            or not labels.get("agentplatform.io/session")
        ):
            raise ValueError("actor Pod is not the exact running session sandbox")
        release_name = labels.get("agentplatform.io/release", "")
        if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", release_name):
            raise ValueError("actor session release label missing")
        release = self.kubectl(
            ["get", "agentrelease", release_name, "-n", namespace, "-o", "json"]
        )
        template_name = release.get("status", {}).get("podTemplateConfigMap", "")
        if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", template_name):
            raise ValueError("actor release template missing")
        configmap = self.kubectl(
            ["get", "configmap", template_name, "-n", namespace, "-o", "json"]
        )
        provenance = pod_provenance(agent, pod, release, configmap)
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
        assertion_claims = human.jwt.decode(
            assertion, options={"verify_signature": False}
        )
        binding = assertion_claims.get("kubernetes.io", {})
        if (
            assertion_claims.get("sub")
            != "system:serviceaccount:" + namespace + ":agent-" + agent
            or assertion_claims.get("aud") != [human.ISSUER]
            or type(assertion_claims.get("exp")) is not int
            or assertion_claims["exp"] < time.time() + 60
            or binding.get("namespace") != namespace
            or binding.get("pod", {}).get("name") != pod_name
            or binding.get("pod", {}).get("uid") != pod_uid
            or binding.get("serviceaccount", {}).get("name") != "agent-" + agent
        ):
            raise ValueError("API TokenRequest response binding differs")
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
        claims = self.current(token)
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
        current_pod = self.kubectl(
            ["get", "pod", pod_name, "-n", namespace, "-o", "json"]
        )
        if (
            current_pod["metadata"].get("uid") != pod_uid
            or current_pod["metadata"].get("deletionTimestamp")
            or current_pod.get("status", {}).get("phase") != "Running"
        ):
            raise ValueError("actor Pod ended or changed during authentication")
        pod_provenance(agent, current_pod, release, configmap)
        return (
            assertion,
            token,
            sub,
            {
                **provenance,
                "namespace": namespace,
                "pod": pod_name,
                "uid": pod_uid,
                "session": labels["agentplatform.io/session"],
                "client_id": client_id,
                "client_authentication_verified": True,
                "assertion_audience": human.ISSUER,
                "assertion_expires_at": assertion_claims["exp"],
                "actor_expires_at": claims["exp"],
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
        or not {ACTOR, "agent-policy-service"}.issubset(aud)
        or "agent-policy-service" not in subject_claims.get("scope", "").split()
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

    def negative(name, *, subject_path=None, subject_sub=alice, other_tenant=None):
        # Refresh/verify fixtures first, then obtain fresh genuine actor auth for
        # this variant. Never count authentication/expiry as a consent refusal.
        target = None
        if subject_path is not None:
            target, target_claims = op.subject(subject_path, subject_sub)
            if name == "wrong_consent" and (
                target_claims.get("may_act")
                or any(
                    scope.startswith("delegation:client:")
                    for scope in target_claims.get("scope", "").split()
                )
            ):
                raise ValueError(
                    "wrong-consent fixture actually has delegation consent"
                )
            if name == "wrong_user" and (
                subject_sub == alice
                or other_tenant == "tenant-test"
                or not re.fullmatch(r"tenant-[a-z0-9-]{1,50}", other_tenant or "")
                or target_claims.get("tenant") != other_tenant
            ):
                raise ValueError("other-tenant fixture lacks signed tenant provenance")
        positive, positive_claims = op.subject(args.subject, alice)
        positive_aud = positive_claims.get("aud", [])
        positive_aud = [positive_aud] if isinstance(positive_aud, str) else positive_aud
        if (
            positive_claims.get("may_act") != {"sub": actor_sub, "client_id": ACTOR}
            or not {ACTOR, "agent-policy-service"}.issubset(positive_aud)
            or "agent-policy-service" not in positive_claims.get("scope", "").split()
            or "delegation:client:" + ACTOR
            not in positive_claims.get("scope", "").split()
        ):
            raise ValueError("fresh positive subject lacks exact consent")
        fresh_assertion, fresh_actor, fresh_sub, fresh_pod = op.actor(
            "conformance", args.pod, args.pod_uid
        )
        baseline = exchange_form(fresh_assertion, fresh_actor, positive)

        def control():
            op.current(positive)
            op.current(fresh_actor)
            if fresh_pod["assertion_expires_at"] < time.time() + 30:
                raise ValueError("actor assertion too close to expiry")
            control_status, response = op.post(baseline)
            valid = control_status == 200 and all(
                claim_checks(
                    op.current(response["access_token"]), alice, fresh_sub
                ).values()
            )
            return control_status, valid

        before_status, before = control()
        if not before:
            checks[name] = False
            evidence[name] = {
                "positive_before_status": before_status,
                "positive_before": False,
                "negative_sent": False,
            }
            return
        request = dict(baseline)
        request_pod = fresh_pod
        if target is not None:
            op.current(target)
            request["subject_token"] = target
        if name == "wrong_audience":
            request["audience"] = BAD_AUDIENCE
        if name == "wrong_actor":
            other_assertion, other_token, _, other_pod = op.actor(
                "conformance-b", args.wrong_actor_pod, args.wrong_actor_pod_uid
            )
            op.current(other_token)
            request = exchange_form(
                other_assertion,
                other_token,
                positive,
                actor="agent-tenant-test-conformance-b",
            )
            request_pod = other_pod
        if request_pod["assertion_expires_at"] < time.time() + 30:
            raise ValueError("negative actor assertion too close to expiry")
        status, result = op.post(request)
        reason = refusal_reason(name, status, result)
        after_status, after = control()
        checks[name] = before and after and reason is not None
        evidence[name] = {
            "status": status,
            "error": result.get("error")
            if result.get("error") in ERRORS
            else "unclassified",
            "reason": reason or "unclassified",
            "positive_before_status": before_status,
            "positive_after_status": after_status,
            "positive_before": before,
            "positive_after": after,
            "negative_sent": True,
            "actor_provenance": request_pod,
        }

    negative("wrong_consent", subject_path=args.wrong_consent)
    negative("wrong_audience")
    if args.wrong_actor_pod and args.wrong_actor_pod_uid:
        negative("wrong_actor")
    else:
        checks["wrong_actor"] = False
        evidence["wrong_actor"] = {"missing": "genuine conformance-b Running sandbox"}
    if args.other_user and args.other_user_sub and args.other_tenant:
        negative(
            "wrong_user",
            subject_path=args.other_user,
            subject_sub=args.other_user_sub,
            other_tenant=args.other_tenant,
        )
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
