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

The backend image is the AMD64 build of ZetRA `59e959f`, pinned by digest, on
rig0's platform role (backend source unchanged from `655cc39`).
Live inventory identifies rig0 as amd64; the arm64 node sparky has no platform role. It has no service-account token or API/Redis permission.
Only the agents gateway can reach it. A fresh static credential is SOPS-encrypted
in the backend and gateway namespaces; the harness and sandboxes do not mount it.
The backend logs only safe request identity, status and computed usage fields.
No body, bearer, credential hash or raw stderr is report evidence.

The two `v0.1.0` releases under `apps/agents/tenant-test/` are exact release
assets with checked SHA256SUMS, staged **unapproved**. Both signer declarations
add only their exact release-workflow/tag identities. Approve separately after
signature, all five attestations and NoDrift verification. Day has exactly
2000 daily tokens; session has exactly 1000 session tokens. These are separate
identities so daily exhaustion cannot spoil the session test.

The observation endpoint is enabled only for
`system:serviceaccount:agent-platform:conformance-harness`, using TokenReview
with audience `agent-policy-service`, and these two fixture names in
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

The runner and all manual consumers pin the published `d7950de` image, including
the budget harness and cleanup/checkpoint fixes. The APS pin is still awaiting
the combined grant-discovery build; neither Job may be unsuspended until that
matching APS image is committed and healthy. Fixture releases remain unapproved
until verified separately.

## Operator sequence

1. Finish any active conformance batch. Pin the reviewed combined APS, runner,
   cleanup reconciler and both manual Jobs to the matching published images.
   Confirm two Ready gateway replicas and no unrelated fixture sessions. Never
   deploy workers or APS in the middle of qualification.
2. Verify and separately approve both fixture releases. Confirm exact Agent
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
5. T13b needs no operator mutation. It proves ten concurrent requests with
   exactly three reservations accepted and seven APS budget denials, each
   settled response within five seconds, independent sessions, exact exhaustion,
   local usage tampering, and normal generation-two checkpoint restoration.
   Timeouts, local gateway throttles, missing or extra decisions/captures,
   unreadable logs, absent trusted ledger samples and cleanup failures fail.
6. Retain the complete report and confirm normal Temporal stop/delete/grant
   cleanup. The day fixture deliberately exhausts its real daily ledger: a
   same-day repeat cannot silently reset it. Wait for a new UTC day or record an
   explicitly authorized operator reset outside qualification; no reset tool is
   part of the harness. Neither this workflow nor the observer restarts Redis.

Run the cross-manifest and signer regressions with:

```sh
RUN_GATEWAY_IMAGE_TESTS=1 uv run python -m unittest discover -s tests -p 'test_budget_*.py' -v
uv run python -m unittest discover -s tests -p test_tenant_signers.py -v
```

The pinned gateway regression uses a loopback stub and tests actual body parsing,
model pins and path rewrites. It isolates those rules from JWT issuance; the
manifest checks verify strict JWT policy attachment and exact fixture identities.
The backend Go suite separately checks its enforced byte tokenizer and limits.
