"""`just agent run` for a release that requires a person's consent, and `just agent consent --session`.

The fake identity provider and the fake kube of the neighbouring test files; no real IdP, cluster or policy service.
What the runner pod does with a request is covered in test_agent_ops_remote_grant.py.
"""

from __future__ import annotations

import calendar
import contextlib
import functools
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_agent_ops import AGENT_BODY, RELEASE, kube_for_run, make_root
from test_agent_ops_consent import SCOPE, Browser, FakeIdp, cli

from agent_ops import delegation, live, run

ON_BEHALF_OF = AGENT_BODY.replace("mode: agent", "mode: on-behalf-of")
ACCEPTED = {"workflow_id": "session:tenant-test:sample:s", "run_id": "r", "namespace": "agents-tenant-test", "task_queue": "sessions-tenant-test"}
DEPOSITED = {"deposited": True}
OTHER_SESSION = "6b1f2f0e-3c1c-4f65-9d0a-5b0e2c7a9d41"


def stamp(seconds: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(seconds)))


def seconds(text: str) -> int:
    return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))


class Case(unittest.TestCase):
    def setUp(self):
        self.idp = FakeIdp()
        self.addCleanup(self.idp.close)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = make_root(self.tmp, agent_body=ON_BEHALF_OF)
        self.out = self.tmp / "run"
        self.said: list[str] = []
        self.consent_said: list[str] = []
        self.clock_now = [0.0]

    def browser(self, **kwargs) -> Browser:
        browser = Browser(self.idp, **kwargs)
        self.addCleanup(browser.close)
        return browser

    def kube(self, results=(), mode="on-behalf-of", required=True):
        return kube_for_run(list(results), mode, required)

    def no_sign_in(self, *args, **kwargs):
        self.fail("a sign-in was started")

    def sign_in(self, browser):
        if browser is None:
            return self.no_sign_in
        return functools.partial(delegation.sign_in, issuer=self.idp.issuer, open_url=browser)

    def submit(self, kube, browser=None, **kwargs):
        kwargs.setdefault("out", self.out)
        kwargs.setdefault("wait", False)
        kwargs.setdefault("is_tty", lambda: True)
        kwargs.setdefault("sign_in", self.sign_in(browser))
        return run.submit(self.root, "sample", {"request": "go"}, kube=kube, say=self.said.append, browser=browser is not None, **kwargs)

    def consent(self, session, browser=None, kube=None, **kwargs):
        kwargs.setdefault("run_dir", self.out)
        kwargs.setdefault("is_tty", lambda: True)
        kwargs.setdefault("sign_in", self.sign_in(browser))
        kwargs.setdefault("root", self.root)
        root = kwargs.pop("root")
        return run.consent(root, "sample", session, kube=kube or self.kube(), say=self.consent_said.append, browser=browser is not None, **kwargs)

    def start_waiting(self, kube, **kwargs):
        """Start a run that cannot sign anyone in. Returns, once it has asked for consent, a function that ends it and gives its result."""
        box = {}

        def target():
            try:
                box["result"] = self.submit(kube, is_tty=lambda: False, sleep=lambda s: time.sleep(0.005), clock=lambda: self.clock_now[0], **kwargs)
            except BaseException as exc:  # noqa: BLE001 - handed to the test's own thread
                box["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self.addCleanup(self.give_up)
        deadline = time.monotonic() + 10
        while not self.said and "error" not in box and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(self.said, box)
        self.session = self.request(kwargs.get("out", self.out))["session_id"]

        def finish():
            thread.join(10)
            self.assertFalse(thread.is_alive(), "the run is still waiting")
            if "error" in box:
                raise box["error"]
            return box["result"]

        return finish

    def give_up(self):
        """Move the waiting run's clock past its deadline."""
        self.clock_now[0] = 1e6

    def request(self, out=None) -> dict:
        return json.loads(((out or self.out) / "request.json").read_text())

    def receipt(self, out=None) -> dict:
        return json.loads(((out or self.out) / "receipt.json").read_text())

    def names(self, out=None) -> list[str]:
        return sorted(p.name for p in (out or self.out).iterdir())

    def tokens(self) -> dict:
        """The tokens of the single sign-in a test performed."""
        jwts = [t for t in self.idp.issued if t.count(".") == 2]
        self.assertIn(len(jwts), (2, 3))
        return {"access": jwts[0], "id": jwts[1], "refresh": jwts[2] if len(jwts) == 3 else None}

    def secrets(self) -> set[str]:
        seen = set(self.idp.issued) | set(self.idp.verifiers)
        for token in [t for t in self.idp.issued if t.count(".") == 2]:
            seen.update(token.split("."))
        seen.discard("")
        return seen

    def assert_secrets_only_on_stdin(self, kube, call: int, *texts: str) -> None:
        """Every code, verifier, token and token segment is absent from files, command lines and the given texts; the token went to one exec's stdin."""
        secrets_seen = self.secrets()
        self.assertGreaterEqual(len(secrets_seen), 8)
        haystacks = [(str(p), p.read_bytes().decode("utf-8", "replace")) for p in self.tmp.rglob("*") if p.is_file()]
        haystacks += [(f"text {i}", text) for i, text in enumerate(texts)]
        haystacks += [("said", "\n".join(self.said + self.consent_said)), ("argv", json.dumps(kube.argvs))]
        for where, text in haystacks:
            for secret in secrets_seen:
                self.assertNotIn(secret, text, where)
        access = self.tokens()["access"].encode()
        self.assertEqual([i for i, stdin in enumerate(kube.stdins) if access in stdin], [call])
        for argv in kube.argvs:
            self.assertEqual(argv, [run.PYTHON, "-c", run.BOOTSTRAP, str(len(run.REMOTE.read_bytes()))])


class IdentityRowTests(Case):
    """One test per row of the identity table: who is asked, and what the runner pod is sent."""

    def assert_never_asked(self, kube, **kwargs):
        for name, is_tty in (("terminal", True), ("no-terminal", False)):
            with self.subTest(name):
                out = self.tmp / name
                code, envelope = self.submit(kube, out=out, is_tty=lambda v=is_tty: v, **kwargs)
                self.assertEqual((code, envelope["status"]), (0, "SUBMITTED"))
                self.assertIsNone(self.receipt(out)["consent"])
                self.assertEqual(self.names(out), ["receipt.json", "request.json"])
        self.assertEqual((self.said, self.idp.calls), ([], []))
        for sent in kube.exec_calls:
            self.assertEqual(sent["action"], "submit")
            self.assertEqual(set(sent) & {"deposit", "deposited_grant"}, set())
        return kube.exec_calls

    def test_own_identity_agent_is_never_asked(self):
        calls = self.assert_never_asked(self.kube([ACCEPTED, ACCEPTED], "agent", False))
        self.assertEqual([c["grant_handle"] for c in calls], [None, None])
        self.assertEqual((self.receipt(self.tmp / "terminal")["identity"], self.receipt(self.tmp / "terminal")["delegated"]), ("agent", False))

    def test_optional_delegation_without_a_handle_is_never_asked(self):
        calls = self.assert_never_asked(self.kube([ACCEPTED, ACCEPTED], "on-behalf-of", False))
        self.assertEqual([c["grant_handle"] for c in calls], [None, None])
        self.assertEqual((self.receipt(self.tmp / "terminal")["identity"], self.receipt(self.tmp / "terminal")["delegated"]), ("on-behalf-of", False))

    def test_required_delegation_with_a_grant_handle_is_never_asked(self):
        calls = self.assert_never_asked(self.kube([ACCEPTED, ACCEPTED]), grant_handle="h-1")
        self.assertEqual([c["grant_handle"] for c in calls], ["h-1", "h-1"])
        self.assertEqual(self.receipt(self.tmp / "terminal")["delegated"], True)
        for path in self.tmp.rglob("*.json"):
            self.assertNotIn("h-1", path.read_text())

    def test_required_delegation_from_a_terminal_signs_in_and_deposits_and_submits_in_one_call(self):
        kube, browser = self.kube([ACCEPTED]), self.browser()
        now = float(int(time.time()))
        code, envelope = self.submit(kube, browser, now=lambda: now)
        self.assertEqual((code, envelope["status"]), (0, "SUBMITTED"))
        self.assertEqual(browser.params["prompt"], "consent", "an open Keycloak session is reused; the consent screen is still shown")
        self.assertEqual(browser.params["scope"].split(), ["openid", "agent-policy-service", SCOPE])
        tokens = self.tokens()
        session = self.request()["session_id"]
        self.assertEqual(len(kube.exec_calls), 1, "the deposit and the start are one remote call")
        sent = kube.exec_calls[0]
        self.assertEqual(sent["deposit"], {"access_token": tokens["access"], "refresh_token": tokens["refresh"], "expires_at": stamp(now + 8 * 3600)})
        self.assertEqual((sent["action"], sent["session_id"], sent["grant_handle"], "deposited_grant" in sent), ("submit", session, None, False))
        receipt = self.receipt()
        self.assertEqual((receipt["identity"], receipt["delegated"], receipt["sessionId"]), ("on-behalf-of", True, session))
        self.assertEqual(receipt["consent"], {"mode": "inline", "subject": "user-1", "subjectSource": "verified access token", "refreshTokenIssued": True, "grantExpiresAt": stamp(now + 8 * 3600)})
        self.assertEqual(set(self.request()), {"action", "tenant", "agent", "release", "session_id", "task", "max_boundaries"})
        self.assertEqual(self.names(), ["receipt.json", "request.json"])
        self.assertIn(f"sample (tenant tenant-test, release {RELEASE}) will act as you for session {session}", self.said[0])
        self.assertEqual(len(self.said), 2)
        self.assert_secrets_only_on_stdin(kube, 0, json.dumps(envelope))

    def test_required_delegation_without_a_terminal_waits_for_the_consent_command(self):
        kube, browser = self.kube([DEPOSITED, ACCEPTED]), self.browser()
        finish = self.start_waiting(kube)
        self.assertEqual(len(self.said), 1, "one line tells the operator what the person has to run")
        self.assertEqual(self.idp.calls, [], "the run itself signs nobody in")
        self.assertEqual(kube.exec_calls, [])
        command = self.said[0].split("in a terminal on this machine: ", 1)[1]
        self.assertEqual(command, f"just agent consent sample --session {self.session} --run-dir {self.out}")
        # The person runs exactly what was printed, in their own terminal.
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(delegation, "ISSUER", self.idp.issuer),
            patch.object(delegation, "interactive", lambda: True),
            patch.object(delegation.webbrowser, "open", browser),
            patch.object(live, "Kube", lambda: kube),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(["--root", str(self.root), *command.split()[2:], "--browser"])
            result = finish()
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual((result[0], result[1]["status"]), (0, "SUBMITTED"))
        self.assertEqual(browser.params["prompt"], "consent")
        tokens = self.tokens()
        report = json.loads(out.getvalue())
        self.assertEqual({k: report[k] for k in ("agent", "tenant", "sessionId", "deposited", "subject", "preferredUsername", "refreshTokenIssued", "runDir")}, {"agent": "sample", "tenant": "tenant-test", "sessionId": self.session, "deposited": True, "subject": "user-1", "preferredUsername": "person", "refreshTokenIssued": True, "runDir": str(self.out)})
        self.assertIn('Task: {"request": "go"}', err.getvalue())
        self.assertEqual([c["action"] for c in kube.exec_calls], ["deposit", "submit"])
        deposit, submitted = kube.exec_calls
        self.assertEqual(deposit, {"action": "deposit", "tenant": "tenant-test", "agent": "sample", "session_id": self.session, "deposit": {"access_token": tokens["access"], "refresh_token": tokens["refresh"], "expires_at": report["grantExpiresAt"]}})
        self.assertTrue(0 <= seconds(report["grantExpiresAt"]) - (time.time() + 8 * 3600 - 30) <= 31)
        self.assertEqual((submitted["deposited_grant"], submitted["grant_handle"], submitted["session_id"], "deposit" in submitted), (True, None, self.session, False))
        record = json.loads((self.out / "consent.json").read_text())
        self.assertEqual({k: v for k, v in record.items() if k != "depositedAt"}, {"schemaVersion": 1, "sessionId": self.session, "agent": "sample", "tenant": "tenant-test", "subject": "user-1", "refreshTokenIssued": True, "grantExpiresAt": report["grantExpiresAt"]})
        self.assertEqual(self.receipt()["consent"], {"mode": "awaited", "subject": "user-1", "subjectSource": "consent command record", "refreshTokenIssued": True, "grantExpiresAt": report["grantExpiresAt"]})
        self.assertEqual(self.receipt()["delegated"], True)
        self.assertEqual(self.names(), ["consent.json", "deposit.lock", "receipt.json", "request.json", "waiting.lock"])
        for name in self.names():
            self.assertEqual(oct(os.stat(self.out / name).st_mode & 0o777), "0o600", name)
        self.assert_secrets_only_on_stdin(kube, 0, out.getvalue(), err.getvalue(), json.dumps(result[1]))


class RunWaitTests(Case):
    def test_await_consent_makes_a_run_at_a_terminal_wait_instead_of_signing_in(self):
        kube = self.kube()
        code, envelope = self.submit(kube, await_consent=True, clock=iter([0, 1000]).__next__, sleep=lambda s: self.fail("slept past the deadline"))
        self.assertEqual(code, run.NO_CONSENT)
        self.assertEqual(len(self.said), 1)
        self.assertIn("just agent consent sample --session", self.said[0])

    def test_nobody_consents_in_time_exits_3_and_nothing_was_deposited_or_submitted(self):
        kube = self.kube()
        code, envelope = self.submit(kube, is_tty=lambda: False, consent_timeout=120, clock=iter([0, 1000]).__next__, sleep=lambda s: self.fail("slept past the deadline"))
        self.assertEqual((code, run.NO_CONSENT), (3, 3))
        session = self.request()["session_id"]
        self.assertEqual(envelope, {"status": "NOT_SUBMITTED", "reason": "no consent arrived in time; nothing was deposited or submitted", "sessionId": session, "dir": str(self.out), "timeoutSeconds": 120})
        self.assertEqual(json.loads((self.out / "status.json").read_text()), envelope)
        self.assertEqual((kube.exec_calls, self.idp.calls), ([], []))
        self.assertEqual(self.names(), ["deposit.lock", "request.json", "status.json", "waiting.lock"])
        self.assertIn("Within 120 seconds", self.said[0])
        # A consent that arrives after the run gave up is refused before anyone signs in.
        browser = self.browser()
        with self.assertRaisesRegex(delegation.ConsentError, "no longer waiting for consent; nothing was deposited"):
            self.consent(session, browser, kube)
        self.assertEqual((browser.opened, kube.exec_calls, self.idp.calls), (0, [], []))

    def test_a_record_written_as_the_deadline_passes_is_honoured(self):
        kube = self.kube([ACCEPTED])
        ticks = iter([0, 1000])

        def clock():
            tick = next(ticks)
            if tick:  # the consent command finished between the run's last look and its giving up
                session = self.request()["session_id"]
                (self.out / "consent.json").write_text(json.dumps({"sessionId": session, "subject": "user-1", "refreshTokenIssued": True, "grantExpiresAt": "2030-01-01T00:00:00Z"}))
            return tick

        code, envelope = self.submit(kube, is_tty=lambda: False, clock=clock)
        self.assertEqual((code, envelope["status"]), (0, "SUBMITTED"))
        self.assertEqual(kube.exec_calls[0]["deposited_grant"], True)
        self.assertFalse((self.out / "status.json").exists())

    def test_a_record_for_another_session_is_not_taken_as_consent(self):
        kube = self.kube([ACCEPTED])
        self.out.mkdir(parents=True)
        # `submit` creates its directory itself, so plant the record from the first sleep instead.
        self.out.rmdir()

        def sleep(_):
            (self.out / "consent.json").write_text(json.dumps({"sessionId": OTHER_SESSION, "subject": "user-1"}))

        with self.assertRaisesRegex(run.RunError, "is not a consent record for this session"):
            self.submit(kube, is_tty=lambda: False, sleep=sleep, clock=lambda: 0)
        self.assertEqual(kube.exec_calls, [])
        self.assertFalse((self.out / "receipt.json").exists())

    def test_sign_in_not_completed_at_a_terminal_exits_3_and_nothing_was_deposited_or_submitted(self):
        kube = self.kube()
        sign_in = functools.partial(delegation.sign_in, issuer=self.idp.issuer, clock=iter([0, 1000]).__next__)
        code, envelope = self.submit(kube, sign_in=sign_in, consent_timeout=60)
        self.assertEqual(code, 3)
        self.assertEqual((envelope["status"], envelope["reason"], envelope["timeoutSeconds"]), ("NOT_SUBMITTED", "the sign-in was not completed in time; nothing was deposited or submitted", 60))
        self.assertEqual((kube.exec_calls, self.idp.calls), ([], []))
        self.assertEqual(self.names(), ["request.json", "status.json"])

    def test_consent_recorded_but_no_grant_held_exits_1_without_a_receipt(self):
        kube, browser = self.kube([DEPOSITED, lambda request: {"granted": False, "session_id": request["session_id"]}]), self.browser()
        finish = self.start_waiting(kube)
        self.assertEqual(self.consent(self.session, browser, kube)[0], 0)
        code, envelope = finish()
        self.assertEqual((code, envelope["status"]), (1, "NOT_SUBMITTED"))
        self.assertIn("no longer holds a grant for this session", envelope["reason"])
        self.assertEqual(envelope["consent"]["mode"], "awaited")
        self.assertFalse((self.out / "receipt.json").exists())
        self.assertEqual(json.loads((self.out / "status.json").read_text()), envelope)
        self.assertEqual([c["action"] for c in kube.exec_calls], ["deposit", "submit"])

    def test_default_run_directory_is_found_by_session_id(self):
        kube, browser = self.kube([DEPOSITED, ACCEPTED]), self.browser()
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.tmp / "state")}):
            finish = self.start_waiting(kube, out=None)
            self.assertNotIn("--run-dir", self.said[0])
            self.assertTrue(self.said[0].endswith(f"just agent consent sample --session {self.session}"))
            code, report = self.consent(self.session, browser, kube, run_dir=None)
            result = finish()
        self.assertEqual((code, result[0]), (0, 0))
        self.assertTrue(report["runDir"].startswith(str(self.tmp / "state/kubani/agent-runs/sample/")))
        self.assertTrue(report["runDir"].endswith("-" + self.session[:8]))

    def request(self, out=None) -> dict:
        if out is None and not self.out.exists():
            (out,) = (self.tmp / "state/kubani/agent-runs/sample").iterdir()
        return super().request(out)


class RunRefusalTests(Case):
    def test_await_consent_is_refused_when_no_consent_would_be_asked(self):
        for mode, required, grant in (("agent", False, None), ("on-behalf-of", False, None), ("on-behalf-of", True, "h-1")):
            kube = self.kube([ACCEPTED], mode, required)
            with self.assertRaisesRegex(run.RunError, "--await-consent applies only when the release requires delegation and no --grant-handle is given"):
                self.submit(kube, await_consent=True, grant_handle=grant)
            self.assertEqual((kube.exec_calls, self.out.exists(), self.said), ([], False, []))

    def test_consent_timeout_bounds_are_refused_before_anything_exists(self):
        for timeout in (0, -1, delegation.MAX_TIMEOUT + 1):
            for is_tty in (True, False):
                kube = self.kube()
                with self.assertRaisesRegex(run.RunError, "--consent-timeout must be above 0 and at most 900 seconds"):
                    self.submit(kube, consent_timeout=timeout, is_tty=lambda v=is_tty: v)
                self.assertEqual((kube.exec_calls, self.out.exists(), self.said), ([], False, []))

    def test_a_token_the_policy_service_would_refuse_is_never_sent(self):
        scenarios = {
            "scope": (lambda t: t["access"].update(scope="openid agent-policy-service"), f"scope does not include {SCOPE}"),
            "may_act": (lambda t: t["access"].pop("may_act"), "no may_act.sub"),
            "audience": (lambda t: t["access"].update(aud=["account"]), "audience does not include agent-policy-service"),
            "agent token": (lambda t: t["access"].update(client_type="agent"), "client_type agent"),
        }
        for name, (mutate, expected) in scenarios.items():
            with self.subTest(name):
                self.idp.mutate = mutate
                kube, out = self.kube([ACCEPTED]), self.tmp / name.replace(" ", "-")
                with self.assertRaises(run.RunError) as caught:
                    self.submit(kube, self.browser(), out=out)
                self.assertIn("would not be accepted for deposit, so nothing was deposited or submitted", str(caught.exception))
                self.assertIn(expected, str(caught.exception))
                self.assertEqual((kube.exec_calls, self.names(out)), ([], ["request.json"]))
                for secret in self.secrets():
                    self.assertNotIn(secret, str(caught.exception))

    def test_refused_at_keycloak_or_without_pyjwt_nothing_is_sent(self):
        kube = self.kube([ACCEPTED])
        with self.assertRaisesRegex(delegation.ConsentError, "Keycloak returned the error access_denied"):
            self.submit(kube, self.browser(error="access_denied"))
        self.assertEqual((kube.exec_calls, self.names()), ([], ["request.json"]))
        with patch.dict(sys.modules, {"jwt": None}):
            with self.assertRaisesRegex(delegation.ConsentError, "PyJWT is not installed"):
                self.submit(kube, self.browser(), out=self.tmp / "b")
            self.assertEqual((kube.exec_calls, (self.tmp / "b").exists(), len(self.said)), ([], False, 2))
            # Only a sign-in needs PyJWT: a run that asks nobody, and a run that waits, start without it.
            self.assertEqual(self.submit(self.kube([ACCEPTED], "agent", False), out=self.tmp / "c")[0], 0)
            self.assertEqual(self.submit(self.kube(), is_tty=lambda: False, out=self.tmp / "d", clock=iter([0, 1000]).__next__)[0], 3)

    def test_a_deposit_the_policy_service_refuses_is_reported_and_leaves_no_receipt(self):
        refusal = "deposit refused: the token names no agent allowed to act for the person"
        kube = self.kube([{"error": refusal}])
        with self.assertRaisesRegex(run.RunError, "remote submit failed: " + refusal):
            self.submit(kube, self.browser())
        self.assertEqual(len(kube.exec_calls), 1)
        self.assertEqual(self.names(), ["request.json"])
        self.assert_secrets_only_on_stdin(kube, 0)

    def test_an_unanswered_remote_call_says_its_outcome_is_unknown(self):
        def unanswered(request):
            raise subprocess.TimeoutExpired("kubectl", run.EXEC_TIMEOUT)

        kube = self.kube([unanswered])
        with self.assertRaisesRegex(run.RunError, "remote submit did not answer within 60 seconds; whether it took effect is not known"):
            self.submit(kube, self.browser())
        self.assertEqual(self.names(), ["request.json"])
        self.assert_secrets_only_on_stdin(kube, 0)


class ConsentCommandTests(Case):
    def planted(self, *names: str, session: str = OTHER_SESSION, agent: str = "sample") -> Path:
        """A run directory as a `run` would have left it, without a live run behind it."""
        out = self.tmp / "planted"
        out.mkdir()
        (out / "request.json").write_text(json.dumps({"session_id": session, "agent": agent, "tenant": "tenant-test", "release": RELEASE, "task": {"request": "go"}}))
        for name in names:
            (out / name).write_text("{}")
        return out

    def refused(self, session, **kwargs) -> str:
        browser, kube = self.browser(), self.kube([DEPOSITED])
        before = (len(self.idp.calls), len(self.consent_said))
        with self.assertRaises(delegation.ConsentError) as caught:
            self.consent(session, browser, kube, **kwargs)
        self.assertEqual((browser.opened, kube.exec_calls, (len(self.idp.calls), len(self.consent_said))), (0, [], before))
        return str(caught.exception)

    def test_refused_without_a_terminal_and_for_an_own_identity_agent(self):
        out = self.planted("waiting.lock")
        self.assertIn("stdin, stdout and stderr must all be a TTY", self.refused(OTHER_SESSION, run_dir=out, is_tty=lambda: False))
        own = make_root(self.tmp / "own")
        self.assertIn("declares identity mode 'agent'", self.refused(OTHER_SESSION, run_dir=out, root=own, is_tty=lambda: self.fail("the TTY check ran")))
        for timeout in (0, -1, delegation.MAX_TIMEOUT + 1):
            self.assertIn("--timeout must be above 0", self.refused(OTHER_SESSION, run_dir=out, timeout=timeout))

    def test_refused_unless_a_live_run_on_this_machine_waits_for_that_session(self):
        for bad in ("x", "", OTHER_SESSION.upper(), OTHER_SESSION.replace("-", ""), OTHER_SESSION + "/.."):
            self.assertIn("a lower-case UUID", self.refused(bad, run_dir=self.planted("waiting.lock")))
            (self.tmp / "planted/request.json").unlink()
            (self.tmp / "planted/waiting.lock").unlink()
            (self.tmp / "planted").rmdir()
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.tmp / "state")}):
            self.assertIn(f"no run of sample on this machine is waiting for consent to session {OTHER_SESSION}", self.refused(OTHER_SESSION, run_dir=None))
        self.assertIn("no run of sample on this machine is waiting", self.refused(OTHER_SESSION, run_dir=self.tmp / "absent"))
        out = self.planted("waiting.lock", session="11111111-2222-4333-8444-555555555555")
        self.assertIn("no run of sample on this machine is waiting", self.refused(OTHER_SESSION, run_dir=out), "the directory belongs to another session")
        (out / "request.json").write_text(json.dumps({"session_id": OTHER_SESSION, "agent": "other", "tenant": "tenant-test"}))
        self.assertIn("no run of sample on this machine is waiting", self.refused(OTHER_SESSION, run_dir=out), "the directory belongs to another agent")

    def test_refused_when_the_run_is_over_or_consent_was_already_given(self):
        states = {
            (): "this run is not waiting for consent; nothing was deposited",
            ("waiting.lock",): "the run that asked for this consent has ended; nothing was deposited",
            ("waiting.lock", "receipt.json"): "this run is no longer waiting for consent; nothing was deposited",
            ("waiting.lock", "status.json"): "this run is no longer waiting for consent; nothing was deposited",
            ("waiting.lock", "consent.json"): "consent was already given for this session; nothing was deposited",
        }
        for names, expected in states.items():
            with self.subTest(names):
                out = self.planted(*names)
                self.assertEqual(self.refused(OTHER_SESSION, run_dir=out), expected)
                for path in out.iterdir():
                    path.unlink()
                out.rmdir()

    def test_a_second_consent_to_a_waiting_run_is_refused(self):
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        # What a consent command that died mid-write leaves: not the record, and no obstacle to the next one.
        (self.out / "consent.json.tmp").write_text("{}")
        self.assertEqual(self.consent(self.session, self.browser(), kube)[0], 0)
        self.assertEqual(self.refused(self.session), "consent was already given for this session; nothing was deposited")
        self.assertEqual(finish()[0], 0)
        self.assertEqual(self.refused(self.session), "consent was already given for this session; nothing was deposited")
        self.assertEqual([c["action"] for c in kube.exec_calls], ["deposit", "submit"])
        self.assertFalse((self.out / "consent.json.tmp").exists())

    def waiting_run_is_untouched(self, kube, finish, calls=()):
        """The consent attempt left the run waiting; it then gives up with nothing submitted."""
        self.assertEqual([c["action"] for c in kube.exec_calls], list(calls))
        self.assertFalse((self.out / "consent.json").exists())
        self.give_up()
        code, envelope = finish()
        self.assertEqual((code, envelope["status"]), (3, "NOT_SUBMITTED"))
        self.assertFalse((self.out / "receipt.json").exists())

    def test_a_token_the_policy_service_would_refuse_is_not_deposited(self):
        kube = self.kube([DEPOSITED])
        finish = self.start_waiting(kube)
        self.idp.mutate = lambda t: t["access"].update(scope="openid")
        code, report = self.consent(self.session, self.browser(), kube)
        self.assertEqual((code, report["deposited"], report["subject"], len(report["missing"])), (1, False, "user-1", 1))
        self.assertIn(SCOPE, report["missing"][0])
        self.waiting_run_is_untouched(kube, finish)
        for secret in self.secrets():
            self.assertNotIn(secret, json.dumps(report) + "\n".join(self.consent_said))

    def test_sign_in_not_completed_exits_124_and_deposits_nothing(self):
        kube = self.kube([DEPOSITED])
        finish = self.start_waiting(kube)
        sign_in = functools.partial(delegation.sign_in, issuer=self.idp.issuer, clock=iter([0, 1000]).__next__)
        code, report = self.consent(self.session, kube=kube, sign_in=sign_in, timeout=45)
        self.assertEqual((code, report), (124, {"agent": "sample", "tenant": "tenant-test", "sessionId": self.session, "runDir": str(self.out), "deposited": False, "timedOut": True, "timeoutSeconds": 45}))
        self.waiting_run_is_untouched(kube, finish)

    def test_a_refused_or_unanswered_deposit_writes_no_record(self):
        def unanswered(request):
            raise subprocess.TimeoutExpired("kubectl", run.EXEC_TIMEOUT)

        kube = self.kube([{"error": "deposit refused: this session already has a grant"}, unanswered, {"deposited": False}])
        finish = self.start_waiting(kube)
        with self.assertRaisesRegex(run.RunError, "remote deposit failed: deposit refused: this session already has a grant"):
            self.consent(self.session, self.browser(), kube)
        with self.assertRaisesRegex(run.RunError, "remote deposit did not answer within 60 seconds; whether it took effect is not known"):
            self.consent(self.session, self.browser(), kube)
        with self.assertRaisesRegex(run.RunError, "did not confirm the deposit"):
            self.consent(self.session, self.browser(), kube)
        self.assertEqual(sorted(p.name for p in self.out.iterdir() if p.name.startswith("consent")), [])
        self.waiting_run_is_untouched(kube, finish, ["deposit", "deposit", "deposit"])
        for secret in self.secrets():
            for path in self.tmp.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret, path.read_bytes().decode("utf-8", "replace"), path)

    def test_the_task_is_shown_before_the_sign_in_and_a_long_one_is_cut(self):
        kube = self.kube([DEPOSITED, ACCEPTED])
        box = {}
        thread = threading.Thread(target=lambda: box.update(result=run.submit(self.root, "sample", {"request": "x" * 5000}, kube=kube, say=self.said.append, out=self.out, wait=False, is_tty=lambda: False, sleep=lambda s: time.sleep(0.005))), daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not self.said and time.monotonic() < deadline:
            time.sleep(0.005)
        session = self.request()["session_id"]
        self.assertEqual(self.consent(session, self.browser(), kube)[0], 0)
        thread.join(10)
        self.assertEqual(box["result"][0], 0)
        self.assertTrue(self.consent_said[0].startswith('Task: {"request": "xxxx'))
        self.assertIn(f"characters; the whole task is in {self.out / 'request.json'})", self.consent_said[0])
        self.assertLess(len(self.consent_said[0]), 2300)
        self.assertIn(f"will act as you for session {session}, on the task above", self.consent_said[1])
        self.assertTrue(self.consent_said[2].startswith(self.idp.issuer + delegation.AUTH_PATH))


class RefreshTokenTests(Case):
    """Whether Keycloak issues `agent-cli` a refresh token is not known, so both answers are handled and said."""

    def test_without_a_refresh_token_the_grant_ends_with_the_access_token_and_both_commands_say_so(self):
        self.idp.refresh = False
        kube = self.kube([ACCEPTED])
        before = int(time.time())
        self.submit(kube, self.browser())
        sent = kube.exec_calls[0]["deposit"]
        self.assertIsNone(sent["refresh_token"])
        self.assertTrue(before + 300 <= seconds(sent["expires_at"]) <= int(time.time()) + 300, "the access token's own expiry")
        consent = self.receipt()["consent"]
        self.assertEqual((consent["refreshTokenIssued"], consent["grantExpiresAt"]), (False, sent["expires_at"]))
        self.assertEqual(self.said[2], f"Keycloak issued no refresh token: sample can act for you only until the access token expires at {sent['expires_at']}.")

    def test_consent_command_without_a_refresh_token(self):
        self.idp.refresh = False
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        before = int(time.time())
        code, report = self.consent(self.session, self.browser(), kube)
        finish()
        sent = kube.exec_calls[0]["deposit"]
        self.assertEqual((code, sent["refresh_token"], report["refreshTokenIssued"], report["grantExpiresAt"]), (0, None, False, sent["expires_at"]))
        self.assertTrue(before + 300 <= seconds(sent["expires_at"]) <= int(time.time()) + 300)
        self.assertIn("only until the access token expires", report["note"])
        self.assertEqual(self.receipt()["consent"]["refreshTokenIssued"], False)

    def test_with_a_refresh_token_there_is_no_note(self):
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        code, report = self.consent(self.session, self.browser(), kube)
        finish()
        self.assertNotIn("note", report)


class CommandLineTests(Case):
    """Through `agent-ops.py` itself."""

    def run_cli(self, argv, kube, browser=None, interactive=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(delegation, "ISSUER", self.idp.issuer))
            stack.enter_context(patch.object(live, "Kube", lambda: kube))
            if interactive is not None:
                stack.enter_context(patch.object(delegation, "interactive", lambda: interactive))
            if browser is not None:
                stack.enter_context(patch.object(delegation.webbrowser, "open", browser))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = cli.main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_run_under_a_test_runner_is_not_at_a_terminal_and_exits_3(self):
        kube = self.kube()
        started = time.monotonic()
        code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--consent-timeout", "0.05", "--out", str(self.out)], kube)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(code, 3)
        envelope = json.loads(out)
        self.assertEqual((envelope["status"], envelope["timeoutSeconds"]), ("NOT_SUBMITTED", 0.05))
        self.assertEqual(len(err.splitlines()), 1)
        self.assertIn(f"just agent consent sample --session {envelope['sessionId']} --run-dir {self.out}", err)
        self.assertEqual((kube.exec_calls, self.idp.calls), ([], []))

    def test_run_at_a_terminal_signs_in_and_nothing_secret_reaches_output_or_a_file(self):
        kube, browser = self.kube([ACCEPTED]), self.browser()
        code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--browser", "--out", str(self.out)], kube, browser, interactive=True)
        self.assertEqual(code, 0, err)
        envelope = json.loads(out)
        self.assertEqual((envelope["status"], envelope["receipt"]["consent"]["mode"], envelope["receipt"]["consent"]["subject"]), ("SUBMITTED", "inline", "user-1"))
        self.assertIn(self.idp.issuer + delegation.AUTH_PATH, err)
        self.assert_secrets_only_on_stdin(kube, 0, out, err)

    def test_refusals_exit_2_with_one_line_and_no_document(self):
        self.idp.mutate = lambda t: t["access"].update(scope="openid")
        kube = self.kube([ACCEPTED])
        code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--browser", "--out", str(self.out)], kube, self.browser(), interactive=True)
        self.assertEqual((code, out, kube.exec_calls), (2, "", []))
        self.assertTrue(err.splitlines()[-1].startswith("refused: the token Keycloak issued would not be accepted for deposit"))
        for secret in self.secrets():
            self.assertNotIn(secret, err)
        code, out, err = self.run_cli(["run", "sample", "--task", "go", "--await-consent", "--out", str(self.tmp / "b")], self.kube([ACCEPTED], "agent", False))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("refused: --await-consent applies only", err)
        code, out, err = self.run_cli(["consent", "sample", "--session", OTHER_SESSION, "--run-dir", str(self.tmp / "absent")], kube, self.browser(), interactive=True)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("refused: no run of sample on this machine is waiting", err)
        code, out, err = self.run_cli(["consent", "sample", "--session", OTHER_SESSION], kube)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("must all be a TTY", err)


if __name__ == "__main__":
    unittest.main()
