---
paths:
  - infrastructure/gitops/apps/agents/**/*
  - infrastructure/gitops/apps/agent-platform/**/*
  - infrastructure/gitops/infrastructure/kyverno/**/*
  - infrastructure/scripts/ops/agent*
  - infrastructure/scripts/ops/agent_ops/**/*
  - docs/infrastructure/configuration/agent-*
---

# Agent Runtime Platform Rules

The durable operating contract for the agent platform. Session handoffs under
`docs/infrastructure/configuration/agent-runtime-platform-session-handoff-*.md`
record *state*; this file records what stays true between sessions. When a
handoff and this file disagree about a rule, this file wins and the handoff
needs a fix.

## Start of a session

1. `just agent state` for Flux, platform pods, Agents, releases, sandboxes and
   open PRs.
2. `just agent ls` for the release each agent would run.
3. Read the newest session handoff for in-flight work. Older handoffs and the
   `/tmp` evidence they cite are historical; if a receipt is absent, say so
   rather than reconstructing it.

Broad functional qualification is **paused**. Do not resume fault campaigns,
host capture, versioning promotion or benchmarks because an older plan lists
them as next. The user picks the next item.

## Releases

- The lifecycle is `just agent register` once per source repository, then per
  change `just agent sync`, a source tag, `just agent stage`, a PR, Flux,
  `just agent approve`, a separate PR. See
  [agent operations](../../docs/infrastructure/configuration/agent-operations.md).
- A tenant's signer pin is derived from the sync headers of its committed
  Agents (one branch per source repository, bound to its own agents) and
  `check-sync` fails when either copy drifts; never hand-edit it. Every
  source repository, monorepo or one-agent, uses `agents/<name>/` and
  `<agent>/vX.Y.Z` tags. On the workspace layout `lockSha256` is the
  repository's `uv.lock`; releases built before it are verified against
  `agents/<agent>/uv.lock`, and `stage` picks by what exists at `buildRevision`.
- Approval requires, on the live object: a verified signature from the agent's
  own `release.yml` tag, all five attestations, `PolicyDrift=False` with
  `NoDrift`, a digest equal to `policySha256`, and `Ready=False` solely for
  `NotApproved`. `just agent approve` refuses otherwise; never hand-edit the
  approval block to get past it.
- Publish release tags one at a time, from merged source. Staging and approval
  are separate PRs.
- Never weaken a check, raise a budget, widen a grant or add a fixture-name
  exception to obtain a pass. Deterministic agents declare `model: null` and
  `capabilities.models: []`; that grants no inference route.
- Historical AgentReleases, failed reports and spent ledgers stay. Do not
  delete, relabel or reuse them.

## Live operations

- Read with `KUBECONFIG=/home/al/.kube/config`. Direct writes are expected only
  in `tenant-*`, `agent-platform`, `auth` and `temporal`
  (`.claude/rules/kubernetes.md`).
- Never `kubectl rollout restart` a Flux-managed workload. Exact Pod deletion
  only when the situation calls for it.
- Ask before any vLLM engine or broker downtime. Brokers stay retained.
- Never read Secrets from Pods, print tokens, decrypt without need, or commit
  private reports. Secrets are SOPS `.enc.yaml` only.
- Do not bypass the environment's sudo restriction with privileged containers.
- Ordinary sessions go through `just agent run`; it uses the tenant's Session
  Runner and never applies objects. A completed run is a deployment check, not
  qualification.

## Settled decisions (do not reopen)

- T21: confirmed deletion before replacement; stale-token fencing and blocked
  deletion are tested separately (Kubani #371).
- The original Alice delegation fixtures were approved and applied. The
  Alice-only consolidation in Kubani #374 is a different change awaiting its
  own decision.
- Kubani #380 merged helper source only, not authority to mint another actor.
- Worker Versioning follows the reviewed distinct-queue migration, not #359's
  same-queue promotion. Retained workers and history stay.
- Automatic approval-review rejections on older T23/T29/T21/digest/run34
  payloads stand; never route around a rejection.

## Workspaces

- Work in an isolated checkout or worktree; never reset `/home/al/git/kubani`
  or clean older `/tmp` workspaces, some hold the only copy of unfinished code.
- Use a fresh `UV_CACHE_DIR` and `UV_LINK_MODE=copy` for SDK tests.
- Prefer narrow sub-agents in isolated checkouts for independent work; one
  primary owner handles live operations, merges and serial releases.
