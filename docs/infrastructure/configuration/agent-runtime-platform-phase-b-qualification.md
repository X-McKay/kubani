# Agent Runtime Platform: Phase B qualification, 2026-11-05 to 2026-11-06 (exact T4/T5, T13, T13b, T15, T19, T20, T22 and T25 qualified; Phase B incomplete)

Record of the Phase B conformance harness runs (spec 15, tests T4, T5, T6, T7, T8, T9a, T9b, T11, T12, T13, T13b, T15, T17, T19, T20, T22, T23, T25 and T26)
from [agent-runtime-platform.md](agent-runtime-platform.md), "Phase B
conformance harness". Every timestamp is UTC. The Phase B gate is 22 tests;
this document grows with each batch. Reports: run 3
[13:03](agent-runtime-platform-phase-b-run-2026-11-05T1303.json) (fail), run 5
[14:04](agent-runtime-platform-phase-b-run-2026-11-05T1404.json) (pass, one soft
check false), run 6 [18:39](agent-runtime-platform-phase-b-run-2026-11-05T1839.json)
(**pass, every check true**), run 7
[21:58](agent-runtime-platform-phase-b-run-2026-11-05T2158.json) (first T8/T19 run:
T5 and T8 pass, T4 and T19 fail on harness evidence handling), run 8
[22:13](agent-runtime-platform-phase-b-run-2026-11-05T2213.json) (**pass: T4, T5, T8
and T19, every check true**), run 9
[23:48](agent-runtime-platform-phase-b-run-2026-11-05T2348.json) (**pass: T4, T5, T8,
T11, T12 and T19, every check true, with the capture at the MCP server**).
On 2026-11-06: run 10
[08:17](agent-runtime-platform-phase-b-run-2026-11-06T0817.json) (T4 evidence
miss; T26 seed dropped by the old runner), run 11
[08:32](agent-runtime-platform-phase-b-run-2026-11-06T0832.json) (T5 and T11
model flakes; T26 donor state restored), run 12
[09:35](agent-runtime-platform-phase-b-run-2026-11-06T0935.json) (T4, T5, T8,
T11 and T19 pass; T12 model flake; T26 still fails before boundary 0).
Run 13 [16:07](agent-runtime-platform-phase-b-run-2026-11-06T1607.json) is
**the first T26 pass**, with all seven selected harness tests passing and every
check true. Run 14 [16:31](agent-runtime-platform-phase-b-run-2026-11-06T1631.json)
adds the first **T6/T7 pass**, with nine selected tests and all 94 checks true.
Run 15 [16:49](agent-runtime-platform-phase-b-run-2026-11-06T1649.json)
passes **T9a/T9b** but remains `error` because three T22 cases encountered
Pod Security Admission instead of the expected Kyverno rule. Run 16
[17:04](agent-runtime-platform-phase-b-run-2026-11-06T1704.json) passes all nine
selected tests and all 102 checks, including the first **full T19 qualification**:
50 MCP allow/deny cycles within 10 seconds and model-route alternation.
Run 17 [17:29](agent-runtime-platform-phase-b-run-2026-11-06T1729.json)
passes T9a/T9b/T22 with all 50 checks true, supplying the first corrected T22
pass. Run 18 [17:33](agent-runtime-platform-phase-b-run-2026-11-06T1733.json)
remains `fail`: T4 lacks matching issuance evidence and T11's model never calls
the probe. Its exact T5 human/API-token cases pass for the first time; T6/T7,
T8, agent-mode T12, full T19 and T26 also pass. Run 19
[17:44](agent-runtime-platform-phase-b-run-2026-11-06T1744.json) remains `fail`
on T15's first cancellation round, while T20 first passes all drift and
immutability checks. Run 20 [17:52](agent-runtime-platform-phase-b-run-2026-11-06T1752.json)
first passes **T25**, with all eleven protocol sessions and all 191 checks true.
Run 21 [18:27](agent-runtime-platform-phase-b-run-2026-11-06T1827.json)
passes all nine selected tests and all 115 checks, including the first **exact T4
pass** with matching issuance; T11 actually invokes its probe. Run 22
[18:35](agent-runtime-platform-phase-b-run-2026-11-06T1835.json) first passes **T15**, both rounds and all 38 checks, with exact restoration and cleanup.
Run 23 [18:38](agent-runtime-platform-phase-b-run-2026-11-06T1838.json)
first passes **T13b**, all 28 checks, against the dedicated byte-token backend.
Run 24 [18:44](agent-runtime-platform-phase-b-run-2026-11-06T1844.json)
remains **error** on T13 (`TimeoutError`); it supplies no passing daily-budget
verdict. Runs 25 [18:58](agent-runtime-platform-phase-b-run-2026-11-06T1858.json.gz),
26 [19:09](agent-runtime-platform-phase-b-run-2026-11-06T1909.json.gz) and
27 [19:13](agent-runtime-platform-phase-b-run-2026-11-06T1913.json.gz) remain **fail**
on T17. The first two never reach an outage. Run 27 records successful traffic
checks during a real outage but fails three operator-receipt/generation checks;
it does not qualify T17. Run 28 [19:50](agent-runtime-platform-phase-b-run-2026-11-06T1950.json.gz)
first qualifies T17 with all 18 checks. Run 29
[19:54](agent-runtime-platform-phase-b-run-2026-11-06T1954.json) remains failed on
T23's initial healthy-control transport correlation; no fault session runs.
Run 30 [19:58](agent-runtime-platform-phase-b-run-2026-11-06T1958.json) records
T13 TimeoutError with partial ledger evidence and no gateway replacement.
Run 31 [20:04](agent-runtime-platform-phase-b-run-2026-11-06T2004.json) remains
T27 **error**: capture never started, then missing receipt evaluation raised
AttributeError; no host packet evidence exists.
Run 32 [20:46](agent-runtime-platform-phase-b-run-2026-11-06T2046.json)
first qualifies **T13**, all 23 checks, with the separately approved retry2
identity and both exact gateway Pod replacements inside the active window.
Run 33 [20:52](agent-runtime-platform-phase-b-run-2026-11-06T2052.json) remains
**fail** on T23's first healthy-control transport correlation; the five faults
and second control did not run. Both runs confirmed session cleanup.
The Phase B gate remains incomplete.
Earlier T19 harness passes retain their
five-cycle coverage limit; run 16 supplies the expanded evidence. T12 covers agent-mode APS exchange;
delegated and native-exchange configurations remain unqualified. No earlier
failure is erased by a later pass. Review also found that the old T4 gate
did not assert every required token claim and T5 lacked a genuine human-token
case and used an APS-audience token in place of the API-audience case. Those
historical results remain harness passes. Run 18 supplies exact T5 evidence;
run 21 supplies the first exact T4 pass. Runs 18 and 19 retain their failures.
The exact T4/T5 implementation in zetra#44 and the T22 correction in zetra#45
were not deployed in runs 15 or 16. Run 16 did not select T22.

## What ran

| Item | Value |
|---|---|
| Kubani | Runs 1 to 5: `main` at `8880908e` (#282 controller memory), Job applied from the working tree with the session-runner digest of #283. Run 6: `main` at `d8270180` (#295), Job applied as committed. Run 7: `main` at `af54aeb4` (#305), Job applied as committed. Run 8: `main` at `f6ec966e` (#307), Job applied from the working tree with the session-runner digest of #308. Run 9: `main` at `a90ca95c` (#313), Job applied as committed. Runs 10 to 12: releases and conformance-b signer pin in #317 to #319; runner alignment in #320, workspace-only seed restore in #321. Run 13: `main` at `ac40f142` (kubani#323), all three runner consumers aligned |
| Platform | X-McKay/zetra `408cfab` (zetra#24 harness failure reasons, zetra#26 one cosign at a time); run 1 used the harness at `fe0cc5d`. Run 6 ran against the APS at `7045b5a` (#290, zetra#28). Run 7: session-runner `c53f630` (zetra#30, T8/T19 harness), APS `d4f2e05` (zetra#29), Registry Controller `624a0ba` (zetra#31). Run 8: session-runner `68be306` (zetra#32, evidence fixes). Run 9: session-runner `a7c2c27` (zetra#34, T11/T12 and the capture reader), capture sidecar `bc37532` (zetra#33, #37) on the kubernetes MCP server (#312, #314). Run 10: harness `3794070` (zetra#38, T26/seed) but tenant runner `158a170`. Run 11: harness and runner `3794070` (#320). Run 12: harness, tenant runner and cleanup reconciler `12369f4` (zetra#39, #321). Run 13: all three `e05c9ca` (zetra#40, kubani#323), digest `sha256:4c0dca3e8687e338d24008ba263516839f0fb0663ae9f0d68f7a06036fb77bf9` |
| Agent | `tenant-test/conformance`. Runs 1 to 3: AgentRelease `conformance-2026-11-03-4dfe2607` (zetra-agents `conformance/v0.1.2`, approved by #279). Runs 4 and 5: `conformance-2026-11-05-7af1dd4a` (`conformance/v0.1.3`, applied by #285, approved by #286). Run 6: `conformance-2026-11-05-c5b76ecc` (`conformance/v0.1.4`, applied by #294, approved by #295). Runs 7 to 9: `conformance-2026-11-05-e80880a1` (`conformance/v0.1.5`, `probe_mcp` added, applied by #304, approved by #305). Runs 10 to 14: `conformance-2026-11-06-fe7ac791` (`conformance/v0.1.6`) and `conformance-b-2026-11-06-e54fc106` (`conformance-b/v0.1.0`), both approved and Ready (#317, #318) |
| Harness Job | `agent-platform/conformance-harness` on strix, `agent-conformance --tests T4,T5`, seven sandbox sessions per run; from run 7 `--tests T4,T5,T8,T19`, nine sessions; from run 9 `--tests T4,T5,T8,T11,T12,T19`, eleven sessions; from run 10 add `T26`, fourteen sessions, `--agent-b conformance-b --release-b conformance-b-2026-11-06-e54fc106` and read-only access to the tenant artifacts PVC |
| Sandbox node | rig0, Kata `kata-qemu-runtime-rs`, boot 12.6 to 16.5 s per generation |
| Keycloak | 26.8.1, realm `agents`, identity provider `kubernetes-kubani` (type `CLIENT_ASSERTION`) |

Runs 15 and 16 use `session-runner:d17df45` at
`sha256:87d8adce668831801951afeec3b47e1244ee2fa8a2f697518dba22ef30e6c62f`
for the harness, tenant runner and cleanup reconciler (kubani#328, zetra#42/#43).
Run 15 uses the separate opt-in admission Job and conformance-b v0.1.0 fixture;
its report retains conformance v0.1.6 as the primary release. Run 16 uses kubani
`8f5d4802` (#329/#330) and the approved conformance v0.1.7 release
`conformance-2026-11-06-88b05a89`, image
`sha256:88b05a895fab7d9df7ff3c2fdb2a16c283a3b559f5f0558b13d2ce4a97b56aeb`.
Conformance-b remains v0.1.0. These image pins are retained in GitOps; the two
reports do not contain an automatic component inventory.

Runs 17–19 use runner `89034e2` at
`sha256:d6eba5d7edf98e3f719843c4d678b46d81ca2374f2bf9b7d1f093017bbf817b8`,
deployed by kubani#334 with the exact T4/T5, corrected T22 and T15/T20
implementations. Run 17's primary report retains conformance v0.1.6; run 18
uses conformance v0.1.7. Run 19's dedicated mutation fixture is the signed,
approved `conformance-b-2026-11-06-00fdab05` (v0.1.1, #335/#337).
These pins come from GitOps and operator records, not an automatic inventory
inside the reports. No later pending implementation is credited to these runs.

Run 20 uses the same `89034e2` runner and the dedicated signed, approved
`conformance-protocol-2026-11-06-4c529889` fixture (v0.1.0, #336/#338). Its
manual Job selects only T25 with a 1,800-second session timeout and runs
exclusively without other tenant sessions or worker/APS rollouts. Unlike earlier
reports, its worker inventories record the actual image digest, Pod UID and
restart count; the retained memory samples also identify the process.

Runs 21 and 22 use runner `d7950de` at
`sha256:b8c5a7b582cd2a534e451bff1fd8f921d465f3250ace7f0eb76feb7dff9355a8`
and APS `59e959f` at
`sha256:7c02db8bca220efda962a3569197f11bd096127fcec4358543b9f660480db54e`.
The runner includes the corrected log window (zetra#52) and stop-event timing
(zetra#51). The primary release is conformance v0.1.7. Run 22 mutates the
retained conformance-b v0.1.1 release `conformance-b-2026-11-06-00fdab05`;
it does not use the newer v0.1.2 release. Component pins and post-run Kubernetes
cleanup checks are operator/GitOps evidence, separate from the raw reports.

Runs 23 and 24 retain runner `d7950de` and APS `59e959f`. Their signed fixtures
are `conformance-budget-session-2026-11-06-33e221e7` and
`conformance-budget-day-2026-11-06-362f1075`, staged by #341 and separately
approved before execution. The enforced byte-token backend reserves 300 tokens
and computes 100 tokens per successful response. This qualifies the budget path,
not Qwen token accounting; production limits are unchanged.

Runs 25–27 retain the same `d7950de` runner/harness and `59e959f` APS image
throughout each batch. Their signed traffic fixture is
`conformance-b-2026-11-06-5928c578` (v0.1.2); the reports retain primary
`conformance-2026-11-06-88b05a89`. The helper correction in kubani#349 and the
new-Job UID launch binding precede run 27. These component pins are operator/GitOps
records; the reports directly retain the observed APS image IDs.

The four T17 raw reports (runs 25–28) exceed the repository's 500 KiB artifact limit. They
are retained as lossless `.json.gz` files; decompressing produces the exact
original report bytes, including every failed check. Plaintext summaries retain
all 18 checks and request/observation counts. Both original JSON secret scans and
individual hash/trace false-positive verification completed before compression;
no secret-scan exclusion or hook setting is changed.

| Run | Original JSON bytes | Decompressed SHA256 | Plaintext checks/counts |
|---|---:|---|---|
| 25 | 2,242,779 | `cdcb0e301a472c25d3889281eecd2382c1c6db24a0df3a36d2e10e3737c01d09` | [summary](agent-runtime-platform-phase-b-run-2026-11-06T1858-summary.json) |
| 26 | 2,225,253 | `b19b8311cb8ddedd6b92e3f17551af05cd6ee48b8a295b430889196e3f9df895` | [summary](agent-runtime-platform-phase-b-run-2026-11-06T1909-summary.json) |
| 27 | 2,152,599 | `87896c182576e0c1e6200904ec4d48db22e908382f2320386d1888d98de9bfdb` | [summary](agent-runtime-platform-phase-b-run-2026-11-06T1913-summary.json) |
| 28 | 2,232,709 | `491098a412ab06255c34f8dda2f312f67acc1262be0cd87123c989f743055532` | [summary](agent-runtime-platform-phase-b-run-2026-11-06T1950-summary.json) |

## Runs

Runs 1 to 9 are on 2026-11-05. Runs 10 to 12 and 15 to 30 give the harness start time;
their saved reports do not include the Job creation time. Runs 13 and 14 record both.

| Run | Job created / harness started (UTC) | Harness image | Result | Session outcomes and evidence |
|---|---|---|---|---|
| 1 | 11:44:57 | session-runner `fe0cc5d` | fail (T4 fail, T5 6 fail / 2 pass) | Runner preflight: `Forbidden: release not ready`. The Registry Controller had been OOM-killed on every start since 2026-11-02 (#282) and the release had lost `signatureVerified` |
| 2 | 12:48:59 | session-runner `408cfab` | fail (T4 fail, T5 6 fail / 2 pass) | `run_boundary` `OutcomeUnknown rc=1` on all three generations. The sandbox's POST to `token.agents.internal/v1/token` got 401: Keycloak `CLIENT_LOGIN_ERROR error=invalid_client_credentials`, "Client authentication was attempted did not complete for federated-jwt" |
| 3 | 13:03:16 | session-runner `408cfab` | fail (T4 fail, T5 6 fail / 2 pass) | `run_boundary` `BudgetExceeded: guest reported budget exceeded` (non-retryable). The token was issued; the first `llm-main` call was denied `deny.budget_exhausted` (gateway 429) |
| 4 | 13:58:36 | session-runner `408cfab`, release v0.1.3 | fail (T4 fail, T5 6 fail / 2 pass) | First `llm-main` call allowed and accepted (boundary 0, 780 tokens), `probe_files` tool boundary accepted, then the second `llm-main` call denied `deny.budget_exhausted`: no reservation was ever settled |
| 5 | 14:04:44 | session-runner `408cfab`, release v0.1.3 | **pass** (T4 pass, T5 8 / 8 pass) | Every session `COMPLETED` with 3 to 5 boundaries; one token per sandbox; all six sandbox refusal cases observed the expected 400 or 401 and the APS logged each refusal |
| 6 | 18:39:49 | session-runner `408cfab`, release v0.1.4 (`conformance-2026-11-05-c5b76ecc`, #294, #295) | **pass**, every check true | Same as run 5, and T4's `claims_reported` is now true: the compact `probe_files` report (zetra-agents#14) lists `/sandbox/state/token.json` with audiences `agent-gateway` and `agent-policy-service` beside the two projected-token paths |
| 7 | 21:58:47 | session-runner `c53f630`, release v0.1.5 (`conformance-2026-11-05-e80880a1`, #304, #305) | fail (T4 fail, T5 8 / 8 pass, **T8 pass**, T19 fail) | All nine sessions `COMPLETED` with three boundaries. T8 passed every check. T19's probe reported the exact `ok`/`deny` alternation and the APS logged ten distinct decisions, five `allow` and five `deny.route_not_permitted`, but the harness read them out of time order across the two APS replicas. T4's `token issued` line exists in the APS log at 21:59:09 and the harness's log read did not return it |
| 8 | 22:13:36 | session-runner `68be306`, release v0.1.5 | **pass** (T4, T5 8 / 8, T8, T19, every check true) | All nine sessions `COMPLETED` with three boundaries; no APS pod log was unreadable; T4's token found at 22:14:00; T19's ten decisions in exact alternation once ordered by time |
| 9 | 23:48:37 | session-runner `a7c2c27`, capture sidecar `bc37532`, release v0.1.5 | **pass** (T4, T5 8 / 8, T8 with its server half, **T11**, **T12**, T19, every check true) | All eleven sessions `COMPLETED` with three boundaries; no APS pod log unreadable; the capture at the MCP server carried the session header, the agent's `sub` with no `act`, the backend audience and only exchanged `jti`s |
| 10 | 2026-11-06 08:17:05 (harness start) | session-runner `3794070`; tenant runner still `158a170`; release v0.1.6 + conformance-b v0.1.0 | fail (T4, T26 fail; T5 8 / 8, T8, T11, T12, T19 pass) | All fourteen sessions `COMPLETED`; the old runner silently dropped `seed`, so both T26 recipient sessions reported `FileNotFoundError`. T4 missed a token line present in the APS log |
| 11 | 2026-11-06 08:32:15 (harness start) | session-runner `3794070` for harness and tenant runner; same releases | fail (T5 7 / 8, T11, T26 fail; T4, T8, T12, T19 pass) | T26 stash completed; both seeded sessions failed `run_boundary` with `OutcomeUnknown rc=5` in all three generations after restoring donor `state.json` with `next=3`. T5 omitted the status in its summary; T11 made an extra denied MCP call |
| 12 | 2026-11-06 09:35:45 (harness start) | session-runner `12369f4` for harness, tenant runner and cleanup reconciler; same releases | fail (T12, T26 fail; T4, T5 8 / 8, T8, T11, T19 pass) | T26 stash completed, but both seeded sessions still failed `run_boundary` with `OutcomeUnknown rc=5` in all three generations despite the workspace-only source fix. T12's model never called `probe_mcp`, leaving no server capture |
| 13 | 2026-11-06 16:07:04 / 16:07:06 | session-runner `e05c9ca` for harness, tenant runner and cleanup reconciler; same releases | **pass** (T4, T5 8 / 8, T8, T11, T12, T19, **T26 first pass**), every check true | Fourteen sessions completed; T26 stash and both seeded sessions completed in generation 1 with three boundaries. The same-agent request received 403 `deny.token_bound_elsewhere`; conformance-b received 403 `deny.pod_agent_mismatch`. T19 and T12 retain the coverage limits above |
| 14 | 2026-11-06 16:31:39 / 16:31:41 | session-runner `ef1a16f` on all three consumers; ARM64 model capture `ef1a16f-arm64`; same approved releases | **pass** (nine selected tests, all 94 checks true; **T6/T7 first pass**) | Fifteen sessions completed in generation 1. Direct engine 401/200; captured chat completions use the backend key, contain no agent JWT, and report nonzero usage. Temporary T6 policies removed; T4/T5/T12/T19 coverage limits remain explicit |
| 15 | 2026-11-06 16:49:33 | session-runner `d17df45`; conformance-b v0.1.0 and approved unsigned negative fixture; kubani#328 | **error** (**T9a/T9b pass**; T22 error) | Unsigned/unapproved sessions fail preflight at generation 0 without pod creation; five invalid direct release cases receive named Kyverno denials. All ten T22 mutations are rejected, but extra-container, hostPath and hostNetwork hit PSA instead of the expected rule. Both mutation tests report fixture restoration |
| 16 | 2026-11-06 17:04:11 | session-runner `d17df45`; conformance v0.1.7, conformance-b v0.1.0; kubani `8f5d4802` (#330) | **pass** (nine selected tests, all 102 checks true; **full T19 first qualified**) | Fifteen sessions complete in generation 1. T19 records 100 MCP requests in 8,109.933 ms, two model-route cycles, one token and 104 distinct correlated decisions. Historical T4/T5 and T12 coverage limits remain; T22 is not selected |
| 17 | 2026-11-06 17:29:44 | session-runner `89034e2`, kubani#334 | **pass** (T9a/T9b/T22, all 50 checks true; **T22 first pass**) | True generation-zero negative preflight, named Kyverno release denials, all ten T22 mutation refusals and positive controls pass. HostPath/hostNetwork use exact PSA Restricted evidence; extra-container and ephemeral-attach use named Kyverno rules. Fixtures restored |
| 18 | 2026-11-06 17:33:54 | session-runner `89034e2`; conformance v0.1.7 | **fail** (T4, T11 fail; **exact T5**, T6/T7, T8, T12, T19, T26 pass) | 104 of 115 checks true. T4 has exact claims but no matching issuance line; T11 ends after one model boundary without the probe. Genuine human and verified API-audience tokens receive 401 invalid_client. Full T19 completes 100 MCP requests in 8,174.404 ms |
| 19 | 2026-11-06 17:44:42 | session-runner `89034e2`; conformance-b v0.1.1 mutation fixture | **fail** (T15 first round fail, warm repeat pass; **T20 first pass**) | 60 of 63 checks true. Disable/re-enable works on both APS replicas; first cancellation timing evidence does not satisfy the harness. T20 observes drift in 231.771 ms, both-replica 403 in 501.869 ms, generation-zero preflight rejection and immutable-image 422. Exact fixture/policies/templates restored and cleanup confirmed |
| 20 | 2026-11-06 17:52:15 | session-runner `89034e2`; conformance-protocol v0.1.0 | **pass** (T25, all eleven sessions and 191 checks true; **T25 first pass**) | Five real boundary faults each recover through three generations from the accepted checkpoint, separated by six successful controls. Three real hangs reach the 290-second deadline. Same worker/process, zero restarts, bounded RSS/high-water growth and confirmed cleanup throughout |
| 21 | 2026-11-06 18:27:37 | session-runner `d7950de`, APS `59e959f`; conformance v0.1.7 | **pass** (nine selected tests, all 115 checks true; **exact T4 first pass**) | Exact claims from the committed snapshot match the sole issuance for the current Pod/JTI. Authentic T5 fixtures, actual T11 probe, full T19 (100 MCP requests in 8,123.955 ms) and T26 pass. T12 remains agent-mode only |
| 22 | 2026-11-06 18:35:31 | session-runner `d7950de`, APS `59e959f`; conformance-b v0.1.1 mutation fixture | **pass** (T15, both rounds, all 38 checks true; **T15 first pass**) | Both-replica disable bounds 347.231/1,038.309 ms; first-stop-to-same-replica-403 upper bounds 47.015/7.917 ms. Same Running Pod survives each delayed deletion; exact fixture/policies/templates restored, fresh session completes and cleanup confirmed |
| 23 | 2026-11-06 18:38:23 | session-runner `d7950de`, APS `59e959f`; conformance-budget-session v0.1.0 | **pass** (T13b, all 28 checks true; **T13b first pass**) | Exact 1,000-token session limit and 300-token reservation; ten concurrent requests admit three and refuse seven. Guest usage-zero tampering and normal generation-2 checkpoint restore still receive 429; independent session succeeds. Dedicated byte-backend scope only |
| 24 | 2026-11-06 18:44:17 | session-runner `d7950de`, APS `59e959f`; conformance-budget-day v0.1.0 | **error** (T13 `TimeoutError`) | Report ends 18:48:26 with no checks or retained per-request evidence; no T13 pass can be claimed from this report |
| 25 | 2026-11-06 18:58:14 | session-runner `d7950de`, APS `59e959f`; conformance-b v0.1.2 | **fail** (T17, 12 of 18 checks true) | Scale-to-zero patch fails after Flux pause; no down receipt and no outage. All 900 requests return 200; original replicas and annotation restored |
| 26 | 2026-11-06 19:09:08 | same runner/APS and signed B fixture | **fail** (T17, 12 of 18 checks true) | Operator launch races completed-Job deletion/recreation and receives 404 before any outage. All 900 requests return 200; no down receipt |
| 27 | 2026-11-06 19:13:06 | same runner/APS and signed B fixture | **fail** (T17, 15 of 18 checks true) | Real outage: 900 responses, 63 eligible requests all 403, uninterrupted 5 Hz, ten-second zero-Pod/endpoint window and restored successes. Three receipt/generation checks fail because pause/resume annotations also advance Deployment generation; no T17 pass |
| 28 | 2026-11-06 19:50:05 | session-runner `ce7c06b`, APS `e79bb04`; conformance-b v0.1.2 | **pass** (T17, 18 of 18 checks) | All 900 requests have real responses; 63 eligible requests all 403, exact pause/down/up/resume receipts, zero-Pod/endpoint window and restored successes |
| 29 | 2026-11-06 19:54:46 | same runner, signed conformance-checkpoint v0.1.1 | **fail** (T23, 3 of 5 top-level checks) | Initial healthy control completes three boundaries and cleanup; capture handshake fanout violates the one-record correlation assumption. No fault session starts |
| 30 | 2026-11-06 19:58:16 | same runner, signed conformance-budget-day-retry v0.1.0 | **error** (T13 TimeoutError) | Gateway replacement never occurs; operator log reader changes one-line JSON to a Python dictionary representation. Partial ledger/denial evidence retained; no daily-budget qualification |

The two direct cases pass in every run selecting T5 through run 16:
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

### Run 8: T4, T5, T8 and T19 pass

Started 22:13:41 (Job created 22:13:36), finished 22:17:59, result `pass`,
with session-runner `68be306` (zetra#32) and the same release, APS and
controller as run 7. Nine sessions, each `COMPLETED` with three boundaries;
`aps_log_unreadable` is empty for every test.

- **T4**: token issued at 22:14:00 for `s-e1cf16b994c0438b-g1`, exactly one
  per sandbox, `claims_reported` true. Run 7's miss did not recur; the
  report cannot say whether the second read was needed.
- **T5**: 8 / 8, each observed status equal to the expected one.
- **T8**: as in run 7, every check true for `s-90dd995ed0b19767-g1`.
- **T19**: `s-38a875cde37212c4-g1` (22:17:29 to 22:17:59): ten `tools/call`
  decisions with distinct ids in exact alternation of `allow` on
  `pods_list_in_namespace` and `deny.route_not_permitted` on `pods_get`,
  one evaluation per request, and the probe reported the same sequence.

Four of the 22 Phase B gate tests are now passed by the harness (T4, T5,
T8, T19), on top of the Phase A set (T1, T2a, T3, T28).

### Run 9: T11 and T12 pass with the capture at the MCP server

Started 23:48:42 (Job created 23:48:37), finished 23:53:41, result `pass`,
eleven sessions each `COMPLETED` with three boundaries, `aps_log_unreadable`
empty throughout. New since run 8: the capture proxy (zetra
`platform/capture`, #33 and #37) runs as a sidecar in the kubernetes-mcp
pod (#312, #314): the server listens on 8081 inside the pod, the proxy on
the pod's 8080, so the Service, both NetworkPolicies and the gateway backend
kept their port. It forwards every request and writes one JSON record with
the method, path, status, the `x-agent-*` headers and the bearer's `sub`,
`act.sub`, `aud`, `azp` and `jti`, never the token or a body (13.6). The
harness reads it, and the agents Gateway access log, through the API with
read-only Roles in `mcp` and `ai-gateway`; records are tied to a session by
the `x-agent-session-id` the APS sets on every upstream request.

- **T11 pass**: session `s-f649c2cce5dbfe22-g1`; every bearer the server
  received had `sub` `dcf3e4d4-…`, the same `jwt.sub` the gateway logged for
  the inbound agent token, no `act`, `aud`
  `https://mcp.almckay.io/kubernetes/mcp`, `azp` `agent-policy-service`; the
  APS allowed the call in agent mode; every upstream status was 200 or 202.
- **T12 pass**: the agent token's `jti` (`trrtcc:7a45458e…`) never appeared
  at the server; every captured `jti` (`trrtte:6316e277…`, on every request
  of the session) was the one the APS minted by exchange for that pod. The
  native-exchange configuration of 8.11 is not deployed and is recorded as
  not covered.
- **T8** now has its server half: the server received `x-agent-id`
  `tenant-test/conformance` and the session's own id, none of the forged
  values, and no `x-agent-decision-reason`; it also received
  `x-agent-decision-id`, `x-agent-generation`, `x-agent-policy`,
  `x-agent-release` and `x-agent-spiffe-id` as set by the APS.
- T4, T5 and T19 passed again with every check true.

On the way, the sidecar as first deployed (#312) answered 403 to every
request in 0 ms: the Go MCP SDK v1.8.0 the server is built on rejects a
request that arrives on 127.0.0.1 with a non-localhost `Host` header (DNS
rebinding protection). The kubernetes MCP backend was unusable for agents
from 23:35 to 23:48. zetra#37 makes the proxy set `Host` to the upstream
address and forward the original as `X-Forwarded-Host` (also in the record).

Six of the 22 Phase B gate tests are passed by the harness (T4, T5, T8,
T11, T12, T19), on top of the Phase A set.

### Between runs 9 and 10

T26 gained a snapshot seed channel in zetra#38 (`3794070`). The runner's
task validator rejects token-shaped text, so the bearer cannot be passed
in the task. `probe_token_stash` writes it to
`/sandbox/workspace/t26/token`; the harness reads the donor snapshot through
the artifacts PVC, verifies its `jti`, and supplies the snapshot key as
`SessionInput.seed` to the two recipient sessions. `probe_http(auth="stash")`
reads the restored workspace file. The report records identifiers and
checks, never the bearer.

zetra-agents#16 added the stash probe and the second identity,
`conformance-b`. Release builds initially failed with dind OOMs during a
degraded egress window (finding 15); rerunning one release at a time
produced `conformance/v0.1.6` and `conformance-b/v0.1.0`. The releases
`conformance-2026-11-06-fe7ac791` and
`conformance-b-2026-11-06-e54fc106` were approved and Ready by run 10
(#317, #318), with the conformance-b Kyverno signer pin in #319.

The new client also exposed the Registry Controller's FGAP v2 permission
gap: its POST to the client's realm scope mappings returned 403 (finding
14). Al applied the proposed narrow permission; the pickup notes reported
continued 403 responses and investigator `IdpError` at 08:00 UTC. A later
live check found investigator Ready, with a 07:55:09 UTC transition, and
only successful reads of existing mappings in recent logs (finding 14).
Current readiness does not prove that the controller can create a missing
mapping. At that point the grant remained unverified; finding 14 records
the later 16:57 UTC verification.

### Run 10: the old runner drops the snapshot seed

Started 2026-11-06 08:17:05, finished 08:23:22, result `fail`. The harness
was `3794070`, but the tenant runner was still `158a170`.

- **T26 fail**: the stash session completed and the harness read the token
  from its snapshot, with the expected issued `jti`. Both recipient
  sessions completed with `FileNotFoundError`, no binding decision and no
  403. The old runner's Temporal converter silently dropped the unknown
  `seed` field, so each recipient started with an empty workspace. #320
  aligned the tenant runner and cleanup reconciler with the harness.
- **T4 fail**: the session completed and `claims_reported` was true, but
  `token_issued_for_pod` and `one_token_per_sandbox` were false. The token
  line existed in the APS log for `s-d50620b6bdd3f966-g1`; the harness
  missed it again, as in run 7. `aps_log_unreadable` was empty, so the
  report does not explain the missed read.
- T5 (8 / 8), T8, T11, T12 and T19 passed with every check true.

### Run 11: a seed restores the donor's boundary state

Started 2026-11-06 08:32:15, finished 08:40:11, result `fail`, with the
harness and tenant runner on `3794070` after #320.

- **T26 fail**: the stash session and snapshot checks passed. Both seeded
  sessions failed before accepting any boundary, with retryable
  `run_boundary` `OutcomeUnknown rc=5` in generations 1, 2 and 3. The seed
  restored the donor's `state/` as well as its `workspace/`; the completed
  donor's `state.json` had `next=3`, while each new session requested
  boundary 0, causing a boundary mismatch. zetra#39 limits seed restores
  to `workspace/`; recovery of the same session retains the full snapshot.
- **T5 fail, 7 / 8**: `duplicate_field` ran `probe_http`, the APS logged
  the refusal and the session completed, but the model summarized it as
  `{"calls":["ok"]}` without a status. `status_reported` and
  `status_expected` were false; the report cannot assert the expected 400.
- **T11 fail on `agent_mode` only**: the model made an extra MCP call
  named `probe_mcp`, denied with `deny.route_not_permitted`, before the
  allowed `pods_list_in_namespace` call. The server capture still had the
  agent's subject, no `act`, the backend audience and successful statuses.
- T4, T8, T12 and T19 passed with every check true. T5's omitted status and
  T11's extra call are model behavior flakes, retained as failed results.

### Run 12: seeded sessions still exit 5 after the workspace-only source fix

Started 2026-11-06 09:35:45, finished 09:43:19, result `fail`. The harness,
tenant runner and cleanup reconciler were all on `12369f4` (#321), and the
zetra#39 workspace-only seed restore was verified in that image's source
copy. The post-run investigation below distinguishes it from the installed
package the worker actually imported.

- **T26 fail**: stash session `63617ea9-77d7-46f2-98c8-8811ded257e5`
  completed; the snapshot was readable and its token matched the stash
  pod's issued `jti`. Same-agent session
  `057b23fb-7835-4be9-9009-363c9f7591c7` and other-agent session
  `2333e812-089a-41ca-ad02-9791546101ff` each failed in all three
  generations with `rc=5 truncated=False timed_out=False`, no accepted
  boundaries and no APS binding decisions. Neither required 403 was
  observed. `never_allowed` alone cannot pass T26 when no request ran.
- **T12 fail**: its session completed at boundary 0 with summary `tool
  call`, but the model never invoked `probe_mcp`. No upstream record or
  exchanged `jti` was captured. This is a model behavior flake, not evidence
  that the agent token reached the server; the run remains failed.
- T4, T5 (8 / 8), T8, T11 and T19 passed with every check true.

At the end of this run the remaining T26 cause was unresolved. The agent
image pins agent-runtime at zetra `158a170`; its `step.py` has the same two
exit-5 paths: stdin `ProtocolError` and a boundary/state mismatch. The
runner retains exec stderr but omits it from `OutcomeUnknown`, so this
report cannot distinguish them. The next diagnostic is the seeded
boundary's stderr and workspace/state contents before boundary 0. The
workspace-only fix is necessary, but run 12 does not establish that it is
sufficient.

**Post-run-12 investigation, 2026-11-06:** the live image contains two
copies of the runner. `/app/runner/activities.py` has `SEED_RESTORE_CMD`
and `workspace_only`, but the installed
`/app/.venv/lib/python3.12/site-packages/runner/activities.py` has neither
and still restores the full archive. Its `run_boundary` traceback line
matches the worker's failure, and an isolated Python import confirms that
the installed module lacks `SEED_RESTORE_CMD`. The image inspection before
run 12 checked the source copy, not the package imported by the worker.
A direct diagnostic using the source copy restored a seed with no
`/sandbox/state` and completed boundary 0 with rc=0; its sandbox was
cleaned up. Repeating the diagnostic through the installed package restored
donor `state/` and returned rc=5 with `boundary mismatch`; that sandbox was
also cleaned up. This isolates the stale installed package as the reason
run 12 did not exercise zetra#39. The Dockerfile package reinstall fix was subsequently merged in
[zetra#40](https://github.com/X-McKay/zetra/pull/40), deployed through
[kubani#323](https://github.com/X-McKay/kubani/pull/323), and exercised by
run 13 below. Run 12 remains failed.

### Run 13: T26 first passes after the installed package is rebuilt

Job created 2026-11-06 16:07:04; harness started 16:07:06 and finished
16:13:30, result `pass`. The harness, tenant Session Runner and cleanup
reconciler all use `session-runner:e05c9ca` at digest
`sha256:4c0dca3e8687e338d24008ba263516839f0fb0663ae9f0d68f7a06036fb77bf9`
(zetra#40, kubani#323). This build reinstalls the runner after copying source
and verifies the imported package, so the worker executes zetra#39's
workspace-only seed restore. The approved conformance v0.1.6 and
conformance-b v0.1.0 releases are unchanged.

All seven selected tests pass, all checks are true, and every session
completed. The [raw report](agent-runtime-platform-phase-b-run-2026-11-06T1607.json)
contains identifiers and snapshot hashes, with no JWT. T26's 13 checks now
establish both rejection paths:

- Stash session `7f6b48fc-f3bd-4766-a3a2-75273e4058af` completed with
  `probe_token_stash`. The harness read the snapshot and matched its token
  `jti` to the APS-issued identity for the stash pod.
- Same-agent session `e739918f-a54c-4e65-a93b-5088a1b08ff3` completed with
  three boundaries in generation 1. Its replayed donor token received
  **403 `deny.token_bound_elsewhere`** at 16:12:56.113.
- Other-agent session `4bbd807b-94f9-476a-9591-ddb557de9f89` completed with
  three boundaries in generation 1. Its replayed donor token received
  **403 `deny.pod_agent_mismatch`** at 16:13:24.750. Neither recipient was
  allowed with the donor token, and no APS log was unreadable.

T4, all eight T5 cases, T8, T11 and the implemented T12/T19 checks also pass.
T12 observes only agent-mode APS exchange: delegated T10 and optional
native exchange are not exercised. T19 reports five MCP allow/deny cycles
(ten distinct decisions), not the full spec's 50 alternations within
10 seconds and allowed/forbidden model-route test. These are preserved
harness passes with explicit coverage limits, not full Phase B acceptance.
T6/T7 have not run in this report.

### Run 14: direct model authentication and backend-key replacement pass

The Job was created at 16:31:39 UTC; the harness ran from **16:31:41 to
16:38:43**, result `pass`. GitOps `aa5223cc` includes kubani#276 and #325.
All three runner consumers use `ef1a16f` at
`sha256:fd922ae7ec5ecc0eeb03cb14b6674d33ebfdbce40a9e43d7f3bda78cf5c52617`.
The main engine's ARM64 capture uses `ef1a16f-arm64` at
`sha256:69c984730ca5cafc840946240c3175160ff2bca09ff45f0de3c6fc49e8a87c26`.
Conformance v0.1.6 and conformance-b v0.1.0 remain unchanged.

All nine selected tests pass, **all 94 checks are true**, and all fifteen
sessions complete in generation 1. The [unchanged raw report](agent-runtime-platform-phase-b-run-2026-11-06T1631.json)
and [component image inventory](agent-runtime-platform-phase-b-run-2026-11-06T1631-components.json)
retain the evidence. The inventory is an operator-collected companion to the
harness report; automatic component inventory inside the harness remains open.

- **T6:** direct `llm-engine:8000/v1/models` returns 401 without a credential
  and 200 with the dedicated read-only backend-key mount. The two temporary
  harness-only NetworkPolicies were removed after collection. Tenant policies
  and sandbox mounts were unchanged.
- **T7:** session `93b42c1e-dadb-48cc-9700-1f2ac08a9a50` completes three
  boundaries. Both captured `POST /v1/chat/completions` calls return 200,
  have `backend_key_match: true`, and contain no agent JWT. Gateway and
  committed-boundary usage agree: 1,080/59 and 2,127/297 input/output tokens.
- **Existing cases:** T26 retains both required 403 denials. T8/T11 and the
  implemented T4/T5/T12/T19 checks pass; this run does not close their
  separately documented coverage gaps.

Both brokers are retained. Main sleep remains disabled; fast keeps level-1
sleep and 120-second auto-sleep. The authenticated fast watchdog succeeds.
The [gateway smoke check](agent-runtime-platform-vllm-smoke-2026-11-06.json)
records 200 responses and nonzero usage for AI, main and embeddings; the
separate fast-route check also returned 200 with 27 total tokens. One
[authenticated fast sleep/wake cycle](../inference/benchmarks/fast/20261106T1630Z_phase-b-api-key-wake.json)
passed both gates, with 702 ms sleep and 276.7 ms wake-to-first-token. Both
engines and brokers were Ready with zero restarts, all Flux Kustomizations
were Ready, and no tenant sandbox remained after the run.

### Run 15: admission preflight and release rules pass; T22 records PSA denials

The opt-in admission harness ran from **16:49:33 to 16:51:28 UTC**, overall
result `error`. The [unchanged raw report](agent-runtime-platform-phase-b-run-2026-11-06T1649.json)
contains 50 checks: 47 true and three false `expected_rule` checks in T22.
The dedicated fixture was `conformance-b-2026-11-06-e54fc106`; the unsigned
image fixture was `conformance-b-admission-unsigned-2026-11-06`, staged by
#326 and approved only for the negative tests in #328. The positive control
was admitted, and a valid runner sandbox was observed before the refusals.

- **T9a passes:** both unsigned and temporarily unapproved sessions fail
  non-retryable `Forbidden` at `preflight`, remain at generation 0, schedule
  neither generation setup nor `create_sandbox`, and have an empty pod list.
  Their only recorded activities are `preflight` and `stop_session`.
- **T9b passes:** direct server-side dry-runs reject the unsigned image via
  `agent-image-signature/verify-image-signature` (`no signatures found`).
  Unapproved, drifted, policy-digest-mismatched and agent-label-mismatched
  requests are each rejected by
  `agent-sandbox-admission/release-must-be-ready-and-match`.
- **T22 remains an error:** all ten invalid requests are rejected, including
  the dry-run ephemeral-container attachment to a valid live sandbox.
  Seven carry the expected named Kyverno rule. The other three return
  HTTP 403 from Pod Security Admission `restricted:v1.34`: the added
  container lacks `allowPrivilegeEscalation: false` and `capabilities.drop:
  [ALL]`; the hostPath volume violates restricted volume types; and
  `hostNetwork: true` violates host namespaces. These are actual admission
  denials, but the evaluator required a Kyverno rule and correctly retained
  them as errors under that implementation.

Every direct Pod create/ephemeral-container request used server-side dry-run;
no forbidden Pod or ephemeral container was instantiated. T9a and T9b both
report `fixture_restored: true`. The operator's post-run check confirmed the
exact conformance-b spec was restored, its release was Ready/NoDrift, and
no tenant sandbox remained.

zetra#45 corrects the extra-container fixture by copying the valid container's
security context and accepts only the exact expected Restricted-profile
hostPath/hostNetwork denials for those two T22 cases. It retains strict named
Kyverno evidence for T9b and rejects unrelated PSA/RBAC errors. This changes
the fixture and evaluator, not cluster policy. The fix was not deployed in
run 15 or 16. Run 15 remains a historical `error`; T22 needs a new passing
report from the corrected harness (finding 19).

### Run 16: full T19 cache-separation requirement first qualifies

The harness ran from **17:04:11 to 17:11:25 UTC**, result `pass`, with
conformance v0.1.7 and runner `d17df45`. The
[unchanged raw report](agent-runtime-platform-phase-b-run-2026-11-06T1704.json)
passes T4, T5, T6, T7, T8, T11, T12, T19 and T26: **all 102 checks are true**,
and all fifteen recorded sessions complete in generation 1. The v0.1.7
release (#329/#330) supplies the full T19 probe from zetra-agents#17; the
runner includes the matching evaluator from zetra#43.

T19 session `a8524e13-8ccf-42dd-ae83-cac18a20e985`, pod
`s-d1fe9cc48a221839-g1`, completes from 17:09:06 to 17:10:02. Its accepted
snapshot supplies the raw probe result, with no snapshot-read error:

- **50 MCP cycles / 100 requests in 8,109.933 ms:** the same token alternates
  allowed `pods_list_in_namespace` (200) and forbidden `pods_get` (403) on
  the same Kubernetes MCP path. All 100 requests match distinct APS
  decisions by trace ID, in the exact expected order.
- **Two model-route cycles / four requests:** `llm-main` returns 200 and
  `llm-fast` returns 403 on both cycles, with the same token and four
  distinct matching APS decisions. The separate model probes are outside
  the measured MCP interval; the 10-second bound applies to the MCP batch.
- All 104 decision IDs are distinct; each request has exactly one decision,
  allowed/forbidden reasons match, and no APS log source is unreadable.
  All 14 T19 checks are true.

This is the first retained run that covers the complete T19 requirement;
earlier five-cycle harness passes remain historical partial coverage. T6/T7
and both T26 rejection paths pass again. **T4/T5 still use the older checks:**
run 16 does not assert every required claim, has no genuine human-token case,
and labels an APS-audience token as `wrong_audience` instead of proving the
API-audience case. The exact implementation in zetra#44 was not deployed.
T12 still covers agent-mode APS exchange only. Admission tests were not
selected, so this run does not resolve run 15's T22 errors or complete Phase B.

### Run 17: corrected admission batch first qualifies T22

The [unchanged raw report](agent-runtime-platform-phase-b-run-2026-11-06T1729.json)
runs **17:29:44–17:31:49 UTC**, result `pass`: T9a, T9b and T22, **all 50
checks true**. This is the live rerun of the corrected zetra#45 fixture/evaluator
on runner `89034e2`; run 15 remains its original historical `error`.

T9a retains both positive controls and true generation-zero unsigned/unapproved
refusals, with no generation set or sandbox creation. T9b's five invalid release
cases retain named Kyverno evidence: unsigned image signature verification,
then release readiness/identity/digest rules. T22's ten mutations all fail:
extra-container now reaches `sandbox-no-extras`; ephemeral attach reaches
`agent-sandbox-deny-ephemeral-containers/deny-ephemeral-containers`; the two host
cases have the exact PSA Restricted hostPath/hostNetwork HTTP 403 violations.
The other six cases receive their named Kyverno HTTP 400 rule denials. Valid
controls are admitted. Forbidden Pod mutations remain server-side dry-runs.
Both mutable tests report exact fixture restoration; operator verification
found the original conformance-b spec, Ready/NoDrift and no remaining sandboxes.

### Run 18: authentic T5 fixtures pass; T4 evidence and T11 probe remain failed

The [unchanged raw report](agent-runtime-platform-phase-b-run-2026-11-06T1733.json)
runs **17:33:54–17:41:23 UTC**, result `fail`, **104 of 115 checks true**.
Runner `89034e2` now includes zetra#44's exact token checks. T5, T6, T7, T8,
T12, T19 and T26 pass; T4 and T11 fail.

- **T5 first qualifies the authentic fixtures.** All nine cases pass. The API
  token is verified through the Kubernetes API and carries the cluster's API
  audiences; the genuine `conformance-alice` token is verified against the
  configured issuer/JWKS and `agent-cli` identity. Both receive exact HTTP 401
  `invalid_client`, without a returned token. The six sandbox form refusals and
  non-sandbox-pod case also pass. Earlier T5 passes retain their narrower scope.
- **T4 stays failed.** Session `5b12d716-ce16-44d6-be03-e86fbb4f4f20` completes
  in generation one. Its accepted snapshot proves the exact issuer, agent ID,
  agent client type, both audiences and a 300-second lifetime. No source is
  marked unreadable, but `token_issued` is empty, leaving issuance, one-token
  and matching-JTI checks false. A later fix preserves the original log cutoff
  across slow replica reads and retries only on the exact tenant/pod/JTI; it
  requires a new live report (finding 20). A separate
  [post-run log read](agent-runtime-platform-phase-b-run-2026-11-06T1733-t4-postrun.json)
  at 17:55:33 UTC confirms the exact snapshot JTI was issued at
  **17:34:12.887866593 UTC** on APS replica `tscvj`, for the same namespace,
  agent and Pod. This diagnostic is additional evidence, not a rewritten report.
- **T11 stays failed.** Session `a6cc3cf4-66b9-4d95-88e3-a9014742a698` completes
  after one model boundary, which uses all 2,048 output tokens. It never runs
  `probe_mcp`; there is no MCP decision or upstream capture. The model's
  `tool call` summary is not evidence that a tool ran. Earlier T11 passes remain.
- **Full T19 passes again:** 100 MCP requests in **8,174.404 ms**, four separate
  model requests, one token and 104 distinct correlated decisions. T12 still
  covers agent-mode exchange only; it does not establish delegated behavior.

### Run 19: T20 qualifies; first T15 cancellation timing remains failed

The [unchanged raw report](agent-runtime-platform-phase-b-run-2026-11-06T1744.json)
runs **17:44:42–17:47:31 UTC**, result `fail`, **60 of 63 checks true**.
The dedicated conformance-b v0.1.1 fixture runs against the same two APS replicas.

T15's disable/re-enable checks pass in both rounds: both-replica observed denial
bounds are **714.280 ms** and **298.200 ms**, below five seconds. The exact same
running sandbox is held during cancellation by a named Kyverno DELETE-denial
rule tied to the captured Policy and Pod UIDs. Round one records real HTTP 403
`deny.session_inactive` from both replicas, but its cancellation-to-observation
bound is **2,583.326 ms**, and the report contains no accepted same-replica
stop/denial pair. Its three timing checks fail. Round two passes, including a
**22.896 ms** conservative same-replica stop-to-403 upper bound. Both rounds
restore the exact Agent, deletion policy, policy digest and templates, confirm
sandbox deletion and a cancelled workflow, and a fresh restored session completes.

Post-run review found two evaluator issues (finding 21): the first stop log at
17:45:08.565989092Z and the first decision's millisecond-truncated 17:45:08.565Z
produce an ambiguous negative point delta, and polling stopped at any stop log
rather than waiting for a later valid pair. Separately, the harness applied the
one-second stop-to-denial requirement to cancellation-request/log-observation
latency. The planned correction keeps real stop-to-403 and both-replica denial
evidence mandatory, and makes cancellation latency informational. **Run 19 is
not reclassified by this diagnosis; T15 requires a new passing report.**

T20 first passes: release `policyDrift=true`/`ready=false` is observed within
**231.771 ms**, with approved digest and generated templates unchanged. The
running sandbox gets real HTTP 403 `deny.release_unapproved` from both replicas
within **501.869 ms**. A new submission fails preflight at generation zero with
no Pod or generation set. The image edit is a server-side dry-run rejected with
HTTP 422 `image is immutable`. Same-session allows resume after restoration,
cleanup is confirmed, and a fresh session completes. No release image or status
was fabricated or changed.


### Run 20: protocol faults and bounded worker memory first qualify T25

The [unchanged raw report](agent-runtime-platform-phase-b-run-2026-11-06T1752.json)
runs from **17:52:15 to 18:13:40 UTC**, selecting only T25. The signed protocol
fixture directly emits the specified wire faults; it does not depend on a model
calling a probe or an SDK normalizing invalid output. All **eleven sessions and
191 checks** pass. The sequence is one healthy control, then each of five fault
sessions followed by another healthy control.

| Fault | Recorded boundary-1 result in each of generations 1, 2 and 3 |
|---|---|
| 10 MiB stdout | `OutcomeUnknown`, `truncated=True` |
| Invalid JSON | `OutcomeUnknown`, `malformed boundary output` |
| Wrong boundary number | `OutcomeUnknown`, `inconsistent boundary output` |
| `done: true` with exit 0 | `OutcomeUnknown`, `inconsistent boundary output` |
| Actual indefinite hang | `OutcomeUnknown`, `timed_out=True`; observed durations 290.467, 290.459 and 290.452 seconds |

Each fault session accepts only boundary 0 and its durable checkpoint. Trusted
Temporal event ordering shows confirmed deletion before advancing the generation
fence and creating its replacement; generations 2 and 3 restore that same
checkpoint. The fault sessions end `FAILED` as expected, with no fault output
accepted as progress. All six controls end `COMPLETED` in generation 1. Every
session records `stop=OK`, `delete=DELETED`, `grant=OK`, `CLEANED` and no remaining
session Pods. These expected failed sessions are passing robustness cases.

The exclusive batch retains **226 process-memory samples**, including every
boundary start and end, plus twelve worker inventories. All identify the same
Ready worker `session-runner-tenant-test-69ffcc5cb-zfv92`, Pod UID
`0e8d4560-510d-4dc5-8e4e-fa2b3081176f`, process identity ending `:1:708957251`,
image digest recorded above and zero restarts. Linux RSS rises from
121,929,728 to at most 122,888,192 bytes (**958,464 bytes** growth); kernel
high-water remains 125,071,360 bytes. Both meet the explicit 64 MiB growth bound
and 64 MiB headroom requirement against the configured 1 GiB limit. This is
process-wide sampled RSS plus kernel high-water evidence for this exclusive
batch, not an arbitrary-duration or concurrent-load memory guarantee.

Run 20 supplies the first retained T25 qualification. Earlier T4/T11/T15 failures
and the remaining Phase B coverage gaps are unchanged. No later runner or APS
fix is credited to this `89034e2` run.

### Run 21: exact T4 first passes; all nine selected tests pass

The [raw report](agent-runtime-platform-phase-b-run-2026-11-06T1827.json)
runs from **18:27:37 to 18:34:52 UTC** (Job completed 18:34:55). All **115 of
115 checks** pass across T4, T5, T6, T7, T8, T11, T12, T19 and T26.

- **Exact T4 first passes.** Session `e193303d-f31c-43c5-a5ca-507c80755764`
  completes three boundaries in generation 1. The verified committed snapshot
  supplies the required issuer, exact audiences, agent/client identity and
  300-second lifetime. Its JTI `trrtcc:5f2e819c-46c7-82fb-7b7e-ea2af4a39c79`
  matches the sole APS issuance for `tenant-test/s-e24810769e5df22e-g1` at
  **18:27:54.152445904 UTC**. All APS log sources are readable. The corrected
  reader preserves the initial cutoff across slow replica reads; it does not
  relax the exact Pod, namespace or JTI match.
- **T5 and T11 pass.** All nine T5 cases include the authentic human and
  verified API-audience fixtures. T11's session
  `a5b93ce6-5ea7-4357-81dc-1ae7f0a645c9` actually commits `probe_mcp` at
  boundary 1. The allowed read reaches the server with the agent subject,
  backend audience, no `act`, and successful upstream statuses.
- **Full T19 passes again:** 100 MCP requests in **8,123.955 ms**, four separate
  model requests, one token and 104 distinct correlated decisions. T6/T7, T8,
  agent-mode T12 and both T26 rejection paths also pass. This does not qualify
  delegated or native exchange.

The operator confirms no tenant sandboxes remain and removes the temporary T6
NetworkPolicies and human-token Secret. This new report closes the exact T4
coverage gap; **run 18 remains failed on T4/T11**, including its separately
retained post-run issuance evidence.

### Run 22: active-session revocation first qualifies T15

The [raw report](agent-runtime-platform-phase-b-run-2026-11-06T1835.json)
runs from **18:35:31 to 18:36:56 UTC** (Job completed 18:36:59). T15 passes
both rounds and **all 38 checks**, using the same two Ready APS replicas
`agent-policy-service-85b4886b57-c68w5` and
`agent-policy-service-85b4886b57-qbgmz` throughout.

- **Disable and restore:** real `403 deny.release_unapproved` responses are
  observed from both replicas within conservative bounds of **347.231335 ms**
  and **1,038.308622 ms**, below the five-second requirement. Re-enabling the Agent
  returns both replicas to allow for the same session and pinned token.
- **Cancel with deletion deliberately delayed:** the exact named Kyverno
  deletion rule and Policy UID are evidenced, while the same Pod UID remains
  Running with no deletion timestamp before and after APS stop. Each round
  records real HTTP 403 from both replicas. The first actual stop and the later
  403 on that same replica establish conservative upper bounds of
  **47.014874 ms** and **7.917081 ms**, below one second. Nanosecond stop and
  millisecond decision precision are handled conservatively; a later idempotent
  stop cannot reset the clock. Cancellation-to-observation latency is retained
  separately as information.
- **Restoration and cleanup:** both workflows close as `CANCELED`, each held
  sandbox is subsequently deleted, and exact Agent/release, Policy and template
  restoration checks pass. A fresh session
  `20ec5140-3d53-4585-83c8-cffbe0619053` completes after restoration.

The deployed `d7950de` implementation explicitly patches `Agent.spec.enabled`
to false and restores the original spec; `deny.release_unapproved` is the shared
APS reason for this Agent-disabled path, not evidence that release approval was
changed. The raw mutation receipts retain request/ack timing, not the patched
field values; that operation is established by the pinned implementation.

The operator's before/after records at
`/tmp/phase-b-next/run22-{agent,release}-{before,after}.json` additionally verify
unchanged Agent/release UIDs and complete specs. The temporary Policy, Role and
RoleBinding are removed and no tenant Pods remain. **Run 19 retains its original
T15 failure**; run 22 is the new passing evidence from the corrected timing gate.

### Run 23: session budget, concurrency and tampered-state recovery qualify T13b

The [raw report](agent-runtime-platform-phase-b-run-2026-11-06T1838.json)
runs from **18:38:23 to 18:43:10 UTC** (Job completed 18:43:12).
All **28 checks** pass for the dedicated signed session-budget fixture. The
session limit is exactly **1,000 tokens**, daily limit 2,000,000, enforced
reservation **300**, and computed usage **100** per allowed response.

- **Concurrent reservation:** after a 100-token warm call, ten simultaneous
  requests admit exactly three and immediately refuse seven with APS budget
  denials. All ten decisions precede the first backend response. Trusted ledger
  observations show 900 tokens in flight, then 400 spent/zero in flight after
  settlement; no request admits beyond the limit.
- **Exhaustion survives guest tampering and recovery:** four more allowed calls
  bring the session to 800 spent. The next 300-token reservation is refused with
  429. The guest actually zeroes its committed usage state, yet another request
  remains 429. Normal recovery restores that exact zeroed checkpoint into
  generation 2 and is still refused. Trusted history confirms deletion before
  the generation fence and replacement create; committed guest state cannot
  refund the APS ledger.
- **Independent session and settlement:** the control session's before/after
  requests both succeed. The report correlates all 20 requests (ten 200, ten
  429), with no extra/missing APS or backend decision. All successful response
  settlements are observed within **1.053 seconds**, below five seconds.
  Thirty-five trusted ledger observations cover the requests. Final spent is
  800 for the exhausted session, 200 for the control and 1,000 for the day;
  in-flight balances are zero and spent never decreases.

Both signed-fixture workflows complete; the operator confirms no tenant Pods
remain. This is the first T13b budget-path qualification using the dedicated
byte-token backend. It does **not** establish Qwen accounting accuracy.

### Run 24: daily-budget batch records a timeout

The [raw report](agent-runtime-platform-phase-b-run-2026-11-06T1844.json)
runs from **18:44:17 to 18:48:26 UTC** and ends with T13 `result: error`,
`error: TimeoutError`. It contains no checks or per-request/ledger evidence.
Preserve this failed attempt; a later diagnosis or supplemental observation
cannot turn it into a passing report. T13 requires a new complete live report.

**Separate post-run diagnosis:** the [operator replacement receipt](agent-runtime-platform-phase-b-run-2026-11-06T1844-postrun-gateway.json)
records exact-UID deletion requests at **18:48:27.290517635 UTC** and
**18:48:27.305972157 UTC**, after the report had already ended. The operator acted
too late for the harness's 100-second replacement window. The receipt includes the
exact Job/harness Pod identities and the two old gateway UIDs; it is not a new
conformance verdict. Both replacement gateway Pods were subsequently Ready and no
tenant Pods remained. The operator also observed 18 successful 100-token backend
responses and a retained daily ledger of 1,800 spent; the ledger was not reset.
A timestamped kubelet log places the replacement event at **18:46:44.406998244
UTC**, 102.884 seconds before the first deletion request, beyond the 100-second
gate. A later isolated no-secret probe returned logs while its Job was Running
(Python API 9.4 ms; kubectl 39.2 ms), so library buffering was not reproduced.
The cause of the late operator reaction remains an instrumentation/timing gap;
future receipts must include start, event, deadline and active-Job observations.

### Run 25: scale patch fails before the APS outage

The [unchanged report](agent-runtime-platform-phase-b-run-2026-11-06T1858.json.gz)
runs from **18:58:14 to 19:01:44 UTC** (Job 18:58:12–19:01:47) and remains
`fail`, with **12 of 18 checks true**. Session
`c4c0271e-d3d4-4a5c-9993-777e4c6e00cc` records 900 real HTTP 200 responses at 5 Hz,
900 correlated gateway records and 783 Kubernetes observations. No request is
eligible for an outage-denial check because no outage is established.

The separate [operator state](agent-runtime-platform-phase-b-run-2026-11-06T1858-operator.json)
and [published receipt](agent-runtime-platform-phase-b-run-2026-11-06T1858-receipt.json)
retain no `down` or `up` operation. Operator logs place the baseline at
18:58:40.152 UTC: Flux pause succeeds, then the scale-to-zero patch fails; the
original invocation discarded the API stderr. A later server-side dry-run
reproduces stale-resourceVersion JSON `test` as generic 422 and atomic
resourceVersion `replace` as the canonical 409 storage conflict. The corrected
helper retains UID/spec/replica/annotation guards and retries only that exact
bounded storage-conflict case; this diagnosis does not rewrite run 25.

The operator's `finally` restores two replicas and the original absent Flux
annotation. Observations record generations 4, 5, 6, always with two replicas and
the original Pod UIDs. Generation-one completion/cleanup passes, and the operator
confirms no tenant Pods remain. The six failed outage/receipt checks are retained.

### Run 26: operator launch races Job replacement before any outage

The [unchanged report](agent-runtime-platform-phase-b-run-2026-11-06T1909.json.gz)
runs from **19:09:08 to 19:12:36 UTC** (Job 19:09:06–19:12:39), again `fail`
with **12 of 18 checks true**. Session
`2f3160f2-4a88-4363-a716-9ecb978ecde8` records 900 real HTTP 200 responses, 900
correlated gateway records and 771 Kubernetes observations. Deployment generation 6
and the two original Ready replicas persist; there is no observed outage.

The operator started against the old completed Job while the collector deleted
and recreated it. Its GET returned 404 before scale-down. The retained
[operator state](agent-runtime-platform-phase-b-run-2026-11-06T1909-operator.json)
and [receipt](agent-runtime-platform-phase-b-run-2026-11-06T1909-receipt.json)
contain neither a down operation nor bound active Job/Pod UIDs. Restoration is
recorded, generation-one cleanup passes and no tenant Pods remain. The next
launch binds the newly created Job UID and exact probe marker; run 26 remains
failed independently of run 25's scale-patch failure.

### Run 27: real outage traffic passes but generation receipts fail

The [unchanged report](agent-runtime-platform-phase-b-run-2026-11-06T1913.json.gz)
runs from **19:13:06 to 19:16:31 UTC** (Job 19:13:03–19:16:35) and remains
`fail`, with **15 of 18 checks true**. Its
[launch record](agent-runtime-platform-phase-b-run-2026-11-06T1913-launch.json)
binds the new Job UID `9c3d297c-f540-4b46-abb0-83e7497ed7c2` and marker
`18fb6b4f3ee61b35`. Session `d249deda-39cb-4d3f-9306-35927f530e94` records 900
actual responses: 802 HTTP 200 and 98 HTTP 403, with 900 correlated gateway records and 771
Kubernetes observations. All 63 requests eligible from one second after the
operator scale-down request receive actual 403. Five-Hz continuity, all real
responses, five-second successful baseline/recovery windows and at least ten
seconds with no APS Pods or endpoints pass. Missing responses/timeouts are not
counted as denials. Generation-one completion/cleanup also passes.

The [operator state](agent-runtime-platform-phase-b-run-2026-11-06T1913-operator.json)
and [published receipt](agent-runtime-platform-phase-b-run-2026-11-06T1913-receipt.json)
record scale-down request/ack at 19:13:30.433673389/19:13:30.549760336 UTC and
scale-up at 19:13:44.039682957/19:13:44.158776244 UTC. The operator observes two
new Ready Pods and restores the original absent Flux annotation; no tenant Pods
remain. These observations support the narrower traffic/restoration statements,
not a passing T17 verdict.

Three checks are false: `explicit_operator_receipts`,
`only_recorded_replica_changes`, and `two_new_ready_replicas_restored`. The
receipt evaluator expected only the two scale operations to advance Deployment
generation. In this cluster, the pause annotation advances baseline 6 to 7,
scale-down to 8, scale-up to 9 and annotation restoration to 10. The original
receipt omits the annotation transitions. Record and validate those exact
UID/spec/resourceVersion-bound operations, retain the original failed report,
and obtain a fresh complete T17 pass. Do not loosen traffic, outage-duration,
configuration or identity requirements to accommodate missing receipts.

### Run 28: APS outage first qualifies T17

The [original compressed report](agent-runtime-platform-phase-b-run-2026-11-06T1950.json.gz)
runs from **19:50:05 to 19:53:32 UTC** and passes **all 18 checks**. Its
[plaintext summary](agent-runtime-platform-phase-b-run-2026-11-06T1950-summary.json)
retains each verdict. Session `477d2406-386c-49d5-aa92-db051721352f` has 900 real
responses: 803 HTTP 200 and 97 HTTP 403, 900 gateway records and 772 Kubernetes
observations. All 63 requests eligible from one second after scale-down receive
actual 403. Continuous 5 Hz, five-second all-allow baseline/recovery windows,
at least ten seconds with no APS Pods or endpoints, one token outliving the
probe, and generation-one completion/cleanup all pass. No timeout or missing
response is counted as a denial.

The [operator receipt](agent-runtime-platform-phase-b-run-2026-11-06T1950-operator.json)
uses schema `t17-v2` and records every exact transition: baseline generation 11,
Flux pause 12, scale-down 13, scale-up 14 and annotation restoration 15. Scale-down
request/ack are 19:50:32.199295125/19:50:32.298513883 UTC; scale-up request/ack are
19:50:45.812921125/19:50:45.918559145 UTC. Its UID/spec/resourceVersion guards and
annotation hashes pass. Two new APS Pods become Ready; the original two replicas
and absent Flux annotation are restored, with no tenant Pods remaining. The
[launch binding](agent-runtime-platform-phase-b-run-2026-11-06T1950-launch.json)
uses new Job UID `02045ea2-96e2-4df7-b86a-99554e5a59b1` and marker
`e3ae32dff96866bf`. Runs 25–27 remain unchanged failures.

The [component inventory](agent-runtime-platform-phase-b-run-2026-11-06T1950-components.json)
records runner/reconciler `ce7c06b` at digest
`48ef7c54e41b4ccf0958ff29fd88a3263d59fe6d7d455f0589cac4f0788feca1`
and APS `e79bb04` at digest
`569cf7ffa3d41665ab36ad6078e9a92d90beffd105f806cfca4e45b599700ae5`.
The signed traffic fixture remains B v0.1.2 `5928c578`; this is the first complete
T17 pass, not a change to the original failed reports.

### Run 29: T23 healthy control exposes capture fanout

The [unchanged report](agent-runtime-platform-phase-b-run-2026-11-06T1954.json)
runs from **19:54:46 to 19:55:42 UTC** and remains `fail`: **3 of 5 top-level
checks** and **11 of 13 initial-control checks** are true. The signed checkpoint
[release](agent-runtime-platform-phase-b-run-2026-11-06T1954-release.json) is
`conformance-checkpoint-2026-11-06-66f46e84`. The
[control binding](agent-runtime-platform-phase-b-run-2026-11-06T1954-control.json)
and [worker inventory](agent-runtime-platform-phase-b-run-2026-11-06T1954-components.json)
retain the fresh run ID and the same `ce7c06b` image as production.

The only session, `5d0dd18f-d4e8-4393-8f81-37200031b4d0`, completes all three
boundaries in generation 1, with three hash-verified 2,109,440-byte checkpoints,
normal `DELETED` cleanup, and no remaining Pod. No fault case or final control is
launched because the initial control does not meet its evidence gate. The false
control checks are `complete_transport_correlation` and
`real_mcp_gateway_and_capture_success`; the two false aggregate checks are
`all_evidence_gates` and `all_five_faults_and_two_controls`.

One tools/call decision, `3cf0810c-a1c5-48b5-ac51-16b20aceaadd`, has one APS and one
gateway record but three backend capture rows. All four selected decision IDs
are present; backend rows total ten. Post-run investigation found the pinned
gateway's stateless MCP path initializes an upstream session before forwarding
each non-initialize request. The original report cannot classify those rows and
must remain failed. The correction records only a bounded fixed RPC-method enum,
then requires the exact initialize/notification/original sequence, statuses and
identity for each decision. It must still reject extra, missing, duplicate or
unclassified evidence. Local tests do not qualify T23; a fresh complete seven-case
report is required. Temporary Jobs, RBAC and control were removed after cleanup.

### Run 30: daily-budget retry retains evidence but misses replacement

The [unchanged report](agent-runtime-platform-phase-b-run-2026-11-06T1958.json)
runs from **19:58:16 to 20:02:27 UTC** and remains `error`, with `TimeoutError` in
phase `gateway_replacement`. `fixture_validated` is true and
`orchestration_completed` is false. It uses the separate signed
`conformance-budget-day-retry` fixture, preserving the original day fixture's
spent ledger. This still measures the dedicated byte-token budget path, not
Qwen accounting.

Unlike run 24, the report retains partial session, trusted ledger, denial and
gateway evidence. The first session is
`864edc86-1210-4492-8e69-ac28482ea10a`; its final retained trusted daily ledger is
1,800 spent and zero in flight. The original and retry ledgers are not reset. The replacement event is emitted at
20:00:44.745503302 UTC after the explicit one-second response barrier; the
100-second watcher expires after 100.484 seconds. Both gateway UIDs and their
configuration fingerprint remain unchanged, so `old_uids_absent` and
`completed` are false. The
[operator receipt](agent-runtime-platform-phase-b-run-2026-11-06T1958-operator.json)
records 853 log polls, the exact active Job/Pod binding, `KeyboardInterrupt` and
an empty deletion list. Root stops the operator after its safety window; no late
gateway deletion is credited to the run.

The [post-run diagnostic](agent-runtime-platform-phase-b-run-2026-11-06T1958-log-deserialization.json)
reproduces a Kubernetes 34.1 client conversion: the default
`read_namespaced_pod_log` string response deserializer first parses a single JSON
line, then returns Python dictionary text with single quotes. The helper's
`json.loads` rejects that representation. Raw kubectl log bytes contain the valid
JSON event. Use `_preload_content=False` and decode the actual raw response, with
a real HTTP/client regression; this is not buffering. The same mechanism may
explain run 24, but that link remains an inference until its old helper path is
checked. Keep both failures and all spent ledgers; T13 remains open.

### Run 31: T27 has no capture and a missing-receipt evaluator error

The [byte-for-byte report](agent-runtime-platform-phase-b-run-2026-11-06T2004.json)
runs from **20:04:37 to 20:09:20 UTC** and remains `error` on T27 with
`AttributeError`. Its `capture_start` and `capture_complete` are explicitly null.
The operator capture never started within the exact 240-second gate, and no raw
pcap exists. The evaluator then called `.get` on the null completion receipt,
adding a reporting error to the missing evidence. Neither exact T4 nor T27 passes
in this attempt: the T4 session outcome is FAILED, has no committed snapshot and
no token-issued receipt. The transport session completes and its positive TLS
control returns verified HTTPS 404; the foreign-CA control records one trusted
positive request and zero negative application requests with verify_code 20.
Both sessions have `cleanup_confirmed: true`; fixture and worker stability are
true. The [component receipt](agent-runtime-platform-phase-b-run-2026-11-06T2004-components.json)
retains the unchanged ce7c06b runner image. The
[final control receipt](agent-runtime-platform-phase-b-run-2026-11-06T2004-control.json)
has configuration only, with no capture-start or completion receipt.

The plaintext probe reports `unexpected_http`, but the old classifier assigned
that label to every nonempty unknown response. It retained no raw response, so
that label does not establish HTTP on the wire. A separate credential-free
[host diagnostic](agent-runtime-platform-phase-b-run-2026-11-06T2004-host-diagnostic.json)
observed exactly seven bytes, `15030300020232`: a TLS alert record, legacy version
0x0303, length two, fatal level two, decode_error(50), as defined by
[RFC 5246 sections 6.2.1 and 7.2](https://www.rfc-editor.org/rfc/rfc5246).
This host observation does not retrospectively prove what the Pod received and
is not a packet capture of the run. The pinned gateway v1.7.0 source
[locks rustls 0.23.46](https://github.com/agentgateway/agentgateway/blob/26f5aebe99a36a037fe54f8080a608aca5547e15/Cargo.lock);
its [parser](https://github.com/rustls/rustls/blob/v/0.23.46/rustls/src/conn.rs)
emits fatal decode_error for invalid messages and its
[message builder](https://github.com/rustls/rustls/blob/v/0.23.46/rustls/src/msgs/message/mod.rs)
uses TLSv1_2 record framing for alerts.

Prepared source corrections are [zetra PR65](https://github.com/X-McKay/zetra/pull/65)
(null completion fails capture checks instead of raising) and
[zetra-agents PR29](https://github.com/X-McKay/zetra-agents/pull/29)
(strict complete fatal-alert classification and bounded full-stream reads).
Unknown, partial, warning, wrong-version, unknown-code and trailing bytes remain
failed evidence; arbitrary bytes cannot become an HTTP result or pass. Local
regressions pass (35 runner control/evidence/runtime and 30 fixture tests), which
qualifies only those source paths. A fresh signed transport fixture and updated
runner still need publication, installed-image verification and a new exact-T4
capture before T27 can qualify.

The local coordinator's separate post-report AttributeError needs a dictionary
type guard before parsing JSON log values. It does not replace the harness
regression. Temporary qualification resources were cleaned up and no sandbox or
qualification Job remains active per the session handoff. No host capture or sudo
bypass occurred. Host work remains deferred: coordinate operator readiness and
write a terminal-ready marker only after successful `sudo -v`, then launch the
unchanged 240-second gate with the reviewed bounded capture. The old run31 capture
script is expired; no late receipt is credited to this run.

### Run 32: daily budget persists through both gateway replacements

The harness ran from **20:46:16 to 20:50:46 UTC**. Kubani#372 staged retry2
unapproved; #375 separately approved it after the live controller verified its
signature, all five required attestations, and PolicyDrift=False with reason
NoDrift. The [Ready release](agent-runtime-platform-phase-b-run-2026-11-06T2046-release.json),
[component inventory](agent-runtime-platform-phase-b-run-2026-11-06T2046-components.json),
[launch receipt](agent-runtime-platform-phase-b-run-2026-11-06T2046-launch.json),
[exact Pod deletion receipt](agent-runtime-platform-phase-b-run-2026-11-06T2046-operator.json)
and [summary](agent-runtime-platform-phase-b-run-2026-11-06T2046-summary.json)
accompany the unchanged raw report (SHA-256
`dc968cd59da5227f4fb166c80ea430322e744bf738d340aee28e84a381aecaee`).

The new identity starts at a trusted zero ledger. Eighteen successful requests
consume exactly 1800 tokens; the enforced 300-token reservation causes the next
request to receive budget refusal under its 2000-token daily limit. Both exact
gateway Pods are replaced inside the active test window. The post-replacement
request is still refused, and the ledger is never refunded. All **23 checks**
pass and the tenant is empty after cleanup. Earlier identities and failed
reports remain unchanged; no ledger was reset.

### Run 33: missing initial initialize capture keeps T23 unqualified

The harness ran from **20:52:13 to 20:53:08 UTC**. Production runner,
reconciler, temporary worker and harness all used the same installed digest
`sha256:554a6d6727080390433f4a267a23b449976d844159a968048cc2058d2b025815`.
The MCP capture used
`sha256:be4e8e6a9c3041f3474ee17386c6e9c07639ba884616b1c75979184bc2c55bad`.
The [fresh control configuration](agent-runtime-platform-phase-b-run-2026-11-06T2052-control.json)
binds seven fresh session IDs and the [Ready fixture](agent-runtime-platform-phase-b-run-2026-11-06T2052-release.json).
Only the initial control runs: three boundaries complete and cleanup succeeds,
but `complete_transport_correlation` is false. Three non-initialize request
decisions each have the exact expected three backend records. The initial
initialize decision `7bbcc8c4-9e8c-45bf-a351-4ed72beb4047` appears in APS and
gateway evidence but has no capture row, including the independent
[post-run capture read](agent-runtime-platform-phase-b-run-2026-11-06T2052-capture.json).
The report is retained unchanged; no fault case or second control ran. Both
temporary Jobs, control ConfigMap and temporary Role/RoleBindings were removed,
with no tenant Pods remaining. The cause remains under investigation.

## Status of spec items touched in these runs

| Item | Status |
|---|---|
| Keycloak issues a token to an agent (T4) | **Proven** 13:03:35, after the attribute fix; **T4 passed** 14:05 |
| TokenReview returns pod name and UID for the projected token (17.3) | Proven implicitly: the APS resolved `pod` and `namespace` for the issued token |
| IdP accepts the projected token as a client assertion with the exact client settings (17.3, 7.8) | Proven with `jwt.credential.issuer` / `jwt.credential.sub`; the spec 7.3 keys fail |
| Session runs through the Session Runner | **Completed** in run 5: seven sessions, three to five boundaries each, snapshots taken; run 6: seven sessions, three boundaries each |
| Sandbox network check end to end (egress guard) | **Passed** in runs 2 and 3 |
| Kyverno PolicyReports | **Written** (resolved 21:04): two admission EphemeralReports per sandbox pod from its first second and a PolicyReport at aggregation, all owned by the pod and gone with it; every earlier listing was taken after the run |
| T4, T5 | **Exact T4 first passes in run 21** with committed claims and matching sole current-Pod/JTI issuance; **exact T5 first passes in run 18** and repeats in run 21. Earlier limited passes and run 18 failures remain unchanged |
| T6/T7 model authentication (R4, 15) | **First pass in run 14**: direct engine 401/200, successful captured chat completions, backend-key equality, no agent JWT, and nonzero gateway/boundary usage |
| T8 forged agent headers (8.8, 15) | **Passed** in runs 7 to 9; since run 9 with the server half: the MCP server received the APS-set values and none of the forged ones |
| T11 agent-mode upstream token (R7, 15) | **Passed** in run 9 (23:52): the server received `sub` = the agent's subject, no `act`, the backend audience |
| T12 agent token never at the MCP server (R4, 15) | **Agent-mode harness pass** in runs 9 and 13: only exchanged `jti`s reached the server. Delegated T10 and the optional 8.11 native-exchange variant are not qualified |
| Capture at the MCP server (15.2, 15.4) | **Live** since 23:48: capture sidecar `bc37532` in the kubernetes-mcp pod; a loopback upstream needs `Host` rewritten (Go MCP SDK rebinding protection) |
| T9a/T9b preflight and release admission (15) | **First pass in run 15**: true generation-zero preflight refusals with no pod creation, plus positive controls and five named Kyverno release denials; dedicated fixture restored |
| T17 APS fail-closed (R11, 15) | **First complete pass in run 28:** all 18 checks, 900 real responses, 63 eligible 403s, exact transition receipts, zero-Pod/endpoint window and restored success. Runs 25–27 remain failed |
| T19 no decision caching (15) | **First full qualification in run 16**: 50 MCP allow/deny cycles in 8,109.933 ms, two model-route cycles, one token, and 104 distinct correlated APS decisions. Earlier five-cycle passes retain their narrower scope |
| T22 admission completeness (15) | **First pass in run 17** with all ten mutations rejected by the exact expected admission layer and valid positive controls. Run 15 remains a historical error |
| T13/T13b budget enforcement (R8, 15) | **T13b first passes in run 23**: exact session limit, concurrency, settlement, independent session and zeroed-state generation-2 restore, scoped to the byte-token backend. **T13 first passes in run 32**, all 23 checks with both gateway replacements. Runs 24 and 30 remain errors; original and first-retry ledgers are preserved |
| T15 active-session revocation (R10, 15) | **First pass in run 22**: Agent enable/disable and cancellation pass in both rounds, with 47.015/7.917 ms stop-to-403 upper bounds, exact restoration and cleanup. Run 19 remains failed |
| T20 drift and release immutability (R6, 15) | **First pass in run 19**: controller-observed drift, both-replica active denial, generation-zero preflight refusal and immutable-image rejection, with exact restoration and cleanup |
| T23 checkpoint crash recovery (10.4, 15) | **Runs 29 and 33 remain failed** on initial healthy-control capture correlation. Run 33 has exact non-initialize fanout but no capture for the first initialize decision. No fault session runs; a new complete report is required |
| T25 protocol robustness (10.4, 10.5, 11.8, 15) | **First pass in run 20**: all five real faults through three generations, six subsequent/control sessions, 191 checks, confirmed checkpoint/delete/fence ordering and bounded memory on the same worker/process |
| T26 token binding (R2, 15) | **First pass in run 13** (16:07 to 16:13): all 13 checks true, including the same-agent 403 `deny.token_bound_elsewhere` and other-agent 403 `deny.pod_agent_mismatch`. Runs 10 to 12 remain failed observations |
| Registry Controller realm scope mapping under FGAP v2 (7.5) | **Verified 2026-11-06 16:57 UTC**: permission evaluation with the service-account user and actual controller client returns PERMIT; controller credentials receive 204 when posting an existing scope role, with unchanged mappings. Historical 403 observations remain recorded. The operator grant script is committed; no wider role was granted |
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
13. **A proxy on loopback in front of a Go-MCP-SDK server must rewrite
    `Host`**: the SDK's DNS-rebinding protection returns 403 for a loopback
    request with a non-localhost Host. The first sidecar build cost 13 minutes
    of 403s on the kubernetes backend (#312 to #314).
14. **Keycloak FGAP v2 needs a separate permission for realm-role client
    scope mappings.** With `adminPermissionsEnabled: true`, the controller's
    `manage-clients`, `manage-users` and `view-realm` roles do not authorize
    `POST /clients/{id}/scope-mappings/realm`. The relevant v2 check is
    `RolePermissionsV2.canMapClientScope`: `manage-realm` or a
    `map-role-client-scope` permission on the role. Agents without a
    pre-defined realm scope mapping failed reconciliation with 403;
    `conformance` already had its mapping in `realm-agents.json`. The
    controller warning only names `IdpError`; the preceding httpx line
    identifies the failed POST. Al applied the narrower client policy
    `registry-controller` and scope permission
    `registry-controller-map-role-client-scope` on resource type Roles,
    scope `map-role-client-scope`. The pickup notes reported continued 403
    responses and investigator `IdpError` at 08:00 UTC, but the subsequent
    live check found investigator `Ready=True`, with transition time
    2026-11-06 07:55:09 UTC. Controller logs from 15:10 to 15:40 UTC show
    GET `/clients/{id}/scope-mappings/realm` returning 200 for all three
    clients, with no POST or 403 observed. The controller skips mappings
    that already exist; current readiness and readable mappings do not
    establish that the grant permits creation.

    **Verified at 16:57 UTC:** the permission evaluator returns PERMIT with
    both the controller service-account user and client UUID. User-only
    evaluation returns DENY because the client policy sees admin-permissions.
    The controller's actual credentials then received 204 when posting the
    already assigned `agent-role-kubernetes-read` mapping on conformance-b;
    the mapping set was identical before/after. Keycloak 26.8.1 checks
    `requireMapClientScope` before its idempotent add, so this exercises the
    missing permission without changing access. The historical 403 cause
    is still unknown; no new or broader permission was created in this
    verification. [Evidence](agent-runtime-platform-keycloak-scope-verification-2026-11-06.json)
    and the operator-run [grant script](../../../infrastructure/scripts/ops/grant-map-role-client-scope.sh)
    are now retained. Script syntax and existing-object skip logic were checked;
    its creation branch was applied by Al earlier, not re-executed here.
15. **Release builds can OOM dind during flaky egress.** Four Kata
    `TaskOOM` events on dind (02:00, 02:04, 02:08 and 02:11 UTC on
    2026-11-06) ended the first four builds of `conformance/v0.1.6` and
    `conformance-b/v0.1.0` with buildkit's `cannot allocate memory` at the
    12 GiB limit. A sampled rerun grew from 1 to 8 GiB in 30 seconds while
    Docker's build cache stayed at 290 MB. Failing builds had apt retries
    and 18 to 105 kB/s fetches, with bursty pod egress failures and CoreDNS
    upstream UDP timeouts in the same window; quiet-network builds passed
    around 1.4 GiB. The memory-growing process and causal link remain
    unproven without guest kernel evidence. Run release tags one at a time,
    rerunning the next after the previous job finishes and egress recovers.
16. **The tenant runner image must track harness input changes.** The
    harness Job, tenant runner Deployment and cleanup reconciler pin the
    same image separately. Run 10 used a `3794070` harness with a `158a170`
    runner; Temporal dropped the unknown `seed` field without an error.
    Bump all three together for changes to `SessionInput` or activities;
    a harness-only bump is appropriate only when the intervening changes
    are confined to `conformance.py`. #320 aligned the pins; all three are
    `e05c9ca` after #323, with the installed-package correction in finding 18.
17. **A new session's seed must exclude the donor's runtime state.** Run
    11 restored donor `state.json` with `next=3` into a session starting at
    boundary 0. zetra#39 restores only `workspace/` for a seed; full
    `state/` restoration belongs to recovery of the same session. Run 12
    still failed exit 5 on every generation of both seeded sessions after
    that source fix because of the separate packaging defect in finding 18.
    Run 13 exercises the corrected installed package and passes both T26
    rejection paths; the workspace-only boundary remains required.
18. **Copied source does not update an already installed runner wheel.**
    Image `12369f4` contained the fix under `/app/runner`, while the worker
    imported an older package from `/app/.venv/lib/python3.12/site-packages`.
    The source-copy diagnostic completed boundary 0; the installed-package
    diagnostic restored donor state and failed with `boundary mismatch`.
    zetra#40 reinstalls the package after the source copy and verifies the
    imported implementation. kubani#323 pins harness, tenant runner and
    cleanup reconciler to `e05c9ca` at the same digest. Run 13 then passed
    all 13 T26 checks. This is distinct from finding 17's restore-scope bug:
    the source fix was correct, but run 12 never executed it.
19. **Admission evidence must identify the rejecting layer without masking
    a malformed fixture.** Run 15's T22 hostPath and hostNetwork requests
    were correctly rejected by PSA Restricted before Kyverno, whereas its
    extra container accidentally violated the baseline security context.
    zetra#45 copies the valid container for the extra-container test and
    accepts only the exact expected HTTP 403 Restricted-profile violation
    for the two host cases, alongside the existing named Kyverno path.
    T9b still requires the named Kyverno rule; generic RBAC or unrelated
    PSA denials never pass. All mutations remain server-side dry-runs, and
    no admission policy is weakened. Run 15 remains a historical error;
    run 17 supplies the new passing T22 report from the corrected harness.

20. **A relative log window must preserve its original cutoff across replicas.**
    In run 18, T4's exact claims are present but its matching issuance is absent
    from the report. A retained post-run read finds that exact issuance at
    17:34:12.887866593 UTC. Reproduced reader tests show that a slow first Pod read
    advances the effective cutoff for later Pods when `since_seconds` is reused.
    The correction freezes a monotonic cutoff, recomputes each relative window
    and bounds API reads; T4 retries only for the exact namespace, Pod and JTI.
    This repairs evidence collection, not the token check. Run 18 remains failed;
    run 21 supplies the new exact T4 pass with matching sole issuance.
21. **T15 must measure the specified stop event and respect timestamp precision.**
    Run 19's first stop/decision pair straddles nanosecond versus millisecond
    logging precision; its negative point difference cannot establish ordering.
    Anchor to the first actual stop and poll for a later ordered same-replica
    pair; a repeated idempotent stop must not reset the one-second clock. Keep the actual stop-to-403 one-second check and both replicas'
    real HTTP 403 evidence; cancellation-request latency is separately reported.
    Run 19 remains a historical failure. Run 22 passes both rounds with
    47.015/7.917 ms conservative stop-to-403 upper bounds and confirmed restoration.

22. **Operator coordination must reach the active fault window.** Run 24's
    exact-UID gateway replacement began after its TimeoutError report ended.
    Keep the failure, late receipt and spent ledger; do not reset the ledger or
    credit a later replacement as the in-window post-restart request. Diagnose
    event-delivery latency before a fresh, properly bounded T13 attempt.

23. **Outage evidence must include every operator transition and the active Job.**
    Run 25's failed scale patch and run 26's completed-Job launch race never create
    an outage; successful baseline traffic cannot qualify fail-closed behavior.
    Run 27 creates the outage and passes the traffic checks, but Flux pause/resume
    annotations also advance Deployment generation and are missing from its
    receipt schema. Bind a new Job UID/marker, record exact pause/down/up/resume
    transitions, retain all identity/configuration guards, and require a new
    passing report. Run 28 supplies that complete pass with all 18 checks; runs 25–27 remain historical failures.

24. **Correlate pinned MCP transport expansion without treating handshakes as tools.**
    Run 29's initial healthy control has one APS/gateway decision per request but
    ten backend rows for four decisions. The stateless gateway initializes before
    each non-initialize request. Require fixed-method classification and the exact
    bounded sequence/status/identity for every decision; never accept an arbitrary
    duplicate count. No fault cases ran, and the failed report remains unchanged.

25. **Read Kubernetes log bytes before parsing JSON events.** Run 30 proves that
    the client's default string deserialization turns one-line JSON into Python
    dictionary text, which the operator rejects. Read the raw response with
    `_preload_content=False`; retain active-UID/deadline checks and test the actual
    HTTP client. No replacement occurred, no ledger is reset, and T13 remains open.

Run 32 supersedes the open T13 status in findings 22 and 25; their historical
failures and operator receipts remain unchanged.
