# AI Gateway Routing Decision (roadmap 2.0)

This is the routing decision for
`docs/plans/ideas/2026-09-29-inference-platform-roadmap.md` Phase 2
(agentgateway). It blocks the install (2.1) and exists to avoid ending up
with three things trying to route the same traffic. The staged, not-yet-wired
manifests that implement it live in
`infrastructure/gitops/apps/ai-gateway/` (see that directory's `README.md`
for the stage-to-file map) and
`infrastructure/gitops/infrastructure/sources/agentgateway.yaml`.

## Decision

- **Gateway API is the model for AI traffic.** New hostnames that front LLM
  backends (`ai.almckay.io` now, `llm*.almckay.io` and `embeddings.almckay.io`
  after the 2.5 cutover) are reached through a Kubernetes `Gateway` +
  `HTTPRoute`, not a plain Traefik `Ingress`.
- **agentgateway owns its own `GatewayClass`** (`agentgateway`, controller
  `agentgateway.dev/agentgateway`). It is the only controller that reconciles
  Gateway API objects in this cluster.
- **Traefik keeps doing exactly what it does today for every other hostname:
  `Ingress` plus TLS termination.** `ai.almckay.io` is still a Traefik
  `Ingress` (cert-manager `letsencrypt-prod`, external-dns Cloudflare
  `policy: sync`, same as every other hostname) — Traefik terminates TLS and
  forwards to the gateway's data-plane `ClusterIP` `Service` over plain HTTP
  inside the cluster. Traefik's Gateway API provider stays off
  (`--providers.kubernetescrd` and `--providers.kubernetesingress` only, per
  the cluster facts this decision was written against); it never reconciles
  a `Gateway`.
- **The Gateway API CRDs stay owned by the k3s-bundled `traefik-crd`
  HelmChart.** Their version is pinned by k3s, not by this repo or by
  agentgateway's chart.

## The three-router problem, and why this avoids it

Three things could plausibly want to own "how AI traffic gets routed" here:

1. Traefik's existing `Ingress` path (`--providers.kubernetesingress`).
2. Traefik's Gateway API provider, if it were ever turned on
   (`--providers.kubernetesgateway` — not enabled today).
3. agentgateway's own `GatewayClass`/`Gateway` reconciliation.

If (2) were ever turned on alongside (3), both Traefik and agentgateway would
watch and reconcile the same `Gateway`/`HTTPRoute` objects — two controllers
racing to set `status`, attach listeners, and own the data plane for the
same resources. That is the failure mode this decision heads off: Traefik's
Gateway API provider is never enabled in this cluster. The boundary stays
clean because it is drawn by *traffic type*, not by hostname pattern: Traefik
owns `Ingress` + TLS for everything, unconditionally; agentgateway owns
`Gateway`/`HTTPRoute` for AI traffic, unconditionally. `ai.almckay.io` sits
at the seam — a Traefik `Ingress` whose backend happens to be a Gateway API
data plane instead of an application `Service` — which is an ordinary
Traefik backend from Traefik's point of view, not a second router.

## Gateway API version compatibility (resolved 2026-09-30)

agentgateway publishes a support matrix
(<https://agentgateway.dev/docs/kubernetes/main/reference/versions/>):
**agentgateway 1.5.x supports Gateway API 1.4 through 1.6** and Kubernetes
1.32 through 1.37. This cluster runs Kubernetes v1.34.7 with Gateway API
CRDs **v1.4.0** (standard channel, owned by the k3s-bundled `traefik-crd`
HelmChart). Both are inside the supported range, so **no CRD upgrade is
needed for stage 2.1**. The `v1.6.0` in the install guide is what its
copy-paste command pins, not a minimum.

Two consequences:

- The Gateway API CRDs stay owned by k3s. Nothing in this repo applies or
  bumps them; a k3s upgrade that ships newer Traefik CRDs is the only path
  that changes them, and the matrix says 1.5 and 1.6 remain supported.
- Everything agentgateway needs from Gateway API for this rollout
  (`Gateway`, `HTTPRoute`, `ReferenceGrant`) has been `v1` since Gateway
  API 1.0.

What was verified against the charts and CRDs themselves (pulled from
`oci://cr.agentgateway.dev/charts`, tag `v1.5.0`):

- Two OCI charts, `agentgateway-crds` and `agentgateway`, chart version
  `v1.5.0` (the tag carries the `v`). The CRDs chart puts its four CRDs
  (`AgentgatewayBackend`, `AgentgatewayModel`, `AgentgatewayParameters`,
  `AgentgatewayPolicy`) under `templates/`, so they upgrade like ordinary
  resources and Flux's `install.crds` setting does not apply.
- The control-plane chart accepts `resources`, `nodeSelector`,
  `podSecurityContext`, `securityContext` at the top level; `helm template`
  with this repo's values renders a single `agentgateway` Deployment with the
  expected placement and security context, and a Service on 9978/9093/9092.
  Controller pods are labelled `app.kubernetes.io/name: agentgateway`.
- The `agentgateway` GatewayClass is created by the controller at runtime,
  not by the chart.
- The deployer names the data-plane Deployment and Service after the
  Gateway, labels proxy pods `gateway.networking.k8s.io/gateway-name` and
  `.../gateway-class-name`, annotates them for Prometheus on port 15020, and
  runs the `agentgateway` container as uid 10101 with a read-only root.
- `AgentgatewayParameters` has typed `resources`, `image`, `env`, `logging`,
  `workload`, `service`; placement and pod security context are
  strategic-merge overlays under `deployment.spec`.
- `AgentgatewayBackend.spec.ai.provider` takes `openai.model` plus `host`,
  `port`, `path`/`pathPrefix`; `spec.ai.groups[].providers[]` is the
  priority-ordered failover form.
- `AgentgatewayPolicy` has `traffic.timeouts.request`, `traffic.retry`
  (`attempts`, `codes`, `backoff`, CEL `condition`/`precondition`),
  `backend.health` (`unhealthyCondition` CEL, `eviction`), and
  `frontend.tracing` (`url`, `protocol` GRPC|HTTP, `randomSampling`).
- Flux references OCI charts through `HelmRelease.spec.chartRef` pointing at
  an `OCIRepository` with a Helm-chart `layerSelector`, not through
  `spec.chart.spec.sourceRef`.

## What the broker keeps doing

The gpu-broker services (`llm-api`, `fast-model-api` in namespace `vllm`,
`embeddings-api` once its Deployment is scaled up) keep doing sleep/wake
exactly as they do today. Every `AgentgatewayBackend` in `models.yaml` points
at the broker `Service`, never at the raw engine `Service`
(`llm-engine`/`fast-model-engine`) — the gateway is a client of the broker,
same as Traefik is today, and the broker's wake-up latency and admin API are
unaffected.

The broker's own multi-engine routing phase (from
`docs/plans/active/2026-08-16-vllm-gpu-sleep-wake-broker.md`) is shelved:
agentgateway's failover/priority-group mechanism
(`AgentgatewayBackend.spec.ai.groups`, roadmap 2.2) now owns "route to main,
fail over to fast" at the gateway layer, one layer up from the broker. The
broker stays scoped to what only it can do — sleep/wake a single engine
behind a stable `Service` name — and stops growing a second routing
implementation that would duplicate what the gateway now does.

## Shadow-hostname rollout (roadmap 9.4)

| Stage | What happens | Nothing points at it yet? |
|---|---|---|
| 2.1 install | `Gateway` exists, no `HTTPRoute`s | Yes — control plane up, `rig0` memory within the 9.2 ledger, existing Ingresses/Traefik unaffected |
| 2.2 | `AgentgatewayBackend`s + the `default` failover virtual model + the `/v1/*` `HTTPRoute` exist | Yes — `ai.almckay.io` DNS does not exist yet (no Ingress) |
| 2.3 | `ai.almckay.io` Ingress exists; CoreDNS wildcard extended (below) | **No longer shadow** — real completions can be sent through it, but `llm*.almckay.io` keep serving production traffic unchanged until 2.5 |
| 2.4 benchmark | Gateway path vs broker path, same scenarios, gate at WARN | — |
| 2.5 cutover | Existing `llm.almckay.io`/`llm-fast.almckay.io`/`embeddings.almckay.io` `Ingress`es swap their backend `Service` to the gateway's data-plane `Service`, one hostname at a time; API keys issued first | — |
| 2.6 traces | Tempo added to `monitoring/`; gateway exports OTel spans to Alloy | — |

2.2 and 2.3 together are the "shadow hostname" ring from roadmap 9.4: by the
end of 2.3, `ai.almckay.io` is a real, working endpoint that nothing
production depends on yet, so it can absorb the 7-day soak and the failover
test (scale `gpu-broker-main` to 0 for a minute) without any blast radius on
`llm.almckay.io`.

## Stage-enable steps

Each step is a single-line, reversible edit. In order:

| Stage | File | Change |
|---|---|---|
| 2.1 | `infrastructure/gitops/infrastructure/sources/kustomization.yaml` | add `- agentgateway.yaml` |
| 2.1 | `infrastructure/gitops/apps/kustomization.yaml` | add `- ai-gateway/` |
| 2.1 | `infrastructure/gitops/apps/ai-gateway/kustomization.yaml` | already uncommented (`namespace.yaml`, `helmrelease.yaml`, `gateway.yaml`, `netpol-ai-gateway.yaml`, `netpol-vllm-from-gateway.yaml`) |
| 2.2 | `infrastructure/gitops/apps/ai-gateway/kustomization.yaml` | uncomment `- models.yaml` |
| 2.3 | `infrastructure/gitops/apps/ai-gateway/kustomization.yaml` | uncomment `- ingress.yaml` |
| 2.3 | `infrastructure/gitops/infrastructure/networking/coredns-split-horizon.yaml` | see below |
| 2.6 | `infrastructure/gitops/apps/ai-gateway/kustomization.yaml` | uncomment `- policy-observability.yaml` |

2.4 and 2.5 do not add files from this directory: 2.4 is a benchmark run, and
2.5 edits the existing `apps/vllm/{ingress,fast-model-ingress,embeddings-ingress}.yaml`
backend `Service` names, which belongs to whoever owns that cutover and is
out of this task's scope.

## CoreDNS wildcard rewrite (2.3 — not applied now)

`infrastructure/gitops/infrastructure/networking/coredns-split-horizon.yaml`
today rewrites only `auth.almckay.io` in-cluster:

```
data:
  almckay-split-horizon.override: |
    rewrite name exact auth.almckay.io traefik.kube-system.svc.cluster.local
```

At 2.3, add one more `rewrite name exact` line for the new hostname, the same
shape as the existing one:

```
    rewrite name exact ai.almckay.io traefik.kube-system.svc.cluster.local
```

Deliberately **not** the file's documented wildcard-regex alternative
(`rewrite name regex (.*)\.almckay\.io traefik.kube-system.svc.cluster.local`):
that would also rewrite `llm*.almckay.io` and `embeddings.almckay.io` for
in-cluster consumers before those hostnames actually move behind the gateway
at 2.5, which is not this stage's job. Revisit the wildcard form once 2.5 is
done and every `*.almckay.io` host in active use resolves to Traefik anyway.

## Traces (roadmap 2.6)

`policy-observability.yaml`'s `AgentgatewayPolicy` makes the `ai` Gateway's
data plane export an OTel span for every request it proxies, sent to
`alloy.monitoring.svc.cluster.local:4317`. Alloy's `otelcol.receiver.otlp`
component (`apps/monitoring/alloy-helmrelease.yaml`) forwards them through a
batch processor to Tempo (`apps/monitoring/tempo-helmrelease.yaml`, 3-day
retention on Longhorn). Spans carry the OpenTelemetry GenAI semantic
convention attributes (model, token counts, latency) agentgateway sets by
default — no toggle to enable them.

To find a request's spans: Grafana, **Explore**, select the **Tempo**
datasource, search by service name (the gateway's service name, not a model
name) or paste a trace ID. The Tempo datasource's `tracesToLogsV2` config
jumps from a span to the matching window of Loki logs, so a slow or failed
request's trace and its engine/broker log lines are one click apart.

## Phase 3 hooks (forward references, not built yet)

- **Authentik OIDC JWT policy** on the `ai.almckay.io` listener (roadmap 3.1):
  agentgateway's `AgentgatewayPolicy` CRD carries the auth/authorization
  policies that would attach here — groups to CEL authorization per the auth
  decision table in `docs/infrastructure/configuration/authentik-app-access.md`
  (section 10.5 of the roadmap extends that table with the AI-edge rows).
  Nothing in this directory configures it; `keys/README.md` and this doc are
  the only Phase 3 surface staged so far.
- **Virtual keys / API-key auth** (roadmap 3.2): agentgateway's built-in
  API-key auth matches a request's `Authorization` header against either
  Kubernetes `Secret`s (by label selector) or a `ConfigMap` of SHA-256 key
  hashes, both referenced from an `AgentgatewayPolicy`. Per-key token
  budgets are a separate "virtual keys" feature
  (`agentgateway.dev/docs/kubernetes/main/llm/cost-controls/virtual-keys/`).
  Real keys are generated and SOPS-encrypted by `just gateway-key <name>`
  (roadmap 10.2) directly into `infrastructure/gitops/apps/ai-gateway/keys/`
  as `.enc.yaml` — never as plaintext, never in this doc.

## URLs consulted

- <https://agentgateway.dev/docs/kubernetes/latest/install/helm/>
- <https://agentgateway.dev/docs/kubernetes/main/quickstart/install/>
- <https://agentgateway.dev/docs/kubernetes/1.0.x/install/flux/>
- <https://agentgateway.dev/docs/kubernetes/latest/reference/helm/agentgateway/>
- <https://agentgateway.dev/docs/kubernetes/main/about/architecture/>
- <https://agentgateway.dev/docs/kubernetes/main/llm/providers/openai/>
- <https://agentgateway.dev/docs/kubernetes/latest/llm/failover/>
- <https://agentgateway.dev/docs/kubernetes/latest/resiliency/timeouts/request/>
- <https://agentgateway.dev/docs/kubernetes/latest/resiliency/retry/retry/>
- <https://agentgateway.dev/docs/kubernetes/latest/observability/metrics/dataplane/>
- <https://agentgateway.dev/docs/standalone/main/integrations/observability/opentelemetry/>
- <https://agentgateway.dev/docs/kubernetes/1.0.x/security/extauth/apikey/>
- <https://agentgateway.dev/docs/kubernetes/main/llm/cost-controls/virtual-keys/>
- <https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.0/standard-install.yaml> (referenced, not fetched)

## Open items for the maintainer

- The staged manifests were checked against the pulled charts and CRD
  schemas on 2026-09-30; the remaining runtime check at 2.1 is
  `kubectl get svc,pods -n ai-gateway --show-labels` to confirm the `ai`
  Service and pod labels the deployer produced.
