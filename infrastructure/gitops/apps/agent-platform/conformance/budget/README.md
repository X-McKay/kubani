# Bounded budget qualification (T13 / T13b)

This path qualifies gateway/APS/Redis reservation, settlement, concurrency and
recovery behavior using a deterministic byte-token model. It does not qualify
Qwen token accounting, Redis crash durability, or a real engine's tokenizer.
The production catalogue stays main=131072 and fast=32768. The added
`llm-budget-conformance` reservation is 300 because its backend enforces input
<=200 UTF-8 bytes (including each message role), output <=100 bytes, and one
completion. Normal fixture calls consume a computed 50 input +50 output =100.
Unknown fields, larger inputs, streaming and alternative candidate generation
are rejected independently by the backend. The gateway also requires the exact
model and fixture identity, bounded JSON body/output, and exact chat endpoint.

The backend image is the AMD64 build of ZetRA `e79bb04`, pinned by digest, on
rig0's platform role. It includes the exact retry identity allowlist.
Live inventory identifies rig0 as amd64; the arm64 node sparky has no platform role. It has no service-account token or API/Redis permission.
Only the agents gateway can reach it. A fresh static credential is SOPS-encrypted
in the backend and gateway namespaces; the harness and sandboxes do not mount it.
The backend logs only safe request identity, status and computed usage fields.
No body, bearer, credential hash or raw stderr is report evidence.

The original day, session and explicit day-retry `v0.1.0` releases under
`apps/agents/tenant-test/` are exact assets with checked SHA256SUMS. The retry
release remains **unapproved**; existing approvals are unchanged. Both signer
declarations contain only exact release-workflow/tag identities. Approve each
release separately after signature, all five attestations and NoDrift verification. Day has exactly
2000 daily tokens; session has exactly 1000 session tokens. These are separate
identities so daily exhaustion cannot spoil the session test.

The observation endpoint is enabled only for
`system:serviceaccount:agent-platform:conformance-harness`, using TokenReview
with audience `agent-policy-service`, and these three exact budget fixture names in
`tenant-test`. It checks stored session ownership and exposes numeric budget
state; it has no reset, status mutation, arbitrary ledger key or Redis-credential
interface. Reads use the ordinary expiry sweep and therefore may charge an
expired reservation as fully spent. The Redis late-settlement regression ensures
settlement at or after expiry cannot refund that charge before a prior sweep.

The harness's existing namespace-local Pod/log reads cover APS, backend and
gateway observations. New tenant Roles only read each exact Agent/release and
list Pods for cleanup verification. No Pod delete/exec, Secret read, release
approval or status write is added. Existing narrowly scoped harness-to-APS
network access is reused. The Jobs mount the artifact PVC read-only on strix
for hash-verified committed state, plus the normal Temporal certificate, payload
key and projected observer token. The backend key is not mounted.

The worker, cleanup reconciler and all seven manual Jobs pin the published
`ce7c06b` runner image. All seven manual Jobs remain outside Kustomizations;
only the two budget Jobs and the fail-closed Job are suspended. Existing direct
launch behavior for the other four Jobs is unchanged. APS and the bounded backend pin published `e79bb04`
images, so the additional fixed identity is supported when its allowlist is
activated. APS also enables the read-only lifecycle observer for the same exact
harness service account and only `conformance-lifecycle`, including the merged
orphan-grant discovery fix. This does not launch T24 or qualify its genuine-grant
cases; its manual templates and separate operator controls remain inactive.

## Operator sequence

1. Finish any active conformance batch. Pin the reviewed combined APS, runner,
   cleanup reconciler and both manual Jobs to the matching published images.
   Confirm two Ready gateway replicas and no unrelated fixture sessions. Never
   deploy workers or APS in the middle of qualification.
2. Verify and separately approve the selected day-retry and session fixture releases. Confirm exact Agent
   budgets/model, Ready and NoDrift. Confirm the dedicated route and backend are
   Ready. The local rate limit uses 30/minute with burst 10 so ten concurrent
   fixture calls reach APS; no 429 is retried or relabeled to hide throttling.
3. The two `../../workloads/conformance-budget-{day,session}-job.yaml` templates
   are suspended and absent from every Kustomization. Apply only the selected
   Job, then explicitly remove suspension to start it. Run them exclusively,
   one at a time, with the full output retained. Local tests and staging do not
   constitute live conformance passes.
4. For T13, watch stderr for JSON event `T13 awaiting gateway replacement`.
   It contains exactly two old Pod names/UIDs and a 100-second deadline. The
   authorized operator must verify those name/UID pairs still match, then delete
   exactly those two gateway Pods. Do not use a deployment rollout restart,
   which changes the configuration being compared. The read-only harness must
   observe both old UIDs absent and two new Ready replicas with the same image
   and configuration before the fixed 120-second post-denial request. Missing
   replacement, a late replacement, or changed configuration fails the test.
   Use the bounded operator helper with an explicit kubeconfig and fresh private
   receipt path as soon as the new Job exists:

   ```sh
   python infrastructure/scripts/ops/t13_gateway_replace.py \
     --kubeconfig /absolute/path/to/kubeconfig --receipt /tmp/t13-operator.json
   ```

   The helper requires the Kubernetes Python client and a harness image that emits
   `emitted_ns` in the phase event. It pins the Job and owned harness Pod UIDs,
   verifies the exact T13 agent/test selection, and records polling timestamps.
   Before each UID-conditional deletion it rereads the active Job/Pod and exact
   gateway identity, then requires at least 30 seconds of the 100-second window
   remaining. Expired signals, finished Jobs and replaced Pods are refused. These
   separate API objects cannot be checked atomically; the helper records the last
   observed Job/Pod resource versions immediately before each deletion. Partial
   or uncertain deletions remain in the 0600 receipt; there is no automatic replay.
   A successful helper receipt proves only its actions, not the harness result.

5. T13b needs no operator mutation. It proves ten concurrent requests with
   exactly three reservations accepted and seven APS budget denials, each
   settled response within five seconds, independent sessions, exact exhaustion,
   local usage tampering, and normal generation-two checkpoint restoration.
   Timeouts, local gateway throttles, missing or extra decisions/captures,
   unreadable logs, absent trusted ledger samples and cleanup failures fail.
6. Retain the complete report and confirm normal Temporal stop/delete/grant
   cleanup. The day fixture deliberately exhausts its real daily ledger: a
   same-day repeat cannot reset it. The manual daily Job explicitly selects the
   separately signed `conformance-budget-day-retry` identity through both
   `--agent` and `--budget-day-agent`; the fixed original identity and failed
   ledger remain untouched. Arbitrary aliases and automatic new identities are
   rejected. Each identity still needs a genuine zero baseline and exact limits.
   No reset tool is part of the harness. Neither this workflow nor the observer
   restarts Redis.

Run the cross-manifest and signer regressions with:

```sh
RUN_GATEWAY_IMAGE_TESTS=1 uv run python -m unittest discover -s tests -p 'test_budget_*.py' -v
uv run python -m unittest discover -s tests -p test_tenant_signers.py -v
```

The pinned gateway regression uses a loopback stub and tests actual body parsing,
model pins and path rewrites. It isolates those rules from JWT issuance; the
manifest checks verify strict JWT policy attachment and exact fixture identities.
The backend Go suite separately checks its enforced byte tokenizer and limits.

## Exact daily retry identity

The exact `conformance-budget-day-retry/v0.1.0` release assets from build revision
`c4bb1e7` are SHA256SUMS-verified and staged unapproved as
`conformance-budget-day-retry-2026-11-06-5bfba9a0`.
The additional `conformance-budget-day-retry` fixture retains the original
2000-token daily limit and enforced 300-token maximum reservation. Its driver
and validator sources are identical to the original day fixture. It has a
separate signed, initially unapproved release and exact signer, gateway, backend
and observer identity entries. Existing day and session assets remain intact.
The manual Job keeps the name `conformance-budget-day-harness` for the bounded
operator helper; its explicit agent/release flags select only the retry ledger.

The runner records an explicit one-second post-APS-decision response barrier,
then emits integer `emitted_ns`, exact test/agent/session and the unchanged
100-second deadline. Its read-only watcher rejects readiness observed at or
after that deadline, retaining last inventory and elapsed time. Error reports
freeze safe partial ledger/session/decision/restart observations at the failure
phase, including the barrier receipt; later cleanup cannot turn them into a pass.
Full UTC microseconds preserve same-second ordering. The pause is coordination
only: the committed HTTP completion must still precede the actual watch start,
so a slower guest response can fail that unchanged strict comparison. Missing committed requests or
complete logs remain missing evidence. Original run24's timeout and spent 1800
ledger are preserved; these changes do not reclassify that run.

The coordinated activation includes the new runner, APS and bounded-backend
image pins together with the additional allowlist entries. Older APS/backend
binaries reject the additional identity at startup; do not split those changes.
Wait for the matching workloads to become Ready before launching a manual Job. Keep the Job suspended and unlisted, verify all attestations
and NoDrift, then approve separately. Run only after the current exclusive batch
ends; preserve both SOPS credential copies unchanged. No live pass is claimed by
this staging.
