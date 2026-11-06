# Synthetic Alice delegation fixture

`infrastructure/scripts/ops/conformance-delegation.py` prepares the T10a
prerequisites on the pinned Keycloak26.8.1. Default invocation only reads and
prints the exact missing-object plan. `--apply-scope` creates the built-in
`delegation:client` parameterized scope and attaches it optionally to `agent-cli`.
`--apply-permission` creates one client policy for `agent-tenant-test-conformance`
and one `Users` permission, `delegate`, limited to the existing synthetic Alice
UUID. It does not grant delegation for every user, another agent, administrative
scopes or real human accounts. Existing objects must match exactly; there is no
overwrite/delete path. Both apply modes reread the server configuration.

Credentials are decrypted in memory from local SOPS files. No pod-secret read or
Keycloak restart is required. Set `SOPS_AGE_KEY_FILE` to the existing age key and
use the explicit operator environment. The helper never logs tokens, passwords,
cookies, authorization codes or response bodies. `--mint /tmp/alice.enc.yaml`
performs the normal PKCE login and explicit delegation consent, verifies the
subject and exact `may_act`, scopes and audiences, then writes the access and
refresh tokens only through SOPS. Minting is separate from configuration; the
ordinary T5 human fixture continues to request only `openid profile`.

The scope and mappers come from
[OIDCLoginProtocolFactory at26.8.1](https://github.com/keycloak/keycloak/blob/26.8.1/services/src/main/java/org/keycloak/protocol/oidc/OIDCLoginProtocolFactory.java).
The single-user authorization follows
[ClientDelegationTest.delegationRestrictedToSpecificUser](https://github.com/keycloak/keycloak/blob/26.8.1/tests/base/src/test/java/org/keycloak/tests/oauth/tokenexchange/ClientDelegationTest.java)
and its `PermissionTestUtils` helper. The older realm import's `delegation`
dynamic-scope placeholder is not modified by this script. Replace that import
entry with the actual verified export after live testing; imports do not update
an existing realm.

Configuration and a consented subject token do **not** qualify T10a. The retained
live report must still prove a pod-bound TokenRequest assertion accepted for the
agent's exchange, exact resulting `sub`, `act`, `aud`, `azp`, `scope`, and the
wrong-consent/actor/audience/user refusals. T10/T14 and delegated T12 remain
dependent on that evidence. No live qualification is claimed by this fixture.
