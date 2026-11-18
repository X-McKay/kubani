#!/usr/bin/env python3
"""Render the catalog feed: tenants, trusted repositories, tool servers, model engines and aliases.

The feed is derived from committed manifests and infrastructure/registry/catalog.yaml, which names only what a
manifest cannot say. A separate service reads the JSON; this file only produces it.
Render with: uv run --locked python infrastructure/scripts/ops/registry_feed.py render --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outcome  # noqa: E402
from agent_ops import layout, register  # noqa: E402
from mcp_registry import contract as mcp_contract  # noqa: E402

CATALOG = Path("infrastructure/registry/catalog.yaml")
FEED = Path("infrastructure/gitops/apps/agent-platform/workloads/agent-registry-feed.json")
BACKENDS = Path("infrastructure/mcp/backends")
REVOCATIONS = Path("infrastructure/registry/revocations")
MODEL_CONFIG = Path("infrastructure/gitops/apps/vllm/model-config.yaml")
MODELS = Path("infrastructure/registry/models")
GATEWAY = Path("infrastructure/gitops/apps/ai-gateway/agents/backends.yaml")
BACKEND_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

TOP_KEYS = frozenset({"version", "cluster", "toolServers", "modelEngines", "aliases"})
CLUSTER_KEYS = frozenset({"name", "trustDomain", "gateway", "fluxInventories"})
INVENTORY_KEYS = frozenset({"namespace", "name"})
TOOL_KEYS = frozenset({"name", "namespace", "owner", "description", "source", "manifest", "container", "backend"})
ENGINE_KEYS = frozenset({"name", "namespace", "owner", "description", "source", "workload", "servedNameFrom", "backend"})
SERVED_KEYS = frozenset({"configMap", "key"})
ALIAS_KEYS = frozenset({"alias", "engine"})
MODEL_KEYS = frozenset({"schemaVersion", "engine", "name", "servedName", "weights", "format", "quantisation", "engineImage", "serving", "offers", "evidence"})
MODEL_REQUIRED = frozenset({"schemaVersion", "engine", "name", "servedName", "weights", "engineImage", "offers"})
REVOCATION_KEYS = frozenset({"schemaVersion", "id", "kind", "item", "release", "reason", "sessions", "summary", "revokedBy", "revokedAt"})
REVOCATION_REQUIRED = REVOCATION_KEYS - {"sessions"}
REVOCATION_REASONS = frozenset({"security", "quality"})
REVOCATION_SESSIONS = frozenset({"cancel", "finish"})


def _inside(root: Path, rel) -> Path:
    """A path under root, or ValueError: rendering reads nothing outside the repository."""
    if isinstance(rel, Path):
        rel = rel.as_posix()
    if not isinstance(rel, str) or not rel:
        raise ValueError(f"{rel!r}: a path must be a non-empty string")
    path = (root / rel).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"{rel}: path leaves the repository root")
    return path


def _docs(root: Path, rel) -> list:
    path = _inside(root, rel)
    try:
        return [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d is not None]
    except yaml.YAMLError as exc:
        raise ValueError(f"{rel}: not valid YAML ({type(exc).__name__})") from None


def _require(entry: dict, keys: frozenset, where: str) -> None:
    missing = sorted(keys - set(entry))
    if missing:
        raise ValueError(f"{where}: missing key {', '.join(missing)}")


def _entries(cat: dict, key: str, keys: frozenset, identity: str | None = None) -> list[dict]:
    items = cat[key]
    if not isinstance(items, list):
        raise ValueError(f"{CATALOG}: {key} must be a list")
    seen: set = set()
    for index, item in enumerate(items):
        where = f"{CATALOG}: {key}[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where} must be a mapping")
        _require(item, keys, where)
        if identity is not None:
            if item[identity] in seen:
                raise ValueError(f"{CATALOG}: duplicate name {item[identity]!r} in {key}")
            seen.add(item[identity])
    return items


def _catalog(root: Path) -> dict:
    docs = _docs(root, CATALOG)
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise ValueError(f"{CATALOG}: expected exactly one mapping document")
    cat = docs[0]
    extra = sorted(set(cat) - TOP_KEYS)
    if extra:
        raise ValueError(f"{CATALOG}: unknown top-level key {', '.join(map(str, extra))}")
    _require(cat, TOP_KEYS, CATALOG.as_posix())
    if type(cat["version"]) is not int or cat["version"] != 1:
        raise ValueError(f"{CATALOG}: version must be 1")
    return cat


def _cluster(cat: dict) -> dict:
    cluster = cat["cluster"]
    if not isinstance(cluster, dict):
        raise ValueError(f"{CATALOG}: cluster must be a mapping")
    _require(cluster, CLUSTER_KEYS, f"{CATALOG}: cluster")
    inventories = cluster["fluxInventories"]
    if not isinstance(inventories, list):
        raise ValueError(f"{CATALOG}: cluster.fluxInventories must be a list")
    for index, item in enumerate(inventories):
        if not isinstance(item, dict):
            raise ValueError(f"{CATALOG}: cluster.fluxInventories[{index}] must be a mapping")
        _require(item, INVENTORY_KEYS, f"{CATALOG}: cluster.fluxInventories[{index}]")
    return {
        "name": cluster["name"],
        "trustDomain": cluster["trustDomain"],
        "gateway": cluster["gateway"],
        "fluxInventories": [{"namespace": i["namespace"], "name": i["name"]} for i in inventories],
    }


def _deployment(root: Path, manifest, name: str, namespace: str, where: str) -> dict:
    for doc in _docs(root, manifest):
        if isinstance(doc, dict) and doc.get("kind") == "Deployment":
            meta = doc.get("metadata") or {}
            if meta.get("name") == name and meta.get("namespace") == namespace:
                return doc
    raise ValueError(f"{where}: no Deployment {name} in namespace {namespace} in {manifest}")


def _container_image(deployment: dict, container: str, where: str, manifest) -> str:
    spec = ((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}
    for item in spec.get("containers") or []:
        if isinstance(item, dict) and item.get("name") == container:
            image = item.get("image")
            if not isinstance(image, str) or not image:
                raise ValueError(f"{where}: container {container} in {manifest} has no image")
            return image
    raise ValueError(f"{where}: no container {container} in Deployment in {manifest}")


def _container(deployment: dict, container: str, where: str, manifest) -> dict:
    spec = ((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}
    for item in spec.get("containers") or []:
        if isinstance(item, dict) and item.get("name") == container:
            return item
    raise ValueError(f"{where}: no container {container} in Deployment in {manifest}")


def _contract(root: Path, name: str, backend, image: str, digest: str, where: str):
    """The tool server's contract file as an object, or None when there is none; ValueError when it does not belong to the entry as committed."""
    rel = mcp_contract.contract_path(name)
    path = _inside(root, rel)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise ValueError(f"{rel}: not valid JSON") from None
    if not isinstance(doc, dict) or doc.get("schemaVersion") != mcp_contract.SCHEMA_VERSION or not isinstance(doc.get("tools"), list):
        raise ValueError(f"{rel}: not a tool contract (schemaVersion 1 with a tools list)")
    if doc.get("server") != name:
        raise ValueError(f"{where}: {rel} is the contract of server {doc.get('server')!r}")
    if doc.get("backend") != backend:
        raise ValueError(f"{where}: {rel} names backend {doc.get('backend')!r} but the catalog names {backend!r}")
    if doc.get("configDigest") != digest:
        raise ValueError(f"{where}: {rel} was captured with configDigest {doc.get('configDigest')!r} but the manifest's container has {digest!r}; capture it again (just mcp contract {name})")
    pinned = mcp_contract.image_digest(image)
    if pinned is not None and mcp_contract.image_digest(str(doc.get("image"))) != pinned:
        raise ValueError(f"{where}: {rel} was captured from image {doc.get('image')!r} but the manifest pins {pinned}; capture it again (just mcp contract {name})")
    return doc


def _tool_servers(root: Path, cluster: str, cat: dict) -> list[dict]:
    tools = []
    for entry in _entries(cat, "toolServers", TOOL_KEYS, identity="name"):
        name = entry["name"]
        where = f"{CATALOG}: toolServers {name!r}"
        deployment = _deployment(root, entry["manifest"], name, entry["namespace"], where)
        image = _container_image(deployment, entry["container"], where, entry["manifest"])
        backend = entry["backend"]
        if backend is not None and (not isinstance(backend, str) or not BACKEND_NAME.fullmatch(backend)):
            raise ValueError(f"{where}: backend must be null or a backend name")
        digest = mcp_contract.config_digest(_container(deployment, entry["container"], where, entry["manifest"]))
        tools.append(
            {
                "name": name,
                "cluster": cluster,
                "namespace": entry["namespace"],
                "owner": entry["owner"],
                "description": entry["description"],
                "source": entry["source"],
                "workload": {"apiVersion": "apps/v1", "kind": "Deployment", "name": name},
                "image": image,
                "pinnedByDigest": "@sha256:" in image,
                "registered": backend is not None,
                "backend": backend,
                "configDigest": digest,
                "contract": _contract(root, name, backend, image, digest, where),
            }
        )
    _check_backends(root, tools)
    return tools


def _check_backends(root: Path, tools: list[dict]) -> None:
    """Every backend file is named by exactly one tool server, and every named backend has its file."""
    named: dict[str, str] = {}
    for tool in tools:
        backend = tool["backend"]
        if backend is None:
            continue
        if backend in named:
            raise ValueError(f"{CATALOG}: backend {backend!r} is named by {named[backend]!r} and {tool['name']!r}; exactly one tool server each")
        named[backend] = tool["name"]
        if not _inside(root, BACKENDS / f"{backend}.yaml").is_file():
            raise ValueError(f"{CATALOG}: toolServers {tool['name']!r} names backend {backend!r}; {BACKENDS / (backend + '.yaml')} is missing")
    base = _inside(root, BACKENDS)
    files = sorted(p.stem for p in base.glob("*.yaml") if p.is_file()) if base.is_dir() else []
    for stem in files:
        if stem not in named:
            raise ValueError(f"{BACKENDS / (stem + '.yaml')}: no tool server in {CATALOG} names backend {stem!r}")


def _served_name(root: Path, entry: dict) -> str:
    served = entry["servedNameFrom"]
    where = f"{CATALOG}: modelEngines {entry['name']!r}"
    if not isinstance(served, dict):
        raise ValueError(f"{where}: servedNameFrom must be a mapping")
    _require(served, SERVED_KEYS, f"{where}: servedNameFrom")
    for doc in _docs(root, MODEL_CONFIG):
        if isinstance(doc, dict) and doc.get("kind") == "ConfigMap" and (doc.get("metadata") or {}).get("name") == served["configMap"]:
            value = (doc.get("data") or {}).get(served["key"])
            if not isinstance(value, str) or not value:
                raise ValueError(f"{where}: {MODEL_CONFIG} ConfigMap {served['configMap']} has no key {served['key']}")
            return value
    raise ValueError(f"{where}: no ConfigMap {served['configMap']} in {MODEL_CONFIG}")


def _gateway_model(root: Path, backend: str, where: str) -> str | None:
    for doc in _docs(root, GATEWAY):
        if isinstance(doc, dict) and doc.get("kind") == "AgentgatewayBackend" and (doc.get("metadata") or {}).get("name") == f"agents-{backend}":
            provider = ((doc.get("spec") or {}).get("ai") or {}).get("provider") or {}
            return (provider.get("openai") or {}).get("model")
    raise ValueError(f"{where}: no AgentgatewayBackend agents-{backend} in {GATEWAY}")


def release_slug(served_name: str) -> str:
    """The name a model release keeps its served name under (contract 4.1); also the name of the manifest file."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", served_name).strip("-.")[:128] or "unnamed"


def _model_releases(root: Path, cluster: str) -> list[dict]:
    """One object per infrastructure/registry/models/<engine>/<name>.yaml, sorted by engine and name; [] when there are none."""
    base = _inside(root, MODELS)
    files = sorted(p for p in base.rglob("*.yaml") if p.is_file()) if base.is_dir() else []
    out = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(base).parts
        if len(parts) != 2:
            raise ValueError(f"{rel}: a manifest lives at {MODELS}/<engine>/<name>.yaml")
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            raise ValueError(f"{rel}: not valid YAML") from None
        if not isinstance(doc, dict):
            raise ValueError(f"{rel}: must be one mapping")
        missing = sorted(MODEL_REQUIRED - set(doc))
        if missing:
            raise ValueError(f"{rel}: missing key {', '.join(missing)}")
        extra = sorted(set(doc) - MODEL_KEYS)
        if extra:
            raise ValueError(f"{rel}: unknown key {', '.join(map(str, extra))}")
        if type(doc["schemaVersion"]) is not int or doc["schemaVersion"] != 1:
            raise ValueError(f"{rel}: schemaVersion must be 1")
        if doc["engine"] != parts[0]:
            raise ValueError(f"{rel}: engine {doc['engine']!r} must equal its directory {parts[0]!r}")
        if doc["name"] != path.stem:
            raise ValueError(f"{rel}: name {doc['name']!r} must equal the file name without .yaml")
        if release_slug(doc["name"]) != doc["name"]:
            raise ValueError(f"{rel}: name {doc['name']!r} is not a release slug")
        for key in ("servedName", "engineImage"):
            if not isinstance(doc[key], str) or not doc[key]:
                raise ValueError(f"{rel}: {key} must be a non-empty string")
        weights = doc["weights"]
        if not isinstance(weights, dict) or not isinstance(weights.get("source"), str) or not weights["source"]:
            raise ValueError(f"{rel}: weights.source is required")
        if not isinstance(doc["offers"], dict):
            raise ValueError(f"{rel}: offers must be a mapping")
        out.append({"cluster": cluster, **doc})
    return sorted(out, key=lambda d: (d["engine"], d["name"]))


def _check_release(root: Path, entry: dict, served: str, releases: list[dict], where: str) -> None:
    """The engine's `release` names a manifest of this engine with its served name and its container's image."""
    name = entry["release"]
    if not isinstance(name, str) or not name:
        raise ValueError(f"{where}: release must be a manifest name")
    found = [r for r in releases if r["name"] == name]
    if not found:
        raise ValueError(f"{where}: release {name!r} names no manifest in {MODELS}")
    manifest = next((r for r in found if r["engine"] == entry["name"]), None)
    if manifest is None:
        raise ValueError(f"{where}: release {name!r} is a manifest of engine {found[0]['engine']!r}, not of {entry['name']!r}")
    if manifest["servedName"] != served:
        raise ValueError(f"{where}: release {name!r} serves {manifest['servedName']!r} but the engine serves {served!r}; a changed served name needs a new manifest")
    if not entry.get("manifest") or not entry.get("container"):
        raise ValueError(f"{where}: release needs manifest and container, to compare the manifest's engineImage with the container's")
    deployment = _deployment(root, entry["manifest"], entry["workload"], entry["namespace"], where)
    image = _container_image(deployment, entry["container"], where, entry["manifest"])
    if manifest["engineImage"] != image:
        raise ValueError(f"{where}: release {name!r} has engineImage {manifest['engineImage']!r} but the container runs {image!r}; a changed engine image needs a new manifest")


def _model_engines(root: Path, cluster: str, cat: dict, releases: list[dict]) -> list[dict]:
    engines = []
    for entry in _entries(cat, "modelEngines", ENGINE_KEYS, identity="name"):
        where = f"{CATALOG}: modelEngines {entry['name']!r}"
        served = _served_name(root, entry)
        backend = entry["backend"]
        if backend is not None:
            if not isinstance(backend, str) or not BACKEND_NAME.fullmatch(backend):
                raise ValueError(f"{where}: backend must be null or a backend name")
            model = _gateway_model(root, backend, where)
            if model != served:
                raise ValueError(f"{where}: gateway agents-{backend} routes model {model!r} but the engine serves {served!r} ({MODEL_CONFIG})")
        out = {
            "name": entry["name"],
            "cluster": cluster,
            "namespace": entry["namespace"],
            "owner": entry["owner"],
            "description": entry["description"],
            "source": entry["source"],
            "workload": {"apiVersion": "apps/v1", "kind": "Deployment", "name": entry["workload"]},
            "servedName": served,
            "servedNameFrom": {"kind": "ConfigMap", "name": entry["servedNameFrom"]["configMap"], "key": entry["servedNameFrom"]["key"]},
            "backend": backend,
        }
        if entry.get("release") is not None:
            _check_release(root, entry, served, releases, where)
            out["release"] = entry["release"]
        engines.append(out)
    for release in releases:
        if release["engine"] not in {e["name"] for e in engines}:
            raise ValueError(f"{MODELS}/{release['engine']}/{release['name']}.yaml: no model engine {release['engine']!r} in {CATALOG}")
    return engines


def _aliases(cluster: str, cat: dict, engines: list[dict]) -> list[dict]:
    by_name = {engine["name"]: engine for engine in engines}
    out = []
    for entry in _entries(cat, "aliases", ALIAS_KEYS):
        where = f"{CATALOG}: aliases {entry['alias']!r}"
        engine = by_name.get(entry["engine"])
        if engine is None:
            raise ValueError(f"{where}: unknown model engine {entry['engine']!r}")
        if engine["backend"] is None:
            raise ValueError(f"{where}: model engine {entry['engine']!r} has no backend")
        alias = {"cluster": cluster, "alias": entry["alias"], "engine": engine["name"], "backend": engine["backend"]}
        if entry.get("move") is not None:
            if not isinstance(entry["move"], str) or not entry["move"]:
                raise ValueError(f"{where}: move must be an alias move id")
            alias["move"] = entry["move"]
        out.append(alias)
    return out


class _TextLoader(yaml.SafeLoader):
    """SafeLoader that leaves timestamps as the text written, so the feed carries revokedAt unchanged."""


_TextLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _revocations(root: Path) -> list[dict]:
    """One object per infrastructure/registry/revocations/*.yaml, in id order (delivery.md 8.1); [] when there are none."""
    base = _inside(root, REVOCATIONS)
    files = sorted(p for p in base.glob("*.yaml") if p.is_file()) if base.is_dir() else []
    out = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_TextLoader)  # noqa: S506 - SafeLoader subclass
        except yaml.YAMLError:
            raise ValueError(f"{rel}: not valid YAML") from None
        if not isinstance(doc, dict):
            raise ValueError(f"{rel}: must be one mapping")
        missing = sorted(REVOCATION_REQUIRED - set(doc))
        if missing:
            raise ValueError(f"{rel}: missing key {', '.join(missing)}")
        extra = sorted(set(doc) - REVOCATION_KEYS)
        if extra:
            raise ValueError(f"{rel}: unknown key {', '.join(map(str, extra))}")
        if type(doc["schemaVersion"]) is not int or doc["schemaVersion"] != 1:
            raise ValueError(f"{rel}: schemaVersion must be 1")
        if doc["id"] != path.stem:
            raise ValueError(f"{rel}: id {doc['id']!r} must equal the file name without .yaml")
        if doc["reason"] not in REVOCATION_REASONS:
            raise ValueError(f"{rel}: reason must be security or quality")
        if "sessions" in doc and doc["sessions"] not in REVOCATION_SESSIONS:
            raise ValueError(f"{rel}: sessions must be cancel or finish")
        out.append(doc)
    return sorted(out, key=lambda d: d["id"])


def _tenant_pins(root: Path) -> dict[str, dict]:
    """Each tenant's pin: issuer and subjectRegExp from layout.signer_pin, vulnExceptions from the same pin JSON."""
    data = layout.load_one_plain(_inside(root, layout.SIGNERS)).get("data") or {}
    pins = {}
    for tenant in sorted(register.pinned_tenants(root)):
        pin = layout.signer_pin(root, tenant)
        vulns = json.loads(data[tenant]).get("vulnExceptions")
        if not isinstance(vulns, list):
            raise ValueError(f"{layout.SIGNERS}: {tenant} has no vulnExceptions list")
        pins[tenant] = {"issuer": pin["issuer"], "subjectRegExp": pin["subjectRegExp"], "vulnExceptions": vulns}
    return pins


def _tenants_and_trust(root: Path, cluster: str) -> tuple[list[dict], list[dict]]:
    tenants, trusted = [], []
    for tenant, pin in _tenant_pins(root).items():
        tenants.append(
            {
                "cluster": cluster,
                "name": tenant,
                "namespace": tenant,
                "policy": {"signer": {"issuer": pin["issuer"], "subjectRegExp": pin["subjectRegExp"]}, "vulnExceptions": pin["vulnExceptions"]},
            }
        )
        for repository, agents in sorted(register.sources(root, tenant).items()):
            names = sorted(agents)
            trusted.append(
                {
                    "repository": repository,
                    "cluster": cluster,
                    "tenant": tenant,
                    "issuer": pin["issuer"],
                    "subjectRegExp": register.subject_regexp({repository: tuple(names)}),
                    "agents": names,
                }
            )
    return tenants, trusted


def render(root: Path) -> dict:
    """The feed as a dict, from the files under root. Raises ValueError naming the entry and file on any failed check."""
    root = Path(root).resolve()
    cat = _catalog(root)
    cluster = _cluster(cat)
    tools = _tool_servers(root, cluster["name"], cat)
    releases = _model_releases(root, cluster["name"])
    engines = _model_engines(root, cluster["name"], cat, releases)
    aliases = _aliases(cluster["name"], cat, engines)
    tenants, trusted = _tenants_and_trust(root, cluster["name"])
    return {
        "version": 1,
        "clusters": [cluster],
        "tenants": tenants,
        "trustedRepositories": trusted,
        "toolServers": tools,
        "modelReleases": releases,
        "modelEngines": engines,
        "aliases": aliases,
        "revocations": _revocations(root),
    }


def feed_bytes(feed: dict) -> bytes:
    return (json.dumps(feed, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def emit(document) -> None:
    print(json.dumps(document, sort_keys=True))


class Parser(argparse.ArgumentParser):
    """argparse, which still prints usage to stderr and exits 2, plus the `invalid-arguments` document on stdout."""

    def error(self, message):
        emit(outcome.document({}, outcome.error("invalid-arguments", outcome.usage_message(message))))
        super().error(message)


def parser() -> argparse.ArgumentParser:
    result = Parser(description=__doc__)
    result.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    commands = result.add_subparsers(dest="command", required=True)
    render_cmd = commands.add_parser("render", help="deterministic catalog feed JSON")
    mode = render_cmd.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    return result


def _fail(code: str, message: str) -> int:
    emit(outcome.document({}, outcome.error(code, message)))
    return 1


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    try:
        data = feed_bytes(render(root))
    except outcome.Coded as exc:
        return _fail(exc.code, str(exc))
    except ValueError as exc:
        return _fail("validation-failed", str(exc))
    except OSError as exc:
        code = "not-found" if isinstance(exc, FileNotFoundError) else "failed"
        return _fail(code, f"a file could not be read ({type(exc).__name__})")
    target = root / FEED
    if args.write:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as exc:
            return _fail("failed", f"the feed could not be written ({type(exc).__name__})")
        emit(outcome.document({"status": "rendered", "file": str(FEED)}))
        return 0
    current = target.read_bytes() if target.is_file() else None
    if current == data:
        emit(outcome.document({"status": "current"}))
        return 0
    state = "missing" if current is None else "stale"
    emit(
        outcome.document(
            {"status": "stale", "file": str(FEED)},
            outcome.error(
                "check-failed",
                f"{FEED} is missing or differs from the catalog and manifests; run render --write",
                proofs=[{"path": str(FEED), "state": state}],
            ),
        )
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
