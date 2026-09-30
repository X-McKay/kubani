---
name: gateway-onboard
description: Use when adding a model or MCP backend behind agentgateway (infrastructure/gitops/apps/ai-gateway/) - issuing a new agent/workstream API key, wiring an AgentgatewayModel or MCP backend, setting a budget, or pointing a new client at ai.almckay.io.
---

# Gateway Onboard

Adding a backend or an agent identity to agentgateway touches the auth
decision table (`.claude/rules/auth.md`) at the "Agent / service" rows:
gateway virtual keys for LLM API clients, gateway OAuth via Authentik for
MCP clients. This skill is the repeated procedure for both.

## Adding a model or MCP backend

1. Define the backend under `infrastructure/gitops/apps/ai-gateway/` — an
   `AgentgatewayModel` pointing at the broker Service (`llm-api`,
   `fast-model-api`, the embeddings Service) for an engine, or an MCP
   backend entry for Phase 4 servers. Reuse existing aliases and the virtual
   model rather than inventing new naming.
2. NetworkPolicy: the gateway's egress to the target Service, and (if this
   is the first backend in a new namespace) the target namespace's ingress
   allow from `ai-gateway`. Every cross-namespace path needs its own pair
   (`.claude/rules/gitops.md`).
3. Backend timeout and retry, and — for an engine backend — the failover
   pairing (main -> fast) per the roadmap's Phase 2 design. Do not remove
   the broker's own sleep/wake; the gateway sits in front of it, it does not
   replace it.

## Issuing an agent identity (virtual key)

1. `just gateway-key <name>` generates a 40-char alphanumeric key and writes
   it straight into `infrastructure/gitops/apps/ai-gateway/keys/<name>.enc.yaml`
   via SOPS — the plaintext never touches the repo or the terminal scrollback
   (the script shreds its staging file). Refuses if `age.key` is missing.
2. Add the kustomization line the script prints, attach a token budget and
   an `AgentgatewayPolicy` (one key per agent or workstream — do not share a
   key across unrelated agents, budgets and revocation both depend on that).
3. Commit only the `.enc.yaml` and the manifest changes. Never paste the key
   value into a commit message, a PR description, or a change record.

## Validate

```bash
curl -s -m 30 https://ai.almckay.io/v1/chat/completions \
  -H "Authorization: Bearer <key>" -H 'Content-Type: application/json' \
  -d '{"model":"<alias>","messages":[{"role":"user","content":"Say OK"}],"max_tokens":5}'
```

A real completion, not a 200 on `/v1/models` — same discipline as the
inference-release skill. If this is an image/flag change to an engine
behind the gateway, also bench through the gateway per the gateway-path
guidance in `.claude/skills/inference-release/SKILL.md`.

## Auth inventory

Add a row to the auth inventory in
`docs/infrastructure/configuration/authentik-app-access.md`: the hostname
(if a new one was added), the decision-table row, the key or application
name, and a rotation date. `just drift` checks this against live Ingresses
and gateway policies.

## Red flags: stop

- A key in a ConfigMap, a manifest, or anywhere outside a `.enc.yaml` — see
  `.claude/rules/auth.md` and `.claude/rules/secrets.md`.
- Benchmarking through the gateway without a broker-path baseline first.
  The gateway's overhead needs to be measured against something; see
  `.claude/skills/inference-release/SKILL.md`'s gateway-path guidance.
- Sharing one virtual key across multiple agents "for now" — budgets and
  revocation stop meaning anything per-agent the moment that happens.
- Wiring a backend without the NetworkPolicy pair — default-deny means it
  silently fails closed instead of loudly.
