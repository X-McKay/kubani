# Inactive governed worker templates

These `.yaml.in` files are outside every active Kustomization. They cannot create
workers or change policy in the cluster. The renderer emits zero-replica
Deployments and six exact role/pool NetworkPolicies into a new output directory.
It never applies them, scales them, promotes a Temporal version or updates a
Schedule. Legacy worker manifests and selectors remain intact.

Use only a published runner built from merged source containing
[zetra PR67](https://github.com/X-McKay/zetra/pull/67), after verifying the installed
modules equal that source. Do not reuse the existing ce7c06b image: its worker
ignores WORKER_POOL and polls legacy queues even with a different deployment name.
The renderer refuses that known digest, moving tags, all-zero digests, incomplete
commits, unresolved markers and overwriting existing output. Other image/source
pairs still require independent publication/installed-source verification; format
validation does not prove provenance.

```sh
python infrastructure/scripts/ops/render-worker-versions.py \
  --runner-image 'registry.almckay.io/platform/session-runner@sha256:ACTUAL_PUBLISHED_DIGEST' \
  --source-commit ACTUAL_FULL_MERGED_COMMIT \
  --output /tmp/worker-versions-reviewed
kubectl kustomize /tmp/worker-versions-reviewed
```

The example placeholders intentionally fail validation. Root owns release and
review of concrete rendered manifests before adding them to Flux. Keep replicas
zero during pin/signature/source review; starting the candidate and promotion are
separate reviewed rollout steps. No existing resource must be removed or renamed.

Temporal deployment names are stable per role/pool; Kubernetes Deployment names
append `b-<12 source hex>` and their immutable selectors include app, tenant,
role, pool and build. New app names differ from legacy app names, so the old
Deployment selectors cannot adopt new Pods. Existing ServiceAccounts, certificate
and payload-key projections, APS token audience and security settings are reused.
The new workers poll only the governed queues; their start does not change the
legacy cleanup Schedule.

The session worker shares the existing write-once artifact PVC. Longhorn RWO
allows multiple Pods on one node; required Pod affinity places it with the retained
legacy session worker. This preserves old artifacts but requires that legacy Pod
to be available for initial scheduling. Confirm actual same-node mounts and
concurrent artifact behavior before promotion. Moving to another node or removing
the legacy worker requires a separate storage/scheduling change; do not solve it
by deleting the retained PVC or old histories.

The NetPol additions preserve legacy policies. Each governed role gets API-server,
APS and exact Temporal mTLS endpoint egress, APS ingress and cross-namespace
Temporal ingress; inherited namespace DNS/default-deny still apply. No broad
app-name `In` list or common worker label is added to an old Deployment selector.
Actual cluster enforcement and exact current-worker discovery remain rollout gates.
