"""Inactive worker manifests preserve legacy isolation and fail closed on pins."""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infrastructure/scripts/ops/render-worker-versions.py"
spec = importlib.util.spec_from_file_location("render_worker_versions", SCRIPT)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)
IMAGE = "registry.almckay.io/platform/session-runner@sha256:" + "a" * 64
COMMIT = "b" * 40


def test_render_is_inactive_disjoint_and_keeps_legacy_artifacts(tmp_path):
    out = tmp_path / "rendered"
    renderer.render(IMAGE, COMMIT, out)
    for role, legacy_file in [
        ("sessions", "session-runner-tenant-test.yaml"),
        ("cleanup", "cleanup-reconciler.yaml"),
    ]:
        dep = yaml.safe_load((out / f"{role}.yaml").read_text())
        labels = dep["spec"]["selector"]["matchLabels"]
        legacy = next(
            v
            for v in yaml.safe_load_all(
                (
                    ROOT
                    / "infrastructure/gitops/apps/agent-platform/workloads"
                    / legacy_file
                ).read_text()
            )
            if v.get("kind") == "Deployment"
        )
        assert dep["spec"]["replicas"] == 0
        assert dep["metadata"]["name"] != legacy["metadata"]["name"]
        assert not all(
            dep["spec"]["template"]["metadata"]["labels"].get(k) == v
            for k, v in legacy["spec"]["selector"]["matchLabels"].items()
        )
        assert labels["agentplatform.io/worker-role"] == role
        assert labels["agentplatform.io/worker-pool"] == "governed-v1"
        assert labels.items() <= dep["spec"]["template"]["metadata"]["labels"].items()
        pod = dep["spec"]["template"]["spec"]
        assert (
            pod["serviceAccountName"]
            == legacy["spec"]["template"]["spec"]["serviceAccountName"]
        )
        assert pod["containers"][0]["image"] == IMAGE
        assert pod["terminationGracePeriodSeconds"] == 60
        assert pod["volumes"] == legacy["spec"]["template"]["spec"]["volumes"]
        if role == "sessions":
            affinity = pod["affinity"]["podAffinity"][
                "requiredDuringSchedulingIgnoredDuringExecution"
            ][0]
            assert affinity["topologyKey"] == "kubernetes.io/hostname"
            assert (
                affinity["labelSelector"]["matchLabels"]
                == legacy["spec"]["selector"]["matchLabels"]
            )
    policies = list(yaml.safe_load_all((out / "netpol.yaml").read_text()))
    assert len(policies) == 6
    for policy in policies:
        source = policy["spec"]
        if "egress" in source:
            selector = source["podSelector"]["matchLabels"]
        else:
            selector = source["ingress"][0]["from"][0]["podSelector"]["matchLabels"]
        assert selector["agentplatform.io/tenant"] == "tenant-test"
        assert selector["agentplatform.io/worker-pool"] == "governed-v1"
        assert selector["agentplatform.io/worker-role"] in {"sessions", "cleanup"}


@pytest.mark.parametrize(
    "image,commit",
    [
        ("session-runner:latest", COMMIT),
        (IMAGE, "short"),
        ("registry.almckay.io/platform/session-runner@sha256:" + "0" * 64, COMMIT),
    ],
)
def test_missing_or_invalid_release_pin_never_creates_output(tmp_path, image, commit):
    with pytest.raises(ValueError):
        renderer.render(image, commit, tmp_path / "rendered")
    assert not (tmp_path / "rendered").exists()


def test_renderer_never_overwrites_existing_output(tmp_path):
    out = tmp_path / "rendered"
    out.mkdir()
    (out / "keep").write_text("original")
    with pytest.raises(FileExistsError):
        renderer.render(IMAGE, COMMIT, out)
    assert (out / "keep").read_text() == "original"


def test_inactive_templates_are_not_referenced_by_active_kustomizations():
    for path in (ROOT / "infrastructure/gitops").rglob("kustomization.yaml"):
        assert "worker-versions" not in path.read_text()
