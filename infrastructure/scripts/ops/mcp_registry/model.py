"""Strict, non-secret v1 declarations and the stable identity descriptor."""

from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
import re
import yaml

BASE = "infrastructure/mcp"
LABEL = "app.kubernetes.io/name"


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    result = {}
    for key, value in node.value:
        key = loader.construct_object(key)
        if not isinstance(key, str) or key in result:
            raise ValueError("duplicate or non-string YAML key")
        result[key] = loader.construct_object(value)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def yaml_documents(path):
    try:
        return [
            v
            for v in yaml.load_all(path.read_text(), Loader=UniqueLoader)
            if v is not None
        ]
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {path.name}") from exc


def fields(value, required, optional=()):
    if (
        not isinstance(value, dict)
        or set(value) - set(required) - set(optional)
        or set(required) - set(value)
    ):
        raise ValueError(
            "missing or unknown declaration fields: " + ", ".join(required)
        )


def string(value, pattern=None):
    if (
        not isinstance(value, str)
        or not value
        or "REQUIRED" in value
        or (pattern and not re.fullmatch(pattern, value))
    ):
        raise ValueError("invalid or incomplete string field")


def name(value):
    string(value, r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
    if len(value) > 40:
        raise ValueError("name exceeds 40 characters")


def port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError("invalid port")


def safe_path(root, relative):
    if (
        not isinstance(relative, str)
        or not relative.startswith("infrastructure/")
        or "\\" in relative
    ):
        raise ValueError("unsafe repository path")
    p = PurePosixPath(relative)
    if p.is_absolute() or any(v in (".", "..") for v in p.parts) or str(p) != relative:
        raise ValueError("unsafe repository path")
    target = root / relative
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink traversal refused")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("unsafe repository path")
    return target


def _validate(entry, root):
    fields(
        entry,
        [
            "version",
            "name",
            "profile",
            "workload",
            "authorization",
            "secrets",
            "upstreams",
        ],
        ["bootstrap"],
    )
    if type(entry["version"]) is not int or entry["version"] != 1:
        raise ValueError("unsupported registry version")
    name(entry["name"])
    if entry["profile"] != "container-sse-v1":
        raise ValueError("unsupported transport/auth profile")
    w = entry["workload"]
    fields(w, ["image", "args", "port", "resources", "secretEnv"])
    string(w["image"], r"[^\s]+@sha256:[a-f0-9]{64}")
    port(w["port"])
    if not isinstance(w["args"], list) or not w["args"]:
        raise ValueError("explicit SSE arguments required")
    for arg in w["args"]:
        string(arg)
    if not isinstance(w["secretEnv"], list):
        raise ValueError("secretEnv must be a list")
    seen = set()
    for env in w["secretEnv"]:
        fields(env, ["name", "secret", "key"])
        string(env["name"], r"[A-Z_][A-Z0-9_]*")
        name(env["secret"])
        string(env["key"], r"[A-Za-z0-9_.-]+")
        if env["name"] in seen:
            raise ValueError("duplicate environment name")
        seen.add(env["name"])
    fields(w["resources"], ["requests", "limits"])
    for v in w["resources"].values():
        fields(v, ["cpu", "memory"])
        for quantity in v.values():
            string(quantity, r"[0-9]+(?:\.[0-9]+)?(?:m|Ki|Mi|Gi)?")
    a = entry["authorization"]
    fields(a, ["role", "tools", "scopeDescription"])
    string(a["role"], rf"agent-role-{re.escape(entry["name"])}-[a-z][a-z0-9-]{{0,62}}")
    string(a["scopeDescription"])
    if (
        not isinstance(a["tools"], list)
        or not a["tools"]
        or len(set(a["tools"])) != len(a["tools"])
    ):
        raise ValueError("exact unique tools required")
    for tool in a["tools"]:
        string(tool, r"[A-Za-z_][A-Za-z0-9_.-]*")
    if not isinstance(entry["secrets"], list) or len(set(entry["secrets"])) != len(
        entry["secrets"]
    ):
        raise ValueError("duplicate secret paths")
    available = {}
    for reference in entry["secrets"]:
        p = safe_path(root, reference)
        if not p.name.endswith(".enc.yaml"):
            raise ValueError("only bespoke SOPS Secret references allowed")
        for d in yaml_documents(p):
            if d.get("kind") != "Secret" or "sops" not in d:
                raise ValueError("encrypted Secret manifest required")
            for v in list(d.get("data", {}).values()) + list(
                d.get("stringData", {}).values()
            ):
                if not isinstance(v, str) or not v.startswith("ENC["):
                    raise ValueError("plaintext Secret prohibited")
            available[(d["metadata"].get("namespace"), d["metadata"]["name"])] = set(
                d.get("data", {})
            ) | set(d.get("stringData", {}))
    for env in w["secretEnv"]:
        if env["key"] not in available.get(("mcp", env["secret"]), set()):
            raise ValueError("missing workload Secret reference")
    if not isinstance(entry["upstreams"], list):
        raise ValueError("upstreams must be explicit list")
    seen = set()
    for u in entry["upstreams"]:
        fields(u, ["name", "namespace", "selector", "port"])
        name(u["name"])
        name(u["namespace"])
        port(u["port"])
        if u["name"] in seen:
            raise ValueError("duplicate upstream name")
        seen.add(u["name"])
        if not isinstance(u["selector"], dict) or not u["selector"]:
            raise ValueError("upstream Pod selector required")
        for k, v in u["selector"].items():
            string(k, r"[A-Za-z0-9./_-]+")
            string(v, r"[A-Za-z0-9._-]+")
    if "bootstrap" in entry:
        b = entry["bootstrap"]
        fields(
            b,
            [
                "manifest",
                "name",
                "namespace",
                "revision",
                "sql",
                "sqlSha256",
                "configMap",
                "key",
            ],
        )
        for k in ("name", "namespace", "configMap"):
            name(b[k])
        string(b["revision"], r"v[1-9][0-9]*")
        string(b["key"], r"[A-Za-z0-9_.-]+")
        string(b["sqlSha256"], r"[a-f0-9]{64}")
        if not b["name"].endswith("-" + b["revision"]):
            raise ValueError("bootstrap revision/Job name mismatch")
        if (
            hashlib.sha256(safe_path(root, b["sql"]).read_bytes()).hexdigest()
            != b["sqlSha256"]
        ):
            raise ValueError("bootstrap SQL hash mismatch; review new revision")
        jobs = [
            d
            for d in yaml_documents(safe_path(root, b["manifest"]))
            if d.get("kind") == "Job"
        ]
        if (
            len(jobs) != 1
            or jobs[0]["metadata"]["name"] != b["name"]
            or jobs[0]["metadata"].get("namespace") != b["namespace"]
        ):
            raise ValueError("bootstrap Job identity mismatch")
        volumes = jobs[0]["spec"]["template"]["spec"].get("volumes", [])
        if not any(
            v.get("configMap", {}).get("name") == b["configMap"] for v in volumes
        ):
            raise ValueError("bootstrap ConfigMap reference mismatch")
    return entry


def validate(entry, root):
    try:
        return _validate(entry, root)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid declaration type or structure") from exc


def load_registry(root: Path) -> list[dict]:
    entries = []
    names = set()
    roles = set()
    for path in sorted((root / BASE / "backends").glob("*.yaml")):
        safe_path(root, str(path.relative_to(root)))
        docs = yaml_documents(path)
        if len(docs) != 1:
            raise ValueError("one backend declaration per file required")
        e = validate(docs[0], root)
        if path.stem != e["name"] or e["name"] in names:
            raise ValueError("duplicate name or declaration filename mismatch")
        if e["authorization"]["role"] in roles:
            raise ValueError("backend role collision")
        names.add(e["name"])
        roles.add(e["authorization"]["role"])
        entries.append(e)
    return entries


def scaffold(name: str) -> str:
    globals()["name"](name)
    return yaml.safe_dump(
        {
            "version": 1,
            "name": name,
            "profile": "container-sse-v1",
            "workload": {
                "image": "REQUIRED_IMAGE_AT_SHA256_DIGEST",
                "args": ["REQUIRED_SSE_ARGUMENTS"],
                "port": 8000,
                "resources": {
                    "requests": {"cpu": "50m", "memory": "128Mi"},
                    "limits": {"cpu": "500m", "memory": "512Mi"},
                },
                "secretEnv": [],
            },
            "authorization": {
                "role": f"agent-role-{name}-read",
                "tools": ["REQUIRED_EXACT_TOOL"],
                "scopeDescription": f"MCP backend {name}; optional on agent clients and APS",
            },
            "secrets": [],
            "upstreams": [],
        },
        sort_keys=False,
    )


def descriptor(entry: dict) -> dict:
    n = entry["name"]
    audience = f"https://mcp.almckay.io/{n}/mcp"
    scope = f"mcp:{n}"
    return {
        "role": {
            "name": entry["authorization"]["role"],
            "description": f"MCP backend {n}, read tools",
            "composite": False,
            "clientRole": False,
            "attributes": {},
        },
        "resource": {
            "clientId": audience,
            "name": f"MCP resource: {n}",
            "description": f"Spec 7.7. Target of audience= in exchanges for the {n} backend.",
            "enabled": True,
            "protocol": "openid-connect",
            "bearerOnly": True,
            "publicClient": False,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": False,
        },
        "scope": {
            "name": scope,
            "description": entry["authorization"]["scopeDescription"],
            "protocol": "openid-connect",
            "attributes": {
                "include.in.token.scope": "true",
                "display.on.consent.screen": "false",
            },
            "protocolMappers": [
                {
                    "name": f"aud-{scope}",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-audience-mapper",
                    "consentRequired": False,
                    "config": {
                        "included.custom.audience": audience,
                        "access.token.claim": "true",
                        "id.token.claim": "false",
                        "introspection.token.claim": "true",
                    },
                }
            ],
        },
        "requester": "agent-policy-service",
        "attachment": "optional",
    }
