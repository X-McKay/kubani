# ai-gateway (agentgateway) — staged, not wired into Flux

NOT WIRED INTO FLUX. Enable stage by stage per
`docs/infrastructure/configuration/ai-gateway.md`, which is the routing
decision (roadmap 2.0) this directory implements. Read it before enabling
anything here — it also carries the Gateway API version finding that blocks
stage 2.1 today.

Nothing here reaches the cluster until a maintainer does two things
deliberately:

1. Add `- agentgateway.yaml` to
   `infrastructure/gitops/infrastructure/sources/kustomization.yaml` (that
   file lists its resources explicitly, so the new source file sits present
   but unused until then).
2. Add `- ai-gateway/` to `infrastructure/gitops/apps/kustomization.yaml`.

Both are one-line, reversible edits. Until they land, `agentgateway.yaml` and
everything in this directory is inert YAML that Flux never sees.

## Stage-to-file map

| Stage | What it does | Files to uncomment in `kustomization.yaml` |
|---|---|---|
| 2.1 install | Namespace, Flux-managed agentgateway CRDs + control plane, the `ai` Gateway with no routes, the netpols on both sides | `namespace.yaml`, `helmrelease.yaml`, `gateway.yaml`, `netpol-ai-gateway.yaml`, `netpol-vllm-from-gateway.yaml` (already uncommented — these five are the 2.1 set) |
| 2.2 models | Per-engine `AgentgatewayBackend`s, the `default` virtual model with failover, backend timeout/retry, the health policy that makes failover actually trigger, the `/v1/*` `HTTPRoute` | `models.yaml` |
| 2.3 hostname | `ai.almckay.io` Ingress in front of the gateway's data-plane Service; also requires the CoreDNS wildcard-rewrite change described in the decision doc (edited separately, not staged in this directory) | `ingress.yaml` |
| 2.4 benchmark | No new manifest — run the release-process benchmark (gateway path vs broker path) before touching anything else | — |
| 2.5 cutover | No new manifest here — this stage edits the existing `llm.almckay.io` / `llm-fast.almckay.io` / `embeddings.almckay.io` Ingresses in `apps/vllm/`, which is out of this task's scope | — |
| 2.6 traces | OTel export to Alloy once Tempo exists in `monitoring/` | `policy-observability.yaml` |

Enabling a stage is: uncomment its line(s) in `kustomization.yaml`, run
`just validate-local`, commit with the stage number in the message, push,
watch the ring/gate/soak from roadmap section 9.4 before moving to the next
line.

## What's staged here

- `namespace.yaml` — `ai-gateway`, PSA warn/audit restricted.
- `helmrelease.yaml` — two Flux `HelmRelease`s: `agentgateway-crds` (its own
  CRDs — `AgentgatewayBackend`, `AgentgatewayPolicy`, `AgentgatewayParameters`
  — never the Gateway API CRDs) and `agentgateway` (control plane). Pinned to
  chart `1.5.0`.
- `gateway.yaml` — the `ai` `Gateway` (HTTP listener, port 80 only; TLS stays
  on Traefik) plus an `AgentgatewayParameters` for the data-plane proxy's
  resources/nodeSelector. No `GatewayClass` manifest: the chart creates
  `agentgateway` itself.
- `models.yaml` — `AgentgatewayBackend`s for `llm-main`, `llm-fast`,
  `embeddings`, and the `default` failover virtual model, plus the health,
  timeout, and retry `AgentgatewayPolicy`s and the `/v1/*` `HTTPRoute`.
- `policy-observability.yaml` — OTel trace export policy for stage 2.6.
  Prometheus metrics need no policy (on by default on port 15020).
- `ingress.yaml` — `ai.almckay.io` → the gateway's data-plane Service.
- `netpol-ai-gateway.yaml` — this namespace's default-deny/allow set.
- `netpol-vllm-from-gateway.yaml` — the one cross-namespace edit this task
  makes outside `ai-gateway/`: an allow-ingress rule in namespace `vllm` for
  traffic from `ai-gateway` to the gpu-broker pods on port 8080. `vllm`'s own
  NetworkPolicy file (`infrastructure/gitops/infrastructure/networking/netpol-vllm.yaml`)
  belongs to another workstream and is not touched.
- `keys/README.md` — placeholder; Phase 3 keys go through SOPS, never here
  as plaintext.

## Why nothing can be enabled yet

The Gateway API CRDs agentgateway 1.5.x's install docs apply are v1.6.0
(standard channel). This cluster's Gateway API CRDs are v1.4.0, owned by the
k3s-bundled `traefik-crd` HelmChart (`helm.sh/resource-policy: keep`,
version pinned by k3s). See
`docs/infrastructure/configuration/ai-gateway.md` for the full finding and
what resolving it will take — that is a prerequisite to stage 2.1, tracked
there rather than solved by this staging pass.

Every `# VERIFY:` comment in this directory's YAML marks a field that could
not be confirmed against a literal example during this research pass (the
CRD schemas are only checkable once installed) — check each one with
`helm template` and `kubectl explain` at 2.1 time before applying anything.
