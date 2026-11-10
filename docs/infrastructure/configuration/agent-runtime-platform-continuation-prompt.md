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
- Main heads before this revision: kubani 2daf551c (#415), zetra 677a2dec
  (#78), zetra-agents 1b69fb08 (#39), zetra-template 855310de (#10).
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
  b2f4d57 image. kubani #415 (2daf551c) moved the runner, the cleanup
  reconciler and the conformance Jobs to the 541e2ef image on 2026-11-10; the
  governed A/B workers keep their pins. One `just agent run db-admin` session
  completed on the new runner with confirmed cleanup, which is a deployment
  check and not qualification. Do not revert that pin while a session is in
  flight: a runner built before #76 cannot decode the preflight result the new
  one records, and the session would stop making progress.
- zetra #77 (ebd32904) makes `zetra-agents check` hold deploy/agent.yaml to the
  Agent CRD schema, and zetra #78 (677a2dec) makes a bare `pytest` at the root
  of an agent repository run every agent's tests. A zetra change reaches an
  agent repository only when that repository re-pins zetra; zetra-agents (#39)
  and zetra-template (#10) are pinned at 677a2dec. The re-pin changed
  zetra-agents' uv.lock, so the next release of any agent records a new
  lockSha256.
- kubani #374 (Alice-only delegation consolidation) is open and awaits the
  user's decision; the rules file says so.
- On 2026-11-10 the user selected two items, in this order: a supported path
  from a person's consented delegation to a grant handle `just agent run` can
  use, then building and signing platform images in CI. Open pull requests and
  docs/plans say how far each has got.
- Larger open items, not selected: the plaintext Temporal frontend route, a
  Registry Controller dry-run negative test, the storage backup target.

Use gh and KUBECONFIG=/home/al/.kube/config. Use narrow sub-agents in isolated
checkouts for independent work; one primary owner handles live operations,
merges and serial release publication. Merges, releases and separate
AgentRelease approvals remain authorized only after the gates in the rules file
hold; `just agent approve` enforces them.

Summarize the state briefly, continue the two selected items where they
stand, and agree anything beyond them with the user rather than resuming the
paused qualification backlog.
