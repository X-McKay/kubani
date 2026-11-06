"""The operator can restore after an uncertain PATCH; the harness has no write rights."""

import copy
import importlib.util
import json
from pathlib import Path

import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).parents[1] / "infrastructure/scripts/ops/t17_aps_outage.py"
spec = importlib.util.spec_from_file_location("t17_operator", PATH)
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


def deployment():
    return {
        "metadata": {
            "uid": "aps-uid",
            "resourceVersion": "1",
            "generation": 1,
            "annotations": {"keep": "value"},
        },
        "spec": {"replicas": 2, "template": {"image": "same"}},
        "status": {"observedGeneration": 1, "readyReplicas": 2, "availableReplicas": 2},
    }


class FakeAPI:
    def __init__(self):
        self.dep = deployment()
        self.cm = None
        self.calls = []
        self.fail_once = False

    def get(self, resource, name, namespace=operator.NAMESPACE, optional=False):
        return copy.deepcopy(self.cm if resource == "configmap" else self.dep)

    def create(self, obj):
        assert self.cm is None
        self.cm = copy.deepcopy(obj)
        self.cm["metadata"].update(uid="cm-uid", resourceVersion="10")
        return copy.deepcopy(self.cm)

    def patch(self, resource, name, patch, namespace=operator.NAMESPACE):
        self.calls.append((resource, copy.deepcopy(patch)))
        obj = self.cm if resource == "configmap" else self.dep
        for p in patch:
            if p["op"] == "test":
                fields = p["path"].split("/")[1:]
                actual = obj
                for f in fields:
                    actual = actual[f.replace("~1", "/").replace("~0", "~")]
                assert actual == p["value"]
        for p in patch:
            if p["op"] == "test":
                continue
            fields = p["path"].split("/")[1:]
            target = obj
            for f in fields[:-1]:
                target = target[f.replace("~1", "/").replace("~0", "~")]
            key = fields[-1].replace("~1", "/").replace("~0", "~")
            if p["op"] == "remove":
                target.pop(key)
            else:
                target[key] = copy.deepcopy(p["value"])
            if p["path"] == "/spec/replicas":
                obj["metadata"]["generation"] += 1
        obj["metadata"]["resourceVersion"] = str(
            int(obj["metadata"]["resourceVersion"]) + 1
        )
        if (
            self.fail_once
            and resource == "deployment"
            and self.dep["spec"]["replicas"] == 0
        ):
            self.fail_once = False
            raise RuntimeError("response lost after write")
        return copy.deepcopy(obj)


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tmp = Path(self.directory.name)

    def test_stale_temporary_save_does_not_block_recovery(self):
        path = self.tmp / "state.json"
        stale = self.tmp / "state.json.tmp"
        stale.write_text("interrupted prior write")
        operator.save(path, {"restored": True})
        self.assertEqual(json.loads(path.read_text()), {"restored": True})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(stale.read_text(), "interrupted prior write")

    def test_prepare_is_fresh_and_records_exact_restore_state(self):
        api = FakeAPI()
        state = operator.prepare(api, "a" * 16, self.tmp / "state.json")
        self.assertEqual(api.dep, deployment())
        self.assertEqual(state["deployment_uid"], "aps-uid")
        self.assertEqual(state["original_replicas"], 2)
        self.assertIsNone(state["original_annotation"])
        self.assertEqual((self.tmp / "state.json").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            operator.prepare(api, "b" * 16, self.tmp / "other.json")

    def test_restore_reinstates_exact_replicas_and_annotation(self):
        for annotation in (None, "enabled", "disabled"):
            with self.subTest(annotation=annotation):
                api = FakeAPI()
                if annotation is not None:
                    api.dep["metadata"]["annotations"][operator.RECONCILE] = annotation
                path = self.tmp / str(annotation)
                state = operator.prepare(api, "a" * 16, path)
                operator.pause(api, state)
                operator.scale(api, state, 0, "down", path)
                self.assertEqual(api.dep["spec"]["replicas"], 0)
                operator.restore(api, state, path)
                self.assertEqual(api.dep["spec"]["replicas"], 2)
                self.assertEqual(
                    api.dep["metadata"]["annotations"].get(operator.RECONCILE),
                    annotation,
                )
                self.assertEqual(api.dep["metadata"]["annotations"]["keep"], "value")
                for _, operations in api.calls:
                    self.assertEqual(
                        [p["path"] for p in operations[:2]],
                        ["/metadata/uid", "/metadata/resourceVersion"],
                    )

    def test_lost_scale_response_still_restores(self):
        api, path = FakeAPI(), self.tmp / "state"
        state = operator.prepare(api, "a" * 16, path)
        operator.pause(api, state)
        api.fail_once = True
        with self.assertRaises(RuntimeError):
            operator.scale(api, state, 0, "down", path)
        self.assertEqual(api.dep["spec"]["replicas"], 0)
        operator.restore(api, state, path)
        self.assertEqual(api.dep["spec"]["replicas"], 2)
        self.assertNotIn(operator.RECONCILE, api.dep["metadata"]["annotations"])
        self.assertTrue(state["restored"])

    def test_concurrent_change_is_not_overwritten(self):
        for change in ("uid", "spec", "replicas", "annotation", "receipt_uid"):
            with self.subTest(change=change):
                api, path = FakeAPI(), self.tmp / change
                state = operator.prepare(api, "a" * 16, path)
                operator.pause(api, state)
                if change == "uid":
                    api.dep["metadata"]["uid"] = "replacement"
                elif change == "spec":
                    api.dep["spec"]["template"]["image"] = "other"
                elif change == "replicas":
                    api.dep["spec"]["replicas"] = 3
                elif change == "annotation":
                    api.dep["metadata"]["annotations"][operator.RECONCILE] = "other"
                else:
                    api.cm["metadata"]["uid"] = "replacement"
                before = copy.deepcopy(api.dep)
                with self.assertRaises(ValueError):
                    operator.scale(api, state, 0, "down", path)
                self.assertEqual(api.dep, before)

    def test_failure_or_interrupt_during_outage_restores_in_finally(self):
        for failure in (TimeoutError("missing zero evidence"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                api, path = FakeAPI(), self.tmp / type(failure).__name__
                state = operator.prepare(api, "a" * 16, path)

                def phase(api, state, job, phase, timeout):
                    if phase == "zero_confirmed_restore_now":
                        raise failure

                with patch.object(operator, "wait_phase", phase):
                    with self.assertRaises(type(failure)):
                        operator.run(api, state, path, "job")
                self.assertEqual(api.dep["spec"]["replicas"], 2)
                self.assertNotIn(operator.RECONCILE, api.dep["metadata"]["annotations"])
                self.assertTrue(state["restored"])

    def test_missing_receipt_does_not_block_replica_and_flux_restoration(self):
        api, path = FakeAPI(), self.tmp / "state"
        state = operator.prepare(api, "a" * 16, path)
        operator.pause(api, state)
        operator.scale(api, state, 0, "down", path)
        api.cm["metadata"]["uid"] = "replacement"
        with self.assertRaises(ValueError):
            operator.restore(api, state, path)
        self.assertEqual(api.dep["spec"]["replicas"], 2)
        self.assertNotIn(operator.RECONCILE, api.dep["metadata"]["annotations"])
        self.assertTrue(state["restored"])

    def test_failed_replica_restore_still_attempts_flux_restore(self):
        api, path = FakeAPI(), self.tmp / "state"
        state = operator.prepare(api, "a" * 16, path)
        operator.pause(api, state)
        operator.scale(api, state, 0, "down", path)
        original = api.patch

        def fail_scale(resource, name, operations, namespace=operator.NAMESPACE):
            if any(
                p["path"] == "/spec/replicas"
                and p.get("value") == 2
                and p["op"] == "replace"
                for p in operations
            ):
                raise RuntimeError("unavailable")
            return original(resource, name, operations, namespace)

        api.patch = fail_scale
        with self.assertRaises(RuntimeError):
            operator.restore(api, state, path)
        self.assertNotIn(operator.RECONCILE, api.dep["metadata"]["annotations"])
        self.assertFalse(state["restored"])

    def test_phase_requires_pod_owned_by_pinned_job(self):
        marker = "a" * 16
        state = {"marker": marker}
        api = FakeAPI()
        api.get = lambda *args, **kwargs: {
            "metadata": {"uid": "job-uid"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "args": ["--tests", "T17"],
                                "env": [{"name": "APS_OUTAGE_MARKER", "value": marker}],
                            }
                        ]
                    }
                }
            },
        }
        pod = {
            "metadata": {
                "uid": "pod-uid",
                "name": "pod",
                "ownerReferences": [
                    {"uid": "wrong-job", "kind": "Job", "controller": True}
                ],
            },
            "status": {"phase": "Running"},
        }

        def command(args):
            if args[0] == "get":
                return json.dumps({"items": [pod]})
            return json.dumps(
                {"test": "T17", "marker": marker, "phase": "baseline_ready"}
            )

        api.command = command
        with self.assertRaises(ValueError):
            operator.wait_phase(api, state, "job", "baseline_ready", 1)
        pod["metadata"]["ownerReferences"][0]["uid"] = "job-uid"
        operator.wait_phase(api, state, "job", "baseline_ready", 1)


if __name__ == "__main__":
    unittest.main()
