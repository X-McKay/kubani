# Agent Runtime Platform: Phase B qualification, 2026-11-05 (T4, T5 passed)

Record of the Phase B conformance harness runs (spec 15, tests T4 and T5)
from [agent-runtime-platform.md](agent-runtime-platform.md), "Phase B
conformance harness". Every timestamp is UTC. The Phase B gate is 22 tests;
this document grows with each batch. Reports: run 3
[13:03](agent-runtime-platform-phase-b-run-2026-11-05T1303.json) (fail), run 5
[14:04](agent-runtime-platform-phase-b-run-2026-11-05T1404.json) (pass, one soft
check false), run 6 [18:39](agent-runtime-platform-phase-b-run-2026-11-05T1839.json)
(**pass, every check true**), run 7
[21:58](agent-runtime-platform-phase-b-run-2026-11-05T2158.json) (first T8/T19 run:
T5 and T8 pass, T4 and T19 fail on harness evidence handling).

## What ran

| Item | Value |
|---|---|
| Kubani | Runs 1 to 5: `main` at `8880908e` (#282 controller memory), Job applied from the working tree with the session-runner digest of #283. Run 6: `main` at `d8270180` (#295), Job applied as committed. Run 7: `main` at `af54aeb4` (#305), Job applied as committed |
| Platform | X-McKay/zetra `408cfab` (zetra#24 harness failure reasons, zetra#26 one cosign at a time); run 1 used the harness at `fe0cc5d`. Run 6 ran against the APS at `7045b5a` (#290, zetra#28). Run 7: session-runner `c53f630` (zetra#30, T8/T19 harness), APS `d4f2e05` (zetra#29), Registry Controller `624a0ba` (zetra#31) |
| Agent | `tenant-test/conformance`. Runs 1 to 3: AgentRelease `conformance-2026-11-03-4dfe2607` (zetra-agents `conformance/v0.1.2`, approved by #279). Runs 4 and 5: `conformance-2026-11-05-7af1dd4a` (`conformance/v0.1.3`, applied by #285, approved by #286). Run 6: `conformance-2026-11-05-c5b76ecc` (`conformance/v0.1.4`, applied by #294, approved by #295). Run 7: `conformance-2026-11-05-e80880a1` (`conformance/v0.1.5`, `probe_mcp` added, applied by #304, approved by #305) |
| Harness Job | `agent-platform/conformance-harness` on strix, `agent-conformance --tests T4,T5`, seven sandbox sessions per run; from run 7 `--tests T4,T5,T8,T19`, nine sessions |
| Sandbox node | rig0, Kata `kata-qemu-runtime-rs`, boot 12.6 to 16.5 s per generation |
| Keycloak | 26.8.1, realm `agents`, identity provider `kubernetes-kubani` (type `CLIENT_ASSERTION`) |

## Runs

| Run | Job created | Harness image | Result | Where every sandbox session stopped |
|---|---|---|---|---|
| 1 | 11:44:57 | session-runner `fe0cc5d` | fail (T4 fail, T5 6 fail / 2 pass) | Runner preflight: `Forbidden: release not ready`. The Registry Controller had been OOM-killed on every start since 2026-11-02 (#282) and the release had lost `signatureVerified` |
| 2 | 12:48:59 | session-runner `408cfab` | fail (T4 fail, T5 6 fail / 2 pass) | `run_boundary` `OutcomeUnknown rc=1` on all three generations. The sandbox's POST to `token.agents.internal/v1/token` got 401: Keycloak `CLIENT_LOGIN_ERROR error=invalid_client_credentials`, "Client authentication was attempted did not complete for federated-jwt" |
| 3 | 13:03:16 | session-runner `408cfab` | fail (T4 fail, T5 6 fail / 2 pass) | `run_boundary` `BudgetExceeded: guest reported budget exceeded` (non-retryable). The token was issued; the first `llm-main` call was denied `deny.budget_exhausted` (gateway 429) |
| 4 | 13:58:36 | session-runner `408cfab`, release v0.1.3 | fail (T4 fail, T5 6 fail / 2 pass) | First `llm-main` call allowed and accepted (boundary 0, 780 tokens), `probe_files` tool boundary accepted, then the second `llm-main` call denied `deny.budget_exhausted`: no reservation was ever settled |
| 5 | 14:04:44 | session-runner `408cfab`, release v0.1.3 | **pass** (T4 pass, T5 8 / 8 pass) | Every session `COMPLETED` with 3 to 5 boundaries; one token per sandbox; all six sandbox refusal cases observed the expected 400 or 401 and the APS logged each refusal |
| 6 | 18:39:49 | session-runner `408cfab`, release v0.1.4 (`conformance-2026-11-05-c5b76ecc`, #294, #295) | **pass**, every check true | Same as run 5, and T4's `claims_reported` is now true: the compact `probe_files` report (zetra-agents#14) lists `/sandbox/state/token.json` with audiences `agent-gateway` and `agent-policy-service` beside the two projected-token paths |
| 7 | 21:58:47 | session-runner `c53f630`, release v0.1.5 (`conformance-2026-11-05-e80880a1`, #304, #305) | fail (T4 fail, T5 8 / 8 pass, **T8 pass**, T19 fail) | All nine sessions `COMPLETED` with three boundaries. T8 passed every check. T19's probe reported the exact `ok`/`deny` alternation and the APS logged ten distinct decisions, five `allow` and five `deny.route_not_permitted`, but the harness read them out of time order across the two APS replicas. T4's `token issued` line exists in the APS log at 21:59:09 and the harness's log read did not return it |

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

### Run 4: nothing ever settled

With v0.1.3 the token and the first model call went through, and the
`probe_files` tool ran. The second model call of every session was denied
`deny.budget_exhausted`. Alloy's `otelcol.exporter.otlp "aps"` was failing on
every batch: `Exporting failed. Dropping data ... Unimplemented: Decompressor
is not installed for grpc-encoding "gzip"`. The exporter compresses with gzip
by default and the APS settlement server registers no gzip decompressor, so
the access-log copy that settles reservations (spec 8.9) never arrived. A
reservation stays at the full 131072 until settled, and two of them do not
fit a 200000 session budget. Fixes: kubani#288 (`compression = "none"` on
that exporter; Alloy reloaded it on all four nodes at 14:04 to 14:05) and
zetra#28 (register the decompressor in the APS; needs an APS image rebuild
to take effect).

### Run 5: T4 and T5 pass

Started 14:04:44, finished 14:08:00, result `pass`.

- **T4**: token issued at 14:05:02 for `s-c455dfc4df3db313-g1`, exactly one
  per sandbox, `probe_files` ran, the session completed with three
  boundaries (model, tool, model). The report's `claims_reported` check is
  false: the probe did not return the cached token's claims. The harness
  still passes T4 on the hard evidence (APS `token issued` for that pod,
  session `COMPLETED`); record this as a soft gap in the probe or the check.
- **T5**: all eight cases pass. Six sandbox cases completed (three to five
  boundaries each) and reported the expected status (400 for
  `password_grant`, `token_exchange_grant`, `extra_field`, `duplicate_field`; <!-- pragma: allowlist secret -->
  401 for `client_secret`, `non_jwt_assertion`), with a matching APS `token <!-- pragma: allowlist secret -->
  route refused` entry and no `access_token` in any reply. The two harness-pod
  cases returned 403 and 401 as before.
- Settlement works: the second model call of each session was allowed, which
  needs the first reservation replaced by its actual usage (about 780 tokens).

### Run 6: the `claims_reported` gap closes

Started 18:39:51, finished 18:43:07, result `pass`, with release
`conformance-2026-11-05-c5b76ecc` (`conformance/v0.1.4`, zetra-agents#14:
same Agent as v0.1.3, the image reports `probe_files` compactly so the result
fits the 512-character summary cap) and the APS at `7045b5a` (#290, the
zetra#28 gzip decompressor).

- **T4**: token issued at 18:40:14 for `s-2b941f2c73135e3e-g1`; all five
  checks true, including `claims_reported`. The probe's final summary lists
  the three token files the sandbox holds and their audiences: the projected
  token (two paths) with `aud` `https://idp.almckay.io/realms/agents`, and
  the cached agent token at `/sandbox/state/token.json` with `aud`
  `agent-gateway`, `agent-policy-service`. Three boundaries (model, tool,
  model); no failures.
- **T5**: all eight cases pass again, each sandbox case with exactly three
  boundaries, and the APS refusal reasons are now in the evidence:
  `unsupported_grant_type` (`password_grant`, `token_exchange_grant`),
  `invalid_request` on field `client_secret` (`client_secret`), <!-- pragma: allowlist secret -->
  `assertion_not_authenticated` (`non_jwt_assertion`), `invalid_request` on
  field `audience` (`extra_field`) and on field `client_id`
  (`duplicate_field`). The harness-pod cases returned `not_an_agent` (403)
  and `invalid_client` (401) with no token in either body.
- Kyverno still wrote no report: all four report kinds are empty after the
  seven sandbox pods of this run (35 admitted tenant pods in all).

### MCP probe session: the agent-mode exchange has no scope

Before extending the harness to T8 and T19 (both run over the MCP route), one
`list_pods` session of the conformance agent was submitted at 19:00:42 with
`agent-session-submit` from a one-off Job (`conformance-probe-mcp`, same
identity and mounts as the harness Job; deleted afterwards). Session
`c9bc54a1…`, pod `s-1856cd9a2e54021b-g1`: token issued 19:01:02, first
`llm-main` call allowed, then the sandbox's MCP `initialize` on
`mcp.agents.internal/kubernetes/mcp` was denied `deny.exchange_failed`
(`delegation: agent`, 74 ms) at 19:01:05, and the session completed on the
model's error report. No MCP call has ever reached a backend on this cluster.

Keycloak logged the exchange: `TOKEN_EXCHANGE_ERROR clientId="agent-policy-service"
error="invalid_request" reason="Requested audience not available:
https://mcp.almckay.io/kubernetes/mcp"
subject_token_client_id="agent-tenant-test-conformance"`.

Cause: Keycloak's standard token exchange takes the audiences of the new token
from the **requester's** effective client scopes (default scopes plus the
optional scopes named by `scope`) and only filters them by `audience`. The
realm puts the `mcp:<backend>` audience scopes on the agent clients, which is
right for delegated mode (the APS authenticates as the agent client and sends
`scope=mcp:<backend>`), but agent mode authenticates as `agent-policy-service`,
whose only scope is `basic`, and `Keycloak.Agent` sends no `scope` at all.
Spec 7.5 names `agent-policy-service` as the agent-mode requester without
giving it the audience scopes.

Fix (two halves, both needed): `agent-policy-service` gets the four `mcp:*`
optional client scopes (realm file in this PR; the live realm needs the same
change by `kcadm`, since `--import-realm` never updates an existing realm),
and the APS agent-mode exchange sends `scope=mcp:<backend>` like delegated
mode (zetra `fix/aps-agent-exchange-scope`; new APS image to build and bump).

### Kyverno reports: written, but only while the pod lives

The admission controller was raised to `-v4` (#298) and one `probe_env`
session admitted at 20:56:58. The log showed the whole validation path and
`allowing admission request`, nothing about reports, because
`createReports` only logs on error. The admission pod's metrics then showed
`kyverno_breaker_total{circuit_name="admission reports"} 4` with no drop
counter and four `create` calls on `EphemeralReport` in `tenant-test`, and
the reports controller showed one `create PolicyReport` and seven `delete
EphemeralReport` in `tenant-test` over its lifetime. A second session,
polled every second, settled it: two admission EphemeralReports (pass 1 and
pass 5, owner `s-bd75a983b2d7ecc8-g1`) existed from the pod's first second, a
third appeared on the pod update, and the aggregated PolicyReport at
21:04:13, all gone with the pod. In Kyverno 1.19.2 the only policy-level
exclusion is the `exclude reporting` label, and `NeedsReports` rejects only
dry runs, deletes, Events and objects without a UID. Nothing is wrong, and
`background: false` is right for admission-only policies. The -v4 override
is reverted in the same PR as this record.

### MCP route: proven end to end, after a second realm gap

With the APS at `d4f2e05` (#301) and the `mcp:*` scopes on
`agent-policy-service`, a `list_pods` session at 21:10 got `allow` on
`initialize` (exchange 112 ms, upstream token minted), on
`notifications/initialized` (cached) and on `tools/call
pods_list_in_namespace`, the first MCP call to reach the APS's allow path on
this cluster. The gateway then answered the `tools/call` with 400:
`mcp: authorization denied for tool: pods_list_in_namespace`, from its own
spec 8.8 policy (`"agent-role-kubernetes-read" in jwt.realm_access.roles`).

Cause: the service account holds the role (the Registry Controller assigns
it), but the agent client has `fullScopeAllowed: false` (spec 7.3) and no
realm scope mapping, and Keycloak puts a realm role into a token only when
the client's own scope admits it. Keycloak's example-token endpoint for the
client and its service account showed `client_type` and the audiences and
no `realm_access` claim at all. The registry-controller client met the same
rule in #268.

Fix: a realm scope mapping for `agent-role-kubernetes-read` on
`agent-tenant-test-conformance` (kcadm, 21:13; realm file in this PR), and
the Registry Controller keeps the client's scope mapping in step with the
service account's roles (zetra `fix/controller-role-scope-mapping`). The
session at 21:14 then returned 200 on `initialize`, `tools/list` and
`tools/call pods_list_in_namespace` at the gateway, with the APS allowing the
call on a cached exchange: sandbox, gateway JWT, APS exchange, gateway role
check and the kubernetes MCP server, all in one path. This also proves the
`jwt.realm_access.roles` nested-claim syntax on agentgateway 1.7.0 (spec
17.3), which the stages doc listed under T19.

### Run 7: T8 passes; two harness evidence bugs

Started 21:58:52 (Job created 21:58:47), finished 22:03:01, result `fail`.
Nine sessions, each `COMPLETED` with three boundaries (model, tool, model).
Before the run: Keycloak had crash-looped from 21:22 to 21:58 on
`--import-realm` because #303 put an `x-note` key on the new `scopeMappings`
entry (`Unrecognized field "x-note"`, fixed by #306); the agents IdP was down
for those 36 minutes and `agent-platform-workloads` waited on it. The
controller rolled to `624a0ba` and the release reached `Ready` at 21:58:25.

- **T8 pass**, every check true: session `s-beffaf6aa6185a00-g1`, one
  `tools/call pods_list_in_namespace` decision (`294fe168…`) with reason
  `allow`, agent `tenant-test/conformance`, the session's own id and no
  principal; none of the forged values (`tenant-test/other`, `mallory`,
  `0000`) appears in any decision; the probe reported `{"calls":["ok"]}`.
  The spec's capture at the MCP server stays `not captured`.
- **T5 pass** 8 / 8, each case's observed status equal to the expected one.
- **T19 fail on `exact_alternation` only.** Session `s-7b23e6f8f1b7ec9a-g1`
  (22:02:33 to 22:03:00) reported `ok, deny` five times, and the APS logged
  ten `tools/call` decisions for that pod with ten distinct ids, five
  `allow` on `pods_list_in_namespace` and five `deny.route_not_permitted` on
  `pods_get`: the platform did exactly what T19 asks. The harness reads the
  two APS replicas' logs one after the other and compared the lines in that
  order, so an alternation spread over both pods looked broken. Fixed in
  zetra `fix/harness-decision-order` (sort by decision timestamp; a test lays
  the lines out as two pods would).
- **T4 fail on `token_issued_for_pod`.** Session `s-fe9e21dcbf53ff0a-g1`
  (21:58:52 to 21:59:18) completed with `claims_reported` true, and the APS
  log holds `token issued` for that pod at 21:59:09.938 (jti
  `trrtcc:632c6dfd…`, namespace `tenant-test`), inside the window the
  harness read; the later tests read the same logs without trouble. The
  report's `token_issued` is empty. The reader replaced a failed pod read
  with a `log unavailable` line that the parser dropped, so the report could
  not show what was missing; the same zetra branch retries each pod read,
  keeps the marker as `aps_log_unreadable` evidence, and reads a second time
  for T4 when no issuance was seen. Whether a transient API error was the
  cause will show in run 8.

## Status of spec items touched today

| Item | Status |
|---|---|
| Keycloak issues a token to an agent (T4) | **Proven** 13:03:35, after the attribute fix; **T4 passed** 14:05 |
| TokenReview returns pod name and UID for the projected token (17.3) | Proven implicitly: the APS resolved `pod` and `namespace` for the issued token |
| IdP accepts the projected token as a client assertion with the exact client settings (17.3, 7.8) | Proven with `jwt.credential.issuer` / `jwt.credential.sub`; the spec 7.3 keys fail |
| Session runs through the Session Runner | **Completed** in run 5: seven sessions, three to five boundaries each, snapshots taken; run 6: seven sessions, three boundaries each |
| Sandbox network check end to end (egress guard) | **Passed** in runs 2 and 3 |
| Kyverno PolicyReports | **Written** (resolved 21:04): two admission EphemeralReports per sandbox pod from its first second and a PolicyReport at aggregation, all owned by the pod and gone with it; every earlier listing was taken after the run |
| T4, T5 | **Passed** in run 5 (14:04 to 14:08) with `conformance-2026-11-05-7af1dd4a`; **passed again** in run 6 (18:39 to 18:43) with `conformance-2026-11-05-c5b76ecc`, every check true; run 7: T5 passed again, T4's session completed but the harness's evidence read missed the logged token (see run 7) |
| T8 forged agent headers (8.8, 15) | **Passed** in run 7 (21:59 to 22:00): the decision carries the sandbox's own identity and no forged value |
| T19 no decision caching (15) | **Platform behaviour proven** in run 7: ten fresh decisions in exact alternation across both APS replicas; the harness read them out of order, fixed for run 8 |
| Settlement path gateway → Alloy → APS (8.9) | **Works** after kubani#288; it had silently dropped every batch since B3 |
| MCP route, agent-mode exchange (7.5, 9.5) | **Works** since 21:14: exchange with `scope=mcp:<backend>` (#299, #301), then the gateway's 8.8 role check with the client scope mapping. `tools/call pods_list_in_namespace` returned 200 through the kubernetes MCP server |
| `jwt.realm_access.roles` nested-claim syntax at the gateway (17.3, 8.8) | **Proven** 21:14: the same policy that denied the call without the claim allowed it once `realm_access.roles` carried the role |

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
5. **A dropped settlement stream is invisible until a session needs a second
   reservation.** Nothing in the APS logged the missing settlements; the
   evidence was in Alloy's exporter errors. Alloy exposes no failure counter
   for the OTLP log exporter, so #292 added `AgentPlatformSettlementStalled`
   (inference allowed, nothing settled in 30m) on the APS side, plus
   `AgentPlatformControllerRestarting`; the spec 13.8 rules are live in
   Prometheus since 2026-11-05 (Prometheus itself had been OOM-looping on WAL
   replay for four days until Al reset the WAL at 17:38 UTC).
7. **The agent-mode MCP exchange never worked**: Keycloak needs the audience
   scope on the requester and in the request. Found on 2026-11-05 by the
   first MCP call of any session; the T4/T5 runs never touch the MCP route,
   so nothing earlier could have shown it. Record as a spec 7.5 deviation.
6. ~~`claims_reported` is false in the passing T4~~ Closed by run 6: the cause
   was the 512-character summary cap, not the probe; zetra-agents#14 made the
   report compact (release v0.1.4).
8. **Kyverno reports were never missing**, only short-lived: a sandbox pod
   lives about 25 s and its reports are owned by it. Durable admission
   evidence for sandboxes is the admission log and the Kyverno events, not
   PolicyReports. Checked by polling during a session, not after.
9. **Spec 7.3 clients need a realm scope mapping for their backend roles.**
   `fullScopeAllowed: false` keeps the token minimal, but then the roles the
   controller assigns to the service account never reach `realm_access.roles`
   unless the client's scope admits them. Record as a spec 7.3 deviation next
   to the attribute keys of finding 2; the controller now writes the mapping.
10. **The harness must order APS decisions by time**: the APS runs two
    replicas and the harness reads their logs one pod after the other. Run 7
    read a correct T19 alternation as broken.
11. **A failed APS log read must be evidence, not silence.** Run 7's T4 lost
    a logged `token issued` line without a trace; the reader now retries,
    records unreadable pods and re-reads for T4.
12. **Realm-file notes belong only inside `attributes` maps**: an `x-note`
    key on a `scopeMappings` entry crash-looped Keycloak for 36 minutes
    (#303, fixed by #306) and froze every rollout that depends on the
    `keycloak` kustomization.
