"""Approve a staged AgentRelease only after the controller has verified it live."""

from __future__ import annotations

import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

import outcome

from . import layout, live, registry_client, sync

APPROVAL_RE = re.compile(r"^  approval:\n    approved: false\n", re.MULTILINE)

# What an approval that covers an effect states, after `effect <name>: `. The text is the platform's
# (zetra platform/registry/contract/effects.json at 589ec5c, skills contract section 7.4); a test holds it.
EFFECT_STATEMENTS = {"sandbox_execute": "skill scripts run inside the agent's container and can read the session's identity token"}


class ApproveError(outcome.Coded):
    """A gate refused the approval."""

    default_code = "refused"


def covers(release_spec: dict, agent_spec: dict) -> list[str]:
    """One sentence for each effect the release requests: its declaration's or, for a release without one, its Agent's."""
    declaration = release_spec.get("declaration")
    capabilities = (declaration if isinstance(declaration, dict) else agent_spec).get("capabilities")
    effects = capabilities.get("effects") if isinstance(capabilities, dict) else None
    names = sorted({e for e in effects if isinstance(e, str)}) if isinstance(effects, list) else []
    unknown = [e for e in names if e not in EFFECT_STATEMENTS]
    if unknown:
        raise ApproveError("the release requests an effect this command cannot describe: " + ", ".join(unknown))
    return [f"effect {e}: {EFFECT_STATEMENTS[e]}" for e in names]


def gates(committed: dict, observed: dict, pin: dict, repo: str) -> dict:
    """Return the evidence an approval rests on; raise on the first failed gate."""
    spec, status = observed.get("spec") or {}, observed.get("status") or {}
    cspec = committed["spec"]
    name = committed["metadata"]["name"]
    if observed.get("metadata", {}).get("name") != name:
        raise ApproveError("live object is not the committed release")
    for key in ("agent", "image", "manifestSha256", "policySha256", "lockSha256", "buildRevision", "skills"):
        if spec.get(key) != cspec.get(key):
            raise ApproveError(f"live spec.{key} differs from the committed file")
    if spec.get("approval", {}).get("approved") is not False:
        raise ApproveError("live release is not in the unapproved state")
    conditions = {c.get("type"): c for c in status.get("conditions", [])}
    sig = conditions.get("SignatureVerified", {})
    if status.get("signatureVerified") is not True or sig.get("status") != "True" or sig.get("reason") != "Verified":
        raise ApproveError("controller has not verified the signature")
    signer = status.get("verifiedSigner") or {}
    expected_prefix = layout.expected_subject(repo, f"{cspec['agent']}/")
    subject = signer.get("subject", "")
    if signer.get("issuer") != layout.ISSUER or not subject.startswith(expected_prefix):
        raise ApproveError("verified signer is not this agent's release workflow")
    if pin["issuer"] != layout.ISSUER or not layout.subject_matches(pin, subject):
        raise ApproveError("verified signer subject is outside the tenant signer pin")
    if set(signer.get("attestations") or []) != layout.ATTESTATIONS or len(signer.get("attestations") or []) != 5:
        raise ApproveError("the five required attestations were not all verified")
    drift = conditions.get("PolicyDrift", {})
    if status.get("policyDrift") is not False or drift.get("status") != "False" or drift.get("reason") != "NoDrift":
        raise ApproveError("policy digest drift is not clear")
    if status.get("policyDigest") != "sha256:" + cspec["policySha256"]:
        raise ApproveError("controller policy digest differs from the committed policySha256")
    ready = conditions.get("Ready", {})
    if status.get("ready") is not False or ready.get("reason") != "NotApproved":
        raise ApproveError("release is not waiting solely on approval")
    return {
        "uid": observed.get("metadata", {}).get("uid"),
        "signer": subject,
        "attestations": sorted(signer["attestations"]),
        "policyDigest": status["policyDigest"],
        "readyReason": ready.get("reason"),
    }


def approve(
    root: Path,
    name: str,
    *,
    by: str | None = None,
    ticket: str | None = None,
    repo: str | None = None,
    kube: live.Kube | None = None,
    now: datetime | None = None,
) -> dict:
    if any(x.agent == name for x in layout.agent_dirs(root)):
        d = layout.find_agent(root, name)
        if layout.is_listed(root, d):
            raise ApproveError(f"{name} is an agent on the pull request path; approve one of its staged releases with `just agent approve <release>`", "wrong-path")
        if by is not None:
            raise ApproveError("--by does not apply to an agent owned by the registry: it records the person who signs in", "invalid-arguments")
        return approve_registry(root, d, ticket=ticket)
    kube = kube or live.Kube()
    d, file, committed = layout.find_release(root, name)
    if not layout.is_listed(root, d):
        raise ApproveError(f"{name} belongs to {d.agent}, which the registry owns; approve it with `just agent approve {d.agent}`", "wrong-path")
    if committed["spec"].get("approval") != {"approved": False}:
        raise ApproveError(f"{file.relative_to(root)} is not an unapproved staged release", "conflict")
    observed = kube.get("agentrelease", name, d.tenant)
    evidence = gates(committed, observed, layout.signer_pin(root, d.tenant), repo or sync.source_repo(d))
    agent_spec = layout.committed_agent(d)["spec"]
    statements = covers(committed["spec"], agent_spec)
    approver = by or agent_spec.get("owner")
    if not isinstance(approver, str) or not approver:
        raise ApproveError("no approver: pass --by or set the Agent owner", "invalid-arguments")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = f"  approval:\n    approved: true\n    approvedBy: {approver}\n    approvedAt: \"{stamp}\"\n"
    if ticket:
        block += f"    ticket: {ticket}\n"
    text = file.read_text(encoding="utf-8")
    if len(APPROVAL_RE.findall(text)) != 1:
        raise ApproveError(f"{file.relative_to(root)}: expected exactly one `approval: approved: false` block", "validation-failed")
    updated = APPROVAL_RE.sub(block, text)
    parsed = yaml.safe_load(updated)
    want = dict(committed)
    want["spec"] = dict(committed["spec"])
    want["spec"]["approval"] = {"approved": True, "approvedBy": approver, "approvedAt": stamp}
    if ticket:
        want["spec"]["approval"]["ticket"] = ticket
    if parsed != want:
        raise ApproveError("approval edit changed more than the approval block", "validation-failed")
    file.write_text(updated, encoding="utf-8")
    for statement in statements:
        print(f"This approval covers {statement}", file=sys.stderr, flush=True)
    return {
        "release": name,
        "agent": d.agent,
        "tenant": d.tenant,
        "file": str(file.relative_to(root)),
        "approvedBy": approver,
        "approvedAt": stamp,
        "ticket": ticket,
        "covers": statements,
        "evidence": evidence,
        "next": "commit, merge, then confirm status.ready with `just agent ls`",
    }


def _highest(deployment: dict) -> int:
    numbers = [r.get("number") for r in deployment.get("revisions") or [] if isinstance(r, dict) and isinstance(r.get("number"), int)]
    if not numbers:
        raise ApproveError("the registry holds no revision of this agent; record one with `just agent stage`")
    return max(numbers)


def _show(preview: dict, say) -> None:
    say(f"Approval of {preview.get('deployment')}")
    say(f"  revision {preview.get('revision')}, release {preview.get('release')}, policy revision {preview.get('policyRevision')}")
    changes = preview.get("changes") or []
    if changes:
        say("  the authority is wider than the current release:")
        for change in changes:
            say(f"    - {change}")
    else:
        say("  the authority is no wider than the current release")


def approve_registry(root: Path, d: layout.AgentDir, *, ticket: str | None = None) -> dict:
    """Approve the newest revision of an agent the registry owns, after the person has read what the approval is bound to."""
    cfg = registry_client.settings()
    client = registry_client.Client(cfg, registry_client.person_token())
    path = registry_client.deployment_path(cfg, d.tenant, d.agent)
    deployment = client.get(path)
    number = _highest(deployment)
    preview = client.get(f"{path}/revisions/{number}/approval")
    base = {"agent": d.agent, "deployment": preview.get("deployment") or registry_client.deployment_id(cfg, d.tenant, d.agent), "path": "registry", "release": preview.get("release"), "revision": number}
    if preview.get("approved") is True:
        return {**base, "changed": False, "next": "`just agent status` shows the revision's progress"}
    if preview.get("approvable") is not True:
        failures = preview.get("gateFailures") or []
        state = (preview.get("observation") or {}).get("state")
        raise ApproveError(f"revision {number} of {d.agent} cannot be approved now: " + ("; ".join(str(f) for f in failures) or "no gate failure is listed") + f" (observation {state})")
    say = lambda line: print(line, file=sys.stderr, flush=True)  # noqa: E731
    _show(preview, say)
    print("Type yes to approve this revision: ", end="", file=sys.stderr, flush=True)
    if sys.stdin.readline().strip().lower() != "yes":
        raise ApproveError("not approved: the answer was not yes; nothing was sent", "not-confirmed")
    approval_id = uuid.uuid4().hex
    body = {
        "approvalId": approval_id,
        "revision": number,
        "authorityDigest": preview.get("authorityDigest"),
        "baseAuthorityDigest": preview.get("baseAuthorityDigest"),
        "policyRevision": preview.get("policyRevision"),
        "ticket": ticket,
    }
    answer = client.post(f"{path}/approvals", body)
    approval = answer.get("approval") if isinstance(answer.get("approval"), dict) else {}
    return {
        **base,
        "approvedBy": approval.get("approvedBy"),
        "approvalId": approval.get("id") or approval_id,
        "changes": preview.get("changes") or [],
        "changed": True,
        "next": "`just agent status` shows when the release is running",
    }
