# Starbase2 disposable deployment test

Dedicated installation: `starbase2-prod`, owned only by the existing apps Flux
Kustomization. PostgreSQL database `starbase2_prod`, separate owner/application
roles, Temporal namespace `starbase2-prod`, queue `starbase2-prod-v1`.

The initial acceptance uses only the shipped sample/release workspace. Memory, repairs and legacy commands remain disabled. Test
records are disposable and do not qualify durable production admission or the
platform backup/restore gate. Pause all test duties after acceptance.

LLM advice is explicitly enabled at `https://llm.almckay.io/v1`, model
`Qwen3.6-35B-A3B-NVFP4`, for operator-requested synthetic reviews. Existing
duties remain paused. A pod-local `hostAliases` entry maps only that hostname to
Traefik ClusterIP `10.43.100.136`, preserving TLS hostname validation without node
hairpin, shared DNS changes or broad internet egress. If the Traefik Service is
recreated with a different IP, update this alias and verify worker connectivity
before resuming inference. The Starbase2 network allowance selects only
Traefik pods on TCP8443; standard NetworkPolicy cannot filter HTTPS hostnames,
so the runtime endpoint allowlist remains the application boundary.

Core and worker share pod loopback port18787, preserving the operator's existing
local development service on8787. The port patch preserves Core health checks
and the worker's existing successful-reconciliation heartbeat check, changing
only its endpoint. Operator access:

```sh
kubectl --context default -n starbase2-prod port-forward deployment/starbase2 18787:18787 --address 127.0.0.1
```

Open the native client with `--api=http://127.0.0.1:18787` or use the journal at
that URL. Kubernetes port-forward permission grants operator access. There is
no public Service/Ingress and no automatic workload Kubernetes API token mount.

`worker.enc.yaml` and `database.enc.yaml` are managed by Flux. The encrypted
`migrator.enc.yaml` is retained for explicit migration/recovery and excluded
from Kustomize; neither live container mounts it. Run the migration Job only
with the application stopped and retain failures. Remove its Job and temporary
Secret after successful migration/grants. Do not change shared service identities.

Emergency stop remains available independently of Starbase2: suspend only the
Starbase2 Deployment reconciliation (`kustomize.toolkit.fluxcd.io/reconcile=disabled`)
and scale it to zero, then record matching stopped state through GitOps and
remove that annotation. This uses [Flux resource suspension](https://fluxcd.io/flux/components/kustomize/kustomizations/#suspending-and-resuming).
Do not suspend the shared apps owner. Normal quiesce:
pause duties, drain active work, set admissionfalse then replicas0 through GitOps.
Never replace workers with incompatible images while histories remain open.

## Manual Watchkeeper observation

The only field target is `starbase2-watchkeeper`: GET pod/deployment observations
in `starbase2-prod`, with target inference explicitly false. No GitHub target or
credential and no recurring duty are added. Existing duties remain paused.
The selected API endpoint is `https://100.92.107.71:6443`, verified against the
namespace root CA; egress allows only that endpoint /32 and TCP6443. Revalidate
this pinned route if API endpoints change; there is no unverified fallback.

Role `starbase2-observe` grants only get/list of pods and apps deployments to the
existing `starbase2` ServiceAccount in this namespace. It grants no secrets,
logs, exec, writes, or cross-namespace workloads. Only runtime mounts the
explicit 3600-second projected, pod-bound token and public CA. Kubelet rotates
the token and the adapter rereads it on each capture. Core/init containers do
not mount it; automatic token mounting remains false.

This extends the private-pod trust assumptions deliberately: namespace workload
creators and platform operators can use this ServiceAccount and remain trusted.
Runtime-only mounting limits ordinary exposure; it is not a sandbox between the
trusted containers. Full API objects reach the trusted adapter, while retained
observations omit specs, logs and secrets; the API does not redact those fields.
Memory recall stays disabled; the existing approval ledger endpoint is not
gated by that flag, so this stage does not exercise or claim to disable all
memory operations.
