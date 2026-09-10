# Starbase2 bounded autonomous observation

Dedicated installation: `starbase2-prod`, owned only by the existing apps Flux
Kustomization. PostgreSQL database `starbase2_prod`, separate owner/application
roles, Temporal namespace `starbase2-prod`, queue `starbase2-prod-v1`.

The initial disposable acceptance is complete. Current scope adds read-only field
observations and bounded advisory reasoning. Memory, repairs and legacy commands
remain disabled. This does not qualify the platform backup/restore gate.

LLM advice is explicitly enabled at `https://llm.almckay.io/v1`, model
`Qwen3.6-35B-A3B-NVFP4`, for the two explicitly scoped field targets and synthetic reviews. Each target
permits at most24 inference admissions per UTC day, separated by at least3600
seconds across day boundaries. Core persists this budget; observations continue
with an explicit skip reason when reasoning is not admitted. After deployment
verification, the operator activates Watchkeeper observations every300 seconds
and repository reviews every900 seconds through Core/Godot; GitOps creates no
duties. Existing unrelated duties stay paused. A pod-local `hostAliases` entry maps only that hostname to
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

Open the native client with `--api=http://127.0.0.1:18787` for all normal operations. The HTTP root is a service status page; the retired
browser dashboard and browser assets are not served. Kubernetes port-forward permission grants operator access. There is
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

## Watchkeeper observation

Target `starbase2-watchkeeper` permits GET pod/deployment observations only in
`starbase2-prod`, with advisory inference under the hourly/daily limits above.
The separately scoped GitHub target is described below.
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

## GitHub repository review

Target `starbase2-github` is restricted to `X-McKay/Starbase2`, uses the GET-only
repository adapter, and permits advisory inference under the same per-target
limits. Watchkeeper remains configured separately. No comment, approval, merge,
or repository write is enabled.

The user-provided dedicated fine-grained token `starbase2-readonly` selects only
that repository with Contents/Pull requests read plus implicit Metadata read,
and expires **2026-12-09**. Operator owns rotation before expiry; otherwise
observations fail closed. SOPS source `github-readonly.enc.yaml` supplies Secret
`starbase2-github-readonly`, key `token`. Only runtime mounts it read-only at
`/var/run/starbase2-github`; Core/init never mount it. No operator gh credential
is reused and no plaintext token is stored in repository files.

Actual worker DNS resolved `api.github.com` to `140.82.112.6` immediately before
this promotion. The pod-local host alias pins that API address to keep the /32
TCP443 egress deterministic; HTTPS hostname validation stays enabled and
redirects stay disabled. There is no broad internet or unverified failover
allowance. If the address stops serving GitHub, re-resolve and verify TLS before
updating both alias and egress in GitOps. Existing LLM routing stays unchanged.

Private PR/source records may enter the trusted adapter and Core evidence store;
the user explicitly authorizes bounded source and findings from this private
repository to reach the configured LLM for advisory reasoning. Treat observations as bounded advisory
review with explicit unsupported-language/truncation coverage limits.
