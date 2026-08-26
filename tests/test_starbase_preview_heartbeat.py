from __future__ import annotations

import importlib.util
import unittest
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


if __name__ == "__main__":
    unittest.main()
