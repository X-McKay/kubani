# ai-gateway (agentgateway) — staged, not wired into Flux

NOT WIRED INTO FLUX. Enable stage by stage per
`docs/infrastructure/configuration/ai-gateway.md`, which is the routing
decision (roadmap 2.0) this directory implements.

The Flux sources (`infrastructure/gitops/infrastructure/sources/agentgateway.yaml`)
are already listed in that directory's kustomization, so the chart artifacts
are pulled and ready. Nothing in this directory reaches the cluster until a
maintainer adds `- ai-gateway/` to
`infrastructure/gitops/apps/kustomization.yaml`. That is a one-line,
reversible edit; until it lands, everything here is inert YAML.

## Verified 2026-09-30

Every manifest was checked against the pulled `v1.5.0` charts
(`helm pull oci://cr.agentgateway.dev/charts/{agentgateway-crds,agentgateway}`),
their CRD schemas, the controller's embedded proxy chart, and
`helm template` with this repo's values. The remaining runtime check at 2.1
is `kubectl get svc,pods -n ai-gateway --show-labels` to confirm the `ai`
Service and the proxy pod labels the deployer produces.

Gateway API: the cluster's v1.4.0 CRDs (k3s `traefik-crd`) are inside
agentgateway 1.5.x's supported range (1.4-1.6). No CRD change is needed.

## Stage-to-file map

| Stage | What it does | Files to uncomment in `kustomization.yaml` |
|---|---|---|
| 2.1 install | Namespace, Flux-managed agentgateway CRDs + control plane, the `ai` Gateway with no routes, the netpols on both sides | `namespace.yaml`, `helmrelease.yaml`, `gateway.yaml`, `netpol-ai-gateway.yaml`, `netpol-vllm-from-gateway.yaml` (already uncommented: these five are the 2.1 set) |
| 2.2 models | Per-engine `AgentgatewayBackend`s, the `default` virtual model with failover, backend timeout/retry, the health policy that makes failover trigger, the `/v1/*` `HTTPRoute` | `models.yaml` |
| 2.3 hostname | `ai.almckay.io` Ingress in front of the gateway's data-plane Service (`ai`); also requires the CoreDNS wildcard-rewrite change described in the decision doc | `ingress.yaml` |
| 2.4 benchmark | No new manifest: run the release-process benchmark (gateway path vs broker path) | — |
| 2.5 cutover | No new manifest here: edits the existing `llm*.almckay.io` Ingresses in `apps/vllm/` | — |
| 2.6 traces | OTel export to Alloy once Tempo exists in `monitoring/` | `policy-observability.yaml` |

Enabling a stage is: uncomment its line(s) in `kustomization.yaml`, run
`just validate-local`, commit with the stage number in the message, push,
watch the ring/gate/soak from roadmap section 9.4 before moving to the next
line.

## What's staged here

- `namespace.yaml`: `ai-gateway`, PSA warn/audit restricted.
- `helmrelease.yaml`: two Flux `HelmRelease`s via `chartRef` to the OCI
  sources: `agentgateway-crds` (its own CRDs, never the Gateway API CRDs)
  and `agentgateway` (control plane, rig0, PSA-restricted, RBAC write scope
  limited to this namespace). Tag `v1.5.0`.
- `gateway.yaml`: the `ai` `Gateway` (HTTP listener, port 80 only; TLS stays
  on Traefik) plus an `AgentgatewayParameters` for the data-plane proxy's
  resources and placement. No `GatewayClass` manifest: the controller creates
  `agentgateway` at runtime.
- `models.yaml`: `AgentgatewayBackend`s for `llm-main`, `llm-fast`,
  `embeddings`, and the `default` failover virtual model, plus the health,
  timeout, and retry `AgentgatewayPolicy`s and the `/v1/*` `HTTPRoute`.
- `policy-observability.yaml`: OTel trace export policy for stage 2.6.
  Prometheus metrics need no policy (data plane on 15020, control plane on
  9092; the `agentgateway` scrape job already exists in
  `apps/monitoring/prometheus-helmrelease.yaml`).
- `ingress.yaml`: `ai.almckay.io` to the gateway's data-plane Service `ai`.
- `netpol-ai-gateway.yaml`: this namespace's default-deny/allow set. Data
  plane selected by `gateway.networking.k8s.io/gateway-name: ai`, control
  plane by `app.kubernetes.io/name: agentgateway`.
- `netpol-vllm-from-gateway.yaml`: the one cross-namespace rule: allow
  ingress in namespace `vllm` from `ai-gateway` to the gpu-broker pods on
  port 8080.
- `keys/README.md`: placeholder; Phase 3 keys go through
  `just gateway-key` into SOPS, never here as plaintext.
