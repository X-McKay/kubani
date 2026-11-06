Continue the Agent Runtime Platform rollout in /home/al/git/kubani (GitHub org
X-McKay; sibling repos zetra, zetra-agents, kubani-gpu-broker).

Read docs/infrastructure/configuration/agent-runtime-platform-session-handoff-2026-11-06.md
FIRST, then its linked sibling checkpoint files, the spec, and qualification docs.
The handoff is newer than the general handoff and /tmp/phase-b-next/ROOT-PICKUP.md.
Preserve unfinished/untracked work; inventory current branches and cluster state.

Use Sol sub-agents to parallelize independent work in a cost-effective manner
where possible. Prefer gpt-6.1-sol with narrow, self-contained tasks and isolated
checkouts; use fresh-context forks when selecting the model. Avoid duplicate
research/full-suite runs. Keep one primary owner for live operations, merges,
deployments and serial release tags. Ask agents to checkpoint findings clearly.

Goal: complete implementation and honest end-to-end qualification, not just make
individual test labels pass. T26 and runs10–12 docs are already complete. The
current homelab checklist has16 remaining items:14 conformance gates (T2,T27,T28,
T29,T12,T13,T14,T21,T23,T24,T10a,T10,T16,T18), Worker Versioning, and final integrated
regression/documentation signoff. T2 includes the T2b measurement. Enterprise and
per-agent T30 certification are additional scope.

I authorize necessary PR merges, image releases, and separate AgentRelease
approvals after signature/all-five-attestations/NoDrift verification. Use gh,
KUBECONFIG=/home/al/.kube/config, SOPS-only secrets, and never rollout restart
Flux-managed workloads. Publish agent tags one at a time. No secrets from Pods,
privileged Pods, raw token output, or guard weakening. Ask before any new vLLM
engine/broker downtime. Brokers are retained and T6/T7 already pass.

I explicitly approved optional delegation:client on agent-cli and two separate
Users/delegate grants limited to synthetic Alice for
agent-tenant-test-conformance and agent-tenant-test-conformance-lifecycle.
Do not re-ask for this exact authorization. Apply partially created the scope,
but failed protocolMappers verification; scope is not attached and neither actor
policy/permission exists. Diagnose normalization, retain strict semantics, verify
then mint directly to SOPS files. Read the handoff before retrying.

I deferred host T2a/T27 terminal work for a few hours. Continue independent work;
do not restart capture automatically. This session's no_new_privs blocked sudo.
I will run reviewed host commands later; coordinate a terminal-ready marker
BEFORE launching a new held-sandbox test. Never bypass via privileged containers.
T21's conflict with confirmed deletion remains an explicit contract decision.

Recent evidence: run28 T17PASS18/18; run29 T23FAIL due stateless-MCP handshake
fanout (zetraPR63 fix ready); run30 T13ERROR because Python Kubernetes client
rewrote single-JSON logs (kubaniPR361 fixed/merged); run31 T27ERROR with no capture,
normal cleanup and additional evaluator/classifier issues. Preserve all failures.
No qualification Job/sandbox is active; APS was two Ready replicas. Read the
handoff for current pins, open PRs, retry2 preparation, uv cache contamination,
unfinished T2/T29/versioning code and exact supporting evidence paths.

Proceed autonomously within these authorizations. Start with a short status
update, verify the saved state, and execute the highest-value independent work.
