# Agent SOPs and repository standards

- **Date:** 2026-09-09
- **Status:** active, PR 1 of 5 in flight
- **Owner:** Al McKay
- **Origin:** repository audit and the Starbase `.agents/skills` review, 2026-09-08

## Goal

One set of standards and procedures that both Claude Code and Codex follow,
that a checker enforces where it can, and that future work extends instead of
re-deriving. The measure of success: a new agent session, given a task, finds
the routing table, reads one standard and one skill, runs named `just`
recipes, and hands off with the evidence table this repo now expects.

## Decisions recorded

1. **Tool-neutral.** `AGENTS.md` is the charter. `CLAUDE.md` imports it and
   holds only Claude-specific notes. Skills live in `.agents/skills/<name>/`
   (the Codex layout, each with `SKILL.md` and `agents/openai.yaml`) and
   `.claude/skills` is a symlink to that tree so Claude Code discovers them.
2. **Checker strictness.** Structural failures block (pre-commit and CI);
   everything else is advisory, matching the existing drift philosophy.
3. **Standards get tests.** Every standard names the test or checker that
   enforces it where one is possible. A standard with no check says so.
4. **One authoritative source per fact.** Charter, standards, skills, and
   runbooks link to each other; they do not copy. Historical records go to
   `docs/plans/archive/`, which the drift checker already treats as history.

## Three layers

### Charter: `AGENTS.md`

Principles, engineering workflow, definition of done, and two routing tables
keyed by task type: one to a standard, one to a skill. Contains no inventory
(namespaces, hosts, ports) and no procedure. The current rules under
`.claude/rules/` shrink to path-scoped pointers into the standards; two of
them today use `**/*`, which is no scope at all.

Carried from Starbase, translated: the authority model (Observe, Propose,
Execute, Recover; a skill never grants more than the task does), closed
vocabularies for verification (passed, failed, blocked, not applicable with a
reason) and readiness (ready, conditionally ready, not ready, unable to
determine), "no change is a valid result", and the hand-off block. Left
behind: product vocabulary, prose-only skills, single-commit authoring.

### Standards: `docs/infrastructure/standards/`

Short, normative, each with a "How this is checked" section.

| Standard | Source today | Check |
|---|---|---|
| manifests | gitops.md bullets, CLAUDE.md invariants | contract tests (labels, resources, topology labels, tiers, replicas declared in Git) |
| network-policy | gitops.md section added 2026-09-09 | test: every namespace dir has `netpol-<ns>.yaml`; kube-system grants select pods |
| secrets | `.claude/rules/secrets.md`, `configuration/secrets.md`, `SOPS_SETUP.md` | existing four enforcement layers |
| commits | `.claude/rules/commits.md` | advisory |
| scripts | none | checker: header, snake_case, exec bit, reachable from justfile or hooks |
| documentation | none | checker: no empty files, no broken relative links, no `/home/<user>` paths, hub lists every doc |
| plans | CLAUDE.md "Plans" section | checker: active plans carry a status line; superseded or done plans are in archive |

### Skills: `.agents/skills/`

Fixed skeleton: frontmatter (`name`, `description` with a "Use for" sentence
and a mode), Orient, Mode, Steps naming the `just` recipes they run, Verify
(evidence table with the closed vocabulary), Hand off. Executable, not prose:
every step that can be a command is a command.

| Skill | Replaces | Mode |
|---|---|---|
| `kubani-observe` | `commands/cluster-status.md` | Observe |
| `kubani-diagnose` | `commands/troubleshoot.md`, with a failure taxonomy (desired-state, reconciliation, workload, dependency, stale observation, capacity, policy, drift) | Observe |
| `kubani-verify` | `commands/validate.md`, `commands/preflight.md` | Observe |
| `kubani-change-manifest` | the branch, validate-local, PR, reconcile, verify loop | Propose then Execute |
| `kubani-network-policy` | new; carries the ~20s probe delay and chart-key lesson | Execute |
| `kubani-decommission` | new; inventory, allowlist, out-of-band objects, tracker | Execute |

Each skill is written by using it on a real task and correcting it, one PR
per skill.

### Checker: `infrastructure/scripts/check_agent_config.py`

Runs in pre-commit and CI beside `check_drift.py`. Blocks on:

- a skill without valid frontmatter, or whose directory name differs from `name`
- a `just` recipe named in a skill, standard, or the charter that the justfile lacks
- a doc linked from a hub that is missing or empty; a broken relative link
- a `/home/<user>` path outside `docs/plans/archive/`
- a rule file without a real `paths:` scope
- a gitops namespace directory without a policy file in `networking/`
- a shell script under `infrastructure/scripts/` without the executable bit

Advisory: standards lacking a "How this is checked" section, skills not listed
in the routing table, routing table entries pointing at nothing.

PR template mirrors the hand-off block: Outcome, Scope, Evidence table, Not
verified, Follow-ups.

## Migration

| PR | Content | Blocks on |
|---|---|---|
| 1 | Mechanical fixes the checker will enforce: Linux paths, stale settings entries, wrong script paths, empty and broken docs, misdescribed `infrastructure/sops/`, done plans to archive. This plan. | nothing |
| 2 | `AGENTS.md` charter, `CLAUDE.md` import, standards extracted from rules and the four overlapping secrets docs, rules become scoped pointers | 1 |
| 3 | `.agents/skills/` with observe, diagnose, verify; symlink; commands removed | 2 |
| 4 | change-manifest, network-policy, decommission skills; PR template | 3, each validated on a real change |
| 5 | `check_agent_config.py`, pre-commit and CI wiring, network-policy contract test | 2 |

## Definition of done

- `just validate-local` runs the checker and it passes on a clean tree.
- Every item in the standards table has a check or an explicit "not checked".
- The four commands are gone and the six skills are listed in `AGENTS.md`.
- A Codex session and a Claude Code session, given the same task, reach the
  same skill through the routing table.

## Out of scope

Manifest standardisation itself (hostname pinning, bare `app:` labels,
missing requests, imperative scale-to-zero) and the Authentik upgrade overlay
cleanup. Both are audit items with their own PRs; the manifests standard will
name them as known exceptions until they land.
