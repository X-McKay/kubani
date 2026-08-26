#!/usr/bin/env python3
"""Generate or verify Starbase's inactive, content-bound Kubani bundle.

The credential-bearing source-acquisition job is deliberately outside this
program. This renderer accepts only already-authenticated, clean Git checkouts;
it never reads a token, invokes GitHub, or resolves a floating revision.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ZERO_DIGEST = "sha256:" + ("0" * 64)
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
REMOTE_RESOURCE_RE = re.compile(r"^(?:https?://|git::|ssh://|github\.com/)")

ALLOWED_CLUSTER_SCOPED_KINDS = {
    "Namespace",
    "PersistentVolume",
}
WORKLOAD_KINDS = {"CronJob", "DaemonSet", "Deployment", "Job", "StatefulSet"}
NATIVE_POD_PRODUCING_KINDS = WORKLOAD_KINDS | {
    "Pod",
    "ReplicaSet",
    "ReplicationController",
}
PHASE5_FLUX_REQUIRED_SPEC_FIELDS = {
    "decryption",
    "dependsOn",
    "healthChecks",
    "interval",
    "path",
    "prune",
    "sourceRef",
    "timeout",
}
PHASE5_FLUX_ALLOWED_SPEC_FIELDS = PHASE5_FLUX_REQUIRED_SPEC_FIELDS | {"force"}
PHASE5_PREVIEW_KUSTOMIZATION_FIELDS = {
    "apiVersion",
    "kind",
    "patches",
    "resources",
}
EXPECTED_IMAGE_NAMES = {
    "core",
    "core-migrator",
    "gateway-migrator",
    "github-connector",
    "kubernetes-connector",
    "web",
}
EXPECTED_OBSERVER_RULES = [
    {
        "apiGroups": [""],
        "resources": ["pods"],
        "verbs": ["list"],
    },
    {
        "apiGroups": ["apps"],
        "resources": ["daemonsets", "deployments", "statefulsets"],
        "verbs": ["list"],
    },
]
EXPECTED_OBSERVER_NAMESPACES = {
    "starbase-connectors",
    "starbase-execution",
    "starbase-system",
}
EXPECTED_OBSERVER_ROLE_REF = {
    "apiGroup": "rbac.authorization.k8s.io",
    "kind": "Role",
    "name": "starbase-kubernetes-observer",
}
EXPECTED_OBSERVER_SUBJECTS = [
    {
        "kind": "ServiceAccount",
        "name": "starbase-kubernetes-connector",
        "namespace": "starbase-connectors",
    }
]
MIGRATION_DIRECTORIES = {
    "starbase-core-migrate": "services/corestate/migrations/",
    "starbase-gateway-migrate": "services/experiencegateway/migrations/",
}
PROMOTION_INPUT_KEYS = {
    "allowed_namespaces",
    "base_path",
    "expected_activation",
    "expected_release_version",
    "manifest_evidence",
    "max_objects",
    "repository",
    "schema_version",
    "supported_execution_platforms",
    "target_platform",
}
INACTIVE_ACTIVATION = {
    "bundle": "inactive-not-flux-referenced",
    "core": "blocked-pending-runtime-gates",
    "github_connector": "intentionally-disabled-zero-replicas",
    "kubernetes_connector": "blocked-pending-runtime-gates",
    "migrations": "rendered-not-authorized",
}
INERT_FOUNDATION_ACTIVATION = {
    "bundle": "flux-referenced-inert-foundation",
    "core": "flux-referenced-zero-replicas",
    "github_connector": "intentionally-disabled-zero-replicas",
    "kubernetes_connector": "flux-referenced-zero-replicas",
    "migrations": "flux-referenced-suspended",
}


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def require_mapping(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be an object")
    return value


def require_relative_path(value: Any, description: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{description} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{description} must not escape its source checkout")
    return path


def load_json(path: Path) -> dict[str, Any]:
    try:
        return require_mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON from {path}: {exc}") from exc


def load_verified_manifest(path: Path, expected_digest: str) -> dict[str, Any]:
    if not SHA256_RE.fullmatch(expected_digest):
        raise ValueError("expected manifest digest must be sha256:<64 lowercase hex>")
    actual = sha256_file(path)
    if actual != expected_digest:
        raise ValueError(
            f"manifest digest mismatch: expected {expected_digest}, observed {actual}"
        )
    return load_json(path)


def run(command: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise ValueError(f"command failed ({' '.join(command)}): {stderr}")
    return result.stdout


def normalize_repository(value: str) -> str:
    normalized = value.strip().removesuffix(".git").removesuffix("/")
    if normalized.startswith("git@github.com:"):
        normalized = "https://github.com/" + normalized.removeprefix("git@github.com:")
    return normalized.lower()


def verify_checkout(
    path: Path, revision: str, repository: str, description: str
) -> None:
    if not REVISION_RE.fullmatch(revision):
        raise ValueError(f"{description} revision must be an exact 40-character SHA")
    observed = run(["git", "rev-parse", "HEAD"], cwd=path).strip()
    if observed != revision:
        raise ValueError(
            f"{description} revision mismatch: expected {revision}, observed {observed}"
        )
    dirty = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=path
    ).strip()
    if dirty:
        raise ValueError(f"{description} checkout is dirty")

    remotes = run(["git", "remote", "-v"], cwd=path).splitlines()
    expected = normalize_repository(repository)
    observed_urls = {
        normalize_repository(parts[1])
        for line in remotes
        if len(parts := line.split()) >= 2
    }
    if expected not in observed_urls:
        raise ValueError(
            f"{description} checkout repository does not match {repository}"
        )


def directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"source directory is empty: {root}")
    for path in files:
        if path.is_symlink():
            raise ValueError(f"source directory contains a symlink: {path}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def python_package_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".pyd", ".so"}
    )
    if not files:
        raise ValueError(f"Python package has no hashable source files: {root}")
    for path in files:
        if path.is_symlink():
            raise ValueError(f"Python package contains a symlink: {path}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def validate_local_kustomization(base_path: Path) -> None:
    kustomization_path = base_path / "kustomization.yaml"
    document = require_mapping(
        yaml.safe_load(kustomization_path.read_text(encoding="utf-8")),
        str(kustomization_path),
    )
    for field in ("resources", "components"):
        for resource in document.get(field, []) or []:
            if not isinstance(resource, str):
                raise ValueError(f"{field} entries must be strings")
            if (
                REMOTE_RESOURCE_RE.match(resource)
                or Path(resource).is_absolute()
                or ".." in Path(resource).parts
            ):
                raise ValueError(
                    f"remote or escaping Kustomize resource is forbidden: {resource}"
                )
    for patch in document.get("patches", []) or []:
        if isinstance(patch, dict) and "path" in patch:
            require_relative_path(patch["path"], "Kustomize patch path")


def validate_release_manifest(
    manifest: dict[str, Any], config: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    if manifest.get("schema_version") != 1:
        raise ValueError("release manifest schema_version must be 1")
    if normalize_repository(
        str(manifest.get("repository", ""))
    ) != normalize_repository(str(config.get("repository", ""))):
        raise ValueError("release manifest repository does not match promotion input")
    if manifest.get("version") != config.get("expected_release_version"):
        raise ValueError("release version does not match promotion input")
    revision = manifest.get("revision")
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise ValueError("release manifest revision must be an exact commit SHA")

    images = manifest.get("images")
    if not isinstance(images, list):
        raise ValueError("release manifest images must be an array")
    by_name: dict[str, dict[str, Any]] = {}
    repositories: set[str] = set()
    for raw_image in images:
        image = require_mapping(raw_image, "release image")
        name = image.get("name")
        repository = image.get("image")
        digest = image.get("digest")
        if not isinstance(name, str) or name in by_name:
            raise ValueError("release image names must be unique strings")
        if not isinstance(repository, str) or repository in repositories:
            raise ValueError("release image repositories must be unique strings")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError(f"release image {name} has an invalid digest")
        if image.get("platform") != config.get("target_platform"):
            raise ValueError(f"release image {name} has the wrong platform")
        if image.get("signature_verified") is not True:
            raise ValueError(f"release image {name} lacks verified signature evidence")
        by_name[name] = image
        repositories.add(repository)
    if set(by_name) != EXPECTED_IMAGE_NAMES:
        raise ValueError(
            "release manifest must contain exactly the six Starbase images"
        )
    return by_name


def pod_spec(document: dict[str, Any]) -> dict[str, Any] | None:
    kind = document.get("kind")
    spec = require_mapping(document.get("spec", {}), "object spec")
    if kind == "CronJob":
        return require_mapping(
            require_mapping(spec.get("jobTemplate", {}), "CronJob jobTemplate")
            .get("spec", {})
            .get("template", {})
            .get("spec", {}),
            "CronJob pod spec",
        )
    if kind in {"DaemonSet", "Deployment", "Job", "StatefulSet"}:
        return require_mapping(
            require_mapping(spec.get("template", {}), "workload template").get(
                "spec", {}
            ),
            "workload pod spec",
        )
    return None


def image_slots(value: Any) -> list[tuple[dict[str, Any], str]]:
    slots: list[tuple[dict[str, Any], str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "image" and isinstance(child, str):
                slots.append((value, key))
            else:
                slots.extend(image_slots(child))
    elif isinstance(value, list):
        for child in value:
            slots.extend(image_slots(child))
    return slots


def migration_set_digests(manifest: dict[str, Any]) -> dict[str, str]:
    migrations = manifest.get("database_migrations")
    if not isinstance(migrations, list):
        raise ValueError("release manifest database_migrations must be an array")
    grouped: dict[str, list[dict[str, str]]] = {
        job_name: [] for job_name in MIGRATION_DIRECTORIES
    }
    seen_paths: set[str] = set()
    for raw_migration in migrations:
        migration = require_mapping(raw_migration, "release migration")
        path = migration.get("path")
        digest = migration.get("digest")
        if not isinstance(path, str) or not path.endswith(".sql"):
            raise ValueError("release migration path must identify a SQL file")
        if path in seen_paths:
            raise ValueError(f"release migration path is duplicated: {path}")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError(f"release migration {path} has an invalid digest")
        matching_jobs = [
            job_name
            for job_name, directory in MIGRATION_DIRECTORIES.items()
            if path.startswith(directory)
        ]
        if len(matching_jobs) != 1:
            raise ValueError(f"release migration has no configured migrator: {path}")
        grouped[matching_jobs[0]].append({"path": path, "digest": digest})
        seen_paths.add(path)

    result: dict[str, str] = {}
    for job_name, entries in grouped.items():
        if not entries:
            raise ValueError(f"release manifest has no migrations for {job_name}")
        result[job_name] = sha256_bytes(
            canonical_json(sorted(entries, key=lambda item: item["path"]))
        )
    return result


def validate_observer_rbac(document: dict[str, Any]) -> tuple[str, str] | None:
    kind = document.get("kind")
    if kind not in {"Role", "RoleBinding"}:
        return None
    metadata = require_mapping(document.get("metadata", {}), f"{kind} metadata")
    namespace = metadata.get("namespace")
    if (
        metadata.get("name") != "starbase-kubernetes-observer"
        or namespace not in EXPECTED_OBSERVER_NAMESPACES
    ):
        raise ValueError(f"unexpected {kind} identity")
    assert isinstance(namespace, str)
    if kind == "Role":
        if document.get("rules") != EXPECTED_OBSERVER_RULES:
            raise ValueError("starbase observer Role rules differ from policy")
        return kind, namespace
    if document.get("roleRef") != EXPECTED_OBSERVER_ROLE_REF:
        raise ValueError("starbase observer RoleBinding roleRef differs from policy")
    if document.get("subjects") != EXPECTED_OBSERVER_SUBJECTS:
        raise ValueError("starbase observer RoleBinding subjects differ from policy")
    return kind, namespace


def validate_network_policy(document: dict[str, Any]) -> None:
    if document.get("kind") != "NetworkPolicy":
        return
    for rule in (
        require_mapping(document.get("spec", {}), "NetworkPolicy spec").get(
            "egress", []
        )
        or []
    ):
        rule = require_mapping(rule, "NetworkPolicy egress rule")
        targets = rule.get("to")
        ports = rule.get("ports")
        if not isinstance(targets, list) or not targets:
            raise ValueError("NetworkPolicy catch-all egress is forbidden")
        if not isinstance(ports, list) or not ports:
            raise ValueError("NetworkPolicy unbounded-port egress is forbidden")
        for target in targets:
            target = require_mapping(target, "NetworkPolicy egress target")
            if "ipBlock" in target:
                raise ValueError(
                    "NetworkPolicy ipBlock egress is forbidden in inactive bundle"
                )
        port_numbers = {
            str(port.get("port")) for port in ports if isinstance(port, dict)
        }
        if port_numbers == {"53"}:
            expected_namespace = {
                "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
            }
            expected_pods = {"matchLabels": {"k8s-app": "kube-dns"}}
        elif port_numbers == {"8081"}:
            expected_namespace = {
                "matchLabels": {"kubernetes.io/metadata.name": "starbase-system"}
            }
            expected_pods = {"matchLabels": {"app.kubernetes.io/name": "starbase-core"}}
        else:
            raise ValueError("unexpected egress port in inactive bundle")
        for target in targets:
            if target.get("namespaceSelector") != expected_namespace:
                raise ValueError(
                    "unexpected egress namespace selector in inactive bundle"
                )
            if target.get("podSelector") != expected_pods:
                raise ValueError("unexpected egress pod selector in inactive bundle")


def validate_workload_security(
    kind: str, name: str, workload_spec: dict[str, Any]
) -> None:
    if any(
        workload_spec.get(field) is True
        for field in ("hostIPC", "hostNetwork", "hostPID")
    ):
        raise ValueError(f"{kind}/{name} requests a host namespace")
    pod_security = require_mapping(
        workload_spec.get("securityContext", {}),
        f"{kind}/{name} pod securityContext",
    )
    if pod_security.get("runAsNonRoot") is not True:
        raise ValueError(f"{kind}/{name} must run as non-root")
    seccomp = require_mapping(
        pod_security.get("seccompProfile", {}), f"{kind}/{name} seccompProfile"
    )
    if seccomp.get("type") != "RuntimeDefault":
        raise ValueError(f"{kind}/{name} must use RuntimeDefault seccomp")
    for volume in workload_spec.get("volumes", []) or []:
        if isinstance(volume, dict) and "hostPath" in volume:
            raise ValueError(f"{kind}/{name} must not use hostPath")
    containers = workload_spec.get("containers")
    if not isinstance(containers, list) or not containers:
        raise ValueError(f"{kind}/{name} must define containers")
    init_containers = workload_spec.get("initContainers", [])
    if not isinstance(init_containers, list):
        raise ValueError(f"{kind}/{name} initContainers must be an array")
    for container in containers + init_containers:
        container = require_mapping(container, f"{kind}/{name} container")
        container_name = str(container.get("name", "<unnamed>"))
        security = require_mapping(
            container.get("securityContext", {}),
            f"{kind}/{name} container {container_name} securityContext",
        )
        if security.get("allowPrivilegeEscalation") is not False:
            raise ValueError(
                f"{kind}/{name} container {container_name} permits privilege escalation"
            )
        if security.get("readOnlyRootFilesystem") is not True:
            raise ValueError(
                f"{kind}/{name} container {container_name} needs a read-only root filesystem"
            )
        dropped = require_mapping(
            security.get("capabilities", {}),
            f"{kind}/{name} container {container_name} capabilities",
        ).get("drop")
        if dropped != ["ALL"]:
            raise ValueError(
                f"{kind}/{name} container {container_name} must drop all capabilities"
            )
        resources = require_mapping(
            container.get("resources", {}),
            f"{kind}/{name} container {container_name} resources",
        )
        if not resources.get("requests") or not resources.get("limits"):
            raise ValueError(
                f"{kind}/{name} container {container_name} needs requests and limits"
            )


def transform_and_validate(
    source_documents: list[dict[str, Any]],
    manifest: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    unknown_keys = set(config) - PROMOTION_INPUT_KEYS
    if unknown_keys:
        raise ValueError(f"unknown promotion input keys: {sorted(unknown_keys)}")
    if config.get("schema_version") != 1:
        raise ValueError("promotion input schema_version must be 1")
    max_objects = config.get("max_objects")
    if not isinstance(max_objects, int) or max_objects < 1:
        raise ValueError("max_objects must be a positive integer")
    if len(source_documents) > max_objects:
        raise ValueError(
            f"object count {len(source_documents)} exceeds configured maximum {max_objects}"
        )
    allowed_namespaces = set(config.get("allowed_namespaces", []))
    if not allowed_namespaces or not all(
        isinstance(item, str) and item for item in allowed_namespaces
    ):
        raise ValueError("allowed_namespaces must contain non-empty strings")
    activation = config.get("expected_activation")
    if not isinstance(activation, dict) or set(activation) != {
        "bundle",
        "core",
        "github_connector",
        "kubernetes_connector",
        "migrations",
    }:
        raise ValueError(
            "expected_activation must define the five bounded activation states"
        )

    images = validate_release_manifest(manifest, config)
    image_by_repository = {str(item["image"]): item for item in images.values()}
    documents = copy.deepcopy(source_documents)
    observed_repositories: list[str] = []
    rbac_identities: set[tuple[str, str]] = set()

    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("rendered documents must be objects")
        kind = document.get("kind")
        if kind == "Secret":
            raise ValueError("Secret objects are forbidden in the promotion bundle")
        metadata = require_mapping(document.setdefault("metadata", {}), "metadata")
        name = metadata.get("name")
        if not isinstance(kind, str) or not isinstance(name, str):
            raise ValueError("every object must have a kind and metadata.name")
        namespace = metadata.get("namespace")
        if kind == "Namespace":
            if name not in allowed_namespaces:
                raise ValueError(f"unexpected Namespace {name}")
        elif namespace is None:
            if kind not in ALLOWED_CLUSTER_SCOPED_KINDS:
                raise ValueError(f"unexpected cluster-scoped object {kind}/{name}")
        elif namespace not in allowed_namespaces:
            raise ValueError(f"unexpected namespace {namespace} for {kind}/{name}")
        if kind == "Ingress":
            raise ValueError("Ingress is forbidden in the inactive bundle")
        rbac_identity = validate_observer_rbac(document)
        if rbac_identity is not None:
            if rbac_identity in rbac_identities:
                raise ValueError("bundle duplicates a namespace observer RBAC identity")
            rbac_identities.add(rbac_identity)

        labels = require_mapping(metadata.setdefault("labels", {}), "metadata.labels")
        labels["starbase.io/release"] = str(manifest["version"])
        labels["starbase.io/source-revision"] = str(manifest["revision"])

        workload_spec = pod_spec(document)
        if kind in WORKLOAD_KINDS:
            assert workload_spec is not None
            service_account = workload_spec.get("serviceAccountName")
            if not isinstance(service_account, str) or service_account in {
                "",
                "default",
            }:
                raise ValueError(f"{kind}/{name} must use a dedicated ServiceAccount")
            if workload_spec.get("automountServiceAccountToken") is not False:
                raise ValueError(f"{kind}/{name} must disable automatic token mounting")
            validate_workload_security(kind, name, workload_spec)
        if kind == "Job":
            job_spec = require_mapping(document.get("spec", {}), "Job spec")
            ttl = job_spec.get("ttlSecondsAfterFinished")
            if not isinstance(ttl, int) or not 1 <= ttl <= 86400:
                raise ValueError(
                    f"Job/{name} must have bounded retention of at most one day"
                )
            if not isinstance(job_spec.get("activeDeadlineSeconds"), int):
                raise ValueError(f"Job/{name} must have an active deadline")

        for parent, key in image_slots(document):
            raw = parent[key]
            if "@" not in raw:
                raise ValueError(f"unexpected image without immutable digest: {raw}")
            repository, digest = raw.rsplit("@", 1)
            if repository not in image_by_repository:
                raise ValueError(f"unexpected image repository: {repository}")
            if digest != ZERO_DIGEST:
                raise ValueError(
                    f"source base image is not the fail-safe placeholder: {raw}"
                )
            parent[key] = f"{repository}@{image_by_repository[repository]['digest']}"
            observed_repositories.append(repository)

        validate_network_policy(document)

    expected_rbac_identities = {
        (kind, namespace)
        for kind in ("Role", "RoleBinding")
        for namespace in EXPECTED_OBSERVER_NAMESPACES
    }
    if rbac_identities != expected_rbac_identities:
        raise ValueError(
            "bundle must contain exact namespace observer roles and bindings"
        )

    if sorted(observed_repositories) != sorted(image_by_repository):
        raise ValueError("source base must contain every release image exactly once")

    github = [
        document
        for document in documents
        if document.get("kind") == "Deployment"
        and document["metadata"].get("name") == "starbase-github-connector"
    ]
    if len(github) != 1:
        raise ValueError("bundle must contain one GitHub connector Deployment")
    require_mapping(github[0].get("spec", {}), "GitHub Deployment spec")["replicas"] = 0
    github[0]["metadata"].setdefault("annotations", {})[
        "starbase.io/activation-state"
    ] = "intentionally-disabled-no-egress"

    kubernetes = [
        document
        for document in documents
        if document.get("kind") == "Deployment"
        and document["metadata"].get("name") == "starbase-kubernetes-connector"
    ]
    if len(kubernetes) != 1:
        raise ValueError("bundle must contain one Kubernetes connector Deployment")
    kubernetes_pod = pod_spec(kubernetes[0])
    assert kubernetes_pod is not None
    kubernetes_containers = kubernetes_pod.get("containers", [])
    if not isinstance(kubernetes_containers, list) or len(kubernetes_containers) != 1:
        raise ValueError("Kubernetes connector must contain one container")
    kubernetes_container = require_mapping(
        kubernetes_containers[0], "Kubernetes connector container"
    )
    scope_variables = [
        item
        for item in kubernetes_container.get("env", []) or []
        if isinstance(item, dict) and item.get("name") == "STARBASE_KUBERNETES_SCOPE"
    ]
    if len(scope_variables) != 1 or not isinstance(
        scope_variables[0].get("value"), str
    ):
        raise ValueError("Kubernetes connector must define one literal scope")
    expected_scope = {
        "id": "starbase-namespaces-v1",
        "namespaces": sorted(allowed_namespaces),
        "include_nodes": False,
        "flux_namespaces": [],
    }
    try:
        observed_scope = json.loads(scope_variables[0]["value"])
    except json.JSONDecodeError as exc:
        raise ValueError("Kubernetes connector scope must be valid JSON") from exc
    if observed_scope != expected_scope:
        raise ValueError("Kubernetes connector scope differs from namespace policy")
    # Preserve JSON semantics while giving the deterministic YAML serializer
    # safe wrap points under the repository's 160-column manifest limit.
    scope_variables[0]["value"] = json.dumps(
        expected_scope, separators=(", ", ":"), sort_keys=False
    )

    migration_names = migration_set_digests(manifest)
    for document in documents:
        name = document["metadata"]["name"]
        if document.get("kind") == "Job" and name in migration_names:
            digest = migration_names[name]
            document["metadata"][
                "name"
            ] = f"{name}-{digest.removeprefix('sha256:')[:12]}"
            annotations = document["metadata"].setdefault("annotations", {})
            annotations["starbase.io/migration-set-digest"] = digest
            annotations["starbase.io/activation-state"] = "rendered-not-authorized"

    final_images = [
        parent[key] for document in documents for parent, key in image_slots(document)
    ]
    expected_images = {
        f"{item['image']}@{item['digest']}" for item in image_by_repository.values()
    }
    if set(final_images) != expected_images or len(final_images) != len(
        expected_images
    ):
        raise ValueError(
            "final bundle image set does not exactly match the release manifest"
        )
    return documents


def render_yaml(documents: list[dict[str, Any]]) -> bytes:
    # safe_dump_all intentionally uses the pure-Python SafeDumper. Switching to
    # CSafeDumper or dump_all changes the promotion serialization contract.
    text = yaml.safe_dump_all(
        documents,
        default_flow_style=False,
        explicit_start=True,
        sort_keys=True,
        width=150,
    )
    return text.encode("utf-8")


def object_inventory(documents: list[dict[str, Any]]) -> list[dict[str, str]]:
    inventory = []
    for document in documents:
        metadata = document["metadata"]
        inventory.append(
            {
                "api_version": str(document.get("apiVersion", "")),
                "kind": str(document["kind"]),
                "namespace": str(metadata.get("namespace", "")),
                "name": str(metadata["name"]),
            }
        )
    return inventory


def platform_key() -> str:
    machine = platform.machine().lower()
    normalized = {"x86_64": "amd64", "aarch64": "arm64"}.get(machine, machine)
    return f"{platform.system().lower()}-{normalized}"


def toolchain_identity(kubectl: Path) -> dict[str, Any]:
    version = require_mapping(
        json.loads(run([str(kubectl), "version", "--client", "-o", "json"])),
        "kubectl version",
    )
    client = require_mapping(version.get("clientVersion"), "kubectl clientVersion")
    python_path = Path(sys.executable).resolve()
    yaml_path = Path(yaml.__file__).resolve()
    return {
        "platform": platform_key(),
        "python": {
            "version": platform.python_version(),
            "binary_sha256": sha256_file(python_path),
        },
        "pyyaml": {
            "version": yaml.__version__,
            "package_sha256": python_package_digest(yaml_path.parent),
            "with_libyaml": bool(getattr(yaml, "__with_libyaml__", False)),
        },
        "kubectl": {
            "version": client.get("gitVersion"),
            "kustomize_version": version.get("kustomizeVersion"),
            "binary_sha256": sha256_file(kubectl.resolve()),
        },
    }


def kustomization_references_target(root: Path, target: Path) -> bool:
    """Return whether a local Kustomize resource graph reaches target."""
    root = root.resolve()
    target = target.resolve()
    if root == target:
        return True
    kustomization = root / "kustomization.yaml"
    if not kustomization.is_file():
        return False
    document = require_mapping(
        yaml.safe_load(kustomization.read_text(encoding="utf-8")),
        str(kustomization),
    )
    for resource in document.get("resources", []) or []:
        if not isinstance(resource, str):
            raise ValueError("Kustomize resources must be strings")
        candidate = (root / resource).resolve()
        if candidate == target:
            return True
        if candidate.is_dir() and kustomization_references_target(candidate, target):
            return True
    return False


def assert_phase5_preview_deployments(
    documents: list[dict[str, Any]],
    locked_images: dict[str, Any],
    retained_jobs: list[dict[str, Any]],
) -> None:
    def jobs_by_identity(
        candidates: list[dict[str, Any]], description: str
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        result: dict[tuple[str, str, str], dict[str, Any]] = {}
        for candidate in candidates:
            if candidate.get("kind") != "Job":
                continue
            metadata = require_mapping(candidate.get("metadata", {}), description)
            identity = (
                "Job",
                str(metadata.get("namespace", "")),
                str(metadata.get("name", "")),
            )
            if not identity[1] or not identity[2] or identity in result:
                raise ValueError(f"{description} has an invalid Job identity")
            result[identity] = candidate
        return result

    expected_jobs = jobs_by_identity(retained_jobs, "Phase 5 retained Job baseline")
    expected_job_stages = {
        ("database", "phase4a-database-bootstrap"),
        ("starbase-system", "phase4a-core-migration"),
        ("starbase-system", "phase4a-gateway-migration"),
        ("starbase-system", "phase4a-network-boundary"),
    }
    observed_job_stages = {
        (
            identity[1],
            str(
                require_mapping(job.get("metadata", {}), "Phase 5 retained Job")
                .get("annotations", {})
                .get("starbase.io/activation-stage", "")
            ),
        )
        for identity, job in expected_jobs.items()
    }
    if observed_job_stages != expected_job_stages:
        raise ValueError(
            "Phase 5 retained Job stages differ from the reviewed foundation policy"
        )

    expected_workloads = {
        ("Deployment", "starbase-system", "starbase-core"): 1,
        ("Deployment", "starbase-connectors", "starbase-preview-fixture"): 1,
        ("Deployment", "starbase-connectors", "starbase-github-connector"): 0,
        ("Deployment", "starbase-connectors", "starbase-kubernetes-connector"): 0,
        **{identity: None for identity in expected_jobs},
    }
    observed_workloads = {
        (
            str(document.get("kind", "")),
            str(document.get("metadata", {}).get("namespace", "")),
            str(document.get("metadata", {}).get("name", "")),
        ): (
            document.get("spec", {}).get("replicas")
            if document.get("kind") == "Deployment"
            else None
        )
        for document in documents
        if document.get("kind") in NATIVE_POD_PRODUCING_KINDS
    }
    if observed_workloads != expected_workloads:
        raise ValueError(
            "bounded Phase 5 preview workload inventory differs from policy: "
            f"expected {expected_workloads}, observed {observed_workloads}"
        )

    observed_jobs = jobs_by_identity(documents, "Phase 5 rendered resources")
    if observed_jobs != expected_jobs:
        raise ValueError(
            "Phase 5 retained Job definitions differ from the reviewed foundation"
        )
    if any(
        "kustomize.toolkit.fluxcd.io/force"
        in require_mapping(
            job.get("metadata", {}), "Phase 5 retained Job metadata"
        ).get("annotations", {})
        for job in expected_jobs.values()
    ):
        raise ValueError("Phase 5 retained Job force replacement is forbidden")

    def one(kind: str, namespace: str, name: str) -> dict[str, Any]:
        matches = [
            document
            for document in documents
            if document.get("kind") == kind
            and document.get("metadata", {}).get("namespace", "") == namespace
            and document.get("metadata", {}).get("name") == name
        ]
        if len(matches) != 1:
            raise ValueError(f"Phase 5 fixture boundary requires one {kind}/{name}")
        return matches[0]

    fixture = one("Deployment", "starbase-connectors", "starbase-preview-fixture")

    core = one("Deployment", "starbase-system", "starbase-core")
    core_pod = require_mapping(
        require_mapping(core.get("spec", {}), "preview core spec")
        .get("template", {})
        .get("spec", {}),
        "preview core pod",
    )
    core_containers = core_pod.get("containers", [])

    expected_active_images = {
        ("starbase-system", "starbase-core", "core"): locked_images.get("core"),
        ("starbase-system", "starbase-core", "web"): locked_images.get("web"),
        (
            "starbase-connectors",
            "starbase-preview-fixture",
            "connector",
        ): locked_images.get("github-connector"),
    }
    if any(not isinstance(image, str) for image in expected_active_images.values()):
        raise ValueError("promotion lock lacks a Phase 5 active image")
    observed_active_images: dict[tuple[str, str, str], Any] = {}
    for deployment in (core, fixture):
        metadata = require_mapping(deployment.get("metadata", {}), "active metadata")
        pod_spec = require_mapping(
            require_mapping(deployment.get("spec", {}), "active spec")
            .get("template", {})
            .get("spec", {}),
            "active pod",
        )
        for container_class in ("initContainers", "containers"):
            for active_container in pod_spec.get(container_class, []) or []:
                active = require_mapping(active_container, "active container")
                observed_active_images[
                    (
                        str(metadata.get("namespace", "")),
                        str(metadata.get("name", "")),
                        str(active.get("name", "")),
                    )
                ] = active.get("image")
    if observed_active_images != expected_active_images:
        raise ValueError(
            "Phase 5 active images are not release-locked: "
            f"expected {expected_active_images}, observed {observed_active_images}"
        )

    core_container = next(
        (
            item
            for item in core_containers
            if isinstance(item, dict) and item.get("name") == "core"
        ),
        None,
    )
    if not isinstance(core_container, dict):
        raise ValueError("Phase 5 core issuer identity requires the core container")
    core_environment = {
        str(item.get("name")): item.get("value")
        for item in core_container.get("env", [])
        if isinstance(item, dict)
    }
    if core_environment.get("STARBASE_WORKLOAD_OIDC_TOKEN_FILE") != (
        "/var/run/secrets/starbase.io/workload-issuer-identity/token"
    ):
        raise ValueError("Phase 5 core issuer identity path differs from policy")
    core_volumes = {
        str(item.get("name")): item
        for item in core_pod.get("volumes", [])
        if isinstance(item, dict)
    }
    issuer_token = (
        core_volumes.get("workload-issuer-identity", {})
        .get("projected", {})
        .get("sources", [{}])[0]
        .get("serviceAccountToken", {})
    )
    if issuer_token != {
        "audience": "https://kubernetes.default.svc.cluster.local",
        "expirationSeconds": 600,
        "path": "token",
    }:
        raise ValueError("Phase 5 core issuer identity differs from policy")

    pod = require_mapping(
        require_mapping(fixture.get("spec", {}), "preview fixture spec")
        .get("template", {})
        .get("spec", {}),
        "preview fixture pod",
    )
    containers = pod.get("containers", [])
    if not isinstance(containers, list) or len(containers) != 1:
        raise ValueError("Phase 5 fixture boundary requires one container")
    container = require_mapping(containers[0], "preview fixture container")
    environment = {
        str(item.get("name")): item.get("value")
        for item in container.get("env", [])
        if isinstance(item, dict)
    }
    if environment != {
        "STARBASE_CONNECTOR_MODE": "fixture",
        "STARBASE_FIXTURE_PATH": "/var/run/starbase-preview/repository.json",
    }:
        raise ValueError("Phase 5 fixture boundary has unsafe runtime configuration")
    if container.get("envFrom") != [
        {"configMapRef": {"name": "starbase-connector-runtime"}}
    ]:
        raise ValueError(
            "Phase 5 fixture boundary has an unexpected configuration source"
        )
    if (
        pod.get("serviceAccountName") != "starbase-preview-fixture"
        or pod.get("automountServiceAccountToken") is not False
    ):
        raise ValueError("Phase 5 fixture boundary has an unsafe workload identity")
    volume_items = pod.get("volumes", [])
    if not isinstance(volume_items, list) or any(
        not isinstance(item, dict) for item in volume_items
    ):
        raise ValueError("Phase 5 fixture boundary has an unexpected volume")
    volumes = {str(item.get("name")): item for item in volume_items}
    expected_volumes = {
        "temporary-files": {
            "name": "temporary-files",
            "emptyDir": {"sizeLimit": "64Mi"},
        },
        "fixture": {
            "name": "fixture",
            "configMap": {
                "name": "starbase-preview-fixture-v1",
                "defaultMode": 288,
                "items": [{"key": "repository.json", "path": "repository.json"}],
            },
        },
        "core-workload-identity": {
            "name": "core-workload-identity",
            "projected": {
                "defaultMode": 288,
                "sources": [
                    {
                        "serviceAccountToken": {
                            "audience": "starbase-core",
                            "expirationSeconds": 600,
                            "path": "token",
                        }
                    }
                ],
            },
        },
    }
    if len(volume_items) != len(volumes) or volumes != expected_volumes:
        raise ValueError("Phase 5 fixture boundary has an unexpected volume")

    fixture_config = one(
        "ConfigMap", "starbase-connectors", "starbase-preview-fixture-v1"
    )
    fixture_data = require_mapping(fixture_config.get("data", {}), "fixture data")
    fixture_content = fixture_data.get("repository.json")
    fixture_annotations = require_mapping(
        fixture_config.get("metadata", {}).get("annotations", {}),
        "fixture annotations",
    )
    if (
        fixture_config.get("immutable") is not True
        or not isinstance(fixture_content, str)
        or fixture_annotations.get("starbase.io/content-digest")
        != sha256_bytes(fixture_content.encode("utf-8"))
    ):
        raise ValueError("Phase 5 fixture boundary is not immutable and content-bound")
    try:
        fixture_repository = require_mapping(
            json.loads(fixture_content), "fixture repository"
        )
    except json.JSONDecodeError as exc:
        raise ValueError("Phase 5 fixture boundary contains invalid JSON") from exc
    if (
        fixture_repository.get("owner") != "starbase-preview"
        or fixture_repository.get("name") != "synthetic-observation"
    ):
        raise ValueError("Phase 5 fixture boundary is not visibly synthetic")

    for document in documents:
        if document.get("kind") not in {"RoleBinding", "ClusterRoleBinding"}:
            continue
        for subject in document.get("subjects", []) or []:
            if not isinstance(subject, dict):
                continue
            subject_kind = subject.get("kind")
            subject_name = subject.get("name")
            subject_namespace = subject.get("namespace")
            fixture_subject = (
                (
                    subject_kind == "ServiceAccount"
                    and subject_name == "starbase-preview-fixture"
                    and subject_namespace in {None, "", "starbase-connectors"}
                )
                or (
                    subject_kind == "User"
                    and subject_name
                    == "system:serviceaccount:starbase-connectors:starbase-preview-fixture"
                )
                or (
                    subject_kind == "Group"
                    and subject_name
                    in {
                        "system:authenticated",
                        "system:serviceaccounts",
                        "system:serviceaccounts:starbase-connectors",
                    }
                )
            )
            if fixture_subject:
                raise ValueError(
                    "Phase 5 fixture boundary may not receive Kubernetes RBAC"
                )

    fixture_labels = require_mapping(
        require_mapping(fixture.get("spec", {}), "preview fixture spec")
        .get("template", {})
        .get("metadata", {})
        .get("labels", {}),
        "preview fixture labels",
    )
    matching_policies: set[str] = set()
    for document in documents:
        if (
            document.get("kind") != "NetworkPolicy"
            or document.get("metadata", {}).get("namespace") != "starbase-connectors"
        ):
            continue
        selector = require_mapping(
            document.get("spec", {}).get("podSelector", {}),
            "preview NetworkPolicy selector",
        )
        if set(selector) - {"matchLabels"}:
            raise ValueError(
                "Phase 5 fixture boundary cannot evaluate a complex selector"
            )
        labels = require_mapping(selector.get("matchLabels", {}), "selector labels")
        if all(fixture_labels.get(key) == value for key, value in labels.items()):
            matching_policies.add(str(document.get("metadata", {}).get("name", "")))
    if matching_policies != {
        "default-deny",
        "allow-dns",
        "allow-preview-fixture-to-core",
    }:
        raise ValueError(
            "Phase 5 fixture boundary has unexpected matching egress policy"
        )
    expected_egress = {
        "default-deny": {
            "podSelector": {},
            "policyTypes": ["Ingress", "Egress"],
        },
        "allow-dns": {
            "podSelector": {},
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "kube-system"
                                }
                            },
                            "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                        }
                    ],
                    "ports": [
                        {"protocol": "UDP", "port": 53},
                        {"protocol": "TCP", "port": 53},
                    ],
                }
            ],
        },
        "allow-preview-fixture-to-core": {
            "podSelector": {
                "matchLabels": {"app.kubernetes.io/name": "starbase-preview-fixture"}
            },
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {
                                    "kubernetes.io/metadata.name": "starbase-system"
                                }
                            },
                            "podSelector": {
                                "matchLabels": {
                                    "app.kubernetes.io/name": "starbase-core"
                                }
                            },
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 8081}],
                }
            ],
        },
    }
    for policy_name, expected_spec in expected_egress.items():
        if (
            one("NetworkPolicy", "starbase-connectors", policy_name).get("spec")
            != expected_spec
        ):
            raise ValueError(
                f"Phase 5 fixture boundary egress differs from policy: {policy_name}"
            )


def assert_phase5_preview_kustomization_is_bounded(
    kustomization: dict[str, Any],
) -> None:
    observed_fields = set(kustomization)
    if observed_fields != PHASE5_PREVIEW_KUSTOMIZATION_FIELDS:
        raise ValueError(
            "Phase 5 preview Kustomization fields differ from policy: "
            f"expected {sorted(PHASE5_PREVIEW_KUSTOMIZATION_FIELDS)}, "
            f"observed {sorted(observed_fields)}"
        )
    if (
        kustomization.get("apiVersion") != "kustomize.config.k8s.io/v1beta1"
        or kustomization.get("kind") != "Kustomization"
        or kustomization.get("resources")
        != [
            "../starbase-phase4a-foundation",
            "preview-fixture.yaml",
            "preview-network-policies.yaml",
        ]
        or kustomization.get("patches") != [{"path": "core-preview-patch.yaml"}]
    ):
        raise ValueError("bounded Phase 5 preview composition differs from policy")


def assert_phase5_preview_is_bounded(repository: Path) -> None:
    preview = repository / "infrastructure/gitops/apps/starbase-phase5-preview"
    kustomization = require_mapping(
        yaml.safe_load((preview / "kustomization.yaml").read_text(encoding="utf-8")),
        "Phase 5 preview Kustomization",
    )
    assert_phase5_preview_kustomization_is_bounded(kustomization)
    rendered = run(["kubectl", "kustomize", str(preview)])
    documents = [
        require_mapping(document, "Phase 5 preview document")
        for document in yaml.safe_load_all(rendered)
        if document is not None
    ]
    promotion_lock = load_json(
        repository / "infrastructure/gitops/apps/starbase/promotion-lock.json"
    )
    release = require_mapping(promotion_lock.get("release", {}), "promotion release")
    images = require_mapping(release.get("images", {}), "promotion images")
    foundation_rendered = run(
        [
            "kubectl",
            "kustomize",
            str(repository / "infrastructure/gitops/apps/starbase-phase4a-foundation"),
        ]
    )
    foundation_documents = []
    for document in yaml.safe_load_all(foundation_rendered):
        if document is None:
            continue
        retained = require_mapping(document, "Phase 5 retained Job baseline")
        if retained.get("kind") == "Job":
            foundation_documents.append(retained)
    assert_phase5_preview_deployments(documents, images, foundation_documents)


def assert_phase5_flux_kustomization_is_bounded(spec: dict[str, Any]) -> None:
    observed_fields = set(spec)
    missing = PHASE5_FLUX_REQUIRED_SPEC_FIELDS - observed_fields
    unknown = observed_fields - PHASE5_FLUX_ALLOWED_SPEC_FIELDS
    invalid_force = "force" in spec and spec["force"] is not False
    if missing or unknown or invalid_force:
        raise ValueError(
            "Phase 5 Flux Kustomization spec fields differ from policy: "
            f"missing={sorted(missing)}, unknown={sorted(unknown)}, "
            f"force={spec.get('force', '<absent>')!r}"
        )


def assert_activation_matches_flux(input_path: Path) -> None:
    repository = Path(
        run(["git", "rev-parse", "--show-toplevel"], cwd=input_path.parent).strip()
    )
    promotion = load_json(input_path)
    activation = promotion.get("expected_activation")
    flux_root = repository / "infrastructure/gitops/flux-system"
    aggregate = flux_root / "kustomization.yaml"
    aggregate_config = require_mapping(
        yaml.safe_load(aggregate.read_text(encoding="utf-8")), str(aggregate)
    )
    starbase_root = (repository / "infrastructure/gitops/apps/starbase").resolve()
    references: list[tuple[str, str]] = []
    reference_specs: dict[tuple[str, str], dict[str, Any]] = {}
    for resource in aggregate_config.get("resources", []) or []:
        if not isinstance(resource, str):
            raise ValueError("Flux aggregate resources must be strings")
        resource_path = (flux_root / resource).resolve()
        if not resource_path.is_file():
            continue
        for document in yaml.safe_load_all(resource_path.read_text(encoding="utf-8")):
            if not isinstance(document, dict):
                continue
            if document.get("kind") != "Kustomization" or not str(
                document.get("apiVersion", "")
            ).startswith("kustomize.toolkit.fluxcd.io/"):
                continue
            spec = require_mapping(document.get("spec", {}), "Flux Kustomization spec")
            managed_path = spec.get("path")
            if not isinstance(managed_path, str) or not managed_path.startswith("./"):
                continue
            resolved = (repository / managed_path.removeprefix("./")).resolve()
            if kustomization_references_target(resolved, starbase_root):
                metadata = require_mapping(document.get("metadata", {}), "metadata")
                reference = (str(metadata.get("name", "")), managed_path)
                references.append(reference)
                reference_specs[reference] = spec

    if activation == INACTIVE_ACTIVATION:
        if references:
            raise ValueError(
                "inactive Starbase activation intent conflicts with Flux references: "
                f"{references}"
            )
        return
    if activation == INERT_FOUNDATION_ACTIVATION:
        foundation = [
            (
                "starbase-foundation",
                "./infrastructure/gitops/apps/starbase-phase4a-foundation",
            )
        ]
        preview = [
            (
                "starbase-foundation",
                "./infrastructure/gitops/apps/starbase-phase5-preview",
            )
        ]
        if references == foundation:
            return
        if references == preview:
            # The immutable release bundle remains inert. A later deployment
            # overlay may activate only the separately bounded synthetic
            # preview pair; validate that exact deployment state here rather
            # than rewriting the retained release lock.
            assert_phase5_flux_kustomization_is_bounded(reference_specs[preview[0]])
            assert_phase5_preview_is_bounded(repository)
            return
        raise ValueError(
            "inert bundle has an unsupported Flux activation overlay: "
            f"expected {foundation} or {preview}, observed {references}"
        )
    raise ValueError("expected_activation is not a supported bounded state")


def create_bundle(
    evidence_source: Path,
    starbase_source: Path,
    input_path: Path,
    kubectl: Path,
) -> tuple[bytes, bytes]:
    config = load_json(input_path)
    evidence = require_mapping(config.get("manifest_evidence"), "manifest_evidence")
    repository = str(config.get("repository", ""))
    evidence_revision = str(evidence.get("revision", ""))
    verify_checkout(evidence_source, evidence_revision, repository, "manifest evidence")
    manifest_relative = require_relative_path(evidence.get("path"), "manifest path")
    manifest = load_verified_manifest(
        evidence_source / manifest_relative, str(evidence.get("sha256", ""))
    )
    validate_release_manifest(manifest, config)

    source_revision = str(manifest["revision"])
    verify_checkout(starbase_source, source_revision, repository, "Starbase source")
    base_relative = require_relative_path(config.get("base_path"), "base path")
    base_path = starbase_source / base_relative
    validate_local_kustomization(base_path)
    assert_activation_matches_flux(input_path)

    rendered_source = run([str(kubectl), "kustomize", str(base_path)])
    source_documents = [
        require_mapping(document, "Kustomize document")
        for document in yaml.safe_load_all(rendered_source)
        if document is not None
    ]
    documents = transform_and_validate(source_documents, manifest, config)
    rendered = render_yaml(documents)
    toolchain = toolchain_identity(kubectl)

    supported = config.get("supported_execution_platforms")
    if supported != [toolchain["platform"]]:
        raise ValueError(
            "this promotion input must list exactly the platform whose binary digests "
            "are being recorded"
        )

    lock = {
        "schema_version": 1,
        "repository": repository,
        "manifest_evidence": {
            "revision": evidence_revision,
            "path": manifest_relative.as_posix(),
            "sha256": str(evidence["sha256"]),
        },
        "release": {
            "version": manifest["version"],
            "source_revision": source_revision,
            "images": {
                str(item["name"]): f"{item['image']}@{item['digest']}"
                for item in manifest["images"]
            },
        },
        "inputs": {
            "base_path": base_relative.as_posix(),
            "base_tree_sha256": directory_digest(base_path),
            "overlay_input_sha256": sha256_bytes(canonical_json(config)),
            "renderer_sha256": sha256_file(Path(__file__).resolve()),
            "toolchains": {toolchain["platform"]: toolchain},
        },
        "output": {
            "rendered_manifest_sha256": sha256_bytes(rendered),
            "object_count": len(documents),
            "inventory": object_inventory(documents),
        },
        "activation": copy.deepcopy(config["expected_activation"]),
    }
    return rendered, canonical_json(lock)


def verify_repository_bundle(
    input_path: Path, output_path: Path, lock_path: Path
) -> None:
    """Verify credential-free invariants of the committed inactive bundle."""
    config = load_json(input_path)
    lock = load_json(lock_path)
    rendered = output_path.read_bytes()
    output = require_mapping(lock.get("output"), "promotion lock output")
    if sha256_bytes(rendered) != output.get("rendered_manifest_sha256"):
        raise ValueError("committed rendered manifest digest differs from lock")

    documents = [
        require_mapping(document, "committed rendered document")
        for document in yaml.safe_load_all(rendered)
        if document is not None
    ]
    if len(documents) != output.get("object_count"):
        raise ValueError("committed rendered object count differs from lock")
    if object_inventory(documents) != output.get("inventory"):
        raise ValueError("committed rendered inventory differs from lock")
    if lock.get("activation") != config.get("expected_activation"):
        raise ValueError("committed activation intent differs from promotion input")

    forbidden = [
        document
        for document in documents
        if document.get("kind") in {"Ingress", "Secret"}
    ]
    if forbidden:
        raise ValueError("committed bundle contains a forbidden Secret or Ingress")

    rbac_identities: set[tuple[str, str]] = set()
    for document in documents:
        kind = str(document.get("kind", ""))
        name = str(
            require_mapping(document.get("metadata", {}), "metadata").get("name", "")
        )
        workload_spec = pod_spec(document)
        if kind in WORKLOAD_KINDS:
            assert workload_spec is not None
            if workload_spec.get("automountServiceAccountToken") is not False:
                raise ValueError(
                    f"committed {kind}/{name} enables automatic token mounting"
                )
            validate_workload_security(kind, name, workload_spec)
        validate_network_policy(document)
        rbac_identity = validate_observer_rbac(document)
        if rbac_identity is not None:
            if rbac_identity in rbac_identities:
                raise ValueError(
                    "committed bundle duplicates a namespace observer RBAC identity"
                )
            rbac_identities.add(rbac_identity)
    expected_rbac_identities = {
        (kind, namespace)
        for kind in ("Role", "RoleBinding")
        for namespace in EXPECTED_OBSERVER_NAMESPACES
    }
    if rbac_identities != expected_rbac_identities:
        raise ValueError(
            "committed bundle must contain exact namespace observer roles and bindings"
        )

    github = [
        document
        for document in documents
        if document.get("kind") == "Deployment"
        and document.get("metadata", {}).get("name") == "starbase-github-connector"
    ]
    if len(github) != 1 or github[0].get("spec", {}).get("replicas") != 0:
        raise ValueError("committed GitHub connector must remain at zero replicas")
    if (
        github[0]
        .get("metadata", {})
        .get("annotations", {})
        .get("starbase.io/activation-state")
        != "intentionally-disabled-no-egress"
    ):
        raise ValueError("committed GitHub connector activation intent is missing")

    expected_images = set(
        require_mapping(lock.get("release"), "promotion lock release")
        .get("images", {})
        .values()
    )
    actual_images = [
        parent[key] for document in documents for parent, key in image_slots(document)
    ]
    if set(actual_images) != expected_images or len(actual_images) != len(
        expected_images
    ):
        raise ValueError("committed bundle images differ from promotion lock")
    assert_activation_matches_flux(input_path)


def verify_exact_files(
    output_path: Path,
    lock_path: Path,
    expected_output: bytes,
    expected_lock: bytes,
) -> None:
    if output_path.read_bytes() != expected_output:
        raise ValueError(
            "committed rendered manifest differs from deterministic output"
        )
    if lock_path.read_bytes() != expected_lock:
        raise ValueError("committed promotion lock differs from deterministic output")


def write_exact(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("generate", "verify"))
    parser.add_argument("--evidence-source", type=Path, required=True)
    parser.add_argument("--starbase-source", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--kubectl", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output, lock = create_bundle(
            args.evidence_source.resolve(),
            args.starbase_source.resolve(),
            args.input.resolve(),
            args.kubectl.resolve(),
        )
        if args.mode == "generate":
            write_exact(args.output, output)
            write_exact(args.lock, lock)
        else:
            verify_exact_files(args.output, args.lock, output, lock)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
