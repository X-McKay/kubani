# Starbase GHCR pull-auth recovery

Date: 2026-08-25

Status: review candidate; no live credential or workload change is authorized by
this document

## Trigger and observed state

The first `starbase-core-migrate-22bfaa3b1e8f` attempt was scheduled on
preferred node `asio`, but GHCR denied the anonymous manifest request with HTTP
401. Kubernetes exhausted the Job's five-minute active deadline without
starting the container. The Job is retained as Failed, the
`starbase-foundation` Flux Kustomization is NotReady, every Starbase Deployment
remains at zero replicas, and unrelated Flux resources continue reconciling.

At the recovery preflight, all four nodes were Ready and pressure-free. `asio`
used 247m CPU / 4,601 MiB memory and `strix` used 376m CPU / 2,515 MiB memory,
leaving ample headroom for the migration's 25m CPU / 32 MiB request. No live
cluster object was changed while preparing this recovery.

## Credential and consumer contract

The operator-created classic GitHub personal access token has only
`read:packages`, expires at `2026-11-23T00:00:00Z`, and is represented only as
SOPS ciphertext in Git. It grants package download; it grants no repository,
workflow, organization, package-write, package-delete, or GitHub API mutation
authority. The token value must not appear in shell history, logs, PR text,
evidence, or decrypted files.

At `2026-08-25T23:28:41Z`, a process-memory-only preflight decrypted one
document, called GitHub's authenticated user endpoint, and received exactly
`X-OAuth-Scopes: read:packages`. A separate authenticated GHCR manifest GET for
`starbase/core-migrator:0.1.0-rc.2` returned HTTP 200, OCI image-index media
type, and the exact rendered digest
`sha256:90f72400491e6ce13c8186a59fdc05bfedd256462cd03d6a5e1ec543de15bd08`.
No credential or manifest body was printed or retained. This proves current
token scope and package-read access from the operator host; it does not prove
SOPS decryption or image pulling from Kubani before reconciliation.

Two namespace-local `kubernetes.io/dockerconfigjson` Secrets share the name
`starbase-ghcr-pull`:

- `starbase-system`, consumed by `starbase-core`; and
- `starbase-connectors`, consumed by the GitHub and Kubernetes connector
  ServiceAccounts.

The binding is on the existing ServiceAccounts, not a namespace default
ServiceAccount, so unrelated workloads cannot inherit it. Automounted
Kubernetes API tokens remain disabled. The connector package credential is not
a GitHub repository/API credential; both connector Deployments remain at zero
replicas in this recovery.

## One-time immutable Job recovery

Adding an image-pull Secret to a ServiceAccount cannot modify the pod template
of the already-created Failed Job. The recovery therefore adds an explicit
`imagePullSecrets` reference to that Job and the resource-scoped
`kustomize.toolkit.fluxcd.io/force: enabled` annotation. Flux may replace only
this content-named Job when the immutable template update cannot be patched.
Kustomization-wide force remains disabled.

The replacement retains all existing fences: one attempt, five-minute active
deadline, no completion TTL, the dedicated migration credential, and required
node affinity limited to `asio` or `strix`. The gateway migration and all
Deployments remain inactive.

The force annotation is temporary. After the migration succeeds and acceptance
evidence is retained, a follow-up cleanup must remove it so a later immutable
change cannot implicitly rerun the Job. That cleanup must preserve the
completed Job until gateway-migration acceptance authorizes its removal.

## Merge and live verification gates

Immediately before merge, record the exact reviewed revision and reconfirm:

1. CI and repository validation are green and the encrypted Secret contract is
   unchanged from review.
2. API/etcd, all nodes, Flux, PostgreSQL, Longhorn, Authentik, certificate, and
   backup/restore evidence are healthy and fresh.
3. `asio` and `strix` remain Ready, pressure-free, schedulable, and have enough
   requested/observed CPU and memory headroom. Stop rather than relying on
   `rig0` or `sparky`.
4. The retained core migration Job is still Failed only from the documented
   anonymous GHCR 401, and the gateway migration and every Deployment remain
   inactive.
5. Al McKay gives the exact-revision go/no-go.

After merge, observe Flux continuously. Success requires both Secrets to exist
without reading their values, all three ServiceAccounts to reference the exact
namespace-local Secret, one replacement migration pod on `asio` or `strix`, a
successful authenticated image pull, one completed migration attempt, the
reviewed migration digest and schema/ownership invariants, no gateway change,
and no degradation in nodes, PostgreSQL, storage, Authentik, or unrelated Flux
objects. Record sanitized Job status, events, placement, restart count, Flux
revision, and capacity before and after. Never record Secret data.

## Stop, rollback, and revocation

Stop on any unexpected node placement, retry, image digest, registry endpoint,
credential consumer, Job replacement, migration output, schema ownership,
Secret exposure, node pressure, or dependency degradation. Preserve the Failed
Job, pod status, sanitized events, and logs; keep later stages inactive.

Before a successful migration, rollback is a reviewed Git revert that removes
the pull-secret resource, ServiceAccount bindings, Job pull reference, and
force annotation. Reconciliation may leave the migration failed, which is the
safe state. Revoke the GitHub token immediately if exposure is suspected or
the recovery is abandoned; do not wait for Git cleanup. A revoked token may
leave cached images runnable but prevents new authenticated pulls.

Rotate before expiry, with an owned target of `2026-11-16`: create a new
read-only package token, update both encrypted Secret documents in one reviewed
change, verify one bounded pull without printing credentials, then revoke the
old token. Owner: Al McKay. Expiry without rotation is a fail-closed release and
restart blocker, not permission to broaden scope or use a personal repository
token.
