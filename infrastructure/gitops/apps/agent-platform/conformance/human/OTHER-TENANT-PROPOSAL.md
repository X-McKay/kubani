# Offline T10a other-tenant human proposal

**Proposal and offline-tested helper; not authorization or live qualification.**
This package has created or changed no user, client scope, mapper, profile
metadata, role, permission, token or Secret and has minted no token. Read-only
planning inputs may be collected by root through the existing admin helper. Existing Alice consent
approval (PR374) is separate and remains unaffected. This package is solely for
review before a distinct user approval decision; do not run an apply/mint command.

The merged [T10a gate](T10A.md) requires a genuinely different subject and a signed
`tenant` claim. The current [human helper](../../../../../scripts/ops/conformance-human-token.py)
hardcodes Alice and ordinary PKCE scopes; renaming its SOPS file or changing a
JWT cannot supply that evidence. The
[contract operator](../../../../../scripts/ops/conformance-delegation-contract.py)
already accepts an independently verified SOPS other-user input plus exact subject
and other tenant, and fails missing provenance. This proposal keeps that behavior.

## Exact proposed objects

| Object | Proposed change | Explicit limits |
| --- | --- | --- |
| One realm agents user | Create absent username `conformance-bob-tenant-other`; server assigns a fresh subject distinct from recorded Alice | Never modify/reuse an existing username/subject or reset its password |
| User attributes | `conformance_tenant=["tenant-other"]` only | Only the new Bob record gets the provenance value |
| Managed profile attribute | Add `conformance_tenant`, scalar, administrator view/edit only, exact tenant-other validation | Preserve every existing profile entry, group, setting and unmanaged-attribute policy |
| One OIDC client scope | Create `conformance:t10a:tenant-provenance` with the single mapper below | Ordinary provenance only; no parameterized/client-delegation mapper, role, authorization policy or audience mapper |
| agent-cli attachment | Attach that scope as optional only | No default scope; no attachment to another client; public PKCE client settings unchanged |
| Local credential storage | A new SOPS-only `bob-tenant-other-credentials.enc.yaml`, with assigned subject and generated password after creation | Do not create/generate it during this offline proposal; no plaintext file/log/argv |
| Future short-lived input | SOPS-only ordinary access-token fixture `bob-tenant-other-token.enc.yaml` | No Kubernetes apply; no delegation, backend/admin grant, offline scope or stored refresh token |

User metadata would be exactly username above, enabled=true, firstName=Bob,
lastName=Conformance, email=bob.tenant-other@conformance.invalid,
emailVerified=true, requiredActions=[] and the single protected attribute. The exact server-assigned new UUID is recorded
in a local reviewed provision receipt; no `conformance_fixture` attribute is added.
The omitted unmanaged-attribute policy stays omitted. A strong
random password is generated only by the later approved helper and sent in memory
on creation; no sample credential or fabricated UUID is part of this proposal.
The assigned subject is recorded only after the issuer returns/verifies it.

Proposed managed-profile entry (merge one entry, not replace the realm profile):

```json
{
  "name": "conformance_tenant",
  "displayName": "T10a synthetic tenant provenance",
  "multivalued": false,
  "permissions": {"view": ["admin"], "edit": ["admin"]},
  "validations": {"pattern": {"pattern": "^tenant-other$"}}
}
```

Proposed scope and mapper representation, subject to exact pinned26.8.1 schema
normalization verification before any future apply:

```json
{
  "name": "conformance:t10a:tenant-provenance",
  "description": "T10a admin-controlled synthetic tenant provenance only",
  "protocol": "openid-connect",
  "attributes": {
    "display.on.consent.screen": "true",
    "include.in.token.scope": "true",
    "consent.screen.text": "T10a synthetic tenant provenance"
  },
  "protocolMappers": [{
    "name": "conformance-t10a-tenant",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-usermodel-attribute-mapper",
    "config": {
      "user.attribute": "conformance_tenant",
      "claim.name": "tenant",
      "jsonType.label": "String",
      "multivalued": "false",
      "aggregate.attrs": "false",
      "access.token.claim": "true",
      "id.token.claim": "false",
      "userinfo.token.claim": "false",
      "introspection.token.claim": "false"
    }
  }]
}
```

The optional scope is requestable by agent-cli users generally; its name is not
an authorization boundary. The boundary is the administrator-controlled managed
attribute, set only on the new Bob user. An ordinary user must be unable to add,
replace or supply that attribute through profile/account update, registration or
login parameters. If pinned Keycloak cannot enforce that exact protection, stop;
do not substitute a user-editable attribute, a hardcoded tenant mapper available
to all users, another role, or broader delegation permission. Read-only configuration inspection supports planning only; the live self-service
protection controls below remain unqualified.

`tenant-other` is synthetic signed provenance for this negative input only. Do
not create a Kubernetes namespace/tenant, Agent/AgentRelease, workload, new client
or service account, tenant/backend RBAC or resource audience to support it.

## Helper/code changes to review before approval

1. Preserve existing Alice defaults, scope allowlist and credential path. Do not
   temporarily monkeypatch the Alice helper's USERNAME/CREDENTIALS globals.
2. Add a narrowly named other-tenant helper/profile fixed to the proposed username,
   subject file, issuer, agent-cli, callback and tenant-other. Reuse only pure
   issuer/origin/callback/PKCE/form/SOPS utilities, factoring the login routine
   explicitly if necessary; do not add arbitrary username/tenant/client flags.
3. Plan mode is offline by default and cannot call admin_client/decrypt/request,
   generate credentials, encrypt output or mint. A later separately reviewed
   apply path must reject existing/mismatched objects and preserve normalized
   exact semantics. The default mode below is local planning; explicit execution/mint modes remain unapproved.
4. Keep creation/configuration separate from minting. The future PKCE request
   scope is exactly `openid profile conformance:t10a:tenant-provenance`, with
   nonce/state/S256 checks and the existing pinned origin/callback restrictions.
   No password grant, agent impersonation, actor assertion, token exchange,
   delegation scope, backend audience/scope, offline_access or approval in mint.
5. Recursively inspect direct/composite roles and group memberships with the
   existing assert_unprivileged policy. Permit only its existing baseline realm
   and account self-service roles; create/assign no roles or group membership.
   In particular, no FGAP delegate permission for Bob, no actor user/client policy,
   no backend/admin role, no service account and no consent impersonation.
6. Verify RS256/JWKS, exact issuer, expiry, azp=agent-cli, preferred_username,
   recorded fresh Bob sub != Alice sub, typ=Bearer and scalar tenant=tenant-other
   before writing a fixture. Reject act, may_act, agent_id, agent client_type,
   delegation:client scopes or unexpected backend/admin claims. Keep only the
   ordinary access token in SOPS; discard any unneeded ID/online refresh token in
   memory. Reports contain safe subject/tenant/issuer/times and typed failure only.

## Required preconditions and negative constraints

Before a future approved apply, read-only planning must prove exact Keycloak
version/schema, unique agent-cli and proposed scope/user names, no conflicting
managed profile field or existing tenant claim mapper, and no other user carrying
conformance_tenant. If anything differs, return a concrete new review delta;
never adopt a preexisting principal or silently modify another attribute/mapper.
Preserve existing profile metadata and scope attachments byte-semantically except
for the explicitly listed additions. Server scalar defaults may be normalized
only when demonstrably equivalent; no wildcard comparison may hide extra mappers.

Review offline regressions for: existing Bob subject/password untouched; existing
Alice behavior unchanged; alternate username/tenant/issuer/client refused; no
non-allowlisted scope; no group/admin/backend/delegate assignment; unmanaged or
user-editable provenance refused; multi-valued/wrong/missing tenant rejected;
wrong/expired signature, subject, nonce/state/azp or token type rejected; raw
responses/credentials absent from stdout, argv, temporary files and artifacts.
Mocked planner tests must prove zero network/decrypt/mint calls in offline mode.

Only after separate approval and readback should an actual self-service negative
attempt prove Bob cannot change/add the managed attribute, while administrator
readback and the signed JWT agree on tenant-other. Do not credit a locally forged
claim or local verifier exception as a real IdP refusal. Verify optional-scope
absence does not add a tenant claim to ordinary Alice or other normal tokens;
requesting the scope without the protected attribute must not manufacture one.
All live checks are later root work, not done by this proposal.

## Eventual T10a use and honest mechanism

After approval, genuine creation, signed-claim verification and fresh ordinary
PKCE mint, root may pass the SOPS path, assigned subject and other tenant together:
`--other-user BOB_SOPS_FILE --other-user-sub ACTUAL_BOB_SUB --other-tenant tenant-other`.
No guessed subject, Alice alias, edited JWT or unsigned claim qualifies. Positive
Alice controls must bracket the real wrong-user exchange, with fresh genuine
Pod-bound actor authentication; actual pinned status/error/description refusal
classification remains unchanged. Missing/expired fixtures remain incomplete.

Bob receives no user-specific FGAP delegate permission and no may_act. The observed
refusal may therefore be missing consent or requester-not-audience before any
independent tenant matcher. Record that exact safe refusal mechanism; do not claim
that tenant claim mismatch alone caused denial or grant Bob delegation merely to
create a matching positive consent. If the acceptance contract requires an
isolated tenant-only denial with otherwise equivalent consent/audience, that
additional requirement remains unresolved under this proposal's no-grants bound.
It is not satisfied by silently broadening Bob's privileges.

## Approval boundary and cleanup

A later user approval request should enumerate exactly the new Bob user, one
protected managed-profile field, one access-token-only provenance scope/mapper,
one optional agent-cli attachment and ordinary short-lived SOPS fixture minting.
No part of Alice's pending approval authorizes these objects. Review command shapes below do not request or infer approval.

Record before/after safe object IDs and configuration hashes, never raw exports
or credentials. Any future rollback must match the recorded exact new IDs before
removing Bob's session/consent/user and the new optional attachment/scope. Remove
the managed-profile entry only if it is still exact and no unrelated principal
uses it; otherwise stop for review. Preserve historical failure reports, existing
Alice/actor permissions, client defaults and all unrelated users/configuration.
Destroy expired local fixture material through the established SOPS workflow;
never reset another user's password or create a delegation grant for cleanup.

## Concrete helper and review commands

`infrastructure/scripts/ops/conformance-other-tenant.py --snapshot SAFE_SNAPSHOT.json`
performs strictly local planning by default. Its pure planner uses only the Python
standard library. It never imports execution, admin, SOPS or PKCE code in this
mode. A partial snapshot produces explicit blockers. Complete inputs must prove
pinned version 26.8.1, bounded pagination and associated reads, exact public S256
agent-cli settings, absence of Bob/protected provenance, and the recursive allowed
default role graph with zero default groups. Input observations must be no older
than one hour when producing a plan. This is freshness of planning evidence, not
live authorization; execution always repeats the reads.

The plan resolves the existing agent-cli UUID, includes the exact full preserved
profile PUT, exact scope POST, optional scope attachment and fixed new-user POST,
and fingerprints all safe preflight projections. New scope/user IDs remain
issuer-assigned. Existing agent tenant mappers on unrelated agent-only scopes are
preserved and fingerprinted. Tenant claim collisions on agent-cli's effective
direct/default/optional mapper set are refused; any conformance_tenant mapper
anywhere, or any existing user with that attribute, is refused globally. Optional
attachment representations may omit protocol; their exact IDs/names are bound to
the associated realm scope representation. No mapper values outside the reviewed
collision projection are needed because no existing mapper is modified.

Execution is **not approved**. The reviewable opt-in command shape is:

```text
conformance-other-tenant.py --mode execute --approved-plan REVIEWED_PLAN.json \
  --approved-plan-sha256 EXACT_DIGEST --receipt NEW_LOCAL_RECEIPT.json \
  --exclusive-profile-writer
```

Only after user approval, root may run it under exclusive profile-writer ownership.
It validates the digest before admin login, performs all fresh bounded reads and
requires the resulting plan to equal the approved plan. Observation time and
request count alone do not alter semantic fingerprints. It rechecks the exact
profile preimage immediately before writing; Keycloak has no CAS, so exclusive
writer ownership remains mandatory. It makes only the four proposed mutations,
with exact readbacks after each, and stops on unexpected server normalization.
The new protected attribute is scalar/admin-only; the unmanaged policy remains
omitted if omitted in the preimage. No role/group/grant or client configuration
mutation is available.

The helper exclusively creates a new local receipt before its first write,
records each confirmed operation and new immutable ID, and retains typed failure
and partial state on any error. Existing receipts, Bob users, scopes or credential
files are refused; it never adopts objects, resets passwords or automatically
retries ambiguous writes. Root must reconcile any partial failure using the exact
receipt and fresh reads before a new reviewed action. Password generation occurs
only immediately before new-user creation. The password enters only memory and
the fixed SOPS credential file, encrypted before creation and updated with the
verified server subject after creation. No plaintext temporary file or argv is
used. Receipt files contain no password or token.

The separate ordinary PKCE mint command shape is:

```text
conformance-other-tenant.py --mode mint --approved-plan REVIEWED_PLAN.json \
  --approved-plan-sha256 EXACT_DIGEST --receipt PROVISION_RECEIPT.json
```

Mint revalidates exact Bob metadata, no groups/privileged roles, own scope/mapper,
protected profile hash, client S256 settings and unchanged scope attachments. The
request scope is exactly openid/profile/provenance. Response scope may additionally
contain only the recorded unchanged default scope names (the existing client has
acr, roles, profile, basic and email). No delegation, offline or backend scope is
requested or accepted. RS256/JWKS verification, pinned issuer/expiry/subject/azp,
nonce/state and exact username/Bearer checks remain shared with Alice's unchanged
PKCE transport. Additional Bob checks enforce scalar tenant-other, recorded new
subject, no act/may_act/agent identity, exact permitted standard claims, baseline
realm/account roles and only account/agent-cli audiences. Only the access token is
written to the fixed SOPS token path; ID/refresh tokens are not persisted. No
Kubernetes apply or admin grant is part of minting.

All listed live checks, including protected-attribute self-service refusal and
missing-attribute/no-scope controls, remain root work after separate approval.
Synthetic tests and this plan do not qualify those checks or the actual wrong-user
transport refusal. Preserve historical failures and report the observed refusal
mechanism without claiming an isolated tenant-only matcher.
