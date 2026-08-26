from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from infrastructure.scripts import starbase_promotion

ZERO_DIGEST = "sha256:" + ("0" * 64)


def restricted_container(name: str, image: str) -> dict:
    return {
        "name": name,
        "image": image,
        "resources": {
            "requests": {"cpu": "10m", "memory": "16Mi"},
            "limits": {"cpu": "100m", "memory": "64Mi"},
        },
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "readOnlyRootFilesystem": True,
        },
    }


def restricted_pod(service_account: str, containers: list[dict]) -> dict:
    return {
        "serviceAccountName": service_account,
        "automountServiceAccountToken": False,
        "securityContext": {
            "runAsNonRoot": True,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": containers,
    }


def observer_rbac_documents() -> list[dict]:
    documents = []
    rules = [
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["list"]},
        {
            "apiGroups": ["apps"],
            "resources": ["daemonsets", "deployments", "statefulsets"],
            "verbs": ["list"],
        },
    ]
    for namespace in (
        "starbase-system",
        "starbase-connectors",
        "starbase-execution",
    ):
        documents.extend(
            [
                {
                    "apiVersion": "rbac.authorization.k8s.io/v1",
                    "kind": "Role",
                    "metadata": {
                        "name": "starbase-kubernetes-observer",
                        "namespace": namespace,
                    },
                    "rules": copy.deepcopy(rules),
                },
                {
                    "apiVersion": "rbac.authorization.k8s.io/v1",
                    "kind": "RoleBinding",
                    "metadata": {
                        "name": "starbase-kubernetes-observer",
                        "namespace": namespace,
                    },
                    "roleRef": {
                        "apiGroup": "rbac.authorization.k8s.io",
                        "kind": "Role",
                        "name": "starbase-kubernetes-observer",
                    },
                    "subjects": [
                        {
                            "kind": "ServiceAccount",
                            "name": "starbase-kubernetes-connector",
                            "namespace": "starbase-connectors",
                        }
                    ],
                },
            ]
        )
    return documents


def release_manifest() -> dict:
    return {
        "schema_version": 1,
        "repository": "https://github.com/X-McKay/Starbase",
        "revision": "a" * 40,
        "version": "0.1.0-rc.2",
        "images": [
            {
                "name": "core",
                "image": "ghcr.io/x-mckay/starbase/core",
                "digest": "sha256:" + ("1" * 64),
                "platform": "linux/amd64",
                "signature_verified": True,
            },
            {
                "name": "github-connector",
                "image": "ghcr.io/x-mckay/starbase/github-connector",
                "digest": "sha256:" + ("2" * 64),
                "platform": "linux/amd64",
                "signature_verified": True,
            },
            {
                "name": "kubernetes-connector",
                "image": "ghcr.io/x-mckay/starbase/kubernetes-connector",
                "digest": "sha256:" + ("3" * 64),
                "platform": "linux/amd64",
                "signature_verified": True,
            },
            {
                "name": "web",
                "image": "ghcr.io/x-mckay/starbase/web",
                "digest": "sha256:" + ("4" * 64),
                "platform": "linux/amd64",
                "signature_verified": True,
            },
            {
                "name": "core-migrator",
                "image": "ghcr.io/x-mckay/starbase/core-migrator",
                "digest": "sha256:" + ("5" * 64),
                "platform": "linux/amd64",
                "signature_verified": True,
            },
            {
                "name": "gateway-migrator",
                "image": "ghcr.io/x-mckay/starbase/gateway-migrator",
                "digest": "sha256:" + ("6" * 64),
                "platform": "linux/amd64",
                "signature_verified": True,
            },
        ],
        "database_migrations": [
            {
                "path": "services/corestate/migrations/0001_initial.sql",
                "digest": "sha256:" + ("7" * 64),
            },
            {
                "path": "services/experiencegateway/migrations/0001_operator_sessions.sql",
                "digest": "sha256:" + ("8" * 64),
            },
        ],
    }


def promotion_input(max_objects: int = 32) -> dict:
    return {
        "schema_version": 1,
        "repository": "https://github.com/X-McKay/Starbase",
        "expected_release_version": "0.1.0-rc.2",
        "target_platform": "linux/amd64",
        "max_objects": max_objects,
        "allowed_namespaces": [
            "starbase-connectors",
            "starbase-execution",
            "starbase-system",
        ],
        "expected_activation": {
            "bundle": "inactive-not-flux-referenced",
            "core": "blocked-pending-runtime-gates",
            "github_connector": "intentionally-disabled-zero-replicas",
            "kubernetes_connector": "blocked-pending-runtime-gates",
            "migrations": "rendered-not-authorized",
        },
    }


def documents() -> list[dict]:
    return [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "starbase-system"},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "starbase-core",
                "namespace": "starbase-system",
            },
            "spec": {
                "replicas": 1,
                "template": {
                    "spec": restricted_pod(
                        "starbase-core",
                        [
                            restricted_container(
                                "core", f"ghcr.io/x-mckay/starbase/core@{ZERO_DIGEST}"
                            ),
                            restricted_container(
                                "web", f"ghcr.io/x-mckay/starbase/web@{ZERO_DIGEST}"
                            ),
                        ],
                    )
                },
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "starbase-github-connector",
                "namespace": "starbase-connectors",
            },
            "spec": {
                "replicas": 1,
                "template": {
                    "metadata": {"labels": {"starbase.io/access-core": "true"}},
                    "spec": restricted_pod(
                        "starbase-github-connector",
                        [
                            restricted_container(
                                "connector",
                                (
                                    "ghcr.io/x-mckay/starbase/github-connector@"
                                    f"{ZERO_DIGEST}"
                                ),
                            )
                        ],
                    ),
                },
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "starbase-kubernetes-connector",
                "namespace": "starbase-connectors",
            },
            "spec": {
                "replicas": 1,
                "template": {
                    "spec": restricted_pod(
                        "starbase-kubernetes-connector",
                        [
                            restricted_container(
                                "connector",
                                (
                                    "ghcr.io/x-mckay/starbase/kubernetes-connector@"
                                    f"{ZERO_DIGEST}"
                                ),
                            )
                            | {
                                "env": [
                                    {
                                        "name": "STARBASE_KUBERNETES_SCOPE",
                                        "value": json.dumps(
                                            {
                                                "id": "starbase-namespaces-v1",
                                                "namespaces": [
                                                    "starbase-connectors",
                                                    "starbase-execution",
                                                    "starbase-system",
                                                ],
                                                "include_nodes": False,
                                                "flux_namespaces": [],
                                            },
                                            separators=(",", ":"),
                                        ),
                                    }
                                ]
                            }
                        ],
                    )
                },
            },
        },
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "starbase-core-migrate",
                "namespace": "starbase-system",
            },
            "spec": {
                "activeDeadlineSeconds": 300,
                "ttlSecondsAfterFinished": 86400,
                "template": {
                    "spec": restricted_pod(
                        "starbase-core",
                        [
                            restricted_container(
                                "migrate",
                                (
                                    "ghcr.io/x-mckay/starbase/core-migrator@"
                                    f"{ZERO_DIGEST}"
                                ),
                            )
                        ],
                    )
                },
            },
        },
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": "starbase-gateway-migrate",
                "namespace": "starbase-system",
            },
            "spec": {
                "activeDeadlineSeconds": 300,
                "ttlSecondsAfterFinished": 86400,
                "template": {
                    "spec": restricted_pod(
                        "starbase-core",
                        [
                            restricted_container(
                                "migrate",
                                (
                                    "ghcr.io/x-mckay/starbase/gateway-migrator@"
                                    f"{ZERO_DIGEST}"
                                ),
                            )
                        ],
                    )
                },
            },
        },
    ] + observer_rbac_documents()


class PromotionPolicyTests(unittest.TestCase):
    def test_rejects_unknown_promotion_input(self) -> None:
        config = promotion_input()
        config["source_revision"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "unknown promotion input"):
            starbase_promotion.transform_and_validate(
                documents(), release_manifest(), config
            )

    def test_transform_is_deterministic_and_records_intent(self) -> None:
        manifest = release_manifest()
        config = promotion_input()

        first = starbase_promotion.transform_and_validate(
            copy.deepcopy(documents()), manifest, config
        )
        second = starbase_promotion.transform_and_validate(
            copy.deepcopy(documents()), manifest, config
        )

        self.assertEqual(first, second)
        github = next(
            doc
            for doc in first
            if doc.get("kind") == "Deployment"
            and doc["metadata"]["name"] == "starbase-github-connector"
        )
        self.assertEqual(github["spec"]["replicas"], 0)
        images = json.dumps(first, sort_keys=True)
        self.assertNotIn(ZERO_DIGEST, images)
        self.assertIn("@sha256:" + ("1" * 64), images)
        core_job = next(
            doc
            for doc in first
            if doc.get("kind") == "Job"
            and doc["metadata"]["name"].startswith("starbase-core-migrate-")
        )
        self.assertEqual(
            core_job["metadata"]["annotations"]["starbase.io/migration-set-digest"],
            starbase_promotion.migration_set_digests(manifest)["starbase-core-migrate"],
        )

    def test_rejects_unexpected_image(self) -> None:
        docs = documents()
        docs[1]["spec"]["template"]["spec"]["containers"].append(
            restricted_container("sidecar", "docker.io/library/busybox:latest")
        )

        with self.assertRaisesRegex(ValueError, "unexpected image"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_object_growth_beyond_bound(self) -> None:
        with self.assertRaisesRegex(ValueError, "object count"):
            starbase_promotion.transform_and_validate(
                documents(), release_manifest(), promotion_input(max_objects=5)
            )

    def test_rejects_secret_object(self) -> None:
        docs = documents()
        docs.append(
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "forbidden", "namespace": "starbase-system"},
                "stringData": {"fixture": "not-sensitive"},
            }
        )

        with self.assertRaisesRegex(ValueError, "Secret"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_migration_name_changes_with_content_digest(self) -> None:
        original = starbase_promotion.transform_and_validate(
            documents(), release_manifest(), promotion_input()
        )
        changed_manifest = release_manifest()
        changed_manifest["database_migrations"][0]["digest"] = "sha256:" + ("9" * 64)
        changed = starbase_promotion.transform_and_validate(
            documents(), changed_manifest, promotion_input()
        )
        original_name = next(
            doc["metadata"]["name"]
            for doc in original
            if doc.get("kind") == "Job"
            and doc["metadata"]["name"].startswith("starbase-core-migrate-")
        )
        changed_name = next(
            doc["metadata"]["name"]
            for doc in changed
            if doc.get("kind") == "Job"
            and doc["metadata"]["name"].startswith("starbase-core-migrate-")
        )
        self.assertNotEqual(original_name, changed_name)

    def test_migration_name_changes_when_migration_is_added(self) -> None:
        original = starbase_promotion.transform_and_validate(
            documents(), release_manifest(), promotion_input()
        )
        changed_manifest = release_manifest()
        changed_manifest["database_migrations"].append(
            {
                "path": "services/corestate/migrations/0002_add_index.sql",
                "digest": "sha256:" + ("9" * 64),
            }
        )
        changed = starbase_promotion.transform_and_validate(
            documents(), changed_manifest, promotion_input()
        )
        original_name = next(
            doc["metadata"]["name"]
            for doc in original
            if doc.get("kind") == "Job"
            and doc["metadata"]["name"].startswith("starbase-core-migrate-")
        )
        changed_name = next(
            doc["metadata"]["name"]
            for doc in changed
            if doc.get("kind") == "Job"
            and doc["metadata"]["name"].startswith("starbase-core-migrate-")
        )
        self.assertNotEqual(original_name, changed_name)

    def test_rejects_unbounded_job_retention(self) -> None:
        docs = documents()
        core_job = next(doc for doc in docs if doc.get("kind") == "Job")
        core_job["spec"]["ttlSecondsAfterFinished"] = 172800
        with self.assertRaisesRegex(ValueError, "bounded retention"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_automatic_service_account_token(self) -> None:
        docs = documents()
        docs[1]["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
        with self.assertRaisesRegex(ValueError, "disable automatic token"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_github_https_egress(self) -> None:
        docs = documents()
        docs.append(
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": "forbidden-github-egress",
                    "namespace": "starbase-connectors",
                },
                "spec": {
                    "podSelector": {
                        "matchLabels": {
                            "app.kubernetes.io/name": "starbase-github-connector"
                        }
                    },
                    "policyTypes": ["Egress"],
                    "egress": [
                        {
                            "to": [
                                {
                                    "namespaceSelector": {
                                        "matchLabels": {
                                            "kubernetes.io/metadata.name": "external"
                                        }
                                    }
                                }
                            ],
                            "ports": [{"protocol": "TCP", "port": 443}],
                        }
                    ],
                },
            }
        )
        with self.assertRaisesRegex(ValueError, "unexpected egress port"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_broad_dns_selector(self) -> None:
        docs = documents()
        docs.append(
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": "forbidden-broad-dns",
                    "namespace": "starbase-connectors",
                },
                "spec": {
                    "podSelector": {},
                    "policyTypes": ["Egress"],
                    "egress": [
                        {
                            "to": [{"namespaceSelector": {}, "podSelector": {}}],
                            "ports": [{"protocol": "UDP", "port": 53}],
                        }
                    ],
                },
            }
        )
        with self.assertRaisesRegex(ValueError, "namespace selector"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_privilege_escalation(self) -> None:
        docs = documents()
        core = docs[1]["spec"]["template"]["spec"]["containers"][0]
        core["securityContext"]["allowPrivilegeEscalation"] = True
        with self.assertRaisesRegex(ValueError, "privilege escalation"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_privileged_init_container(self) -> None:
        docs = documents()
        pod = docs[1]["spec"]["template"]["spec"]
        web = pod["containers"].pop()
        web["securityContext"]["allowPrivilegeEscalation"] = True
        pod["initContainers"] = [web]
        with self.assertRaisesRegex(ValueError, "privilege escalation"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_expanded_namespace_observer_role(self) -> None:
        docs = documents()
        role = next(doc for doc in docs if doc.get("kind") == "Role")
        role["rules"][0]["verbs"] = ["*"]
        with self.assertRaisesRegex(ValueError, "observer Role rules"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_substituted_namespace_observer_role_binding(self) -> None:
        for field, value in (
            (
                "roleRef",
                {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "Role",
                    "name": "cluster-admin",
                },
            ),
            (
                "subjects",
                [
                    {
                        "kind": "ServiceAccount",
                        "name": "default",
                        "namespace": "default",
                    }
                ],
            ),
        ):
            with self.subTest(field=field):
                docs = documents()
                binding = next(
                    doc for doc in docs if doc.get("kind") == "RoleBinding"
                )
                binding[field] = value
                with self.assertRaisesRegex(ValueError, f"observer RoleBinding {field}"):
                    starbase_promotion.transform_and_validate(
                        docs, release_manifest(), promotion_input()
                    )

    def test_rejects_cluster_scoped_observer_authority(self) -> None:
        docs = documents()
        docs.append(
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {"name": "starbase-kubani-observer"},
                "rules": [{"apiGroups": ["*"], "resources": ["*"], "verbs": ["*"]}],
            }
        )
        with self.assertRaisesRegex(ValueError, "unexpected cluster-scoped object"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_missing_namespace_observer_binding(self) -> None:
        docs = documents()
        docs = [
            document
            for document in docs
            if not (
                document.get("kind") == "RoleBinding"
                and document.get("metadata", {}).get("namespace")
                == "starbase-execution"
            )
        ]
        with self.assertRaisesRegex(ValueError, "exact namespace observer roles"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )

    def test_rejects_expanded_kubernetes_connector_scope(self) -> None:
        docs = documents()
        connector = next(
            document
            for document in docs
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name")
            == "starbase-kubernetes-connector"
        )
        scope = connector["spec"]["template"]["spec"]["containers"][0]["env"][0]
        scope["value"] = json.dumps(
            {
                "id": "starbase-namespaces-v1",
                "namespaces": ["kube-system", "starbase-system"],
                "include_nodes": True,
                "flux_namespaces": ["flux-system"],
            }
        )
        with self.assertRaisesRegex(ValueError, "scope differs from namespace policy"):
            starbase_promotion.transform_and_validate(
                docs, release_manifest(), promotion_input()
            )


class PromotionEvidenceTests(unittest.TestCase):
    def make_checkout(self, root: Path) -> str:
        subprocess.run(["git", "init", "-q", root], check=True)
        subprocess.run(
            ["git", "-C", root, "config", "user.email", "fixture@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", root, "config", "user.name", "Fixture"], check=True
        )
        subprocess.run(
            [
                "git",
                "-C",
                root,
                "remote",
                "add",
                "origin",
                "https://github.com/X-McKay/Starbase.git",
            ],
            check=True,
        )
        (root / "source.txt").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", root, "add", "source.txt"], check=True)
        subprocess.run(["git", "-C", root, "commit", "-qm", "fixture"], check=True)
        return subprocess.check_output(
            ["git", "-C", root, "rev-parse", "HEAD"], text=True
        ).strip()

    def test_checkout_rejects_revision_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp)
            self.make_checkout(checkout)
            with self.assertRaisesRegex(ValueError, "revision mismatch"):
                starbase_promotion.verify_checkout(
                    checkout,
                    "f" * 40,
                    "https://github.com/X-McKay/Starbase",
                    "fixture",
                )

    def test_checkout_rejects_dirty_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            checkout = Path(temp)
            revision = self.make_checkout(checkout)
            (checkout / "source.txt").write_text("substituted\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checkout is dirty"):
                starbase_promotion.verify_checkout(
                    checkout,
                    revision,
                    "https://github.com/X-McKay/Starbase",
                    "fixture",
                )

    def test_manifest_digest_must_match_promotion_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest_path = Path(temp) / "release-manifest.json"
            manifest_path.write_text(
                json.dumps(release_manifest(), sort_keys=True), encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "manifest digest"):
                starbase_promotion.load_verified_manifest(
                    manifest_path, "sha256:" + ("f" * 64)
                )

    def test_exact_generated_files_detect_hand_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "rendered.yaml"
            lock = root / "promotion-lock.json"
            output.write_text("expected\n", encoding="utf-8")
            lock.write_text('{"schema_version":1}\n', encoding="utf-8")

            starbase_promotion.verify_exact_files(
                output,
                lock,
                b"expected\n",
                b'{"schema_version":1}\n',
            )
            output.write_text("hand edited\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "rendered manifest"):
                starbase_promotion.verify_exact_files(
                    output,
                    lock,
                    b"expected\n",
                    b'{"schema_version":1}\n',
                )


class RepositoryBundleTests(unittest.TestCase):
    def test_committed_bundle_is_self_consistent_and_matches_activation(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        bundle = repository / "infrastructure/gitops/apps/starbase"
        starbase_promotion.verify_repository_bundle(
            bundle / "promotion-input.json",
            bundle / "rendered.yaml",
            bundle / "promotion-lock.json",
        )

    def test_inactive_intent_rejects_flux_referenced_foundation(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        bundle = repository / "infrastructure/gitops/apps/starbase"
        inactive = {
            "bundle": "inactive-not-flux-referenced",
            "core": "blocked-pending-runtime-gates",
            "github_connector": "intentionally-disabled-zero-replicas",
            "kubernetes_connector": "blocked-pending-runtime-gates",
            "migrations": "rendered-not-authorized",
        }
        with tempfile.TemporaryDirectory(dir=repository) as temp:
            input_path = Path(temp) / "promotion-input.json"
            lock_path = Path(temp) / "promotion-lock.json"
            promotion = json.loads((bundle / "promotion-input.json").read_text())
            lock = json.loads((bundle / "promotion-lock.json").read_text())
            promotion["expected_activation"] = inactive
            lock["activation"] = inactive
            input_path.write_text(json.dumps(promotion), encoding="utf-8")
            lock_path.write_text(json.dumps(lock), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "inactive.*Flux"):
                starbase_promotion.verify_repository_bundle(
                    input_path,
                    bundle / "rendered.yaml",
                    lock_path,
                )

    def test_preview_activation_rejects_flux_transform_overrides(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        flux = yaml.safe_load(
            (
                repository
                / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
            ).read_text()
        )
        spec = flux["spec"]
        starbase_promotion.assert_phase5_flux_kustomization_is_bounded(spec)

        mutations = {
            "patches": [{"patch": "- op: replace\n  path: /spec/replicas\n  value: 2"}],
            "images": [{"name": "starbase-core", "newTag": "latest"}],
            "components": ["../unreviewed-component"],
            "postBuild": {"substitute": {"STARBASE_MODE": "live"}},
            "commonMetadata": {"annotations": {"example.com/force": "true"}},
            "namePrefix": "unreviewed-",
            "nameSuffix": "-unreviewed",
            "targetNamespace": "default",
            "force": True,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(spec)
                changed[field] = value
                with self.assertRaisesRegex(ValueError, "Flux.*transformation"):
                    starbase_promotion.assert_phase5_flux_kustomization_is_bounded(
                        changed
                    )

    def test_preview_activation_rejects_unexpected_nonzero_deployment(self) -> None:
        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        live_github = next(
            document
            for document in documents
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name") == "starbase-github-connector"
        )
        live_github["spec"]["replicas"] = 1
        with self.assertRaisesRegex(ValueError, "bounded Phase 5 preview"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

    def test_preview_activation_rejects_unexpected_workload_kind(self) -> None:
        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        documents.append(
            {
                "apiVersion": "batch/v1",
                "kind": "CronJob",
                "metadata": {"name": "unexpected", "namespace": "starbase-connectors"},
                "spec": {},
            }
        )
        with self.assertRaisesRegex(ValueError, "workload inventory"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

    def test_preview_activation_rejects_raw_pod(self) -> None:
        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        documents.append(
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {"name": "unexpected", "namespace": "starbase-connectors"},
                "spec": {},
            }
        )
        with self.assertRaisesRegex(ValueError, "workload inventory"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

    def test_preview_activation_rejects_unexpected_native_pod_controllers(self) -> None:
        for api_version, kind in (
            ("apps/v1", "ReplicaSet"),
            ("v1", "ReplicationController"),
        ):
            with self.subTest(kind=kind):
                documents, locked_images, retained_jobs = (
                    self._phase5_preview_documents()
                )
                documents.append(
                    {
                        "apiVersion": api_version,
                        "kind": kind,
                        "metadata": {
                            "name": "unexpected",
                            "namespace": "starbase-connectors",
                        },
                        "spec": {},
                    }
                )
                with self.assertRaisesRegex(ValueError, "workload inventory"):
                    starbase_promotion.assert_phase5_preview_deployments(
                        documents, locked_images, retained_jobs
                    )

    def test_preview_activation_rejects_retained_job_replacement_or_drift(self) -> None:
        for mutation in ("force", "baseline-force", "command"):
            with self.subTest(mutation=mutation):
                documents, locked_images, retained_jobs = (
                    self._phase5_preview_documents()
                )
                retained = next(
                    document
                    for document in documents
                    if document.get("kind") == "Job"
                    and document.get("metadata", {}).get("name")
                    == "starbase-database-bootstrap-v1-0f68098795da"
                )
                if mutation in {"force", "baseline-force"}:
                    retained.setdefault("metadata", {}).setdefault("annotations", {})[
                        "kustomize.toolkit.fluxcd.io/force"
                    ] = "enabled"
                    if mutation == "baseline-force":
                        baseline = next(
                            document
                            for document in retained_jobs
                            if document.get("metadata", {}).get("name")
                            == "starbase-database-bootstrap-v1-0f68098795da"
                        )
                        baseline.setdefault("metadata", {}).setdefault(
                            "annotations", {}
                        )["kustomize.toolkit.fluxcd.io/force"] = "enabled"
                else:
                    retained["spec"]["template"]["spec"]["containers"][0]["command"] = [
                        "/bin/sh",
                        "-c",
                        "echo replaced",
                    ]
                with self.assertRaisesRegex(ValueError, "retained Job"):
                    starbase_promotion.assert_phase5_preview_deployments(
                        documents, locked_images, retained_jobs
                    )

    def test_preview_activation_rejects_unlocked_core_or_web_image(self) -> None:
        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        core = next(
            document
            for document in documents
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name") == "starbase-core"
        )
        core["spec"]["template"]["spec"]["containers"][0]["image"] += "-different"
        with self.assertRaisesRegex(ValueError, "release-locked"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

    def test_preview_activation_rejects_nested_projected_secret(self) -> None:
        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        fixture = next(
            document
            for document in documents
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name") == "starbase-preview-fixture"
        )
        identity = next(
            volume
            for volume in fixture["spec"]["template"]["spec"]["volumes"]
            if volume["name"] == "core-workload-identity"
        )
        identity["projected"]["sources"].append(
            {"secret": {"name": "github"}}  # pragma: allowlist secret
        )
        with self.assertRaisesRegex(ValueError, "fixture boundary"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

    def test_preview_activation_rejects_indirect_fixture_rbac(self) -> None:
        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        documents.append(
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "RoleBinding",
                "metadata": {"name": "indirect", "namespace": "starbase-connectors"},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "Role",
                    "name": "observer",
                },
                "subjects": [
                    {
                        "kind": "Group",
                        "name": "system:serviceaccounts:starbase-connectors",
                    }
                ],
            }
        )
        with self.assertRaisesRegex(ValueError, "Kubernetes RBAC"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

    def test_preview_activation_rejects_modified_inherited_egress(self) -> None:
        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        allow_dns = next(
            document
            for document in documents
            if document.get("kind") == "NetworkPolicy"
            and document.get("metadata", {}).get("namespace") == "starbase-connectors"
            and document.get("metadata", {}).get("name") == "allow-dns"
        )
        allow_dns["spec"]["egress"].append(
            {
                "to": [
                    {
                        "podSelector": {
                            "matchLabels": {"app.kubernetes.io/name": "proxy"}
                        }
                    }
                ],
                "ports": [{"protocol": "TCP", "port": 443}],
            }
        )
        with self.assertRaisesRegex(ValueError, "egress differs"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

    def test_preview_activation_rejects_live_fixture_or_unlocked_image(self) -> None:
        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        fixture = next(
            document
            for document in documents
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name") == "starbase-preview-fixture"
        )
        fixture["spec"]["template"]["spec"]["containers"][0]["env"][0][
            "value"
        ] = "github"
        with self.assertRaisesRegex(ValueError, "fixture boundary"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        fixture = next(
            document
            for document in documents
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name") == "starbase-preview-fixture"
        )
        fixture["spec"]["template"]["spec"]["volumes"].append(
            {
                "name": "provider-credential",
                "secret": {"secretName": "github"},  # pragma: allowlist secret
            }
        )
        with self.assertRaisesRegex(ValueError, "fixture boundary"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

        documents, locked_images, retained_jobs = self._phase5_preview_documents()
        fixture = next(
            document
            for document in documents
            if document.get("kind") == "Deployment"
            and document.get("metadata", {}).get("name") == "starbase-preview-fixture"
        )
        fixture["spec"]["template"]["spec"]["containers"][0]["image"] += "-different"
        with self.assertRaisesRegex(ValueError, "release-locked"):
            starbase_promotion.assert_phase5_preview_deployments(
                documents, locked_images, retained_jobs
            )

    @staticmethod
    def _phase5_preview_documents() -> tuple[list[dict], dict[str, str], list[dict]]:
        repository = Path(__file__).resolve().parents[1]
        preview = repository / "infrastructure/gitops/apps/starbase-phase5-preview"
        rendered = subprocess.run(
            ["kubectl", "kustomize", str(preview)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        documents = [document for document in yaml.safe_load_all(rendered) if document]
        locked_images = json.loads(
            (
                repository / "infrastructure/gitops/apps/starbase/promotion-lock.json"
            ).read_text()
        )["release"]["images"]
        foundation = (
            repository / "infrastructure/gitops/apps/starbase-phase4a-foundation"
        )
        foundation_rendered = subprocess.run(
            ["kubectl", "kustomize", str(foundation)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        retained_jobs = [
            document
            for document in yaml.safe_load_all(foundation_rendered)
            if document and document.get("kind") == "Job"
        ]
        return documents, locked_images, retained_jobs


if __name__ == "__main__":
    unittest.main()
