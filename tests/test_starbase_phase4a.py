from __future__ import annotations

import json
import subprocess
import unittest
from hashlib import sha256
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "infrastructure/gitops/apps/starbase-phase4a"
FOUNDATION_OVERLAY = ROOT / "infrastructure/gitops/apps/starbase-phase4a-foundation"
AUTHENTIK_BLUEPRINTS = (
    ROOT / "infrastructure/gitops/apps/authentik/blueprints-configmap.yaml"
)
AUTHENTIK_HELMRELEASE = ROOT / "infrastructure/gitops/apps/authentik/helmrelease.yaml"
APPS_KUSTOMIZATION = ROOT / "infrastructure/gitops/apps/kustomization.yaml"
FOUNDATION_FLUX = (
    ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
)
FLUX_AGGREGATE = ROOT / "infrastructure/gitops/flux-system/kustomization.yaml"
PROMOTION_INPUT = ROOT / "infrastructure/gitops/apps/starbase/promotion-input.json"
PROMOTION_LOCK = ROOT / "infrastructure/gitops/apps/starbase/promotion-lock.json"
RC2_MIGRATION_EVIDENCE = (
    ROOT
    / "docs/infrastructure/gitops/evidence/starbase-rc2-migration-retirement"
)
RC4_CORE_MIGRATION_EVIDENCE = (
    ROOT / "docs/infrastructure/gitops/evidence/starbase-rc4-core-migration"
)
RC4_GATEWAY_MIGRATION_EVIDENCE = (
    ROOT / "docs/infrastructure/gitops/evidence/starbase-rc4-gateway-migration"
)
SOPS_CONFIG = yaml.safe_load((ROOT / ".sops.yaml").read_text())
SOPS_RECIPIENT = SOPS_CONFIG["creation_rules"][0]["age"]
EXPECTED_ENCRYPTED_SECRETS = {
    ("database", "starbase-database-bootstrap"): {
        "core-runtime-password",
        "core-migrator-password",
        "gateway-runtime-password",
        "gateway-migrator-password",
    },
    ("starbase-system", "starbase-core-runtime"): {"database-url"},
    ("starbase-system", "starbase-gateway-runtime"): {
        "database-url",
        "session-encryption-key",
    },
    ("starbase-system", "starbase-core-migration"): {"database-url"},
    ("starbase-system", "starbase-gateway-migration"): {"database-url"},
}
EXPECTED_REGISTRY_SECRETS = {
    ("starbase-system", "starbase-ghcr-pull"),
    ("starbase-connectors", "starbase-ghcr-pull"),
}


def render_documents(path: Path) -> list[dict]:
    result = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class StarbasePhase4AContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["kubectl", "kustomize", str(OVERLAY)],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.rendered = result.stdout
        cls.documents = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
        cls.by_identity = {
            (
                doc["kind"],
                doc.get("metadata", {}).get("namespace", ""),
                doc["metadata"]["name"],
            ): doc
            for doc in cls.documents
        }

    def object(self, kind: str, namespace: str, name: str) -> dict:
        return self.by_identity[(kind, namespace, name)]

    def test_foundation_runs_only_authorized_database_stages(self) -> None:
        aggregate = yaml.safe_load(APPS_KUSTOMIZATION.read_text())
        self.assertNotIn("starbase-phase4a-foundation/", aggregate["resources"])
        self.assertNotIn("starbase-phase4a/", aggregate["resources"])
        self.assertNotIn("starbase/", aggregate["resources"])

        foundation_flux = yaml.safe_load(FOUNDATION_FLUX.read_text())
        flux_aggregate = yaml.safe_load(FLUX_AGGREGATE.read_text())
        self.assertIn(
            "starbase-foundation-kustomization.yaml", flux_aggregate["resources"]
        )
        self.assertEqual(foundation_flux["metadata"]["name"], "starbase-foundation")
        self.assertEqual(
            foundation_flux["metadata"]["labels"]["starbase.io/activation-wave"],
            "phase4a-restore-v1",
        )
        self.assertEqual(
            foundation_flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase5-preview",
        )
        dependency = foundation_flux["spec"]["dependsOn"][0]
        self.assertEqual(dependency["name"], "databases")
        for requirement in (
            "starbase.io/activation-wave",
            "exists(e, e.type == 'Ready' && e.status == 'True')",
            "dep.metadata.generation == dep.status.observedGeneration",
        ):
            self.assertIn(requirement, dependency["readyExpr"])
        self.assertNotIn(".all(", dependency["readyExpr"])

        expected_activation = {
            "bundle": "flux-referenced-inert-foundation",
            "core": "flux-referenced-zero-replicas",
            "github_connector": "intentionally-disabled-zero-replicas",
            "kubernetes_connector": "flux-referenced-zero-replicas",
            "migrations": "flux-referenced-suspended",
        }
        self.assertEqual(
            json.loads(PROMOTION_INPUT.read_text())["expected_activation"],
            expected_activation,
        )
        self.assertEqual(
            json.loads(PROMOTION_LOCK.read_text())["activation"],
            expected_activation,
        )

        foundation = render_documents(FOUNDATION_OVERLAY)
        kinds = {document["kind"] for document in foundation}
        self.assertEqual(
            {
                (document["metadata"]["namespace"], document["metadata"]["name"])
                for document in foundation
                if document["kind"] == "Secret"
            },
            set(EXPECTED_ENCRYPTED_SECRETS) | EXPECTED_REGISTRY_SECRETS,
        )
        self.assertIn("Ingress", kinds)
        self.assertIn("Certificate", kinds)
        self.assertFalse(
            any(
                document["kind"] == "ConfigMap"
                and document["metadata"]["name"] == "starbase-authentik-blueprint"
                for document in foundation
            )
        )
        self.assertTrue(
            any(document["kind"] == "ResourceQuota" for document in foundation)
        )
        self.assertTrue(
            any(document["kind"] == "NetworkPolicy" for document in foundation)
        )
        runnable_jobs = []
        for document in foundation:
            if document["kind"] == "Deployment":
                self.assertEqual(document["spec"]["replicas"], 0)
            if document["kind"] == "Job":
                if not document["spec"]["suspend"]:
                    runnable_jobs.append(
                        (
                            document["metadata"]["namespace"],
                            document["metadata"]["name"],
                        )
                    )
        boundary_probe = next(
            document
            for document in foundation
            if document["kind"] == "Job"
            and document["metadata"].get("annotations", {}).get(
                "starbase.io/activation-stage"
            )
            == "phase4a-network-boundary"
        )
        self.assertEqual(
            set(runnable_jobs),
            {
                ("database", "starbase-database-bootstrap-v1-0f68098795da"),
                ("starbase-system", boundary_probe["metadata"]["name"]),
            },
        )

        health_checks = {
            (
                check["apiVersion"],
                check["kind"],
                check["namespace"],
                check["name"],
            )
            for check in foundation_flux["spec"]["healthChecks"]
        }
        self.assertEqual(
            health_checks,
            {
                (
                    "batch/v1",
                    "Job",
                    "database",
                    "postgres-backup-restore-verification-v1-e4deaaf32203",
                ),
                (
                    "batch/v1",
                    "Job",
                    "starbase-system",
                    boundary_probe["metadata"]["name"],
                ),
                (
                    "cert-manager.io/v1",
                    "Certificate",
                    "starbase-system",
                    "starbase-tls",
                ),
                (
                    "apps/v1",
                    "Deployment",
                    "starbase-system",
                    "starbase-core",
                ),
                (
                    "apps/v1",
                    "Deployment",
                    "starbase-connectors",
                    "starbase-preview-fixture",
                ),
            },
        )

    def test_network_boundary_probe_uses_real_core_identity_and_is_content_bound(self) -> None:
        probe = next(
            document
            for document in self.documents
            if document["kind"] == "Job"
            and document["metadata"].get("annotations", {}).get(
                "starbase.io/activation-stage"
            )
            == "phase4a-network-boundary"
        )
        pod = probe["spec"]["template"]["spec"]
        container = pod["containers"][0]
        command = container["args"][0]
        self.assertEqual(
            probe["metadata"]["name"],
            f"starbase-network-boundary-v1-{sha256(command.encode()).hexdigest()[:12]}",
        )
        self.assertEqual(probe["spec"]["backoffLimit"], 0)
        self.assertEqual(probe["spec"]["activeDeadlineSeconds"], 300)
        self.assertIsNone(probe["spec"]["ttlSecondsAfterFinished"])
        self.assertEqual(pod["serviceAccountName"], "starbase-core")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"][0]
            ["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        self.assertEqual(
            probe["spec"]["template"]["metadata"]["labels"],
            {
                "app.kubernetes.io/name": "starbase-core",
                "app.kubernetes.io/part-of": "starbase",
                "starbase.io/network-boundary-probe": "true",
            },
        )
        self.assertEqual(
            container["image"],
            "docker.io/bitnami/postgresql@sha256:e93732718bf7fafa61a04abaa437fc601c80a791857105fd6fca18407b5725c9",
        )
        token = next(
            source["serviceAccountToken"]
            for volume in pod["volumes"]
            if volume["name"] == "kubernetes-api-identity"
            for source in volume["projected"]["sources"]
            if "serviceAccountToken" in source
        )
        self.assertEqual(
            token["audience"], "https://kubernetes.default.svc.cluster.local"
        )
        self.assertEqual(token["expirationSeconds"], 600)
        self.assertEqual(token["path"], "token")
        for required in (
            "api_status()",
            "postgresql.database.svc.cluster.local/5432",
            "auth.almckay.io/application/o/starbase/.well-known/openid-configuration",
            "api_status '/openid/v1/jwks'",
            "api_status '/api/v1/secrets?limit=1'",
            "/var/run/secrets/starbase.io/kubernetes-api/ca.crt",
            "/var/run/secrets/starbase.io/kubernetes-api/token",
            '[[ "$issuer_status" == "200" ]]',
            '[[ "$status" == "403" ]]',
            "--config -",
            "expect_tcp_blocked 169.254.169.254 80",
            "expect_tcp_blocked example.com 443",
            "PASS: Starbase core network and RBAC boundary verified",
        ):
            self.assertIn(required, command)
        self.assertEqual(command.count('header = "Authorization: Bearer %s"'), 1)
        self.assertEqual(command.count("--config -"), 1)
        self.assertNotIn("/var/run/secrets/starbase.io/workload-identity", command)
        self.assertNotIn("Authorization: Bearer $(", command)
        self.assertNotIn("audience: starbase-core", str(probe))
        self.assertNotIn("secretKeyRef", str(probe))

    def test_kubernetes_observer_is_namespace_bounded(self) -> None:
        self.assertFalse(
            any(
                document["kind"] in {"ClusterRole", "ClusterRoleBinding"}
                for document in self.documents
            )
        )
        namespaces = {
            "starbase-system",
            "starbase-connectors",
            "starbase-execution",
        }
        roles = [
            document
            for document in self.documents
            if document["kind"] == "Role"
            and document["metadata"]["name"] == "starbase-kubernetes-observer"
        ]
        bindings = [
            document
            for document in self.documents
            if document["kind"] == "RoleBinding"
            and document["metadata"]["name"] == "starbase-kubernetes-observer"
        ]
        self.assertEqual(
            {document["metadata"]["namespace"] for document in roles}, namespaces
        )
        self.assertEqual(
            {document["metadata"]["namespace"] for document in bindings},
            namespaces,
        )
        expected_rules = [
            {"apiGroups": [""], "resources": ["pods"], "verbs": ["list"]},
            {
                "apiGroups": ["apps"],
                "resources": ["daemonsets", "deployments", "statefulsets"],
                "verbs": ["list"],
            },
        ]
        for role in roles:
            self.assertEqual(role["rules"], expected_rules)
        for binding in bindings:
            self.assertEqual(
                binding["roleRef"],
                {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "Role",
                    "name": "starbase-kubernetes-observer",
                },
            )
            self.assertEqual(
                binding["subjects"],
                [
                    {
                        "kind": "ServiceAccount",
                        "name": "starbase-kubernetes-connector",
                        "namespace": "starbase-connectors",
                    }
                ],
            )

    def test_contract_contains_only_exact_encrypted_secrets_and_immutable_images(self) -> None:
        self.assertEqual(len(self.documents), 59)
        secrets = {
            (document["metadata"]["namespace"], document["metadata"]["name"]): document
            for document in self.documents
            if document["kind"] == "Secret"
        }
        self.assertEqual(
            set(secrets), set(EXPECTED_ENCRYPTED_SECRETS) | EXPECTED_REGISTRY_SECRETS
        )
        for identity, expected_keys in EXPECTED_ENCRYPTED_SECRETS.items():
            secret = secrets[identity]
            self.assertEqual(secret["type"], "Opaque")
            self.assertNotIn("data", secret)
            self.assertEqual(set(secret["stringData"]), expected_keys)
            for encrypted_value in secret["stringData"].values():
                self.assertRegex(encrypted_value, r"^ENC\[AES256_GCM,data:")
            self.assertEqual(
                secret["metadata"]["annotations"]["starbase.io/credential-contract"],
                "phase4a-v1",
            )
            self.assertEqual(
                secret["metadata"]["annotations"]["starbase.io/activation-state"],
                "provisioned-inactive",
            )
            age_entries = secret["sops"]["age"]
            self.assertEqual(len(age_entries), 1)
            self.assertEqual(
                age_entries[0]["recipient"],
                SOPS_RECIPIENT,
            )
            self.assertEqual(secret["sops"]["encrypted_regex"], "^(data|stringData)$")
        for identity in EXPECTED_REGISTRY_SECRETS:
            secret = secrets[identity]
            self.assertEqual(secret["type"], "kubernetes.io/dockerconfigjson")
            self.assertNotIn("data", secret)
            self.assertEqual(set(secret["stringData"]), {".dockerconfigjson"})
            self.assertRegex(
                secret["stringData"][".dockerconfigjson"], r"^ENC\[AES256_GCM,data:"
            )
            self.assertEqual(
                secret["metadata"]["annotations"]["starbase.io/credential-contract"],
                "ghcr-read-packages-v1",
            )
            self.assertEqual(
                secret["metadata"]["annotations"]["starbase.io/expires-on"],
                "2026-11-23T00:00:00Z",
            )
            self.assertEqual(
                secret["sops"]["age"][0]["recipient"], SOPS_RECIPIENT
            )
            self.assertEqual(
                secret["sops"]["encrypted_regex"], "^(data|stringData)$"
            )
        for doc in self.documents:
            pod = None
            if doc["kind"] == "Deployment":
                pod = doc["spec"]["template"]["spec"]
            elif doc["kind"] == "Job":
                pod = doc["spec"]["template"]["spec"]
            if pod is None:
                continue
            for container in pod.get("initContainers", []) + pod.get("containers", []):
                self.assertRegex(container["image"], r"@sha256:[0-9a-f]{64}$")

    def test_database_bootstrap_is_bounded_and_authorized(self) -> None:
        script = self.object(
            "ConfigMap", "database", "starbase-database-bootstrap-v1"
        )["data"]["bootstrap.sh"]
        expected_name = f"starbase-database-bootstrap-v1-{sha256(script.encode()).hexdigest()[:12]}"
        job = self.object("Job", "database", expected_name)
        self.assertEqual(
            job["metadata"]["annotations"]["starbase.io/bootstrap-contract-digest"],
            f"sha256:{sha256(script.encode()).hexdigest()}",
        )
        subprocess.run(["sh", "-n"], input=script, check=True, text=True)
        self.assertEqual(job["metadata"]["annotations"]["starbase.io/activation-state"], "authorized")
        self.assertEqual(
            job["metadata"]["annotations"]["starbase.io/activation-stage"],
            "phase4a-database-bootstrap",
        )
        self.assertNotIn("starbase.io/blocker", job["metadata"]["annotations"])
        self.assertEqual(job["spec"]["suspend"], False)
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 300)
        self.assertNotIn("ttlSecondsAfterFinished", job["spec"])
        pod = job["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["serviceAccountName"], "starbase-database-bootstrap")
        self.assertEqual(
            pod["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        container = pod["containers"][0]
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertIn("requests", container["resources"])
        self.assertIn("limits", container["resources"])

        for database in ("starbase_core", "starbase_gateway"):
            self.assertIn(database, script)
        for role in (
            "starbase_core_migrator",
            "starbase_core_runtime",
            "starbase_gateway_migrator",
            "starbase_gateway_runtime",
        ):
            self.assertIn(role, script)
        self.assertIn(
            "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION", script
        )
        self.assertNotIn("SUPERUSER CREATEDB", script)
        self.assertNotIn("GRANT ALL ON DATABASE", script)
        self.assertNotIn("--set=password=", script)
        self.assertIn(r"\getenv role STARBASE_BOOTSTRAP_ROLE", script)
        self.assertIn(r"\getenv credential STARBASE_BOOTSTRAP_CREDENTIAL", script)
        self.assertIn("SET log_statement = 'none';", script)

    def test_runtime_bindings_use_separate_secret_contracts(self) -> None:
        secret_contract = self.object(
            "ConfigMap", "starbase-system", "starbase-secret-contracts"
        )
        self.assertEqual(
            secret_contract["metadata"]["annotations"]["starbase.io/activation-state"],
            "gateway-migration-authorized-runtime-inactive",
        )
        self.assertEqual(
            secret_contract["metadata"]["annotations"]["starbase.io/blocker"],
            "runtime-separately-authorized",
        )

        core = self.object("Deployment", "starbase-system", "starbase-core")
        container = next(
            container
            for container in core["spec"]["template"]["spec"]["containers"]
            if container["name"] == "core"
        )
        env = {entry["name"]: entry for entry in container["env"]}
        self.assertEqual(
            env["STARBASE_CORE_DATABASE_URL"]["valueFrom"]["secretKeyRef"],
            {"name": "starbase-core-runtime", "key": "database-url"},
        )
        self.assertNotIn("STARBASE_CORE_MIGRATION_DATABASE_URL", env)
        self.assertEqual(env["STARBASE_OIDC_CLIENT_ID"]["value"], "starbase-kubani")
        self.assertEqual(
            env["STARBASE_OIDC_ISSUER"]["value"],
            "https://auth.almckay.io/application/o/starbase/",
        )
        required_groups = env["STARBASE_OIDC_REQUIRED_GROUPS"]["value"]
        self.assertEqual(required_groups, '["starbase-operators"]')
        self.assertEqual(json.loads(required_groups), ["starbase-operators"])
        self.assertEqual(env["STARBASE_EXTERNAL_URL"]["value"], "https://starbase.almckay.io")
        self.assertEqual(
            env["STARBASE_WORKLOAD_OIDC_ISSUER"]["value"],
            "https://kubernetes.default.svc.cluster.local",
        )
        self.assertEqual(
            env["STARBASE_WORKLOAD_OIDC_JWKS_URL"]["value"],
            "https://100.92.107.71:6443/openid/v1/jwks",
        )
        self.assertNotIn("STARBASE_WORKLOAD_OIDC_TOKEN_FILE", env)
        self.assertEqual(core["spec"]["replicas"], 0)

        mounts = {mount["name"]: mount for mount in container["volumeMounts"]}
        self.assertTrue(mounts["gateway-runtime"]["readOnly"])
        self.assertEqual(
            env["STARBASE_GATEWAY_DATABASE_URL_FILE"]["value"],
            "/var/run/secrets/starbase.io/gateway/database-url",
        )
        self.assertEqual(
            env["STARBASE_SESSION_ENCRYPTION_KEY_FILE"]["value"],
            "/var/run/secrets/starbase.io/gateway/session-encryption-key",
        )

        core_migration = self.object(
            "Job", "starbase-system", "starbase-core-migrate-0da307f3148a"
        )
        gateway_migration = self.object(
            "Job", "starbase-system", "starbase-gateway-migrate-f2fa2f551602"
        )
        self.assertTrue(core_migration["spec"]["suspend"])
        self.assertEqual(core_migration["spec"]["backoffLimit"], 0)
        self.assertEqual(core_migration["spec"]["activeDeadlineSeconds"], 300)
        self.assertNotIn("ttlSecondsAfterFinished", core_migration["spec"])
        self.assertEqual(
            core_migration["metadata"]["annotations"]["starbase.io/activation-state"],
            "blocked",
        )
        self.assertEqual(
            core_migration["metadata"]["annotations"]["starbase.io/activation-stage"],
            "rc5-unchanged-migrations-suspended",
        )
        self.assertEqual(
            core_migration["metadata"]["annotations"]["starbase.io/blocker"],
            "unchanged-schema-prior-rc4-completion-retained",
        )
        core_pod = core_migration["spec"]["template"]["spec"]
        self.assertEqual(
            core_pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        self.assertNotIn(
            "preferredDuringSchedulingIgnoredDuringExecution",
            core_pod["affinity"]["nodeAffinity"],
        )
        core_container = core_pod["containers"][0]
        self.assertEqual(
            core_container["env"][0]["valueFrom"]["secretKeyRef"],
            {"name": "starbase-core-migration", "key": "database-url"},
        )

        self.assertTrue(gateway_migration["spec"]["suspend"])
        self.assertEqual(gateway_migration["spec"]["backoffLimit"], 0)
        self.assertEqual(gateway_migration["spec"]["activeDeadlineSeconds"], 300)
        self.assertNotIn("ttlSecondsAfterFinished", gateway_migration["spec"])
        self.assertEqual(
            gateway_migration["metadata"]["annotations"][
                "starbase.io/activation-state"
            ],
            "blocked",
        )
        self.assertEqual(
            gateway_migration["metadata"]["annotations"][
                "starbase.io/activation-stage"
            ],
            "rc5-unchanged-migrations-suspended",
        )
        self.assertEqual(
            gateway_migration["metadata"]["annotations"]["starbase.io/blocker"],
            "unchanged-schema-prior-rc4-completion-retained",
        )
        self.assertEqual(
            gateway_migration["metadata"]["annotations"][
                "starbase.io/migration-set-digest"
            ],
            "sha256:38db198875781dd2d640358b1840ae28e7574dd4c87661e0a8bb0b2e8837d3f3",
        )
        self.assertEqual(
            core_migration["metadata"]["annotations"]["starbase.io/migrator-image"],
            "ghcr.io/x-mckay/starbase/core-migrator@"
            "sha256:983ed5ea6c6cf5820c42f171429eea7716633d5b0dee5347f5a7182c07d88462",
        )
        self.assertEqual(
            gateway_migration["metadata"]["annotations"][
                "starbase.io/migrator-image"
            ],
            "ghcr.io/x-mckay/starbase/gateway-migrator@"
            "sha256:b4ab2e9e07726f855b9eea91c112291350cdef2e3f316253b03167860bab4b8a",
        )
        gateway_pod = gateway_migration["spec"]["template"]["spec"]
        self.assertEqual(
            gateway_pod["affinity"]["nodeAffinity"]
            ["requiredDuringSchedulingIgnoredDuringExecution"]
            ["nodeSelectorTerms"][0]["matchExpressions"][0]["values"],
            ["asio", "strix"],
        )
        self.assertNotIn(
            "preferredDuringSchedulingIgnoredDuringExecution",
            gateway_pod["affinity"]["nodeAffinity"],
        )
        gateway_container = gateway_pod["containers"][0]
        self.assertEqual(
            gateway_container["image"],
            "ghcr.io/x-mckay/starbase/gateway-migrator@"
            "sha256:b4ab2e9e07726f855b9eea91c112291350cdef2e3f316253b03167860bab4b8a",
        )
        self.assertEqual(
            gateway_container["env"][0]["valueFrom"]["secretKeyRef"],
            {"name": "starbase-gateway-migration", "key": "database-url"},
        )

    def test_registry_pull_authority_is_bounded_and_recovers_only_core_migration(self) -> None:
        for namespace, name in (
            ("starbase-system", "starbase-core"),
            ("starbase-connectors", "starbase-github-connector"),
            ("starbase-connectors", "starbase-kubernetes-connector"),
        ):
            account = self.object("ServiceAccount", namespace, name)
            self.assertEqual(
                account["imagePullSecrets"], [{"name": "starbase-ghcr-pull"}]
            )
            self.assertFalse(account["automountServiceAccountToken"])

        core_migration = self.object(
            "Job", "starbase-system", "starbase-core-migrate-0da307f3148a"
        )
        self.assertNotIn(
            "kustomize.toolkit.fluxcd.io/force",
            core_migration["metadata"]["annotations"],
        )
        self.assertNotIn(
            "starbase.io/recovery-reason",
            core_migration["metadata"]["annotations"],
        )
        self.assertEqual(
            core_migration["spec"]["template"]["spec"]["imagePullSecrets"],
            [{"name": "starbase-ghcr-pull"}],
        )
        self.assertTrue(core_migration["spec"]["suspend"])
        self.assertEqual(core_migration["spec"]["backoffLimit"], 0)

        for namespace, name in (
            ("starbase-system", "starbase-core"),
            ("starbase-connectors", "starbase-github-connector"),
            ("starbase-connectors", "starbase-kubernetes-connector"),
        ):
            self.assertEqual(
                self.object("Deployment", namespace, name)["spec"]["replicas"], 0
            )

    def test_authentik_blueprint_is_public_pkce_and_group_bounded(self) -> None:
        owner = yaml.safe_load(AUTHENTIK_BLUEPRINTS.read_text())
        self.assertEqual(owner["metadata"]["name"], "authentik-blueprints")
        self.assertEqual(
            set(owner["data"]), {"kubani-forward-auth.yaml", "starbase.yaml"}
        )
        blueprint = owner["data"]["starbase.yaml"]
        self.assertIn("model: authentik_providers_oauth2.oauth2provider", blueprint)
        self.assertIn("client_type: public", blueprint)
        self.assertIn("client_id: starbase-kubani", blueprint)
        self.assertIn("issuer_mode: per_provider", blueprint)
        self.assertIn("grant_types:\n        - authorization_code", blueprint)
        provider = next(
            entry
            for entry in yaml.load(blueprint, Loader=yaml.BaseLoader)["entries"]
            if entry.get("id") == "starbase-provider"
        )
        self.assertEqual(provider["attrs"]["access_token_validity"], "minutes=15")
        self.assertEqual(provider["attrs"]["refresh_token_validity"], "hours=8")
        self.assertIn("redirect_uri_type: authorization", blueprint)
        self.assertNotIn("client_secret", blueprint)
        self.assertIn("https://starbase.almckay.io/api/v1/auth/callback", blueprint)
        self.assertIn("matching_mode: strict", blueprint)
        self.assertIn('"groups"', blueprint)
        self.assertIn("id: starbase-operators-group", blueprint)
        self.assertIn("id: starbase-application", blueprint)
        self.assertIn("model: authentik_policies.policybinding", blueprint)
        self.assertIn("target: !KeyOf starbase-application", blueprint)
        self.assertIn("group: !KeyOf starbase-operators-group", blueprint)
        self.assertIn("policy_engine_mode: all", blueprint)
        self.assertIn("signing_key: !Find", blueprint)
        self.assertIn("scope-openid", blueprint)
        self.assertIn("scope-email", blueprint)
        self.assertIn("scope-profile", blueprint)
        self.assertIn("is_superuser: false", blueprint)
        self.assertIn(
            'request.user.groups.filter(name="starbase-operators")', blueprint
        )
        self.assertNotIn("request.user.groups.all()", blueprint)

        helmrelease = yaml.safe_load(AUTHENTIK_HELMRELEASE.read_text())
        mounted = helmrelease["spec"]["values"]["blueprints"]["configMaps"]
        self.assertEqual(mounted, ["authentik-blueprints"])
        self.assertNotIn("starbase-authentik-blueprint", self.rendered)
        self.assertFalse((OVERLAY / "authentik-blueprint.yaml").exists())

    def test_authentik_has_bounded_read_only_verifier(self) -> None:
        verifier_path = ROOT / "infrastructure/scripts/validate-starbase-oidc.sh"
        verifier = verifier_path.read_text()
        subprocess.run(["bash", "-n", str(verifier_path)], check=True)
        for requirement in (
            "check-cluster-identity.sh",
            "/readyz",
            "starbase/.well-known/openid-configuration",
            "application/o/starbase/jwks/",
            "starbase-operators",
            "authentik-blueprints",
            "starbase.yaml",
            "Cache-Control: no-cache",
            "observed_at=",
            "grant_types_supported",
            "response_types_supported",
        ):
            self.assertIn(requirement, verifier)
        for unsafe_prefix_match in (
            '== *"access_token_validity: minutes=15"*',
            '== *"refresh_token_validity: hours=8"*',
        ):
            self.assertNotIn(unsafe_prefix_match, verifier)
        for exact_scalar_check in (
            'assert_blueprint_scalar "$blueprint" "access_token_validity" "minutes=15"',
            'assert_blueprint_scalar "$blueprint" "refresh_token_validity" "hours=8"',
        ):
            self.assertIn(exact_scalar_check, verifier)
        for forbidden in (
            "kubectl apply",
            "kubectl patch",
            "kubectl delete",
            "flux reconcile",
            "get secret",
            "get secrets",
            "authentik-credentials",
            "spec.replicas",
            "spec.suspend",
        ):
            self.assertNotIn(forbidden, verifier.lower())

    def test_authentik_verifier_matches_complete_unique_lifetime_scalars(self) -> None:
        verifier_path = ROOT / "infrastructure/scripts/validate-starbase-oidc.sh"
        command = (
            'source "$1"; blueprint="$(cat)"; '
            'assert_blueprint_scalar "$blueprint" "$2" "$3" "fixture lifetime"'
        )
        cases = (
            ("access_token_validity", "minutes=15", "access_token_validity: minutes=15\n", True),
            ("access_token_validity", "minutes=15", "access_token_validity: minutes=150\n", False),
            (
                "access_token_validity",
                "minutes=15",
                "access_token_validity: minutes=15\naccess_token_validity: minutes=150\n",
                False,
            ),
            ("refresh_token_validity", "hours=8", "refresh_token_validity: hours=8\n", True),
            ("refresh_token_validity", "hours=8", "refresh_token_validity: hours=80\n", False),
        )
        for key, expected, blueprint, accepted in cases:
            with self.subTest(key=key, blueprint=blueprint):
                result = subprocess.run(
                    ["bash", "-c", command, "bash", str(verifier_path), key, expected],
                    input=blueprint,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_ingress_exposes_only_the_browser_service(self) -> None:
        ingress = self.object("Ingress", "starbase-system", "starbase")
        backend = ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"]
        self.assertEqual(backend["name"], "starbase-core")
        self.assertEqual(backend["port"]["number"], 80)
        self.assertNotIn("starbase-core-api", str(ingress))
        self.assertNotIn(
            "cert-manager.io/cluster-issuer",
            ingress["metadata"].get("annotations", {}),
        )
        certificate = self.object("Certificate", "starbase-system", "starbase-tls")
        self.assertEqual(certificate["spec"]["dnsNames"], ["starbase.almckay.io"])

    def test_network_policy_is_exact_and_github_stays_disabled(self) -> None:
        db_ingress = self.object(
            "NetworkPolicy", "database", "allow-starbase-postgresql"
        )
        source = db_ingress["spec"]["ingress"][0]["from"][0]
        self.assertEqual(
            source["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"],
            "starbase-system",
        )
        self.assertEqual(db_ingress["spec"]["ingress"][0]["ports"][0]["port"], 5432)

        api_egress = self.object(
            "NetworkPolicy", "starbase-system", "allow-core-to-workload-issuer"
        )
        paths = {
            (
                rule["to"][0]["ipBlock"]["cidr"],
                rule["ports"][0]["port"],
            )
            for rule in api_egress["spec"]["egress"]
        }
        self.assertEqual(paths, {("10.43.0.1/32", 443), ("100.92.107.71/32", 6443)})

        connector_api_egress = self.object(
            "NetworkPolicy", "starbase-connectors", "allow-kubernetes-connector-to-api"
        )
        self.assertEqual(
            connector_api_egress["spec"]["podSelector"]["matchLabels"],
            {"app.kubernetes.io/name": "starbase-kubernetes-connector"},
        )
        connector_paths = {
            (rule["to"][0]["ipBlock"]["cidr"], rule["ports"][0]["port"])
            for rule in connector_api_egress["spec"]["egress"]
        }
        self.assertEqual(
            connector_paths, {("10.43.0.1/32", 443), ("100.92.107.71/32", 6443)}
        )

        kubernetes_connector = self.object(
            "Deployment", "starbase-connectors", "starbase-kubernetes-connector"
        )
        self.assertEqual(kubernetes_connector["spec"]["replicas"], 0)

        github = self.object(
            "Deployment", "starbase-connectors", "starbase-github-connector"
        )
        self.assertEqual(github["spec"]["replicas"], 0)
        self.assertFalse(
            any(
                doc["kind"] == "NetworkPolicy"
                and "github" in doc["metadata"]["name"].lower()
                for doc in self.documents
            )
        )

    def test_resource_governance_preserves_measured_headroom(self) -> None:
        quota = self.object("ResourceQuota", "starbase-system", "starbase-system")
        self.assertEqual(quota["spec"]["hard"]["requests.cpu"], "500m")
        self.assertEqual(quota["spec"]["hard"]["requests.memory"], "512Mi")
        self.assertEqual(quota["spec"]["hard"]["limits.cpu"], "3")
        self.assertEqual(quota["spec"]["hard"]["limits.memory"], "2Gi")

    def test_rc2_migration_retirement_evidence_is_complete_and_checksummed(self) -> None:
        checksum_lines = (
            (RC2_MIGRATION_EVIDENCE / "SHA256SUMS").read_text().splitlines()
        )
        checksums = {
            filename: digest
            for digest, filename in (line.split("  ", 1) for line in checksum_lines)
        }
        self.assertEqual(
            set(checksums),
            {
                "README.md",
                "core-job-status.json",
                "core.log",
                "gateway-job-status.json",
                "gateway-log-capture.json",
            },
        )
        for filename, expected_digest in checksums.items():
            content = (RC2_MIGRATION_EVIDENCE / filename).read_bytes()
            self.assertEqual(sha256(content).hexdigest(), expected_digest)

        core = json.loads(
            (RC2_MIGRATION_EVIDENCE / "core-job-status.json").read_text()
        )
        gateway = json.loads(
            (RC2_MIGRATION_EVIDENCE / "gateway-job-status.json").read_text()
        )
        for evidence in (core, gateway):
            self.assertEqual(evidence["job"]["succeeded"], 1)
            self.assertEqual(evidence["job"]["failed"], 0)
            self.assertEqual(evidence["pod"]["node"], "asio")
            self.assertEqual(evidence["pod"]["restart_count"], 0)
            self.assertEqual(evidence["pod"]["exit_code"], 0)
            self.assertIn(
                {"type": "Complete", "status": "True"},
                [
                    {"type": condition["type"], "status": condition["status"]}
                    for condition in evidence["job"]["conditions"]
                ],
            )

        core_log = (RC2_MIGRATION_EVIDENCE / "core.log").read_bytes()
        self.assertEqual(len(core_log), 132)
        self.assertEqual(core_log.count(b"\n"), 1)
        gateway_log = json.loads(
            (RC2_MIGRATION_EVIDENCE / "gateway-log-capture.json").read_text()
        )
        self.assertEqual(gateway_log["exit_status"], 0)
        self.assertEqual(gateway_log["bytes"], 0)
        self.assertEqual(gateway_log["lines"], 0)
        self.assertEqual(gateway_log["content"], [])

    def test_rc4_core_migration_evidence_is_complete_and_checksummed(self) -> None:
        checksum_lines = (
            (RC4_CORE_MIGRATION_EVIDENCE / "SHA256SUMS").read_text().splitlines()
        )
        checksums = {
            filename: digest
            for digest, filename in (line.split("  ", 1) for line in checksum_lines)
        }
        self.assertEqual(
            set(checksums),
            {"README.md", "execution-status.json", "events.json", "core.log"},
        )
        for filename, expected_digest in checksums.items():
            content = (RC4_CORE_MIGRATION_EVIDENCE / filename).read_bytes()
            self.assertEqual(sha256(content).hexdigest(), expected_digest)

        evidence = json.loads(
            (RC4_CORE_MIGRATION_EVIDENCE / "execution-status.json").read_text()
        )
        self.assertEqual(evidence["cluster"], "kubani")
        self.assertEqual(
            evidence["job"]["name"], "starbase-core-migrate-67c24a8df537"
        )
        self.assertFalse(evidence["job"]["suspend"])
        self.assertEqual(evidence["job"]["succeeded"], 1)
        self.assertEqual(evidence["job"]["failed"], 0)
        self.assertIn(
            {"type": "Complete", "status": "True"},
            [
                {"type": condition["type"], "status": condition["status"]}
                for condition in evidence["job"]["conditions"]
            ],
        )
        self.assertEqual(evidence["pod"]["node"], "asio")
        self.assertEqual(evidence["pod"]["phase"], "Succeeded")
        self.assertEqual(evidence["pod"]["restart_count"], 0)
        self.assertEqual(evidence["pod"]["exit_code"], 0)
        self.assertEqual(
            evidence["log_capture"],
            {"file": "core.log", "bytes": 132, "lines": 1},
        )

        events = json.loads(
            (RC4_CORE_MIGRATION_EVIDENCE / "events.json").read_text()
        )
        self.assertEqual(
            [event["reason"] for event in events["events"]],
            ["SuccessfulCreate", "Resumed", "Completed"],
        )

    def test_rc4_gateway_migration_evidence_is_complete_and_checksummed(self) -> None:
        checksum_lines = (
            (RC4_GATEWAY_MIGRATION_EVIDENCE / "SHA256SUMS").read_text().splitlines()
        )
        checksums = {
            filename: digest
            for digest, filename in (line.split("  ", 1) for line in checksum_lines)
        }
        self.assertEqual(
            set(checksums),
            {
                "README.md",
                "execution-status.json",
                "events.json",
                "gateway-log-capture.json",
            },
        )
        for filename, expected_digest in checksums.items():
            content = (RC4_GATEWAY_MIGRATION_EVIDENCE / filename).read_bytes()
            self.assertEqual(sha256(content).hexdigest(), expected_digest)

        evidence = json.loads(
            (RC4_GATEWAY_MIGRATION_EVIDENCE / "execution-status.json").read_text()
        )
        self.assertEqual(evidence["cluster"], "kubani")
        self.assertEqual(
            evidence["job"]["name"], "starbase-gateway-migrate-c5de66b03eaf"
        )
        self.assertFalse(evidence["job"]["suspend"])
        self.assertEqual(evidence["job"]["succeeded"], 1)
        self.assertEqual(evidence["job"]["failed"], 0)
        self.assertIn(
            {"type": "Complete", "status": "True"},
            [
                {"type": condition["type"], "status": condition["status"]}
                for condition in evidence["job"]["conditions"]
            ],
        )
        self.assertEqual(evidence["pod"]["node"], "asio")
        self.assertEqual(evidence["pod"]["phase"], "Succeeded")
        self.assertEqual(evidence["pod"]["restart_count"], 0)
        self.assertEqual(evidence["pod"]["exit_code"], 0)
        self.assertEqual(
            evidence["log_capture"],
            {
                "file": "gateway-log-capture.json",
                "exit_status": 0,
                "bytes": 0,
                "lines": 0,
            },
        )

        events = json.loads(
            (RC4_GATEWAY_MIGRATION_EVIDENCE / "events.json").read_text()
        )
        self.assertEqual(
            [event["reason"] for event in events["events"]],
            ["SuccessfulCreate", "Resumed", "Completed"],
        )
        log_capture = json.loads(
            (RC4_GATEWAY_MIGRATION_EVIDENCE / "gateway-log-capture.json").read_text()
        )
        self.assertEqual(log_capture["exit_status"], 0)
        self.assertEqual(log_capture["bytes"], 0)
        self.assertEqual(log_capture["lines"], 0)
        self.assertEqual(log_capture["content"], [])


if __name__ == "__main__":
    unittest.main()
