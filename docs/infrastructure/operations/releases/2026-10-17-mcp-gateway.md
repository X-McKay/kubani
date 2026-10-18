# 2026-10-17 MCP servers behind agentgateway

**Status:** in progress. M0 released 2026-10-17 23:34Z; M1 released
2026-10-18 00:35Z (gate passed 00:37Z); M2 (Kubernetes MCP) next
**Profile:** gateway
**Scope:** agentgateway (`ai-gateway`), new `mcp` namespace, Authentik
(`auth` network policy now; blueprint in M1), rig0 node label
**Window:** no downtime expected. Each step adds new objects; the existing
LLM routes on `ai.almckay.io` are only re-checked, never changed.

Plan: `docs/plans/ideas/2026-10-17-mcp-gateway-openshell-tetragon.md`,
section 2 (design and per-PR gates) and section 6 (testing and rollback).
One record covers M0 to M5; each step adds its own section below.

## Why
Give agents and Claude Code a single authenticated entry point
(`mcp.almckay.io`) to read-only Kubernetes, Graphiti, Postgres and GitHub
tools, with Authentik groups deciding who can call which tool.

## Rollout rules
Al shortened the soak on 2026-10-17: readings at T+15 min and T+1 h after
each step, then the next step, instead of 24 h. Stop and roll back on a
failed gate, an LLM-route regression, or a node over its memory ceiling.

**Shared-gateway regression check**, after every step: no new 4xx/5xx on
`agentgateway_requests_total`, and the gateway pods Ready with no restarts.
Baseline (24 h before M0): 12 requests, all 200; zero 400/404/502.

## M0: `mcp` namespace and network paths

| | Before | After |
|---|---|---|
| Namespaces | none | `mcp` (PSA `restricted`, default-deny ingress, DNS-only egress) |
| `ai-gateway` egress | LLM backends | + `mcp` pods on 8000/8080/8082, + Authentik server :9000 (JWKS) |
| `auth` ingress | existing | + from the `ai-gateway` data plane to the Authentik server :9000 |
| rig0 label | none | `topology.kubani.io/role=platform` (inventory, applied with `kubectl label`) |

**Rollback SHA:** `6a94426ad0aaa4dd6d85665a774bcf8191f3c311` (main before
M0). Rollback is `git revert -m 1 <M0 merge>`; nothing is left behind
(plan 6.2).
The rig0 label is harmless on its own and is removed with
`kubectl label node rig0 topology.kubani.io/role-` only if M2+ are reverted
too.

**Gate:**
- `just validate-local` before merge.
- After reconcile: `apps` Kustomization Ready, `kubectl get ns mcp` shows
  `pod-security.kubernetes.io/enforce=restricted`, the three network
  policies exist.
- Shared-gateway regression check above.

## M1: Authentik provider, groups and `mcp.almckay.io`

| | Before | After |
|---|---|---|
| Authentik | no MCP objects | blueprint `kubani-mcp.yaml`: groups `mcp-users`, `mcp-admin`, `mcp-agents`; public PKCE provider "Kubani agentgateway MCP" (`client_id: kubani-agentgateway-mcp`, grant types set explicitly, localhost callback regexes); application `agentgateway-mcp` bound to the three groups |
| Ingress | none | `mcp.almckay.io` to the `ai` data plane, certificate `mcp-tls` from `letsencrypt-prod`. The gateway answers 404 for it until M2 adds routes |

**Accepted risk (Al, 2026-10-17):** Authentik does not force PKCE on public
clients; a code without a challenge is accepted. Exploiting it needs a client
that skips PKCE (Claude Code and the MCP SDKs always send S256) and a second
local process that captures the loopback callback, which could already read
that client's tokens. Revisit before agents use any other OAuth client.

**Rollback SHA:** `1599e292d5c5d34421572b1d7ca51295bd97de7e` (main before
the M1 merge).
Rollback is **not** a plain revert: Authentik blueprints do not delete
objects that disappear from a blueprint. Revert in two steps:
1. A PR that sets `state: absent` on every entry of `kubani-mcp.yaml`, then
   confirm in Authentik that the provider, application and groups are gone.
2. A PR that removes the `kubani-mcp.yaml` key and the Ingress.

**Gate:**
- The blueprint instance `Kubani - MCP gateway` shows status `successful`
  in Authentik (Admin > Customization > Blueprints), and no other blueprint
  changes status.
- `https://auth.almckay.io/application/o/agentgateway-mcp/.well-known/openid-configuration`
  returns the discovery document, with `issuer` equal to
  `https://auth.almckay.io/application/o/agentgateway-mcp/` (the value M2's
  policy will check).
- `/application/o/agentgateway-mcp/jwks/` returns a key set.
- Certificate `mcp-tls` Ready; `https://mcp.almckay.io/` answers 404 from
  the gateway (not a TLS or Traefik error).
- Authentik regression: an existing login (Grafana) still works, and
  `authentik-server` and `authentik-worker` have no new restarts.
- Shared-gateway regression check above.

**Gate result (2026-10-18 00:37Z): PASS.** Blueprint `successful`; the
blueprints already in error before M1 are unchanged. Discovery `issuer` and
JWKS (RS256) as expected. `mcp-tls` Ready at 00:35Z; `mcp.almckay.io`
resolves and answers 404, counted by `agentgateway_requests_total`, so it is
the gateway answering. Grafana's OAuth redirect still reaches the Authentik
login flow; `authentik-server`, `authentik-worker` and the gateway pods have
0 restarts; gateway status counts show only 200s besides the two probe 404s.

## M2: Kubernetes MCP server

| | Before | After |
|---|---|---|
| `mcp` namespace | empty | `kubernetes-mcp` Deployment and Service on rig0 (`read_only`, ServiceAccount bound to cluster `view`) |
| `ai-gateway` | no MCP routes | AgentgatewayBackend, HTTPRoute (`/kubernetes/mcp` and its two `.well-known` paths on `mcp.almckay.io`) and AgentgatewayPolicy (Authentik JWT, read-tool allow-list for `mcp-users`/`mcp-agents`) |
| `auth` | none | ReferenceGrant letting the policy read the `authentik-server` JWKS |

**Capacity:** +50m / 64Mi requests on rig0 (ledger updated).

**Rollback SHA:** main before the M2 merge (recorded at merge). Rollback is
`git revert -m 1 <M2 merge>`; the backend, route, policy, grant and the
`view` binding all go with it (plan 6.2).

**Gate (plan 2.2):**
- `apps` Kustomization Ready; the AgentgatewayPolicy and HTTPRoute status
  conditions Accepted/ResolvedRefs (an unresolved JWKS ref 401s everything).
- `kubernetes-mcp` pod Ready on rig0, 0 restarts.
- Unauthenticated `POST /kubernetes/mcp` returns 401 with
  `WWW-Authenticate` pointing at the protected-resource metadata, and that
  metadata URL answers.
- Needs Al: `claude mcp add --transport http kubernetes
  https://mcp.almckay.io/kubernetes/mcp` completes the browser login, then
  `tools/list` shows only the allow-listed tools and listing pods works. A
  user outside `mcp-users` gets 403.
- Shared-gateway regression check above.

## Resource readings
| Step | T+15 min | T+1 h |
|---|---|---|
| M0 | PASS (23:48Z): no gateway requests in the window, no restarts in `ai-gateway` or `auth`, `mcp` policies present | PASS (00:33Z): 40 gateway requests since M0, all 200; no restarts; all pods Ready |
| M1 | | |
| M2 | | |

## Decision
<kept / reverted, and why>
