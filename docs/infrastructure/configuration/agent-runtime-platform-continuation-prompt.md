Continue work on the Agent Runtime Platform in /home/al/git/kubani. Work in a
git worktree or isolated checkout; preserve every local branch, untracked file
and older /tmp workspace. Fetch origin/main first; local main may be behind.

Rules that hold between sessions are in .claude/rules/agent-platform.md. Read
it before anything else; it settles the release gates, live-operation limits,
decisions not to reopen, and that broad functional qualification is PAUSED.

Then establish state from the cluster, not from prose:

    just agent state      # Flux, platform pods, Agents, releases, sandboxes, open PRs
    just agent ls         # the release each agent would run

Then read, in this order, for in-flight work and history:
- docs/infrastructure/configuration/agent-operations.md (just agent ls/run/sync/stage/approve)
- docs/infrastructure/configuration/agent-runtime-platform-session-handoff-2026-11-08.md
  (current checkpoint; its "2026-11-09 update" lists what changed since)
- docs/infrastructure/configuration/agent-onboarding-preflight.md
- docs/infrastructure/configuration/mcp-backend-registry.md
- docs/infrastructure/configuration/db-admin-deployment-notes.md

Private /tmp receipts cited there may be absent in a new environment; do not
invent missing evidence or call an unobserved result passed.

Use gh and KUBECONFIG=/home/al/.kube/config. Use narrow sub-agents in isolated
checkouts for independent work; one primary owner handles live operations,
merges and serial release publication. Merges, releases and separate
AgentRelease approvals remain authorized only after the gates in the rules file
hold; `just agent approve` enforces them.

No next implementation item is selected. Summarize the state briefly, then
agree the next shared deployment or design improvement with the user rather
than resuming the paused qualification backlog.
