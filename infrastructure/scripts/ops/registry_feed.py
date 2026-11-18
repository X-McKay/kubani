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

CATALOG = Path("infrastructure/registry/catalog.yaml")
FEED = Path("infrastructure/gitops/apps/agent-platform/workloads/agent-registry-feed.json")
BACKENDS = Path("infrastructure/mcp/backends")
MODEL_CONFIG = Path("infrastructure/gitops/apps/vllm/model-config.yaml")
GATEWAY = Path("infrastructure/gitops/apps/ai-gateway/agents/backends.yaml")
BACKEND_NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")

TOP_KEYS = frozenset({"version", "cluster", "toolServers", "modelEngines", "aliases"})
CLUSTER_KEYS = frozenset({"name", "trustDomain", "gateway", "fluxInventories"})
INVENTORY_KEYS = frozenset({"namespace", "name"})
TOOL_KEYS = frozenset({"name", "namespace", "owner", "description", "source", "manifest", "container", "backend"})
ENGINE_KEYS = frozenset({"name", "namespace", "owner", "description", "source", "workload", "servedNameFrom", "backend"})
SERVED_KEYS = frozenset({"configMap", "key"})
ALIAS_KEYS = frozenset({"alias", "engine"})


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


def _model_engines(root: Path, cluster: str, cat: dict) -> list[dict]:
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
        engines.append(
            {
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
        )
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
        out.append({"cluster": cluster, "alias": entry["alias"], "engine": engine["name"], "backend": engine["backend"]})
    return out


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
    engines = _model_engines(root, cluster["name"], cat)
    aliases = _aliases(cluster["name"], cat, engines)
    tenants, trusted = _tenants_and_trust(root, cluster["name"])
    return {
        "version": 1,
        "clusters": [cluster],
        "tenants": tenants,
        "trustedRepositories": trusted,
        "toolServers": tools,
        "modelEngines": engines,
        "aliases": aliases,
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
