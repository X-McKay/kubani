from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "infrastructure/gitops/apps/starbase-phase10-autonomous-reader-prepared"
ACTIVATION = ROOT / "infrastructure/gitops/apps/starbase-phase10-autonomous-crew-prepared"
FOUNDATION_FLUX = ROOT / "infrastructure/gitops/flux-system/starbase-foundation-kustomization.yaml"
PREVIOUS_CORE_DIGEST = (
    "sha256:e17f0c1531d32995473dc72a7e717ce8e06a525fc22c563c94e9b7e66bab71b1"
)
PREVIOUS_WEB_DIGEST = (
    "sha256:bab74851a342539d20d959f18e381499d0841b86b9b454ec11e1aac29b37df15"
)
PREVIOUS_KUBANI_REVISION = (
    "8dafebf1f03f069643d4f3d30c173f70e7ccb2a7"  # pragma: allowlist secret
)
RELEASE = "0.1.0-rc.14"
SOURCE_REVISION = "61ad6ccf06418bc9cee5c48f45823fe3131baa7b"  # pragma: allowlist secret
RELEASE_MANIFEST_DIGEST = (
    "sha256:2c3745639a84269e1deb7731bdf62752a5aceae384b6447e9a20d07d77a02896"
)
RELEASE_IMAGES = {
    "core": "ghcr.io/x-mckay/starbase/core@sha256:e16df3b47487905b5aec917b848047fb8c05d0ab80810aa7c314e05ba25c4178",
    "web": "ghcr.io/x-mckay/starbase/web@sha256:86e5734b0bc9d93cff010858ef8507651d3123db91d6472a6533c1b0c4559609",
    "github-connector": "ghcr.io/x-mckay/starbase/github-connector@sha256:7f93b762aa9dddb268e380cd70c2f240f736cb87fdb147474be9885f4f6f5037",
    "kubernetes-connector": "ghcr.io/x-mckay/starbase/kubernetes-connector@sha256:53382049eabb3ee91d99b2be1648ef2bbb8ec2d042611d7d34936e7726831753",
}


def render(path: Path) -> list[dict]:
    content = subprocess.run(
        ["kubectl", "kustomize", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [document for document in yaml.safe_load_all(content) if document]


class StarbasePhase10AutonomousCrewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reader = render(READER)
        cls.activation = render(ACTIVATION)
        cls.reader_by_identity = cls.index(cls.reader)
        cls.activation_by_identity = cls.index(cls.activation)

    @staticmethod
    def index(documents: list[dict]) -> dict[tuple[str, str, str], dict]:
        return {
            (
                document["kind"],
                document.get("metadata", {}).get("namespace", ""),
                document["metadata"]["name"],
            ): document
            for document in documents
        }

    @staticmethod
    def object(
        index: dict[tuple[str, str, str], dict], kind: str, namespace: str, name: str
    ) -> dict:
        return index[(kind, namespace, name)]

    @staticmethod
    def core_container(deployment: dict) -> dict:
        return next(
            container
            for container in deployment["spec"]["template"]["spec"]["containers"]
            if container["name"] == "core"
        )

    def test_autonomous_overlay_is_live_after_reader_stage(self) -> None:
        reader = yaml.safe_load((READER / "kustomization.yaml").read_text())
        activation = yaml.safe_load((ACTIVATION / "kustomization.yaml").read_text())
        flux = yaml.safe_load(FOUNDATION_FLUX.read_text())
        self.assertIn("../starbase-phase9-foundation", reader["resources"])
        self.assertIn("../starbase-phase10-autonomous-reader-prepared", activation["resources"])
        self.assertEqual(
            flux["spec"]["path"],
            "./infrastructure/gitops/apps/starbase-phase10-autonomous-crew-prepared",
        )

    def test_reader_stage_is_compatible_disabled_and_reversible(self) -> None:
        config = self.object(
            self.reader_by_identity, "ConfigMap", "starbase-system", "starbase-runtime"
        )["data"]
        self.assertEqual(config["STARBASE_BOUNTY_AUTOMATION_ENABLED"], "false")
        self.assertEqual(config["STARBASE_BOUNTY_AUTOMATION_DISPATCH_ENABLED"], "false")
        self.assertNotIn("STARBASE_TEMPORAL_MODE", config)
        self.assertNotIn("STARBASE_BOUNTY_MODEL_ENDPOINT", config)

        core = self.object(
            self.reader_by_identity, "Deployment", "starbase-system", "starbase-core"
        )
        self.assertEqual(core["spec"]["strategy"], {"type": "Recreate"})
        labels = core["spec"]["template"]["metadata"]["labels"]
        self.assertEqual(labels["starbase.io/temporal-client"], "false")
        self.assertEqual(labels["starbase.io/external-authority"], "false")
        annotations = core["spec"]["template"]["metadata"]["annotations"]
        self.assertEqual(annotations["starbase.io/rollback-core-digest"], PREVIOUS_CORE_DIGEST)
        self.assertEqual(annotations["starbase.io/rollback-web-digest"], PREVIOUS_WEB_DIGEST)
        self.assertEqual(
            annotations["starbase.io/rollback-kubani-revision"],
            PREVIOUS_KUBANI_REVISION,
        )
        self.assertEqual(annotations["starbase.io/activation-stage"], "phase10-autonomous-reader-prepared")
        self.assertEqual(annotations["starbase.io/release"], RELEASE)
        self.assertEqual(annotations["starbase.io/source-revision"], SOURCE_REVISION)
        self.assertEqual(
            annotations["starbase.io/release-manifest-digest"],
            RELEASE_MANIFEST_DIGEST,
        )
        containers = {
            container["name"]: container["image"]
            for container in core["spec"]["template"]["spec"]["containers"]
        }
        self.assertEqual(containers["core"], RELEASE_IMAGES["core"])
        self.assertEqual(containers["web"], RELEASE_IMAGES["web"])

        expected_strategies = {
            "starbase-preview-fixture": {"type": "Recreate"},
            "starbase-github-connector": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1},
            },
            "starbase-kubernetes-connector": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1},
            },
        }
        for deployment_name, image_name in (
            ("starbase-preview-fixture", "github-connector"),
            ("starbase-github-connector", "github-connector"),
            ("starbase-kubernetes-connector", "kubernetes-connector"),
        ):
            deployment = self.object(
                self.reader_by_identity,
                "Deployment",
                "starbase-connectors",
                deployment_name,
            )
            deployment_annotations = deployment["spec"]["template"]["metadata"]["annotations"]
            self.assertEqual(
                deployment["spec"]["strategy"], expected_strategies[deployment_name]
            )
            self.assertEqual(deployment_annotations["starbase.io/release"], RELEASE)
            self.assertEqual(
                deployment_annotations["starbase.io/source-revision"],
                SOURCE_REVISION,
            )
            self.assertEqual(
                deployment["spec"]["template"]["spec"]["containers"][0]["image"],
                RELEASE_IMAGES[image_name],
            )

    def test_activation_sets_exact_bounded_runtime_contract(self) -> None:
        config = self.object(
            self.activation_by_identity, "ConfigMap", "starbase-system", "starbase-runtime"
        )["data"]
        expected = {
            "STARBASE_BOUNTY_AUTOMATION_ENABLED": "true",
            "STARBASE_BOUNTY_AUTOMATION_DISPATCH_ENABLED": "true",
            "STARBASE_TEMPORAL_MODE": "kubani-internal-preproduction",
            "STARBASE_TEMPORAL_ADDRESS": "temporal-frontend.temporal.svc.cluster.local:7233",
            "STARBASE_TEMPORAL_NAMESPACE": "default",
            "STARBASE_TEMPORAL_IDENTITY": "starbase-autonomous-core",
            "STARBASE_TEMPORAL_INTERNAL_ACK": "adr-0016",
            "STARBASE_BOUNTY_MODEL_ENDPOINT": "https://llm-fast.almckay.io/v1/chat/completions",
            "STARBASE_BOUNTY_MODEL_ALLOWED_HOSTS": "llm-fast.almckay.io",
            "STARBASE_BOUNTY_MODEL": "Qwen/Qwen3.5-0.8B",
            "STARBASE_MISSION_SANDBOX_ENVIRONMENT_DIGEST": (
                "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            ),
        }
        for name, value in expected.items():
            self.assertEqual(config[name], value)
        self.assertEqual(config["STARBASE_MUTATION_ENABLED"], "false")
        self.assertNotIn("STARBASE_BOUNTY_MODEL_TOKEN", config)
        self.assertNotIn("STARBASE_BOUNTY_MODEL_ALLOW_PLAINTEXT_LOOPBACK", config)

        core = self.object(
            self.activation_by_identity, "Deployment", "starbase-system", "starbase-core"
        )
        labels = core["spec"]["template"]["metadata"]["labels"]
        self.assertEqual(labels["starbase.io/temporal-client"], "true")
        self.assertEqual(labels["starbase.io/external-authority"], "false")
        annotations = core["spec"]["template"]["metadata"]["annotations"]
        self.assertEqual(
            annotations["starbase.io/autonomous-runtime-revision"],
            "dispatch-enabled-v1",
        )
        self.assertFalse(core["spec"]["template"]["spec"]["automountServiceAccountToken"])

    def test_activation_opens_only_the_required_temporal_and_https_paths(self) -> None:
        source = self.object(
            self.activation_by_identity,
            "NetworkPolicy",
            "starbase-system",
            "allow-core-to-bounty-temporal",
        )
        self.assertEqual(
            source["spec"]["podSelector"]["matchLabels"],
            {
                "app.kubernetes.io/name": "starbase-core",
                "starbase.io/temporal-client": "true",
            },
        )
        self.assertEqual(source["spec"]["egress"][0]["ports"], [{"protocol": "TCP", "port": 7233}])
        self.assertEqual(
            source["spec"]["egress"][0]["to"][0]["namespaceSelector"]["matchLabels"],
            {"kubernetes.io/metadata.name": "temporal"},
        )

        destination = self.object(
            self.activation_by_identity,
            "NetworkPolicy",
            "temporal",
            "allow-starbase-core-bounty-ingress",
        )
        self.assertEqual(destination["spec"]["ingress"][0]["ports"], [{"protocol": "TCP", "port": 7233}])
        peer = destination["spec"]["ingress"][0]["from"][0]
        self.assertEqual(
            peer["namespaceSelector"]["matchLabels"],
            {"kubernetes.io/metadata.name": "starbase-system"},
        )
        self.assertEqual(
            peer["podSelector"]["matchLabels"],
            {
                "app.kubernetes.io/name": "starbase-core",
                "starbase.io/temporal-client": "true",
            },
        )

        model = self.object(
            self.activation_by_identity,
            "NetworkPolicy",
            "starbase-system",
            "allow-core-to-bounty-model-https",
        )
        rule = model["spec"]["egress"][0]
        self.assertEqual(rule["ports"], [{"protocol": "TCP", "port": 443}])
        self.assertEqual(
            {peer["ipBlock"]["cidr"] for peer in rule["to"]},
            {"100.71.65.62/32", "100.76.45.84/32", "100.77.107.81/32", "100.92.107.71/32"},
        )
        self.assertEqual(
            model["metadata"]["annotations"]["starbase.io/revalidate-before-activation"],
            "true",
        )
        self.assertEqual(
            model["metadata"]["annotations"]["starbase.io/endpoint-observed-at"],
            "2026-09-05T07:19:24Z",
        )


if __name__ == "__main__":
    unittest.main()
