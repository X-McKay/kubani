# Kubani investigator POC

The scaffolded investigator runs a complete Google ADK agent and its tools in a
fresh OpenShell sandbox per session. The external Temporal worker owns accepted
progress. The real local vLLM endpoint selects three reviewed Kubernetes MCP read
tools, compares a healthy fixture with a broken pod, and writes `report.md` plus
content-addressed evidence. It correctly identifies missing ConfigMap
`investigator-demo-config` as the cause of `CreateContainerConfigError`.

Deployment inputs stay in this application, outside Zetra. There is no custom
scheduler, token refresher, recovery registry, cleanup controller or second
durability engine. The dedicated namespaces are `zetra-poc`,
`zetra-poc-sandboxes`, and `zetra-poc-fixtures`; all enforce restricted admission.
This is a reviewed internal-agent POC, not hostile-code or production qualification.

## Current shared CLI image results (SDK 12647b3)

The current immutable image is
`registry.almckay.io/zetra/kubani-investigator@sha256:43652fd7b6e26ab390851a4d4f50ed96ddbd7af1edb03e0c4c9a8830a22dc71f`.
Release `zetra-5d36253ffc7afb6f7f2804922ad410dec94209c669ea6a25367ebfe7a3854ba9`
binds the source, lock and SDK implementation `12647b3`. Both worker and clients
invoke the standard SDK CLI; the custom application runtime is removed.

| Scenario | Workflow seconds | Result | Cleanup |
| --- | ---: | --- | --- |
| Normal 1 | 24.865 | SUCCEEDED | DELETED |
| Normal 2 | 24.831 | SUCCEEDED | DELETED |
| Normal 3 | 24.905 | SUCCEEDED | DELETED |
| Graceful worker replacement | 27.901 | SUCCEEDED | DELETED |
| Accepted-checkpoint sandbox replacement | 47.916 | SUCCEEDED | DELETED |
| Native cancellation | 19.803 | CANCELED | DELETED |

All six qualifications passed, including exact release/run checks, report hashes
and links, single-attempt effects, replay, retained accepted receipts and native/
Kubernetes absence. The three normal samples had median 24.865s, provisioning plus
runtime startup 9.319–9.330s and cleanup 2.731–2.943s. The earlier normal median was
24.840s; these small samples do not establish a latency change, p95, or pure SDK
overhead. All normal reports used all three MCP read tools, four evidence files
and 81–101 narrative words.

The deterministic model and tool SIGKILL controls also passed independently:

| Gate | Accepted → candidate cursor | Kill before Activity deadline | Outcome | Proof |
| --- | --- | ---: | --- | --- |
| Model, `investigate-cli-loss-model-01` | 0 → 1 | 43.181s | OUTCOME_UNKNOWN, DELETED | no redispatch, replay, native/Kubernetes absence |
| MCP tool, `investigate-cli-loss-tool-02` | 1 → 2 | 44.755s | OUTCOME_UNKNOWN, DELETED | no redispatch, replay, native/Kubernetes absence |

The uploaded candidates never advanced the accepted cursor. The exact child
processes exited with `-9`; ungated replacements performed cleanup without
executing business effects. This validates completion-loss behavior, not a claim
that an unacknowledged external effect can be safely repeated.

`investigate-cli-loss-tool-01` failed before any model/tool dispatch: its native
supervisor remained unready until the 90-second gate timeout. The startup cause
was not established. Cancellation before accepted provisioning correctly left
SDK cleanup `NOT_CONFIRMED`; observed resource disappearance does not close late
admission or upgrade that proof. The failed attempt remains in qualification.json,
separately from the fresh successful tool test. Neither policy nor cleanup
semantics was weakened.

The complete SDK local gate passed 272 tests; a separate kind run passed all 42
cluster tests. Four additional native cancellation runs passed in Kubani. The
application gate passed 31 tests, official MCP fixture evaluation and wheel checks.
All three kind benchmark tests passed: transport latency (four durable/four native
controls, 18 reconstructions and prepared replay), SDK latency (three fixture,
one vLLM), and ten fresh provisioning trials. SDK latency samples were
15.762/19.744/16.210s for the fixture model and 23.205s for vLLM, excluding shared
worker startup. Existing lab sandbox releases/images retain their prior pins;
these are regression measurements, distinct from the new Kubani image results.

The current-image credential/isolation control also passed: two separate native
sandboxes, authenticated MCP reads before/after rotation in one unchanged warm
process, filesystem/network denials, and DELETED for both instances. Final
inspection found zero native sandboxes, session Kubernetes sandboxes/pods/PVCs
and session PVs. Shared gateway, worker, fixtures and artifact storage remain.
The failed pre-gate attempt retains its separate NOT_CONFIRMED proof status.

The first two image pushes failed with HTTP 499. Registry logs showed the
109,698,276-byte blob upload disconnecting at roughly 60 seconds. A one-shot
[native chunked registry upload](https://distribution.github.io/distribution/spec/api/#chunked-upload)
with 8 MiB chunks, verified HTTPS and digest validation succeeded, followed by
ordinary Docker manifest publication. Approved temporary authentication was
removed. No registry/ingress change or SDK publishing service was added.

## Earlier image qualification (SDK 328937a)

The earlier image pins SDK commit `328937a`; its exact identities remain in
`qualification.json` under `previous_release`. All six agent sessions passed:

| Scenario | Workflow seconds | Result | Cleanup |
| --- | ---: | --- | --- |
| Normal 1 | 24.840 | SUCCEEDED | DELETED |
| Normal 2 | 28.786 | SUCCEEDED | DELETED |
| Normal 3 | 24.794 | SUCCEEDED | DELETED |
| Graceful worker replacement | 30.180 | SUCCEEDED | DELETED |
| Accepted-checkpoint sandbox replacement | 48.893 | SUCCEEDED | DELETED |
| Native cancellation | 19.801 | CANCELED | DELETED |

Normal-session median was 24.840s. Provisioning including runtime startup took
9.309–9.332s; cleanup took 2.742–3.148s. The complete set of runner-advance
Activities took 1.867–2.190s per normal session. Model/tool counts varied 6/5 to 7/6,
so the samples are not identical execution graphs. Their reports were 76–97 words,
with four valid content-addressed evidence files and all three required MCP tools.
These are component observations, not a pure-overhead or p95 estimate.

The final-image native credential/isolation control passed with both instances
DELETED. Final inspection found zero native sandboxes, session Kubernetes
sandboxes/pods/PVCs, and session PV objects. Shared gateway, worker, fixtures and
artifact storage remain deployed so the POC can be used again.

The SDK locked local gate passed 256 tests with 42 cluster cases deselected; four
additional native Temporal cancellation regressions passed. The application gate
passed 25 tests plus official MCP fixture evaluation and wheel/resource checks.
Both SDK CI jobs passed. Earlier failed attempts remain documented below.

## Evidence and limits

Compact immutable image/release identities, attempts and Activity timings are in
[qualification.json](qualification.json). Raw histories and exported fixture
observations remain ignored operator evidence. Successful runs verify exact
report links and evidence hashes, native Temporal replay, one-attempt model/tool
Activities, native deletion and Kubernetes absence of sandbox, workload,
supervisor and workspace claim. Recovery runs compare every previously accepted
receipt and require a different replacement sandbox identity where applicable.

The native credential control uses two separate sandboxes. It verifies isolated
workspaces and PID namespaces, a positive authenticated MCP read, denied
unlisted filesystem access, denied wrong-method/other-backend requests, and
a direct Temporal connection rejected with `PermissionError`. An unchanged warm process succeeds both before
and after native credential rotation with the same opaque environment reference.
This proves the exercised native control; it is not a Temporal business workflow.
Automatic refresh was independently observed from native structured status,
without issuing a Rotate RPC. Credentials stay in OpenShell's encrypted store;
no app password/token was placed in Workflow inputs or sandbox specifications.
The image was published with an approved temporary registry configuration,
which was deleted afterward.

The gateway and artifact PVCs are local-path volumes on rig0. Worker pod/process
replacement is exercised; node/storage loss and gateway HA are not. Shared
workers/gateway startup, cold image pulls, throughput and p95 are not measured.
Model Activity timings include inference and transport; tool timings include MCP
and checkpoint capture. These are end-to-end component timings, not a controlled
measurement of pure SDK overhead. Earlier kind regression samples (different
sandbox release, SDK61a579c) were fixture 18.480/14.148/15.981s and vLLM 20.335s,
including provision/deletion; they do not qualify this MCP path.

## Failures preserved during qualification

- `investigate-live-20261019-01` mechanically succeeded and cleaned up, but the
  model invented shortened evidence filenames and initially omitted report
  content. The report tool now requires content, enforces at most 150 narrative
  words, and appends exact evidence links itself. Regression tests failed before
  this correction and pass afterward.
- `investigate-qualified-normal-01` reached 12 accepted boundaries, then a model
  execution returned `OUTCOME_UNKNOWN`; cleanup was DELETED. That operation was
  not repeated. An independent new inference using the captured request succeeded,
  so that original provider cause remains unrecorded. The dispatcher/wire error lost
  its underlying cause. `investigate-final-normal-01` later had the same unknown
  model boundary with DELETED cleanup. Three independent diagnostic calls using
  that captured request produced one complete response and two responses with
  finish_reason=length and 512 tokens. The profile correctly rejected both
  incomplete responses. The agent instructions now request only `Report ready.`
  after the report is saved, instead of repeating the report in the final answer.
  Limits, provider retries and unknown-outcome handling are unchanged. These
  diagnostics do not establish the missing cause of either original invocation. Finite sanitized executor failure codes are a useful
  follow-up; arbitrary provider exception text must not enter history.
- `investigate-qualified-hardloss-01` and `-02` missed their intended model
  interruption: work completed within the Kubernetes termination grace. The
  harness rejected both qualifications even though their sessions succeeded and
  cleaned up. They are not proof of abrupt in-flight worker-loss behavior. The
  subsequent deterministic control gates an uploaded candidate before Activity
  acceptance and kills the exact worker process; those later observations are
  recorded separately below. Existing SDK kind tests also cover completion loss
  with a controlled transport.
- `investigate-qualified-cancel-01` recorded native cancellation but continued
  scheduling boundaries and succeeded. This exposed a real SDK cancellation race:
  `WAIT_CANCELLATION_COMPLETED` can return a successful Activity after cancellation.
  SDK commit `328937a` checks Temporal's retained cancellation state before more work and
  after cleanup. Four real-Temporal regressions cover successful provision,
  advance, execute and cleanup completion after cancellation, with no later
  business boundary. A native patch marker preserves replay of recorded
  histories. The original observation remains unchanged.
- First chart admission, missing supervisor CA, Temporal policy connection and
  registry authentication failures were deployment failures, not successful live
  agent tests. A first direct native delete timed out while teardown continued;
  subsequent controls used the SDK's existing stop-before-delete sequence and
  confirmed deletion. No failed attempt is counted as a passing qualification.

## Developer friction and ownership

1. Zetra needed only reviewed `remote_read` admission and native provider-name
   attachment. Reads retain single-attempt execution and uncertainty handling;
   remote writes remain excluded. Provider profiles/credentials are deployment
   configuration, not frozen in Release metadata. Workers on a queue must share
   the same reviewed configuration; change the runtime/queue for incompatible
   authorization configuration.
2. MCP 2 uses `httpx2` and a stream pair. Older client examples failed; the official
   transport now passes both fixture and live reads. The fixture evaluator selects
   fixture settings in a temporary source copy. A shared evaluation override could
   remove that scaffolding without expanding agent code.
3. OpenShell 0.1.4's certgen hook needs an asserted nonroot/seccomp chart patch.
   Helm post-renderers do not transform hooks. Separate sandbox namespaces also
   require staging the public gateway CA. The capability-free runtime requires
   sandbox UID/GID 1500 to match the image/process policy. Enforcement was retained.
4. Native provider administration currently uses generated RPCs: workspace profiles
   require `profile_workspace="default"`; refresh-resolvable credentials allow an
   initially empty provider; static `stable_placeholder` mode is incompatible with
   gateway-managed refresh. Configure revokes an authorization epoch, while
   automatic refresh/Rotate preserves warm handles. This is a one-time operator
   concern. The ready-provider setup helper was tested; its complete fresh path
   still needs a disposable-gateway test.
5. Temporal frontend default-deny needed a POC-only native ingress policy. New-pod
   policy propagation briefly refused bootstrap. Bounded Kubernetes Job retries
   reuse the exact session/release; they do not retry model/tool effects.
6. SDK fixture packaging assertions must check this agent's resources rather than
   document-reader-specific instruction text. Initialize Git when scaffolding a
   new project so Ruff's ignore discovery excludes in-project uv caches.
7. The application now invokes the standard SDK CLI directly. The shared CLI
   handles worker signals, provider references, release approval, exact handles,
   verified workspace exports and compact console output. The custom runtime
   module is removed. Kubernetes manifests, storage and credential administration
   remain deployment concerns.

## Before broader use

Use a dedicated agent identity and backend namespace authorization. The approved
`mcp-test-user` has broader reads than the wrappers. AgentGateway advertises only
read tools and Kubernetes MCP uses the `view` role; OpenShell's method/path policy
does not filter JSON-RPC tool names or namespace arguments. The fixed fixture
namespace is a reviewed-code constraint, not independent hostile-code fencing.

Keep the SDK's existing late-admission limitation explicit: native request IDs
deduplicate creates but do not close admission after an unacknowledged create.
Those cases remain `NOT_CONFIRMED`; successful normal cleanup is not proof of a
stronger lifecycle fence or physical data erasure. The POC does not add custom
platform machinery to claim otherwise.

## Shared CLI and deterministic loss control

The POC worker and one-shot clients use `python -m zetra`; the agent repository no
longer maintains a custom worker/client runtime. Export metadata is outside the
verified `workspace/` subtree. The CLI refuses unrelated export directories and
paths overlapping input workspaces or artifact backing. Its static export marker
is local filesystem ownership metadata, never recovery authority.

`evals/inflight_loss.py` mounts test-only code into a dedicated Kubernetes Job.
It uses a separate task queue/runtime per session and an immutable copy of the
selected release. After real OpenShell execution uploads a valid candidate, a
test child gates its return before Temporal accepts completion. The supervisor
verifies the candidate and kills that exact process with SIGKILL before its
Activity deadline. An ungated replacement must observe a native Activity timeout,
retain the accepted cursor, avoid effect redispatch, replay history, and confirm
native/Kubernetes sandbox absence. Model and tool boundaries are tested separately.
No fault-hook API or additional recovery component is added to the SDK.

Sol review added export deletion guards and hardened test release binding, pod
selectors, failure evidence and cleanup budget. A lost submission acknowledgement
is recovered from the native exact run and verified SDK history before cleanup;
the harness never resubmits during this failure path. Unavailable discovery
remains NOT_CONFIRMED. Connection bootstrap retries only establish the test
connection; they do not retry model or tool effects.
