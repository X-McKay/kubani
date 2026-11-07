"""Reviewed public object references for the bounded Kubernetes HTTP profile."""

from __future__ import annotations

import hashlib
import json
import tomllib

from . import model

PROFILE = "existing-streamable-http-v1"
WORKLOAD = "infrastructure/gitops/apps/mcp/kubernetes-mcp.yaml"
AGENTS = "infrastructure/gitops/apps/ai-gateway/agents/"
VIEW = "infrastructure/mcp/baseline/kubernetes-view.json"
TOOLS = [
    "events_list",
    "pods_get",
    "pods_list_in_namespace",
    "pods_log",
    "resources_get",
    "resources_list",
]
SOURCE_REFS = [
    (WORKLOAD, "v1", "ServiceAccount", "mcp", "kubernetes-mcp"),
    (
        WORKLOAD,
        "rbac.authorization.k8s.io/v1",
        "ClusterRoleBinding",
        "",
        "mcp-kubernetes-mcp-view",
    ),
    (WORKLOAD, "v1", "ConfigMap", "mcp", "kubernetes-mcp-config"),
    (WORKLOAD, "apps/v1", "Deployment", "mcp", "kubernetes-mcp"),
    (WORKLOAD, "v1", "Service", "mcp", "kubernetes-mcp"),
    (
        WORKLOAD,
        "networking.k8s.io/v1",
        "NetworkPolicy",
        "mcp",
        "allow-kubernetes-mcp-apiserver-egress",
    ),
    (
        AGENTS + "backends.yaml",
        "agentgateway.dev/v1alpha1",
        "AgentgatewayBackend",
        "ai-gateway",
        "agents-mcp-kubernetes",
    ),
    (
        AGENTS + "routes.yaml",
        "gateway.networking.k8s.io/v1",
        "HTTPRoute",
        "ai-gateway",
        "agents-mcp-kubernetes",
    ),
    (
        AGENTS + "policies-extauth.yaml",
        "agentgateway.dev/v1alpha1",
        "AgentgatewayPolicy",
        "ai-gateway",
        "agents-extauth-mcp-kubernetes",
    ),
    (
        AGENTS + "policies-mcp-tools.yaml",
        "agentgateway.dev/v1alpha1",
        "AgentgatewayPolicy",
        "ai-gateway",
        "agents-mcp-kubernetes-tools",
    ),
]
EXTERNAL_REFS = [(VIEW, "rbac.authorization.k8s.io/v1", "ClusterRole", "", "view")]


def canonical_sha256(document):
    try:
        content = json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid canonical public object") from exc
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _identity(document):
    return (
        document.get("apiVersion"),
        document.get("kind"),
        document.get("metadata", {}).get("namespace", ""),
        document.get("metadata", {}).get("name"),
    )


def referenced_objects(root, entry, *, external=False):
    refs = entry["externalReferences" if external else "references"]
    contract = EXTERNAL_REFS if external else SOURCE_REFS
    if not isinstance(refs, list) or len(refs) != len(contract):
        raise ValueError("exact bounded public references required")
    selected, seen, cache = [], set(), {}
    for ref in refs:
        model.fields(
            ref, ["path", "apiVersion", "kind", "namespace", "name", "canonicalSHA256"]
        )
        key = tuple(ref[k] for k in ("path", "apiVersion", "kind", "namespace", "name"))
        if key not in contract or key in seen:
            raise ValueError("unexpected or duplicate public reference")
        seen.add(key)
        model.string(ref["canonicalSHA256"], r"sha256:[a-f0-9]{64}")
        path = model.safe_path(root, ref["path"])
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("public reference file exceeds bound")
        if ref["path"] not in cache:
            docs = model.yaml_documents(path)
            if len(docs) > 128 or any(not isinstance(d, dict) for d in docs):
                raise ValueError("invalid bounded public manifest")
            cache[ref["path"]] = docs
        docs = cache[ref["path"]]
        objects = [d for d in docs if _identity(d) == key[1:]]
        if len(objects) != 1 or canonical_sha256(objects[0]) != ref["canonicalSHA256"]:
            raise ValueError("reviewed public reference missing, ambiguous or changed")
        selected.append(objects[0])
    if not external:
        docs = cache[WORKLOAD]
        if len(docs) != 6 or {_identity(d) for d in docs} != {
            r[1:] for r in SOURCE_REFS if r[0] == WORKLOAD
        }:
            raise ValueError("unexpected workload manifest object set")
    else:
        if len(cache[VIEW]) != 1:
            raise ValueError("exact external view snapshot required")
        view = selected[0]
        model.fields(
            view, ["apiVersion", "kind", "metadata", "rules", "aggregationRule"]
        )
        if (
            view["metadata"] != {"name": "view"}
            or not isinstance(view["rules"], list)
            or not isinstance(view["aggregationRule"], dict)
        ):
            raise ValueError("invalid external view projection")
    return selected


def validate(entry, root):
    model.fields(
        entry,
        [
            "version",
            "name",
            "profile",
            "workload",
            "authorization",
            "secrets",
            "upstreams",
            "references",
            "externalReferences",
        ],
    )
    if (
        type(entry["version"]) is not int
        or entry["version"] != 1
        or entry["name"] != "kubernetes"
        or entry["profile"] != PROFILE
    ):
        raise ValueError("unsupported existing HTTP backend")
    if entry["workload"] != {
        "namespace": "mcp",
        "service": "kubernetes-mcp",
        "port": 8080,
        "path": "/mcp",
        "protocol": "StreamableHTTP",
    }:
        raise ValueError("existing HTTP transport contract mismatch")
    if entry["secrets"] != [] or entry["upstreams"] != []:
        raise ValueError("existing HTTP profile has no generated secrets or upstreams")
    auth = entry["authorization"]
    model.fields(auth, ["role", "tools", "scopeDescription"])
    if auth["role"] != "agent-role-kubernetes-read" or auth["tools"] != TOOLS:
        raise ValueError("existing HTTP role or tools mismatch")
    model.string(auth["scopeDescription"])
    docs = referenced_objects(root, entry)
    referenced_objects(root, entry, external=True)
    by_kind = {d["kind"]: d for d in docs if d["kind"] != "AgentgatewayPolicy"}
    binding = by_kind["ClusterRoleBinding"]
    if binding["roleRef"] != {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "ClusterRole",
        "name": "view",
    } or binding["subjects"] != [
        {"kind": "ServiceAccount", "name": "kubernetes-mcp", "namespace": "mcp"}
    ]:
        raise ValueError("view ServiceAccount binding required")
    config = tomllib.loads(by_kind["ConfigMap"]["data"]["config.toml"])
    if any(
        config.get(k) != v
        for k, v in {
            "port": "8081",
            "read_only": True,
            "stateless": True,
            "cluster_auth_mode": "kubeconfig",
            "toolsets": ["core"],
        }.items()
    ):
        raise ValueError("read-only kubeconfig server configuration required")
    pod = by_kind["Deployment"]["spec"]["template"]["spec"]
    if pod.get("serviceAccountName") != "kubernetes-mcp":
        raise ValueError("reviewed ServiceAccount required")
    containers = {c["name"]: c for c in pod["containers"]}
    if set(containers) != {"capture", "kubernetes-mcp"} or containers[
        "kubernetes-mcp"
    ].get("args") != ["--config", "/etc/kubernetes-mcp-server/config.toml"]:
        raise ValueError("reviewed capture and configured server required")
    backend = by_kind["AgentgatewayBackend"]["spec"]["mcp"]
    if backend != {
        "failureMode": "FailClosed",
        "sessionRouting": "Stateless",
        "targets": [
            {
                "name": "kubernetes",
                "static": {
                    "host": "kubernetes-mcp.mcp.svc.cluster.local",
                    "port": 8080,
                    "path": "/mcp",
                    "protocol": "StreamableHTTP",
                },
            }
        ],
    }:
        raise ValueError("existing HTTP backend mismatch")
    service = by_kind["Service"]["spec"]
    if service["selector"] != {model.LABEL: "kubernetes-mcp"} or service["ports"] != [
        {
            "name": "http",
            "port": 8080,
            "targetPort": "http",
            "appProtocol": "agentgateway.dev/mcp",
        }
    ]:
        raise ValueError("capture Service routing mismatch")
    if not any(
        p.get("name") == "http" and p.get("containerPort") == 8080
        for p in containers["capture"].get("ports", [])
    ):
        raise ValueError("capture Service port missing")
    route = by_kind["HTTPRoute"]["spec"]
    if route != {
        "parentRefs": [{"name": "agents", "sectionName": "agents-https"}],
        "hostnames": ["mcp.agents.internal"],
        "rules": [
            {
                "matches": [
                    {"path": {"type": "PathPrefix", "value": "/kubernetes/mcp"}}
                ],
                "backendRefs": [
                    {
                        "group": "agentgateway.dev",
                        "kind": "AgentgatewayBackend",
                        "name": "agents-mcp-kubernetes",
                    }
                ],
            }
        ],
    }:
        raise ValueError("existing Kubernetes route mismatch")
    policies = {
        d["metadata"]["name"]: d["spec"]
        for d in docs
        if d["kind"] == "AgentgatewayPolicy"
    }
    tool_policy = policies["agents-mcp-kubernetes-tools"]
    expected_expr = 'jwt.client_type == "agent" && "agent-role-kubernetes-read" in jwt.realm_access.roles && mcp.tool.name in ["events_list", "pods_get", "pods_list_in_namespace", "pods_log", "resources_get", "resources_list"]'
    expected_tools = {
        "targetRefs": [
            {
                "group": "agentgateway.dev",
                "kind": "AgentgatewayBackend",
                "name": "agents-mcp-kubernetes",
            }
        ],
        "backend": {
            "mcp": {
                "authorization": {
                    "action": "Allow",
                    "policy": {"matchExpressions": [expected_expr]},
                }
            }
        },
    }
    normalized = json.loads(json.dumps(tool_policy))
    normalized["backend"]["mcp"]["authorization"]["policy"]["matchExpressions"] = [
        " ".join(v.split())
        for v in tool_policy["backend"]["mcp"]["authorization"]["policy"][
            "matchExpressions"
        ]
    ]
    if normalized != expected_tools:
        raise ValueError("exact read-only Kubernetes tool policy required")
    ext = policies["agents-extauth-mcp-kubernetes"]
    if ext != {
        "targetRefs": [
            {
                "group": "gateway.networking.k8s.io",
                "kind": "HTTPRoute",
                "name": "agents-mcp-kubernetes",
            }
        ],
        "traffic": {
            "extAuth": {
                "backendRef": {
                    "kind": "Service",
                    "name": "agent-policy-service",
                    "namespace": "agent-platform",
                    "port": 9001,
                },
                "failureMode": "FailClosed",
                "forwardBody": {"maxSize": 65536},
                "grpc": {
                    "contextExtensions": {"route": "mcp", "backend": "kubernetes"}
                },
            }
        },
    }:
        raise ValueError("existing Kubernetes extAuth mismatch")
    return entry
