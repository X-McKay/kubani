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
    "sha256:e70596ab4514f64714307e223d4a2b2d74ebc535e56af5b6e7891c42ea4b9c4b"
)
PREVIOUS_WEB_DIGEST = (
    "sha256:6e237e10d23e4cce4b9aaf8bdd40f4ed6f9230d1275b8dbd5702a36b75bb40a0"
)
PREVIOUS_KUBANI_REVISION = (
    "822089bc86b1b11dd424b3a382d4c6c214b3205e"  # pragma: allowlist secret
)
RELEASE = "0.1.0-rc.11"
SOURCE_REVISION = "5ffa445a21796c8d745197186fbf348f056893e4"  # pragma: allowlist secret
RELEASE_MANIFEST_DIGEST = (
    "sha256:4c26e778b72a81ea89af0a505c59f24cbef2a8adb302a791f937231ef1e38ae8"
)
RELEASE_IMAGES = {
    "core": "ghcr.io/x-mckay/starbase/core@sha256:008327ad0083c0b94f13d6b6fb7cdcc9c7e588f739737e23dacc1f2af0c7db44",
    "web": "ghcr.io/x-mckay/starbase/web@sha256:2cbd3de603bcf62b6ef9e9415849aca06e6ccf79ebf29ef7e13cf99c0c85ae25",
    "github-connector": "ghcr.io/x-mckay/starbase/github-connector@sha256:f848bd161dcaddd4afb74f9dfed7a86d3447c5ce300bd4aa45d725e5bfad67f6",
    "kubernetes-connector": "ghcr.io/x-mckay/starbase/kubernetes-connector@sha256:96239515e2e7eaffdb8beda1afa670b27e8cac16f6fa2c1d7f847e9a10eae0e1",
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

    def test_autonomous_stage_is_live_and_inherits_the_accepted_reader(self) -> None:
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
            "2026-09-04T19:05:57Z",
        )


if __name__ == "__main__":
    unittest.main()
