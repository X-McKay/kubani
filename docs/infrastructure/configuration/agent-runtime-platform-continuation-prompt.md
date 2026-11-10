Continue work on the Agent Runtime Platform in /home/al/git/kubani. Work in a
git worktree or isolated checkout; preserve every local branch, untracked file
and older /tmp workspace. Fetch origin/main first; local main may be behind.

Rules that hold between sessions are in .claude/rules/agent-platform.md. Read
it before anything else; it settles the release gates, live-operation limits,
decisions not to reopen, and that broad functional qualification is PAUSED.

Then establish state from the cluster, not from prose:

    just agent state      # Flux, platform pods, Agents, releases, sandboxes, Kubani's open PRs
    just agent ls         # the release each agent would run

`just agent state` lists open pull requests in X-McKay/kubani only. List the
others with `gh pr list -R X-McKay/zetra`, `-R X-McKay/zetra-agents` and
`-R X-McKay/zetra-template`.

Then read, in this order, for in-flight work and history:
- docs/infrastructure/configuration/agent-operations.md
  (just agent ls/run/register/sync/stage/approve; "Grant handles" says why an
  agent that requires delegation cannot be run yet)
- docs/plans/ideas/2026-11-09-agent-repo-golden-path.md
  (section 6a is the status of the agent repository work, section 7 the
  newcomer path)
- docs/infrastructure/configuration/agent-runtime-platform-session-handoff-2026-11-08.md
  (checkpoint for the paused qualification work; it and its "2026-11-09 update"
  predate the golden path, so its baseline commits are older than main)
- docs/infrastructure/configuration/agent-onboarding-preflight.md
- docs/infrastructure/configuration/mcp-backend-registry.md
- docs/infrastructure/configuration/db-admin-deployment-notes.md

Private /tmp receipts cited there may be absent in a new environment; do not
invent missing evidence or call an unobserved result passed.

State when this prompt was last revised, 2026-11-10. The commands above and the
pull requests themselves override anything in this list:
- Main heads: kubani eda4fde7 (#413), zetra 541e2ef2 (#76), zetra-agents
  e87022f1 (#38), zetra-template 3174962c (#9).
- Every pull request in the golden path sequence is merged. Its first release,
  investigator v0.1.5 (investigator-2026-11-09-93383f45), is approved and Ready
  beside investigator-2026-11-01-c5dd3a5f, so `just agent run investigator` is
  refused without --release.
- investigator cannot run a session through `just agent run` even with
  --release: both releases require delegation and no supported path produces a
  grant handle. The golden path's closing session check is open for that
  reason.
- zetra #76 (541e2ef2) makes the Session Runner stop a session at the smaller
  of the submitter's limit and the Agent's spec.runtime.maxBoundaries. A runner
  built before it stops at the submitter's limit only, and that includes the
  b2f4d57 image. The pin in
  infrastructure/gitops/apps/agent-platform/workloads/session-runner-tenant-test.yaml
  says which is deployed; the runner, the cleanup reconciler and the
  conformance Jobs move together, and the governed A/B workers keep their pins.
- zetra #77 (ebd32904) makes `zetra-agents check` hold deploy/agent.yaml to the
  Agent CRD schema. It, and anything else merged to zetra after 9d8601c1,
  reaches an agent repository only when that repository re-pins zetra;
  zetra-agents and zetra-template are pinned at 9d8601c1.
- kubani #374 (Alice-only delegation consolidation) is open and awaits the
  user's decision; the rules file says so.
- Larger open items, none selected: the plaintext Temporal frontend route,
  platform image signing, a Registry Controller dry-run negative test, the
  storage backup target.

Use gh and KUBECONFIG=/home/al/.kube/config. Use narrow sub-agents in isolated
checkouts for independent work; one primary owner handles live operations,
merges and serial release publication. Merges, releases and separate
AgentRelease approvals remain authorized only after the gates in the rules file
hold; `just agent approve` enforces them.

No next implementation item is selected. Summarize the state briefly, then
agree the next shared deployment or design improvement with the user rather
than resuming the paused qualification backlog.
