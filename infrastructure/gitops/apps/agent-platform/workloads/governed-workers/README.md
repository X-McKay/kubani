# Governed A/B workers: retained candidates

All four Deployments are configured with one replica after the separate reviewed
zero-replica staging step. They poll only their distinct governed queues. Starting
these candidates does not promote a Temporal version or route the legacy cleanup
Schedule; root performs those guarded operations separately under the
[live qualification plan](../../../../../../docs/plans/2026-11-06-worker-versioning-live-qualification.md).
Legacy workers, image pins and histories remain retained. Worker readiness alone
does not qualify routing, storage concurrency, replay, rollback or retention.

| Version | Merged source prefix | Build ID | Matching source/installed module receipts |
| --- | --- | --- | --- |
| A | 9c2c092 | b-9c2c0928b226 | 38 entries |
| B | b2f4d57 | b-b2f4d578cb72 | 40 entries |

Full source commits are pinned in each Deployment annotation, and exact published
RepoDigests in its container image field. Root supplied verified release pins;
this staging work independently compared the existing source/installed JSON hash
dictionaries for equality at `/tmp/runtime-resume-evidence/runner-{9c2c092,b2f4d57}-{source,installed}-hashes.json`.
It did not pull, rebuild, republish or deploy an image. Receipt equality does not
replace root's release/source verification or later actual Pod imageID checks.

The merged renderer generated both variants into isolated local directories.
The committed Deployment data differs from those zero-replica outputs only in
the separately reviewed one-replica startup setting; explanatory comments differ. Fourteen exact scanner-baseline additions mark only the two
public source commits and existing TLS/payload Secret object names as non-secrets;
all earlier baseline entries, plugins, filters and security hooks remain unchanged. New app names differ from
legacy app names; exact immutable selectors also include tenant, role, pool and
build, so A/B and legacy controllers cannot adopt one another's Pods. Temporal
role deployment names stay stable within governed-v1, while Kubernetes Deployment
names are build-specific. Explicit WORKER_POOL/BUILD_ID/DEPLOYMENT settings select
only the disjoint governed queues. Legacy queues, workers and histories stay.

Shared six-role policy additions live once in `../../netpol-governed-workers.yaml`
and the app Kustomization, not once per build. They grant both governed roles'
API/APS/Temporal paths and the corresponding ingress halves without broadening
old selectors. Existing namespace DNS/default-deny rules still apply. The stage
Kustomization contains exactly four Deployments and no operator Job or RBAC.

Both session workers project the existing write-once artifact PVC and require
same-node Pod affinity with the retained legacy runner, preserving Longhorn RWO
constraints. Cleanup workers retain their existing emptyDir artifact behavior.
Actual concurrent mounts/write-once behavior, API enforcement, fresh Workflow and
Activity pollers, source/Pod UID stability, replay/drain/rollback, future cleanup
cadence and seven-day query/retention evidence remain later root qualification.

The optional B operator was rendered locally only at
`/tmp/runtime-resume-versioning/stage-b-verified-local-operator/operator.yaml`.
It is absent from this directory, all committed resources and all Flux
Kustomizations; root may review/use it separately after final image/source and
exact Job/Pod binding checks. Neither local render was applied.
