# POC findings (in progress)

## Confirmed developer friction

- The SDK initially admitted only workspace tool effects. Added `remote_read` admission with the same single-attempt durable tool execution, and native OpenShell provider-name attachments. Remote writes remain outside this profile.
- Native provider names/profiles are deployment configuration, not frozen into the agent Release. Workers sharing a queue must use the same configuration; a changed profile requires a new reviewed runtime/queue. This is a caller-managed trust boundary.
- MCP v2 uses `httpx2` and stream pairs; code written against older client examples failed the first fixture evaluation. The corrected official transport passes the fixture evaluator.
- The SDK fixture evaluator requires a fixture model manifest. This application currently evaluates a temporary project copy with fixture settings. A first-class evaluation override would remove this scaffolding, but is not added to the SDK for this POC.
- The stock OpenShell 0.1.4 chart certgen hook lacks pod security settings required by a restricted namespace. Helm post-renderers do not transform hooks. A small asserted patch to the pinned chart sets non-root UID and RuntimeDefault seccomp for the certgen hook; namespace enforcement stays restricted.
- OpenShell's public Python helpers do not cover provider profile import/refresh administration. Operator bootstrap uses the pinned native generated RPCs, not a new SDK credential service.
- Template packaging tests contained an instruction string specific to the document reader; changed the application check to resource presence and agent identity.

## Evidence so far

- SDK full locked gate: 256 passed; 38 live cluster tests deselected (not evidence for live enforcement).
- MCP authentication, initialize, list-tools and namespace read passed using the explicitly approved test identity; 10 tools advertised. No token persisted by that probe.
- Application unit/packaging/recovery-command checks: 18 passed. Official MCP fixture evaluation: passed after correcting the transport stream-pair API.
- Dedicated OpenShell gateway is Ready on rig0 with native mTLS user authentication enabled. Live agent sandbox qualification remains pending.

Live deployment, recovery, isolation probes and latency results will be recorded after execution. This document does not claim those checks have passed.

## Sol review corrections

- Repeated observations now have content-addressed evidence filenames. Regression: changed responses preserve both citations.
- Run commands require an explicit reusable session ID and allow repeated output export. Regression: lost submission acknowledgement and repeated completed-session export reuse the same request/handle; Temporal remains the only authority.
- Worker handles SIGTERM/SIGINT and requests a 20-second graceful drain, within a 60-second pod termination grace. Subprocess signal regressions pass. Hard-loss unknown outcomes are unchanged.
- SDK security and architecture scope text now distinguishes reviewed MCP reads from excluded writes. No additional SDK code defect was identified by the independent review.
- OpenShell's capability-free runtime requires identical sandbox/agent UID/GID. Configured native UID/GID1500 and restricted admission for every POC namespace; no namespace security policy was weakened.
- Initialize Git after scaffolding: otherwise Ruff can traverse an in-project uv cache because Git ignore discovery is unavailable. A cloned template already has a Git repository.

- Separate gateway/sandbox namespaces require staging the public gateway CA into the sandbox namespace: the first runtime control found the native supervisor waiting on `openshell-client-tls`. Only `ca.crt` is copied; user TLS certificates and private keys stay outside the sandbox namespace.
- External registry push failed because Docker had no BasicAuth login. Publishing the built image needs operator-approved registry authentication; no other account is reused.

- The inherited kind qualification workflow needs application-specific infrastructure and MCP credentials. It is omitted from the POC rather than presented as Kubani qualification. Local validation and wheel workflows remain. Worker/run manifests passed server-side dry-run against Kubani under restricted admission.
- Regression latency on the existing dedicated kind setup: fixture sessions 18.480s, 14.148s, 15.981s; vLLM session 20.335s. Each includes provisioning and confirmed deletion; shared worker startup excluded. Four samples are not a Kubani MCP latency benchmark.
- First credential-free native runtime control started and executed, then its direct delete RPC timed out while teardown continued. Kubernetes later confirmed no remaining sandbox, pods or workspace claims. This control did not use the SDK's existing stop-before-delete optimization; the subsequent controls used the SDK's stop-before-delete native sequence and confirmed deletion. The initial failed probe does not establish a deletion timing or enforcement result.

## Kubani native runtime control

The credential-free public Python base-image control passed explicit assertions: UID/GID1500, workspace writes allowed, unlisted reads and normally writable `/var/tmp` writes denied, unapproved internet/MCP connections denied, model-list GET denied403, approved model POST succeeded200. Native deletion and Kubernetes absence of sandbox, pods and workspace claim were confirmed. Latest sample: provisioning6.420s, deletion2.364s. An earlier control without a positive inference check measured9.631s and3.004s. These are controls for native platform behavior, not full SDK-agent, OAuth provider or recovery qualification. See native-runtime-control.json.

The application command also recovers if a local handle receipt was interrupted mid-write: the caller repeats the explicit session ID, the SDK verifies the accepted Temporal start, and replaces the convenience receipt. Local JSON is not a recovery authority.

Remaining gates: registry login/publication, native encrypted MCP provider setup/renewal approval, final image deployment, live agent correctness, worker/sandbox recovery, cancellation and per-session isolation checks. Full POC completion is not claimed.

## Follow-up simplifications to discuss

The application runtime currently supplies worker signal handling, provider-name references, release approval and result export. These are candidates for shared SDK CLI options/helpers after the POC, so future agent repositories do not copy worker glue. Kubernetes resources, credential administration and storage deployment should remain application/platform configuration.

The kind timing baseline used the current branch's host worker with existing immutable sandbox images pinned to SDK61a579c3de43844c7bb0ef13fe32fab000316c07. The new investigator image pins SDKf8e9a5626edb3c2d7ffedcabd0cbcb939a9975dc. Baseline timings do not qualify the new MCP/provider path.
