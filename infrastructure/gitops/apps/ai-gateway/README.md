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
| 2.1b parameters | `AgentgatewayParameters` for the data plane (its CRD comes from the HelmRelease, so it cannot be in the same apply) | `parameters.yaml` |
| 2.2 models | Per-engine `AgentgatewayBackend`s, the `default` virtual model with failover, backend timeout/retry, the health policy that makes failover trigger, the `/v1/*` `HTTPRoute` | `models.yaml` |
| 2.3 hostname | `ai.almckay.io` Ingress in front of the gateway's data-plane Service (`ai`); also requires the CoreDNS wildcard-rewrite change described in the decision doc | `ingress.yaml` |
| 2.4 benchmark | No new manifest: run the release-process benchmark (gateway path vs broker path) | — |
| 2.5 cutover | No new manifest here: edits the existing `llm*.almckay.io` Ingresses in `apps/vllm/` | — |
| 2.6 traces | OTel export to Alloy once Tempo exists in `monitoring/` | `policy-observability.yaml` |
| AGW-1.7 upgrade | agentgateway 1.5.0 -> 1.7.0 (CRDs, control plane, both data planes). Prerequisite of `agents/` | none here: `ref.tag: v1.5.0` -> `v1.7.0` on both OCIRepositories in `infrastructure/gitops/infrastructure/sources/agentgateway.yaml` (see below) |
| ARP agents | The sandbox-only `agents` Gateway of the Agent Runtime Platform | `- agents/`, then the stages inside `agents/kustomization.yaml` |

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

## Stage AGW-1.7: agentgateway 1.5.0 -> 1.7.0

The Agent Runtime Platform pins agentgateway 1.7.0 (spec 3.1: control plane,
data plane and CRDs move together). The version lives in the two
OCIRepositories in `infrastructure/gitops/infrastructure/sources/agentgateway.yaml`,
so this stage is a two-line change there (`ref.tag: v1.5.0` -> `v1.7.0` on
`agentgateway-crds` and `agentgateway`), committed on its own, before any
`agents/` stage. **It upgrades the live `ai` Gateway too**: the same
control plane re-renders the `ai` data plane, which rolls.

Checked offline on 2026-10-30 against the v1.7.0 module source
(`proxy.golang.org`, `controller/install/helm`):

- Every `agentgateway.dev` object this directory renders today (19 objects:
  backends, policies, parameters) validates against the v1.7.0 CRD schemas
  with unknown fields treated as errors (CEL rules not evaluated).
- Every chart value in `helmrelease.yaml` still exists in v1.7.0. New
  defaults: `agentgatewayModels.enabled` is now `true` (this repo sets
  `false`, unchanged), `xBackend.enabled: false`, `istio.enabled: true`
  (RBAC for ServiceEntry/WorkloadEntry only; no Istio CRDs here).
- The data-plane Service/pod naming and labels (`app.kubernetes.io/name`,
  `gateway.networking.k8s.io/gateway-name` = Gateway name) are unchanged, so
  `ingress*.yaml` and the netpols still select the right pods.
- 1.7.0 is built against Gateway API v1.7.0-rc.3; the cluster's Gateway API
  CRDs are v1.4.0 (k3s traefik-crd). Confirm 1.7.0 supports 1.4.0 (release
  notes / supported-versions page) before merging; if it needs >= 1.5, the
  Gateway API CRDs move first.

Re-test after the upgrade, on the `ai` Gateway:

- `kubectl get gateway,httproute,agentgatewaybackend,agentgatewaypolicy -n ai-gateway`:
  every object Accepted/Programmed, no new status errors.
- `ai.almckay.io`, `llm.almckay.io`, `llm-fast.almckay.io`,
  `embeddings.almckay.io`: `/v1/models`, a chat completion, a legacy
  completion, an embedding; the `default` group still fails over to fast
  while main sleeps (429 from the broker).
- `mcp.almckay.io/{kubernetes,graphiti,postgres,github}/mcp`: Authentik OAuth
  discovery (`/.well-known/oauth-*`), `tools/list` shows only the allowed
  tools, one allowed and one denied `tools/call`, GitHub PAT injection.
- Traces still reach Tempo; Prometheus `agentgateway` job targets up;
  "shared-gateway regression check" from
  `docs/infrastructure/operations/releases/2026-10-17-mcp-gateway.md`
  (no new 4xx/5xx on `agentgateway_requests_total`).
- Spec 14.4: after `agents/` is live, T1, T6, T7, T12 as well.

Rollback: revert the tag change; the HelmRelease `rollback` block restores
the previous release.

## `agents/`: the Agent Runtime Platform gateway

A second Gateway (`agents`, HTTPS 443, fixed ClusterIP 10.43.250.10, internal
CA) on the same control plane, reachable only from tenant sandboxes. It does
not modify any file above. Stages, prerequisites and the pending changes
outside this directory are in `agents/kustomization.yaml`.
