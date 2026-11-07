# DB Admin deployment observations

Work in progress. Platform qualifications remain paused; this record covers adding the DB Admin agent.

| Observation | Consequence | Follow-up for discussion |
| --- | --- | --- |
| Agent README still says the platform has not run on the cluster. | New authors cannot trust the starting instructions. | Maintain one current deployment status/onboarding guide. |
| Agent source, manifest, Agent permissions and applied copy live in multiple files/repositories. | Adding a tool requires synchronized edits and release checks. | Scaffold from a single declarative agent definition and validate generated copies. |
| New MCP backend requires route, backend, JWT targets, external authorization, tool policy, network policy and IdP configuration. | Omitting one produces a late runtime failure. | Declarative backend registration with completeness validation. |
| Fresh isolated checkout emits mise trust warnings on login-shell startup. | Noisy setup even for read-only commands. | Document checkout setup; use non-login shells for explicit tools. |

No credentials, raw tokens, private database contents or session output belong in this document.
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

## Validation before deployment

- Kubani local validation passed all GitOps builds and 70 infrastructure tests. Dedicated gateway/identity/backend manifest checks passed; real PostgreSQL checks run separately in an explicitly owned local container.
- Isolated PostgreSQL 18 checks covered bootstrap reruns, application-row/write denial, role/ACL collisions, redaction of a known other session, actual lock blocking, and bounded database coverage. The four queries also ran through the pinned restricted MCP image.
- Independent review cleared the backend and gateway wiring. Source-agent review found inconsistent row totals could be accepted; the correction and 37 focused regression tests passed before release.
- Backend PR #388 merged; its exact Keycloak helper applied successfully and read-only verification showed no remaining operations. Flux/backend readiness and the signed agent release are tracked below.

## Release staging

Source PR zetra-agents#30 merged as `3d8ff011bc97984767f497049250212c4b1e9d39`. Tag `db-admin/v0.1.0` completed release run `42324691829`, including scanning, signing and all five attestations. Release `db-admin-2026-11-07-42aab28f` is staged unapproved from the exact published assets. Checksums and the independently recompiled Agent/Release/policy/predicate agree. The published image also passed an offline, nonprivileged verification: all three agent files, all nine SDK modules, manifest and tools match pinned source. Controller verification, separate approval and the normal live session remain required.
