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


def fields(value, required, optional=(), path="definition"):
    """Refuse a non-mapping, missing fields or unknown fields, naming the fields (never their values)."""
    if not isinstance(value, dict):
        raise ValueError(f"{path}: must be a mapping")
    missing = ", ".join(f for f in required if f not in value)
    unknown = ", ".join(
        sorted(str(k)[:40] for k in set(value) - set(required) - set(optional))
    )
    if missing and unknown:
        raise ValueError(
            f"{path}: missing field(s) {missing}; unknown field(s) {unknown}"
        )
    if missing:
        raise ValueError(f"{path}: missing field(s) {missing}")
    if unknown:
        raise ValueError(f"{path}: unknown field(s) {unknown}")


def string(value, pattern=None, path="value", expect="a non-empty string"):
    """Refuse a value that is not `expect`; the message names `path`, never the value."""
    if isinstance(value, str) and "REQUIRED" in value:
        raise ValueError(
            f"{path}: still holds a REQUIRED placeholder; replace it with {expect}"
        )
    if (
        not isinstance(value, str)
        or not value
        or (pattern and not re.fullmatch(pattern, value))
    ):
        raise ValueError(f"{path}: must be {expect}")


def name(value, path="name"):
    string(
        value,
        r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*",
        path,
        "a lower-case name of letters, digits and single dashes, starting with a letter",
    )
    if len(value) > 40:
        raise ValueError(f"{path}: must be at most 40 characters")


def port(value, path="port"):
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError(f"{path}: must be an integer from 1 to 65535")


def safe_path(root, relative, where="path"):
    if (
        not isinstance(relative, str)
        or not relative.startswith("infrastructure/")
        or "\\" in relative
    ):
        raise ValueError(
            f"{where}: must be a repository path under infrastructure/ without backslashes"
        )
    p = PurePosixPath(relative)
    if p.is_absolute() or any(v in (".", "..") for v in p.parts) or str(p) != relative:
        raise ValueError(f"{where}: must be a canonical path without . or .. parts")
    target = root / relative
    current = root
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{where}: a component of the path is a symlink; refused")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"{where}: resolves outside the repository")
    return target


def require_file(path, relative, where):
    """A declared file must exist; the declared path is shown so it can be found."""
    if not path.is_file():
        raise ValueError(f"{where}: declared file is not an existing file: {relative}")


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
        path="provision",
    )
    if p["profile"] != "postgres-secret-pair-v1":
        raise ValueError("provision.profile: must be postgres-secret-pair-v1")
    if "bootstrap" not in entry:
        raise ValueError(
            "provision: needs a bootstrap section (the reviewed Job that creates the role)"
        )
    for key in ("username", "database"):
        string(
            p[key],
            r"[a-z_][a-z0-9_]{0,62}",
            f"provision.{key}",
            "a lower-case database identifier (letters, digits, underscores; at most 63 characters)",
        )
    string(p["policyDescription"], None, "provision.policyDescription", "a non-empty description")
    string(
        p["host"],
        r"[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*\.svc\.cluster\.local",
        "provision.host",
        "a cluster-local host of the form <service>.<namespace>.svc.cluster.local",
    )
    port(p["port"], "provision.port")
    service, namespace = p["host"].split(".")[:2]
    if not any(
        u["name"] == service and u["namespace"] == namespace and u["port"] == p["port"]
        for u in entry["upstreams"]
    ):
        raise ValueError(
            "provision.host and provision.port: no entry in upstreams has this service, namespace and port"
        )
    if p["roleManifest"] == p["workloadManifest"]:
        raise ValueError(
            "provision.roleManifest and provision.workloadManifest: must be two different paths"
        )
    for field in ("roleManifest", "workloadManifest"):
        safe_path(root, p[field], f"provision.{field}")
        if p[field] not in entry["secrets"]:
            raise ValueError(f"provision.{field}: must also be listed in secrets")
        if not p[field].endswith(".enc.yaml"):
            raise ValueError(f"provision.{field}: must end in .enc.yaml")
    workload = [
        v["secretKeyRef"]
        for v in entry["workload"]["secretEnv"]
        if v["name"] == "DATABASE_URI"
    ]
    manifest = safe_path(root, entry["bootstrap"]["manifest"], "bootstrap.manifest")
    require_file(manifest, entry["bootstrap"]["manifest"], "bootstrap.manifest")
    jobs = [d for d in yaml_documents(manifest) if d.get("kind") == "Job"]
    if len(jobs) != 1:
        raise ValueError(
            f"bootstrap.manifest: expected exactly 1 Job to find the role credential consumer, found {len(jobs)}"
        )
    spec = jobs[0]["spec"]["template"]["spec"]
    role = [
        v.get("valueFrom", {}).get("secretKeyRef", {})
        for c in spec.get("containers", []) + spec.get("initContainers", [])
        for v in c.get("env", [])
        if v.get("name") == "MCP_PASSWORD"
    ]
    consumer = "workload.secretEnv[DATABASE_URI].secretKeyRef"
    job_consumer = "bootstrap.manifest Job env MCP_PASSWORD secretKeyRef"
    if len(workload) != 1:
        raise ValueError(
            f"workload.secretEnv: expected exactly 1 entry named DATABASE_URI, found {len(workload)}"
        )
    if workload[0].get("key") != "DATABASE_URI":
        raise ValueError(f"{consumer}.key: must be DATABASE_URI")
    if len(role) != 1:
        raise ValueError(
            f"bootstrap.manifest: expected exactly 1 MCP_PASSWORD env var in the Job, found {len(role)}"
        )
    if role[0].get("key") != "password":
        raise ValueError(f"{job_consumer}.key: must be password")
    for where, ref in ((consumer, workload[0]), (job_consumer, role[0])):
        fields(ref, ["name", "key"], ["optional"], where)
        if ref.get("optional", False):
            raise ValueError(
                f"{where}.optional: must not be true; the credential reference is required"
            )
        name(ref["name"], f"{where}.name")
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
        raise ValueError("version: must be the integer 1")
    name(entry["name"], "name")
    if entry["profile"] != "container-sse-v1":
        raise ValueError(
            "profile: must be container-sse-v1 (or existing-streamable-http-v1 for the reviewed Kubernetes backend)"
        )
    w = entry["workload"]
    fields(w, ["image", "args", "port", "resources", "secretEnv"], path="workload")
    string(
        w["image"],
        r"[^\s]+@sha256:[a-f0-9]{64}",
        "workload.image",
        "an image reference pinned by digest, <image>@sha256:<64 hex digits>",
    )
    port(w["port"], "workload.port")
    if not isinstance(w["args"], list) or not w["args"]:
        raise ValueError("workload.args: must be a non-empty list of SSE server arguments")
    for i, arg in enumerate(w["args"]):
        string(arg, None, f"workload.args[{i}]", "a non-empty argument")
    if not isinstance(w["secretEnv"], list):
        raise ValueError("workload.secretEnv: must be a list")
    seen = set()
    for i, env in enumerate(w["secretEnv"]):
        at = f"workload.secretEnv[{i}]"
        fields(env, ["name", "secretKeyRef"], path=at)
        fields(env["secretKeyRef"], ["name", "key"], path=f"{at}.secretKeyRef")
        string(
            env["name"],
            r"[A-Z_][A-Z0-9_]*",
            f"{at}.name",
            "an environment variable name (upper-case letters, digits, underscores)",
        )
        name(env["secretKeyRef"]["name"], f"{at}.secretKeyRef.name")
        string(
            env["secretKeyRef"]["key"],
            r"[A-Za-z0-9_.-]+",
            f"{at}.secretKeyRef.key",
            "a Secret key (letters, digits, underscores, dots, dashes)",
        )
        if env["name"] in seen:
            raise ValueError(f"{at}.name: duplicate of an earlier secretEnv entry")
        seen.add(env["name"])
    fields(w["resources"], ["requests", "limits"], path="workload.resources")
    for kind, v in w["resources"].items():
        fields(v, ["cpu", "memory"], path=f"workload.resources.{kind}")
        for resource, quantity in v.items():
            string(
                quantity,
                r"[0-9]+(?:\.[0-9]+)?(?:m|Ki|Mi|Gi)?",
                f"workload.resources.{kind}.{resource}",
                "a Kubernetes quantity such as 500m, 128Mi or 1",
            )
    a = entry["authorization"]
    fields(a, ["role", "tools", "scopeDescription"], path="authorization")
    string(
        a["role"],
        rf"agent-role-{re.escape(entry['name'])}-[a-z][a-z0-9-]{{0,62}}",
        "authorization.role",
        "agent-role-<backend name>-<suffix> with a lower-case suffix of letters, digits and dashes",
    )
    string(a["scopeDescription"], None, "authorization.scopeDescription", "a non-empty description")
    if not isinstance(a["tools"], list) or not a["tools"]:
        raise ValueError("authorization.tools: must be a non-empty list of tool names")
    for i, tool in enumerate(a["tools"]):
        string(
            tool,
            r"[A-Za-z_][A-Za-z0-9_.-]*",
            f"authorization.tools[{i}]",
            "a tool name (letters, digits, underscores, dots, dashes; not starting with a digit)",
        )
    if len(set(a["tools"])) != len(a["tools"]):
        raise ValueError("authorization.tools: entries must be unique")
    if not isinstance(entry["secrets"], list):
        raise ValueError("secrets: must be a list")
    if len(set(entry["secrets"])) != len(entry["secrets"]):
        raise ValueError("secrets: entries must be unique")
    pair = provision_pair(entry, root) if "provision" in entry else []
    available = {}
    absent = [
        v for v in pair if not safe_path(root, v["path"], "provision").exists()
    ]
    if absent and len(absent) != 2:
        raise ValueError(
            "provision.roleManifest and provision.workloadManifest: only one of the two Secret files exists; both or neither are required"
        )
    for i, reference in enumerate(entry["secrets"]):
        at = f"secrets[{i}]"
        p = safe_path(root, reference, at)
        if not p.name.endswith(".enc.yaml"):
            raise ValueError(f"{at}: must end in .enc.yaml (a SOPS-encrypted Secret)")
        planned = next((v for v in absent if v["path"] == reference), None)
        if planned and provisioning:
            available[(planned["namespace"], planned["name"])] = {planned["key"]}
            continue
        require_file(p, reference, at)
        for d in yaml_documents(p):
            if d.get("kind") != "Secret" or "sops" not in d:
                raise ValueError(
                    f"{at}: every document must be a Secret manifest with a sops block"
                )
            for v in list(d.get("data", {}).values()) + list(
                d.get("stringData", {}).values()
            ):
                if not isinstance(v, str) or not v.startswith("ENC["):
                    raise ValueError(
                        f"{at}: every Secret value must be SOPS ciphertext (ENC[...]); a plaintext value is prohibited"
                    )
            desired = next((v for v in pair if v["path"] == reference), None)
            if desired and (d["metadata"].get("namespace"), d["metadata"]["name"]) != (
                desired["namespace"],
                desired["name"],
            ):
                raise ValueError(
                    f"{at}: the Secret's namespace and name do not match the consumer that provision derives them from"
                )
            if desired and desired["key"] not in (
                set(d.get("data", {})) | set(d.get("stringData", {}))
            ):
                raise ValueError(
                    f"{at}: the Secret lacks the key its consumer reads (password for the role, DATABASE_URI for the workload)"
                )
            available[(d["metadata"].get("namespace"), d["metadata"]["name"])] = set(
                d.get("data", {})
            ) | set(d.get("stringData", {}))
    for i, env in enumerate(w["secretEnv"]):
        if env["secretKeyRef"]["key"] not in available.get(
            ("mcp", env["secretKeyRef"]["name"]), set()
        ):
            raise ValueError(
                f"workload.secretEnv[{i}].secretKeyRef: no Secret listed in secrets supplies this name and key in namespace mcp"
            )
    if not isinstance(entry["upstreams"], list):
        raise ValueError("upstreams: must be a list")
    seen = set()
    for i, u in enumerate(entry["upstreams"]):
        at = f"upstreams[{i}]"
        fields(u, ["name", "namespace", "selector", "port"], path=at)
        name(u["name"], f"{at}.name")
        name(u["namespace"], f"{at}.namespace")
        port(u["port"], f"{at}.port")
        if u["name"] in seen:
            raise ValueError(f"{at}.name: duplicate of an earlier upstream")
        seen.add(u["name"])
        if not isinstance(u["selector"], dict) or not u["selector"]:
            raise ValueError(f"{at}.selector: must be a non-empty mapping of Pod labels")
        for k, v in u["selector"].items():
            string(
                k,
                r"[A-Za-z0-9./_-]+",
                f"{at}.selector keys",
                "a label key such as app.kubernetes.io/name",
            )
            string(
                v,
                r"[A-Za-z0-9._-]+",
                f"{at}.selector values",
                "a label value (letters, digits, dots, underscores, dashes)",
            )
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
            path="bootstrap",
        )
        for k in ("name", "namespace", "configMap"):
            name(b[k], f"bootstrap.{k}")
        string(b["revision"], r"v[1-9][0-9]*", "bootstrap.revision", "v followed by a positive integer, such as v1")
        string(
            b["key"],
            r"[A-Za-z0-9_.-]+",
            "bootstrap.key",
            "a ConfigMap key (letters, digits, underscores, dots, dashes)",
        )
        string(
            b["sqlSha256"],
            r"sha256:[a-f0-9]{64}",
            "bootstrap.sqlSha256",
            "sha256: followed by 64 lower-case hex digits",
        )
        if not b["name"].endswith("-" + b["revision"]):
            raise ValueError("bootstrap.name: must end in - followed by bootstrap.revision")
        sql = safe_path(root, b["sql"], "bootstrap.sql")
        require_file(sql, b["sql"], "bootstrap.sql")
        if "sha256:" + hashlib.sha256(sql.read_bytes()).hexdigest() != b["sqlSha256"]:
            raise ValueError(
                "bootstrap.sqlSha256: does not match the SHA-256 of the bootstrap.sql file; review the change and set a new bootstrap.revision"
            )
        manifest = safe_path(root, b["manifest"], "bootstrap.manifest")
        require_file(manifest, b["manifest"], "bootstrap.manifest")
        jobs = [d for d in yaml_documents(manifest) if d.get("kind") == "Job"]
        if len(jobs) != 1:
            raise ValueError(
                f"bootstrap.manifest: expected exactly 1 Job, found {len(jobs)}"
            )
        if jobs[0]["metadata"]["name"] != b["name"]:
            raise ValueError(
                "bootstrap.manifest: expected the Job's metadata.name to equal bootstrap.name, found a different name"
            )
        if jobs[0]["metadata"].get("namespace") != b["namespace"]:
            raise ValueError(
                "bootstrap.manifest: expected the Job's metadata.namespace to equal bootstrap.namespace, found a different namespace"
            )
        volumes = jobs[0]["spec"]["template"]["spec"].get("volumes", [])
        if not any(
            v.get("configMap", {}).get("name") == b["configMap"] for v in volumes
        ):
            raise ValueError(
                "bootstrap.configMap: expected the Job to mount a ConfigMap volume of this name, found none"
            )
    return entry


def validate(entry, root, *, provisioning=False):
    try:
        return _validate(entry, root, provisioning=provisioning)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(
            f"the definition or a file it points at has an unexpected structure ({type(exc).__name__}); check that every field has the documented shape"
        ) from exc


def load_registry(root: Path, *, provisioning=False) -> list[dict]:
    entries = []
    names = set()
    roles = set()
    pairs = set()
    for path in sorted((root / BASE / "backends").glob("*.yaml")):
        safe_path(root, str(path.relative_to(root)), "backend definition file")
        docs = yaml_documents(path)
        if len(docs) != 1:
            raise ValueError(
                f"{path.name}: expected exactly 1 YAML document, found {len(docs)}"
            )
        e = validate(docs[0], root, provisioning=provisioning)
        if path.stem != e["name"]:
            raise ValueError(
                f"{path.name}: the file name without .yaml must equal the definition's name"
            )
        if e["name"] in names:
            raise ValueError(f"{path.name}: name is already used by another backend")
        if e["authorization"]["role"] in roles:
            raise ValueError(
                f"{path.name}: authorization.role is already used by another backend"
            )
        names.add(e["name"])
        roles.add(e["authorization"]["role"])
        for credential in provision_pair(e, root) if "provision" in e else []:
            identity = (credential["namespace"], credential["name"])
            if identity in pairs or credential["path"] in pairs:
                raise ValueError(
                    f"{path.name}: provision credentials collide with another backend's Secret identity or path"
                )
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
