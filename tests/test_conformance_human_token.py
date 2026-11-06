"""Credential-bearing requests must stay on the pinned issuer origin."""

import importlib.util
import unittest
from pathlib import Path


PATH = (
    Path(__file__).resolve().parents[1]
    / "infrastructure/scripts/ops/conformance-human-token.py"
)
SPEC = importlib.util.spec_from_file_location("human_fixture", PATH)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class HumanFixtureTests(unittest.TestCase):
    def test_unlisted_consent_scope_rejected_before_credentials_are_read(self):
        with self.assertRaises(ValueError):
            fixture.mint_tokens("openid realm-admin")

    def test_existing_privileged_fixture_is_rejected(self):
        normal = {
            "id": "default",
            "name": "default-roles-agents",
            "composite": True,
            "clientRole": False,
        }
        replies = {
            "users/alice/groups": [],
            "clients?clientId=account": [{"id": "account-id"}],
            "users/alice/role-mappings": {"realmMappings": [normal]},
            "roles-by-id/default/composites": [
                {
                    "id": "view",
                    "name": "view-profile",
                    "clientRole": True,
                    "containerId": "account-id",
                },
            ],
        }
        fixture.assert_unprivileged(replies.__getitem__, "alice")
        replies["roles-by-id/default/composites"].append(
            {
                "id": "admin",
                "name": "realm-admin",
                "clientRole": True,
                "containerId": "realm-management-id",
            }
        )
        with self.assertRaises(ValueError):
            fixture.assert_unprivileged(replies.__getitem__, "alice")

    def test_existing_group_membership_is_rejected(self):
        with self.assertRaises(ValueError):
            fixture.assert_unprivileged(lambda _: [{"id": "unexpected-group"}], "alice")

    def test_only_exact_https_issuer_accepts_credentials(self):
        fixture.issuer_url(fixture.ISSUER + "/login-actions/authenticate?a=1")
        for target in (
            "http://idp.almckay.io/realms/agents/login-actions/authenticate",
            "https://idp.almckay.io.evil.invalid/realms/agents/login-actions/authenticate",
            "https://idp.almckay.io@evil.invalid/realms/agents/login-actions/authenticate",
            "https://idp.almckay.io:444/realms/agents/login-actions/authenticate",
            "https://idp.almckay.io/realms/other/login-actions/authenticate",
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                fixture.issuer_url(target)

    def test_callback_requires_exact_redirect_and_single_matching_state(self):
        valid = fixture.CALLBACK + "?code=example-code&state=expected"
        self.assertEqual(fixture.callback_code(valid, "expected"), "example-code")
        for target in (
            valid.replace("expected", "wrong"),
            valid + "&state=expected",
            valid + "&code=another-code",
            valid.replace("127.0.0.1", "localhost"),
            valid.replace("/callback", "/other"),
            fixture.CALLBACK + "?error=access_denied&state=expected",
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                fixture.callback_code(target, "expected")

    def test_pkce_matches_rfc7636_vector(self):
        self.assertEqual(
            fixture.pkce_challenge(
                "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"  # pragma: allowlist secret
            ),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",  # pragma: allowlist secret
        )

    def test_form_only_carries_hidden_inputs_and_selected_submit(self):
        form = fixture.Forms()
        form.feed("""<form id="kc-form-login" action="/realms/agents/login-actions/authenticate?a=1&amp;b=2">
          <input name="credentialId" type="hidden" value="c">
          <input name="username" value="unexpected"><input name="password" value="unexpected">
          <button name="cancel" value="true">Cancel</button></form>""")
        self.assertEqual(form.forms[0]["hidden"], {"credentialId": "c"})
        self.assertEqual(
            form.forms[0]["action"], "/realms/agents/login-actions/authenticate?a=1&b=2"
        )


if __name__ == "__main__":
    unittest.main()
