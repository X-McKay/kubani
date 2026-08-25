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
| SOPS credentials | passed | PR #69 merged as `6b97be2d`; Flux owns the exact five Secrets and all consumers remain inactive |
| Authentik integration | partially passed | PR #70 merged as `345986db`; blueprint/discovery verification passed and Al McKay verified member-visible Starbase; denied-non-member behavior remains a hard pre-bootstrap gate |
| Database bootstrap | candidate; blocked from merge | logging, backup, health, capacity, and absence preflight passed at `2026-08-25T18:54Z`; denied-non-member evidence and exact-revision go/no-go remain required |
| Migrations | blocked | successful database bootstrap required |
| Ingress and core | blocked | migrations, identity, network probes, and go/no-go required |
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
reported that Starbase is visible in Authentik. This closes the member-visible
application-policy check. The available operator browser session was no longer
authenticated when the denial exercise was attempted, so denied-non-member
behavior has **not** been claimed. It remains a hard pre-merge gate for Stage 6;
membership must be restored and reconfirmed immediately after that bounded
exercise. The Starbase-side group denial, callback, token, session, expiry, and
logout checks remain correctly deferred until DNS, TLS, Ingress, and core exist.

## Stage 6 database-bootstrap candidate

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

Merge remains blocked until denied-non-member Authentik behavior is witnessed,
fresh checks reproduce this baseline, CI is green, and Al McKay gives the
exact-revision Stage 6 go/no-go. After merge, stop on any unexpected placement,
retry, log content, ownership, role, grant, health, capacity, or Flux result.
Rollback after partial execution is not merely a Git revert: keep workloads and
migrations inactive, preserve evidence, and use the reviewed Starbase-only
database/role cleanup path or forward repair according to the observed state.
