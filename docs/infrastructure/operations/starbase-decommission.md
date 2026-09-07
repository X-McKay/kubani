# Starbase decommission tracker

Date: 2026-09-05. Owner and authorizing operator: Al McKay.
Status: scoped repository removal prepared, not deployed. Lite remains excluded.

## Scoped progress after approval on 2026-09-06

Al approved smaller, separately reviewed changes after the combined operation
was blocked. In the isolated branch, the newer-Starbase overlays, bundle,
promotion scripts, observer files and corresponding activation tests have now
been removed. CI references have been updated to retain shared-service tests
and the replacement decommission boundary tests.

The two existing Flux controller identities remain to prune their old inventory.
Foundation's new target contains only the protected namespace, registry Secret,
ResourceQuota, LimitRange, default-deny policy and DNS policy in starbase-system.
Dojo's new target is empty. The encrypted registry Secret is copied intact.
Lite's sensor ServiceAccount and cluster RBAC are not owned by either retiring
controller and must remain untouched. No namespace-wide Starbase-system deletion
is permitted. Historical namespace labels are preserved rather than silently
changing Lite's security or resource constraints.

No live deletion, merge, or data erasure has occurred. Shared Authentik blueprint,
Temporal network policy, service probes and database configuration have not been
changed in this scoped removal. Their newer-Starbase references require separate
review. Backup versus permanent erasure remains an explicit unresolved choice.

The exact-support test found a test-authoring error: existing SOPS credentials
use encrypted stringData, which the test incorrectly rejects. Correction was
requested; do not treat this branch as passing or merge-ready until corrected
and all checks and independent review pass.

## Starbase-lite preservation boundary

Al explicitly excluded Starbase-lite from decommissioning on 2026-09-06.
This overrides the earlier inventory's proposed deletion of its namespace.
The Lite deployment definitions in X-McKay/Starbase-lite identify these
protected dependencies, even though they do not all contain "lite" in the name:

- Kubernetes namespace `starbase-system` and its namespace-level controls.
- Registry pull resource `starbase-system/starbase-ghcr-pull`; never revoke its underlying
  registry credential as part of newer-Starbase credential cleanup.
- ServiceAccount `starbase-system/starbase-sensor`.
- ClusterRole and ClusterRoleBinding `starbase-sensor-read`.
- Temporal namespace `starbase-lite`, including its seven completed histories,
  search attributes, schedules, task queues and archival state.
- All Lite manifests, repositories, worktrees, images, credentials, data and
  evidence, including `starbase-lite-evidence` and `station.almckay.io`.
- Shared Temporal, PostgreSQL, FalkorDB, model serving and cluster infrastructure.

Do not delete `starbase-system` or select deletion targets by a `starbase*`
prefix. Preserve ambiguous ownership until it is resolved. The earlier
classification of `starbase-sensor-read` as a deletion candidate was incorrect.
No deletion had been performed when this correction was recorded.

The combined repository-removal operation was rejected by safety review because
it included shared CI, Authentik, network policy, probes and database-policy
edits. It was not executed. Further removal requires a bounded reviewed change;
the current branch must not be merged while its tests and manifests disagree.

## Decision and scope

Stop Starbase implementation and remove its Kubani functionality and owned
runtime state. Preserve unrelated services, the Starbase source repository,
historical evidence, and enough configuration history to recommission later.
This supersedes the autonomous activation objective. Recommissioning is a new
reviewed deployment, not automatic rollback or a promise to recover deleted data.

The first PR only stops workloads. Later removal must use explicit reviewed
resource and data allowlists. Do not delete shared databases, Temporal's default
namespace, shared users, shared credentials, backup volumes, or shared graphs.

## Preserved source

- Dirty Kubani network policy saved and pushed on branch
  `codex/preserve-pre-decommission-worktree`, commit `5334d78`.
- The preserved branch is not deployed. Local main was 71 commits behind remote
  main, so the decommission branch starts at remote revision
  `1d816581416368c0aec92c78ebbf4d81e7c631d3` instead.
- Last healthy autonomous foundation revision recorded in the prior handoff:
  `703cfb14528e61c18d5c7ff56b161eff459cf3e8` (historical, not a safe disabled rollback).
- Starbase RC14 source: `61ad6ccf06418bc9cee5c48f45823fe3131baa7b`.
- Keep immutable release artifacts and historical evidence for recommissioning;
  credentials must be reissued rather than copied into this document.

## Verified inventory

Read-only observations on 2026-09-05, Kubani context `default`:

| Surface | Owned targets | Status / next action |
| --- | --- | --- |
| Flux | `starbase-foundation`, `starbase-dojo` | Foundation not Ready; Dojo Ready. Shutdown PR pending. |
| Namespaces | `starbase-system`, `starbase-connectors`, `starbase-execution` | Retain until data inventory and shutdown are complete. |
| Workloads | core, GitHub connector, Kubernetes connector, preview fixture, Dojo runtime, Dojo workflow worker | Six deployments; scale all to zero first. |
| PostgreSQL | `starbase_core`, `starbase_gateway`, `starbase_dojo` | Catalog confirms dedicated databases. Inventory tables and recovery before deletion. |
| PostgreSQL roles | runtime and migrator roles for each of the three databases | Six roles; check dependencies before dropping. |
| Temporal shared | `default`: nine visible `starbase.bounty.workflow.v1` executions, all completed or failed | Delete only identified Starbase execution IDs through Temporal APIs. Never delete `default`. |
| Temporal Lite | `starbase-lite`: seven completed executions | PROTECTED. Four AgentRunWorkflow and three MissionWorkflow histories; do not delete. |
| Authentik | application slug `starbase`, provider ID `19` / client `starbase-kubani`, group `starbase-operators` | Remove bindings, tokens and dedicated scope mapping; preserve users and other applications. |
| FalkorDB | No clearly Starbase-owned graph in GRAPH.LIST | Do not delete ambiguous `__probe__` or other applications' graphs. |
| Shared namespaces | database bootstrap Jobs, ConfigMaps, Secrets, ServiceAccounts and NetworkPolicies; Temporal ingress policy | Owned by Starbase Flux inventories; prune in later removal. |
| Cluster RBAC | `starbase-sensor-read` ClusterRole and ClusterRoleBinding | PROTECTED: owned by Starbase-lite; preserve alongside its sensor ServiceAccount. |
| Edge | `starbase` Ingress; `starbase-tls` and `starbase-dojo-tls` certificates | Remove after shutdown; verify DNS ownership and record removal. |
| Repository | phase4a through phase10 overlays, bundle, promotion/heartbeat scripts, policy tests, CI/justfile entries | Remove active functionality in subsequent PR; retain useful historical evidence. |

## Remaining discovery

- PostgreSQL table inventories, active connections, restore copies, and backup
  contents/retention. Shared backup infrastructure is not Starbase-owned.
- Starbase tables outside the three dedicated databases, including older PoC
  state; identify by migrations and ownership, not name substrings alone.
- Temporal schedules, task queues, archives and older workflow IDs in all
  relevant namespaces; pagination and retention can limit visible histories.
- Authentik blueprint reconciliation, dedicated group scope mapping, application
  bindings, OAuth grants/tokens, and workload identities.
- Redis keyspaces, Qdrant collections, object storage, PVC/PV snapshots, and
  external credentials/webhooks/GitHub App installation ownership.
- Osprey `starbase-preview-heartbeat` timer/service and its deployed script.
- DNS records for `starbase.almckay.io` and `starbase.kubani.dev`; the earlier
  handoff reported the latter NXDOMAIN, not reverified here.
- Outstanding PRs, scheduled automations and any controller capable of
  recreating removed resources. Do not remove unrelated repository work.

## Ordered progress checklist

- [x] Preserve and push the dirty Kubani worktree change.
- [x] Establish isolated branch from current remote main.
- [x] Capture initial repository, cluster and service ownership inventory.
- [ ] Review and merge shutdown PR with exact-head CI and inline review checked.
- [ ] Observe natural Flux reconciliation; confirm six deployments at zero,
  no Starbase pods or running workflows, and healthy shared services.
- [ ] Finish exact state/credential/backup inventory and recovery disposition.
- [ ] Remove Authentik recreation sources and dedicated provider objects.
- [ ] Prune newer-Starbase Dojo and foundation resources through reviewed GitOps;
  retain `starbase-system`, Lite support, and all Lite-owned resources.
- [ ] Remove all active Starbase functionality from Kubani, including scripts,
  tests, CI wiring, observers, shared policy exceptions and active docs.
- [ ] Delete only newer-Starbase PostgreSQL state/roles and its identified
  workflows in `default`; never delete `default` or `starbase-lite` namespaces.
- [ ] Remove dedicated caches, indexes, storage, credentials, DNS and observers.
- [ ] Document retained shared backups, expiry and post-restore deletion rules;
  never erase unrelated backup data to achieve a superficial zero-reference scan.
- [ ] Verify final desired/live absence and shared service health; record results.

## Shutdown behavior and recovery

The temporary decommission overlays select the disabled RC14 reader foundation
and existing Dojo configuration, with all six deployment replicas set to zero.
They retain existing data, namespaces, credentials, migrations and health gates.
The invalid immutable synthetic fixture v2 and autonomous network paths are no
longer desired and can be pruned without rewriting the immutable ConfigMap.
No imperative apply, forced reconciliation, database deletion, or namespace
deletion is included in this stage.

Before data deletion, require a verified recovery path or explicit recorded
acceptance of permanent data loss. A Git branch is not a database backup.
Once data is erased, reverting manifests alone cannot restore Starbase.

For recommissioning, retrieve the preserved configuration and immutable source,
review current platform compatibility, reissue dedicated credentials, create
owned databases and namespaces, apply migrations through owning services,
start in reader mode with automation/mutation/external authority disabled, and
revalidate authenticated UI and all workflow routes before enabling dispatch.
Do not reuse the historical active revision as an automatic rollback target.

## Evidence limitations

Inventory is not completion. No resources or data were deleted at the time this
tracker was created. The initial database query used the non-admin password
variable and failed authentication; the subsequent catalog query used the
existing admin variable successfully, without exposing either value.
