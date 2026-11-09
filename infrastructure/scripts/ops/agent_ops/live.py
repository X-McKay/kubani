"""Read-only Kubernetes views of applied agents and their releases."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from . import layout

PLATFORM_NAMESPACE = "agent-platform"


class LiveError(Exception):
    pass


class Kube:
    """kubectl reads with an explicit kubeconfig; `exec` is the one non-read path (run)."""

    def __init__(self, kubeconfig: str | None = None):
        self.kubeconfig = kubeconfig or os.environ.get("KUBECONFIG") or os.path.expanduser("~/.kube/config")

    def _base(self) -> list[str]:
        return ["kubectl", "--kubeconfig", self.kubeconfig]

    def get(self, kind: str, name: str | None, namespace: str, *, selector: str | None = None) -> dict:
        cmd = self._base() + ["get", kind, "-n", namespace, "-o", "json"]
        if name:
            cmd.append(name)
        if selector:
            cmd += ["-l", selector]
        try:
            out = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30).stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            raise LiveError(f"kubectl get {kind} {name or ''} -n {namespace} failed") from exc
        return json.loads(out)

    def exec(self, pod: str, namespace: str, container: str, argv: list[str], stdin: bytes, timeout: int) -> subprocess.CompletedProcess:
        cmd = self._base() + ["exec", "-i", "-n", namespace, pod, "-c", container, "--", *argv]
        return subprocess.run(cmd, input=stdin, capture_output=True, timeout=timeout)


@dataclass(frozen=True)
class ReleaseView:
    name: str
    agent: str
    approved: bool
    ready: bool
    signature: bool
    drift: bool
    identity_mode: str | None
    delegation_required: bool | None
    ready_reason: str | None


def _conditions(status: dict) -> dict:
    return {c.get("type"): c for c in status.get("conditions", []) if isinstance(c, dict)}


def releases(kube: Kube, tenant: str) -> list[ReleaseView]:
    items = kube.get("agentreleases", None, tenant).get("items", [])
    views = []
    for item in items:
        spec, status = item.get("spec") or {}, item.get("status") or {}
        views.append(
            ReleaseView(
                name=item["metadata"]["name"],
                agent=spec.get("agent", ""),
                approved=spec.get("approval", {}).get("approved") is True,
                ready=status.get("ready") is True,
                signature=status.get("signatureVerified") is True,
                drift=status.get("policyDrift") is True,
                identity_mode=status.get("identityMode"),
                delegation_required=status.get("delegationRequired"),
                ready_reason=_conditions(status).get("Ready", {}).get("reason"),
            )
        )
    return sorted(views, key=lambda v: (v.agent, v.name))


def agents(kube: Kube, tenant: str) -> dict[str, dict]:
    items = kube.get("agents", None, tenant).get("items", [])
    out = {}
    for item in items:
        spec, status = item.get("spec") or {}, item.get("status") or {}
        out[item["metadata"]["name"]] = {
            "ready": _conditions(status).get("Ready", {}).get("status") == "True",
            "identity": (spec.get("identity") or {}).get("mode"),
            "models": [m.get("backend") for m in (spec.get("capabilities") or {}).get("models") or []],
            "mcp": [m.get("backend") for m in (spec.get("capabilities") or {}).get("mcp") or []],
            "description": spec.get("description", ""),
        }
    return out


def runnable(views: list[ReleaseView], agent: str) -> list[ReleaseView]:
    return [v for v in views if v.agent == agent and v.approved and v.ready and v.signature and not v.drift]


def resolve_release(views: list[ReleaseView], agent: str, explicit: str | None) -> ReleaseView:
    candidates = runnable(views, agent)
    if explicit:
        match = [v for v in candidates if v.name == explicit]
        if not match:
            raise LiveError(f"{explicit} is not an approved, Ready, signature-verified release of {agent}")
        return match[0]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise LiveError(f"{agent} has no approved Ready release")
    names = ", ".join(v.name for v in candidates)
    raise LiveError(f"{agent} has {len(candidates)} Ready releases; pass --release one of: {names}")


def listing(root, kube: Kube) -> list[dict]:
    rows = []
    tenants = sorted({d.tenant for d in layout.agent_dirs(root)})
    for tenant in tenants:
        live_agents = agents(kube, tenant)
        views = releases(kube, tenant)
        committed = {d.agent for d in layout.agent_dirs(root) if d.tenant == tenant}
        for name in sorted(committed | set(live_agents)):
            info = live_agents.get(name)
            mine = [v for v in views if v.agent == name]
            ok = runnable(views, name)
            rows.append(
                {
                    "tenant": tenant,
                    "agent": name,
                    "committed": name in committed,
                    "live": info is not None,
                    "ready": bool(info and info["ready"]),
                    "identity": info["identity"] if info else None,
                    "models": info["models"] if info else [],
                    "mcp": info["mcp"] if info else [],
                    "releases": len(mine),
                    "readyReleases": [v.name for v in ok],
                    "runnable": ok[0].name if len(ok) == 1 else None,
                    "description": info["description"] if info else "",
                }
            )
    return rows


def format_listing(rows: list[dict]) -> str:
    head = ("AGENT", "IDENTITY", "READY", "RELEASES", "RUNNABLE RELEASE")
    table = [head]
    for r in rows:
        if r["runnable"]:
            runnable_col = r["runnable"]
        elif len(r["readyReleases"]) > 1:
            runnable_col = f"ambiguous ({len(r['readyReleases'])} Ready; pass --release)"
        else:
            runnable_col = "none"
        table.append(
            (
                r["agent"],
                r["identity"] or ("absent" if not r["live"] else "?"),
                "yes" if r["ready"] else "no",
                f"{len(r['readyReleases'])}/{r['releases']}",
                runnable_col,
            )
        )
    widths = [max(len(row[i]) for row in table) for i in range(len(head))]
    return "\n".join("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip() for row in table)


def runner_pod(kube: Kube, tenant: str) -> dict:
    """The single Ready legacy-pool Session Runner pod of the tenant."""
    selector = f"app.kubernetes.io/name=session-runner,agentplatform.io/tenant={tenant}"
    items = kube.get("pods", None, PLATFORM_NAMESPACE, selector=selector).get("items", [])
    ready = []
    for pod in items:
        if pod["metadata"].get("deletionTimestamp"):
            continue
        statuses = {c["name"]: c for c in pod.get("status", {}).get("containerStatuses", [])}
        runner = statuses.get("runner")
        if pod.get("status", {}).get("phase") == "Running" and runner and runner.get("ready"):
            ready.append(pod)
    if len(ready) != 1:
        raise LiveError(f"expected exactly one Ready session-runner pod for {tenant}, found {len(ready)}")
    pod = ready[0]
    runner = next(c for c in pod["status"]["containerStatuses"] if c["name"] == "runner")
    return {
        "name": pod["metadata"]["name"],
        "uid": pod["metadata"]["uid"],
        "containerID": runner.get("containerID"),
        "imageID": runner.get("imageID"),
        "restartCount": runner.get("restartCount"),
    }
