from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "infrastructure/scripts/starbase_preview_heartbeat.py"


def load_module():
    spec = importlib.util.spec_from_file_location("starbase_preview_heartbeat", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load heartbeat module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StarbasePreviewHeartbeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.heartbeat = load_module()

    def valid_login_location(self) -> str:
        query = urlencode(
            {
                "client_id": "starbase-kubani",
                "redirect_uri": "https://starbase.almckay.io/api/v1/auth/callback",
                "response_type": "code",
                "code_challenge_method": "S256",
                "prompt": "login",
                "max_age": "0",
                "scope": "groups openid",
                "state": "state-value",
                "nonce": "nonce-value",
                "code_challenge": "challenge-value",
            }
        )
        return f"https://auth.almckay.io/application/o/authorize/?{query}"

    def journal_line(self, timestamp: str, **overrides: object) -> str:
        event: dict[str, object] = {
            "status": "ok",
            "checks": 7,
            "observer": "osprey",
        }
        event.update(overrides)
        return (
            f"{timestamp} osprey starbase-preview-heartbeat[123]: "
            f"{self.heartbeat.json.dumps(event)}\n"
        )

    def test_exact_oidc_redirect_is_accepted(self) -> None:
        self.heartbeat.validate_login_redirect(self.valid_login_location())

    def test_oidc_redirect_rejects_target_scope_and_parameter_changes(self) -> None:
        cases = (
            self.valid_login_location().replace("auth.almckay.io", "attacker.invalid"),
            self.valid_login_location().replace(
                "groups+openid", "groups+openid+offline_access"
            ),
            self.valid_login_location().replace("starbase-kubani", "substituted-client"),
            self.valid_login_location() + "&unexpected=value",
        )
        for location in cases:
            with self.subTest(location=location):
                with self.assertRaises(self.heartbeat.ProbeError):
                    self.heartbeat.validate_login_redirect(location)

    def test_observer_hostname_is_bound_to_osprey(self) -> None:
        self.heartbeat.validate_hostname("osprey.example", "osprey")
        with self.assertRaises(self.heartbeat.ProbeError):
            self.heartbeat.validate_hostname("rig0", "osprey")

    def test_dns_is_limited_to_the_reviewed_ingress_addresses(self) -> None:
        reviewed = ("100.92.107.71", "100.77.107.81")
        self.assertEqual(
            self.heartbeat.validate_dns_addresses(
                ["100.77.107.81", "100.92.107.71", "100.77.107.81"], reviewed
            ),
            ("100.77.107.81", "100.92.107.71"),
        )
        for addresses in ([], ["100.92.107.71", "203.0.113.10"]):
            with self.subTest(addresses=addresses):
                with self.assertRaises(self.heartbeat.ProbeError):
                    self.heartbeat.validate_dns_addresses(addresses, reviewed)

    def test_probe_covers_each_ingress_path_dns_session_and_login(self) -> None:
        ready = (200, {}, b'{"status":"ready"}')
        session = (200, {}, b'{"mode":"oidc","authenticated":false}')
        login = (303, {"Location": self.valid_login_location()}, b"")
        responses = [ready] * 5 + [session, login]
        dns_result = [(2, 1, 6, "", (self.heartbeat.TARGET_ADDRESSES[0], 443))]

        with patch.object(
            self.heartbeat.socket, "getaddrinfo", return_value=dns_result
        ), patch.object(self.heartbeat, "_request", side_effect=responses) as request:
            self.assertEqual(self.heartbeat.probe_starbase(timeout=1), 7)
        self.assertEqual(request.call_count, 7)

    def test_probe_fails_before_auth_checks_when_an_ingress_path_is_down(self) -> None:
        with patch.object(
            self.heartbeat,
            "_request",
            return_value=(503, {}, b'{"status":"unavailable"}'),
        ) as request:
            with self.assertRaises(self.heartbeat.ProbeError):
                self.heartbeat.probe_starbase(timeout=1)
        self.assertEqual(request.call_count, 1)

    def test_journal_verifier_reports_count_and_maximum_gap(self) -> None:
        lines = [
            "2026-08-26T12:00:00.000000+0000 osprey systemd[1]: Starting\n",
            self.journal_line("2026-08-26T12:00:10.000000+0000"),
            self.journal_line("2026-08-26T12:05:05.000000+0000"),
            self.journal_line("2026-08-26T12:10:00.000000+0000"),
        ]

        result = self.heartbeat.verify_journal(
            lines,
            window_start=datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
            checkpoint=datetime(2026, 8, 26, 12, 10, 5, tzinfo=timezone.utc),
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["runs"], 3)
        self.assertEqual(result["max_gap_seconds"], 295.0)

    def test_journal_verifier_rejects_missing_or_late_success(self) -> None:
        start = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
        checkpoint = datetime(2026, 8, 26, 12, 8, 10, tzinfo=timezone.utc)
        cases = (
            [],
            [
                self.journal_line("2026-08-26T12:00:10.000000+0000"),
                self.journal_line("2026-08-26T12:08:00.000000+0000"),
            ],
        )

        for lines in cases:
            with self.subTest(lines=lines):
                with self.assertRaises(self.heartbeat.ProbeError):
                    self.heartbeat.verify_journal(
                        lines,
                        window_start=start,
                        checkpoint=checkpoint,
                    )

    def test_journal_verifier_rejects_ambiguous_success_evidence(self) -> None:
        start = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
        checkpoint = datetime(2026, 8, 26, 12, 1, tzinfo=timezone.utc)
        cases = (
            [self.journal_line("2026-08-26T12:00:10.000000+0000", checks=6)],
            [self.journal_line("2026-08-26T12:00:10.000000+0000", status="failed")],
            [
                "2026-08-26T12:00:10.000000+0000 osprey "
                "starbase-preview-heartbeat[123]: {not-json}\n"
            ],
        )

        for lines in cases:
            with self.subTest(lines=lines):
                with self.assertRaises(self.heartbeat.ProbeError):
                    self.heartbeat.verify_journal(
                        lines,
                        window_start=start,
                        checkpoint=checkpoint,
                    )

    def test_journal_verifier_rejects_failure_between_timely_successes(self) -> None:
        lines = [
            self.journal_line("2026-08-26T12:00:10.000000+0000"),
            "2026-08-26T12:02:30.000000+0000 osprey "
            "starbase-preview-heartbeat[123]: "
            "starbase preview heartbeat failed: readiness check failed\n",
            self.journal_line("2026-08-26T12:05:05.000000+0000"),
        ]

        with self.assertRaisesRegex(
            self.heartbeat.ProbeError, "failed observer run"
        ):
            self.heartbeat.verify_journal(
                lines,
                window_start=datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
                checkpoint=datetime(2026, 8, 26, 12, 5, 10, tzinfo=timezone.utc),
            )

    def test_verify_journal_cli_reads_export_and_emits_one_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "observer.log"
            journal.write_text(
                self.journal_line("2026-08-26T12:00:10.000000+0000"),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            argv = [
                str(SCRIPT),
                "--verify-journal",
                str(journal),
                "--window-start",
                "2026-08-26T12:00:00Z",
                "--checkpoint",
                "2026-08-26T12:01:00Z",
            ]

            with patch.object(self.heartbeat.sys, "argv", argv), redirect_stdout(
                stdout
            ):
                self.assertEqual(self.heartbeat.main(), 0)

            self.assertEqual(
                json.loads(stdout.getvalue()),
                {
                    "max_gap_seconds": 50.0,
                    "runs": 1,
                    "status": "ok",
                    "window_seconds": 60.0,
                },
            )


if __name__ == "__main__":
    unittest.main()
