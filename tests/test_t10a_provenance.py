import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest

path = (
    Path(__file__).parents[1]
    / "infrastructure/scripts/ops/conformance-delegation-contract.py"
)
spec = importlib.util.spec_from_file_location("provenance", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def documents():
    sid = "00000000-0000-4000-8000-000000000001"
    name = "s-" + hashlib.sha256(sid.encode()).hexdigest()[:16] + "-g1"
    expected = {
        "runtimeClassName": "kata-qemu-runtime-rs",
        "serviceAccountName": "agent-conformance",
        "containers": [
            {
                "name": "agent",
                "image": "image@sha256:" + "a" * 64,
                "env": [{"name": "AGENT_SESSION_ID", "value": ""}],
            }
        ],
    }
    pod = {
        "metadata": {
            "name": name,
            "uid": "pod-uid",
            "labels": {
                "agentplatform.io/tenant": "tenant-test",
                "agentplatform.io/release": "release",
                "agentplatform.io/session": sid,
                "agentplatform.io/generation": "1",
            },
            "annotations": {"agentplatform.io/policy-digest": "digest"},
        },
        "spec": copy.deepcopy(expected),
    }
    pod["spec"]["containers"][0]["env"][0]["value"] = sid
    release = {
        "metadata": {
            "name": "release",
            "namespace": "tenant-test",
            "uid": "release-uid",
        },
        "spec": {
            "agent": "conformance",
            "image": "image@sha256:" + "a" * 64,
            "approval": {"approved": True},
        },
        "status": {
            "ready": True,
            "signatureVerified": True,
            "policyDrift": False,
            "podTemplateConfigMap": "podtemplate-release",
        },
    }
    cm = {
        "metadata": {
            "name": "podtemplate-release",
            "uid": "template-uid",
            "ownerReferences": [
                {"kind": "AgentRelease", "uid": "release-uid", "controller": True}
            ],
        },
        "data": {
            "pod.yaml": m.human.yaml.safe_dump(
                {
                    "kind": "Pod",
                    "metadata": {
                        "annotations": {"agentplatform.io/policy-digest": "digest"}
                    },
                    "spec": expected,
                }
            )
        },
    }
    return pod, release, cm


def test_signed_template_session_provenance_allows_scalar_api_defaults():
    pod, rel, cm = documents()
    pod["spec"]["dnsPolicy"] = "ClusterFirst"
    receipt = m.pod_provenance("conformance", pod, rel, cm)
    assert (
        receipt["release_uid"] == "release-uid"
        and receipt["template_uid"] == "template-uid"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_name",
        "session_not_uuid",
        "wrong_generation",
        "unsigned",
        "not_ready",
        "drift",
        "unapproved",
        "owner_replaced",
        "wrong_image",
        "extra_container",
        "wrong_runtime",
        "wrong_annotation",
        "wrong_session_env",
    ],
)
def test_forged_labels_or_release_template_drift_never_prove_session(fault):
    pod, rel, cm = documents()
    if fault == "wrong_name":
        pod["metadata"]["name"] = "debug"
    elif fault == "session_not_uuid":
        pod["metadata"]["labels"]["agentplatform.io/session"] = "fake"
    elif fault == "wrong_generation":
        pod["metadata"]["labels"]["agentplatform.io/generation"] = "2"
    elif fault == "unsigned":
        rel["status"]["signatureVerified"] = False
    elif fault == "not_ready":
        rel["status"]["ready"] = False
    elif fault == "drift":
        rel["status"]["policyDrift"] = True
    elif fault == "unapproved":
        rel["spec"]["approval"]["approved"] = False
    elif fault == "owner_replaced":
        cm["metadata"]["ownerReferences"][0]["uid"] = "other"
    elif fault == "wrong_image":
        pod["spec"]["containers"][0]["image"] = "other"
    elif fault == "extra_container":
        pod["spec"]["containers"].append(copy.deepcopy(pod["spec"]["containers"][0]))
    elif fault == "wrong_runtime":
        pod["spec"]["runtimeClassName"] = "runc"
    elif fault == "wrong_annotation":
        pod["metadata"]["annotations"].clear()
    elif fault == "wrong_session_env":
        pod["spec"]["containers"][0]["env"][0]["value"] = "other"
    with pytest.raises(ValueError):
        m.pod_provenance("conformance", pod, rel, cm)


@pytest.mark.parametrize("fault", [None, "wrong_uid", "wrong_audience", "expired"])
def test_actor_uses_real_api_tokenrequest_binding_without_exporting_jwt(fault):
    import json
    import time
    from types import SimpleNamespace as NS

    pod, release, cm = documents()
    uid = "00000000-0000-4000-8000-000000000002"
    pod["metadata"]["uid"] = uid
    pod["metadata"]["labels"].update(
        {"agentplatform.io/sandbox": "true", "agentplatform.io/agent": "conformance"}
    )
    pod["status"] = {"phase": "Running", "containerStatuses": [{"ready": True}]}
    assertion_claims = {
        "sub": "system:serviceaccount:tenant-test:agent-conformance",
        "aud": [m.human.ISSUER],
        "exp": int(time.time()) + 300,
        "kubernetes.io": {
            "namespace": "tenant-test",
            "pod": {"name": pod["metadata"]["name"], "uid": uid},
            "serviceaccount": {"name": "agent-conformance"},
        },
    }
    if fault == "wrong_uid":
        assertion_claims["kubernetes.io"]["pod"]["uid"] = "replacement"
    elif fault == "wrong_audience":
        assertion_claims["aud"] = ["other"]
    elif fault == "expired":
        assertion_claims["exp"] = int(time.time()) - 1
    assertion = m.human.jwt.encode(
        assertion_claims, "test-only-key-not-a-live-credential", algorithm="HS256"
    )
    calls = []

    def kubectl(args, document=None):
        calls.append((args, document))
        if args[0] == "create":
            return {"status": {"token": assertion}}
        return {"pod": pod, "agentrelease": release, "configmap": cm}[args[1]]

    op = m.Operator.__new__(m.Operator)
    op.kubectl = kubectl
    op.api = NS(
        unique_client=lambda cid: {"id": "client"},
        call=lambda path: {"id": "actor-sub"},
    )
    op.verify = lambda token: {
        "sub": "actor-sub",
        "azp": m.ACTOR,
        "agent_id": "tenant-test/conformance",
        "tenant": "tenant-test",
        "client_type": "agent",
        "exp": int(time.time()) + 300,
    }
    op.post = lambda fields: (200, {"access_token": "actor-token"})
    if fault:
        with pytest.raises(ValueError, match="binding differs"):
            op.actor("conformance", pod["metadata"]["name"], uid)
    else:
        _, _, _, receipt = op.actor("conformance", pod["metadata"]["name"], uid)
        assert assertion not in json.dumps(receipt) and "actor-token" not in json.dumps(
            receipt
        )
        request = next(doc for args, doc in calls if args[0] == "create")
        assert request["spec"]["boundObjectRef"] == {
            "apiVersion": "v1",
            "kind": "Pod",
            "name": pod["metadata"]["name"],
            "uid": uid,
        }
        assert (
            request["spec"]["audiences"] == [m.human.ISSUER]
            and request["spec"]["expirationSeconds"] == 300
        )
        assert receipt["client_authentication_verified"] is True


def test_refresh_normalizes_token_key_and_persists_rotation_only_as_sops(monkeypatch):
    import time

    old = {
        "sub": "alice",
        "azp": "agent-cli",
        "typ": "Bearer",
        "exp": int(time.time()) - 5,
    }
    new = dict(old, exp=int(time.time()) + 300)
    op = m.Operator.__new__(m.Operator)
    op.verify = lambda token, **kwargs: old if token == "old-access" else new
    op.post = lambda fields: (
        200,
        {"access_token": "fresh-access", "refresh_token": "rotated-refresh"},
    )
    monkeypatch.setattr(
        m.human,
        "decrypt",
        lambda path: {"token": "old-access", "refresh_token": "old-refresh"},
    )
    written = []
    monkeypatch.setattr(m.human, "encrypt", lambda path, doc: written.append(doc))
    token, claims = op.subject(Path("fixture.enc.yaml"), "alice")
    assert token == "fresh-access" and claims == new
    assert written == [
        {
            "fixture": "T10a subject fixture",
            "stringData": {
                "access_token": "fresh-access",
                "refresh_token": "rotated-refresh",
            },
        }
    ]


@pytest.mark.parametrize("fault", ["wrong_subject", "wrong_type", "delegated"])
def test_subject_fixture_rejects_wrong_identity_or_nonhuman_access_token(
    monkeypatch, fault
):
    import time

    claims = {
        "sub": "alice",
        "azp": "agent-cli",
        "typ": "Bearer",
        "exp": int(time.time()) + 300,
    }
    if fault == "wrong_subject":
        claims["sub"] = "other"
    elif fault == "wrong_type":
        claims["typ"] = "ID"
    else:
        claims["act"] = {"sub": "actor"}
    op = m.Operator.__new__(m.Operator)
    op.verify = lambda *args, **kwargs: claims
    monkeypatch.setattr(m.human, "decrypt", lambda path: {"access_token": "access"})
    with pytest.raises(ValueError):
        op.subject(Path("fixture.enc.yaml"), "alice")
