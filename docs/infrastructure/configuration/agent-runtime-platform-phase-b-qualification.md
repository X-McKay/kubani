# Agent Runtime Platform: Phase B qualification, 2026-11-05 (in progress)

Record of the Phase B conformance harness runs (spec 15, tests T4 and T5)
from [agent-runtime-platform.md](agent-runtime-platform.md), "Phase B
conformance harness". Every timestamp is UTC. The Phase B gate is 22 tests;
this document grows with each batch. The latest report is
[agent-runtime-platform-phase-b-run-2026-11-05.json](agent-runtime-platform-phase-b-run-2026-11-05.json).

## What ran

| Item | Value |
|---|---|
| Kubani | `main` at `8880908e` (#282 controller memory), Job applied from the working tree with the session-runner digest of #283 |
| Platform | X-McKay/zetra `408cfab` (zetra#24 harness failure reasons, zetra#26 one cosign at a time); run 1 used the harness at `fe0cc5d` |
| Agent | `tenant-test/conformance`, AgentRelease `conformance-2026-11-03-4dfe2607` (zetra-agents `conformance/v0.1.2`, image `sha256:4dfe2607…ba0e`, approved by #279) |
| Harness Job | `agent-platform/conformance-harness` on strix, `agent-conformance --tests T4,T5`, seven sandbox sessions per run |
| Sandbox node | rig0, Kata `kata-qemu-runtime-rs`, boot 12.6 to 16.5 s per generation |
| Keycloak | 26.8.1, realm `agents`, identity provider `kubernetes-kubani` (type `CLIENT_ASSERTION`) |

## Runs

| Run | Job created | Harness image | Result | Where every sandbox session stopped |
|---|---|---|---|---|
| 1 | 11:44:57 | session-runner `fe0cc5d` | fail (T4 fail, T5 6 fail / 2 pass) | Runner preflight: `Forbidden: release not ready`. The Registry Controller had been OOM-killed on every start since 2026-11-02 (#282) and the release had lost `signatureVerified` |
| 2 | 12:48:59 | session-runner `408cfab` | fail (T4 fail, T5 6 fail / 2 pass) | `run_boundary` `OutcomeUnknown rc=1` on all three generations. The sandbox's POST to `token.agents.internal/v1/token` got 401: Keycloak `CLIENT_LOGIN_ERROR error=invalid_client_credentials`, "Client authentication was attempted did not complete for federated-jwt" |
| 3 | 13:03:16 | session-runner `408cfab` | fail (T4 fail, T5 6 fail / 2 pass) | `run_boundary` `BudgetExceeded: guest reported budget exceeded` (non-retryable). The token was issued; the first `llm-main` call was denied `deny.budget_exhausted` (gateway 429) |

The two T5 cases that pass in every run are the harness pod's own POSTs:
`non_sandbox_pod` (IdP-audience token, 403 `not_an_agent`) and
`wrong_audience` (APS-audience token, 401 `invalid_client`), with no
`access_token` in either reply.

### Between runs 1 and 2

#282 merged at 8880908e; Flux replaced the controller pod at 12:40:20 with
request 256Mi / limit 768Mi. It has stayed `1/1 Running` with 0 restarts.
The release regained `Ready` and `SignatureVerified` at 12:40:39 with all
five attestations, without any change to the release. The pinned
`registry-controller:0fa3367` image was still running; #283 brings the
zetra#26 image (one cosign process at a time), built on rig0 with
`--no-cache` and the pinned cosign v2.6.1 checksum.

### Run 2: Keycloak ignores the spec 7.3 client attributes

Evidence, in order along the path:

- Kyverno admitted the sandbox pods (first tenant pods ever admitted with
  Rule 1 in Enforce): the admission controller log shows `image attestations
  verification succeeded` and `validation passed` for the conformance digest.
- The egress guard passed for the first time end to end: `egress-guard ok:
  attested, gateway reachable`.
- The agents Gateway logged `POST token.agents.internal /v1/token` → 401 from
  the APS, once per sandbox generation (21 in all).
- The APS logged no `token route refused`, so the TokenReview of the
  projected token succeeded and the request was forwarded to Keycloak.
- Keycloak: `CLIENT_LOGIN_ERROR ... clientId="agent-tenant-test-conformance"
  error="invalid_client_credentials"
  client_assertion_issuer="https://kubernetes.default.svc.cluster.local"
  client_assertion_sub="system:serviceaccount:tenant-test:agent-conformance"
  grant_type="client_credentials"`. Issuer, subject and audience
  (`https://idp.almckay.io/realms/agents`, the realm issuer Keycloak also
  reports on its in-cluster URL thanks to `KC_HOSTNAME`) were all correct.
- The live client carried `clientAuthenticatorType: federated-jwt` with the
  attributes `federated.jwt.identity.provider` and
  `federated.jwt.expected.subject`, as in spec 7.3 and `realm-agents.json`
  (whose own note called them "explicitly unconfirmed").

Cause: Keycloak 26.8.1's `FederatedJWTClientAuthenticator` defines its two
per-client properties as `jwt.credential.issuer` (identity provider alias)
and `jwt.credential.sub` (federated subject), and
`DefaultClientAssertionStrategy` finds the client by exactly those two
attributes. Any other key is ignored, so no client matched and the flow
failed. `GET authentication/config-description/federated-jwt` returns no
properties because they are per-client, not per-flow.

Fix: both tenant-test agent clients were given the two attributes with
`kcadm update` inside the Keycloak pod at about 13:01 (the stale
`federated.jwt.*` keys were left in place; the controller only adds and
overwrites attributes). Durable fixes: zetra#27 (controller writes
`jwt.credential.*`) and kubani#284 (template client in `realm-agents.json`).

### Run 3: the session budget cannot hold one reservation

- The APS issued the first agent token on this cluster at 13:03:35 for pod
  `s-f78cc5be9c5c4a25-g1` (`token issued`, jti `trrtcc:3f2daedb…`); the
  gateway's token route returned 200 for every sandbox, and the report's
  `one_token_per_sandbox` check passed.
- The sandbox's first `POST inference.agents.internal/models/llm-main/v1/chat/completions`
  was denied by the APS with `deny.budget_exhausted` (gateway 429); the guest
  exited 4 and the runner recorded `BudgetExceeded`, non-retryable.
- The ledgers were empty: no inference call had ever been admitted.

Cause: the APS reserves the backend's `maxModelLen` per inference request
(spec 3.7, 9.3 step 10): 131072 tokens for `llm-main` in
`APS_BACKEND_CATALOGUE`, which matches the engine's `LLM_MAX_MODEL_LEN`. The
conformance manifest sets `tokensPerSession: 50000`, so `spent + inflight +
131072 > 50000` on the first call. The investigator manifest uses 200000.

Fix: zetra-agents#13 raises the conformance budget to 200000 per session and
5M per day. Because the release's `policySha256` pins the compiled bundle,
changing the applied Agent in kubani alone would only register as
`PolicyDrift`; the fix needs release `conformance/v0.1.3`, then the
unapproved AgentRelease copied into `apps/agents/tenant-test/conformance/`
and approved by PR, then a fourth run.

## Status of spec items touched today

| Item | Status |
|---|---|
| Keycloak issues a token to an agent (T4 first half) | **Proven** 13:03:35, after the attribute fix |
| TokenReview returns pod name and UID for the projected token (17.3) | Proven implicitly: the APS resolved `pod` and `namespace` for the issued token |
| IdP accepts the projected token as a client assertion with the exact client settings (17.3, 7.8) | Proven with `jwt.credential.issuer` / `jwt.credential.sub`; the spec 7.3 keys fail |
| Session runs through the Session Runner | Sessions ran (21 sandboxes in run 2, 7 in run 3); none has completed yet |
| Sandbox network check end to end (egress guard) | **Passed** in runs 2 and 3 |
| Kyverno PolicyReports | Still none: `ephemeralreports`, `policyreports` and the cluster-scoped kinds are all empty after 28 admitted tenant pods, although the admission log shows the verification. The `background: true` suspicion stands |
| T4, T5 | Not passed yet; blocked on the conformance budget (zetra-agents#13 and a release) |

## Findings

1. **Harness runs must wait for `Ready` and `SignatureVerified: true` on the
   release**: run 1 was started while the controller was crash-looping and
   produced only `FAILED` with no reason. The zetra#24 harness now decodes
   the Temporal failure and reports it (`failures` in each case's evidence),
   which is what made runs 2 and 3 diagnosable from the report alone.
2. **Spec 7.3's client attribute keys are wrong for Keycloak 26.8**; record as
   a deviation and feed back to the spec text.
3. **Per-session budgets below the backend's `maxModelLen` admit nothing.**
   Either every manifest keeps `tokensPerSession >= maxModelLen` of each
   backend it names (the pragmatic choice taken here), or the reservation
   rule changes (spec 3.7). The agent-platform tooling could reject a manifest
   whose budget cannot hold one reservation.
4. Sessions that fail non-retryably still cost a Kata boot each (12.6 to
   16.5 s); a retryable `OutcomeUnknown` costs three.
