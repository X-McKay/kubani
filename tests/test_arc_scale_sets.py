"""The two ARC scale sets share one runner layout; each has its own job guard.

The runner executes the job-started hook with no arguments, before any step,
with only the GITHUB_* values it derives from the job. A non-zero exit fails
the job. These tests run the guard scripts as the runner would.
"""

import copy
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ARC = Path(__file__).resolve().parents[1] / "infrastructure/gitops/apps/arc-runners"
AGENTS = ARC / "scale-set-zetra-agents.yaml"
ZETRA = ARC / "scale-set-zetra.yaml"

ZETRA_WORKFLOW = "X-McKay/zetra/.github/workflows/platform-release.yml@refs/heads/main"
AGENTS_WORKFLOW = (
    "X-McKay/zetra-agents/.github/workflows/release.yml@refs/tags/demo/v1.2.3"
)


def load(path):
    return yaml.safe_load(path.read_text())


def template(path):
    return load(path)["spec"]["values"]["template"]["spec"]


def container(spec, name):
    return next(c for c in spec["containers"] if c["name"] == name)


def guard_script(configmap_file, name):
    docs = [d for d in yaml.safe_load_all(configmap_file.read_text()) if d]
    cm = next(d for d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == name)
    return cm["data"]["job-started.sh"]


def run_guard(script, **env):
    with tempfile.TemporaryDirectory() as directory:
        hook = Path(directory) / "job-started.sh"
        hook.write_text(script)
        hook.chmod(0o700)
        clean = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}
        clean.update(env)
        return subprocess.run(
            [str(hook)], env=clean, capture_output=True, text=True, timeout=10
        )


class ScaleSetParity(unittest.TestCase):
    def setUp(self):
        self.agents = load(AGENTS)
        self.zetra = load(ZETRA)

    def test_names_and_repositories(self):
        for doc, name, url in (
            (self.agents, "kubani-zetra-agents", "https://github.com/X-McKay/zetra-agents"),
            (self.zetra, "kubani-zetra", "https://github.com/X-McKay/zetra"),
        ):
            values = doc["spec"]["values"]
            self.assertEqual(doc["metadata"]["name"], name)
            self.assertEqual(values["runnerScaleSetName"], name)
            self.assertEqual(values["githubConfigUrl"], url)
            self.assertEqual(values["minRunners"], 0)
            self.assertEqual(values["githubConfigSecret"], "arc-github-app")

    def test_zetra_allows_one_runner(self):
        self.assertEqual(self.zetra["spec"]["values"]["maxRunners"], 1)
        self.assertEqual(self.agents["spec"]["values"]["maxRunners"], 2)

    def test_everything_but_the_known_differences_is_identical(self):
        a, z = copy.deepcopy(self.agents), copy.deepcopy(self.zetra)
        for doc in (a, z):
            values = doc["spec"]["values"]
            doc["metadata"].pop("name")
            for key in ("githubConfigUrl", "runnerScaleSetName", "maxRunners"):
                values.pop(key)
            spec = values["template"]["spec"]
            runner = container(spec, "runner")
            # The job guard ConfigMap is each scale set's own.
            next(v for v in spec["volumes"] if v["name"] == "job-guard").pop("configMap")
            if doc is z:
                # The registry login: a Secret volume, a scratch config
                # directory, and their two mounts on the runner container.
                spec["volumes"] = [
                    v
                    for v in spec["volumes"]
                    if v["name"] not in ("registry-push", "docker-config")
                ]
                runner["volumeMounts"] = [
                    m
                    for m in runner["volumeMounts"]
                    if m["name"] not in ("registry-push", "docker-config")
                ]
            # Comments are not data, so the images, MTU wrapper, resources,
            # security context, runtime class, placement, env and listener
            # must match exactly.
        self.assertEqual(a, z)

    def test_sandbox_and_placement_properties_hold_for_both(self):
        for name, path in (("agents", AGENTS), ("zetra", ZETRA)):
            with self.subTest(scale_set=name):
                values = load(path)["spec"]["values"]
                spec = values["template"]["spec"]
                self.assertEqual(spec["runtimeClassName"], "kata-qemu-runtime-rs")
                self.assertEqual(spec["nodeSelector"], {"topology.kubani.io/role": "platform"})
                dind = next(c for c in spec["initContainers"] if c["name"] == "dind")
                self.assertTrue(dind["securityContext"]["privileged"])
                self.assertEqual(dind["resources"]["limits"], {"memory": "12Gi"})
                runner = container(spec, "runner")
                self.assertEqual(runner["resources"]["limits"], {"memory": "4Gi"})
                for image in (runner["image"], dind["image"]):
                    self.assertIn("@sha256:", image)
                    self.assertTrue(image.startswith("registry.almckay.io/mirror/"))
                listener = values["listenerTemplate"]["spec"]
                self.assertTrue(listener["securityContext"]["runAsNonRoot"])
                lsc = listener["containers"][0]["securityContext"]
                self.assertFalse(lsc["allowPrivilegeEscalation"])
                self.assertTrue(lsc["readOnlyRootFilesystem"])
                self.assertEqual(lsc["capabilities"], {"drop": ["ALL"]})

    def test_each_scale_set_mounts_its_own_guard(self):
        for path, configmap in ((AGENTS, "runner-job-guard"), (ZETRA, "runner-job-guard-zetra")):
            with self.subTest(configmap=configmap):
                spec = template(path)
                volume = next(v for v in spec["volumes"] if v["name"] == "job-guard")
                self.assertEqual(volume["configMap"]["name"], configmap)
                self.assertEqual(volume["configMap"]["defaultMode"], 0o555)
                runner = container(spec, "runner")
                env = {e["name"]: e["value"] for e in runner["env"]}
                self.assertEqual(
                    env["ACTIONS_RUNNER_HOOK_JOB_STARTED"], "/home/runner/hooks/job-started.sh"
                )
                mount = next(m for m in runner["volumeMounts"] if m["name"] == "job-guard")
                self.assertEqual(mount["mountPath"], "/home/runner/hooks")
                self.assertTrue(mount["readOnly"])


class RegistryLogin(unittest.TestCase):
    def test_only_the_zetra_runner_container_holds_the_login(self):
        self.assertNotIn("registry-platform-push", AGENTS.read_text())
        spec = template(ZETRA)
        volume = next(v for v in spec["volumes"] if v["name"] == "registry-push")
        self.assertEqual(volume["secret"]["secretName"], "registry-platform-push")
        self.assertEqual(
            volume["secret"]["items"], [{"key": ".dockerconfigjson", "path": "config.json"}]
        )
        self.assertFalse(volume["secret"].get("optional", False))
        # Root owns the file and the runner user reads it, so a stricter
        # mode stops every release at its first step.
        self.assertEqual(volume["secret"]["defaultMode"], 0o444)
        holders = [
            c["name"]
            for c in spec["containers"] + spec["initContainers"]
            if any(m["name"] == "registry-push" for m in c.get("volumeMounts", []))
        ]
        self.assertEqual(holders, ["runner"])

    def test_the_login_is_one_read_only_file_in_a_writable_directory(self):
        runner = container(template(ZETRA), "runner")
        mounts = {m["name"]: m for m in runner["volumeMounts"]}
        directory, login = mounts["docker-config"], mounts["registry-push"]
        self.assertEqual(directory["mountPath"], "/home/runner/.docker")
        self.assertFalse(directory.get("readOnly", False))
        self.assertEqual(login["mountPath"], "/home/runner/.docker/config.json")
        self.assertEqual(login["subPath"], "config.json")
        self.assertTrue(login["readOnly"])
        volumes = {v["name"]: v for v in template(ZETRA)["volumes"]}
        self.assertEqual(volumes["docker-config"], {"name": "docker-config", "emptyDir": {}})

    def test_the_secret_is_built_with_the_scale_set_that_mounts_it(self):
        resources = load(ARC / "kustomization.yaml")["resources"]
        for name in (
            "scale-set-zetra.yaml",
            "job-guard-zetra.yaml",
            "registry-platform-push.enc.yaml",
        ):
            self.assertIn(name, resources)
            self.assertTrue((ARC / name).is_file(), name)

    def test_the_secret_file_is_the_object_the_volume_names(self):
        # Only what SOPS leaves readable is checked; the value stays encrypted.
        secret = load(ARC / "registry-platform-push.enc.yaml")
        volume = next(
            v for v in template(ZETRA)["volumes"] if v["name"] == "registry-push"
        )["secret"]
        self.assertEqual(secret["kind"], "Secret")
        self.assertEqual(secret["type"], "kubernetes.io/dockerconfigjson")
        self.assertEqual(
            secret["metadata"],
            {"name": volume["secretName"], "namespace": load(ZETRA)["metadata"]["namespace"]},
        )
        values = {**secret.get("data", {}), **secret.get("stringData", {})}
        self.assertEqual(list(values), [item["key"] for item in volume["items"]])
        for value in values.values():
            self.assertTrue(value.startswith("ENC["))
        self.assertTrue(secret["sops"]["age"])
        self.assertTrue(secret["sops"]["mac"])


class ZetraGuard(unittest.TestCase):
    script = guard_script(ARC / "job-guard-zetra.yaml", "runner-job-guard-zetra")
    allowed = {
        "GITHUB_REPOSITORY": "X-McKay/zetra",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": ZETRA_WORKFLOW,
    }

    def refused(self, **changes):
        result = run_guard(self.script, **{**self.allowed, **changes})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("::error title=kubani runner guard::", result.stdout)

    def test_admits_the_one_allowed_combination(self):
        result = run_guard(self.script, **self.allowed)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("admitted", result.stdout)

    def test_refuses_each_single_deviation(self):
        for label, changes in {
            "another repository": {"GITHUB_REPOSITORY": "X-McKay/zetra-agents"},
            "a fork-like name": {"GITHUB_REPOSITORY": "attacker/zetra"},
            "a different case": {"GITHUB_REPOSITORY": "x-mckay/zetra"},
            "pull_request": {"GITHUB_EVENT_NAME": "pull_request"},
            "pull_request_target": {"GITHUB_EVENT_NAME": "pull_request_target"},
            "workflow_dispatch": {"GITHUB_EVENT_NAME": "workflow_dispatch"},
            "a tag ref": {"GITHUB_REF": "refs/tags/platform/v1"},
            "another branch": {"GITHUB_REF": "refs/heads/feature"},
            "a branch that extends main": {"GITHUB_REF": "refs/heads/main2"},
            "a pull ref": {"GITHUB_REF": "refs/pull/1/merge"},
            "another workflow file": {
                "GITHUB_WORKFLOW_REF": "X-McKay/zetra/.github/workflows/other.yml@refs/heads/main"
            },
            "the right workflow at another ref": {
                "GITHUB_WORKFLOW_REF": "X-McKay/zetra/.github/workflows/platform-release.yml@refs/heads/feature"
            },
            "the right workflow at a tag": {
                "GITHUB_WORKFLOW_REF": "X-McKay/zetra/.github/workflows/platform-release.yml@refs/tags/v1"
            },
            "the workflow of another repository": {
                "GITHUB_WORKFLOW_REF": "X-McKay/zetra-agents/.github/workflows/platform-release.yml@refs/heads/main"
            },
            "a workflow reference with a suffix": {"GITHUB_WORKFLOW_REF": ZETRA_WORKFLOW + "x"},
        }.items():
            with self.subTest(label):
                self.refused(**changes)

    def test_refuses_when_a_value_is_missing_or_empty(self):
        for key in self.allowed:
            with self.subTest(key=key, how="empty"):
                self.refused(**{key: ""})
            with self.subTest(key=key, how="unset"):
                env = {k: v for k, v in self.allowed.items() if k != key}
                result = run_guard(self.script, **env)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_refuses_the_zetra_agents_release_shape(self):
        self.refused(
            GITHUB_REPOSITORY="X-McKay/zetra-agents",
            GITHUB_REF="refs/tags/demo/v1.2.3",
            GITHUB_WORKFLOW_REF=AGENTS_WORKFLOW,
        )


class ZetraAgentsGuard(unittest.TestCase):
    script = guard_script(ARC / "job-guard.yaml", "runner-job-guard")
    allowed = {
        "GITHUB_REPOSITORY": "X-McKay/zetra-agents",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/tags/demo/v1.2.3",
        "GITHUB_WORKFLOW_REF": AGENTS_WORKFLOW,
    }

    def test_still_admits_a_release_tag_push(self):
        for ref in ("refs/tags/demo/v1.2.3", "refs/tags/a-b/v0.1.0+rc.1"):
            with self.subTest(ref=ref):
                env = {
                    **self.allowed,
                    "GITHUB_REF": ref,
                    "GITHUB_WORKFLOW_REF": f"X-McKay/zetra-agents/.github/workflows/release.yml@{ref}",
                }
                result = run_guard(self.script, **env)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_still_refuses_a_zetra_platform_job(self):
        result = run_guard(
            self.script,
            GITHUB_REPOSITORY="X-McKay/zetra",
            GITHUB_EVENT_NAME="push",
            GITHUB_REF="refs/heads/main",
            GITHUB_WORKFLOW_REF=ZETRA_WORKFLOW,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_still_refuses_deviations(self):
        for label, changes in {
            "pull_request": {"GITHUB_EVENT_NAME": "pull_request"},
            "main branch": {
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_WORKFLOW_REF": "X-McKay/zetra-agents/.github/workflows/release.yml@refs/heads/main",
            },
            "another workflow": {
                "GITHUB_WORKFLOW_REF": "X-McKay/zetra-agents/.github/workflows/ci.yml@refs/tags/demo/v1.2.3"
            },
        }.items():
            with self.subTest(label):
                result = run_guard(self.script, **{**self.allowed, **changes})
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
