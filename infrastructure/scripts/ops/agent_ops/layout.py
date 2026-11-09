"""Committed layout of applied agents: apps/agents/<tenant>/<agent>/."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

AGENTS_DIR = Path("infrastructure/gitops/apps/agents")
SIGNERS = Path("infrastructure/gitops/infrastructure/kyverno/tenant-signers.yaml")
NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?\Z")
TAG = re.compile(r"^(?P<agent>[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?)/(?P<version>v[0-9][A-Za-z0-9.+-]*)\Z")
SHA256 = re.compile(r"^[0-9a-f]{64}\Z")
ISSUER = "https://token.actions.githubusercontent.com"
ATTESTATIONS = frozenset(
    {
        "https://slsa.dev/provenance/v1",
        "https://spdx.dev/Document",
        "https://cosign.sigstore.dev/attestation/vuln/v1",
        "https://agentplatform.io/eval/v1",
        "https://agentplatform.io/attestations/release/v1",
    }
)


class LayoutError(Exception):
    """The committed tree does not have the expected shape."""


@dataclass(frozen=True)
class AgentDir:
    root: Path
    tenant: str
    agent: str

    @property
    def path(self) -> Path:
        return self.root / AGENTS_DIR / self.tenant / self.agent

    @property
    def agent_file(self) -> Path:
        return self.path / "agent.yaml"

    @property
    def kustomization(self) -> Path:
        return self.path / "kustomization.yaml"

    def release_files(self) -> list[Path]:
        return sorted(p for p in self.path.glob("agentrelease*.yaml") if p.is_file())


def load_one(path: Path, kind: str) -> dict:
    docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d is not None]
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise LayoutError(f"{path}: expected exactly one document")
    doc = docs[0]
    if doc.get("apiVersion") != "agentplatform.io/v1alpha1" or doc.get("kind") != kind:
        raise LayoutError(f"{path}: expected agentplatform.io/v1alpha1 {kind}")
    if not isinstance(doc.get("metadata"), dict) or not isinstance(doc.get("spec"), dict):
        raise LayoutError(f"{path}: metadata and spec must be mappings")
    return doc


def agent_dirs(root: Path) -> list[AgentDir]:
    base = root / AGENTS_DIR
    if not base.is_dir():
        raise LayoutError(f"{base} is missing")
    found = []
    for tenant in sorted(p for p in base.iterdir() if p.is_dir()):
        for agent in sorted(p for p in tenant.iterdir() if p.is_dir()):
            if (agent / "agent.yaml").is_file():
                if not NAME.match(tenant.name) or not NAME.match(agent.name):
                    raise LayoutError(f"{agent}: tenant and agent directories must be DNS labels")
                found.append(AgentDir(root, tenant.name, agent.name))
    return found


def find_agent(root: Path, agent: str) -> AgentDir:
    matches = [d for d in agent_dirs(root) if d.agent == agent]
    if len(matches) != 1:
        raise LayoutError(f"agent {agent!r}: expected exactly one committed directory, found {len(matches)}")
    return matches[0]


def find_release(root: Path, name: str) -> tuple[AgentDir, Path, dict]:
    hits = []
    for d in agent_dirs(root):
        for file in d.release_files():
            doc = load_one(file, "AgentRelease")
            if doc["metadata"].get("name") == name:
                hits.append((d, file, doc))
    if len(hits) != 1:
        raise LayoutError(f"AgentRelease {name!r}: expected exactly one committed file, found {len(hits)}")
    return hits[0]


def committed_agent(d: AgentDir) -> dict:
    doc = load_one(d.agent_file, "Agent")
    if doc["metadata"].get("name") != d.agent or doc["metadata"].get("namespace") != d.tenant:
        raise LayoutError(f"{d.agent_file}: metadata must name {d.agent} in {d.tenant}")
    return doc


def signer_pin(root: Path, tenant: str) -> dict:
    doc = load_one_plain(root / SIGNERS)
    data = doc.get("data") or {}
    if tenant not in data:
        raise LayoutError(f"{SIGNERS}: no signer pin for tenant {tenant}")
    pin = json.loads(data[tenant])
    pattern = pin.get("subjectRegExp", "")
    if not pattern.startswith("^") or not pattern.endswith("$"):
        raise LayoutError(f"{SIGNERS}: {tenant} subjectRegExp must be anchored")
    return {"issuer": pin.get("issuer"), "subjectRegExp": pattern}


def load_one_plain(path: Path) -> dict:
    docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d is not None]
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise LayoutError(f"{path}: expected exactly one document")
    return docs[0]


def expected_subject(repo: str, tag: str) -> str:
    return f"https://github.com/{repo}/.github/workflows/release.yml@refs/tags/{tag}"


def subject_matches(pin: dict, subject: str) -> bool:
    return re.fullmatch(pin["subjectRegExp"], subject) is not None


def kustomization_resources(d: AgentDir) -> list[str]:
    doc = load_one_plain(d.kustomization)
    resources = doc.get("resources")
    if not isinstance(resources, list) or not all(isinstance(r, str) for r in resources):
        raise LayoutError(f"{d.kustomization}: resources must be a list of file names")
    return resources


def append_resource(d: AgentDir, file_name: str) -> None:
    """Append one entry to the agent kustomization's `resources:` list."""
    append_listed(d.kustomization, file_name)


def listed_resources(path: Path) -> list[str]:
    """The `resources:` of a kustomization whose file ends with that list (so it can be appended to)."""
    doc = load_one_plain(path)
    resources = doc.get("resources")
    if not isinstance(resources, list) or not all(isinstance(r, str) for r in resources):
        raise LayoutError(f"{path}: resources must be a list of file names")
    lines = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    if not lines or not re.match(r"^  - \S+$", lines[-1]):
        raise LayoutError(f"{path}: expected the file to end with the resources list")
    return list(resources)


def append_listed(path: Path, entry: str) -> None:
    """Append one entry to a `resources:` list that ends the file; refuse anything else."""
    if entry in listed_resources(path):
        raise LayoutError(f"{path}: {entry} is already listed")
    lines = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    path.write_text("\n".join(lines) + f"\n  - {entry}\n", encoding="utf-8")
