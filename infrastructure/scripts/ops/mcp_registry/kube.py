"""Bounded exact-object kubectl reads shared by status and preflight."""

from __future__ import annotations

import json
import re
import subprocess

KUBE_NAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
RESOURCES = {
    ("v1", "Service"): "services",
    ("v1", "ConfigMap"): "configmaps",
    ("v1", "Secret"): "secrets",
    ("v1", "Namespace"): "namespaces",
    ("v1", "ServiceAccount"): "serviceaccounts",
    ("rbac.authorization.k8s.io/v1", "ClusterRoleBinding"): "clusterrolebindings.rbac.authorization.k8s.io",
    ("rbac.authorization.k8s.io/v1", "ClusterRole"): "clusterroles.rbac.authorization.k8s.io",
    ("apps/v1", "Deployment"): "deployments.apps",
    ("batch/v1", "Job"): "jobs.batch",
    ("networking.k8s.io/v1", "NetworkPolicy"): "networkpolicies.networking.k8s.io",
    (
        "gateway.networking.k8s.io/v1",
        "HTTPRoute",
    ): "httproutes.gateway.networking.k8s.io",
    ("gateway.networking.k8s.io/v1", "Gateway"): "gateways.gateway.networking.k8s.io",
    (
        "agentgateway.dev/v1alpha1",
        "AgentgatewayBackend",
    ): "agentgatewaybackends.agentgateway.dev",
    (
        "agentgateway.dev/v1alpha1",
        "AgentgatewayPolicy",
    ): "agentgatewaypolicies.agentgateway.dev",
}


class KubeReader:
    """Bounded exact-object reads; Secret reads return only the object's name."""

    def __init__(self, kubeconfig, *, run=None):
        self.kubeconfig = kubeconfig
        self.run = run or subprocess.run

    def __call__(self, api_version, kind, namespace, name):
        resource = RESOURCES.get((api_version, kind))
        if (
            resource is None
            or not isinstance(name, str)
            or not KUBE_NAME.fullmatch(name)
        ):
            raise ValueError("unsupported object identity")
        cluster_scoped = kind in {"Namespace", "ClusterRoleBinding", "ClusterRole"}
        if cluster_scoped and namespace != "":
            raise ValueError("cluster-scoped namespace must be empty")
        if not cluster_scoped and (
            not isinstance(namespace, str) or not KUBE_NAME.fullmatch(namespace)
        ):
            raise ValueError("invalid namespace")
        argv = ["kubectl"]
        if self.kubeconfig:
            argv += ["--kubeconfig", str(self.kubeconfig)]
        argv += ["--request-timeout=10s", "get", resource, name, "--ignore-not-found"]
        if not cluster_scoped:
            argv += ["--namespace", namespace]
        argv += ["-o", "jsonpath={.metadata.name}" if kind == "Secret" else "json"]
        result = self.run(argv, capture_output=True, text=True, timeout=15, check=False)
        if result.returncode:
            raise RuntimeError("cluster read failed")
        raw = result.stdout.strip()
        if not raw:
            return None
        if len(raw.encode()) > 4 * 1024 * 1024:
            raise ValueError("cluster object exceeds bound")
        if kind == "Secret":
            if raw != name:
                raise ValueError("secret identity differs")
            return {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": name, "namespace": namespace},
            }
        value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or value.get("kind") != kind
            or value.get("apiVersion") != api_version
            or value.get("metadata", {}).get("name") != name
            or (
                not cluster_scoped
                and value.get("metadata", {}).get("namespace") != namespace
            )
        ):
            raise ValueError("cluster object identity differs")
        if cluster_scoped and value.get("metadata", {}).get("namespace", "") != "":
            raise ValueError("cluster object namespace differs")
        return value
