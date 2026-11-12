"""Read-only Kubernetes views of applied agents and their releases."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

import outcome

from . import layout

PLATFORM_NAMESPACE = "agent-platform"


class LiveError(outcome.Coded):
    """A live read failed. The default is the cluster (or kubectl) being out of reach; a raise site that knows better says so."""

    default_code = "unavailable"


def last_line(stderr, limit: int = 200) -> str:
    """The last non-empty line of a failed command's stderr as `: <line>`, trimmed; empty when there is none."""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    lines = [x.strip() for x in (stderr or "").splitlines() if x.strip()]
    if not lines:
        return ""
    line = lines[-1]
    return ": " + (line if len(line) <= limit else line[: limit - 3] + "...")


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
        what = f"kubectl get {kind} {name or ''} -n {namespace}"
        try:
            out = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30).stdout
        except FileNotFoundError as exc:
            raise LiveError(f"{what} failed: kubectl is not installed or not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise LiveError(f"{what} failed: timed out after 30 seconds (API server unreachable or slow)") from exc
        except subprocess.CalledProcessError as exc:
            raise LiveError(f"{what} failed: kubectl exited {exc.returncode}{last_line(exc.stderr)}") from exc
        except OSError as exc:
            raise LiveError(f"{what} failed: kubectl could not be run: {exc.strerror or type(exc).__name__}") from exc
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
    approved_at: str | None = None


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
                approved_at=spec["approval"].get("approvedAt") if isinstance(spec.get("approval"), dict) else None,
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


def _approved_instant(view: ReleaseView) -> datetime | None:
    if not isinstance(view.approved_at, str):
        return None
    try:
        moment = datetime.fromisoformat(view.approved_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def newest(candidates: list[ReleaseView]) -> ReleaseView | None:
    """The most recently approved of several releases, by `spec.approval.approvedAt`; None when that cannot be told
    (a release without a readable time, or two with the same time)."""
    if len(candidates) == 1:
        return candidates[0]
    moments = [_approved_instant(v) for v in candidates]
    if not candidates or any(m is None for m in moments) or len(set(moments)) != len(moments):
        return None
    return max(zip(moments, candidates), key=lambda pair: pair[0])[1]


def resolve_release(views: list[ReleaseView], agent: str, explicit: str | None) -> ReleaseView:
    """The pinned release, else the only runnable one, else the most recently approved runnable one."""
    candidates = runnable(views, agent)
    if explicit:
        match = [v for v in candidates if v.name == explicit]
        if not match:
            raise LiveError(f"{explicit} is not an approved, Ready, signature-verified release of {agent}", "not-found")
        return match[0]
    if not candidates:
        raise LiveError(f"{agent} has no approved Ready release", "not-found")
    chosen = newest(candidates)
    if chosen is None:
        names = ", ".join(v.name for v in candidates)
        raise LiveError(f"{agent} has {len(candidates)} Ready releases and their approval times do not order them; pass --release one of: {names}", "conflict")
    return chosen


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
                    "runnable": chosen.name if (chosen := newest(ok)) else None,
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
