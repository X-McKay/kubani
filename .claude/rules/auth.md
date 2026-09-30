---
paths:
  - infrastructure/gitops/**/*
  - docs/infrastructure/configuration/**
---

# Auth Rules

How a client authenticates to a Kubani service is decided by what kind of
client it is and what surface it's hitting, not by habit or by what the last
service did. Pick the row, don't invent a new mechanism.

## Auth decision table

| Client | Surface | Mechanism | Where configured |
|---|---|---|---|
| Human in a browser | Admin UI (Grafana, Qdrant, FalkorDB, Temporal) | Authentik: native OIDC if supported, else Traefik forwardAuth via blueprint | Authentik blueprints in `apps/authentik/` |
| Human in a browser | AI gateway UI/API | Authentik OIDC, JWT policy on the gateway listener, groups to CEL authorization | `AgentgatewayPolicy` |
| Agent / service | LLM API (`ai.almckay.io`, `llm*.almckay.io`) | Gateway virtual key with token budget; one key per agent or workstream; SOPS-stored | gateway policy + `.enc.yaml` |
| Agent / service | MCP servers | Gateway OAuth with Authentik as provider; per-tool authorization | `AgentgatewayPolicy`, Authentik provider blueprint |
| Service to service inside the cluster | Any | NetworkPolicy plus the service's native auth; never the human SSO | netpol + app config |
| TCP protocols (Postgres, Redis, FalkorDB) | Databases | Private network and native credentials; tailnet ACL is the outer layer | SOPS secrets, Tailscale ACL |

Full context and the per-service examples (Grafana, Temporal, FalkorDB,
Qdrant) live in
`docs/infrastructure/configuration/authentik-app-access.md`. This table is
the quick-reference version; when they disagree, the doc is the source of
truth and this file should be updated to match.

## Rules

- **Never a key in a ConfigMap, a manifest, or a commit.** Gateway virtual
  keys, API keys, and OIDC client secrets are SOPS `.enc.yaml` only — the
  same rule as every other credential (`.claude/rules/secrets.md`). A key
  that only ever needs to exist inside the cluster still goes through SOPS;
  "it's just for one agent" is not an exception.
- **Rotation follows `.claude/rules/secrets.md` step 6**: after rotating a
  gateway key or an OIDC client secret, restart the consuming workload.
  Env vars sourced from `secretKeyRef` do not hot-reload — Flux updating the
  Secret alone leaves the old value live in the running pod.
- **Every new hostname gets a row in the auth inventory** in
  `docs/infrastructure/configuration/authentik-app-access.md` (hostname, the
  decision-table row it uses, the Authentik application or gateway key name,
  rotation date). A hostname without an inventory row is drift, and
  `just drift` checks the inventory against live Ingresses and gateway
  policies.
- **The tailnet ACL is the outer layer.** Every mechanism above assumes
  `*.almckay.io` is reachable only over the tailnet (see
  `.claude/CLAUDE.md` invariants); it is not a substitute for per-surface
  auth, but it is what keeps a misconfigured or not-yet-authenticated
  service from being internet-reachable in the meantime.
- Adding a model, MCP backend, or agent identity behind the gateway: follow
  `.claude/skills/gateway-onboard/SKILL.md`. Adding or changing an Authentik
  application: follow `.claude/skills/authentik-app/SKILL.md`.
