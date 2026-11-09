"""Approve a staged AgentRelease only after the controller has verified it live."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import layout, live

APPROVAL_RE = re.compile(r"^  approval:\n    approved: false\n", re.MULTILINE)


class ApproveError(Exception):
    pass


def gates(committed: dict, observed: dict, pin: dict, repo: str) -> dict:
    """Return the evidence an approval rests on; raise on the first failed gate."""
    spec, status = observed.get("spec") or {}, observed.get("status") or {}
    cspec = committed["spec"]
    name = committed["metadata"]["name"]
    if observed.get("metadata", {}).get("name") != name:
        raise ApproveError("live object is not the committed release")
    for key in ("agent", "image", "manifestSha256", "policySha256", "lockSha256", "buildRevision"):
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
    repo: str = "X-McKay/zetra-agents",
    kube: live.Kube | None = None,
    now: datetime | None = None,
) -> dict:
    kube = kube or live.Kube()
    d, file, committed = layout.find_release(root, name)
    if committed["spec"].get("approval") != {"approved": False}:
        raise ApproveError(f"{file.relative_to(root)} is not an unapproved staged release")
    observed = kube.get("agentrelease", name, d.tenant)
    evidence = gates(committed, observed, layout.signer_pin(root, d.tenant), repo)
    approver = by or layout.committed_agent(d)["spec"].get("owner")
    if not isinstance(approver, str) or not approver:
        raise ApproveError("no approver: pass --by or set the Agent owner")
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    block = f"  approval:\n    approved: true\n    approvedBy: {approver}\n    approvedAt: \"{stamp}\"\n"
    if ticket:
        block += f"    ticket: {ticket}\n"
    text = file.read_text(encoding="utf-8")
    if len(APPROVAL_RE.findall(text)) != 1:
        raise ApproveError(f"{file.relative_to(root)}: expected exactly one `approval: approved: false` block")
    updated = APPROVAL_RE.sub(block, text)
    parsed = yaml.safe_load(updated)
    want = dict(committed)
    want["spec"] = dict(committed["spec"])
    want["spec"]["approval"] = {"approved": True, "approvedBy": approver, "approvedAt": stamp}
    if ticket:
        want["spec"]["approval"]["ticket"] = ticket
    if parsed != want:
        raise ApproveError("approval edit changed more than the approval block")
    file.write_text(updated, encoding="utf-8")
    return {
        "release": name,
        "agent": d.agent,
        "tenant": d.tenant,
        "file": str(file.relative_to(root)),
        "approvedBy": approver,
        "approvedAt": stamp,
        "ticket": ticket,
        "evidence": evidence,
        "next": "commit, merge, then confirm status.ready with `just agent ls`",
    }
