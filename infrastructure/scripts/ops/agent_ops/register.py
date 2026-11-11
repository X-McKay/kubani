"""Register a source repository's agents with a tenant.

A tenant's signer pin is a pure function of its committed Agents: every
`apps/agents/<tenant>/<agent>/agent.yaml` carries a sync header naming the
repository it came from, and the pin accepts exactly those repositories, each
only for its own agents. `register` adds the agent directories for a repository
(synced from a checkout) and regenerates the pin in both places it is declared:
the tenant Namespace annotation the Registry Controller reads and the
`kyverno/tenant-signers` ConfigMap Kyverno Rule 1 reads. `check` verifies both
copies against the derived value, so a hand edit to either is drift.

The expression is the one zetra's contracts produce (`subject_regexp_for`, and
`subject_regexp_for_sources` from zetra PR #72 on); with one repository it is byte
for byte the pin `agentctl signer-annotations --repo ... --agent ...` prints.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml

import outcome

from . import layout, sync

NAMESPACES = Path("infrastructure/gitops/infrastructure/namespace-policy/agent-platform-namespaces.yaml")
ANNOTATION = "agentplatform.io/signer-subject-regexp"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
AGENT_KUSTOMIZATION = "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - agent.yaml\n"
TAG_SUFFIX = "/v[0-9][A-Za-z0-9.+-]*"


class RegisterError(outcome.Coded):
    default_code = "validation-failed"


def _lit(text: str) -> str:
    # Only "." needs escaping in these charsets; RE2 and Python agree (contracts signing.py).
    return text.replace(".", "\\.")


def subject_regexp(sources: dict[str, tuple[str, ...]], workflow: str = "release.yml") -> str:
    """The tenant pin for repositories and the agents each may sign for."""
    if not sources:
        raise RegisterError("a tenant pin needs at least one repository")
    if len(sources) > 1 and any(not agents for agents in sources.values()):
        raise RegisterError("with several repositories each must name its agents; a wildcard would let one sign another's")
    branches = []
    for repository in sorted(sources):
        if not REPOSITORY.fullmatch(repository):
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


def _pins_from_texts(signers_text: str, namespaces_text: str, tenant: str) -> dict[str, str]:
    """The pin as both documents declare it: {"configmap": ..., "namespace": ...}."""
    doc = _single(signers_text, layout.SIGNERS)
    data = doc.get("data") or {}
    if tenant not in data:
        raise RegisterError(f"{layout.SIGNERS}: no signer pin for tenant {tenant}", "not-found")
    try:
        configmap = json.loads(data[tenant]).get("subjectRegExp")
    except (ValueError, AttributeError):
        raise RegisterError(f"{layout.SIGNERS}: {tenant} entry is not a JSON object") from None
    if not isinstance(configmap, str):
        raise RegisterError(f"{layout.SIGNERS}: {tenant} has no subjectRegExp")
    namespace = None
    try:
        docs = list(yaml.safe_load_all(namespaces_text))
    except yaml.YAMLError as exc:
        raise RegisterError(f"{NAMESPACES}: not valid YAML: {exc}") from None
    for doc in docs:
        if isinstance(doc, dict) and doc.get("kind") == "Namespace" and (doc.get("metadata") or {}).get("name") == tenant:
            namespace = (doc["metadata"].get("annotations") or {}).get(ANNOTATION)
    if not isinstance(namespace, str):
        raise RegisterError(f"{NAMESPACES}: Namespace {tenant} has no {ANNOTATION} annotation")
    return {"configmap": configmap, "namespace": namespace}


def _single(text: str, path: Path) -> dict:
    try:
        docs = [d for d in yaml.safe_load_all(text) if d is not None]
    except yaml.YAMLError as exc:
        raise RegisterError(f"{path}: not valid YAML: {exc}") from None
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise RegisterError(f"{path}: expected exactly one document")
    return docs[0]


def committed_pins(root: Path, tenant: str) -> dict[str, str]:
    return _pins_from_texts(
        (root / layout.SIGNERS).read_text(encoding="utf-8"),
        (root / NAMESPACES).read_text(encoding="utf-8"),
        tenant,
    )


def pinned_tenants(root: Path) -> list[str]:
    data = _single((root / layout.SIGNERS).read_text(encoding="utf-8"), layout.SIGNERS).get("data") or {}
    return sorted(data)


def check(root: Path) -> dict:
    """Every pinned tenant: do both pin copies equal the pin derived from its committed Agents?

    A pinned tenant without committed Agents is reported too: its pin trusts a repository
    for agents that do not exist, which is either a bootstrap in progress or stale trust.
    """
    rows = []
    dirs = layout.agent_dirs(root)
    names: dict[str, list[str]] = {}
    for d in dirs:
        names.setdefault(d.agent, []).append(d.tenant)
    duplicates = {agent: tenants for agent, tenants in names.items() if len(tenants) > 1}
    try:
        tenants = sorted(set(pinned_tenants(root)) | {d.tenant for d in dirs})
    except RegisterError as exc:
        return {"ok": False, "tenants": [{"tenant": "*", "state": "fail", "detail": str(exc)}]}
    for tenant in tenants:
        row = {"tenant": tenant}
        if tenant not in {d.tenant for d in dirs}:
            row.update(state="fail", detail="pinned tenant has no committed Agents; register one or remove the pin")
            rows.append(row)
            continue
        try:
            found = sources(root, tenant)
            want = subject_regexp(found)
            have = committed_pins(root, tenant)
        except (layout.LayoutError, RegisterError, sync.SyncError) as exc:
            row.update(state="fail", detail=str(exc))
            rows.append(row)
            continue
        drift = [name for name, value in have.items() if value != want]
        row.update(
            sources={repo: list(agents) for repo, agents in sorted(found.items())},
            state="ok" if not drift else "drift",
            detail="both pin copies equal the pin derived from the sync headers" if not drift else f"{', '.join(drift)} differ from the derived pin; run `just agent register`",
        )
        rows.append(row)
    if duplicates:
        rows.append({"tenant": "*", "state": "fail", "detail": "agent names are committed in more than one tenant: " + ", ".join(f"{a} ({', '.join(t)})" for a, t in sorted(duplicates.items()))})
    return {"ok": all(r["state"] == "ok" for r in rows), "tenants": rows}


def write_pins(root: Path, tenant: str, pattern: str) -> list[str]:
    """Replace the tenant's subjectRegExp in both files textually, keeping everything else.

    Both new texts are built and parsed back before either file is written, so the two
    copies never disagree because of a failure between the writes.
    """
    if "'" in pattern or "\n" in pattern:
        raise RegisterError("pin cannot contain a single quote or a newline")
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
    signers_text = "\n".join(lines)

    namespaces = root / NAMESPACES
    lines = namespaces.read_text(encoding="utf-8").split("\n")
    start = _index(lines, f"  name: {tenant}", namespaces)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("---") or lines[i].startswith("  name: "):
            raise RegisterError(f"{NAMESPACES}: Namespace {tenant} has no {ANNOTATION} line")
        if lines[i].startswith(f"    {ANNOTATION}: "):
            lines[i] = f"    {ANNOTATION}: '{pattern}'"
            break
    else:
        raise RegisterError(f"{NAMESPACES}: Namespace {tenant} has no {ANNOTATION} line")
    namespaces_text = "\n".join(lines)

    have = _pins_from_texts(signers_text, namespaces_text, tenant)
    if any(value != pattern for value in have.values()):
        raise RegisterError("rewritten pin files would not parse back to the pin")
    signers.write_text(signers_text, encoding="utf-8")
    namespaces.write_text(namespaces_text, encoding="utf-8")
    return [str(layout.SIGNERS), str(NAMESPACES)]


def _index(lines: list[str], exact: str, path: Path) -> int:
    hits = [i for i, line in enumerate(lines) if line == exact]
    if len(hits) != 1:
        raise RegisterError(f"{path}: expected exactly one line {exact!r}, found {len(hits)}")
    return hits[0]


def register(root: Path, tenant: str, repo: str, agents: list[str], source: Path) -> dict:
    """Add `agents` of `repo` to `tenant`, synced from `source`, and regenerate the pin."""
    if not layout.NAME.match(tenant):
        raise RegisterError("tenant must be a DNS label", "invalid-arguments")
    if not REPOSITORY.fullmatch(repo):
        raise RegisterError("repository must be owner/name", "invalid-arguments")
    if not agents:
        raise RegisterError("name at least one agent", "invalid-arguments")
    committed_pins(root, tenant)  # the tenant must already exist in both pin files
    top = root / layout.AGENTS_DIR / "kustomization.yaml"
    listed = layout.listed_resources(top)  # refuses a kustomization that cannot be appended
    existing = {d.agent: d for d in layout.agent_dirs(root)}
    added, kept = [], []
    for agent in agents:
        if not layout.NAME.match(agent):
            raise RegisterError(f"agent name {agent!r} is not a DNS label", "invalid-arguments")
        d = existing.get(agent)
        entry = f"{tenant}/{agent}/"
        if d is not None:
            if d.tenant != tenant:
                raise RegisterError(f"{agent} is already committed in {d.tenant}; agent names are unique across tenants", "conflict")
            if sync.source_repo(d) != repo:
                raise RegisterError(f"{agent} is already registered from {sync.source_repo(d)}", "conflict")
            if entry not in listed:  # an earlier run stopped between sync and the listing
                layout.append_listed(top, entry)
                listed.append(entry)
            kept.append(agent)
            continue
        d = layout.AgentDir(root, tenant, agent)
        if d.path.exists():
            # Left by a run that failed before agent.yaml existed; nothing in it is reviewed.
            if any(p.name != "kustomization.yaml" for p in d.path.iterdir()):
                raise RegisterError(f"{d.path.relative_to(root)} exists without agent.yaml; inspect and remove it", "conflict")
            shutil.rmtree(d.path)
        d.path.mkdir(parents=True, exist_ok=False)
        try:
            d.kustomization.write_text(AGENT_KUSTOMIZATION, encoding="utf-8")
            sync.sync(root, agent, source, repo=repo, d=d)
            layout.append_listed(top, entry)
        except BaseException:
            shutil.rmtree(d.path, ignore_errors=True)
            raise
        listed.append(entry)
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
