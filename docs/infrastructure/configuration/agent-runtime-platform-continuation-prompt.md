Continue work in /home/al/git/kubani, preserving all local branches and untracked
work. The original local main may be old; inspect/fetch origin/main and use an
isolated checkout instead of resetting the original workspace.

First read the latest origin/main versions of:
- docs/infrastructure/configuration/agent-runtime-platform-session-handoff-2026-11-08.md
- docs/infrastructure/configuration/agent-onboarding-preflight.md
- docs/infrastructure/configuration/mcp-backend-registry.md
- docs/infrastructure/configuration/db-admin-deployment-notes.md

The November 8 handoff supersedes current-state claims in the November 6 handoff.
Read its referenced checkpoint files before touching older unfinished work.
Private /tmp receipts may be absent elsewhere; do not invent missing evidence.

Use narrow gpt-6.1-sol sub-agents in isolated checkouts, avoid duplicate full
testing, and keep one primary owner for live operations and serial releases.
Use gh and KUBECONFIG=/home/al/.kube/config. Necessary merges/releases and separate
AgentRelease approvals remain authorized after signature, all five attestations
and NoDrift verification. Publish agent tags one at a time.

Latest completed work: all 13 agents pass actual offline generic preflight.
Model-free lifecycle/performance/transport fixtures have signed replacements,
separately approved and Ready (Kubani #402/#403, zetra-agents #35). Runner MTU
correction #401 is deployed. The registry, encrypted credential preparation,
bounded session CLI and generic preflight are implemented. Do not repeat these
releases or describe the old 6/13 or 10/13 matrices as current blockers.

Broad functional qualifications remain PAUSED. Host T2a/T27 capture is deferred.
T21's contract is decided: confirmed deletion before replacement, with stale-token
fencing and blocked-deletion tests separate. Preserve historical failures and
spent ledgers; never weaken checks. Do not bypass sudo restrictions with privileged
containers. Ask before new vLLM engine/broker downtime; brokers stay retained.
Never rollout restart Flux-managed workloads; use exact Pod deletion only when
appropriate. Keep secrets SOPS-encrypted; never print tokens or read Pod secrets.

Original exact Alice delegation fixtures were approved and later applied; do not
re-ask for those. Open #374's different consolidation proposal and older publication
holds are not silently resolved by this prompt. Read the new handoff before acting.

Start by verifying saved repository/live state and briefly summarizing progress.
No next implementation item is selected: prioritize shared deployment/design
improvements with the user rather than automatically resuming qualification.
