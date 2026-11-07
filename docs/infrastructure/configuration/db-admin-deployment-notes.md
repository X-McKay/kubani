# DB Admin deployment observations

Platform qualifications remain paused; this record covers adding the DB Admin agent.

| Observation | Consequence | Follow-up for discussion |
| --- | --- | --- |
| Agent README still says the platform has not run on the cluster. | New authors cannot trust the starting instructions. | Maintain one current deployment status/onboarding guide. |
| Agent source, manifest, Agent permissions and applied copy live in multiple files/repositories. | Adding a tool requires synchronized edits and release checks. | Scaffold from a single declarative agent definition and validate generated copies. |
| New MCP backend requires route, backend, JWT targets, external authorization, tool policy, network policy and IdP configuration. | Omitting one produces a late runtime failure. | Declarative backend registration with completeness validation. |
| Fresh isolated checkout emits mise trust warnings on login-shell startup. | Noisy setup even for read-only commands. | Document checkout setup; use non-login shells for explicit tools. |

| Restricted MCP parsing differs by SQL syntax: scalar custom calls are filtered, while a custom function in FROM was accepted by the actual image. | Initial source-only research overstated the restriction; parser filtering is not the database permission boundary. | Retain tested fixed view queries and database ACLs. Consider a typed monitoring MCP adapter instead of a generic SQL tool. |
| MCP 0.3.0 SQL results are Python representations, not structured JSON. | Agent needs a bounded parser and explicit JSON payload projection. | Prefer structuredContent/JSON in a future server version or adapter. |
| Controller registers agent scopes, but does not attach new backend scopes to APS. | A Ready agent can still fail token exchange at its first MCP call. | Include requester audience/scope setup in backend registration and preflight. |
| Normal submission CLI returns a workflow ID but does not wait for completion or retrieve the report. | An operator must bind the run, check cleanup and fetch the workspace artifact separately. | Add a bounded `run --wait` / report command using the existing runtime API. |
| New agent names require edits to two signer allowlists. | A correct signed image can be rejected if the declarations disagree. | Generate both pins from a single reviewed tenant declaration. |
| Controller can assign existing backend realm roles but lacks permission to create a new realm role. | New backends need a narrow administrator bootstrap step before agent reconciliation. | Declare backend roles in the same registration workflow; retain the controller's limited authority. |
| Keycloak realm import is a hashed ConfigMap, but changes do not update an existing realm. | Editing the seed would restart the IdP without applying the backend setup. | Keep this backend delta in `apps/keycloak/db-admin-backend.json` (not mounted); run the verified helper after realm bootstrap. A reconciled backend resource would remove this manual step. |
| Gateway permissions currently constrain identity, backend and tool name, not exact SQL arguments. | The signed agent exposes only fixed diagnostic queries; database ACLs and restricted transactions remain essential enforcement layers. | Consider typed server tools or a separately tested argument policy before exposing model-supplied queries. |
| Initial 100k session budget was below the main backend’s 131,072-token reservation. | It would reject the first model request despite valid source tests; caught before release. | Use the existing 200k session budget and check applied Agent budgets against the APS catalogue before deployment. |
| `gh pr edit` failed on the deprecated classic Projects GraphQL field. | PR body update required a REST API fallback through `gh api`. | Update the CLI or standardize the supported API path. |
| Secret scanning flagged four public release hashes as high entropy. | Exact published assets could not be committed until the known public digests were reviewed. | Added only those four verified non-secret baseline entries; retain scanner settings and existing entries. Consider typed release-hash recognition. |

| First operator session helper omitted required `grant_handle=None` for agent identity mode. | A local client TypeError occurred before submission; an exact workflow lookup confirmed NOT_FOUND before retry. | Make the normal agent-mode submission command construct this field and provide bounded wait/report retrieval. Preserve the failed invocation receipt. |

| First live agent skipped blocking, then asserted no blocking in prose while its coverage section correctly flagged the missing observation. | Runtime completion is not task correctness; artifact verification failed despite clean sandbox cleanup. | Require all four diagnostic attempts before report writing; generate findings, limitations and conditional follow-ups from the latest validated evidence instead of accepting model prose. Preserve the failed report and verify the correction with a new signed release. |

No credentials, raw tokens, private database contents or session output belong in this document.

## Validation before deployment

- Kubani local validation passed all GitOps builds and 70 infrastructure tests. Dedicated gateway/identity/backend manifest checks passed; real PostgreSQL checks run separately in an explicitly owned local container.
- Isolated PostgreSQL 18 checks covered bootstrap reruns, application-row/write denial, role/ACL collisions, redaction of a known other session, actual lock blocking, and bounded database coverage. The four queries also ran through the pinned restricted MCP image.
- Independent review cleared the backend and gateway wiring. Source-agent review found inconsistent row totals could be accepted; the correction and 37 focused regression tests passed before release.
- Backend PR #388 merged; its exact Keycloak helper applied successfully and read-only verification showed no remaining operations. Flux/backend readiness and the signed agent release are tracked below.

## Release staging

Source PR zetra-agents#30 merged as `3d8ff011bc97984767f497049250212c4b1e9d39`. Tag `db-admin/v0.1.0` completed release run `42324691829`, including scanning, signing and all five attestations. Release `db-admin-2026-11-07-42aab28f` is staged unapproved from the exact published assets. Checksums and the independently recompiled Agent/Release/policy/predicate agree. The published image also passed an offline, nonprivileged verification: all three agent files, all nine SDK modules, manifest and tools match pinned source. The controller independently verified the exact staged spec, signature, all five attestations and NoDrift while approval was false. Separate approval PR #390 then merged; the same release UID became Ready with unchanged image, policy and signer evidence. The first normal live session completed and cleaned up its sandbox, but failed report qualification: only three diagnostics were attempted and its narrative asserted no blocking without blocking evidence. The strict artifact check rejected it; the failed report and receipts are preserved privately. A source correction and a new signed release are required before declaring the agent usable.

## Highest-value follow-ups

1. Declare each MCP backend once and validate gateway, identity, requester scopes and network wiring together, retaining the explicit administrator bootstrap boundary.
2. Run cross-repository preflight before tagging: budget/reservation compatibility, both signer allowlists, and source/applied capability agreement.
3. Add a bounded normal `run --wait --report` command with exact run binding, cleanup verification and report retrieval.

The first live failure also motivates a design discussion: fixed monitoring checks and evidence-derived reporting may fit a deterministic workflow. The current fix retains the agent interface while making its saved report deterministic; no broader platform redesign is included.

## Corrective release

Source PR zetra-agents#31 merged as `cf08c2ba24652263b6313a2010a51dd500719cba`. The v0.1.1 report tool takes no arguments, requires all four diagnostic attempts, and generates facts, limitations and conditional follow-ups from the latest validated evidence. A latest error, stale record or invalid observation never falls back to older success. The fix passed 44 focused regression tests, independent review and all source CI checks. Database permissions, gateway policy, fixed queries and SDK pin are unchanged.

Tag `db-admin/v0.1.1` completed release run `42326773446`. Release `db-admin-2026-11-07-3e94dc5e` is staged unapproved from exact published artifacts; independent compilation and installed-image verification passed, including all zero-argument tool signatures. Controller verification, separate approval and the corrected live report remain pending.
