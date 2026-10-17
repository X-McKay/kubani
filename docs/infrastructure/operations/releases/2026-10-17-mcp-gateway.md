# 2026-10-17 MCP servers behind agentgateway

**Status:** in progress. M0 (namespace and network paths)
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

## Resource readings
| Step | T+15 min | T+1 h |
|---|---|---|
| M0 | | |

## Decision
<kept / reverted, and why>
