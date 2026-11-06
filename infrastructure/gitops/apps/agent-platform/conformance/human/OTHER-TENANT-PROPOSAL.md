# Offline T10a other-tenant human proposal

**Proposal only; not authorization or live evidence.** No user, client scope,
mapper, profile metadata, role, permission, token or Secret has been created,
changed, read from Keycloak or minted for this proposal. Existing Alice consent
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
| User attributes | `conformance_fixture=["agent-platform-t10a-other-tenant"]`, `conformance_tenant=["tenant-other"]` | Only the new Bob record gets the provenance value |
| Managed profile attribute | Add `conformance_tenant`, scalar, administrator view/edit only, exact tenant-other validation | Preserve every existing profile entry, group, setting and unmanaged-attribute policy |
| One OIDC client scope | Create `conformance:t10a:tenant-provenance` with the single mapper below | Ordinary provenance only; no parameterized/client-delegation mapper, role, authorization policy or audience mapper |
| agent-cli attachment | Attach that scope as optional only | No default scope; no attachment to another client; public PKCE client settings unchanged |
| Local credential storage | A new SOPS-only `bob-tenant-other-credentials.enc.yaml`, with assigned subject and generated password after creation | Do not create/generate it during this offline proposal; no plaintext file/log/argv |
| Future short-lived input | SOPS-only ordinary access-token fixture `bob-tenant-other-token.enc.yaml` | No Kubernetes apply; no delegation, backend/admin grant, offline scope or stored refresh token |

User metadata would be exactly username above, enabled=true, firstName=Bob,
lastName=Conformance, email=bob.tenant-other@conformance.invalid,
emailVerified=true, requiredActions=[] and the two explicit attributes. A strong
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
to all users, another role, or broader delegation permission. This is an offline
schema proposal, not a claim that current realm metadata has been inspected.

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
   exact semantics. No source helper implementation is included here yet.
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
No part of Alice's pending approval authorizes these objects. No current apply or
mint command is provided, and this document does not request or infer approval.

Record before/after safe object IDs and configuration hashes, never raw exports
or credentials. Any future rollback must match the recorded exact new IDs before
removing Bob's session/consent/user and the new optional attachment/scope. Remove
the managed-profile entry only if it is still exact and no unrelated principal
uses it; otherwise stop for review. Preserve historical failure reports, existing
Alice/actor permissions, client defaults and all unrelated users/configuration.
Destroy expired local fixture material through the established SOPS workflow;
never reset another user's password or create a delegation grant for cleanup.
