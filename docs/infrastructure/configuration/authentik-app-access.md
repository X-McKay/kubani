# Authentik App Access Pattern

This note captures the preferred Authentik pattern for apps exposed by the Kubani homelab cluster.

## Preferred Split

- Use native OIDC when the application supports it well.
- Use Traefik `forwardAuth` with Authentik for HTTP admin UIs that do not need native SSO.
- Manage Authentik proxy providers, applications, and outpost assignments with
  mounted Authentik blueprints.
- Keep non-HTTP protocols and service-to-service APIs on their own auth model and restrict them to internal or tailnet access.

## Current Examples

- Grafana already uses native Authentik OIDC.
- Temporal Web uses native OIDC with Authentik.
- FalkorDB Browser uses Traefik `forwardAuth` with Authentik.
- Qdrant's HTTP ingress uses Traefik `forwardAuth` with Authentik.
- Prometheus is not part of the current Authentik app-access surface while the
  monitoring stack remains scaled down.

Native OIDC and Traefik `forwardAuth` should be the default patterns for future apps.

## Authentik Blueprints

- Proxy-backed apps must be added to
  `infrastructure/gitops/apps/authentik/blueprints-configmap.yaml`.
- The Authentik HelmRelease mounts `authentik-blueprints` through
  `values.blueprints.configMaps`, and Authentik instantiates blueprints labeled
  `blueprints.goauthentik.io/instantiate: "true"`.
- Do not attach `authentik-auth@kubernetescrd` to an Ingress until the matching
  proxy provider and outpost assignment are present in the blueprint.
- Keep the Traefik middleware as a transport integration only. The application,
  provider, external host, internal host, and outpost membership belong in
  Authentik.
- A mounted blueprint is not automatically undone by removing its ConfigMap
  key. First reconcile a reviewed `state: absent` blueprint in dependency
  order, verify the objects and discovery endpoint are gone, then remove the
  file in a follow-up cleanup revision.

## Temporal

- Use Temporal Web's native OIDC integration with Authentik.
- Do not add Traefik `forwardAuth` in front of Temporal Web unless the Authentik
  proxy provider and outpost assignment are managed and validated first.
- Keep the OIDC provider URL on `https://auth.almckay.io` so issuer, browser
  redirects, and TLS names match.

## FalkorDB

- Protect the Browser UI on `falkordb.almckay.io` with Traefik `forwardAuth`.
- The Authentik proxy provider is `Kubani FalkorDB Browser`, with external host
  `https://falkordb.almckay.io` and internal host
  `http://falkordb.database.svc.cluster.local:3000`.
- Do not treat RESP on port `6380` as something Authentik can protect through Traefik HTTP middleware.
- Keep RESP private to the cluster or tailnet unless there is a strong reason to expose it.

FalkorDB is a Redis module, so its wire protocol authenticates with
`requirepass` only — there is no native SSO to fall back on. Ingress-level
protection of the Browser UI plus a strong generated password on the RESP port
is the practical posture.

## Qdrant

- Keep Qdrant's native API-key authentication for API and SDK traffic.
- The external HTTP ingress is protected with Authentik `forwardAuth` for browser access.
- The Authentik proxy provider is `Kubani Qdrant`, with external host
  `https://qdrant.almckay.io` and internal host
  `http://qdrant.database.svc.cluster.local:6333`.
- Do not use Authentik as a replacement for the Qdrant API key.

Qdrant's documented self-hosted security model is API key plus TLS, not full native OIDC.

## Decision table

Six rows, covering the AI edge (gateway, MCP) as well as the existing
browser/API/TCP split. Pick the row that matches a new service's client and
surface, record the choice in the service's `auth.md`
(`infrastructure/gitops/_templates/service/auth.md`), and add it to the
[auth inventory](#auth-inventory) below once the Ingress is live.

| Client | Surface | Mechanism | Where configured |
|---|---|---|---|
| Human in a browser | Admin UI (Grafana, Qdrant, FalkorDB, Temporal) | Authentik: native OIDC if supported, else Traefik forwardAuth via blueprint | Authentik blueprints in `apps/authentik/` |
| Human in a browser | AI gateway UI/API | Authentik OIDC, JWT policy on the gateway listener, groups to CEL authorization | `AgentgatewayPolicy` |
| Agent / service | LLM API (`ai.almckay.io`, `llm*.almckay.io`) | Gateway virtual key with token budget; one key per agent or workstream; SOPS-stored | gateway policy + `.enc.yaml` |
| Agent / service | MCP servers | Gateway OAuth with Authentik as provider; per-tool authorization | `AgentgatewayPolicy`, Authentik provider blueprint |
| Service to service inside the cluster | Any | NetworkPolicy plus the service's native auth; never the human SSO | netpol + app config |
| TCP protocols (Postgres, Redis, FalkorDB) | Databases | Private network and native credentials; tailnet ACL is the outer layer | SOPS secrets, Tailscale ACL |

The last two rows describe what already exists (`vllm`, `database`, `cache`
namespaces); the gateway rows apply once agentgateway lands in Phase 2/3 of
`docs/plans/ideas/2026-09-29-inference-platform-roadmap.md`.

## Auth inventory

Every hostname that exists, the decision-table row it uses, and what
implements that row. Checked against live Ingresses by `just drift`
(advisory — a hostname `just drift` cannot match to a manifest is reported,
not blocked). Planned rows are marked as such and have no live Ingress yet.

| Hostname | Row | Authentik application or gateway key | Last rotated | Notes |
|---|---|---|---|---|
| `grafana.almckay.io` | Human / admin UI | native OIDC, application `grafana` (provider `Kubani Grafana`, blueprint, `grant_types` set explicitly) | 2026-10-01 | `disable_login_form` is currently `false` — see [Grafana](#grafana) below |
| `prometheus.almckay.io` | Human in a browser, admin UI | Traefik forwardAuth, Authentik application `prometheus` (provider `Kubani Prometheus`, blueprint) | 2026-10-01 | Prometheus has no auth of its own |
| `qdrant.almckay.io` | Human / admin UI (HTTP ingress) + Service API (native key) | forwardAuth, Authentik application `Kubani Qdrant` | — | RESP-equivalent API traffic keeps its own API key regardless of the forwardAuth layer |
| `falkordb.almckay.io` | Human / admin UI | forwardAuth, Authentik application `Kubani FalkorDB Browser` | — | RESP port `6380` is not behind Traefik; see [FalkorDB](#falkordb) above |
| `temporal.almckay.io` | Human / admin UI | native OIDC | — | issuer pinned to `https://auth.almckay.io` |
| `auth.almckay.io` | n/a | Authentik itself | — | identity provider; see [Authentik version pin](#authentik-version-pin) |
| `llm.almckay.io`, `llm-fast.almckay.io`, `embeddings.almckay.io` | Agent / service, LLM API | none today | n/a | Tailnet-only mitigates; move to gateway virtual keys in Phase 2/3 per roadmap section 1 goal 2 |
| `registry.almckay.io` | Service API | Traefik basic auth (`registry-basic-auth` middleware), not Authentik | — | see `infrastructure/gitops/infrastructure/registry/middleware.yaml`; out of scope for the Authentik decision table today |
| `ntfy.almckay.io` | API clients (phone app, Alertmanager bridge) | ntfy native auth from the `ntfy-auth` Secret: user `al` (admin), user `alertmanager` with a write-only token on `kubani-*`, default access deny-all | 2026-10-01 | Phase 0.2 (roadmap); still tailnet-only; rotation via `ONLY_NTFY=1 make_integration_secrets.sh` (operations/pending-secrets.md) |
| `ai.almckay.io` | Human / browser + Agent / service, AI gateway | planned: Authentik OIDC (humans) + gateway virtual keys (agents) | n/a | **Planned, Phase 2.** No Ingress exists yet |
| `mcp` subdomain (Phase 4, planned) | Agent / service, MCP servers | planned: gateway OAuth with Authentik as provider | n/a | **Planned, Phase 4.** No Ingress exists yet |

Every non-planned hostname above has a matching `Ingress` under
`infrastructure/gitops/`; check
`infrastructure/gitops/apps/monitoring/prometheus-ingress.yaml`,
`infrastructure/gitops/infrastructure/qdrant/ingress.yaml`,
`infrastructure/gitops/infrastructure/falkordb/ingress.yaml`,
`infrastructure/gitops/apps/temporal/ingress.yaml`,
`infrastructure/gitops/apps/authentik/ingress.yaml`,
`infrastructure/gitops/apps/vllm/{ingress,fast-model-ingress,embeddings-ingress}.yaml`,
and `infrastructure/gitops/infrastructure/registry/ingress.yaml`.

## Rotation runbook

- **Gateway virtual keys**: `just gateway-key <name>` generates the key,
  encrypts it with SOPS into the gateway's secret, and prints the kustomize
  line to add. One key per agent or workstream — never a shared key.
- **OIDC client secrets** (Grafana, Temporal): rotate in Authentik's admin
  UI, update the corresponding `.enc.yaml` secret (see
  `docs/infrastructure/configuration/secrets.md` and
  `.claude/rules/secrets.md`), commit, and reconcile.
- **Every rotation ends with step 6 of the secrets rule**: restart the
  consuming workload. Environment variables sourced from `secretKeyRef` do
  not hot-reload — Flux updating the `Secret` alone leaves the old value
  live in the running pod until it restarts.
- Record the rotation date in the [auth inventory](#auth-inventory)'s "Last
  rotated" column.

## Grafana

Grafana uses the existing `oauth-secret.enc.yaml`
(`infrastructure/gitops/apps/monitoring/oauth-secret.enc.yaml`) with an
Authentik OIDC provider managed by blueprint — no local admin login is
meant to be exposed. `disable_login_form` in
`grafana-helmrelease.yaml` is currently `false`, so the local login form is
still reachable alongside OIDC. Tightening that (`disable_login_form:
true`) is a follow-up, not yet done.

## Tailnet ACL as the outer layer

What is known: every `*.almckay.io` hostname resolves via Cloudflare to
Traefik's ServiceLB on the Tailscale IPs of the cluster nodes, so every
service in this table is reachable only from the tailnet regardless of
whatever HTTP-layer auth sits in front of it (see invariant 1 in
`docs/plans/ideas/2026-09-29-inference-platform-roadmap.md` section 3).
That makes the tailnet ACL the true outer layer for everything in this
document, including the hosts marked "none today."

What is not known: which devices on the tailnet should reach which ports.
This question was raised and left open in the May 2026 audit
(`docs/plans/ideas/2026-05-09-audit-followup.md`) and is still open. The
operator decision required is whether to move from "any tailnet device
reaches any `*.almckay.io` host" to a scoped ACL that limits, for example,
which devices can reach `registry.almckay.io`'s push path or the database
hostnames directly. This document does not propose an ACL, because no ACL
has been decided — it only states that the decision is still pending and
where it is tracked (roadmap Phase 5.4).

## Authentik version pin

Authentik is pinned to `2026.5.6`; the upstream migration blocker and the
full upgrade/recovery plan are in
[`docs/infrastructure/operations/authentik-upgrade.md`](../operations/authentik-upgrade.md).
Phase 3 of the roadmap (gateway OIDC, agent identities) uses this pinned
version's OIDC support, which is sufficient for both the human-login and
groups-to-CEL-authorization use cases — no upgrade is required to start
Phase 3.

## Validation

After changing Authentik proxy blueprints:

```bash
flux reconcile helmrelease authentik -n auth
kubectl rollout status deployment/authentik-worker -n auth
```

Unauthenticated browser routes should redirect to Authentik login, not return an
outpost 404:

```bash
curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://falkordb.almckay.io/
curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://qdrant.almckay.io/
```
