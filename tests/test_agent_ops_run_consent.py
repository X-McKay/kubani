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
import shlex
import stat
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from test_agent_ops import AGENT_BODY, RELEASE, kube_for_run, make_root
from test_agent_ops_consent import SCOPE, Browser, FakeIdp, Stream, cli

from agent_ops import delegation, live, run

ON_BEHALF_OF = AGENT_BODY.replace("mode: agent", "mode: on-behalf-of")
ACCEPTED = {"workflow_id": "session:tenant-test:sample:s", "run_id": "r", "namespace": "agents-tenant-test", "task_queue": "sessions-tenant-test"}
DEPOSITED = {"deposited": True}
OTHER_SESSION = "6b1f2f0e-3c1c-4f65-9d0a-5b0e2c7a9d41"
NOTHING_SENT = "no token was sent to the cluster and no workflow was started"
NEVER_DEPOSITED = "no consent command reached the deposit step and no workflow was started"


def interrupted(*args, **kwargs):
    raise KeyboardInterrupt


def foreign(real):
    """A stat seam that reports the real entry as owned by another account."""

    def stat_as_another_account(target):
        held = real(target)
        return types.SimpleNamespace(st_mode=held.st_mode, st_uid=held.st_uid + 1)

    return stat_as_another_account


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

    def status(self, out=None) -> dict:
        return json.loads(((out or self.out) / "status.json").read_text())

    def digest(self, session, task=None, **changed) -> str:
        """The digest of what this file's runs submit, or of that with one part changed."""
        shown = dict({"tenant": "tenant-test", "agent": "sample", "release": RELEASE, "session": session, "task": task or {"request": "go"}}, **changed)
        return run.shown_digest(**shown)

    def record(self, session, **changed) -> dict:
        """A consent record as the consent command writes it for this file's runs."""
        return dict({"schemaVersion": 1, "sessionId": session, "agent": "sample", "tenant": "tenant-test", "shownSha256": self.digest(session), "subject": "user-1", "refreshTokenIssued": True, "grantRequestedUntil": "2030-01-01T00:00:00Z"}, **changed)

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

    def test_the_run_directory_is_exactly_0700_whatever_the_umask(self):
        """`consent` trusts a run directory only at mode 0700, so `run` must not leave the mode to the umask."""
        for umask in (0o000, 0o100):  # under 0o100 a bare mkdir(mode=0o700) gives 0600
            with self.subTest(umask=oct(umask)):
                out = self.tmp / f"umask-{umask:o}"
                before = os.umask(umask)
                try:
                    self.submit(self.kube([ACCEPTED], "agent", False), out=out)
                finally:
                    os.umask(before)
                self.assertEqual(stat.S_IMODE(os.stat(out).st_mode), 0o700)

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
        said_before_the_browser = []

        def opened(url):
            said_before_the_browser.extend(self.said)
            browser(url)

        code, envelope = self.submit(kube, browser, now=lambda: now, sign_in=functools.partial(delegation.sign_in, issuer=self.idp.issuer, open_url=opened))
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
        self.assertEqual(receipt["consent"], {"mode": "inline", "subject": "user-1", "subjectSource": "verified access token", "refreshTokenIssued": True, "grantRequestedUntil": stamp(now + 8 * 3600)})
        self.assertEqual(set(self.request()), {"action", "tenant", "agent", "release", "session_id", "task", "max_boundaries"})
        self.assertEqual(self.names(), ["receipt.json", "request.json"])
        # The person is shown the task, then who will act for them and for which session, before the URL is opened.
        self.assertEqual(self.said[0], 'Task: {"request": "go"}')
        self.assertTrue(self.said[1].startswith(f"sample (tenant tenant-test, release {RELEASE}) will act as you for session {session}, on the task above"))
        self.assertTrue(self.said[2].startswith(self.idp.issuer + delegation.AUTH_PATH))
        self.assertEqual(said_before_the_browser, self.said[:3])
        self.assertEqual(self.said[3:], ["Signed in as person."])
        self.assertEqual(oct(os.stat(self.out).st_mode & 0o777), "0o700")
        self.assert_secrets_only_on_stdin(kube, 0, json.dumps(envelope))

    def test_the_account_that_signed_in_is_named_by_username_or_else_by_subject(self):
        self.idp.mutate = lambda t: t["access"].pop("preferred_username", None)
        self.assertEqual(self.submit(self.kube([ACCEPTED]), self.browser())[0], 0)
        self.assertEqual(self.said[3], "Signed in as user-1.")
        self.idp.mutate = lambda t: t["access"].update(preferred_username="per\x1b[2Json\n")
        self.assertEqual(self.submit(self.kube([ACCEPTED]), self.browser(), out=self.tmp / "b")[0], 0)
        self.assertEqual(self.said[-1], "Signed in as per?[2Json?.", "what Keycloak put in the claim cannot move the cursor or start a line")

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
        shown = err.getvalue().splitlines()
        self.assertEqual(shown[0], 'Task: {"request": "go"}')
        self.assertTrue(shown[1].startswith(f"sample (tenant tenant-test, release {RELEASE}) will act as you for session {self.session}, on the task above"))
        self.assertEqual(shown[3:], ["Signed in as person."])
        self.assertEqual([c["action"] for c in kube.exec_calls], ["deposit", "submit"])
        deposit, submitted = kube.exec_calls
        self.assertEqual(deposit, {"action": "deposit", "tenant": "tenant-test", "agent": "sample", "session_id": self.session, "deposit": {"access_token": tokens["access"], "refresh_token": tokens["refresh"], "expires_at": report["grantRequestedUntil"]}})
        self.assertTrue(0 <= seconds(report["grantRequestedUntil"]) - (time.time() + 8 * 3600 - 30) <= 31)
        self.assertEqual((submitted["deposited_grant"], submitted["grant_handle"], submitted["session_id"], "deposit" in submitted), (True, None, self.session, False))
        record = json.loads((self.out / "consent.json").read_text())
        self.assertEqual({k: v for k, v in record.items() if k != "depositedAt"}, self.record(self.session, grantRequestedUntil=report["grantRequestedUntil"]))
        self.assertEqual(record["shownSha256"], run.shown_digest("tenant-test", "sample", RELEASE, self.session, {"request": "go"}), "the digest of what the person was shown")
        self.assertEqual(self.receipt()["consent"], {"mode": "awaited", "subject": "user-1", "subjectSource": "consent command record", "refreshTokenIssued": True, "grantRequestedUntil": report["grantRequestedUntil"]})
        self.assertEqual(self.receipt()["delegated"], True)
        self.assertEqual(self.names(), ["consent.json", "deposit.lock", "receipt.json", "request.json", "waiting.lock"])
        for name in self.names():
            self.assertEqual(oct(os.stat(self.out / name).st_mode & 0o777), "0o600", name)
        self.assertEqual(oct(os.stat(self.out).st_mode & 0o777), "0o700")
        self.assert_secrets_only_on_stdin(kube, 0, out.getvalue(), err.getvalue(), json.dumps(result[1]))


class RunWaitTests(Case):
    def test_nobody_consents_in_time_exits_3_and_nothing_was_deposited_or_submitted(self):
        kube = self.kube()
        code, envelope = self.submit(kube, is_tty=lambda: False, consent_timeout=120, clock=iter([0, 1000]).__next__, sleep=lambda s: self.fail("slept past the deadline"))
        self.assertEqual((code, run.NO_CONSENT), (3, 3))
        session = self.request()["session_id"]
        self.assertEqual(envelope, {"status": "NOT_SUBMITTED", "reason": "no consent was recorded in time; " + NEVER_DEPOSITED, "sessionId": session, "dir": str(self.out), "timeoutSeconds": 120})
        self.assertEqual(self.status(), envelope)
        self.assertEqual((kube.exec_calls, self.idp.calls), ([], []))
        self.assertEqual(self.names(), ["deposit.lock", "request.json", "status.json", "waiting.lock"])
        self.assertIn("Within 120 seconds", self.said[0])
        self.assertIn("stdin and stderr are not both a terminal", self.said[0])
        # A consent that arrives after the run gave up is refused before anyone signs in.
        browser = self.browser()
        with self.assertRaisesRegex(delegation.ConsentError, "no longer waiting for consent; this command deposited nothing"):
            self.consent(session, browser, kube)
        self.assertEqual((browser.opened, kube.exec_calls, self.idp.calls), (0, [], []))

    def test_a_record_written_as_the_deadline_passes_is_honoured(self):
        kube = self.kube([ACCEPTED])
        ticks = iter([0, 1000])

        def clock():
            tick = next(ticks)
            if tick:  # the consent command finished between the run's last look and its giving up
                session = self.request()["session_id"]
                (self.out / "consent.json").write_text(json.dumps(self.record(session)))
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

        code, envelope = self.submit(kube, is_tty=lambda: False, sleep=sleep, clock=lambda: 0)
        self.assertEqual((code, envelope["status"]), (1, "NOT_SUBMITTED"))
        self.assertEqual(envelope["reason"], f"{self.out / 'consent.json'} is not a consent record for this session; no workflow was started. If a consent command deposited a token, {run.GRANT_MAY_BE_HELD}")
        self.assertEqual(kube.exec_calls, [])
        self.assertEqual(self.status(), envelope)
        self.assertFalse((self.out / "receipt.json").exists())

    def test_a_record_that_does_not_carry_the_digest_of_what_this_run_holds_starts_nothing(self):
        """The run trusts a record only when the person was shown the tenant, agent, release, session and task it would submit."""
        others = {
            "absent": None,
            "empty": "",
            "not a string": 7,
            "another task": lambda session: self.digest(session, {"request": "go", "also": "this"}),
            "another release": lambda session: self.digest(session, release="sample-2026-01-01-ffffffff"),
            "another tenant": lambda session: self.digest(session, tenant="tenant-other"),
            "another agent": lambda session: self.digest(session, agent="other"),
            "another session": lambda session: self.digest(OTHER_SESSION),
            "a prefix": lambda session: self.digest(session)[:32],
        }
        for name, other in others.items():
            with self.subTest(name):
                kube, out = self.kube([ACCEPTED]), self.tmp / name.replace(" ", "-")

                def sleep(_, out=out, other=other):
                    session = self.request(out)["session_id"]
                    record = self.record(session)
                    if other is None:
                        del record["shownSha256"]
                    else:
                        record["shownSha256"] = other(session) if callable(other) else other
                    (out / "consent.json").write_text(json.dumps(record))

                code, envelope = self.submit(kube, is_tty=lambda: False, sleep=sleep, clock=lambda: 0, out=out)
                self.assertEqual((code, envelope["status"]), (1, "NOT_SUBMITTED"))
                self.assertEqual(envelope["reason"], "the consent record does not carry the digest of this run's tenant, agent, release, session and task, so the person was not shown what this run would submit; no workflow was started, and " + run.GRANT_MAY_BE_HELD)
                self.assertIn("cleanup reconciler's next pass", envelope["reason"])
                self.assertEqual((envelope["consent"]["mode"], envelope["consent"]["subject"]), ("awaited", "user-1"))
                self.assertEqual(kube.exec_calls, [], "no remote call: nothing is submitted and no handle is fetched")
                self.assertEqual(self.status(out), envelope)
                self.assertFalse((out / "receipt.json").exists())

    def test_a_request_file_changed_under_the_consent_command_starts_nothing(self):
        """What the person was shown comes from request.json; what is submitted comes from the run's memory. They must be the same."""
        kube, browser = self.kube([DEPOSITED, ACCEPTED]), self.browser()
        finish = self.start_waiting(kube)
        written = self.request()
        (self.out / "request.json").write_text(json.dumps(dict(written, task={"request": "something harmless"})))
        code, report = self.consent(self.session, browser, kube)
        self.assertEqual((code, report["deposited"]), (0, True))
        self.assertEqual(self.consent_said[0], 'Task: {"request": "something harmless"}')
        code, envelope = finish()
        self.assertEqual((code, envelope["status"]), (1, "NOT_SUBMITTED"))
        self.assertIn("the person was not shown what this run would submit; no workflow was started", envelope["reason"])
        self.assertIn(run.GRANT_MAY_BE_HELD, envelope["reason"])
        self.assertEqual([c["action"] for c in kube.exec_calls], ["deposit"], "the task the run holds was never submitted")
        self.assertFalse((self.out / "receipt.json").exists())
        self.assertEqual(self.status(), envelope)

    def test_the_digest_is_over_one_canonical_encoding(self):
        base = run.shown_digest("t", "a", "r", OTHER_SESSION, {"x": 1, "y": [1, 2]})
        self.assertRegex(base, "^[0-9a-f]{64}$")
        self.assertEqual(base, run.shown_digest("t", "a", "r", OTHER_SESSION, {"y": [1, 2], "x": 1}), "key order is not part of the task")
        changed = [("T", "a", "r", OTHER_SESSION, {"x": 1, "y": [1, 2]}), ("t", "A", "r", OTHER_SESSION, {"x": 1, "y": [1, 2]}), ("t", "a", "R", OTHER_SESSION, {"x": 1, "y": [1, 2]}), ("t", "a", "r", OTHER_SESSION.replace("6", "7", 1), {"x": 1, "y": [1, 2]}), ("t", "a", "r", OTHER_SESSION, {"x": 1, "y": [2, 1]}), ("t", "a", "r", OTHER_SESSION, {"x": "1", "y": [1, 2]}), ("ta", "", "r", OTHER_SESSION, {"x": 1, "y": [1, 2]})]
        self.assertEqual(len({base, *(run.shown_digest(*parts) for parts in changed)}), len(changed) + 1)

    def test_sign_in_not_completed_at_a_terminal_exits_3_and_nothing_was_deposited_or_submitted(self):
        kube = self.kube()
        sign_in = functools.partial(delegation.sign_in, issuer=self.idp.issuer, clock=iter([0, 1000]).__next__)
        code, envelope = self.submit(kube, sign_in=sign_in, consent_timeout=60)
        self.assertEqual(code, 3)
        self.assertEqual((envelope["status"], envelope["reason"], envelope["timeoutSeconds"]), ("NOT_SUBMITTED", "the sign-in was not completed in time; " + NOTHING_SENT, 60))
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

    def test_any_directory_the_lookup_would_not_find_is_named_in_the_printed_command(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.tmp / "state")}):
            base = self.tmp / "state/kubani/agent-runs"
            # Inside the default directory under another name, under another agent's directory, and one that needs quoting.
            for number, out in enumerate((base / "sample/mine", base / "other/mine", self.tmp / "my runs/it's here")):
                with self.subTest(out=out):
                    self.said.clear()
                    self.clock_now[0] = 0.0
                    kube, browser = self.kube([DEPOSITED, ACCEPTED]), self.browser()
                    finish = self.start_waiting(kube, out=out)
                    command = self.said[0].split("in a terminal on this machine: ", 1)[1]
                    argv = shlex.split(command)
                    self.assertEqual(argv, ["just", "agent", "consent", "sample", "--session", self.session, "--run-dir", str(out)])
                    self.assertEqual(command.endswith(f"--run-dir {out}"), number < 2, "quoted only when the shell needs it")
                    # Without the directory the lookup finds nothing; with it, as printed, the consent is given.
                    with self.assertRaisesRegex(delegation.ConsentError, "no run of sample on this machine is waiting"):
                        self.consent(self.session, browser, kube, run_dir=None)
                    self.assertEqual(self.consent(self.session, browser, kube, run_dir=Path(argv[-1]))[0], 0)
                    self.assertEqual(finish()[0], 0)

    def test_an_interrupted_wait_exits_130_and_says_what_is_known_of_a_deposit(self):
        kube = self.kube()
        code, envelope = self.submit(kube, is_tty=lambda: False, sleep=interrupted, clock=lambda: 0)
        self.assertEqual((code, run.INTERRUPTED), (130, 130))
        self.assertEqual((envelope["status"], envelope["reason"]), ("NOT_SUBMITTED", "interrupted while waiting for consent; " + NEVER_DEPOSITED))
        self.assertEqual(self.status(), envelope)
        self.assertEqual((kube.exec_calls, self.names()), ([], ["deposit.lock", "request.json", "status.json", "waiting.lock"]))
        # A consent command had sent a token and recorded nothing when the run was interrupted.
        out = self.tmp / "b"

        def marked_then_interrupted(_):
            (out / run.DEPOSIT_ATTEMPT).write_text("2030-01-01T00:00:00Z\n")
            raise KeyboardInterrupt

        code, envelope = self.submit(kube, is_tty=lambda: False, sleep=marked_then_interrupted, clock=lambda: 0, out=out)
        self.assertEqual((code, envelope["reason"]), (130, f"interrupted while waiting for consent; a consent command sent a token and recorded no deposit, so {run.GRANT_MAY_BE_HELD}; no workflow was started"))
        self.assertEqual(kube.exec_calls, [])

    def request(self, out=None) -> dict:
        if out is None and not self.out.exists():
            (out,) = (self.tmp / "state/kubani/agent-runs/sample").iterdir()
        return super().request(out)


class RunRefusalTests(Case):
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
                code, envelope = self.submit(kube, self.browser(), out=out)
                # The same exit code as `consent --session` and `consent --check` give for such a token.
                self.assertEqual((code, envelope["status"]), (1, "NOT_SUBMITTED"))
                self.assertEqual(envelope["reason"], "the token Keycloak issued would not be accepted for deposit; " + NOTHING_SENT)
                self.assertEqual((envelope["subject"], envelope["preferredUsername"], len(envelope["missing"])), ("user-1", "person", 1))
                self.assertIn(expected, envelope["missing"][0])
                self.assertEqual((kube.exec_calls, self.names(out)), ([], ["request.json", "status.json"]))
                self.assertEqual(self.status(out), envelope)
                self.assertEqual(self.said[-1], "Signed in as person.")
                for secret in self.secrets():
                    self.assertNotIn(secret, json.dumps(envelope) + "\n".join(self.said))

    def test_refused_at_keycloak_or_without_pyjwt_nothing_is_sent(self):
        kube = self.kube([ACCEPTED])
        code, envelope = self.submit(kube, self.browser(error="access_denied"))
        self.assertEqual((code, envelope["status"]), (2, "NOT_SUBMITTED"))
        self.assertEqual(envelope["reason"], "Keycloak returned the error access_denied instead of an authorization code; " + NOTHING_SENT)
        self.assertEqual((kube.exec_calls, self.names(), self.status()), ([], ["request.json", "status.json"], envelope))
        with patch.dict(sys.modules, {"jwt": None}):
            with self.assertRaisesRegex(delegation.ConsentError, "PyJWT is not installed"):
                self.submit(kube, self.browser(), out=self.tmp / "b")
            self.assertEqual((kube.exec_calls, (self.tmp / "b").exists(), len(self.said)), ([], False, 3))
            # Only a sign-in needs PyJWT: a run that asks nobody, and a run that waits, start without it.
            self.assertEqual(self.submit(self.kube([ACCEPTED], "agent", False), out=self.tmp / "c")[0], 0)
            self.assertEqual(self.submit(self.kube(), is_tty=lambda: False, out=self.tmp / "d", clock=iter([0, 1000]).__next__)[0], 3)

    def test_a_deposit_the_policy_service_refuses_is_reported_and_leaves_no_receipt(self):
        refusal = "deposit refused: the token names no agent allowed to act for the person"
        kube = self.kube([{"error": refusal}])
        code, envelope = self.submit(kube, self.browser())
        self.assertEqual((code, envelope["status"]), (2, "SUBMIT_UNCONFIRMED"))
        self.assertEqual(envelope["reason"], f"remote submit failed: {refusal}; the policy service holds no grant from this run")
        self.assertEqual((envelope["consent"]["mode"], envelope["consent"]["subject"]), ("inline", "user-1"))
        self.assertEqual(len(kube.exec_calls), 1)
        self.assertEqual((self.names(), self.status()), (["request.json", "status.json"], envelope))
        self.assert_secrets_only_on_stdin(kube, 0, json.dumps(envelope))

    def test_a_failure_after_the_token_was_sent_says_a_grant_may_be_held(self):
        # The pod deposits before it starts the workflow and releases the grant on a failure only as a best effort.
        kube = self.kube([{"error": "workflow start failed"}])
        code, envelope = self.submit(kube, self.browser())
        self.assertEqual((code, envelope["status"], envelope["reason"]), (2, "SUBMIT_UNCONFIRMED", "remote submit failed: workflow start failed; " + run.GRANT_MAY_BE_HELD))
        self.assertIn("every five minutes", envelope["reason"])
        self.assertEqual(self.names(), ["request.json", "status.json"])
        # A run that sent no token and deposited nothing says nothing about a grant.
        kube = self.kube([{"error": "workflow start failed"}], "on-behalf-of", True)
        code, envelope = self.submit(kube, grant_handle="h-1", out=self.tmp / "b")
        self.assertEqual((code, envelope["status"], envelope["reason"]), (2, "SUBMIT_UNCONFIRMED", "remote submit failed: workflow start failed"))
        self.assertNotIn("h-1", json.dumps(envelope))

    def test_an_unanswered_remote_call_says_its_outcome_is_unknown(self):
        def unanswered(request):
            raise subprocess.TimeoutExpired("kubectl", run.EXEC_TIMEOUT)

        kube = self.kube([unanswered])
        code, envelope = self.submit(kube, self.browser())
        self.assertEqual((code, envelope["status"]), (2, "SUBMIT_UNCONFIRMED"))
        self.assertEqual(envelope["reason"], "remote submit did not answer within 60 seconds; whether it took effect is not known; " + run.GRANT_MAY_BE_HELD)
        self.assertEqual((self.names(), self.status()), (["request.json", "status.json"], envelope))
        self.assert_secrets_only_on_stdin(kube, 0, json.dumps(envelope))

    def test_an_interrupt_at_each_step_exits_130_with_an_envelope_and_no_traceback(self):
        # During the sign-in: nothing left this process.
        kube = self.kube([ACCEPTED])
        code, envelope = self.submit(kube, sign_in=interrupted)
        self.assertEqual((code, envelope["status"], envelope["reason"]), (130, "NOT_SUBMITTED", "interrupted during the sign-in; " + NOTHING_SENT))
        self.assertEqual((kube.exec_calls, self.names(), self.status()), ([], ["request.json", "status.json"], envelope))
        # While the one remote call was in flight: whether a workflow exists is not known.
        kube, out = self.kube([interrupted]), self.tmp / "b"
        code, envelope = self.submit(kube, self.browser(), out=out)
        self.assertEqual((code, envelope["status"]), (130, "SUBMIT_UNCONFIRMED"))
        self.assertEqual(envelope["reason"], "interrupted while the submit call was in flight; whether a workflow was started is not known; " + run.GRANT_MAY_BE_HELD)
        self.assertEqual((self.names(out), self.status(out)), (["request.json", "status.json"], envelope))
        # After the receipt, while following: the workflow is left running and the receipt names it.
        kube, out = self.kube([ACCEPTED, interrupted]), self.tmp / "c"
        code, envelope = self.submit(kube, self.browser(), out=out, wait=True)
        self.assertEqual((code, envelope["status"], envelope["cleanup"]), (130, "INTERRUPTED", "NOT_CONFIRMED"))
        self.assertEqual(envelope["receipt"], self.receipt(out))
        self.assertIn(f"the workflow was not cancelled, and `just agent status --receipt {out / 'receipt.json'}` reads it", envelope["reason"])
        self.assertEqual(self.names(out), ["receipt.json", "request.json"])
        self.assertEqual([c["action"] for c in kube.exec_calls], ["submit", "status"])


class ConsentCommandTests(Case):
    def planted(self, *names: str, session: str = OTHER_SESSION, agent: str = "sample", tenant: str = "tenant-test") -> Path:
        """A run directory as a `run` would have left it, without a live run behind it."""
        out = self.tmp / "planted"
        out.mkdir()
        os.chmod(out, 0o700)
        (out / "request.json").write_text(json.dumps({"session_id": session, "agent": agent, "tenant": tenant, "release": RELEASE, "task": {"request": "go"}}))
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
        self.assertIn("stdin and stderr must both be a TTY", self.refused(OTHER_SESSION, run_dir=out, is_tty=lambda: False))
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
        for path in out.iterdir():
            path.unlink()
        out.rmdir()

    def test_a_run_of_the_same_agent_name_in_another_tenant_is_not_this_one(self):
        """Everything but the tenant matches, and the lock is held as a waiting run holds it: the tenant alone is what refuses."""
        out = self.planted("waiting.lock", tenant="tenant-other")
        with run._locked(out / "waiting.lock"):
            self.assertEqual(self.refused(OTHER_SESSION, run_dir=out), f"no run of sample on this machine is waiting for consent to session {OTHER_SESSION}; consent is given where `just agent run` is waiting (add --run-dir DIR when the run was started with --out)")
            request = json.loads((out / "request.json").read_text())
            (out / "request.json").write_text(json.dumps(dict(request, tenant="tenant-test")))
            # The same directory once it names this tenant: consent goes ahead.
            kube = self.kube([DEPOSITED])
            self.assertEqual(self.consent(OTHER_SESSION, self.browser(), kube, run_dir=out)[0], 0)
            self.assertEqual([c["tenant"] for c in kube.exec_calls], ["tenant-test"])

    def test_a_run_directory_or_request_another_account_owns_is_refused(self):
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        with patch.object(run, "_stat_directory", foreign(run._stat_directory)):
            self.assertEqual(self.refused(self.session), f"{self.out} is not owned by you; consent is given only to a run you started")
        with patch.object(run, "_stat_open_file", foreign(run._stat_open_file)):
            self.assertEqual(self.refused(self.session), f"{self.out / 'request.json'} is not a regular file owned by you; consent is given only to a run you started")
        # Nothing else stood in the way: the same run, seen as the caller's own, is consented to.
        self.assertEqual(self.consent(self.session, self.browser(), kube)[0], 0)
        self.assertEqual(finish()[0], 0)

    def test_what_is_shown_cannot_drive_the_terminal(self):
        """Escape sequences and direction overrides in the task or the release reach the terminal as visible text, never as themselves."""
        said = []
        intro = run._show(said.append, "tenant-test", "sample", "r1\x1b[2K\x1b[1Aharmless", OTHER_SESSION, {"request": "a\x1b[2K\u202eb\nc"})
        self.assertEqual(said, ['Task: {"request": "a\\u001b[2K\\u202eb\\nc"}'])
        self.assertIn("release r1?[2K?[1Aharmless)", intro)
        for text in said + [intro]:
            self.assertTrue(text.isprintable(), text)
        who = []
        run._say_who(who.append, {"preferredUsername": "al\x1b[2Kice\u202e", "subject": "s"})
        self.assertEqual(who, ["Signed in as al?[2Kice?."])
        # Every name on the line, and what is printable yet shows as nothing or reorders the line: a Hangul filler, a
        # braille blank, a combining mark, a Hebrew letter.
        intro = run._show([].append, "t\x1b[2Kt", "a\x1b[2Ka", "r\u3164\u2800\u0301\u05d0r", "s\x1b[2Ks", {})
        self.assertTrue(intro.startswith("a?[2Ka (tenant t?[2Kt, release r????r) will act as you for session s?[2Ks, on the task above"), intro)
        self.assertTrue(intro.isascii() and intro.isprintable(), intro)
        # A name is never cut silently: two that differ only past the cut would otherwise read the same.
        self.assertEqual(run._plain("r" * 256), "r" * 256)
        self.assertEqual(run._plain("r" * 300), "r" * 256 + "...(300 characters)")

    def test_reading_a_request_leaves_no_descriptor_open(self):
        held = self.tmp / "held"
        held.mkdir(mode=0o700)
        os.chmod(held, 0o700)
        (held / "request.json").write_text("{}")
        before = len(os.listdir("/proc/self/fd"))
        for _ in range(3):
            self.assertEqual(run._own_request(held), {})
        os.unlink(held / "request.json")
        os.mkdir(held / "request.json")
        for _ in range(3):
            with self.assertRaises(delegation.ConsentError):
                run._own_request(held)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)

    def test_a_request_that_is_not_a_regular_file_is_refused(self):
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        aside = self.tmp / "aside.json"
        os.rename(self.out / "request.json", aside)
        for plant, remove in ((os.mkdir, os.rmdir), (os.mkfifo, os.unlink)):
            with self.subTest(plant.__name__):
                plant(self.out / "request.json")
                self.assertEqual(self.refused(self.session), f"{self.out / 'request.json'} is not a regular file owned by you; consent is given only to a run you started")
                remove(self.out / "request.json")
        os.rename(aside, self.out / "request.json")
        self.assertEqual(self.consent(self.session, self.browser(), kube)[0], 0)
        self.assertEqual(finish()[0], 0)

    def test_a_run_directory_whose_mode_is_not_0700_is_refused(self):
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        for mode in (0o750, 0o705, 0o701, 0o770, 0o777, 0o1700, 0o500):
            with self.subTest(oct(mode)):
                os.chmod(self.out, mode)
                self.addCleanup(os.chmod, self.out, 0o700)
                self.assertEqual(self.refused(self.session), f"{self.out} has mode {mode:04o}, not 0700 as `just agent run` creates it; another account could have changed what it says the run will do")
        os.chmod(self.out, 0o700)
        self.assertEqual(self.consent(self.session, self.browser(), kube)[0], 0)
        self.assertEqual(finish()[0], 0)

    def test_a_request_that_is_a_symbolic_link_is_refused(self):
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        elsewhere = self.tmp / "elsewhere.json"
        os.rename(self.out / "request.json", elsewhere)
        os.symlink(elsewhere, self.out / "request.json")
        self.assertEqual(self.refused(self.session), f"{self.out / 'request.json'} is a symbolic link, not the file `just agent run` wrote")
        os.unlink(self.out / "request.json")
        os.rename(elsewhere, self.out / "request.json")
        self.assertEqual(self.consent(self.session, self.browser(), kube)[0], 0)
        self.assertEqual(finish()[0], 0)

    def test_a_distrusted_directory_found_by_the_default_lookup_is_named_not_skipped(self):
        kube = self.kube([DEPOSITED])
        with patch.dict(os.environ, {"XDG_STATE_HOME": str(self.tmp / "state")}):
            self.start_waiting(kube, out=None)
            (out,) = (self.tmp / "state/kubani/agent-runs/sample").iterdir()
            os.chmod(out, 0o755)
            self.addCleanup(os.chmod, out, 0o700)
            self.assertIn(f"{out} has mode 0755, not 0700", self.refused(self.session, run_dir=None))

    def request(self, out=None) -> dict:
        if out is None and not self.out.exists():
            (out,) = (self.tmp / "state/kubani/agent-runs/sample").iterdir()
        return super().request(out)

    def test_refused_when_the_run_is_over_or_consent_was_already_given(self):
        states = {
            (): "this run is not waiting for consent; this command deposited nothing",
            ("waiting.lock",): "the run that asked for this consent has ended; this command deposited nothing",
            ("waiting.lock", "receipt.json"): "this run is no longer waiting for consent; this command deposited nothing",
            ("waiting.lock", "status.json"): "this run is no longer waiting for consent; this command deposited nothing",
            ("waiting.lock", "consent.json"): "consent was already given for this session; this command deposited nothing",
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
        self.assertEqual(self.refused(self.session), "consent was already given for this session; this command deposited nothing")
        self.assertEqual(finish()[0], 0)
        self.assertEqual(self.refused(self.session), "consent was already given for this session; this command deposited nothing")
        self.assertEqual([c["action"] for c in kube.exec_calls], ["deposit", "submit"])
        self.assertFalse((self.out / "consent.json.tmp").exists())

    def test_a_run_that_gives_up_during_the_sign_in_gets_no_deposit(self):
        kube = self.kube([DEPOSITED])
        finish = self.start_waiting(kube)
        browser = self.browser()
        person = self.sign_in(browser)

        def slow_person(*args, **kwargs):
            signed = person(*args, **kwargs)
            self.give_up()  # the run's deadline passes while the person is still at the consent screen
            self.assertEqual(finish()[0], run.NO_CONSENT)
            return signed

        with self.assertRaises(delegation.ConsentError) as caught:
            self.consent(self.session, browser, kube, sign_in=slow_person)
        self.assertEqual(str(caught.exception), "this run is no longer waiting for consent; this command deposited nothing")
        self.assertTrue(self.idp.calls)  # the person did sign in; what was refused is the deposit
        self.assertEqual(kube.exec_calls, [])
        self.assertFalse((self.out / "consent.json").exists())

    def waiting_run_is_untouched(self, kube, finish, calls=(), known="; " + NEVER_DEPOSITED):
        """The consent attempt left the run waiting; it then gives up with nothing submitted and says what it knows of a deposit."""
        self.assertEqual([c["action"] for c in kube.exec_calls], list(calls))
        self.assertFalse((self.out / "consent.json").exists())
        self.give_up()
        code, envelope = finish()
        self.assertEqual((code, envelope["status"], envelope["reason"]), (3, "NOT_SUBMITTED", "no consent was recorded in time" + known))
        self.assertFalse((self.out / "receipt.json").exists())

    def test_a_token_the_policy_service_would_refuse_is_not_deposited(self):
        kube = self.kube([DEPOSITED])
        finish = self.start_waiting(kube)
        self.idp.mutate = lambda t: t["access"].update(scope="openid")
        code, report = self.consent(self.session, self.browser(), kube)
        self.assertEqual((code, report["deposited"], report["subject"], len(report["missing"])), (1, False, "user-1", 1))
        self.assertIn(SCOPE, report["missing"][0])
        self.assertEqual(self.consent_said[-1], "Signed in as person.")
        self.assertFalse((self.out / run.DEPOSIT_ATTEMPT).exists())
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

        refusal = "deposit refused: the token names no agent allowed to act for the person"
        kube = self.kube([{"error": refusal}, unanswered, {"deposited": False}, {"error": refusal}, {"error": "policy service unreachable"}])
        finish = self.start_waiting(kube)
        marker = self.out / run.DEPOSIT_ATTEMPT
        who = {"agent": "sample", "tenant": "tenant-test", "sessionId": self.session, "runDir": str(self.out), "subject": "user-1", "preferredUsername": "person"}
        # Refused by the policy service: this command left no grant, and says so.
        self.assertEqual(self.consent(self.session, self.browser(), kube), (2, dict(who, deposited=False, reason=f"remote deposit failed: {refusal}; this command deposited nothing")))
        self.assertFalse(marker.exists())
        # No answer, and an answer that confirms nothing: the outcome is not known, and that is what is said and left behind.
        self.assertEqual(self.consent(self.session, self.browser(), kube), (2, dict(who, deposited=None, reason="remote deposit did not answer within 60 seconds; whether it took effect is not known; " + run.GRANT_MAY_BE_HELD)))
        self.assertEqual(len(marker.read_text().splitlines()), 1)
        self.assertEqual(self.consent(self.session, self.browser(), kube), (2, dict(who, deposited=None, reason="remote deposit did not confirm the deposit; whether it took effect is not known, and " + run.GRANT_MAY_BE_HELD)))
        # A later refusal does not erase what an earlier attempt left unknown.
        self.assertEqual(self.consent(self.session, self.browser(), kube)[1]["deposited"], False)
        self.assertEqual(len(marker.read_text().splitlines()), 3)
        # A failure that is not a refusal by the policy service is not known to have left nothing.
        self.assertEqual(self.consent(self.session, self.browser(), kube), (2, dict(who, deposited=None, reason="remote deposit failed: policy service unreachable; " + run.GRANT_MAY_BE_HELD)))
        self.assertEqual(oct(os.stat(marker).st_mode & 0o777), "0o600")
        self.assertEqual(sorted(p.name for p in self.out.iterdir() if p.name.startswith("consent")), [])
        self.waiting_run_is_untouched(kube, finish, ["deposit"] * 5, f"; a consent command sent a token and recorded no deposit, so {run.GRANT_MAY_BE_HELD}; no workflow was started")
        for secret in self.secrets():
            for path in self.tmp.rglob("*"):
                if path.is_file():
                    self.assertNotIn(secret, path.read_bytes().decode("utf-8", "replace"), path)

    def test_an_interrupted_consent_exits_130_and_says_what_is_known(self):
        kube = self.kube([interrupted])
        finish = self.start_waiting(kube)
        base = {"agent": "sample", "tenant": "tenant-test", "sessionId": self.session, "runDir": str(self.out)}
        # At the consent screen: no token exists yet.
        self.assertEqual(self.consent(self.session, kube=kube, sign_in=interrupted), (130, dict(base, deposited=False, interrupted=True)))
        self.assertEqual((kube.exec_calls, (self.out / run.DEPOSIT_ATTEMPT).exists()), ([], False))
        # While the token was on its way to the pod: the outcome is not known.
        code, report = self.consent(self.session, self.browser(), kube)
        self.assertEqual((code, report), (130, dict(base, deposited=None, interrupted=True, subject="user-1", preferredUsername="person", reason="interrupted while the deposit was in flight; whether it took effect is not known, and " + run.GRANT_MAY_BE_HELD)))
        self.assertTrue((self.out / run.DEPOSIT_ATTEMPT).exists())
        self.waiting_run_is_untouched(kube, finish, ["deposit"], f"; a consent command sent a token and recorded no deposit, so {run.GRANT_MAY_BE_HELD}; no workflow was started")
        for secret in self.secrets():
            self.assertNotIn(secret, json.dumps(report))

    def test_the_whole_task_is_shown_before_the_sign_in_however_long(self):
        """The digest covers the whole task, so the display may not stop short of it: the end of a long task is shown too."""
        kube = self.kube([DEPOSITED, ACCEPTED])
        box = {}
        task = {"request": "x" * 15000 + " and then the last instruction"}
        thread = threading.Thread(target=lambda: box.update(result=run.submit(self.root, "sample", task, kube=kube, say=self.said.append, out=self.out, wait=False, is_tty=lambda: False, sleep=lambda s: time.sleep(0.005))), daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not self.said and time.monotonic() < deadline:
            time.sleep(0.005)
        session = self.request()["session_id"]
        self.assertEqual(self.consent(session, self.browser(), kube)[0], 0)
        thread.join(10)
        self.assertEqual(box["result"][0], 0)
        self.assertEqual(self.consent_said[0], "Task: " + json.dumps(task, sort_keys=True))
        self.assertTrue(self.consent_said[0].endswith('and then the last instruction"}'))
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
        self.assertEqual((consent["refreshTokenIssued"], consent["grantRequestedUntil"]), (False, sent["expires_at"]))
        self.assertEqual(self.said[-1], f"Keycloak issued no refresh token: sample can act for you only until the access token expires at {sent['expires_at']}.")

    def test_consent_command_without_a_refresh_token(self):
        self.idp.refresh = False
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        before = int(time.time())
        code, report = self.consent(self.session, self.browser(), kube)
        finish()
        sent = kube.exec_calls[0]["deposit"]
        self.assertEqual((code, sent["refresh_token"], report["refreshTokenIssued"], report["grantRequestedUntil"]), (0, None, False, sent["expires_at"]))
        self.assertTrue(before + 300 <= seconds(sent["expires_at"]) <= int(time.time()) + 300)
        self.assertIn("only until the access token expires, at grantRequestedUntil", report["note"])
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

    def test_every_ending_prints_exactly_one_json_document(self):
        self.idp.mutate = lambda t: t["access"].update(scope="openid")
        kube = self.kube([ACCEPTED])
        # A token the policy service would refuse: exit 1, as `consent --session` and `consent --check` give for it.
        code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--browser", "--out", str(self.out)], kube, self.browser(), interactive=True)
        envelope = json.loads(out)
        self.assertEqual((code, envelope["status"], kube.exec_calls), (1, "NOT_SUBMITTED", []))
        self.assertIn("would not be accepted for deposit", envelope["reason"])
        self.assertIn(SCOPE, envelope["missing"][0])
        self.assertEqual(err.splitlines()[-1], "Signed in as person.")
        for secret in self.secrets():
            self.assertNotIn(secret, out + err)
        self.idp.mutate = lambda t: None
        # Refused at Keycloak, from a terminal: the run directory exists, so the envelope is the run's own.
        code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--browser", "--out", str(self.tmp / "b")], kube, self.browser(error="access_denied"), interactive=True)
        self.assertEqual((code, json.loads(out)["status"], json.loads(out)["dir"]), (2, "NOT_SUBMITTED", str(self.tmp / "b")))
        # Interrupted at the sign-in, and interrupted somewhere the run does not handle itself.
        with patch.object(delegation, "sign_in", interrupted):
            code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--out", str(self.tmp / "c")], kube, interactive=True)
        self.assertEqual((code, json.loads(out)["status"]), (130, "NOT_SUBMITTED"))
        self.assertIn("interrupted during the sign-in", json.loads(out)["reason"])
        self.assertNotIn("Traceback", err)
        with patch.object(run, "plan", interrupted):
            code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--out", str(self.tmp / "d")], kube, interactive=True)
        self.assertEqual((code, json.loads(out)["status"], err), (130, "INTERRUPTED", "interrupted\n"))
        # Refusals before a run directory exists: the one stderr line as before, and a document that says the same.
        refusals = [
            (["run", "sample", "--task", "go", "--task-json", "{}"], "pass exactly one of --task, --task-json or --task-file", None),
            (["run", "sample", "--task", "go", "--consent-timeout", "0"], "--consent-timeout must be above 0", None),
            (["run", "sample", "--task", "go", "--grant-handle", ""], "", None),
            (["consent", "sample", "--session", OTHER_SESSION, "--run-dir", str(self.tmp / "absent")], "no run of sample on this machine is waiting", True),
            (["consent", "sample", "--session", OTHER_SESSION], "stdin and stderr must both be a TTY", None),
            (["consent", "sample"], "pass exactly one of --session ID", True),
        ]
        for argv, expected, interactive in refusals:
            with self.subTest(argv):
                code, out, err = self.run_cli(argv, kube, self.browser(), interactive=interactive)
                document = json.loads(out)
                self.assertEqual((code, document["status"], set(document)), (2, "REFUSED", {"status", "reason"}))
                self.assertIn(expected, document["reason"])
                self.assertEqual(err, f"refused: {document['reason']}\n")
        # An error that is not a refusal.
        code, out, err = self.run_cli(["run", "sample", "--task-file", str(self.tmp / "absent.json")], kube)
        self.assertEqual((code, json.loads(out)["status"]), (1, "ERROR"))
        self.assertTrue(err.startswith("error: "))
        # An error nobody foresaw: still one document, naming the exception's type and place and never its message.
        def unforeseen(*args, **kwargs):
            raise KeyError("a value that must not be printed")
        with patch.object(run, "plan", unforeseen):
            code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--out", str(self.tmp / "e")], kube, interactive=True)
        document = json.loads(out)
        self.assertEqual((code, document["status"], set(document)), (1, "ERROR", {"status", "reason"}))
        self.assertRegex(document["reason"], r"^unexpected KeyError at test_agent_ops_run_consent\.py:\d+$")
        self.assertEqual(err, f"error: {document['reason']}\n")
        # The same after the run directory exists, here a started workflow whose answer lacks a field: the document names
        # the session and the directory, so the run can still be found.
        answer = {k: v for k, v in ACCEPTED.items() if k != "workflow_id"}
        code, out, err = self.run_cli(["run", "sample", "--task", "go", "--no-wait", "--browser", "--out", str(self.tmp / "f")], self.kube([answer]), self.browser(), interactive=True)
        document = json.loads(out)
        self.assertEqual((code, document["status"], set(document), document["dir"]), (1, "ERROR", {"status", "reason", "sessionId", "dir"}, str(self.tmp / "f")))
        self.assertRegex(document["reason"], r"^unexpected KeyError at run\.py:\d+$")
        self.assertEqual(json.loads((self.tmp / "f" / "request.json").read_text())["session_id"], document["sessionId"])
        for secret in self.secrets():
            self.assertNotIn(secret, out + err)
        # Only `run` and `consent` promise one document: any other command lets an unforeseen error through as it is.
        with patch.object(live, "listing", unforeseen), self.assertRaises(KeyError):
            self.run_cli(["ls"], kube)
        self.assertNotIn("must not be printed", out + err)
        self.assertEqual(kube.exec_calls, [])

    def test_await_consent_is_no_longer_an_option(self):
        kube = self.kube([ACCEPTED])
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(io.StringIO()) as err:
            cli.main(["--root", str(self.root), "run", "sample", "--task", "go", "--await-consent"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("unrecognized arguments: --await-consent", err.getvalue())
        self.assertNotIn("await_consent", Path(run.__file__).read_text())
        self.assertEqual(kube.exec_calls, [])

    def test_a_consent_command_that_ends_in_a_document_keeps_its_exit_code(self):
        kube = self.kube([{"error": "deposit refused: the token names no agent allowed to act for the person"}])
        finish = self.start_waiting(kube)
        code, out, err = self.run_cli(["consent", "sample", "--session", self.session, "--run-dir", str(self.out), "--browser"], kube, self.browser(), interactive=True)
        report = json.loads(out)
        self.assertEqual((code, report["deposited"]), (2, False))
        self.assertTrue(report["reason"].endswith("this command deposited nothing"))
        self.give_up()
        self.assertEqual(finish()[0], 3)


class TerminalTests(Case):
    """The real terminal check, on stand-in streams: a person is here when stdin and stderr are terminals, whatever stdout is."""

    def streams(self, stdin: bool, stdout: bool, stderr: bool):
        return patch.multiple(sys, stdin=Stream(stdin), stdout=Stream(stdout), stderr=Stream(stderr))

    def test_run_signs_in_here_when_stdin_and_stderr_are_terminals_and_stdout_is_a_pipe(self):
        for stdout in (False, True):
            with self.subTest(stdout=stdout):
                kube, out = self.kube([ACCEPTED]), self.tmp / f"stdout-{stdout}"
                with self.streams(True, stdout, True):
                    code, envelope = self.submit(kube, self.browser(), is_tty=None, out=out)
                self.assertEqual((code, envelope["status"], envelope["receipt"]["consent"]["mode"]), (0, "SUBMITTED", "inline"))
                self.assertEqual(len(kube.exec_calls), 1)

    def test_run_signs_nobody_in_unless_both_stdin_and_stderr_are_terminals(self):
        for stdin, stdout, stderr in ((False, False, True), (False, True, True), (True, False, False), (True, True, False), (False, False, False), (False, True, False)):
            with self.subTest(stdin=stdin, stdout=stdout, stderr=stderr):
                self.said.clear()
                kube, out = self.kube([ACCEPTED]), self.tmp / f"{stdin}-{stdout}-{stderr}"
                with self.streams(stdin, stdout, stderr):
                    code, envelope = self.submit(kube, is_tty=None, sign_in=self.no_sign_in, out=out, clock=iter([0, 1000]).__next__)
                self.assertEqual((code, envelope["status"]), (3, "NOT_SUBMITTED"))
                self.assertEqual(len(self.said), 1)
                self.assertIn("just agent consent sample --session", self.said[0])
                self.assertEqual((kube.exec_calls, self.idp.calls), ([], []))

    def test_consent_needs_the_same_two_terminals(self):
        kube = self.kube([DEPOSITED, ACCEPTED])
        finish = self.start_waiting(kube)
        for stdin, stdout, stderr in ((False, True, True), (True, True, False), (False, True, False)):
            with self.subTest(stdin=stdin, stderr=stderr), self.streams(stdin, stdout, stderr), self.assertRaisesRegex(delegation.ConsentError, "stdin and stderr must both be a TTY"):
                self.consent(self.session, kube=kube, is_tty=None)
        self.assertEqual((kube.exec_calls, self.idp.calls), ([], []))
        with self.streams(True, False, True):
            code, report = self.consent(self.session, self.browser(), kube, is_tty=None)
        self.assertEqual((code, report["deposited"]), (0, True))
        self.assertEqual(finish()[0], 0)


if __name__ == "__main__":
    unittest.main()
