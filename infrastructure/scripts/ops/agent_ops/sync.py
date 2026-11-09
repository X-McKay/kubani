"""Verified copies of each agent's `deploy/agent.yaml` from the source repository.

The committed Agent is the source file's exact bytes behind a three-line header
that records where it came from. `check` verifies the header against the body
offline and, given a source checkout, against the recorded commit.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from . import layout

HEADER_RE = re.compile(
    r"^# Synced from (?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+) (?P<path>agents/[a-z0-9-]+/deploy/agent\.yaml)"
    r" at (?P<commit>[0-9a-f]{40})\n"
    r"# sha256:(?P<sha>[0-9a-f]{64}) of the body below; do not hand-edit\.\n"
    r"# Change deploy/agent\.yaml in the source repository, then: just agent sync (?P<agent>[a-z0-9-]+) --source PATH\n",
)
DEFAULT_REPO = "X-McKay/zetra-agents"


class SyncError(Exception):
    pass


def _git(source: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(source), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise SyncError(f"git {' '.join(args)} failed in {source}") from exc


def source_file(source: Path, agent: str, commit: str) -> str:
    return _git(source, "show", f"{commit}:agents/{agent}/deploy/agent.yaml")


def source_head(source: Path, agent: str) -> tuple[str, bool]:
    head = _git(source, "rev-parse", "HEAD").strip()
    dirty = bool(_git(source, "status", "--porcelain", "--", f"agents/{agent}").strip())
    return head, dirty


def source_repo(d: layout.AgentDir) -> str:
    """The repository the committed Agent was synced from, per its header."""
    meta, _ = split(d.agent_file.read_text(encoding="utf-8"))
    if meta is None:
        raise SyncError(f"{d.agent_file.relative_to(d.root)} has no sync header; pass --repo or run `just agent register`")
    return meta["repo"]


def header(repo: str, agent: str, commit: str, body: str) -> str:
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return (
        f"# Synced from {repo} agents/{agent}/deploy/agent.yaml at {commit}\n"
        f"# sha256:{sha} of the body below; do not hand-edit.\n"
        f"# Change deploy/agent.yaml in the source repository, then: just agent sync {agent} --source PATH\n"
    )


def split(text: str) -> tuple[dict | None, str]:
    m = HEADER_RE.match(text)
    if not m:
        return None, text
    return m.groupdict(), text[m.end() :]


def sync(root: Path, agent: str, source: Path, *, repo: str | None = None, d: layout.AgentDir | None = None) -> dict:
    """Copy the source Agent behind a header. `repo` defaults to the one already recorded;
    `d` names a directory that does not exist yet (used by `register`)."""
    d = d or layout.find_agent(root, agent)
    repo = repo or source_repo(d)
    head, dirty = source_head(source, agent)
    if dirty:
        raise SyncError(f"{source}/agents/{agent} has uncommitted changes; commit them first")
    body = source_file(source, agent, head)
    doc = _parse_agent(body, d)
    current = layout.committed_agent(d) if d.agent_file.is_file() else None
    spec_changed = current is None or current["spec"] != doc["spec"]
    d.agent_file.write_text(header(repo, agent, head, body) + body, encoding="utf-8")
    return {
        "agent": agent,
        "tenant": d.tenant,
        "file": str(d.agent_file.relative_to(root)),
        "source": {"repo": repo, "commit": head},
        "specChanged": spec_changed,
    }


def _parse_agent(body: str, d: layout.AgentDir) -> dict:
    import yaml

    docs = [x for x in yaml.safe_load_all(body) if x is not None]
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise SyncError("source deploy/agent.yaml must hold exactly one document")
    doc = docs[0]
    meta = doc.get("metadata") or {}
    if doc.get("kind") != "Agent" or meta.get("name") != d.agent or meta.get("namespace") != d.tenant:
        raise SyncError(f"source Agent must be named {d.agent} in namespace {d.tenant}")
    if not isinstance(doc.get("spec"), dict):
        raise SyncError("source Agent spec must be a mapping")
    return doc


def check(root: Path, *, source: Path | None = None, agents: list[str] | None = None) -> dict:
    rows = []
    for d in layout.agent_dirs(root):
        if agents and d.agent not in agents:
            continue
        rows.append(_check_one(d, source))
    ok = all(r["state"] == "ok" for r in rows)
    return {"ok": ok, "agents": rows}


def _check_one(d: layout.AgentDir, source: Path | None) -> dict:
    row = {"agent": d.agent, "tenant": d.tenant, "file": str(d.agent_file.relative_to(d.root))}
    text = d.agent_file.read_text(encoding="utf-8")
    meta, body = split(text)
    if meta is None:
        row.update(state="unsynced", detail="no sync header; run `just agent sync`")
        return row
    if meta["agent"] != d.agent or meta["path"] != f"agents/{d.agent}/deploy/agent.yaml":
        row.update(state="fail", detail="header names a different agent")
        return row
    actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if actual != meta["sha"]:
        row.update(state="fail", detail="body does not match the header sha256; hand-edited?")
        return row
    try:
        layout.committed_agent(d)
    except layout.LayoutError as exc:
        row.update(state="fail", detail=str(exc))
        return row
    row.update(commit=meta["commit"], repo=meta["repo"])
    if source is None:
        row.update(state="ok", detail="header verified offline; source not compared")
        return row
    try:
        recorded = source_file(source, d.agent, meta["commit"])
    except SyncError:
        row.update(state="fail", detail="recorded commit or file is not present in the source checkout")
        return row
    if recorded != body:
        row.update(state="fail", detail="body differs from the source file at the recorded commit")
        return row
    head, _ = source_head(source, d.agent)
    latest = source_file(source, d.agent, head) if head != meta["commit"] else body
    row.update(state="ok", detail="matches recorded commit", stale=latest != body, sourceHead=head)
    return row
