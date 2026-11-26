"""Committed layout of applied agents: apps/agents/<tenant>/<agent>/."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

import outcome

AGENTS_DIR = Path("infrastructure/gitops/apps/agents")
SIGNERS = Path("infrastructure/gitops/infrastructure/kyverno/tenant-signers.yaml")
POLICY_SERVICE = Path("infrastructure/gitops/apps/agent-platform/workloads/agent-policy-service.yaml")
BACKEND_CATALOGUE = "APS_BACKEND_CATALOGUE"
BUDGET_FIELDS = ("tokensPerSession", "tokensPerDay")
AGENT_CRD = Path("infrastructure/gitops/infrastructure/agent-platform-crds/agents.agentplatform.io.yaml")
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


class LayoutError(outcome.Coded):
    """The committed tree does not have the expected shape."""

    default_code = "validation-failed"


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
        raise LayoutError(f"{base} is missing", "not-found")
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
        raise LayoutError(f"agent {agent!r}: expected exactly one committed directory, found {len(matches)}", "not-found" if not matches else "conflict")
    return matches[0]


def find_release(root: Path, name: str) -> tuple[AgentDir, Path, dict]:
    hits = []
    for d in agent_dirs(root):
        for file in d.release_files():
            doc = load_one(file, "AgentRelease")
            if doc["metadata"].get("name") == name:
                hits.append((d, file, doc))
    if len(hits) != 1:
        raise LayoutError(f"AgentRelease {name!r}: expected exactly one committed file, found {len(hits)}", "not-found" if not hits else "conflict")
    return hits[0]


def committed_agent(d: AgentDir) -> dict:
    doc = load_one(d.agent_file, "Agent")
    if doc["metadata"].get("name") != d.agent or doc["metadata"].get("namespace") != d.tenant:
        raise LayoutError(f"{d.agent_file}: metadata must name {d.agent} in {d.tenant}")
    return doc


def backend_reservations(root: Path) -> dict[str, int]:
    """Backend -> the tokens the policy service reserves for each call to it (`maxModelLen`), as the policy service's own
    manifest in `root` declares them in APS_BACKEND_CATALOGUE."""
    path = root / POLICY_SERVICE
    try:
        docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if isinstance(d, dict)]
    except OSError as exc:
        raise LayoutError(f"{POLICY_SERVICE}: {exc.strerror or type(exc).__name__}", "not-found") from None
    except yaml.YAMLError as exc:
        raise LayoutError(f"{POLICY_SERVICE}: not valid YAML: {exc}") from None
    values = [
        env.get("value")
        for doc in docs
        if doc.get("kind") == "Deployment"
        for container in (((doc.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []
        for env in container.get("env") or []
        if isinstance(env, dict) and env.get("name") == BACKEND_CATALOGUE
    ]
    if len(values) != 1 or not isinstance(values[0], str):
        raise LayoutError(f"{POLICY_SERVICE}: expected exactly one {BACKEND_CATALOGUE} value on the Deployment, found {len(values)}")
    try:
        catalogue = json.loads(values[0])
        return {backend: entry["maxModelLen"] for backend, entry in catalogue.items() if isinstance(entry["maxModelLen"], int)}
    except (ValueError, AttributeError, KeyError, TypeError):
        raise LayoutError(f"{POLICY_SERVICE}: {BACKEND_CATALOGUE} is not an object of backends that each carry an integer maxModelLen") from None


def budget_problems(root: Path, doc: dict) -> list[str]:
    """Why a call to a model backend of this Agent could never be admitted, one message per problem; empty when none.

    The policy service reserves the backend's whole context length for every call, so a session or day budget below it
    admits nothing, and a backend the catalogue does not list is refused outright. A grant with no budget is skipped."""
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    models = (spec.get("capabilities") or {}).get("models") or []
    if not models:
        return []
    name = (doc.get("metadata") or {}).get("name") or "agent"
    reserved = backend_reservations(root)
    problems = []
    for grant in models:
        if not isinstance(grant, dict):
            continue
        backend = grant.get("backend")
        if backend not in reserved:
            problems.append(f"{name}: model grant names backend {backend}, which is not in {BACKEND_CATALOGUE}; the policy service would refuse every call. Use a backend the catalogue lists ({', '.join(sorted(reserved))})")
            continue
        budget = grant.get("budget")
        for field in BUDGET_FIELDS:
            declared = budget.get(field) if isinstance(budget, dict) else None
            if isinstance(declared, int) and not isinstance(declared, bool) and declared < reserved[backend]:
                problems.append(f"{name}: {field} {declared} is below the {reserved[backend]} tokens reserved for each call to {backend} ({BACKEND_CATALOGUE}); no call would be admitted. Raise the budget in the agent's source and release a new version")
    return problems


def _with_defaults(value, schema: dict):
    """A value with the schema's defaults filled in, the way the API server fills them: a default applies to a property
    that is missing from a mapping which is itself present."""
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        result = {key: _with_defaults(item, properties.get(key) or {}) for key, item in value.items()}
        for key, prop in properties.items():
            if "default" in prop and result.get(key) is None:
                result[key] = copy.deepcopy(prop["default"])
        return result
    if isinstance(value, list):
        return [_with_defaults(item, schema.get("items") or {}) for item in value]
    return copy.deepcopy(value)


def applied_agent(root: Path, d: AgentDir) -> dict:
    """The committed Agent as the cluster and the registry hold it: apiVersion, kind, name, namespace and the spec with
    the defaults of the committed Agent definition filled in."""
    doc = committed_agent(d)
    version = doc["apiVersion"].partition("/")[2]
    versions = (load_one_plain(root / AGENT_CRD).get("spec") or {}).get("versions") or []
    schemas = [((v.get("schema") or {}).get("openAPIV3Schema") or {}).get("properties", {}).get("spec") for v in versions if isinstance(v, dict) and v.get("name") == version]
    if len(schemas) != 1 or not isinstance(schemas[0], dict):
        raise LayoutError(f"{AGENT_CRD}: expected one {version} schema with a spec")
    return {
        "apiVersion": doc["apiVersion"],
        "kind": doc["kind"],
        "metadata": {"name": d.agent, "namespace": d.tenant},
        "spec": _with_defaults(doc["spec"], schemas[0]),
    }


def signer_pin(root: Path, tenant: str) -> dict:
    doc = load_one_plain(root / SIGNERS)
    data = doc.get("data") or {}
    if tenant not in data:
        raise LayoutError(f"{SIGNERS}: no signer pin for tenant {tenant}", "not-found")
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


AGENTS_LIST = AGENTS_DIR / "kustomization.yaml"


def list_entry(d: AgentDir) -> str:
    return f"{d.tenant}/{d.agent}"


def _same_entry(text: str, d: AgentDir) -> bool:
    return text.removeprefix("./").rstrip("/") == list_entry(d)


def is_listed(root: Path, d: AgentDir) -> bool:
    """Whether `apps/agents/kustomization.yaml` lists the agent's directory: the pull request path owns it. An unlisted directory belongs to the registry."""
    return any(_same_entry(entry, d) for entry in load_one_plain(root / AGENTS_LIST).get("resources") or [] if isinstance(entry, str))


def unlist(root: Path, d: AgentDir) -> None:
    """Remove the agent's one line from `apps/agents/kustomization.yaml`; every other line stays as it is."""
    path = root / AGENTS_LIST
    lines = path.read_text(encoding="utf-8").split("\n")
    hits = [i for i, line in enumerate(lines) if re.match(r"^  - \S+\s*$", line) and _same_entry(line[4:].strip(), d)]
    if len(hits) != 1:
        raise LayoutError(f"{path}: expected exactly one line listing {list_entry(d)}, found {len(hits)}")
    del lines[hits[0]]
    path.write_text("\n".join(lines), encoding="utf-8")


def relist(root: Path, d: AgentDir) -> None:
    """List the agent's directory again, at the end of `apps/agents/kustomization.yaml`."""
    append_listed(root / AGENTS_LIST, list_entry(d) + "/")
