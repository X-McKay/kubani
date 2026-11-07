"""Strict, non-secret v1 declarations and the stable identity descriptor."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

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


def provision_pair(entry, root):
    """Derive the two identities only from the reviewed consumers."""
    p = entry["provision"]
    fields(
        p,
        [
            "profile",
            "roleManifest",
            "workloadManifest",
            "username",
            "database",
            "host",
            "port",
            "policyDescription",
        ],
    )
    if p["profile"] != "postgres-secret-pair-v1" or "bootstrap" not in entry:
        raise ValueError("unsupported provisioning profile or missing bootstrap")
    for key in ("username", "database"):
        string(p[key], r"[a-z_][a-z0-9_]{0,62}")
    string(p["policyDescription"])
    string(p["host"], r"[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*\.svc\.cluster\.local")
    port(p["port"])
    service, namespace = p["host"].split(".")[:2]
    if not any(
        u["name"] == service and u["namespace"] == namespace and u["port"] == p["port"]
        for u in entry["upstreams"]
    ):
        raise ValueError("provision upstream mismatch")
    if p["roleManifest"] == p["workloadManifest"]:
        raise ValueError("distinct credential paths required")
    for field in ("roleManifest", "workloadManifest"):
        safe_path(root, p[field])
        if p[field] not in entry["secrets"] or not p[field].endswith(".enc.yaml"):
            raise ValueError("provision path must be a declared encrypted Secret")
    workload = [
        v["secretKeyRef"]
        for v in entry["workload"]["secretEnv"]
        if v["name"] == "DATABASE_URI"
    ]
    jobs = [
        d
        for d in yaml_documents(safe_path(root, entry["bootstrap"]["manifest"]))
        if d.get("kind") == "Job"
    ]
    if len(jobs) != 1:
        raise ValueError("unique bootstrap Job required")
    spec = jobs[0]["spec"]["template"]["spec"]
    role = [
        v.get("valueFrom", {}).get("secretKeyRef", {})
        for c in spec.get("containers", []) + spec.get("initContainers", [])
        for v in c.get("env", [])
        if v.get("name") == "MCP_PASSWORD"
    ]
    if (
        len(workload) != 1
        or workload[0].get("key") != "DATABASE_URI"
        or len(role) != 1
        or role[0].get("key") != "password"
    ):
        raise ValueError("unique bounded credential consumer references required")
    for ref in (workload[0], role[0]):
        fields(ref, ["name", "key"], ["optional"])
        if ref.get("optional", False):
            raise ValueError("credential reference must be required")
        name(ref["name"])
    return [
        {
            "path": p["roleManifest"],
            "namespace": entry["bootstrap"]["namespace"],
            "name": role[0]["name"],
            "key": "password",
        },
        {
            "path": p["workloadManifest"],
            "namespace": "mcp",
            "name": workload[0]["name"],
            "key": "DATABASE_URI",
        },
    ]


def _validate(entry, root, *, provisioning=False):
    if (
        isinstance(entry, dict)
        and entry.get("profile") == "existing-streamable-http-v1"
    ):
        from . import references

        return references.validate(entry, root)
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
        ["bootstrap", "provision"],
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
        raise TypeError("secretEnv must be a list")
    seen = set()
    for env in w["secretEnv"]:
        fields(env, ["name", "secretKeyRef"])
        fields(env["secretKeyRef"], ["name", "key"])
        string(env["name"], r"[A-Z_][A-Z0-9_]*")
        name(env["secretKeyRef"]["name"])
        string(env["secretKeyRef"]["key"], r"[A-Za-z0-9_.-]+")
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
    string(a["role"], rf"agent-role-{re.escape(entry['name'])}-[a-z][a-z0-9-]{{0,62}}")
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
    pair = provision_pair(entry, root) if "provision" in entry else []
    available = {}
    absent = [v for v in pair if not safe_path(root, v["path"]).exists()]
    if absent and len(absent) != 2:
        raise ValueError("partial credential pair refused")
    for reference in entry["secrets"]:
        p = safe_path(root, reference)
        if not p.name.endswith(".enc.yaml"):
            raise ValueError("only bespoke SOPS Secret references allowed")
        planned = next((v for v in absent if v["path"] == reference), None)
        if planned and provisioning:
            available[(planned["namespace"], planned["name"])] = {planned["key"]}
            continue
        for d in yaml_documents(p):
            if d.get("kind") != "Secret" or "sops" not in d:
                raise ValueError("encrypted Secret manifest required")
            for v in list(d.get("data", {}).values()) + list(
                d.get("stringData", {}).values()
            ):
                if not isinstance(v, str) or not v.startswith("ENC["):
                    raise ValueError("plaintext Secret prohibited")
            desired = next((v for v in pair if v["path"] == reference), None)
            if desired and (d["metadata"].get("namespace"), d["metadata"]["name"]) != (
                desired["namespace"],
                desired["name"],
            ):
                raise ValueError("provision Secret identity mismatch")
            if desired and desired["key"] not in (
                set(d.get("data", {})) | set(d.get("stringData", {}))
            ):
                raise ValueError("provision Secret key missing")
            available[(d["metadata"].get("namespace"), d["metadata"]["name"])] = set(
                d.get("data", {})
            ) | set(d.get("stringData", {}))
    for env in w["secretEnv"]:
        if env["secretKeyRef"]["key"] not in available.get(
            ("mcp", env["secretKeyRef"]["name"]), set()
        ):
            raise ValueError("missing workload Secret reference")
    if not isinstance(entry["upstreams"], list):
        raise TypeError("upstreams must be explicit list")
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
        string(b["sqlSha256"], r"sha256:[a-f0-9]{64}")
        if not b["name"].endswith("-" + b["revision"]):
            raise ValueError("bootstrap revision/Job name mismatch")
        if (
            "sha256:"
            + hashlib.sha256(safe_path(root, b["sql"]).read_bytes()).hexdigest()
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


def validate(entry, root, *, provisioning=False):
    try:
        return _validate(entry, root, provisioning=provisioning)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid declaration type or structure") from exc


def load_registry(root: Path, *, provisioning=False) -> list[dict]:
    entries = []
    names = set()
    roles = set()
    pairs = set()
    for path in sorted((root / BASE / "backends").glob("*.yaml")):
        safe_path(root, str(path.relative_to(root)))
        docs = yaml_documents(path)
        if len(docs) != 1:
            raise ValueError("one backend declaration per file required")
        e = validate(docs[0], root, provisioning=provisioning)
        if path.stem != e["name"] or e["name"] in names:
            raise ValueError("duplicate name or declaration filename mismatch")
        if e["authorization"]["role"] in roles:
            raise ValueError("backend role collision")
        names.add(e["name"])
        roles.add(e["authorization"]["role"])
        for credential in provision_pair(e, root) if "provision" in e else []:
            identity = (credential["namespace"], credential["name"])
            if identity in pairs or credential["path"] in pairs:
                raise ValueError("credential pair collision")
            pairs.update((identity, credential["path"]))
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


def canonical_sha256(document):
    from . import references

    return references.canonical_sha256(document)


def referenced_objects(root, entry, *, external=False):
    from . import references

    return references.referenced_objects(root, entry, external=external)
