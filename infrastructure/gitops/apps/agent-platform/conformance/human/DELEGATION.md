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

For bounded tests, `--mint /tmp/alice-online.enc.yaml --refresh-mode online`
explicitly omits only `offline_access`; it keeps the same exact actor delegation
consent, required audiences, PKCE flow and mandatory nonempty refresh token.
Default `--refresh-mode offline` still requests offline access and fails if the
server refuses it. There is no automatic fallback and no role/scope mutation.

The online option addresses the observed local eligibility mismatch: Alice
already inherits `offline_access`, but `agent-cli` has `fullScopeAllowed=false`
and neither the client nor its optional `offline_access` scope maps that role.
Keycloak 26.8.1 therefore returns HTTP400 `not_allowed` at authorization-code
exchange when offline access is requested. This is distinct from the approved
Alice-specific Users/delegate grant.

Online refresh is constrained by the realm/client online session idle and maximum
lifetimes and session termination. It is suitable only for a bounded run after
checking actual remaining TTL, not proof of offline access or eight-hour
persistence. Mint output labels the mode and includes the server-reported
`refresh_expires_in` as `refresh_lifetime_seconds` when present (otherwise null).
A reported zero must not be treated as proof of unlimited session lifetime.
Actual grant/vault TTL and refresh behavior still require the live test evidence.

## Proposed Alice-only permission consolidation (new approval required)

Read-only evaluation on pinned Keycloak 26.8.1 found that the two separately
approved Alice/delegate permissions conflict under the admin-permissions
resource server's UNANIMOUS strategy: conformance's own permission permits its
actor, but the lifecycle permission denies it, so `canDelegate` denies overall
and the parameterized consent scope is omitted. Do not change the global
resource-server strategy or add a broader user/actor grant.

The reviewed migration preserves both exact existing actor client policies.
It updates only `conformance-alice-delegate` to resources=[exact synthetic Alice],
scopes=[delegate], policies=[conformance-alice-actor,
conformance-lifecycle-alice-actor], logic=POSITIVE, decisionStrategy=AFFIRMATIVE.
After strict reads verify that combined permission and both unchanged policies,
it deletes only the exact superseded `conformance-lifecycle-alice-delegate`
permission. No user, actor policy, client, scope mapper or global setting changes.
This replaces the previously approved two-permission representation and requires
new user approval before applying, even though the intended allowed principal
set is unchanged.

Plan without mutation:

```sh
python infrastructure/scripts/ops/conformance-delegation.py --consolidate-alice-permissions
```

Only after the user approves the exact reviewed plan, root may add
`--apply-consolidation`. Use an exclusive authorization-configuration window:
Keycloak's policy update/delete endpoints have no revision/CAS support. The
helper re-reads strict state immediately before each write and verifies after
it, but cannot make separate REST calls atomic against another administrator.

Only the exact legacy, verified expanded (PUT succeeded, DELETE outstanding),
and completed consolidated states are recognized. An interrupted verified PUT
can resume only its exact DELETE. Missing, unknown, broader or changed state is
refused; no compensating recreation or global change is attempted. Repeated
completed application writes nothing. Ordinary `configure` recognizes completed
consolidation for either approved actor, rejects partial consolidation before
any writes, and never recreates the conflicting separate lifecycle permission.
Configuration no longer creates missing delegation policies/permissions; missing
or unknown grant state needs an explicit reviewed recovery plan.

After application, repeat read-only permission evaluation for each exact actor
against Alice and verify PERMIT, and verify conformance-b/another user remain
DENY. Then mint fresh explicit consent and continue T10a. Preparation and unit
tests are not proof of live scope issuance or delegated exchange acceptance.
