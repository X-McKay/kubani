"""The outcome contract of the three operator tools: one document, `ok`, and a closed set of error codes."""

import contextlib
import importlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

OPS = Path(__file__).resolve().parents[1] / "infrastructure/scripts/ops"
sys.path.insert(0, str(OPS))
import outcome  # noqa: E402
from agent_ops import approve, delegation, layout, live, register, run, stage, state, sync  # noqa: E402
from agent_preflight import source as preflight_source  # noqa: E402
from keycloak_admin import KeycloakHTTPError  # noqa: E402


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, OPS / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_cli = load("agent_ops_cli_outcome", "agent-ops.py")
preflight_cli = load("agent_preflight_cli_outcome", "agent-preflight.py")
mcp_cli = load("mcp_registry_cli_outcome", "mcp-registry.py")


def call(module, argv):
    """(exit code, stdout, stderr); a SystemExit becomes its code."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = module.main(argv)
        except SystemExit as exit_:
            code = exit_.code
    return code, out.getvalue(), err.getvalue()


def only_document(text):
    """Exactly one JSON document on stdout."""
    decoder = json.JSONDecoder()
    value, end = decoder.raw_decode(text.lstrip())
    assert text.lstrip()[end:].strip() == "", "more than one document on stdout"
    return value


class OutcomeModule(unittest.TestCase):
    def test_set_is_closed_and_each_code_has_a_class(self):
        self.assertEqual(
            set(outcome.CODES),
            {"invalid-arguments", "validation-failed", "not-found", "refused", "conflict", "check-failed", "failed", "not-confirmed", "no-consent", "timeout", "interrupted", "unavailable", "internal"},
        )
        self.assertEqual({c for c, retryable in outcome.CODES.items() if retryable}, {"no-consent", "timeout", "interrupted", "unavailable"})

    def test_constructor_refuses_a_code_outside_the_set(self):
        with self.assertRaisesRegex(ValueError, "unknown outcome code"):
            outcome.error("oops", "message")

    def test_constructor_refuses_a_retryable_flag_that_disagrees(self):
        for code, retryable in outcome.CODES.items():
            proofs = [] if code == "check-failed" else None
            self.assertEqual(outcome.error(code, "m", retryable=retryable, proofs=proofs)["retryable"], retryable)
            with self.assertRaisesRegex(ValueError, "disagrees"):
                outcome.error(code, "m", retryable=not retryable, proofs=proofs)

    def test_retryable_is_filled_from_the_class(self):
        self.assertIs(outcome.error("timeout", "m")["retryable"], True)
        self.assertIs(outcome.error("refused", "m")["retryable"], False)

    def test_proofs_belong_to_check_failed_only(self):
        with self.assertRaises(ValueError):
            outcome.error("check-failed", "m")
        with self.assertRaises(ValueError):
            outcome.error("refused", "m", proofs=[])
        self.assertEqual(outcome.error("check-failed", "m", proofs=[{"a": 1}])["proofs"], [{"a": 1}])

    def test_message_is_text(self):
        with self.assertRaises(ValueError):
            outcome.error("failed", "")

    def test_coded_exception_refuses_an_unknown_code(self):
        self.assertEqual(outcome.Coded("m", "conflict").code, "conflict")
        self.assertEqual(outcome.Coded("m").code, "failed")
        with self.assertRaises(ValueError):
            outcome.Coded("m", "nope")

    def test_document_adds_ok_and_error_and_changes_nothing_else(self):
        doc = {"status": "X", "n": 1}
        self.assertEqual(outcome.document(doc), {"status": "X", "n": 1, "ok": True})
        failure = outcome.error("failed", "m")
        self.assertEqual(outcome.document(doc, failure), {"status": "X", "n": 1, "ok": False, "error": failure})
        self.assertEqual(doc, {"status": "X", "n": 1})
        self.assertEqual(outcome.document({"ok": False}, failure)["ok"], False)
        with self.assertRaises(ValueError):
            outcome.document({"ok": False})
        with self.assertRaises(ValueError):
            outcome.document({"error": "kept"}, failure)

    def test_every_code_the_tools_use_is_in_the_set(self):
        # Every default_code and every literal passed to a Coded exception is checked at construction; the classes' defaults here.
        for cls in (layout.LayoutError, live.LiveError, sync.SyncError, sync.SourceMissing, register.RegisterError, stage.StageError, approve.ApproveError, run.RunError, delegation.ConsentError):
            self.assertIn(cls.default_code, outcome.CODES)


class AgentOps(unittest.TestCase):
    def cli(self, argv):
        return call(agent_cli, ["--root", "/nonexistent-root", *argv])

    def doc(self, argv, expect_code):
        code, out, err = self.cli(argv)
        self.assertEqual(code, expect_code, (out, err))
        document = only_document(out)
        self.assertIsInstance(document["ok"], bool)
        self.assertEqual(document["ok"], expect_code == 0)
        if expect_code:
            self.assertEqual(set(document["error"]) - {"proofs"}, {"code", "message", "retryable"})
            self.assertIn(document["error"]["code"], outcome.CODES)
            self.assertIs(document["error"]["retryable"], outcome.CODES[document["error"]["code"]])
        return document, err

    def test_success_documents_have_ok_true(self):
        snapshot = {"flux": [], "platformPods": {"total": 0, "unhealthy": []}, "tenants": {}, "openPullRequests": None}
        with patch.object(state, "snapshot", return_value=snapshot), patch.object(live, "Kube"):
            document, _ = self.doc(["state", "--json"], 0)
        self.assertEqual(document, dict(snapshot, ok=True))
        with patch.object(sync, "sync", return_value={"agent": "sample"}):
            document, _ = self.doc(["sync", "sample", "--source", "/x"], 0)
        self.assertEqual(document, {"agent": "sample", "ok": True})
        with patch.object(sync, "check", return_value={"ok": True, "agents": [{"agent": "sample", "state": "ok"}]}), patch.object(register, "check", return_value={"ok": True, "tenants": []}):
            document, _ = self.doc(["check-sync"], 0)
        self.assertEqual((document["ok"], document["pins"], document["agents"][0]["state"]), (True, [], "ok"))

    def test_ls_json_is_one_object_with_the_rows_under_agents(self):
        rows = [{"agent": "sample", "ready": True}, {"agent": "other", "ready": False}]
        with patch.object(live, "listing", return_value=rows), patch.object(live, "Kube"):
            document, _ = self.doc(["ls", "--json"], 0)
        self.assertEqual(document, {"agents": rows, "ok": True})
        with patch.object(live, "listing", return_value=[]), patch.object(live, "Kube"):
            document, _ = self.doc(["ls", "--json"], 0)
        self.assertEqual(document, {"agents": [], "ok": True})

    def test_ls_without_json_still_prints_the_table(self):
        with patch.object(live, "listing", return_value=[{"agent": "sample"}]), patch.object(live, "format_listing", return_value="TABLE"), patch.object(live, "Kube"):
            code, out, _ = self.cli(["ls"])
        self.assertEqual((code, out), (0, "TABLE\n"))

    def test_check_sync_failure_carries_every_check_as_proofs_and_keeps_exit_1(self):
        agents = [{"agent": "a", "state": "ok"}, {"agent": "b", "state": "fail", "detail": "x"}]
        pins = [{"tenant": "t", "state": "drift", "detail": "y"}]
        with patch.object(sync, "check", return_value={"ok": False, "agents": agents}), patch.object(register, "check", return_value={"ok": True, "tenants": pins}):
            document, _ = self.doc(["check-sync"], 1)
        self.assertEqual(document["ok"], False)
        self.assertEqual(document["agents"], agents)
        self.assertEqual(document["pins"], pins)
        error = document["error"]
        self.assertEqual((error["code"], error["retryable"]), ("check-failed", False))
        self.assertEqual([(p["check"], p["state"]) for p in error["proofs"]], [("agent-sync", "ok"), ("agent-sync", "fail"), ("tenant-pin", "drift")])

    def test_exceptions_map_to_codes_and_keep_exit_codes(self):
        cases = [
            (layout.LayoutError("agent 'z': expected exactly one committed directory, found 0", "not-found"), 2, "not-found"),
            (layout.LayoutError("bad shape"), 2, "validation-failed"),
            (live.LiveError("kubectl get x failed: timed out"), 2, "unavailable"),
            (live.LiveError("no approved Ready release", "not-found"), 2, "not-found"),
            (sync.SyncError("recorded from elsewhere", "conflict"), 2, "conflict"),
            (sync.SourceMissing("x is not in y"), 2, "not-found"),
            (stage.StageError("gh missing", "unavailable"), 2, "unavailable"),
            (approve.ApproveError("controller has not verified the signature"), 2, "refused"),
            (register.RegisterError("x"), 2, "validation-failed"),
            (FileNotFoundError("no such receipt"), 1, "not-found"),
            (PermissionError("denied"), 1, "failed"),
            (ValueError("bad json"), 1, "validation-failed"),
        ]
        for exc, exit_code, code in cases:
            with self.subTest(exc=repr(exc)), patch.object(sync, "sync", side_effect=exc):
                document, err = self.doc(["sync", "sample", "--source", "/x"], exit_code)
                self.assertEqual(document["error"]["code"], code)
                self.assertEqual(document["error"]["message"], str(exc))
                self.assertIn(str(exc), err)
                self.assertEqual(set(document), {"ok", "error"})

    def test_unforeseen_error_in_any_command_is_internal_and_names_no_text(self):
        with patch.object(sync, "sync", side_effect=KeyError("TOKEN-VALUE-MUST-NOT-APPEAR")):
            document, _ = self.doc(["sync", "sample", "--source", "/x"], 1)
        self.assertEqual(document["error"]["code"], "internal")
        self.assertRegex(document["error"]["message"], r"^unexpected KeyError at \w+\.py:\d+$")
        self.assertNotIn("TOKEN-VALUE-MUST-NOT-APPEAR", json.dumps(document))

    def test_run_endings_map_to_codes_and_keep_exit_codes(self):
        cases = [
            (3, run.tag({"status": "NOT_SUBMITTED", "reason": "r"}, "no-consent"), "no-consent", True),
            (130, run.tag({"status": "NOT_SUBMITTED", "reason": "r"}, "interrupted"), "interrupted", True),
            (1, run.tag({"status": "NOT_SUBMITTED", "reason": "r", "missing": ["m"]}, "refused"), "refused", False),
            (1, run.tag({"status": "NOT_SUBMITTED", "reason": "r"}, "conflict"), "conflict", False),
            (1, run.tag({"status": "NOT_SUBMITTED", "reason": "r"}, "validation-failed"), "validation-failed", False),
            (2, run.tag({"status": "SUBMIT_UNCONFIRMED", "reason": "r"}, "not-confirmed"), "not-confirmed", False),
            (130, run.tag({"status": "SUBMIT_UNCONFIRMED", "reason": "r"}, "not-confirmed"), "not-confirmed", False),
            (124, run.tag({"status": "RUNNING", "timedOut": True, "reason": "r", "next": "just agent status --receipt /r/receipt.json"}, "not-confirmed"), "not-confirmed", False),
            (1, run.tag({"status": "FAILED", "confirmed": True}, "failed"), "failed", False),
            (130, run.tag({"status": "INTERRUPTED", "reason": "r"}, "interrupted"), "interrupted", True),
            (130, run.tag({"status": "INTERRUPTED", "reason": "r", "next": "just agent status --receipt /r/receipt.json"}, "not-confirmed"), "not-confirmed", False),
        ]
        for code_, envelope, code, retryable in cases:
            with self.subTest(status=envelope["status"], code=code), patch.object(run, "submit", return_value=(code_, envelope)), patch.object(live, "Kube"):
                document, _ = self.doc(["run", "sample", "--task", "go"], code_)
                for key, value in envelope.items():
                    self.assertEqual(document[key], value)
                self.assertEqual((document["error"]["code"], document["error"]["retryable"]), (code, retryable))
                self.assertEqual(set(document) - set(envelope), {"ok", "error"})
                if code == "not-confirmed":
                    self.assertIn("do not repeat this command", document["error"]["message"])

    def test_run_fallbacks_without_a_kind(self):
        for exit_code, code in ((124, "timeout"), (130, "interrupted"), (3, "no-consent"), (1, "failed")):
            with self.subTest(exit_code=exit_code), patch.object(run, "submit", return_value=(exit_code, {"status": "COMPLETED"})), patch.object(live, "Kube"):
                document, _ = self.doc(["run", "sample", "--task", "go"], exit_code)
                self.assertEqual(document["error"]["code"], code)

    def test_status_of_a_running_session_is_a_success_through_main(self):
        running = {"receipt": {}, "status": "RUNNING", "query": {"state": "RUNNING"}, "cleanup": "NOT_CONFIRMED"}
        with patch.object(run, "resume", return_value=(0, dict(running))):
            document, _ = self.doc(["status", "--receipt", "/r/receipt.json"], 0)
        self.assertEqual(document, dict(running, ok=True))

    def test_status_of_a_terminal_session_keeps_its_exit_code_and_code(self):
        closed = {"receipt": {}, "status": "FAILED", "confirmed": False, "cleanup": "NOT_CONFIRMED"}
        with patch.object(run, "resume", return_value=(1, run.tag(closed, "failed"))):
            document, _ = self.doc(["status", "--receipt", "/r/receipt.json"], 1)
        self.assertEqual(document["error"]["code"], "failed")
        self.assertIn("FAILED", document["error"]["message"])
        done = {"receipt": {}, "status": "COMPLETED", "confirmed": True, "cleanup": "CONFIRMED"}
        with patch.object(run, "resume", return_value=(0, run.tag(done, None))):
            document, _ = self.doc(["status", "--receipt", "/r/receipt.json"], 0)
        self.assertEqual(document["status"], "COMPLETED")

    def test_wait_that_ends_first_is_still_124_timeout(self):
        with patch.object(run, "resume", return_value=(124, run.tag({"receipt": {}, "status": "RUNNING", "timedOut": True}, "timeout"))):
            document, _ = self.doc(["wait", "--receipt", "/r/receipt.json"], 124)
        self.assertEqual(document["error"]["code"], "timeout")

    def test_cancel_not_accepted(self):
        with patch.object(run, "resume", return_value=(1, run.tag({"receipt": {}, "cancel": {}}, "failed"))):
            document, _ = self.doc(["cancel", "--receipt", "/r/receipt.json"], 1)
        self.assertEqual(document["error"]["code"], "failed")

    def test_run_success_has_ok_true(self):
        with patch.object(run, "submit", return_value=(0, {"status": "SUBMITTED", "receipt": {}})), patch.object(live, "Kube"):
            document, _ = self.doc(["run", "sample", "--task", "go"], 0)
        self.assertEqual(document, {"status": "SUBMITTED", "receipt": {}, "ok": True})

    def test_consent_check_and_session_endings(self):
        claims = {"agent": "sample", "tenant": "t", "requiredScope": "s", "hasPolicyServiceAudience": True, "hasDelegationScope": False, "mayActSubPresent": True, "clientType": None, "undecodableClaims": [], "wouldBeAcceptedForDeposit": False, "missing": ["scope"]}
        with patch.object(delegation, "check", return_value=(1, claims)):
            document, _ = self.doc(["consent", "sample", "--check"], 1)
        error = document["error"]
        self.assertEqual(error["code"], "check-failed")
        self.assertEqual([p["ok"] for p in error["proofs"]], [True, True, False, True, True])
        self.assertEqual(document["missing"], ["scope"])
        with patch.object(delegation, "check", return_value=(124, {"agent": "sample", "timedOut": True})):
            document, _ = self.doc(["consent", "sample", "--check"], 124)
        self.assertEqual((document["error"]["code"], document["error"]["retryable"]), ("no-consent", True))
        with patch.object(run, "consent", return_value=(0, {"deposited": True})):
            document, _ = self.doc(["consent", "sample", "--session", "6b1f2f0e-3c1c-4f65-9d0a-5b0e2c7a9d41"], 0)
        self.assertEqual(document, {"deposited": True, "ok": True})
        with patch.object(run, "consent", return_value=(2, run.tag({"deposited": None, "reason": "r"}, "not-confirmed"))):
            document, _ = self.doc(["consent", "sample", "--session", "6b1f2f0e-3c1c-4f65-9d0a-5b0e2c7a9d41"], 2)
        self.assertEqual((document["error"]["code"], document["error"]["retryable"]), ("not-confirmed", False))

    def test_consent_and_run_argument_errors_are_invalid_arguments(self):
        document, _ = self.doc(["consent", "sample"], 2)
        self.assertEqual(document["error"]["code"], "invalid-arguments")
        self.assertEqual(document["status"], "REFUSED")
        document, _ = self.doc(["run", "sample"], 2)
        self.assertEqual(document["error"]["code"], "invalid-arguments")

    def test_keyboard_interrupt_outside_run_ends_with_a_document_then_propagates(self):
        out = io.StringIO()
        with patch.object(live, "listing", side_effect=KeyboardInterrupt), patch.object(live, "Kube"), contextlib.redirect_stdout(out), self.assertRaises(KeyboardInterrupt):
            agent_cli.main(["--root", "/x", "ls"])
        self.assertEqual(only_document(out.getvalue())["error"]["code"], "interrupted")

    def test_malformed_command_lines_print_usage_to_stderr_and_a_document_to_stdout(self):
        for argv in (["bogus"], [], ["run"], ["run", "sample", "--max-boundaries", "0"], ["status"], ["wait", "--receipt", "r", "--wait-timeout", "-1"]):
            with self.subTest(argv=argv):
                code, out, err = call(agent_cli, argv)
                self.assertEqual(code, 2)
                self.assertIn("usage:", err)
                document = only_document(out)
                self.assertEqual((document["ok"], document["error"]["code"], document["error"]["retryable"]), (False, "invalid-arguments", False))
                self.assertEqual(set(document), {"ok", "error"})

    def test_unrecognized_arguments_never_echo_their_values_into_the_document(self):
        marker = "VALUE-MARKER-9f3a"
        for argv in (
            ["status", "--receipt", "r", "--grant-handle", marker],
            ["status", "--receipt", "r", f"--grant-handle={marker}"],
            ["ls", marker],
            ["state", "--json", "--token", marker, "-x", marker, f"--other={marker}"],
        ):
            with self.subTest(argv=argv):
                code, out, err = call(agent_cli, argv)
                self.assertEqual(code, 2)
                self.assertNotIn(marker, out)
                self.assertIn(marker, err, "what argparse writes to stderr is unchanged")
                self.assertIn("usage:", err)
                document = only_document(out)
                self.assertEqual((document["ok"], document["error"]["code"], document["error"]["retryable"]), (False, "invalid-arguments", False))
                self.assertEqual(document["error"]["message"], "unrecognized arguments (values are not shown); usage is on stderr")

    def test_required_arguments_missing_keep_argparses_message_in_the_document(self):
        code, out, err = call(agent_cli, ["run"])
        self.assertEqual(only_document(out)["error"]["message"], "the following arguments are required: agent; usage is on stderr")


    def test_help_is_untouched(self):
        code, out, _ = call(agent_cli, ["--help"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("usage:"))


class AgentPreflight(unittest.TestCase):
    def preflight(self, result=None, side_effect=None):
        argv = ["sample", "--source", "/trusted", "--tag", "sample/v1"]
        with patch.object(preflight_cli, "run", return_value=result, side_effect=side_effect):
            return call(preflight_cli, argv)

    def test_success_keeps_the_receipt_and_its_ok(self):
        receipt = {"schemaVersion": 1, "ok": True, "checks": [{"code": "c", "state": "pass", "required": True}]}
        code, out, _ = self.preflight(receipt)
        self.assertEqual((code, json.loads(out)), (0, receipt))

    def test_failed_checks_are_check_failed_with_every_check_as_proof(self):
        checks = [
            {"code": "a", "state": "pass", "required": True},
            {"code": "b", "state": "fail", "required": True},
            {"code": "c", "state": "not_checked", "required": False},
        ]
        code, out, _ = self.preflight({"schemaVersion": 1, "ok": False, "checks": checks})
        document = only_document(out)
        self.assertEqual(code, 1)
        self.assertEqual((document["ok"], document["checks"], document["schemaVersion"]), (False, checks, 1))
        self.assertEqual((document["error"]["code"], document["error"]["retryable"], document["error"]["proofs"]), ("check-failed", False, checks))

    def test_only_unavailable_evidence_is_unavailable(self):
        checks = [{"code": "a", "state": "pass", "required": True}, {"code": "b", "state": "unavailable", "required": True}]
        code, out, _ = self.preflight({"ok": False, "checks": checks})
        error = only_document(out)["error"]
        self.assertEqual((code, error["code"], error["retryable"]), (1, "unavailable", True))
        self.assertNotIn("proofs", error)

    def test_a_missing_source_environment_is_not_found_and_keeps_the_checks_state(self):
        checks = [
            {"code": "source_compatibility", "state": "unavailable", "required": True, "explanation": preflight_source.NO_ENVIRONMENT},
            {"code": "live_agent_identity", "state": "not_checked", "required": False},
        ]
        code, out, _ = self.preflight({"schemaVersion": 1, "ok": False, "checks": checks})
        document = only_document(out)
        self.assertEqual(code, 1)
        self.assertEqual(document["checks"][0]["state"], "unavailable")
        self.assertEqual((document["error"]["code"], document["error"]["retryable"]), ("not-found", False))
        self.assertIn("uv sync --locked", document["error"]["message"])
        self.assertNotIn("proofs", document["error"])

    def test_the_missing_environment_is_not_found_only_when_it_is_the_one_blocking_check(self):
        missing = {"code": "source_compatibility", "state": "unavailable", "required": True, "explanation": preflight_source.NO_ENVIRONMENT}
        cases = (
            # another blocking check that is also unavailable: the unavailable class is what holds
            ([missing, {"code": "mcp_dependencies", "state": "unavailable", "required": True}], "unavailable"),
            # another blocking check that failed
            ([missing, {"code": "agent_semantics", "state": "fail", "required": True}], "check-failed"),
            # the source checker failed some other way: that one may succeed on a repeat
            ([dict(missing, explanation="The source checker failed, timed out or returned an invalid bounded receipt")], "unavailable"),
            # the same words on another check
            ([dict(missing, code="mcp_dependencies")], "unavailable"),
        )
        for checks, expected in cases:
            with self.subTest(checks=[c["code"] + ":" + c["state"] for c in checks]):
                code, out, _ = self.preflight({"schemaVersion": 1, "ok": False, "checks": checks})
                self.assertEqual((code, only_document(out)["error"]["code"]), (1, expected))

    def test_the_receipt_core_writes_for_a_missing_environment_is_what_the_cli_recognises(self):
        from agent_preflight import core

        with tempfile.TemporaryDirectory() as tmp, patch.object(preflight_source, "interpreter", side_effect=preflight_source.SourceEnvironmentError(preflight_source.NO_ENVIRONMENT)):
            result = core.run(Path(tmp), Path(tmp), "sample", "sample/v1")
        (check,) = [c for c in result["checks"] if c["code"] == "source_compatibility"]
        self.assertEqual((check["state"], check["required"], check["explanation"]), ("unavailable", True, preflight_source.NO_ENVIRONMENT))
        # Alone, that check is what the CLI reports as not-found.
        self.assertEqual(preflight_cli.failure_for({"checks": [check]})["code"], "not-found")

    def test_bare_failure_without_checks_is_check_failed(self):
        code, out, _ = self.preflight({"schemaVersion": 1, "ok": False})
        self.assertEqual((code, only_document(out)["error"]["code"]), (1, "check-failed"))

    def test_unforeseen_error_is_internal_without_its_text(self):
        code, out, err = self.preflight(side_effect=RuntimeError("SECRET-RESPONSE"))
        document = only_document(out)
        self.assertEqual(code, 1)
        self.assertEqual(document["error"]["code"], "internal")
        self.assertRegex(document["error"]["message"], r"^unexpected RuntimeError at \w+\.py:\d+$")
        self.assertNotIn("SECRET-RESPONSE", out)
        self.assertIn("RuntimeError", err)

    def test_malformed_command_lines(self):
        for argv in ([], ["sample"], ["sample", "--source", "/s"], ["sample", "--source", "/s", "--tag", "t", "--nope"]):
            with self.subTest(argv=argv):
                code, out, err = call(preflight_cli, argv)
                self.assertEqual(code, 2)
                self.assertIn("usage:", err)
                document = only_document(out)
                self.assertEqual((document["ok"], document["error"]["code"]), (False, "invalid-arguments"))


class AgentPreflightArguments(unittest.TestCase):
    def test_unrecognized_arguments_never_echo_their_values_into_the_document(self):
        marker = "VALUE-MARKER-9f3a"
        code, out, err = call(preflight_cli, ["sample", "--source", "/s", "--tag", "t", "--grant-handle", marker, f"--secret={marker}", marker])
        self.assertEqual(code, 2)
        self.assertNotIn(marker, out)
        self.assertIn(marker, err)
        message = only_document(out)["error"]["message"]
        self.assertEqual(message, "unrecognized arguments (values are not shown); usage is on stderr")


class McpRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.modules = SimpleNamespace(
            model=SimpleNamespace(
                load_registry=Mock(return_value=[{"name": "existing"}]),
                yaml_documents=lambda path: [],
                scaffold=Mock(return_value="version: 1\nname: extra\n"),
                descriptor=Mock(return_value={"role": {}}),
            ),
            render=SimpleNamespace(render=Mock(return_value={}), write=Mock(), objects=Mock(return_value=[])),
            check=SimpleNamespace(check=Mock(return_value=[])),
            identity=SimpleNamespace(admin=Mock(), configure=Mock(return_value={"planned": [], "changed": []})),
            kube=SimpleNamespace(KubeReader=Mock()),
            provision=SimpleNamespace(plan=Mock(return_value={"status": "ready"}), apply=Mock(return_value={"status": "created"})),
            status=SimpleNamespace(inspect_registration=Mock(return_value={"complete": True, "functional": "not-tested", "layers": []})),
        )

    def invoke(self, *args):
        out = io.StringIO()
        with patch.object(mcp_cli, "modules", return_value=self.modules), contextlib.redirect_stdout(out):
            code = mcp_cli.main(["--root", str(self.root), *args])
        return code, only_document(out.getvalue())

    def test_success_documents_have_ok_true(self):
        for args, expected in (
            (("check",), {"status": "valid", "scope": "offline-registration", "ok": True}),
            (("render", "--write"), {"status": "rendered", "ok": True}),
            (("render", "--check"), {"status": "current", "files": [], "ok": True}),
            (("provision", "plan", "existing"), {"status": "ready", "ok": True}),
            (("identity", "plan", "existing"), {"planned": [], "changed": [], "ok": True}),
            (("status", "existing"), {"complete": True, "functional": "not-tested", "layers": [], "ok": True}),
        ):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args), (0, expected))

    def test_add_success_and_each_refusal_code(self):
        code, document = self.invoke("add", "extra")
        self.assertEqual((code, document["ok"], document["status"]), (0, True, "definition-created"))
        # The scaffold is on disk: exclusive creation refuses to overwrite it.
        code, document = self.invoke("add", "extra")
        self.assertEqual((code, document["error"]["code"], document["error_type"]), (1, "conflict", "FileExistsError"))
        # A declaration that already names the backend.
        self.modules.model.yaml_documents = lambda path: [{"name": "extra"}]
        code, document = self.invoke("add", "extra")
        self.assertEqual((code, document["error"]["code"], document["error"]["message"]), (1, "conflict", "backend already registered"))
        self.assertEqual((document["status"], document["stage"], document["error_type"]), ("refused", "add", "ValueError"))
        self.assertEqual(self.invoke("add", "Bad_Name")[1]["error"]["code"], "invalid-arguments")
        (self.root / "infrastructure/mcp/backends/link.yaml").symlink_to(self.root)
        self.assertEqual(self.invoke("add", "other")[1]["error"]["code"], "refused")

    def test_stale_render_check_is_check_failed_with_every_file_as_proof(self):
        (self.root / "current.yaml").write_bytes(b"same")
        self.modules.render.render.return_value = {"current.yaml": b"same", "stale.yaml": b"new"}
        code, document = self.invoke("render", "--check")
        self.assertEqual((code, document["status"], document["files"], document["ok"]), (1, "stale", ["stale.yaml"], False))
        self.assertEqual(document["error"]["code"], "check-failed")
        self.assertEqual(document["error"]["proofs"], [{"path": "current.yaml", "state": "current"}, {"path": "stale.yaml", "state": "stale"}])

    def test_invalid_registration_is_check_failed_at_every_stage_that_runs_it(self):
        self.modules.check.check.return_value = ["missing JWT protection", "second"]
        for args in (("check",), ("identity", "plan", "existing"), ("status", "existing")):
            with self.subTest(args=args):
                code, document = self.invoke(*args)
                self.assertEqual((code, document["status"], document["issues"]), (1, "invalid-registration", ["missing JWT protection", "second"]))
                self.assertEqual(document["error"]["code"], "check-failed")
                self.assertEqual([p["detail"] for p in document["error"]["proofs"]], ["missing JWT protection", "second"])

    def test_provision_conflict_is_conflict_and_unknown_backend_is_not_found(self):
        self.modules.provision.plan.return_value = {"status": "conflict", "issues": ["missing encrypted dependency"]}
        code, document = self.invoke("provision", "plan", "existing")
        self.assertEqual((code, document["status"], document["issues"], document["error"]["code"]), (1, "conflict", ["missing encrypted dependency"], "conflict"))
        code, document = self.invoke("provision", "plan", "unknown")
        self.assertEqual((code, document["error"]["code"], document["status"]), (1, "not-found", "refused"))
        self.assertNotIn("uniquely", document["error"]["message"])  # a credential stage: fixed sentence

    def test_incomplete_status_is_check_failed_or_unavailable(self):
        layers = [{"layer": "Deployment", "complete": True, "state": "current"}, {"layer": "Service", "complete": False, "state": "missing"}]
        self.modules.status.inspect_registration.return_value = {"complete": False, "layers": layers}
        code, document = self.invoke("status", "existing")
        self.assertEqual((code, document["layers"], document["error"]["code"], document["error"]["proofs"]), (1, layers, "check-failed", layers))
        layers = [{"layer": "Service", "complete": False, "state": "unavailable"}]
        self.modules.status.inspect_registration.return_value = {"complete": False, "layers": layers}
        code, document = self.invoke("status", "existing")
        self.assertEqual((code, document["error"]["code"], document["error"]["retryable"]), (1, "unavailable", True))

    def test_credential_stages_never_show_exception_text(self):
        marker = "PRIVATE_CREDENTIAL_MARKER https://idp/token?code=abc"
        cases = (
            (("identity", "plan", "existing"), self.modules.identity.admin, ValueError(marker), "unavailable"),
            (("identity", "apply", "existing"), self.modules.identity.admin, RuntimeError(marker), "unavailable"),
            (("identity", "plan", "existing"), self.modules.identity.configure, ValueError(marker), "conflict"),
            (("identity", "plan", "existing"), self.modules.identity.configure, subprocess.TimeoutExpired(marker, 1), "timeout"),
            (("identity", "plan", "existing"), self.modules.identity.configure, KeyError(marker), "internal"),
            (("status", "existing"), self.modules.status.inspect_registration, ValueError(marker), "validation-failed"),
            (("status", "existing"), self.modules.status.inspect_registration, OSError(marker), "unavailable"),
            (("provision", "apply", "existing"), self.modules.provision.apply, RuntimeError(marker), "unavailable"),
            (("provision", "plan", "existing"), self.modules.provision.plan, ValueError(marker), "validation-failed"),
        )
        for args, target, exc, code in cases:
            with self.subTest(args=args, exc=type(exc).__name__):
                target.side_effect = exc
                try:
                    status, document = self.invoke(*args)
                finally:
                    target.side_effect = None
                text = json.dumps(document)
                self.assertEqual((status, document["error"]["code"], document["status"], document["error_type"]), (1, code, "refused", type(exc).__name__))
                self.assertNotIn("PRIVATE_CREDENTIAL_MARKER", text)
                self.assertNotIn("code=abc", text)
                self.assertEqual(document["error"]["retryable"], outcome.CODES[code])
                self.assertTrue(document["note"].startswith("No conflicting identity"))

    def test_keycloak_client_errors_are_refused_and_server_errors_unavailable(self):
        marker = "RESPONSE-BODY-MARKER"
        cases = (
            (400, "refused"), (401, "refused"), (403, "refused"), (404, "refused"), (409, "refused"),
            (408, "unavailable"), (429, "unavailable"),
            (500, "unavailable"), (502, "unavailable"), (503, "unavailable"),
        )
        stages = (
            (("identity", "plan", "existing"), self.modules.identity.admin, "identity-authentication"),
            (("identity", "apply", "existing"), self.modules.identity.configure, "identity"),
            (("provision", "apply", "existing"), self.modules.provision.apply, "provision"),
            (("status", "existing"), self.modules.status.inspect_registration, "status"),
        )
        for status_code, expected in cases:
            for args, target, stage in stages:
                with self.subTest(status=status_code, stage=stage):
                    target.side_effect = KeycloakHTTPError(f"Keycloak admin HTTP {status_code}; response omitted {marker}", status_code)
                    try:
                        status, document = self.invoke(*args)
                    finally:
                        target.side_effect = None
                    error = document["error"]
                    self.assertEqual((status, error["code"], error["retryable"], document["error_type"], document["stage"]), (1, expected, expected == "unavailable", "RuntimeError", stage if stage != "identity-authentication" else "identity-authentication"))
                    self.assertTrue(error["message"].endswith(f"(HTTP {status_code})"), error["message"])
                    self.assertNotIn(marker, json.dumps(document), "the exception's text is never shown")
                    self.assertEqual(error["retryable"], outcome.CODES[error["code"]])

    def test_network_failures_in_the_credential_stages_stay_unavailable(self):
        import urllib.error

        for exc, code in ((urllib.error.URLError("refused"), "unavailable"), (ConnectionResetError("reset"), "unavailable"), (TimeoutError("slow"), "timeout"), (RuntimeError("plain runtime error"), "unavailable")):
            with self.subTest(exc=type(exc).__name__):
                self.modules.identity.admin.side_effect = exc
                try:
                    status, document = self.invoke("identity", "plan", "existing")
                finally:
                    self.modules.identity.admin.side_effect = None
                self.assertEqual((status, document["error"]["code"], document["error"]["retryable"]), (1, code, True))

    def test_offline_stage_shows_the_message_and_classifies_by_type(self):
        cases = (
            (self.modules.check.check, ValueError("registry broke"), "validation-failed", "registry broke"),
            (self.modules.check.check, FileNotFoundError(2, "No such file", "kubectl"), "unavailable", None),
            (self.modules.check.check, FileNotFoundError(2, "No such file", "backends.yaml"), "not-found", None),
            (self.modules.check.check, PermissionError("denied"), "failed", None),
            (self.modules.check.check, subprocess.TimeoutExpired("kubectl", 90), "timeout", None),
            (self.modules.check.check, KeyError("k"), "internal", None),
        )
        for target, exc, code, message in cases:
            with self.subTest(exc=repr(exc)):
                target.side_effect = exc
                try:
                    status, document = self.invoke("check")
                finally:
                    target.side_effect = None
                self.assertEqual((status, document["error"]["code"], document["stage"]), (1, code, "check"))
                if message:
                    self.assertEqual(document["error"]["message"], message)

    def test_malformed_command_lines(self):
        for argv in ([], ["bogus"], ["render"], ["provision", "plan"], ["provision", "explode", "x"]):
            with self.subTest(argv=argv):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                    mcp_cli.main(argv)
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("usage:", err.getvalue())
                document = only_document(out.getvalue())
                self.assertEqual((document["ok"], document["error"]["code"], document["error"]["retryable"]), (False, "invalid-arguments", False))


class ArgumentErrorsNeverEchoWhatWasTyped(unittest.TestCase):
    """`usage_message` keeps only text the parser defines: no typed word, value or choice reaches the document."""

    MARKER = "VALUE-MARKER-9f3a"
    ENDING = "; usage is on stderr"

    def test_each_shape_of_argparse_message(self):
        m = self.MARKER
        for message, expected in (
            ("the following arguments are required: agent, --tag", "the following arguments are required: agent, --tag"),
            ("argument --max-boundaries: expected one argument", "argument --max-boundaries: the value is invalid or missing"),
            (f"argument --max-boundaries: '{m}' is not a whole number", "argument --max-boundaries: the value is invalid or missing"),
            (f"argument --consent-timeout: invalid float value: '{m}'", "argument --consent-timeout: the value is invalid or missing"),
            (f"argument --no-wait: ignored explicit argument '{m}'", "argument --no-wait: the value is invalid or missing"),
            (f"argument command: invalid choice: '{m}' (choose from 'ls', 'state')", "argument command: the value is invalid or missing (choose from 'ls', 'state')"),
            (f"argument action: invalid choice: '{m} (choose from x)' (choose from 'plan', 'apply')", "argument action: the value is invalid or missing (choose from 'plan', 'apply')"),
            (f"ambiguous option: --no={m} could match --no-wait, --no-browser", "an option was ambiguous (could match --no-wait, --no-browser)"),
            (f"ambiguous option: {m} could match could match --a, --b", "an option was ambiguous (could match --a, --b)"),
            (f"unrecognized arguments: --grant-handel -{m} {m}", "unrecognized arguments (values are not shown)"),
            (f"something argparse has not said before: {m}", "invalid arguments (the text is not shown)"),
            (f"the following: {m}", "invalid arguments (the text is not shown)"),
        ):
            with self.subTest(message=message):
                shown = outcome.usage_message(message)
                self.assertEqual(shown, expected + self.ENDING)
                self.assertNotIn(m, shown)

    def assert_echoes_nothing(self, module, cases):
        for label, argv in cases:
            with self.subTest(tool=module.__name__, case=label):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                    module.main(argv)
                self.assertEqual(caught.exception.code, 2)
                self.assertNotIn(self.MARKER, out.getvalue())
                self.assertIn(self.MARKER, err.getvalue(), "what argparse writes to stderr is unchanged")
                document = only_document(out.getvalue())
                self.assertEqual((document["ok"], document["error"]["code"]), (False, "invalid-arguments"))
                self.assertTrue(document["error"]["message"].endswith(self.ENDING), document["error"]["message"])

    def test_agent_ops(self):
        m = self.MARKER
        self.assert_echoes_nothing(
            agent_cli,
            [
                ("dash word after an unknown option", ["status", "--receipt", "r", "--grant-handel", f"-{m}"]),
                ("short option with an attached value", ["run", "sample", f"-g{m}"]),
                ("ambiguous abbreviation with =", ["run", "sample", f"--no={m}"]),
                ("invalid choice", [m]),
                ("whole-number type error", ["run", "sample", "--max-boundaries", m]),
                ("number type error", ["run", "sample", "--wait-timeout", m]),
                ("float type error", ["run", "sample", "--consent-timeout", m]),
                ("explicit value for a flag", ["run", "sample", f"--no-wait={m}"]),
                ("unrecognized value", ["ls", m]),
            ],
        )

    def test_agent_preflight(self):
        m = self.MARKER
        base = ["sample", "--source", "/s", "--tag", "t"]
        self.assert_echoes_nothing(
            preflight_cli,
            [
                ("dash word after an unknown option", [*base, "--grant-handel", f"-{m}"]),
                ("short option with an attached value", [*base, f"-g{m}"]),
                ("explicit value for a flag", [*base, f"--live={m}"]),
                ("unrecognized value", [*base, m]),
            ],
        )

    def test_mcp_registry(self):
        m = self.MARKER
        self.assert_echoes_nothing(
            mcp_cli,
            [
                ("dash word after an unknown option", ["status", "x", "--grant-handel", f"-{m}"]),
                ("short option with an attached value", ["status", "x", f"-g{m}"]),
                ("invalid command", [m]),
                ("invalid choice", ["provision", m, "x"]),
                ("explicit value for a flag", ["render", f"--check={m}"]),
                ("unrecognized value", ["check", m]),
            ],
        )


if __name__ == "__main__":
    unittest.main()
