"""Concrete A/B candidates retain exact pins, disjoint selectors and legacy workers."""

from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
AP = ROOT / "infrastructure/gitops/apps/agent-platform"
STAGE = AP / "workloads/governed-workers"
PINS = {
    "a": (
        "9c2c0928b22647f8475a163cda74be84bc80e91d",
        "registry.almckay.io/platform/session-runner:9c2c092@sha256:d6a785a6b94af6bcb95e34954db3b84bcaf370ac5ff28cdef2efb5fbc57f6e52",
    ),
    "b": (
        "b2f4d578cb724e04a60114bc3a8d714656434841",
        "registry.almckay.io/platform/session-runner:b2f4d57@sha256:4a443f97c33bfa95303787b517558d8d1e4375d8d92f27682722485154bc64e1",
    ),
}


def load(path):
    return yaml.safe_load(path.read_text())


def test_all_four_retained_candidates_have_one_replica_and_exact_verified_config():
    for variant, (commit, image) in PINS.items():
        build = "b-" + commit[:12]
        for role, prefix in [
            ("sessions", "session-runner"),
            ("cleanup", "cleanup-reconciler"),
        ]:
            dep = load(STAGE / f"{role}-{variant}.yaml")
            assert dep["kind"] == "Deployment" and dep["spec"]["replicas"] == 1
            assert dep["metadata"]["namespace"] == "agent-platform"
            assert (
                dep["metadata"]["annotations"]["agentplatform.io/source-commit"]
                == commit
            )
            assert (
                dep["metadata"]["name"] == f"{prefix}-tenant-test-governed-v1-{build}"
            )
            assert len(dep["metadata"]["name"]) <= 63
            spec = dep["spec"]["template"]["spec"]
            container = spec["containers"][0]
            assert container["image"] == image
            env = {e["name"]: e.get("value") for e in container["env"]}
            assert env["WORKER_POOL"] == "governed-v1"
            assert env["WORKER_BUILD_ID"] == build
            assert env["WORKER_DEPLOYMENT"] == f"{prefix}-tenant-test-governed-v1"
            assert spec["serviceAccountName"] == prefix
            assert spec["terminationGracePeriodSeconds"] == 60


def test_new_selectors_are_pairwise_disjoint_and_not_selected_by_either_legacy_deployment():
    staged = [
        load(STAGE / f"{r}-{v}.yaml") for r in ["sessions", "cleanup"] for v in PINS
    ]
    legacy = [
        next(
            d
            for d in yaml.safe_load_all((AP / "workloads" / name).read_text())
            if d.get("kind") == "Deployment"
        )
        for name in ["session-runner-tenant-test.yaml", "cleanup-reconciler.yaml"]
    ]
    for i, dep in enumerate(staged):
        own = dep["spec"]["template"]["metadata"]["labels"]
        assert dep["spec"]["selector"]["matchLabels"].items() <= own.items()
        for other in staged[:i] + staged[i + 1 :] + legacy:
            assert not other["spec"]["selector"]["matchLabels"].items() <= own.items()


def test_shared_policies_referenced_once_and_no_operator_job_in_flux_stage():
    refs = load(AP / "kustomization.yaml")["resources"]
    assert refs.count("netpol-governed-workers.yaml") == 1
    policies = list(
        yaml.safe_load_all((AP / "netpol-governed-workers.yaml").read_text())
    )
    assert len(policies) == 6
    assert (
        len({(p["metadata"]["namespace"], p["metadata"]["name"]) for p in policies})
        == 6
    )
    refs = load(STAGE / "kustomization.yaml")["resources"]
    assert set(refs) == {
        "sessions-a.yaml",
        "cleanup-a.yaml",
        "sessions-b.yaml",
        "cleanup-b.yaml",
    }
    assert all(load(STAGE / r)["kind"] == "Deployment" for r in refs)
    assert (
        load(AP / "workloads/kustomization.yaml")["resources"].count("governed-workers")
        == 1
    )


def test_rwo_storage_projects_existing_artifacts_and_colocates_with_retained_legacy():
    for variant in PINS:
        pod = load(STAGE / f"sessions-{variant}.yaml")["spec"]["template"]["spec"]
        artifacts = next(v for v in pod["volumes"] if v["name"] == "artifacts")
        assert (
            artifacts["persistentVolumeClaim"]["claimName"]
            == "agent-artifacts-tenant-test"
        )
        affinity = pod["affinity"]["podAffinity"][
            "requiredDuringSchedulingIgnoredDuringExecution"
        ][0]
        assert affinity["topologyKey"] == "kubernetes.io/hostname"
        assert affinity["labelSelector"]["matchLabels"] == {
            "app.kubernetes.io/name": "session-runner",
            "agentplatform.io/tenant": "tenant-test",
        }
