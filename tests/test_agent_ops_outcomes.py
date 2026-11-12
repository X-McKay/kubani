"""Every ending of `just agent run`, `wait` and `cancel`, driven through the command entry point (`main`).

The runner is the fake kube of test_agent_ops.py. Nothing here patches `run.submit` or `run.resume`, so the code each
ending is tagged with at its own site is what is asserted, together with the exit code, `retryable` and the fields a caller
needs to follow up. Contract: docs/infrastructure/configuration/cli-contract.md.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_agent_ops import BytesKube, cli, kube_for_run, make_root

from agent_ops import live, run

ACCEPTED = {"workflow_id": "session:tenant-test:sample:s", "run_id": "r", "namespace": "agents-tenant-test", "task_queue": "sessions-tenant-test"}
RUNNING = {"workflow_id": "w", "run_id": "r", "status": "RUNNING", "query": {"state": "RUNNING"}}
DONE = {"workflow_id": "w", "run_id": "r", "status": "COMPLETED", "query": {"state": "CLEANED"}, "result": {"outcome": "COMPLETED"}, "confirmed": True}
FAILED = {"workflow_id": "w", "run_id": "r", "status": "FAILED", "query": {"state": "FAILED"}, "result": {"outcome": "FAILED"}, "confirmed": True}
FOLLOW_UP_KEYS = {"sessionId", "dir", "receiptPath", "next"}


def times_out(request):
    raise subprocess.TimeoutExpired("kubectl", run.EXEC_TIMEOUT)


def interrupts(request):
    raise KeyboardInterrupt


def cannot_start(request):
    raise OSError("kubectl is not installed")


def unforeseen(request):
    raise KeyError("a value that must not be printed")


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = make_root(self.tmp)
        self.out = self.tmp / "run"

    def kube(self, results):
        return kube_for_run(list(results), kube_class=BytesKube)

    def main(self, argv, kube):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(live, "Kube", lambda: kube), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--root", str(self.root), *argv])
        return code, json.loads(out.getvalue()), err.getvalue()

    def run_main(self, results, *extra):
        return self.main(["run", "sample", "--task", "go", "--out", str(self.out), *extra], self.kube(results))

    def assert_ending(self, document, code, error_code, retryable):
        self.assertIs(document["ok"], False)
        self.assertEqual((document["error"]["code"], document["error"]["retryable"]), (error_code, retryable), document)
        self.assertEqual(self.exit_code, code)

    def ended(self, results, *extra):
        self.exit_code, document, err = self.run_main(results, *extra)
        return document, err

    def assert_not_confirmed(self, document, exit_code, *, receipt):
        self.assert_ending(document, exit_code, "not-confirmed", False)
        self.assertEqual((document["sessionId"], document["dir"]), (json.loads((self.out / "request.json").read_text())["session_id"], str(self.out)))
        self.assertIn("do not repeat this command", document["error"]["message"])
        if receipt:
            path = self.out / "receipt.json"
            self.assertEqual((document["receiptPath"], document["next"]), (str(path), f"just agent status --receipt {path}"))
            self.assertIn(document["next"], document["error"]["message"])
        else:
            self.assertFalse(FOLLOW_UP_KEYS - {"sessionId", "dir"} & set(document))
            self.assertFalse((self.out / "receipt.json").exists())


class SubmitEndings(Case):
    """From the moment the submit call is attempted, none of its failures is safe to repeat."""

    def test_submit_call_that_does_not_answer(self):
        document, _ = self.ended([times_out])
        self.assertEqual(document["status"], "SUBMIT_UNCONFIRMED")
        self.assertIn("whether it took effect is not known", document["reason"])
        self.assert_not_confirmed(document, 2, receipt=False)

    def test_submit_call_that_returns_something_unreadable(self):
        document, _ = self.ended([b"<html>502 Bad Gateway</html>"])
        self.assertEqual(document["status"], "SUBMIT_UNCONFIRMED")
        self.assertIn("returned no JSON", document["reason"])
        self.assert_not_confirmed(document, 2, receipt=False)

    def test_submit_call_the_pod_answers_with_an_error(self):
        for answer in ("session identity already exists", "workflow start failed", "deposit refused: the policy service did not accept the token"):
            with self.subTest(answer=answer):
                self.out = self.tmp / ("run-" + str(abs(hash(answer))))
                document, _ = self.ended([{"error": answer}])
                self.assertEqual(document["status"], "SUBMIT_UNCONFIRMED")
                self.assert_not_confirmed(document, 2, receipt=False)

    def test_interrupt_while_the_submit_call_is_in_flight(self):
        document, _ = self.ended([interrupts])
        self.assertEqual(document["status"], "SUBMIT_UNCONFIRMED")
        self.assert_not_confirmed(document, 130, receipt=False)

    def test_error_that_escapes_the_submit_call_to_the_generic_handler(self):
        for exc, exit_code in ((cannot_start, 1), (unforeseen, 1)):
            with self.subTest(exc=exc.__name__):
                self.out = self.tmp / exc.__name__
                document, err = self.ended([exc])
                self.assertEqual(document["status"], "SUBMIT_UNCONFIRMED")
                self.assert_not_confirmed(document, exit_code, receipt=False)
                self.assertNotIn("must not be printed", json.dumps(document) + err)

    def test_answer_that_lacks_a_field_after_the_session_was_started(self):
        document, _ = self.ended([{k: v for k, v in ACCEPTED.items() if k != "workflow_id"}])
        self.assertEqual(document["status"], "SUBMIT_UNCONFIRMED")
        self.assert_not_confirmed(document, 1, receipt=False)


class FollowEndings(Case):
    """After the receipt is written, only a finish the runner confirmed is anything but `not-confirmed`."""

    def test_status_poll_that_does_not_answer_while_following(self):
        document, err = self.ended([ACCEPTED, times_out])
        self.assertEqual(document["status"], "FOLLOW_FAILED")
        self.assertTrue(err.startswith("refused: "))
        self.assert_not_confirmed(document, 2, receipt=True)

    def test_status_poll_that_returns_something_unreadable_while_following(self):
        document, _ = self.ended([ACCEPTED, b"not json"])
        self.assertEqual(document["status"], "FOLLOW_FAILED")
        self.assert_not_confirmed(document, 2, receipt=True)

    def test_other_errors_while_following(self):
        for exc in (cannot_start, unforeseen):
            with self.subTest(exc=exc.__name__):
                self.out = self.tmp / exc.__name__
                document, err = self.ended([ACCEPTED, exc])
                self.assertEqual(document["status"], "FOLLOW_FAILED")
                self.assert_not_confirmed(document, 1, receipt=True)
                self.assertNotIn("must not be printed", json.dumps(document) + err)

    def test_interrupt_while_following(self):
        document, _ = self.ended([ACCEPTED, interrupts])
        self.assertEqual(document["status"], "INTERRUPTED")
        self.assert_not_confirmed(document, 130, receipt=True)

    def test_interrupt_outside_the_places_run_handles_itself_after_the_receipt(self):
        with patch.object(run, "follow", side_effect=KeyboardInterrupt):
            document, _ = self.ended([ACCEPTED])
        self.assert_not_confirmed(document, 130, receipt=True)

    def test_run_that_gives_up_waiting(self):
        document, _ = self.ended([ACCEPTED, *[RUNNING] * 200], "--wait-timeout", "0.05", "--poll-interval", "0.01")
        self.assertEqual((document["status"], document["timedOut"]), ("RUNNING", True))
        self.assert_not_confirmed(document, 124, receipt=True)
        self.assertEqual(json.loads((self.out / "status.json").read_text())["next"], document["next"])

    def test_session_that_closed_unsuccessfully_is_a_failed_not_a_not_confirmed(self):
        document, _ = self.ended([ACCEPTED, FAILED])
        self.assert_ending(document, 1, "failed", False)
        self.assertNotIn("next", document)

    def test_no_wait_and_a_confirmed_finish_are_successes(self):
        self.exit_code, document, _ = self.run_main([ACCEPTED], "--no-wait")
        self.assertEqual((self.exit_code, document["ok"], document["status"]), (0, True, "SUBMITTED"))
        self.assertNotIn("next", document)
        self.out = self.tmp / "second"
        self.exit_code, document, _ = self.run_main([ACCEPTED, DONE, dict(DONE, report="# R\n", workspace=[])])
        self.assertEqual((self.exit_code, document["ok"], document["status"]), (0, True, "COMPLETED"))


class BeforeAnySubmission(Case):
    """An ending before the submission is attempted keeps its code: nothing was started and repeating is as safe as before."""

    def test_interrupt_before_the_run_has_a_directory(self):
        with patch.object(run, "Runner", side_effect=KeyboardInterrupt):
            document, _ = self.ended([])
        self.assert_ending(document, 130, "interrupted", True)
        self.assertNotIn("sessionId", document)
        self.assertFalse(self.out.exists())

    def test_refusal_before_the_run_has_a_directory(self):
        document, _ = self.ended([], "--grant-handle", "h-1")
        self.assert_ending(document, 2, "invalid-arguments", False)
        self.assertFalse(self.out.exists())

    def test_error_after_the_directory_and_before_the_submission(self):
        with patch.object(run, "_private", side_effect=PermissionError("denied")):
            document, _ = self.ended([])
        self.assert_ending(document, 1, "failed", False)
        self.assertEqual(document["status"], "ERROR")


class ResumeEndings(Case):
    """`wait`, `status` and `cancel` read a receipt and are safe to repeat; their codes stay as they were."""

    def receipt(self):
        self.exit_code, document, _ = self.run_main([ACCEPTED], "--no-wait")
        self.assertEqual(self.exit_code, 0, document)
        return str(self.out / "receipt.json")

    def resume(self, command, results, *extra):
        receipt = self.receipt()
        self.exit_code, document, _ = self.main([command, "--receipt", receipt, *extra], self.kube(results))
        return document

    def test_wait_that_passes_its_own_deadline_stays_a_retryable_timeout(self):
        document = self.resume("wait", [*[RUNNING] * 200], "--wait-timeout", "0.05", "--poll-interval", "0.01")
        self.assert_ending(document, 124, "timeout", True)
        self.assertNotIn("next", document)

    def test_cancel_the_runner_accepted(self):
        document = self.resume("cancel", [{"workflow_id": "w", "run_id": "r", "cancel_requested": True}])
        self.assertEqual((self.exit_code, document["ok"], document["cancel"]["cancel_requested"]), (0, True, True))
        self.assertNotIn("error", document)

    def test_cancel_the_runner_did_not_accept(self):
        for answer in ({"workflow_id": "w", "run_id": "r", "cancel_requested": False}, {"workflow_id": "w", "run_id": "r"}):
            with self.subTest(answer=answer):
                self.out = self.tmp / ("c" + str(len(answer)))
                document = self.resume("cancel", [answer])
                self.assert_ending(document, 1, "failed", False)
                self.assertIn("did not accept the cancel", document["error"]["message"])

    def test_cancel_whose_call_does_not_answer_is_still_retryable(self):
        document = self.resume("cancel", [times_out])
        self.assert_ending(document, 2, "timeout", True)


if __name__ == "__main__":
    unittest.main()
