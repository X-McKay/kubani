# Starbase Phase 4A activation evidence

This ledger records evidence and decisions for the staged Kubani Phase 4A
activation. It complements
[`starbase-phase4a-preflight.md`](starbase-phase4a-preflight.md) and
[`postgresql-backup-recovery.md`](../operations/postgresql-backup-recovery.md).

## Gate status

| Gate | State | Evidence or blocker |
|---|---|---|
| Off-node encrypted backup | passed | Stage 1 evidence below |
| Trusted promotion regeneration | accepted bounded deferral | Starbase ADR 0009 accepts exact owner-local regeneration as non-independent evidence until its first trigger or 2026-11-30; Starbase PR #18 merged as `68ac908f` on `2026-08-25` |
| Isolated restore | passed | corrected exact Job `postgres-backup-restore-verification-v1-e4deaaf32203` restored the current encrypted backup into an isolated PostgreSQL instance |
| Fail-closed foundation | passed | dedicated Flux Kustomization admitted the inert foundation only after the corrected restore completed |
| SOPS database credentials | passed | PR #69 merged as `6b97be2d`; Flux owns the exact five database Secrets and all consumers remain inactive |
| GHCR pull authentication | passed | PR #81 merged as `2f2043c9`; both namespace-local Secrets and exact ServiceAccount bindings applied; authenticated immutable pull succeeded; cleanup merge `12bcffa7` removed temporary resource-scoped force without replacing or rerunning the completed Job |
| Authentik integration | passed for pre-runtime scope | PR #70 merged as `345986db`; blueprint/discovery verification passed; Al McKay verified member-visible Starbase; Authentik's user-scoped policy check allowed the member and denied two active non-superuser non-members |
| Database bootstrap | passed | PR #79 merged as `beccd384`; the retained Job completed once on `asio`, and exact role, database, ownership, isolation, grant, logging, health, and capacity checks passed |
| Core migration | passed | replacement Job completed once on `asio` at `2026-08-25T23:34:32Z`; exact ledger, ownership, empty-state, privilege, gateway-isolation, lock, health, and capacity checks passed |
| Gateway migration | passed | PR #83 merged as `5f437226`; the exact migration completed once on `asio`, and schema, ledger, ownership, privilege, empty-state, dependency, health, and capacity checks passed |
| Edge and core-identity boundary | passed | PRs #84, #86, and #87 converged fail closed; the final content-bound probe completed at `main@sha1:0e5f5667`, TLS/DNS/expected zero-backend HTTPS passed, and core plus connectors remained at zero |
| Runtime telemetry | accepted pre-runtime constraint; Phase 5 blocker | Prometheus and Grafana remain intentionally scaled to zero by Al McKay; structured logs, probes, Flux/Kubernetes state, and the external operator cover this zero-replica edge stage, but a retained external heartbeat and preview measurement path are required before core activation |
| Ingress and core | edge passed; core blocked | edge acceptance passed; preview telemetry, exact runtime activation, and go/no-go remain required |
| Kubernetes connector | blocked | healthy core and connector-specific verification required |

## Stage 1: off-node encrypted backup

Authorization: Al McKay approved the bounded Stage 1 operation.

- Flux applied revision before and after:
  `main@sha1:fb9a35f9156f91b57bf1fd28adb982d63a91779b`.
- Manual Job from the reviewed CronJob:
  `database/postgres-backup-rig0-initial-202608242352`.
- Started `2026-08-24T23:54:03Z`; completed `2026-08-24T23:54:16Z`.
- Result: one successful pod, zero retries and restarts, 13 seconds.
- Placement: `rig0`, as required by the retained local volume contract.
- Artifact: `postgres-20260824-235406.sql.gz.enc`, 16,454,048 bytes, with a
  matching SHA-256 sidecar after built-in decrypt-and-gzip validation.
- Claim: `database/postgres-backup-rig0`, Bound to
  `pvc-ae2b39f5-8a1b-41a7-bac9-507fd3f41af0`, 2 GiB,
  `local-path-retain`, reclaim policy `Retain`, node affinity `rig0`.
- The legacy `database/postgres-backup` claim remained Bound and unchanged.
- PostgreSQL stayed Ready on `strix` with zero restarts. All nodes remained
  Ready and free of memory, disk, and PID pressure.
- `rig0` stayed at approximately 0% CPU and 19% memory; available filesystem
  capacity after the copy was 972,294,766,592 bytes.
- The expected CronJob-controller `UnexpectedJob` warning for a manually
  instantiated child was observed; the controller adopted the successful Job.
  The unrelated failed scheduled Job from 2026-06-14 predates this exercise.

Conclusion: the fresh encrypted copy is eligible for isolated restore testing.
It is not yet recovery-verified and does not authorize database bootstrap.

Al McKay accepted Starbase ADR 0009 on 2026-08-24 to defer ADR 0008's separate
trusted private-source regeneration gate during bounded single-owner homelab
pre-production. The accepted decision is being versioned in
[Starbase PR #18](https://github.com/X-McKay/Starbase/pull/18), which merged as
`68ac908f` before this activation candidate. Local deterministic regeneration
from exact clean evidence revision `c966518b8c82e755664faa9c37bfd5854089f8a2` and source
revision `ab25087ec856be89d2e00f69f7d230d71cf5301a` verified the changed lock and
left the rendered workload bytes unchanged. This is owner-controlled,
non-independent evidence; ordinary CI does not authenticate the private source.

The original GitHub App, Linux toolchain, credential-isolation, fork-failure,
and revocation gate becomes mandatory again before ADR 0009's first trigger or
2026-11-30 expiry. The deferral does not waive any restore, cluster-health,
capacity, GitOps, rollback, identity, migration, or provider-authority gate.

## Stage 2 pre-change checkpoint

Read-only observations at `2026-08-25T00:01:42Z`:

- Kubernetes API and etcd readiness passed.
- `asio`, `rig0`, `sparky`, and `strix` were Ready and free of memory, disk,
  and PID pressure.
- Node use was: `asio` 3% CPU / 29% memory, `strix` 4% / 21%, `rig0` 0% /
  19%, and `sparky` 1% / 56%.
- All Flux sources, Helm releases, and Kustomizations were Ready at
  `main@sha1:fb9a35f9`.
- PostgreSQL was Ready. No active pod was outside Running or Succeeded state.
- The exact restore verifier remained suspended and had not run.

The Stage 2 change places the exact restore health check on the dedicated
`starbase-foundation` Kustomization. Its matching activation-wave label and
generation check first require the databases Kustomization to apply the
unsuspended Job. The foundation may then apply its inert resources, but it
cannot become Ready or admit a later Starbase activation stage unless the
restore passes. A 25-minute Flux timeout covers the Job's 20-minute deadline
with a controller cushion. A failed restore does not freeze reconciliation of
unrelated Authentik, monitoring, vLLM, or Temporal resources. No Secret,
Authentik mutation, Certificate, Ingress, database bootstrap, migration, or
running Starbase Deployment is part of this tranche.

Repository validation before review:

- the full local inventory, secret scans, six Kustomize builds, 33 promotion,
  dependency, and recovery tests, and required hook checks passed;
- changed-file YAML, secret, private-key, large-file, conflict, and policy
  hooks passed;
- the 45-resource foundation passed strict Kubernetes 1.34 schema validation;
- the rendered foundation contained zero runnable Starbase workloads;
- cached Trivy checks reported only the documented `export PGPASSWORD`
  ConfigMap heuristic; the script contains a variable name, not a value, and
  independent plaintext-Secret and secret scans passed;
- Actionlint, shell parsing, and `git diff --check` passed; and
- server-side dry-run under Flux's existing field-manager identity accepted
  the databases Kustomization, new foundation Kustomization, restore ConfigMap,
  and exact restore Job without persisting them.

A second read-only cluster checkpoint at `2026-08-25T00:08:11Z` found the API,
all nodes, Flux, and PostgreSQL healthy. `asio` remained at 3% CPU / 29% memory,
`strix` at 4% / 21%, and `rig0` at 0% / 19%. The restore Job remained suspended
with no active, successful, or failed pod. No cluster mutation occurred during
development or validation.

## Stage 2 acceptance evidence to record after merge

Before and after reconciliation, record API/etcd, Flux, PostgreSQL, node
pressure and use, `rig0` filesystem headroom, unexpected pods, and the exact
applied revision. Then record:

- restore Job start, finish, node, pod count, retries, restarts, and duration;
- checksum, decrypt, restore, and catalog-invariant success without names,
  SQL, hashes, or credentials in retained logs;
- confirmation that the backup volume mounted read-only and no connection
  reached the source PostgreSQL service;
- the databases Flux Kustomization applying the unsuspended Job while remaining
  independent of its result;
- the `starbase-foundation` Flux Kustomization applying only inert resources
  and becoming Ready only after exact Job completion;
- the ordinary apps Kustomization remaining Ready and able to reconcile;
- all Starbase Deployments remaining at zero and all Starbase Jobs remaining
  suspended; and
- no Authentik, Certificate, Ingress, DNS, Secret, or database mutation from
  the foundation.

Any failed or ambiguous check is a stop. Preserve the Job and logs and revert
the complete activation commit to resuspend the verifier, remove the health
check, and reconcile normal desired state. Re-suspending only the Job while
leaving the health check in place is not rollback: the suspended Job can never
complete, so `starbase-foundation` remains NotReady indefinitely. That partial
state is isolated from the ordinary apps tier, but no later Starbase gate may
advance from it.

## Stage 2 failed attempt and correction candidate

The merged revision `main@sha1:d5356873bc6b6e7e7247da1d1387afd63c89125d`
was observed by Flux before the verifier started. At `2026-08-25T01:09:08Z`,
the exact Job `postgres-backup-restore-verification-v1-945bf4f5b132` created one
pod on `rig0`. It exited once with code 1, zero restarts, and zero retries at
`2026-08-25T01:09:09Z`. The encrypted backup checksum and stream-integrity
check passed. PostgreSQL initialization did not begin because direct Kubernetes
`command` replacement bypassed the pinned Bitnami image entrypoint, leaving UID
1001 absent from the container identity database. The retained sanitized error
was `initdb: could not look up effective user ID 1001: user does not exist`.

The failure did not connect to or mutate source PostgreSQL. PostgreSQL remained
Ready on `strix` with zero restarts. All Starbase Deployments remained at zero,
all database bootstrap and migration Jobs remained suspended, and the ordinary
`apps`, `databases`, `flux-system`, and `infrastructure` Kustomizations remained
Ready. The dedicated `starbase-foundation` Kustomization became NotReady with
`HealthCheckFailed`, which is the intended fail-closed result. At the
`2026-08-25T01:10:28Z` checkpoint all four nodes were Ready and pressure-free;
`asio` used 4% CPU / 29% memory, `strix` 5% / 21%, and `rig0` 0% / 19%.

The proposed correction preserves the image's reviewed entrypoint, passes the
verifier script as arguments, and adds an explicit runtime-identity guard before
`initdb`. The content-bound replacement Job is
`postgres-backup-restore-verification-v1-e4deaaf32203`. Local execution against
the exact pinned image confirmed that the preserved entrypoint exposes UID 1001
through NSS and successfully initializes PostgreSQL. The live failed Job is the
evidence for the bypassed Kubernetes path; the local Podman runtime supplies
its own user mapping and cannot reproduce that missing-identity condition.
Merging the correction would create a new, unsuspended restore Job and therefore
requires a fresh cluster checkpoint and separate authorization; preparing or
reviewing this change does not authorize the rerun.

## Stage 2 successful corrected exercise

Al McKay merged the reviewed correction at
`main@sha1:aa892945e23c36d24101a22eae5a9e408e4193de` on
`2026-08-25T02:51:58Z`. Flux applied that exact revision. The content-bound Job
`postgres-backup-restore-verification-v1-e4deaaf32203` started on `rig0` at
`2026-08-25T02:52:42Z` and completed at `2026-08-25T02:52:49Z`. It created one
pod, exited 0, and had zero retries and restarts.

The Job selected the scheduled `2026-08-25T02:00:00Z` encrypted copy. Its
checksum and decrypt/gzip integrity checks passed, the isolated Unix-socket-only
PostgreSQL restore completed, and the catalog invariants reported 10 databases,
25 roles, and 345 Authentik application tables. The backup claim was mounted
read-only. The restore pod was selected by the namespace-wide DNS-only egress
policy and by no PostgreSQL allow policy, so it had no network path to source
PostgreSQL. From merge to verified completion was 51 seconds, within the
development two-hour RTO objective; the backup was 53 minutes old at completion,
within the 24-hour RPO objective.

Afterward, all Flux Kustomizations were Ready at the merged revision. PostgreSQL
remained 2/2 Ready on `strix` with zero restarts. All nodes were Ready and free
of memory, disk, and PID pressure. `rig0` remained at 0% CPU and 19% memory with
972,268,703,744 filesystem bytes available at `2026-08-25T02:53:33Z`. Core and
both connectors stayed at zero replicas; both migration Jobs stayed suspended;
no failed or pending pod remained. The old and new backup claims remained Bound.

### Retained `psql` output deviation

The successful restore pipeline used `psql --quiet`, but successful dump replay
still emitted non-secret `NOTICE` messages naming known databases and roles plus
sequence-result rows. Review found no credential, password hash, or plaintext
SQL in the retained log. The output did not affect restore integrity, source
isolation, or authorization, but it was noisier than this ledger's intended
minimal evidence standard.

Retain the Job and log as truthful exercise evidence; do not delete them to make
the record cleaner. Al McKay owns a normal-priority follow-up for the next
separately authorized restore-script revision and exercise: suppress successful
replay stdout and `NOTICE` output while preserving actionable stderr, add an
allowlist regression test for retained lines, and verify the resulting
content-named Job. The current unsuspended script must not be edited solely for
log cosmetics because a digest change would create and run a new Job without a
new restore authorization.

## Stage 3 encrypted-credential candidate

The next reviewed tranche adds exactly five SOPS-encrypted, workload-scoped
Secrets for database bootstrap, core runtime, gateway runtime, core migration,
and gateway migration. PostgreSQL TLS is disabled in the current HelmRelease,
so database URLs explicitly use `sslmode=disable` within the existing exact
NetworkPolicy boundary. Core and connectors remain at zero replicas and all
database Jobs remain suspended. Merge would provision credentials but would not
use them; it requires a fresh checkpoint, exact-revision authorization, SOPS
reconciliation evidence, and confirmation that no workload started.

Each file is encrypted to the repository's existing age recipient, and the
current Flux Kustomization successfully decrypts existing files for that same
recipient. On `2026-08-25`, the owner-protected age identity already retained
on `rig0` was copied to the operator workstation's gitignored `age.key` path
with mode `0600`. The identity's derived public recipient exactly matched
`.sops.yaml`, and all five candidate files decrypted locally to a discarded
output stream. No private key or decrypted Secret value was printed, retained
as evidence, committed, uploaded, or copied into this branch. The temporary
transfer copy was removed after installation, while the original recovery copy
on `rig0` was preserved.

This closes the off-cluster recoverability and local-ciphertext merge gate. It
does not prove live Flux application, authorize merge, or authorize credential
use. Merge still requires a fresh health and capacity checkpoint,
exact-revision authorization, SOPS reconciliation evidence, and confirmation
that no workload started. Do not retrieve or publish the live `sops-age`
Secret merely to repeat this verification.

## Stage 3 encrypted-credential acceptance

PR #69 merged at `2026-08-25T03:29:31Z` as
`6b97be2da67b2ecb8cabcc0214cda0e3ae26e6fb`. At
`2026-08-25T03:31:47Z` and `2026-08-25T03:32:44Z`, Flux reported all five
Kustomizations Ready at the exact revision. The foundation inventory owned the
five reviewed Secret objects and each exposed only its reviewed key names; no
value was printed or retained. Core and both connectors remained at zero, all
three database Jobs remained suspended, and no Starbase pod existed. API/etcd,
all nodes, Authentik, PostgreSQL, and unrelated Flux resources stayed healthy.
No rollback was indicated. The retained PR evidence is
<https://github.com/X-McKay/kubani/pull/69#issuecomment-5404721619>.

## Stage 4 Authentik owner-path candidate

The candidate moves the already-reviewed `starbase.yaml` data into the sole
mounted `authentik-blueprints` ConfigMap and removes the duplicate review-only
ConfigMap. Merge can create or update the non-superuser group, group scope,
public OAuth2 provider, Starbase application, and direct group binding in
Authentik. Authentik applies a blueprint transaction atomically; failure must
leave no partial configuration. The change cannot start a Starbase Deployment,
unsuspend a Job, create a Starbase Ingress, or issue its certificate.

Before the upgrade, a read-only query of the then-installed `2025.10.3` public
OpenAPI document established why the original candidate omitted newer grant
and redirect-type fields. That evidence remains historical only; it no longer
describes the active Authentik API.

The pre-change checkpoint at `2026-08-25T03:38:42Z` passed: API/etcd and all
Flux resources were Ready at `main@sha1:6b97be2d`; all four nodes were Ready and
pressure-free; `asio` used 3% CPU / 29% memory and `strix` 4% / 21%; Authentik
server and worker were Ready on `asio` and `strix`; its certificate and health
endpoint were Ready; all Starbase Deployments stayed at zero and Jobs stayed
suspended. The Starbase discovery endpoint returned 404, proving the provider
was not active before this candidate.

The post-validation checkpoint at `2026-08-25T03:47:29Z` reproduced that
state. Flux remained Ready at unchanged `main@sha1:6b97be2d`; the live owner
ConfigMap still contained only `kubani-forward-auth.yaml`; discovery still
returned 404; all nodes remained pressure-free; `asio` and `strix` were each at
4% CPU with 29% and 21% memory use; and every Starbase workload remained
inactive. Server-side dry-run persisted no object.

PR #78 merged the separately reviewed Authentik upgrade at
`2026-08-25T15:43:45Z` as
`fe9a6047dcf53c1d8bd220847a4cfd5df04e6bc6`. The refreshed checkpoint observed
all Flux Kustomizations Ready at that exact revision; all four nodes Ready and
pressure-free; at `2026-08-25T16:17:45Z`, `asio` was at approximately 4% CPU /
35% memory and `strix` at 5% / 18%; and the Authentik server and worker were
Ready on those preferred nodes at `2026.5.6`, with zero restarts. Authentik
readiness returned HTTP 200, the
embedded outpost retained the FalkorDB and Qdrant assignments, and PostgreSQL
showed no waiting locks or idle-in-transaction sessions. A transient image-pull
DNS failure recovered without intervention and did not recur during the
checkpoint.

The refreshed read-only live-service suite passed every required probe. The
registry authenticated probe remained intentionally skipped because no
registry credential was supplied, and the embeddings model probe was skipped
because its owning Deployment explicitly remained at zero replicas. The three
empty Starbase/embeddings Services were likewise accepted only because their
mapped owner Deployments explicitly declared zero; the checks fail closed as
soon as an owner is activated. All Starbase Deployments remained at zero and
all Starbase migration Jobs remained suspended.

Al McKay reported a successful interactive Authentik login after the upgrade.
This attests to that baseline login path only; it is not evidence of
Starbase application launch, group authorization, logout, token validation, or
refresh behavior.

A cache-busted read-only query of the live `2026.5.6` OpenAPI document verified
that `OAuth2ProviderRequest` accepts an explicit `authorization_code` grant and
that strict redirect entries accept `redirect_uri_type: authorization`. The
candidate now declares both. Authentik's public schema endpoint was observed
serving a stale CDN-cached `2025.10.3` document without cache busting, so schema
verification and the OIDC verifier use explicit no-cache requests and an
observation query parameter.

After an authorized merge, stop unless the exact revision reconciles, the
worker remains healthy, discovery advertises the exact issuer and S256 PKCE,
JWKS contains an RSA key, and all product workloads remain inactive. Run the
read-only `infrastructure/scripts/validate-starbase-oidc.sh`, inspect the
blueprint result in Authentik, deliberately add only the intended operator to
`starbase-operators`, and exercise both allowed-member and denied-non-member
behavior before any core activation.

Removal of `starbase.yaml` alone is not rollback: Authentik leaves created
objects intact when a file-based blueprint disappears. Roll back with a
reviewed forward revision whose mounted blueprint sets the policy binding,
application, provider, scope mapping, and finally the dedicated group to
`state: absent`; verify discovery returns 404 and existing Authentik apps remain
healthy; then remove the cleanup file in a later revision. Do not remove the
group while it has another member or use.

## Stage 5 Authentik owner-path acceptance

PR #70 merged at `2026-08-25T17:50:13Z` as
`345986dbd1c2ac7f90825e23da5b1465dff02079`. Flux reconciled every source and
Kustomization at that exact revision. The Authentik blueprint instance reported
successful application; the non-superuser `starbase-operators` group, public
Starbase provider, application, scope, and direct group binding matched the
reviewed contract. The read-only OIDC verifier passed the exact issuer,
discovery, RSA JWKS, S256 advertisement, callback, and public-client contract.
All Starbase Deployments stayed at zero and every database Job stayed suspended.

Al McKay was deliberately added as the sole `starbase-operators` member and
reported that Starbase is visible in Authentik. Authentik's authenticated,
user-scoped `check_access` API then evaluated the exact Starbase application:
the intended member passed, while both existing active, non-superuser,
zero-group outpost service principals were denied. Only boolean policy results
were retained; no membership or identity state changed. This independently
closes the provider application-policy member and non-member gate. The
Starbase-side group denial, callback, token, session, expiry, and logout checks
remain correctly deferred until DNS, TLS, Ingress, and core exist.

## Stage 6 database-bootstrap acceptance

Read-only preflight between `2026-08-25T18:46Z` and `2026-08-25T18:55Z` used
Kubani context `default` at applied revision `main@sha1:345986db`. Kubernetes
API/CoreDNS/metrics reachability passed; all four nodes were Ready and free of
memory, disk, and PID pressure; no active pod was outside Running or Succeeded;
and every Flux source, HelmRelease, and Kustomization was Ready. `asio` measured
3% CPU / 34% memory with 1,425m CPU and 830 MiB requested. `strix` measured 4%
CPU / 18% memory with 1,555m CPU and 1,144 MiB requested. Both retain ample
headroom for the 25m CPU / 32 MiB bootstrap request.

PostgreSQL was 1/1 Ready on `strix`, accepted connections, had no ungranted
locks or active waiting sessions, and its 20 GiB Longhorn volume was attached
and healthy. Neither Starbase database nor any of the four Starbase roles
existed. The `2026-08-25T02:00Z` backup completed in ten seconds on `rig0`; its
log reported the built-in encrypted-stream/checksum proof and a 16,491,408-byte
artifact. It was less than 48 hours old. The previously verified isolated
restore and retained claims remain present.

The statement-capture preflight found `log_statement=none`, `log_duration=off`,
`log_min_duration_statement=-1`, empty session/local preload lists, and only
`pgaudit` in `shared_preload_libraries`. `pgaudit.log=none`, catalog logging,
parameter logging, relation logging, and statement-once logging were all off;
only `plpgsql` was installed. No unreviewed password-bearing statement-capture
path was found. These settings must be refreshed immediately before merge.

The candidate unsuspends only
`database/starbase-database-bootstrap-v1-0f68098795da`. It restricts scheduling
to the `asio`/`strix` set, sets zero automatic retries, and removes the 24-hour
completion TTL so Flux cannot garbage-collect and recreate a successfully
completed Job. The completed Job remains immutable evidence through both
migration gates. Al McKay owns its removal after status, sanitized logs, exact
ownership/grant checks, and both successful migration results are retained in
this ledger; removal is a later reviewed cleanup and must not recreate or rerun
the bootstrap. Both migration Jobs and all three Deployments remain inactive;
no Certificate, Ingress, or DNS resource is added.

Merge remains blocked until fresh checks reproduce this baseline, CI is green,
and Al McKay gives the exact-revision Stage 6 go/no-go. After merge, stop on any
unexpected placement, retry, log content, ownership, role, grant, health,
capacity, or Flux result.
Rollback after partial execution is not merely a Git revert: keep workloads and
migrations inactive, preserve evidence, and use the reviewed Starbase-only
database/role cleanup path or forward repair according to the observed state.

Al McKay approved and merged PR #79 at `2026-08-25T19:25:26Z` as
`beccd384b2b876a7418279cf7de23d06d45f96fb`. This happened before the operator
could run the intended final pre-merge refresh. The last complete pre-merge
checkpoint was at `2026-08-25T19:06:55Z`, approximately 19 minutes before
merge. This timing deviation is retained rather than retroactively described
as a satisfied gate. Immediate post-merge observation began at
`2026-08-25T19:27:05Z`; no drift, degradation, or abort condition was found.

Flux applied `main@sha1:beccd384`. The exact Job
`database/starbase-database-bootstrap-v1-0f68098795da` started at
`2026-08-25T19:26:11Z` and completed at `2026-08-25T19:26:27Z`: one successful
pod, zero failed attempts, zero container restarts, and placement on preferred
node `asio`. Its bounded log contained ordinary PostgreSQL command tags and the
reviewed completion message; no credential value was emitted. The completed
Job remains retained without a TTL and with `backoffLimit: 0` through both
migration gates.

Independent catalog checks found exactly four `LOGIN NOINHERIT` Starbase roles,
all without superuser, database-create, role-create, or replication authority.
`starbase_core` is owned by `starbase_core_migrator`; `starbase_gateway` is
owned by `starbase_gateway_migrator`; `PUBLIC` cannot connect. Each runtime and
migrator role can connect only to its owned service database, with every
cross-service connection check denied. The `starbase_core` and
`experience_gateway` schemas are owned by their corresponding migrators.
Runtime roles have schema usage but not create authority; `PUBLIC` cannot create
in either public schema. Default table DML and sequence privileges are scoped
only to the corresponding runtime role. Both service schemas contained zero
tables, no Starbase role membership existed, and there were no ungranted locks,
active waiting client sessions, or idle transactions.

At the final `2026-08-25T19:29:18Z` checkpoint every Flux source,
Kustomization, and HelmRelease was Ready at the merge revision. PostgreSQL was
2/2 Ready with zero restarts on `strix`; its 20 GiB Longhorn volume remained
attached and healthy. All nodes were Ready and pressure-free: `asio` used 3%
CPU / 30% memory and `strix` 5% / 18%. Both migration Jobs remained suspended,
all Starbase Deployments remained at zero, no Starbase Ingress or Certificate
existed, the OIDC verifier passed, and Authentik's user-scoped policy check
allowed the intended member while denying both tested non-members. The retained
backup and isolated-restore evidence remained valid. No rollback or recovery
action was indicated.

## Stage 7 core-migration candidate

This candidate unsuspends only
`starbase-system/starbase-core-migrate-22bfaa3b1e8f`. The immutable migrator
image is unchanged. The Job uses the dedicated core-migrator credential, a
single PostgreSQL connection, a content-bound advisory lock, a two-second lock
timeout, a ten-second per-migration statement timeout, a two-minute process
timeout, and a five-minute Job deadline. It requests 25m CPU / 32 MiB memory,
is required to schedule on `asio` or `strix`, has zero automatic retries, and
has no completion TTL. The Starbase foundation Flux Kustomization gains an
exact health check for this Job, so it cannot report Ready until the migration
succeeds. The gateway migration remains suspended; all Deployments remain at
zero; Certificate, Ingress, and DNS remain absent.

The core migration is additive and operates on a new empty authoritative
database. It creates `starbase_core.schema_migrations`,
`starbase_core.state_journal`, and `starbase_core.state_current`; it performs no
backfill and contains no `DROP`, `TRUNCATE`, or `DELETE`. The expected ledger
entry is `0001_initial.sql` with digest
`sha256:dd8924aec9c52d3e4bc106f9501a52c92129cdd3d4a43745a614534abcc624a7`.

The read-only candidate baseline at `2026-08-25T19:34:43Z` used context
`default` at `main@sha1:beccd384`. All nodes were Ready and pressure-free.
`asio` used 3% CPU / 30% memory with 1,425m CPU and 830 MiB requested;
`strix` used 4% / 18% with 1,555m CPU and 1,144 MiB requested. The namespace
quota had zero active pod CPU or memory usage, two of six allowed Jobs, and
ample room for the 25m / 32 MiB request. All Flux resources were Ready.
PostgreSQL was 2/2 Ready with zero restarts on `strix`, accepted connections,
and its 20 GiB Longhorn volume was attached and healthy. There were no
ungranted locks, active waiting client sessions, or idle transactions. The
bootstrap and isolated-restore Jobs remained successfully retained; the core
and gateway schemas remained empty; both migration Jobs remained suspended;
and every Starbase Deployment remained at zero. OIDC discovery, JWKS, owner
blueprint, and inactive-workload checks passed.

The latest encrypted off-node backup completed at `2026-08-25T02:00:10Z`, and
the corrected isolated restore completed at `2026-08-25T02:52:49Z`. That backup
predates the bootstrap and therefore does not contain the new empty Starbase
databases or roles. This is explicitly acceptable for this candidate because
there is no Starbase application data: the deterministic bootstrap and
encrypted credentials can recreate the empty boundary, while a failed core
migration is handled by Starbase-only forward repair or cleanup rather than a
shared PostgreSQL restore. Backup freshness and this no-data invariant must be
rechecked before merge.

Kubernetes server-side dry-run accepted the complete Secret-free rendered
foundation and the Flux health-gate update using Flux's real server-side apply
manager and conflict semantics. This proves the never-started suspended Job's
scheduling, retry, retention, annotation, and suspension updates are currently
admission-valid; it does not execute or authorize the migration.

Review follow-up at `2026-08-25T21:34:59Z` independently rechecked the possible
Job-immutability failure against Kubani's Kubernetes `v1.34.7+k3s1` API. The
live core migration Job existed with `suspend: true`, `backoffLimit: 2`, no
start time, and no active, successful, or failed pod. A server dry-run changing
only `backoffLimit` to zero succeeded. The exact rendered Flux-mode server
dry-run, including the preferred-to-required node-affinity change, also
succeeded. As a positive control, a server dry-run changing the truly immutable
pod-template `serviceAccountName` failed with `spec.template: field is
immutable`. This demonstrates that admission validation was active and that the
candidate relies only on Kubernetes' supported
[mutable scheduling directives](https://v1-34.docs.kubernetes.io/docs/concepts/workloads/controllers/job/#mutable-scheduling-directives)
for a suspended Job that has never been unsuspended; delete/recreate or Flux
force replacement is neither required nor desirable.

The same review follow-up queried both live Kustomization `dependsOn` entries
and desired-state manifests. No Kustomization depends on
`starbase-foundation`. A failed core migration therefore makes only the
Starbase foundation NotReady; it does not stall the `apps`, `databases`,
`infrastructure`, or other unrelated reconciliation paths.

Before merge, the operator must freshly reconfirm the exact approved PR head,
green CI, cluster context, node pressure and capacity, Flux health, PostgreSQL
readiness, storage health, backup age and restore evidence, no waiting locks or
idle transactions, the completed bootstrap invariants, an empty core schema,
and an inactive gateway migration and runtime. The live
`starbase-core-migrate-22bfaa3b1e8f` Job must still report `suspend: true` with
no `status.startTime`, active pod, success, or failure; otherwise stop because
the scheduling-directive update is no longer proven admission-valid. Al
McKay's exact-revision go/no-go remains required.

After merge, stop on unexpected placement, any retry, timeout, ambiguous Job
state, migration digest mismatch, unexpected object or owner, missing runtime
grant, gateway mutation, Flux degradation, PostgreSQL contention, storage or
backup degradation, node pressure, or loss of external observation. Success
requires one completed pod on `asio` or `strix`; exactly the three expected
tables owned by `starbase_core_migrator`; exactly one migration-ledger row with
the expected digest; empty state tables; runtime DML without schema-create or
ownership authority; no gateway schema change; healthy PostgreSQL, Flux,
storage, identity, and nodes; and continued zero replicas.

Application rollback does not reverse schema. If the Job fails, preserve its
pod, status, events, and sanitized logs; keep the gateway migration and every
runtime inactive; and diagnose before retry. Prefer a reviewed forward repair
when the schema is compatible. Because no Starbase application data exists,
the separately reviewed Starbase-only cleanup remains available if the schema
is unusable; never restore or alter the shared PostgreSQL instance for this
bounded case. Retain the completed core Job through gateway-migration
acceptance, then remove it only through a reviewed cleanup that cannot rerun it.

## Stage 7 pull-auth failure and recovery candidate

The merged activation scheduled the exact core migration Job on `asio`, but the
container never started. GHCR returned HTTP 401 to the anonymous manifest-token
request, Kubernetes entered `ImagePullBackOff`, and the retained Job reached its
five-minute active deadline with no schema execution. This is a registry
authentication failure, not migration evidence. The foundation alone is
NotReady; unrelated Flux objects remain healthy and every Starbase Deployment
remains at zero replicas.

The reviewed recovery contract is
[`starbase-ghcr-pull-recovery.md`](starbase-ghcr-pull-recovery.md). It adds two
namespace-local SOPS-encrypted `read:packages` pull Secrets, binds only the
three current Starbase ServiceAccounts, and uses Flux's temporary
resource-scoped force annotation to replace the one immutable Failed Job. The
gateway migration and all Deployments remain inactive. Successful acceptance
requires a single authenticated pull and completed migration on `asio` or
`strix`, full schema and ownership verification, healthy dependencies and
capacity, retained sanitized evidence, and a follow-up cleanup removing the
force annotation.

## Stage 7 recovery and core-migration acceptance

Al McKay merged PR #81 as `2f2043c9122925904e75a2b47559ae9b5d45782b`
after its three exact-head CI checks passed. Flux replaced only the Failed core
migration Job. The replacement started at `2026-08-25T23:34:27Z`, completed at
`2026-08-25T23:34:32Z`, ran once on preferred node `asio`, had zero restarts and
zero failed attempts, and used the reviewed immutable image digest
`sha256:90f72400491e6ce13c8186a59fdc05bfedd256462cd03d6a5e1ec543de15bd08`.
Its retained log contains only the structured completion event.

Both namespace-local pull Secrets existed with type
`kubernetes.io/dockerconfigjson` and expiry `2026-11-23T00:00:00Z`; the core,
GitHub-connector, and Kubernetes-connector ServiceAccounts referenced only their
namespace-local `starbase-ghcr-pull`. No Secret data was read. The gateway
migration remained suspended and all three Starbase Deployments remained at
zero replicas.

Read-only PostgreSQL catalog verification found exactly
`schema_migrations`, `state_current`, and `state_journal`, all owned by
`starbase_core_migrator`. The ledger contained exactly `0001_initial.sql` with
digest
`sha256:dd8924aec9c52d3e4bc106f9501a52c92129cdd3d4a43745a614534abcc624a7`.
Both state tables contained zero rows. `starbase_core_runtime` had schema usage
and table DML but no schema-create or table ownership authority. The gateway
schema still contained zero tables. PostgreSQL reported zero waiting locks and
zero idle-in-transaction sessions.

At the final checkpoint, every Flux source, HelmRelease, and Kustomization was
Ready at `main@sha1:2f2043c9`. All nodes were Ready with MemoryPressure,
DiskPressure, and PIDPressure false. `asio` used 3% CPU / 28% memory and `strix`
5% / 18%. PostgreSQL remained Ready with zero restarts on `strix`; Authentik's
server and worker were Available. No unhealthy pod was returned. The retained
core Job was Complete and all later Starbase stages remained inactive.

All acceptance invariants passed. This candidate removes the temporary
`kustomize.toolkit.fluxcd.io/force` annotation only; the completed Job remains
retained and the pull bindings remain required. Gateway migration must not be
authorized until that cleanup reconciles and the same health, capacity,
database, and inactivity gates are freshly rechecked. That condition was
satisfied when cleanup merge `12bcffa7` reconciled; Stage 8 now governs the
separate gateway decision.

## Stage 8 gateway-migration candidate

This candidate unsuspends only
`starbase-system/starbase-gateway-migrate-38db19887578` and adds that exact Job
to the Starbase-only Flux health gate. The immutable gateway-migrator image is
`ghcr.io/x-mckay/starbase/gateway-migrator@sha256:89956fe4ee3d75cb5106150334c70ef83894aa0b504de34520b5bd8fce089820`.
An authenticated operator-host manifest check returned HTTP 200 and that exact
OCI index digest without retaining a credential or manifest body.

The Job uses only the dedicated gateway-migrator database credential. It has a
single PostgreSQL connection, advisory-lock fencing, a two-second DDL lock
timeout, a ten-second per-migration statement timeout, a five-minute Job
deadline, zero retries, and no completion TTL. It requests 25m CPU / 32 MiB
memory, must schedule on `asio` or `strix`, cannot automount a Kubernetes token,
and has no provider authority. The completed core Job remains retained; every
Deployment stays at zero; Certificate, Ingress, DNS, and connector activation
remain absent.

The migration set digest is
`sha256:38db198875781dd2d640358b1840ae28e7574dd4c87661e0a8bb0b2e8837d3f3`.
It creates only `experience_gateway.schema_migrations`,
`experience_gateway.operator_sessions`, and the session-expiry index. The sole
embedded migration is `0001_operator_sessions.sql` with digest
`sha256:e860af141ba5717dcf84020da9a5c1f18b841e34b9c9d3a5d3b95aec9b45e3b6`.
It is additive, performs no backfill, and contains no `DROP`, `TRUNCATE`, or
`DELETE`. The session table persists a session digest and encrypted refresh
token rather than access tokens, ID tokens, plaintext session tokens, or email.
No row is created by the migration.

At `2026-08-25T23:45:50Z`, every Flux Kustomization was Ready at cleanup merge
`12bcffa7`; all four nodes were Ready and pressure-free; `asio` used 4% CPU /
29% memory and `strix` 5% / 18%. PostgreSQL was Ready with zero restarts on
`strix`; its 20 GiB Longhorn volume was attached and healthy. The gateway
schema contained zero tables, its runtime role had schema usage but not create
authority, and PostgreSQL had zero waiting locks or idle-in-transaction
sessions. The live Job remained suspended with no start, success, failure, or
pod; core migration remained accepted; every Starbase Deployment remained at
zero. Kubernetes server-side dry-run accepted the exact candidate without
persistence.

The latest scheduled encrypted backup completed at `2026-08-25T02:00:10Z`, and
the matching isolated restore completed at `2026-08-25T02:52:49Z`. They predate
the deterministic empty Starbase schemas. This remains an explicit bounded
no-application-data exception: core state tables are empty, the gateway schema
is empty, and each schema can be deterministically recreated or removed using
the already reviewed Starbase-only recovery path. Recheck the next scheduled
backup if it completes before merge; stop if any application row appears or the
no-data invariant changes.

Before merge, freshly reconfirm the exact approved PR head, green CI, Flux
health, node pressure/headroom, PostgreSQL readiness, Longhorn health, backup
status, zero locks/idle transactions, the accepted core ledger and empty state,
an empty gateway schema, a never-started suspended gateway Job, and zero
Starbase replicas. Al McKay's merge is the exact-revision go/no-go.

After merge, stop on unexpected placement, any retry, image or migration digest
drift, unexpected table/owner/row, missing runtime grant, core mutation, Flux or
dependency degradation, node pressure, or loss of external observation.
Success requires one completed pod on `asio` or `strix`; exactly the two
expected tables owned by `starbase_gateway_migrator`; one expected ledger row;
zero operator-session rows; runtime DML without schema-create or ownership;
unchanged core ledger/state; healthy Flux, PostgreSQL, Longhorn, Authentik, and
nodes; and continued zero replicas. Preserve the completed Job and evidence;
prefer forward repair or the reviewed Starbase-only cleanup over shared
PostgreSQL restore if an invariant fails.

## Stage 8 gateway-migration acceptance

Al McKay merged PR #83 as
`5f437226342b5c83cfa1ede298b939c6e72e4f38` at
`2026-08-25T23:52:52Z`. Flux first exposed the expected dependency-not-current
state while the new source revision propagated, then every Kustomization became
Ready at that exact merge revision without intervention.

The Job `starbase-gateway-migrate-38db19887578` started at
`2026-08-25T23:54:36Z` and completed at `2026-08-25T23:54:40Z`. It ran once on
`asio`, had zero restarts and no failed attempt, and used the reviewed image
digest `sha256:89956fe4ee3d75cb5106150334c70ef83894aa0b504de34520b5bd8fce089820`.
Its retained log was empty; no credential or database content was emitted.

Independent read-only catalog verification found exactly
`experience_gateway.schema_migrations` and
`experience_gateway.operator_sessions`, both owned by
`starbase_gateway_migrator`, plus the exact session-expiry index. The ledger
contained exactly `0001_operator_sessions.sql` with digest
`sha256:e860af141ba5717dcf84020da9a5c1f18b841e34b9c9d3a5d3b95aec9b45e3b6`.
The session table contained zero rows. `starbase_gateway_runtime` had the
required table DML and no schema-create authority. PostgreSQL had zero waiting
locks and zero idle-in-transaction sessions.

The core ledger remained exactly `0001_initial.sql` at digest
`sha256:dd8924aec9c52d3e4bc106f9501a52c92129cdd3d4a43745a614534abcc624a7`,
and both core state tables remained empty. PostgreSQL and its Longhorn volume,
Authentik, Flux, the API, and every node remained healthy. At the final
checkpoint, `asio` used 7% CPU / 29% memory and `strix` 4% / 18%; neither had
memory, disk, or PID pressure. No unhealthy pod existed, and core plus both
connectors remained at zero replicas.

The first observer query used `table_name` instead of PostgreSQL's
`pg_tables.tablename` and failed read-only before returning acceptance data.
The corrected query then produced the evidence above. This was an operator
query defect, not a migration retry or workload failure.

## Stage 9 edge and network-boundary candidate

This candidate moves the already reviewed `Certificate` and browser-only
`Ingress` into the active Starbase foundation while every Deployment remains
at zero. The Ingress routes only `starbase.almckay.io/` to the web Service on
port 80; the connector-only API Service is absent from the route. ExternalDNS,
currently one healthy replica on `asio`, owns creation of the DNS-only
Cloudflare record from that Ingress. `starbase.almckay.io` deliberately has no
pre-existing DNS answer, so no unmanaged record or ad hoc Cloudflare mutation
is being accepted. The `letsencrypt-prod` ClusterIssuer is Ready, and the Flux
gate now requires the exact `starbase-tls` Certificate to become Ready.

The content-bound Job `starbase-network-boundary-v1-c804f51209e6` uses the
real `starbase-core` ServiceAccount, policy-selecting labels, a dedicated
ten-minute token whose audience is the K3s service-account issuer, the root CA,
and required `asio`/`strix` placement. The API-audience token is used only to
prove successful Kubernetes authentication followed by Secret-list RBAC denial;
it is not accepted as a Starbase workload token and no custom `starbase-core`
audience token is presented to the API server.
It contains no application or database credential and reuses Kubani's existing
digest-pinned PostgreSQL utility image. With zero retries and a five-minute
deadline, it must prove PostgreSQL TCP, Authentik discovery, and Kubernetes
issuer reachability; Kubernetes Secret listing must authenticate but return
403; cloud-metadata and arbitrary Internet TCP paths must remain blocked. Flux
cannot report the foundation Ready until the exact Job succeeds. The completed
Job is retained without a TTL so ordinary reconciliation cannot rerun it.

The first merged Stage 9 attempt at Kubani revision `1e3f02e2` failed closed
on `asio` before reaching the RBAC assertion. Retained logs showed that the
projected token and CA had moved to the `kubernetes-api` mount while both
`curl --cacert` arguments still referenced the removed `workload-identity`
path. The Job had zero retries, Flux reported the foundation unhealthy, and
core plus both connectors remained at zero replicas. The correction updates
both CA references, forbids the stale path in the contract test, and changes
the content-bound Job identity. The failed attempt is retained as diagnostic
evidence and is not counted as a successful boundary verification.

The second merged attempt at Kubani revision `f7709517` resolved the CA mount
but failed closed on `asio` when the unauthenticated issuer JWKS request
returned `401`. It again ran once with zero restarts, left every runtime at
zero replicas, and kept Flux unhealthy. The corrected probe now sends the same
short-lived API-audience token to both Kubernetes endpoints through one
stdin-fed curl configuration. It requires authenticated JWKS access to return
`200` and the Secret-list request to return `403`; the token remains absent
from process arguments. This failed attempt is also retained as diagnostic
evidence and does not count as successful verification.

Prometheus and Grafana remain intentionally scaled to zero. This zero-replica
edge stage therefore uses the Kubernetes API, Flux status, Job and Certificate
health, structured retained logs, and the external operator as compensating
observation. That does not satisfy the Phase 5 preview telemetry or external
heartbeat gate. Core activation remains blocked until a separately reviewed
retained heartbeat and measurement path exists; this constraint does not
silently treat missing telemetry as healthy.

Before merge, reconfirm the exact PR head and CI; API, Flux, ExternalDNS,
cert-manager, Authentik, PostgreSQL, Longhorn, backups, nodes, and capacity;
the two accepted migration ledgers and empty tables; absence of the Starbase
DNS record, Certificate, and Ingress; and zero replicas. After merge, success
requires exactly one probe attempt on `asio` or `strix`, all positive and
negative boundary checks, an ExternalDNS-managed DNS answer, a Ready valid TLS
Certificate, expected TLS behavior with an unavailable zero-replica backend,
healthy unrelated workloads, and continued zero Starbase replicas. Any
unexpected egress, Secret access, retry, placement, route, certificate failure,
dependency degradation, or loss of observation is a stop.

## Stage 9 edge and network-boundary acceptance

Al McKay merged the initial edge activation as PR #84 at
`main@sha1:1e3f02e2`, the CA-path correction as PR #86 at
`main@sha1:f7709517`, and the authenticated API-probe correction as PR #87 at
`main@sha1:0e5f5667174b31bfc3bf41af6ac77ce7412950c2`. The first two immutable
Jobs failed once on `asio` as recorded above. Core and both live connectors
remained at zero throughout, and Flux retained the fail-closed foundation
condition until the corrected revision became eligible.

Flux allowed the prior 25-minute health-check window to expire rather than
being manually reconciled. It then applied the exact PR #87 merge revision.
The final Job `starbase-network-boundary-v1-c804f51209e6` started at
`2026-08-26T01:30:10Z` and completed at `2026-08-26T01:30:18Z`. It ran once on
preferred node `asio`, exited 0, had zero restarts and no failed attempt, and
retained only `PASS: Starbase core network and RBAC boundary verified` in its
log. Independent authorization checks confirmed that the core ServiceAccount
could read `/openid/v1/jwks` and could not list Secrets in `starbase-system`.

After completion, all five Flux Kustomizations were Ready at the exact merge
revision. The Kubernetes API readiness check passed. Authentik server and
worker were Available with zero restarts, PostgreSQL remained 2/2 Ready with
zero restarts on `strix`, and no pod was outside Running or Succeeded. All four
nodes were Ready. `asio` used approximately 3% CPU / 29% memory and `strix` 5%
CPU / 18% memory; the inactive `starbase-system` workloads requested no CPU or
memory against the 500m / 512Mi namespace request quotas.

The Certificate was Ready and valid from `2026-08-26T00:01:47Z` through
`2026-11-24T00:01:46Z`. DNS returned the four current Kubani Tailscale node
addresses, the Ingress routed only `starbase.almckay.io` to the browser Service,
and public HTTPS returned the expected HTTP/2 `503` while the backend remained
at zero replicas. Core, GitHub connector, and Kubernetes connector desired zero
replicas. Prometheus and Grafana also remained intentionally scaled to zero;
their absence is not counted as telemetry success. Recent Warning events
retained the two failed probe attempts and the expected timeout transition, but
no current unhealthy pod or unexplained Starbase warning remained.

All Stage 9 acceptance invariants passed without imperative reconciliation or
rollback. This permits the separately reviewed Phase 5 synthetic-preview
candidate to proceed to review. It does not authorize core activation, start
the 24-hour preview clock, or grant either live connector provider authority.
