"""Register a source repository's agents with a tenant.

A tenant's signer pin is a pure function of its committed Agents: every
`apps/agents/<tenant>/<agent>/agent.yaml` carries a sync header naming the
repository it came from, and the pin accepts exactly those repositories, each
only for its own agents. `register` adds the agent directories for a repository
(synced from a checkout) and regenerates the pin in both places it is declared:
the tenant Namespace annotation the Registry Controller reads and the
`kyverno/tenant-signers` ConfigMap Kyverno Rule 1 reads. `check` verifies both
copies against the derived value, so a hand edit to either is drift.

The expression is the one `agent_platform.signing.subject_regexp_for_sources`
produces in zetra (platform/contracts); with one repository it is byte for byte
the pin a single `agentctl signer-annotations --repo ... --agent ...` prints.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from . import layout, sync

NAMESPACES = Path("infrastructure/gitops/infrastructure/namespace-policy/agent-platform-namespaces.yaml")
ANNOTATION = "agentplatform.io/signer-subject-regexp"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
AGENT_KUSTOMIZATION = "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - agent.yaml\n"
TAG_SUFFIX = "/v[0-9][A-Za-z0-9.+-]*"


class RegisterError(Exception):
    pass


def _lit(text: str) -> str:
    # Only "." needs escaping in these charsets; RE2 and Python agree (contracts signing.py).
    return text.replace(".", "\\.")


def subject_regexp(sources: dict[str, tuple[str, ...]], workflow: str = "release.yml") -> str:
    """The tenant pin for repositories and the agents each may sign for."""
    if not sources:
        raise RegisterError("a tenant pin needs at least one repository")
    branches = []
    for repository in sorted(sources):
        if not REPOSITORY.match(repository):
            raise RegisterError(f"repository must be owner/name: {repository!r}")
        agents = sorted(set(sources[repository]))
        bad = [a for a in agents if not layout.NAME.match(a)]
        if bad:
            raise RegisterError(f"bad agent names: {', '.join(bad)}")
        tag = "(?:" + "|".join(agents) + ")" if agents else "[a-z0-9-]+"
        branches.append(f"{_lit(repository)}/\\.github/workflows/{_lit(workflow)}@refs/tags/{tag}")
    body = branches[0] if len(branches) == 1 else "(?:" + "|".join(branches) + ")"
    return "^https://github\\.com/" + body + TAG_SUFFIX + "$"


def sources(root: Path, tenant: str) -> dict[str, tuple[str, ...]]:
    """Repository -> agents, read from the sync headers of the tenant's committed Agents."""
    found: dict[str, list[str]] = {}
    for d in layout.agent_dirs(root):
        if d.tenant != tenant:
            continue
        found.setdefault(sync.source_repo(d), []).append(d.agent)
    return {repo: tuple(agents) for repo, agents in found.items()}


def derived_pin(root: Path, tenant: str) -> str:
    return subject_regexp(sources(root, tenant))


def committed_pins(root: Path, tenant: str) -> dict[str, str]:
    """The pin as both files declare it: {"configmap": ..., "namespace": ...}."""
    configmap = layout.signer_pin(root, tenant)["subjectRegExp"]
    namespace = None
    for doc in yaml.safe_load_all((root / NAMESPACES).read_text(encoding="utf-8")):
        if isinstance(doc, dict) and doc.get("kind") == "Namespace" and (doc.get("metadata") or {}).get("name") == tenant:
            namespace = ((doc["metadata"].get("annotations") or {}).get(ANNOTATION))
    if not isinstance(namespace, str):
        raise RegisterError(f"{NAMESPACES}: Namespace {tenant} has no {ANNOTATION} annotation")
    return {"configmap": configmap, "namespace": namespace}


def check(root: Path) -> dict:
    """Every tenant with committed Agents: do both pin copies equal the derived pin?"""
    rows = []
    for tenant in sorted({d.tenant for d in layout.agent_dirs(root)}):
        row = {"tenant": tenant}
        try:
            want = derived_pin(root, tenant)
            have = committed_pins(root, tenant)
        except (layout.LayoutError, RegisterError, sync.SyncError) as exc:
            row.update(state="fail", detail=str(exc))
            rows.append(row)
            continue
        drift = [name for name, value in have.items() if value != want]
        row.update(
            sources={repo: list(agents) for repo, agents in sorted(sources(root, tenant).items())},
            state="ok" if not drift else "drift",
            detail="both pin copies equal the pin derived from the sync headers" if not drift else f"{', '.join(drift)} differ from the derived pin; run `just agent register`",
        )
        rows.append(row)
    return {"ok": all(r["state"] == "ok" for r in rows), "tenants": rows}


def write_pins(root: Path, tenant: str, pattern: str) -> list[str]:
    """Replace the tenant's subjectRegExp in both files textually, keeping everything else."""
    changed = []
    signers = root / layout.SIGNERS
    lines = signers.read_text(encoding="utf-8").split("\n")
    start = _index(lines, f"  {tenant}: |", signers)
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i].startswith("    "):
            raise RegisterError(f"{layout.SIGNERS}: no subjectRegExp line in the {tenant} block")
        m = re.match(r'^(\s+"subjectRegExp": )"(?:[^"\\]|\\.)*"(,?)$', lines[i])
        if m:
            lines[i] = f"{m.group(1)}{json.dumps(pattern)}{m.group(2)}"
            break
    else:
        raise RegisterError(f"{layout.SIGNERS}: no subjectRegExp line in the {tenant} block")
    signers.write_text("\n".join(lines), encoding="utf-8")
    changed.append(str(layout.SIGNERS))

    namespaces = root / NAMESPACES
    lines = namespaces.read_text(encoding="utf-8").split("\n")
    start = _index(lines, f"  name: {tenant}", namespaces)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("---") or lines[i].startswith("  name: "):
            raise RegisterError(f"{NAMESPACES}: Namespace {tenant} has no {ANNOTATION} line")
        if lines[i].startswith(f"    {ANNOTATION}: "):
            if "'" in pattern:
                raise RegisterError("pin cannot contain a single quote")
            lines[i] = f"    {ANNOTATION}: '{pattern}'"
            break
    else:
        raise RegisterError(f"{NAMESPACES}: Namespace {tenant} has no {ANNOTATION} line")
    namespaces.write_text("\n".join(lines), encoding="utf-8")
    changed.append(str(NAMESPACES))

    have = committed_pins(root, tenant)
    if any(value != pattern for value in have.values()):
        raise RegisterError("pin files did not parse back to the written pin")
    return changed


def _index(lines: list[str], exact: str, path: Path) -> int:
    hits = [i for i, line in enumerate(lines) if line == exact]
    if len(hits) != 1:
        raise RegisterError(f"{path}: expected exactly one line {exact!r}, found {len(hits)}")
    return hits[0]


def register(root: Path, tenant: str, repo: str, agents: list[str], source: Path) -> dict:
    """Add `agents` of `repo` to `tenant`, synced from `source`, and regenerate the pin."""
    if not layout.NAME.match(tenant):
        raise RegisterError("tenant must be a DNS label")
    if not REPOSITORY.match(repo):
        raise RegisterError("repository must be owner/name")
    if not agents:
        raise RegisterError("name at least one agent")
    layout.signer_pin(root, tenant)  # the tenant must already exist in both pin files
    committed_pins(root, tenant)
    existing = {d.agent: d for d in layout.agent_dirs(root)}
    added, kept = [], []
    for agent in agents:
        if not layout.NAME.match(agent):
            raise RegisterError(f"agent name {agent!r} is not a DNS label")
        d = existing.get(agent)
        if d is not None:
            if d.tenant != tenant:
                raise RegisterError(f"{agent} is already committed in {d.tenant}; agent names are unique across tenants")
            if sync.source_repo(d) != repo:
                raise RegisterError(f"{agent} is already registered from {sync.source_repo(d)}")
            kept.append(agent)
            continue
        d = layout.AgentDir(root, tenant, agent)
        d.path.mkdir(parents=True, exist_ok=False)
        d.kustomization.write_text(AGENT_KUSTOMIZATION, encoding="utf-8")
        try:
            sync.sync(root, agent, source, repo=repo, d=d)
        except sync.SyncError:
            d.kustomization.unlink()
            d.path.rmdir()
            raise
        layout.append_listed(root / layout.AGENTS_DIR / "kustomization.yaml", f"{tenant}/{agent}/")
        added.append(agent)
    pattern = derived_pin(root, tenant)
    changed = write_pins(root, tenant, pattern) if any(v != pattern for v in committed_pins(root, tenant).values()) else []
    return {
        "tenant": tenant,
        "repo": repo,
        "added": added,
        "alreadyRegistered": kept,
        "sources": {r: list(a) for r, a in sorted(sources(root, tenant).items())},
        "pinFiles": changed,
        "next": "commit as one PR; after Flux applies, `just agent stage <agent> <agent>/vX.Y.Z` per release",
    }
