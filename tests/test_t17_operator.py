"""The operator can restore after an uncertain PATCH; the harness has no write rights."""

import copy
import importlib.util
import json
from pathlib import Path

import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path(__file__).parents[1] / "infrastructure/scripts/ops/t17_aps_outage.py"
spec = importlib.util.spec_from_file_location("t17_operator", PATH)
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


CONFLICT = (
    "Error from server (Conflict): Operation cannot be fulfilled on "
    'deployments.apps "agent-policy-service": the object has been modified; '
    "please apply your changes to the latest version and try again"
)
INVALID = "The request is invalid: the server rejected our request due to an error in our request"


def server_failure(stderr):
    with patch.object(
        operator.subprocess,
        "run",
        return_value=SimpleNamespace(returncode=1, stdout="", stderr=stderr),
    ):
        try:
            operator.API("/not-used").command(
                ["patch", "deployment", operator.DEPLOYMENT]
            )
        except RuntimeError as error:
            return error
    raise AssertionError("API failure was swallowed")


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
        stored = self.cm if resource == "configmap" else self.dep
        obj = copy.deepcopy(stored)
        for p in patch:
            if p["op"] == "test":
                fields = p["path"].split("/")[1:]
                actual = obj
                for f in fields:
                    actual = actual[f.replace("~1", "/").replace("~0", "~")]
                if actual != p["value"]:
                    raise server_failure(INVALID)
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
        if resource == "deployment" and (
            obj["spec"] != stored["spec"]
            or obj["metadata"].get("annotations") != stored["metadata"].get("annotations")
        ):
            obj["metadata"]["generation"] += 1
        if obj["metadata"]["resourceVersion"] != stored["metadata"]["resourceVersion"]:
            raise server_failure(CONFLICT)
        obj["metadata"]["resourceVersion"] = str(
            int(stored["metadata"]["resourceVersion"]) + 1
        )
        if resource == "configmap":
            self.cm = obj
        else:
            self.dep = obj
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

    def test_all_four_mutations_record_actual_generation_and_annotation_changes(self):
        api, path = FakeAPI(), self.tmp / "four-phases"
        api.dep["metadata"]["generation"] = 6  # actual run27 started at generation6
        state = operator.prepare(api, "a" * 16, path)
        operator.pause(api, state, path)
        operator.scale(api, state, 0, "down", path)
        api.dep["metadata"]["resourceVersion"] = "100"  # ordinary controller status write
        operator.scale(api, state, 2, "up", path)
        operator.restore(api, state, path)
        receipt = state["receipt"]
        self.assertEqual(receipt["schema"], "t17-v2")
        self.assertEqual(receipt["original_generation"], 6)
        for name, generation in zip(("pause", "down", "up", "resume"), (7, 8, 9, 10)):
            row = receipt[name]
            self.assertEqual(row["generation"], generation)
            self.assertEqual(row["generation_before"], generation - 1)
            self.assertTrue(row["changed"])
            self.assertLessEqual(row["started_ns"], row["acknowledged_ns"])
            self.assertNotEqual(row["resource_version_before"], row["resource_version"])
        self.assertEqual(receipt["resume"]["annotation_sha"], receipt["original_annotation_sha"])
        saved = copy.deepcopy(receipt)
        operator.restore(api, state, path)
        self.assertEqual(state["receipt"], saved)

    def test_original_disabled_annotation_records_explicit_noops(self):
        api, path = FakeAPI(), self.tmp / "noops"
        api.dep["metadata"]["annotations"][operator.RECONCILE] = "disabled"
        state = operator.prepare(api, "a" * 16, path)
        operator.pause(api, state, path)
        operator.scale(api, state, 0, "down", path)
        operator.restore(api, state, path)
        for name in ("pause", "resume"):
            row = state["receipt"][name]
            self.assertFalse(row["changed"])
            self.assertEqual(row["generation_before"], row["generation"])
            self.assertEqual(row["annotation_sha_before"], row["annotation_sha"])

    def test_lost_annotation_responses_never_fabricate_phase_receipts(self):
        for phase in ("pause", "resume"):
            api, path = FakeAPI(), self.tmp / ("lost-" + phase)
            state = operator.prepare(api, "a" * 16, path)
            if phase == "resume":
                operator.pause(api, state, path)
                operator.scale(api, state, 0, "down", path)
                operator.scale(api, state, 2, "up", path)
            original = api.patch
            def lose_response(resource, name, operations, namespace=operator.NAMESPACE):
                result = original(resource, name, operations, namespace)
                if resource == "deployment":
                    raise RuntimeError("response lost")
                return result
            api.patch = lose_response
            with self.assertRaises(RuntimeError):
                (operator.pause if phase == "pause" else operator.restore)(api, state, path)
            self.assertNotIn(phase, state["receipt"])
            api.patch = original
            operator.restore(api, state, path)
            self.assertTrue(state["restored"])
            self.assertNotIn(phase, state["receipt"])

    def test_legacy_state_is_restorable_but_cannot_start_new_qualification(self):
        api, path = FakeAPI(), self.tmp / "legacy"
        state = operator.prepare(api, "a" * 16, path)
        state["receipt"] = {key: state["receipt"][key] for key in
                            ("schema", "marker", "deployment_uid", "original_replicas")}
        state["receipt"]["schema"] = "t17-v1"
        api.cm["data"]["receipt.json"] = json.dumps(state["receipt"])
        with self.assertRaises(ValueError):
            operator.run(api, state, path, "job")
        api.dep["spec"]["replicas"] = 0
        api.dep["metadata"]["annotations"][operator.RECONCILE] = "disabled"
        operator.restore(api, state, path)
        self.assertTrue(state["restored"])
        self.assertEqual(state["receipt"]["schema"], "t17-v1")
        self.assertNotIn("resume", state["receipt"])

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

        failed_attempts = []

        def fail_scale(resource, name, operations, namespace=operator.NAMESPACE):
            if any(
                p["path"] == "/spec/replicas"
                and p.get("value") == 2
                and p["op"] == "replace"
                for p in operations
            ):
                failed_attempts.append(1)
                raise RuntimeError("unavailable")
            return original(resource, name, operations, namespace)

        api.patch = fail_scale
        with self.assertRaises(RuntimeError):
            operator.restore(api, state, path)
        self.assertNotIn(operator.RECONCILE, api.dep["metadata"]["annotations"])
        self.assertFalse(state["restored"])
        self.assertEqual(len(failed_attempts), 1)

    def test_error_diagnostics_are_safe_and_only_exact_storage_conflict_retries(self):
        for stderr, reason, retry in (
            (CONFLICT, "Conflict", True),
            (
                CONFLICT.replace(operator.DEPLOYMENT, "other-deployment"),
                "Conflict",
                False,
            ),
            (
                "Error from server (Conflict): admission denied with private-object",
                "Conflict",
                False,
            ),
            (INVALID, "Invalid", False),
            (
                "Error from server (Forbidden): private-object secret=abc",
                "Forbidden",
                False,
            ),
            ("client error with secret=abc", "Unknown", False),
        ):
            with self.subTest(reason=reason, retry=retry):
                error = server_failure(stderr)
                self.assertIn("reason=" + reason, str(error))
                self.assertEqual(error.resource_version_conflict, retry)
                self.assertNotIn("secret=abc", str(error))
                self.assertNotIn("private-object", str(error))

    def test_stored_resource_version_guard_reports_409_and_legacy_test_reports_422(
        self,
    ):
        api = FakeAPI()
        stale = copy.deepcopy(api.dep)
        api.dep["metadata"]["resourceVersion"] = "2"
        before = copy.deepcopy(api.dep)
        with self.assertRaises(RuntimeError) as caught:
            api.patch(
                "deployment",
                operator.DEPLOYMENT,
                operator.guards(stale)
                + [{"op": "replace", "path": "/spec/replicas", "value": 0}],
            )
        self.assertEqual(caught.exception.status, 409)
        self.assertTrue(caught.exception.resource_version_conflict)
        self.assertEqual(api.dep, before)
        with self.assertRaises(RuntimeError) as caught:
            api.patch(
                "deployment",
                operator.DEPLOYMENT,
                [
                    {"op": "test", "path": "/metadata/resourceVersion", "value": "1"},
                    {"op": "replace", "path": "/spec/replicas", "value": 0},
                ],
            )
        self.assertEqual(caught.exception.status, 422)
        self.assertFalse(caught.exception.resource_version_conflict)
        self.assertEqual(api.dep, before)

    def test_scale_retries_only_proven_conflict_with_fresh_guards(self):
        api, path = FakeAPI(), self.tmp / "conflict"
        state = operator.prepare(api, "a" * 16, path)
        operator.pause(api, state)
        original = api.patch
        calls = []

        def concurrent_status(resource, name, operations, namespace=operator.NAMESPACE):
            if resource == "deployment":
                calls.append(copy.deepcopy(operations))
                if len(calls) == 1:
                    api.dep["metadata"]["resourceVersion"] = "20"
                    raise server_failure(CONFLICT)
            return original(resource, name, operations, namespace)

        api.patch = concurrent_status
        with patch.object(operator.time, "sleep"):
            operator.scale(api, state, 0, "down", path)
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            calls[1][1],
            {"op": "replace", "path": "/metadata/resourceVersion", "value": "20"},
        )
        self.assertEqual(api.dep["spec"]["replicas"], 0)
        diagnostic = state["operation_errors"][0]
        self.assertEqual(
            (diagnostic["status"], diagnostic["reason"]), (409, "Conflict")
        )
        self.assertEqual(diagnostic["operation"], "scale_down")
        self.assertEqual(
            json.loads(path.read_text())["operation_errors"], state["operation_errors"]
        )

    def test_conflict_retry_rechecks_identity_spec_replicas_and_flux_annotation(self):
        for field in ("uid", "spec", "replicas", "annotation"):
            with self.subTest(field=field):
                api, path = FakeAPI(), self.tmp / ("conflict-" + field)
                state = operator.prepare(api, "a" * 16, path)
                operator.pause(api, state)
                calls = []

                def changed(*args, **kwargs):
                    calls.append(1)
                    if field == "uid":
                        api.dep["metadata"]["uid"] = "replacement"
                    elif field == "spec":
                        api.dep["spec"]["template"]["image"] = "other"
                    elif field == "replicas":
                        api.dep["spec"]["replicas"] = 0
                    else:
                        api.dep["metadata"]["annotations"][operator.RECONCILE] = (
                            "enabled"
                        )
                    raise server_failure(CONFLICT)

                api.patch = changed
                with (
                    patch.object(operator.time, "sleep"),
                    self.assertRaises(ValueError),
                ):
                    operator.scale(api, state, 0, "down", path)
                self.assertEqual(len(calls), 1)
                self.assertNotIn("down", state["receipt"])

    def test_conflicts_are_bounded_and_other_errors_never_retried(self):
        for stderr, attempts in (
            (CONFLICT, 3),
            (INVALID, 1),
            ("Error from server (Forbidden): denied", 1),
        ):
            with self.subTest(stderr=stderr):
                api, path = FakeAPI(), self.tmp / str(attempts)
                path.unlink(missing_ok=True)
                state = operator.prepare(api, "a" * 16, path)
                operator.pause(api, state)
                calls = []

                def fail(*args, **kwargs):
                    calls.append(1)
                    raise server_failure(stderr)

                api.patch = fail
                with (
                    patch.object(operator.time, "sleep"),
                    self.assertRaises(RuntimeError),
                ):
                    operator.scale(api, state, 0, "down", path)
                self.assertEqual(len(calls), attempts)
                self.assertNotIn("down", state["receipt"])
                self.assertEqual(api.dep["spec"]["replicas"], 2)

    def test_restore_does_not_claim_an_unacknowledged_external_scale(self):
        api, path = FakeAPI(), self.tmp / "external-restore"
        state = operator.prepare(api, "a" * 16, path)
        operator.pause(api, state)
        operator.scale(api, state, 0, "down", path)
        original = api.patch
        first = True

        def restored_elsewhere(
            resource, name, operations, namespace=operator.NAMESPACE
        ):
            nonlocal first
            if resource == "deployment" and first:
                first = False
                api.dep["spec"]["replicas"] = 2
                api.dep["metadata"]["resourceVersion"] = "20"
                raise server_failure(CONFLICT)
            return original(resource, name, operations, namespace)

        api.patch = restored_elsewhere
        with patch.object(operator.time, "sleep"):
            operator.restore(api, state, path)
        self.assertTrue(state["restored"])
        self.assertNotIn("up", state["receipt"])

    def test_client_timeout_never_exposes_command_or_captured_output(self):
        failure = operator.subprocess.TimeoutExpired(
            ["kubectl", "secret-value"],
            20,
            output="private-object",
            stderr="private-stderr",
        )
        with patch.object(operator.subprocess, "run", side_effect=failure):
            with self.assertRaises(RuntimeError) as caught:
                operator.API("/not-used").command(
                    ["patch", "deployment", operator.DEPLOYMENT]
                )
        self.assertIn("reason=ClientTimeout", str(caught.exception))
        self.assertFalse(caught.exception.resource_version_conflict)
        for value in ("secret-value", "private-object", "private-stderr"):
            self.assertNotIn(value, str(caught.exception))

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
