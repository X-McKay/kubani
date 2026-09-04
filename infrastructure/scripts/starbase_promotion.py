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
PHASE5_RUNTIME_ROLLBACK_KUSTOMIZATION = {
    "apiVersion": "kustomize.config.k8s.io/v1beta1",
    "kind": "Kustomization",
    "resources": ["../starbase-phase5-preview"],
    "patches": [
        {"path": "core-runtime-rollback-patch.yaml"},
        {"path": "fixture-runtime-rollback-patch.yaml"},
    ],
}
PHASE5_SESSION_REPAIR_CORE_IMAGE = (
    "ghcr.io/x-mckay/starbase/core@"
    "sha256:68385b100f24f5a28738799bc3712d6322226760a75ded14c947afbc36533345"  # pragma: allowlist secret
)
PHASE5_SESSION_REPAIR_KUSTOMIZATION = {
    "apiVersion": "kustomize.config.k8s.io/v1beta1",
    "kind": "Kustomization",
    "resources": ["../starbase-phase5-preview"],
    "patches": [{"path": "core-repair-patch.yaml"}],
}
PHASE5_SESSION_REPAIR_PATCH = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "starbase-core",
        "namespace": "starbase-system",
        "annotations": {
            "starbase.io/activation-state": (
                "authorized-preproduction-native-observatory"
            ),
            "starbase.io/activation-stage": (
                "phase5-preproduction-native-observatory"
            ),
        },
    },
    "spec": {
        "template": {
            "metadata": {
                "annotations": {
                    "starbase.io/activation-state": (
                        "authorized-preproduction-native-observatory"
                    ),
                    "starbase.io/activation-stage": (
                        "phase5-preproduction-native-observatory"
                    ),
                    "starbase.io/source-revision": (
                        "b3d54bc875c176dba766682a55d3bb2ca2801819"  # pragma: allowlist secret
                    ),
                }
            },
            "spec": {
                "containers": [
                    {"name": "core", "image": PHASE5_SESSION_REPAIR_CORE_IMAGE}
                ]
            },
        }
    },
}
PHASE6_CORE_IMAGE = (
    "ghcr.io/x-mckay/starbase/core@"
    "sha256:b906d2d2d3e2aff743974cd829b548932101615f9f10ca2ad3c5413b84eb4809"
)
PHASE6_KUBERNETES_CONNECTOR_IMAGE = (
    "ghcr.io/x-mckay/starbase/kubernetes-connector@"
    "sha256:70595d0171b481ae78b221e52b11f38a67aedf6768974fb77b19a875c42ae7c5"
)
PHASE6_KUBERNETES_SOURCE_REVISION = (
    "400711d9fbb3e068f6dff274e58db26bcae934e3"  # pragma: allowlist secret
)
PHASE6_KUBERNETES_CANARY_KUSTOMIZATION = {
    "apiVersion": "kustomize.config.k8s.io/v1beta1",
    "kind": "Kustomization",
    "resources": ["../starbase-phase5-session-repair"],
    "patches": [
        {"path": "core-kubernetes-source-patch.yaml"},
        {"path": "kubernetes-connector-canary-patch.yaml"},
    ],
}
PHASE6_CORE_PATCH = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "starbase-core",
        "namespace": "starbase-system",
        "annotations": {
            "starbase.io/activation-state": (
                "authorized-preproduction-kubernetes-canary"
            ),
            "starbase.io/activation-stage": "phase6-kubernetes-observation",
        },
    },
    "spec": {
        "template": {
            "metadata": {
                "annotations": {
                    "starbase.io/activation-state": (
                        "authorized-preproduction-kubernetes-canary"
                    ),
                    "starbase.io/activation-stage": (
                        "phase6-kubernetes-observation"
                    ),
                    "starbase.io/source-revision": (
                        PHASE6_KUBERNETES_SOURCE_REVISION
                    ),
                    "starbase.io/artifact-class": "owner-local-preproduction",
                }
            },
            "spec": {
                "containers": [
                    {
                        "name": "core",
                        "image": PHASE6_CORE_IMAGE,
                        "env": [
                            {
                                "name": "STARBASE_EXPECTED_SOURCES",
                                "value": (
                                    '{"github:starbase-preview/synthetic-observation":'
                                    '"github","kubernetes:kubani:'
                                    'starbase-namespaces-v1":"kubernetes"}'
                                ),
                            },
                            {
                                "name": "STARBASE_CONNECTOR_IDENTITIES",
                                "value": (
                                    '{"system:serviceaccount:starbase-connectors:'
                                    'starbase-preview-fixture":["github"],'
                                    '"system:serviceaccount:starbase-connectors:'
                                    'starbase-kubernetes-connector":["kubernetes"]}'
                                ),
                            },
                        ],
                    }
                ]
            },
        }
    },
}
PHASE6_CONNECTOR_PATCH = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "starbase-kubernetes-connector",
        "namespace": "starbase-connectors",
        "annotations": {
            "starbase.io/activation-state": (
                "authorized-preproduction-kubernetes-canary"
            ),
            "starbase.io/activation-stage": "phase6-kubernetes-observation",
        },
    },
    "spec": {
        "replicas": 1,
        "template": {
            "metadata": {
                "annotations": {
                    "starbase.io/activation-state": (
                        "authorized-preproduction-kubernetes-canary"
                    ),
                    "starbase.io/activation-stage": (
                        "phase6-kubernetes-observation"
                    ),
                    "starbase.io/source-revision": (
                        PHASE6_KUBERNETES_SOURCE_REVISION
                    ),
                    "starbase.io/artifact-class": "owner-local-preproduction",
                    "starbase.io/blocker": None,
                }
            },
            "spec": {
                "affinity": {
                    "nodeAffinity": {
                        "preferredDuringSchedulingIgnoredDuringExecution": None,
                        "requiredDuringSchedulingIgnoredDuringExecution": {
                            "nodeSelectorTerms": [
                                {
                                    "matchExpressions": [
                                        {
                                            "key": "kubernetes.io/hostname",
                                            "operator": "In",
                                            "values": ["asio", "strix"],
                                        }
                                    ]
                                }
                            ]
                        },
                    }
                },
                "containers": [
                    {
                        "name": "connector",
                        "image": PHASE6_KUBERNETES_CONNECTOR_IMAGE,
                    }
                ],
            },
        },
    },
}
PHASE7_GITHUB_CONNECTOR_IMAGE = (
    "ghcr.io/x-mckay/starbase/github-connector@"
    "sha256:cdec332a5c181a0038373c1c9d3b4ac4f6eff480b51ffca67c786be2b89d93c8"
)
PHASE7_WEB_IMAGE = (
    "ghcr.io/x-mckay/starbase/web@"
    "sha256:4e97f206917bb72b4c001cb3c75822f4f642c105ef4700cc2722b1c3e3a1ff81"
)
PHASE7_GITHUB_CANARY_KUSTOMIZATION = {
    "apiVersion": "kustomize.config.k8s.io/v1beta1",
    "kind": "Kustomization",
    "resources": [
        "../starbase-phase6-github-canary-prepared",
        "github-app-secret.enc.yaml",
    ],
    "patches": [
        {"path": "core-github-source-patch.yaml"},
        {"path": "github-connector-activation-patch.yaml"},
        {"path": "web-ui-acceptance-patch.yaml"},
    ],
}
PHASE7_WEB_PATCH = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "starbase-core", "namespace": "starbase-system"},
    "spec": {
        "template": {
            "spec": {
                "containers": [
                    {
                        "name": "web",
                        "image": PHASE7_WEB_IMAGE,
                        "imagePullPolicy": "IfNotPresent",
                    }
                ]
            }
        }
    },
}
PHASE7_CORE_PATCH = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "starbase-core",
        "namespace": "starbase-system",
        "annotations": {
            "starbase.io/activation-state": (
                "authorized-preproduction-github-canary"
            ),
            "starbase.io/activation-stage": "phase7-github-observation",
        },
    },
    "spec": {
        "template": {
            "metadata": {
                "annotations": {
                    "starbase.io/activation-state": (
                        "authorized-preproduction-github-canary"
                    ),
                    "starbase.io/activation-stage": "phase7-github-observation",
                }
            },
            "spec": {
                "containers": [
                    {
                        "name": "core",
                        "env": [
                            {
                                "name": "STARBASE_EXPECTED_SOURCES",
                                "value": (
                                    '{"github:X-McKay/Starbase":"github",'
                                    '"github:starbase-preview/synthetic-observation":'
                                    '"github","kubernetes:kubani:'
                                    'starbase-namespaces-v1":"kubernetes"}'
                                ),
                            },
                            {
                                "name": "STARBASE_CONNECTOR_IDENTITIES",
                                "value": (
                                    '{"system:serviceaccount:starbase-connectors:'
                                    'starbase-github-connector":["github"],'
                                    '"system:serviceaccount:starbase-connectors:'
                                    'starbase-kubernetes-connector":["kubernetes"],'
                                    '"system:serviceaccount:starbase-connectors:'
                                    'starbase-preview-fixture":["github"]}'
                                ),
                            },
                        ],
                    }
                ]
            },
        }
    },
}
PHASE7_GITHUB_CONNECTOR_PATCH = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {
        "name": "starbase-github-connector",
        "namespace": "starbase-connectors",
        "annotations": {
            "starbase.io/activation-state": (
                "authorized-preproduction-github-canary"
            ),
            "starbase.io/activation-stage": "phase7-github-observation",
        },
    },
    "spec": {
        "replicas": 1,
        "template": {
            "metadata": {
                "annotations": {
                    "starbase.io/activation-state": (
                        "authorized-preproduction-github-canary"
                    ),
                    "starbase.io/activation-stage": "phase7-github-observation",
                    "starbase.io/blocker": None,
                }
            }
        },
    },
}
PHASE9_SOURCE_REVISION = (
    "40bacc987ee45c0c65787c681340c89cafab0b8c"  # pragma: allowlist secret
)
PHASE9_IMAGES = {
    "core": (
        "ghcr.io/x-mckay/starbase/core@"
        "sha256:e70596ab4514f64714307e223d4a2b2d74ebc535e56af5b6e7891c42ea4b9c4b"
    ),
    "web": (
        "ghcr.io/x-mckay/starbase/web@"
        "sha256:6e237e10d23e4cce4b9aaf8bdd40f4ed6f9230d1275b8dbd5702a36b75bb40a0"
    ),
    "github-connector": (
        "ghcr.io/x-mckay/starbase/github-connector@"
        "sha256:8573733893dfc65ab9046b5d426d49805653d316d981d92b8519ceacd2b0ab64"
    ),
    "kubernetes-connector": (
        "ghcr.io/x-mckay/starbase/kubernetes-connector@"
        "sha256:58a815ea51eab5dc5bc6fa2504065822ae7acd0f03c95d782dba76c34dbe362e"
    ),
    "dojo-runtime": (
        "ghcr.io/x-mckay/starbase/dojo-runtime@"
        "sha256:abb76835bb0d5c8c5f52d3e3e5a1a0f290d06596720e3d9e5c2396170c5c0b2d"
    ),
}
PHASE9_FOUNDATION_KUSTOMIZATION = {
    "apiVersion": "kustomize.config.k8s.io/v1beta1",
    "kind": "Kustomization",
    "resources": [
        "../starbase-phase7-github-canary",
        "dojo-reader-secret.enc.yaml",
        "dojo-ca-configmap.yaml",
        "dojo-reader-network-policy.yaml",
    ],
    "patches": [{"path": "signed-observer-and-dojo-reader-patch.yaml"}],
}
PHASE9_DOJO_KUSTOMIZATION = {
    "apiVersion": "kustomize.config.k8s.io/v1beta1",
    "kind": "Kustomization",
    "resources": [
        "../starbase-phase8-dojo-preproduction",
        "dojo-tls.yaml",
        "dojo-reader-network-policy.yaml",
        "dojo-ca-secret.enc.yaml",
    ],
    "patches": [{"path": "governed-proposal-runtime-patch.yaml"}],
}
PHASE10_READER_SOURCE_REVISION = (
    "5ffa445a21796c8d745197186fbf348f056893e4"  # pragma: allowlist secret
)
PHASE10_READER_RELEASE_MANIFEST_DIGEST = (
    "sha256:4c26e778b72a81ea89af0a505c59f24cbef2a8adb302a791f937231ef1e38ae8"
)
PHASE10_READER_IMAGES = {
    "core": (
        "ghcr.io/x-mckay/starbase/core@"
        "sha256:008327ad0083c0b94f13d6b6fb7cdcc9c7e588f739737e23dacc1f2af0c7db44"
    ),
    "web": (
        "ghcr.io/x-mckay/starbase/web@"
        "sha256:2cbd3de603bcf62b6ef9e9415849aca06e6ccf79ebf29ef7e13cf99c0c85ae25"
    ),
    "github-connector": (
        "ghcr.io/x-mckay/starbase/github-connector@"
        "sha256:f848bd161dcaddd4afb74f9dfed7a86d3447c5ce300bd4aa45d725e5bfad67f6"
    ),
    "kubernetes-connector": (
        "ghcr.io/x-mckay/starbase/kubernetes-connector@"
        "sha256:96239515e2e7eaffdb8beda1afa670b27e8cac16f6fa2c1d7f847e9a10eae0e1"
    ),
}
PHASE10_READER_KUSTOMIZATION = {
    "apiVersion": "kustomize.config.k8s.io/v1beta1",
    "kind": "Kustomization",
    "resources": ["../starbase-phase9-foundation"],
    "patches": [{"path": "reader-preparation-patch.yaml"}],
}
PHASE10_READER_FOUNDATION_FLUX_DIGEST = (
    "sha256:11e1af2ca445ae4084e9e6707fd7c625881a8923fcd9bd817a689fae80ae76e6"
)
PHASE10_READER_PREPARATION_PATCH_DIGEST = (
    "sha256:2a45bf987cf5e6ef83f94ca1e7fd5ea182360fb5b9abf1e27180c053c036320e"
)
PHASE10_READER_RENDERED_INVENTORY_DIGEST = (
    "sha256:ac274d985c9f6302281197aef7fc6c479b057a406589314b4e14c2e4c1b27bcd"
)
RC4_RUNTIME_ROLLBACK_IMAGES = {
    "core": (
        "ghcr.io/x-mckay/starbase/core@"
        "sha256:61a0fe54fd5903f5afb9bbae254c794e590444611fdf089308b5a9f70e1e4054"
    ),
    "web": (
        "ghcr.io/x-mckay/starbase/web@"
        "sha256:ab5e5aa20e7c318f38bbfb8c20c739bfa10b5b4888ef152623367dbc24ed9baf"
    ),
    "github-connector": (
        "ghcr.io/x-mckay/starbase/github-connector@"
        "sha256:6a3a5324fb965d0b179f093606747f925f17ff9c2acf35847c2b07b1cd2dab06"
    ),
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
    "starbase-system",
    "starbase-connectors",
    "starbase-execution",
}
EXPECTED_OBSERVER_NAME = "starbase-kubernetes-observer"
EXPECTED_OBSERVER_ROLE_REF = {
    "apiGroup": "rbac.authorization.k8s.io",
    "kind": "Role",
    "name": EXPECTED_OBSERVER_NAME,
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
MIGRATION_IMAGES = {
    "starbase-core-migrate": "core-migrator",
    "starbase-gateway-migrate": "gateway-migrator",
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


def migration_execution_digests(
    manifest: dict[str, Any], images: dict[str, dict[str, Any]]
) -> dict[str, str]:
    migration_sets = migration_set_digests(manifest)
    return {
        job_name: sha256_bytes(
            canonical_json(
                {
                    "migration_set_digest": migration_set_digest,
                    "migrator_image_reference": (
                        f"{images[MIGRATION_IMAGES[job_name]]['image']}@"
                        f"{images[MIGRATION_IMAGES[job_name]]['digest']}"
                    ),
                }
            )
        )
        for job_name, migration_set_digest in migration_sets.items()
    }


def validate_observer_rbac(document: dict[str, Any]) -> tuple[str, str] | None:
    kind = document.get("kind")
    if kind not in {"Role", "RoleBinding"}:
        return None
    metadata = require_mapping(document.get("metadata", {}), f"{kind} metadata")
    if metadata.get("name") != EXPECTED_OBSERVER_NAME:
        raise ValueError(f"unexpected {kind} identity")
    namespace = metadata.get("namespace")
    if namespace not in EXPECTED_OBSERVER_NAMESPACES:
        raise ValueError(f"unexpected observer {kind} namespace")
    if kind == "Role":
        if document.get("rules") != EXPECTED_OBSERVER_RULES:
            raise ValueError("starbase observer Role rules differ from policy")
        return kind, str(namespace)
    if document.get("roleRef") != EXPECTED_OBSERVER_ROLE_REF:
        raise ValueError("starbase observer RoleBinding roleRef differs from policy")
    if document.get("subjects") != EXPECTED_OBSERVER_SUBJECTS:
        raise ValueError("starbase observer RoleBinding subjects differ from policy")
    return kind, str(namespace)


def observer_rbac_counts() -> dict[str, dict[str, int]]:
    return {
        namespace: {"Role": 0, "RoleBinding": 0}
        for namespace in EXPECTED_OBSERVER_NAMESPACES
    }


def require_exact_observer_rbac(
    counts: dict[str, dict[str, int]], prefix: str = "bundle"
) -> None:
    expected = {
        namespace: {"Role": 1, "RoleBinding": 1}
        for namespace in EXPECTED_OBSERVER_NAMESPACES
    }
    if counts != expected:
        raise ValueError(
            f"{prefix} must contain one exact Role and RoleBinding in each observer namespace"
        )


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
    rbac_counts = observer_rbac_counts()

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
        observer_identity = validate_observer_rbac(document)
        if observer_identity is not None:
            observer_kind, observer_namespace = observer_identity
            rbac_counts[observer_namespace][observer_kind] += 1

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

    require_exact_observer_rbac(rbac_counts)

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

    migration_sets = migration_set_digests(manifest)
    migration_executions = migration_execution_digests(manifest, images)
    for document in documents:
        name = document["metadata"]["name"]
        if document.get("kind") == "Job" and name in migration_executions:
            execution_digest = migration_executions[name]
            migration_set_digest = migration_sets[name]
            migrator_image = images[MIGRATION_IMAGES[name]]
            migrator_image_reference = (
                f"{migrator_image['image']}@{migrator_image['digest']}"
            )
            document["metadata"][
                "name"
            ] = f"{name}-{execution_digest.removeprefix('sha256:')[:12]}"
            annotations = document["metadata"].setdefault("annotations", {})
            annotations["starbase.io/migration-set-digest"] = migration_set_digest
            annotations["starbase.io/migrator-image"] = migrator_image_reference
            annotations["starbase.io/migrator-image-digest"] = migrator_image["digest"]
            annotations["starbase.io/migration-execution-digest"] = execution_digest
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
        width=1000,
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
    *,
    active_images: dict[str, Any] | None = None,
    github_connector_image: str | None = None,
    github_connector_replicas: int = 0,
    kubernetes_connector_replicas: int = 0,
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
        ("starbase-system", "rc5-unchanged-migrations-suspended"),
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
        (
            "Deployment",
            "starbase-connectors",
            "starbase-github-connector",
        ): github_connector_replicas,
        (
            "Deployment",
            "starbase-connectors",
            "starbase-kubernetes-connector",
        ): kubernetes_connector_replicas,
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

    approved_active_images = locked_images if active_images is None else active_images
    expected_active_images = {
        ("starbase-system", "starbase-core", "core"): approved_active_images.get(
            "core"
        ),
        ("starbase-system", "starbase-core", "web"): approved_active_images.get(
            "web"
        ),
        (
            "starbase-connectors",
            "starbase-preview-fixture",
            "connector",
        ): approved_active_images.get("github-connector"),
    }
    active_deployments = [core, fixture]
    if github_connector_replicas == 1:
        github_connector = one(
            "Deployment", "starbase-connectors", "starbase-github-connector"
        )
        expected_active_images[
            (
                "starbase-connectors",
                "starbase-github-connector",
                "connector",
            )
        ] = (
            github_connector_image
            if github_connector_image is not None
            else approved_active_images.get("github-connector")
        )
        active_deployments.append(github_connector)
    if kubernetes_connector_replicas == 1:
        kubernetes_connector = one(
            "Deployment", "starbase-connectors", "starbase-kubernetes-connector"
        )
        expected_active_images[
            (
                "starbase-connectors",
                "starbase-kubernetes-connector",
                "connector",
            )
        ] = approved_active_images.get("kubernetes-connector")
        active_deployments.append(kubernetes_connector)
    if any(not isinstance(image, str) for image in expected_active_images.values()):
        raise ValueError("promotion lock lacks a Phase 5 active image")
    observed_active_images: dict[tuple[str, str, str], Any] = {}
    for deployment in active_deployments:
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
            "Phase 5 active images are not release-locked or rollback-approved: "
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
    if "STARBASE_WORKLOAD_OIDC_TOKEN_FILE" in core_environment:
        raise ValueError("Phase 5 core uses an obsolete issuer identity variable")
    if (
        core_environment.get("STARBASE_WORKLOAD_OIDC_ISSUER")
        != "https://kubernetes.default.svc.cluster.local"
        or core_environment.get("STARBASE_WORKLOAD_OIDC_JWKS_URL")
        != "https://100.92.107.71:6443/openid/v1/jwks"
        or core_environment.get("STARBASE_OIDC_REQUIRED_GROUPS")
        != '["starbase-operators"]'
    ):
        raise ValueError("Phase 5 core issuer or operator identity differs from policy")
    runtime_configuration = require_mapping(
        one("ConfigMap", "starbase-system", "starbase-runtime").get("data", {}),
        "Phase 5 core runtime configuration",
    )
    if (
        runtime_configuration.get("STARBASE_WORKLOAD_IDENTITY_FILE")
        != "/var/run/secrets/starbase.io/workload-issuer-identity/token"
        or "STARBASE_WORKLOAD_OIDC_TOKEN_FILE" in runtime_configuration
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
        or kustomization.get("patches")
        != [
            {"path": "core-preview-patch.yaml"},
            {"path": "runtime-contract-patch.yaml"},
            {
                "target": {
                    "kind": "Secret",
                    "name": "starbase-core-runtime",
                    "namespace": "starbase-system",
                },
                "patch": (
                    "- op: replace\n"
                    "  path: /metadata/annotations/starbase.io~1activation-state\n"
                    "  value: authorized-rc5-synthetic-preview"
                ),
            },
            {
                "target": {
                    "kind": "Secret",
                    "name": "starbase-gateway-runtime",
                    "namespace": "starbase-system",
                },
                "patch": (
                    "- op: replace\n"
                    "  path: /metadata/annotations/starbase.io~1activation-state\n"
                    "  value: authorized-rc5-synthetic-preview"
                ),
            },
        ]
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


def assert_phase5_session_repair_is_bounded(repository: Path) -> None:
    repair = repository / "infrastructure/gitops/apps/starbase-phase5-session-repair"
    kustomization = require_mapping(
        yaml.safe_load((repair / "kustomization.yaml").read_text(encoding="utf-8")),
        "Phase 5 session repair Kustomization",
    )
    if kustomization != PHASE5_SESSION_REPAIR_KUSTOMIZATION:
        raise ValueError("Phase 5 session repair composition differs from policy")
    patch = require_mapping(
        yaml.safe_load((repair / "core-repair-patch.yaml").read_text(encoding="utf-8")),
        "Phase 5 session repair patch",
    )
    if patch != PHASE5_SESSION_REPAIR_PATCH:
        raise ValueError("Phase 5 session repair patch differs from policy")

    rendered = run(["kubectl", "kustomize", str(repair)])
    documents = [
        require_mapping(document, "Phase 5 session repair document")
        for document in yaml.safe_load_all(rendered)
        if document is not None
    ]
    promotion_lock = load_json(
        repository / "infrastructure/gitops/apps/starbase/promotion-lock.json"
    )
    release = require_mapping(promotion_lock.get("release", {}), "promotion release")
    images = require_mapping(release.get("images", {}), "promotion images")
    active_images = copy.deepcopy(images)
    active_images["core"] = PHASE5_SESSION_REPAIR_CORE_IMAGE
    foundation_rendered = run(
        [
            "kubectl",
            "kustomize",
            str(repository / "infrastructure/gitops/apps/starbase-phase4a-foundation"),
        ]
    )
    foundation_documents = [
        require_mapping(document, "Phase 5 retained Job baseline")
        for document in yaml.safe_load_all(foundation_rendered)
        if document is not None and document.get("kind") == "Job"
    ]
    assert_phase5_preview_deployments(
        documents,
        images,
        foundation_documents,
        active_images=active_images,
    )


def assert_phase6_kubernetes_canary_is_bounded(repository: Path) -> None:
    """Verify the exact, read-only Phase 6 Kubernetes observation delta."""
    assert_phase5_session_repair_is_bounded(repository)
    canary = repository / "infrastructure/gitops/apps/starbase-phase6-kubernetes-canary"
    expected_files = {
        "kustomization.yaml": PHASE6_KUBERNETES_CANARY_KUSTOMIZATION,
        "core-kubernetes-source-patch.yaml": PHASE6_CORE_PATCH,
        "kubernetes-connector-canary-patch.yaml": PHASE6_CONNECTOR_PATCH,
    }
    for name, expected in expected_files.items():
        observed = require_mapping(
            yaml.safe_load((canary / name).read_text(encoding="utf-8")),
            f"Phase 6 Kubernetes canary {name}",
        )
        if observed != expected:
            raise ValueError(f"Phase 6 Kubernetes canary {name} differs from policy")

    rendered = run(["kubectl", "kustomize", str(canary)])
    documents = [
        require_mapping(document, "Phase 6 Kubernetes canary document")
        for document in yaml.safe_load_all(rendered)
        if document is not None
    ]
    promotion_lock = load_json(
        repository / "infrastructure/gitops/apps/starbase/promotion-lock.json"
    )
    release = require_mapping(promotion_lock.get("release", {}), "promotion release")
    images = require_mapping(release.get("images", {}), "promotion images")
    active_images = copy.deepcopy(images)
    active_images["core"] = PHASE6_CORE_IMAGE
    active_images["kubernetes-connector"] = PHASE6_KUBERNETES_CONNECTOR_IMAGE
    foundation_rendered = run(
        [
            "kubectl",
            "kustomize",
            str(repository / "infrastructure/gitops/apps/starbase-phase4a-foundation"),
        ]
    )
    foundation_documents = [
        require_mapping(document, "Phase 6 retained Job baseline")
        for document in yaml.safe_load_all(foundation_rendered)
        if document is not None and document.get("kind") == "Job"
    ]
    assert_phase5_preview_deployments(
        documents,
        images,
        foundation_documents,
        active_images=active_images,
        kubernetes_connector_replicas=1,
    )


def assert_phase7_github_canary_is_bounded(repository: Path) -> None:
    """Verify the encrypted, repository-scoped Phase 7 GitHub canary delta."""
    assert_phase6_kubernetes_canary_is_bounded(repository)
    canary = repository / "infrastructure/gitops/apps/starbase-phase7-github-canary"
    expected_files = {
        "kustomization.yaml": PHASE7_GITHUB_CANARY_KUSTOMIZATION,
        "core-github-source-patch.yaml": PHASE7_CORE_PATCH,
        "github-connector-activation-patch.yaml": PHASE7_GITHUB_CONNECTOR_PATCH,
        "web-ui-acceptance-patch.yaml": PHASE7_WEB_PATCH,
    }
    for name, expected in expected_files.items():
        observed = require_mapping(
            yaml.safe_load((canary / name).read_text(encoding="utf-8")),
            f"Phase 7 GitHub canary {name}",
        )
        if observed != expected:
            raise ValueError(f"Phase 7 GitHub canary {name} differs from policy")

    secret = require_mapping(
        yaml.safe_load(
            (canary / "github-app-secret.enc.yaml").read_text(encoding="utf-8")
        ),
        "Phase 7 encrypted GitHub App Secret",
    )
    metadata = require_mapping(secret.get("metadata", {}), "Phase 7 Secret metadata")
    encrypted_data = require_mapping(secret.get("data", {}), "Phase 7 Secret data")
    sops = require_mapping(secret.get("sops", {}), "Phase 7 Secret SOPS metadata")
    if (
        secret.get("apiVersion") != "v1"
        or secret.get("kind") != "Secret"
        or metadata
        != {"name": "starbase-github-app", "namespace": "starbase-connectors"}
        or set(encrypted_data)
        != {"app-id", "installation-id", "private-key.pem"}
        or any(
            not isinstance(value, str) or not value.startswith("ENC[AES256_GCM,")
            for value in encrypted_data.values()
        )
        or sops.get("encrypted_regex") != "^(data|stringData)$"
    ):
        raise ValueError("Phase 7 GitHub App Secret is not exactly encrypted")

    rendered = run(["kubectl", "kustomize", str(canary)])
    documents = [
        require_mapping(document, "Phase 7 GitHub canary document")
        for document in yaml.safe_load_all(rendered)
        if document is not None
    ]
    promotion_lock = load_json(
        repository / "infrastructure/gitops/apps/starbase/promotion-lock.json"
    )
    release = require_mapping(promotion_lock.get("release", {}), "promotion release")
    images = require_mapping(release.get("images", {}), "promotion images")
    active_images = copy.deepcopy(images)
    active_images["core"] = PHASE6_CORE_IMAGE
    active_images["kubernetes-connector"] = PHASE6_KUBERNETES_CONNECTOR_IMAGE
    active_images["web"] = PHASE7_WEB_IMAGE
    foundation_rendered = run(
        [
            "kubectl",
            "kustomize",
            str(repository / "infrastructure/gitops/apps/starbase-phase4a-foundation"),
        ]
    )
    foundation_documents = [
        require_mapping(document, "Phase 7 retained Job baseline")
        for document in yaml.safe_load_all(foundation_rendered)
        if document is not None and document.get("kind") == "Job"
    ]
    assert_phase5_preview_deployments(
        documents,
        images,
        foundation_documents,
        active_images=active_images,
        github_connector_image=PHASE7_GITHUB_CONNECTOR_IMAGE,
        github_connector_replicas=1,
        kubernetes_connector_replicas=1,
    )


def assert_phase5_runtime_rollback_is_bounded(repository: Path) -> None:
    rollback = (
        repository
        / "infrastructure/gitops/apps/starbase-phase5-rc4-runtime-rollback"
    )
    kustomization = require_mapping(
        yaml.safe_load((rollback / "kustomization.yaml").read_text(encoding="utf-8")),
        "Phase 5 runtime rollback Kustomization",
    )
    if kustomization != PHASE5_RUNTIME_ROLLBACK_KUSTOMIZATION:
        raise ValueError("Phase 5 runtime rollback composition differs from policy")

    rendered = run(["kubectl", "kustomize", str(rollback)])
    documents = [
        require_mapping(document, "Phase 5 runtime rollback document")
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
    foundation_documents = [
        require_mapping(document, "Phase 5 retained Job baseline")
        for document in yaml.safe_load_all(foundation_rendered)
        if document is not None and document.get("kind") == "Job"
    ]
    assert_phase5_preview_deployments(
        documents,
        images,
        foundation_documents,
        active_images=RC4_RUNTIME_ROLLBACK_IMAGES,
    )

    expected_annotations = {
        "starbase.io/activation-state": "authorized-rc4-runtime-rollback",
        "starbase.io/activation-stage": "phase5-rc4-runtime-rollback",
    }
    active_deployments = {
        ("starbase-system", "starbase-core"),
        ("starbase-connectors", "starbase-preview-fixture"),
    }
    observed: set[tuple[str, str]] = set()
    for document in documents:
        if document.get("kind") != "Deployment":
            continue
        metadata = require_mapping(document.get("metadata", {}), "rollback metadata")
        identity = (str(metadata.get("namespace", "")), str(metadata.get("name", "")))
        if identity not in active_deployments:
            continue
        observed.add(identity)
        pod_metadata = require_mapping(
            require_mapping(document.get("spec", {}), "rollback deployment spec")
            .get("template", {})
            .get("metadata", {}),
            "rollback pod metadata",
        )
        for annotations in (
            require_mapping(metadata.get("annotations", {}), "rollback annotations"),
            require_mapping(
                pod_metadata.get("annotations", {}), "rollback pod annotations"
            ),
        ):
            if any(
                annotations.get(key) != value
                for key, value in expected_annotations.items()
            ):
                raise ValueError(
                    "Phase 5 runtime rollback annotations differ from policy"
                )
    if observed != active_deployments:
        raise ValueError(
            "Phase 5 runtime rollback deployment inventory differs from policy"
        )


def assert_phase9_governed_proposal_ui_is_bounded(repository: Path) -> None:
    """Verify the exact signed Phase 9 observer and Dojo successor delta."""
    foundation = repository / "infrastructure/gitops/apps/starbase-phase9-foundation"
    dojo = repository / "infrastructure/gitops/apps/starbase-phase9-dojo"

    for root, expected, description in (
        (foundation, PHASE9_FOUNDATION_KUSTOMIZATION, "foundation"),
        (dojo, PHASE9_DOJO_KUSTOMIZATION, "Dojo"),
    ):
        observed = require_mapping(
            yaml.safe_load((root / "kustomization.yaml").read_text(encoding="utf-8")),
            f"Phase 9 {description} Kustomization",
        )
        if observed != expected:
            raise ValueError(
                f"Phase 9 {description} composition differs from policy"
            )

    documents: list[dict[str, Any]] = []
    for root in (foundation, dojo):
        rendered = run(["kubectl", "kustomize", str(root)])
        documents.extend(
            require_mapping(document, "Phase 9 rendered document")
            for document in yaml.safe_load_all(rendered)
            if document is not None
        )

    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    for document in documents:
        metadata = require_mapping(document.get("metadata", {}), "Phase 9 metadata")
        identity = (
            str(document.get("kind", "")),
            str(metadata.get("namespace", "")),
            str(metadata.get("name", "")),
        )
        if identity in indexed:
            if indexed[identity] != document:
                raise ValueError(
                    f"Phase 9 renders conflicting duplicate object {identity}"
                )
            continue
        indexed[identity] = document

    def one(kind: str, namespace: str, name: str) -> dict[str, Any]:
        identity = (kind, namespace, name)
        if identity not in indexed:
            raise ValueError(f"Phase 9 is missing required object {identity}")
        return indexed[identity]

    expected_workload_images = {
        ("starbase-system", "starbase-core"): {
            "core": PHASE9_IMAGES["core"],
            "web": PHASE9_IMAGES["web"],
        },
        ("starbase-connectors", "starbase-preview-fixture"): {
            "connector": PHASE9_IMAGES["github-connector"]
        },
        ("starbase-connectors", "starbase-github-connector"): {
            "connector": PHASE9_IMAGES["github-connector"]
        },
        ("starbase-connectors", "starbase-kubernetes-connector"): {
            "connector": PHASE9_IMAGES["kubernetes-connector"]
        },
        ("starbase-execution", "starbase-dojo-runtime"): {
            "dojo-server": PHASE9_IMAGES["dojo-runtime"],
            "sandbox-fixture": PHASE9_IMAGES["dojo-runtime"],
            "advisory-fixture": PHASE9_IMAGES["dojo-runtime"],
            "evaluation-activity-worker": PHASE9_IMAGES["dojo-runtime"],
        },
        ("starbase-execution", "starbase-dojo-workflow-worker"): {
            "workflow-worker": PHASE9_IMAGES["dojo-runtime"]
        },
    }
    for (namespace, name), expected_images in expected_workload_images.items():
        deployment = one("Deployment", namespace, name)
        pod_template = require_mapping(
            require_mapping(deployment.get("spec", {}), "Phase 9 Deployment spec").get(
                "template", {}
            ),
            "Phase 9 Pod template",
        )
        annotations = require_mapping(
            require_mapping(pod_template.get("metadata", {}), "Phase 9 Pod metadata").get(
                "annotations", {}
            ),
            "Phase 9 Pod annotations",
        )
        if (
            annotations.get("starbase.io/release") != "0.1.0-rc.10"
            or annotations.get("starbase.io/source-revision")
            != PHASE9_SOURCE_REVISION
        ):
            raise ValueError(f"Phase 9 workload identity differs from policy: {name}")
        pod_spec = require_mapping(pod_template.get("spec", {}), "Phase 9 Pod spec")
        observed_images = {
            str(container.get("name", "")): str(container.get("image", ""))
            for container in pod_spec.get("containers", [])
            if isinstance(container, dict)
            and str(container.get("name", "")) in expected_images
        }
        if observed_images != expected_images:
            raise ValueError(f"Phase 9 images differ from policy: {name}")

    core = one("Deployment", "starbase-system", "starbase-core")
    core_container = next(
        container
        for container in core["spec"]["template"]["spec"]["containers"]
        if container.get("name") == "core"
    )
    core_env = {
        str(item.get("name", "")): item
        for item in core_container.get("env", [])
        if isinstance(item, dict)
    }
    if (
        core_env.get("STARBASE_DOJO_URL", {}).get("value")
        != "https://starbase-dojo.starbase-execution.svc.cluster.local:8443"
        or core_env.get("STARBASE_DOJO_CA_FILE", {}).get("value")
        != "/var/run/secrets/starbase.io/dojo/ca.crt"
        or core_env.get("STARBASE_DOJO_READ_TOKEN", {})
        .get("valueFrom", {})
        .get("secretKeyRef")
        != {"name": "starbase-dojo-reader", "key": "read-token"}
    ):
        raise ValueError("Phase 9 core Dojo reader contract differs from policy")

    service = one("Service", "starbase-execution", "starbase-dojo")
    if service.get("spec") != {
        "type": "ClusterIP",
        "selector": {"app.kubernetes.io/name": "starbase-dojo-runtime"},
        "ports": [
            {
                "name": "https",
                "port": 8443,
                "targetPort": "dojo-tls",
                "protocol": "TCP",
            }
        ],
    }:
        raise ValueError("Phase 9 Dojo Service differs from policy")
    if any(
        document.get("kind") == "Ingress"
        and "starbase-dojo" in str(document)
        for document in documents
    ):
        raise ValueError("Phase 9 Dojo must not be exposed through Ingress")

    certificate = one("Certificate", "starbase-execution", "starbase-dojo-tls")
    certificate_spec = require_mapping(
        certificate.get("spec", {}), "Phase 9 Certificate spec"
    )
    if (
        certificate_spec.get("secretName") != "starbase-dojo-tls"
        or certificate_spec.get("duration") != "2160h"
        or certificate_spec.get("renewBefore") != "360h"
        or certificate_spec.get("dnsNames")
        != ["starbase-dojo.starbase-execution.svc.cluster.local"]
        or certificate_spec.get("issuerRef")
        != {"kind": "Issuer", "name": "starbase-dojo-ca"}
    ):
        raise ValueError("Phase 9 Dojo Certificate differs from policy")

    dojo_runtime = one("Deployment", "starbase-execution", "starbase-dojo-runtime")
    dojo_containers = {
        str(container.get("name", "")): container
        for container in dojo_runtime["spec"]["template"]["spec"]["containers"]
    }
    advisory_env = {
        str(item.get("name", "")): item.get("value")
        for item in dojo_containers["advisory-fixture"].get("env", [])
    }
    if advisory_env != {
        "STARBASE_ADVISORY_FIXTURE_MODEL": "starbase-proposal-fixture-v1",
        "STARBASE_ADVISORY_FIXTURE_OUTCOME": "propose",
        "STARBASE_ADVISORY_FIXTURE_ADDRESS": "0.0.0.0:8084",
    }:
        raise ValueError("Phase 9 advisory fixture differs from policy")

    for path, expected_keys in (
        (foundation / "dojo-reader-secret.enc.yaml", {"read-token"}),
        (dojo / "dojo-ca-secret.enc.yaml", {"tls.crt", "tls.key"}),
    ):
        secret = require_mapping(
            yaml.safe_load(path.read_text(encoding="utf-8")), str(path)
        )
        encrypted = secret.get("data", secret.get("stringData", {}))
        encrypted = require_mapping(encrypted, f"Phase 9 encrypted values in {path}")
        sops = require_mapping(secret.get("sops", {}), f"Phase 9 SOPS metadata in {path}")
        if (
            set(encrypted) != expected_keys
            or any(
                not isinstance(value, str) or not value.startswith("ENC[AES256_GCM,")
                for value in encrypted.values()
            )
            or sops.get("encrypted_regex") != "^(data|stringData)$"
        ):
            raise ValueError(f"Phase 9 Secret is not exactly encrypted: {path}")


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


def assert_phase10_autonomous_reader_is_bounded(repository: Path) -> None:
    """Verify the exact disabled, predecessor-compatible Phase 10 reader."""
    root = repository / "infrastructure/gitops/apps/starbase-phase10-autonomous-reader-prepared"
    observed = require_mapping(
        yaml.safe_load((root / "kustomization.yaml").read_text(encoding="utf-8")),
        "Phase 10 reader Kustomization",
    )
    if observed != PHASE10_READER_KUSTOMIZATION:
        raise ValueError("Phase 10 reader composition differs from policy")
    assert_phase10_reader_preparation_patch_is_bounded(
        (root / "reader-preparation-patch.yaml").read_bytes()
    )

    rendered = run(["kubectl", "kustomize", str(root)]).encode("utf-8")
    assert_phase10_reader_render_is_bounded(rendered)
    documents = [
        require_mapping(document, "Phase 10 reader rendered document")
        for document in yaml.safe_load_all(rendered)
        if document is not None
    ]
    indexed = {
        (
            str(document.get("kind", "")),
            str(document.get("metadata", {}).get("namespace", "")),
            str(document.get("metadata", {}).get("name", "")),
        ): document
        for document in documents
    }

    def deployment(namespace: str, name: str) -> dict[str, Any]:
        identity = ("Deployment", namespace, name)
        if identity not in indexed:
            raise ValueError(f"Phase 10 reader is missing required object {identity}")
        return indexed[identity]

    config = indexed.get(("ConfigMap", "starbase-system", "starbase-runtime"))
    if not isinstance(config, dict):
        raise ValueError("Phase 10 reader is missing the runtime ConfigMap")
    data = require_mapping(config.get("data", {}), "Phase 10 reader configuration")
    if (
        data.get("STARBASE_BOUNTY_AUTOMATION_ENABLED") != "false"
        or data.get("STARBASE_BOUNTY_AUTOMATION_DISPATCH_ENABLED") != "false"
        or "STARBASE_TEMPORAL_MODE" in data
        or "STARBASE_BOUNTY_MODEL_ENDPOINT" in data
    ):
        raise ValueError("Phase 10 reader automation is not exactly disabled")

    expected_workload_images = {
        ("starbase-system", "starbase-core"): {
            "core": PHASE10_READER_IMAGES["core"],
            "web": PHASE10_READER_IMAGES["web"],
        },
        ("starbase-connectors", "starbase-preview-fixture"): {
            "connector": PHASE10_READER_IMAGES["github-connector"]
        },
        ("starbase-connectors", "starbase-github-connector"): {
            "connector": PHASE10_READER_IMAGES["github-connector"]
        },
        ("starbase-connectors", "starbase-kubernetes-connector"): {
            "connector": PHASE10_READER_IMAGES["kubernetes-connector"]
        },
    }
    for (namespace, name), expected_images in expected_workload_images.items():
        workload = deployment(namespace, name)
        if workload.get("spec", {}).get("replicas") != 1:
            raise ValueError(f"Phase 10 reader replica count differs from policy: {name}")
        template = require_mapping(
            require_mapping(workload.get("spec", {}), "Phase 10 reader Deployment spec").get(
                "template", {}
            ),
            "Phase 10 reader Pod template",
        )
        annotations = require_mapping(
            require_mapping(template.get("metadata", {}), "Phase 10 reader Pod metadata").get(
                "annotations", {}
            ),
            "Phase 10 reader Pod annotations",
        )
        if (
            annotations.get("starbase.io/release") != "0.1.0-rc.11"
            or annotations.get("starbase.io/source-revision")
            != PHASE10_READER_SOURCE_REVISION
        ):
            raise ValueError(f"Phase 10 reader workload identity differs from policy: {name}")
        pod_spec = require_mapping(template.get("spec", {}), "Phase 10 reader Pod spec")
        assert_phase10_reader_workload_containers_are_bounded(
            pod_spec, expected_images, name
        )

    core = deployment("starbase-system", "starbase-core")
    if core.get("spec", {}).get("strategy") != {"type": "Recreate"}:
        raise ValueError("Phase 10 reader core strategy differs from policy")
    core_containers = require_mapping(
        core["spec"]["template"].get("spec", {}), "Phase 10 reader core Pod spec"
    ).get("containers", [])
    assert_phase10_reader_core_environment_is_bounded(core_containers)
    core_metadata = require_mapping(
        core["spec"]["template"].get("metadata", {}), "Phase 10 reader core metadata"
    )
    annotations = require_mapping(
        core_metadata.get("annotations", {}), "Phase 10 reader core annotations"
    )
    labels = require_mapping(core_metadata.get("labels", {}), "Phase 10 reader core labels")
    if (
        annotations.get("starbase.io/release-manifest-digest")
        != PHASE10_READER_RELEASE_MANIFEST_DIGEST
        or labels.get("starbase.io/temporal-client") != "false"
        or labels.get("starbase.io/external-authority") != "false"
    ):
        raise ValueError("Phase 10 reader core safety metadata differs from policy")


def assert_phase10_reader_preparation_patch_is_bounded(content: bytes) -> None:
    if sha256_bytes(content) != PHASE10_READER_PREPARATION_PATCH_DIGEST:
        raise ValueError("Phase 10 reader preparation patch differs from policy")


def assert_phase10_reader_render_is_bounded(content: bytes) -> None:
    documents = [
        document
        for document in yaml.safe_load_all(content)
        if document is not None
    ]
    canonical_documents = sorted(
        json.dumps(document, sort_keys=True, separators=(",", ":"))
        for document in documents
    )
    canonical_inventory = (
        "[" + ",".join(canonical_documents) + "]"
    ).encode("utf-8")
    if sha256_bytes(canonical_inventory) != PHASE10_READER_RENDERED_INVENTORY_DIGEST:
        raise ValueError("Phase 10 reader complete rendered inventory differs from policy")


def assert_phase10_reader_workload_containers_are_bounded(
    pod_spec: dict[str, Any], expected_images: dict[str, str], name: str
) -> None:
    containers = pod_spec.get("containers", [])
    if not isinstance(containers, list) or any(
        not isinstance(container, dict) for container in containers
    ):
        raise ValueError(f"Phase 10 reader container inventory differs from policy: {name}")
    images = {
        str(container.get("name", "")): str(container.get("image", ""))
        for container in containers
    }
    if len(containers) != len(expected_images) or images != expected_images:
        raise ValueError(f"Phase 10 reader container inventory differs from policy: {name}")
    if pod_spec.get("initContainers", []) not in (None, []):
        raise ValueError(f"Phase 10 reader init container inventory differs from policy: {name}")


def assert_phase10_reader_foundation_flux_bytes_are_bounded(content: bytes) -> None:
    if sha256_bytes(content) != PHASE10_READER_FOUNDATION_FLUX_DIGEST:
        raise ValueError("Phase 10 reader foundation Flux activation differs from policy")


def assert_phase10_reader_foundation_flux_is_bounded(
    repository: Path, aggregate_config: dict[str, Any]
) -> None:
    foundation_resource = "starbase-foundation-kustomization.yaml"
    resources = aggregate_config.get("resources", []) or []
    if foundation_resource not in resources:
        raise ValueError("Phase 10 reader foundation Flux Kustomization is not aggregated")
    flux_root = repository / "infrastructure/gitops/flux-system"
    foundation_path = flux_root / foundation_resource
    foundation_content = foundation_path.read_bytes()
    assert_phase10_reader_foundation_flux_bytes_are_bounded(foundation_content)
    expected_foundation = require_mapping(
        yaml.safe_load(foundation_content), "Phase 10 reader foundation Flux Kustomization"
    )
    rendered_documents = [
        require_mapping(document, "rendered Flux aggregate document")
        for document in yaml.safe_load_all(run(["kubectl", "kustomize", str(flux_root)]))
        if document is not None
    ]
    assert_phase10_reader_rendered_flux_documents_are_bounded(
        repository, rendered_documents, expected_foundation
    )


def assert_phase10_reader_rendered_flux_documents_are_bounded(
    repository: Path,
    documents: list[dict[str, Any]],
    expected_foundation: dict[str, Any],
) -> None:
    def selected(name: str) -> list[dict[str, Any]]:
        return [
            document
            for document in documents
            if document.get("kind") == "Kustomization"
            and str(document.get("apiVersion", "")).startswith(
                "kustomize.toolkit.fluxcd.io/"
            )
            and document.get("metadata", {}).get("namespace") == "flux-system"
            and document.get("metadata", {}).get("name") == name
        ]

    foundations = selected("starbase-foundation")
    if len(foundations) != 1 or foundations[0] != expected_foundation:
        raise ValueError("Phase 10 reader rendered foundation Flux activation differs from policy")
    dojos = selected("starbase-dojo")
    if len(dojos) != 1:
        raise ValueError("Phase 10 reader rendered Dojo Flux activation differs from policy")
    assert_phase9_dojo_flux_document_is_bounded(dojos[0])

    starbase_root = (
        repository / "infrastructure/gitops/apps/starbase"
    ).resolve()
    references: list[tuple[str, str]] = []
    for document in documents:
        if document.get("kind") != "Kustomization" or not str(
            document.get("apiVersion", "")
        ).startswith("kustomize.toolkit.fluxcd.io/"):
            continue
        spec = require_mapping(document.get("spec", {}), "rendered Flux Kustomization spec")
        managed_path = spec.get("path")
        if not isinstance(managed_path, str) or not managed_path.startswith("./"):
            continue
        resolved = (repository / managed_path.removeprefix("./")).resolve()
        if kustomization_references_target(resolved, starbase_root):
            metadata = require_mapping(document.get("metadata", {}), "rendered Flux metadata")
            references.append((str(metadata.get("name", "")), managed_path))
    expected_references = [
        (
            "starbase-foundation",
            "./infrastructure/gitops/apps/starbase-phase10-autonomous-reader-prepared",
        )
    ]
    if references != expected_references:
        raise ValueError(
            "Phase 10 reader rendered Starbase Flux references differ from policy: "
            f"expected {expected_references}, observed {references}"
        )


def assert_phase10_reader_core_environment_is_bounded(
    containers: Any,
) -> None:
    if not isinstance(containers, list):
        raise ValueError("Phase 10 reader core environment differs from policy")
    core_containers = [
        container
        for container in containers
        if isinstance(container, dict) and container.get("name") == "core"
    ]
    if len(core_containers) != 1:
        raise ValueError("Phase 10 reader core environment differs from policy")
    core = core_containers[0]
    if core.get("envFrom") != [{"configMapRef": {"name": "starbase-runtime"}}]:
        raise ValueError("Phase 10 reader core environment differs from policy")
    protected_names = {
        "STARBASE_BOUNTY_AUTOMATION_ENABLED",
        "STARBASE_BOUNTY_AUTOMATION_DISPATCH_ENABLED",
        "STARBASE_TEMPORAL_MODE",
        "STARBASE_BOUNTY_MODEL_ENDPOINT",
    }
    environment = core.get("env", []) or []
    if not isinstance(environment, list) or any(
        isinstance(entry, dict) and entry.get("name") in protected_names
        for entry in environment
    ):
        raise ValueError("Phase 10 reader core environment differs from policy")


def assert_phase9_dojo_flux_is_bounded(
    repository: Path, aggregate_config: dict[str, Any]
) -> None:
    dojo_resource = "starbase-dojo-kustomization.yaml"
    resources = aggregate_config.get("resources", []) or []
    if dojo_resource not in resources:
        raise ValueError("Phase 9 Dojo Flux Kustomization is not aggregated")

    dojo_flux_path = (
        repository / "infrastructure/gitops/flux-system" / dojo_resource
    )
    dojo_flux = require_mapping(
        yaml.safe_load(dojo_flux_path.read_text(encoding="utf-8")),
        "Phase 9 Dojo Flux Kustomization",
    )
    assert_phase9_dojo_flux_document_is_bounded(dojo_flux)


def assert_phase9_dojo_flux_document_is_bounded(dojo_flux: dict[str, Any]) -> None:
    expected = {
        "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
        "kind": "Kustomization",
        "metadata": {
            "name": "starbase-dojo",
            "namespace": "flux-system",
            "labels": {"starbase.io/activation-wave": "phase9-governed-proposal-ui"},
        },
        "spec": {
            "interval": "10m0s",
            "timeout": "10m0s",
            "path": "./infrastructure/gitops/apps/starbase-phase9-dojo",
            "prune": True,
            "sourceRef": {"kind": "GitRepository", "name": "flux-system"},
            "decryption": {
                "provider": "sops",
                "secretRef": {"name": "sops-age"},
            },
            "dependsOn": [{"name": "databases"}],
            "healthChecks": [
                {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "name": "starbase-dojo-database-bootstrap-v1-66e26e025d98",
                    "namespace": "database",
                },
                {
                    "apiVersion": "batch/v1",
                    "kind": "Job",
                    "name": "starbase-dojo-migrate-rc6-5d13884264d9",
                    "namespace": "starbase-execution",
                },
                {
                    "apiVersion": "cert-manager.io/v1",
                    "kind": "Certificate",
                    "name": "starbase-dojo-tls",
                    "namespace": "starbase-execution",
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": "starbase-dojo-runtime",
                    "namespace": "starbase-execution",
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": "starbase-dojo-workflow-worker",
                    "namespace": "starbase-execution",
                },
            ],
        },
    }
    if dojo_flux != expected:
        raise ValueError("Phase 9 Dojo Flux activation differs from policy")


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
        rollback = [
            (
                "starbase-foundation",
                "./infrastructure/gitops/apps/starbase-phase5-rc4-runtime-rollback",
            )
        ]
        repair = [
            (
                "starbase-foundation",
                "./infrastructure/gitops/apps/starbase-phase5-session-repair",
            )
        ]
        kubernetes_canary = [
            (
                "starbase-foundation",
                "./infrastructure/gitops/apps/starbase-phase6-kubernetes-canary",
            )
        ]
        github_canary = [
            (
                "starbase-foundation",
                "./infrastructure/gitops/apps/starbase-phase7-github-canary",
            )
        ]
        phase9 = [
            (
                "starbase-foundation",
                "./infrastructure/gitops/apps/starbase-phase9-foundation",
            ),
        ]
        phase10_reader = [
            (
                "starbase-foundation",
                "./infrastructure/gitops/apps/starbase-phase10-autonomous-reader-prepared",
            ),
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
        if references == rollback:
            assert_phase5_flux_kustomization_is_bounded(reference_specs[rollback[0]])
            assert_phase5_runtime_rollback_is_bounded(repository)
            return
        if references == repair:
            assert_phase5_flux_kustomization_is_bounded(reference_specs[repair[0]])
            assert_phase5_session_repair_is_bounded(repository)
            return
        if references == kubernetes_canary:
            assert_phase5_flux_kustomization_is_bounded(
                reference_specs[kubernetes_canary[0]]
            )
            assert_phase6_kubernetes_canary_is_bounded(repository)
            return
        if references == github_canary:
            assert_phase5_flux_kustomization_is_bounded(
                reference_specs[github_canary[0]]
            )
            assert_phase7_github_canary_is_bounded(repository)
            return
        if references == phase9:
            assert_phase5_flux_kustomization_is_bounded(
                reference_specs[phase9[0]]
            )
            assert_phase9_dojo_flux_is_bounded(repository, aggregate_config)
            assert_phase9_governed_proposal_ui_is_bounded(repository)
            return
        if references == phase10_reader:
            assert_phase10_reader_foundation_flux_is_bounded(
                repository, aggregate_config
            )
            assert_phase5_flux_kustomization_is_bounded(
                reference_specs[phase10_reader[0]]
            )
            assert_phase9_dojo_flux_is_bounded(repository, aggregate_config)
            assert_phase9_governed_proposal_ui_is_bounded(repository)
            assert_phase10_autonomous_reader_is_bounded(repository)
            return
        raise ValueError(
            "inert bundle has an unsupported Flux activation overlay: "
            f"expected {foundation}, {preview}, {repair}, "
            f"{kubernetes_canary}, {github_canary}, {phase9}, "
            f"{phase10_reader}, or {rollback}, "
            f"observed {references}"
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
        if document.get("kind")
        in {"ClusterRole", "ClusterRoleBinding", "Ingress", "Secret"}
    ]
    if forbidden:
        raise ValueError(
            "committed bundle contains a forbidden Secret, Ingress, or cluster-scoped RBAC object"
        )

    rbac_counts = observer_rbac_counts()
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
        observer_identity = validate_observer_rbac(document)
        if observer_identity is not None:
            observer_kind, observer_namespace = observer_identity
            rbac_counts[observer_namespace][observer_kind] += 1
    require_exact_observer_rbac(rbac_counts, "committed bundle")

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
