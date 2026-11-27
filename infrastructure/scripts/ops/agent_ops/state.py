"""One read-only snapshot of the platform: Flux, Agents, releases, pods, open PRs."""

from __future__ import annotations

import json
import subprocess

from . import layout, live, register

FLUX_NAMESPACE = "flux-system"


def _conditions(obj: dict) -> dict:
    return {c.get("type"): c for c in (obj.get("status") or {}).get("conditions", []) if isinstance(c, dict)}


def flux(kube: live.Kube) -> list[dict]:
    rows = []
    for item in kube.get("kustomizations.kustomize.toolkit.fluxcd.io", None, FLUX_NAMESPACE).get("items", []):
        ready = _conditions(item).get("Ready", {})
        rows.append(
            {
                "name": item["metadata"]["name"],
                "ready": ready.get("status") == "True",
                "revision": (item.get("status") or {}).get("lastAppliedRevision"),
                "suspended": bool(item.get("spec", {}).get("suspend")),
                "message": ready.get("message", ""),
            }
        )
    return rows


def pods(kube: live.Kube, namespace: str) -> dict:
    items = kube.get("pods", None, namespace).get("items", [])
    unhealthy = []
    for pod in items:
        phase = pod.get("status", {}).get("phase")
        statuses = pod.get("status", {}).get("containerStatuses") or []
        ready = all(c.get("ready") for c in statuses) and bool(statuses)
        if phase in ("Succeeded",):
            continue
        if phase != "Running" or not ready:
            unhealthy.append({"name": pod["metadata"]["name"], "phase": phase, "ready": ready})
    return {"total": len(items), "unhealthy": unhealthy}


def open_prs(repo: str = "X-McKay/kubani") -> list[dict] | None:
    try:
        out = subprocess.run(
            ["gh", "pr", "list", "-R", repo, "--state", "open", "--json", "number,title,isDraft,updatedAt", "--limit", "50"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    prs = json.loads(out)
    return [p for p in prs if not p["title"].lower().startswith(("chore(deps)", "build(deps"))]


def snapshot(root, kube: live.Kube, *, prs: bool = True) -> dict:
    # A tenant with no agents yet is still a tenant: its Namespace is declared before its first agent is registered.
    tenants = sorted({d.tenant for d in layout.agent_dirs(root)} | set(register.declared_tenants(root)))
    out = {"flux": flux(kube), "platformPods": pods(kube, live.PLATFORM_NAMESPACE), "tenants": {}}
    for tenant in tenants:
        agents = live.agents(kube, tenant)
        views = live.releases(kube, tenant)
        committed = {d.agent: layout.purpose(d) for d in layout.agent_dirs(root) if d.tenant == tenant}
        out["tenants"][tenant] = {
            "agents": {
                "total": len(agents),
                # As `ls` reads it: the applied label, else what this repository will apply.
                "fixtures": sum((a["purpose"] or committed.get(n)) == layout.FIXTURE for n, a in agents.items()),
                "switchedOff": sorted(n for n, a in agents.items() if not a["enabled"]),
                "notReady": sorted(n for n, a in agents.items() if not a["ready"]),
            },
            "releases": {
                "total": len(views),
                "ready": sum(v.ready for v in views),
                "unapproved": sorted(v.name for v in views if not v.approved),
                "approvedNotReady": sorted(f"{v.name} ({v.ready_reason})" for v in views if v.approved and not v.ready),
            },
            "sandboxPods": [p["metadata"]["name"] for p in kube.get("pods", None, tenant).get("items", [])],
        }
    out["openPullRequests"] = open_prs() if prs else None
    return out


def format_snapshot(snap: dict) -> str:
    lines = ["FLUX KUSTOMIZATIONS"]
    for k in snap["flux"]:
        state = "Ready" if k["ready"] else ("Suspended" if k["suspended"] else "NOT READY")
        extra = f"  {k['message']}" if not k["ready"] and k["message"] else ""
        lines.append(f"  {k['name']:28s} {state:10s} {k['revision'] or '-'}{extra}")
    p = snap["platformPods"]
    lines.append("")
    lines.append(f"PLATFORM PODS  {p['total']} total, {len(p['unhealthy'])} unhealthy")
    for u in p["unhealthy"]:
        lines.append(f"  {u['name']}  {u['phase']}  ready={u['ready']}")
    for tenant, t in snap["tenants"].items():
        lines.append("")
        lines.append(f"TENANT {tenant}")
        a = t["agents"]
        lines.append(f"  agents    {a['total'] - a['fixtures']} for use, {a['fixtures']} test fixtures; not Ready: {', '.join(a['notReady']) or 'none'}")
        if a["switchedOff"]:
            lines.append(f"    switched off      {', '.join(a['switchedOff'])}")
        r = t["releases"]
        lines.append(f"  releases  {r['total']} total, {r['ready']} Ready")
        lines.append(f"    unapproved        {', '.join(r['unapproved']) or 'none'}")
        lines.append(f"    approved, !Ready  {', '.join(r['approvedNotReady']) or 'none'}")
        lines.append(f"  sandboxes {', '.join(t['sandboxPods']) or 'none'}")
    prs = snap.get("openPullRequests")
    lines.append("")
    if prs is None:
        lines.append("OPEN PULL REQUESTS  (gh unavailable)")
    else:
        lines.append(f"OPEN PULL REQUESTS  {len(prs)} (dependency bumps hidden)")
        for pr in prs:
            lines.append(f"  #{pr['number']:<5d} {'draft  ' if pr['isDraft'] else ''}{pr['title']}")
    return "\n".join(lines)
