# Kickoff Prompt for `kubani ship` Implementation

> Copy everything below the line into a new Claude Code session.

---

## Prompt

Implement the plan at `docs/superpowers/plans/2026-03-11-ship-command-and-justfile-cleanup.md`. Read the full plan before starting.

### Execution Strategy

Use the `superpowers:executing-plans` skill. The plan has 12 tasks across 5 chunks. Here's the dependency graph and parallelism strategy:

```
Parallel Track A (ship command):     Parallel Track B (justfile cleanup):
  Task 1: components.yaml              Task 6: Remove kdev-* commands
  Task 2: ComponentRegistry            Task 7: Collapse MCP test recipes
  Task 3: ShipOrchestrator             Task 8: Remove dead bump/changelog
  Task 4: Wire CLI command             Task 9: Remove cluster commands
  Task 5: Integrate into deploy.py     Task 10: Add ship recipe
                                        Task 11: Final audit
         \                             /
          \                           /
           → Task 12: Update Claude Code instructions ←
```

**Track A** is sequential (each task depends on the previous). **Track B** tasks are all independent of each other and independent of Track A. **Task 12** must run last after both tracks complete.

### Parallel Execution Plan

1. **Phase 1** — Launch two parallel agents:
   - **Agent A**: Tasks 1 → 2 → 3 (create components.yaml, ComponentRegistry, ShipOrchestrator). Run tests after each task. Stop after Task 3 passes tests.
   - **Agent B**: Tasks 6, 7, 8, 9 (all justfile deletions). Each is a simple removal — do them all in sequence within one agent, committing after each.

2. **Phase 2** — After both Phase 1 agents complete:
   - Task 4: Wire CLI command (depends on Task 3 output)
   - Task 5: Integrate ComponentRegistry into deploy.py
   - Task 10: Add ship recipe to justfile
   - Task 11: Final justfile audit

3. **Phase 3** — After Phase 2:
   - Task 12: Update all 6 Claude Code instruction files

### Critical Implementation Notes

Read these before writing any code — they address real codebase issues the plan already accounts for:

1. **Image names ≠ component names.** The plan's `components.yaml` has an `image_name` field for each component. Use it in `_patch_manifest` regex, not `comp.name`. Examples: `nexus-orchestrator` → image `kubani-nexus-orchestrator`, `registry` → image `kubani-registry`.

2. **Earthly paths need `./` prefix.** All Earthly target paths must start with `./` (e.g., `./kubani/mcp/servers/temporal+push`). Without it, Earthly interprets the path as a remote reference.

3. **kubani-ui has no `push` target.** Its `build_target` field is set to `docker` in components.yaml. The `_build_and_push` method uses `comp.build_target` to handle this.

4. **Deployment names don't always match component names.** The `registry` component's k8s deployment is named `metadata-registry`. The plan handles this via `deployment_name` and `pod_selector` fields with smart defaults in `__post_init__`.

5. **Pre-commit hooks must run visibly.** `_commit_manifest` does NOT use `capture_output=True` so hook output (ruff, gitleaks, detect-secrets) prints to terminal. If hooks fail, the pipeline stops.

6. **Staged changes check at pipeline start.** `_check_clean_staging` prevents contaminating the ship commit with unrelated staged changes. Unstaged changes are fine (multiple Claude Code sessions may be active).

7. **Auto version bump.** `_bump_version` increments patch version in pyproject.toml before building. Uses existing `kubani.cli.version_utils.bump_version()`. Skipped during `--dry-run`.

### Verification Checkpoints

After each task, verify before moving on:

- **Task 2**: `uv run pytest kubani/cli/tests/test_components.py -v` — 10 tests pass
- **Task 3**: `uv run pytest kubani/cli/tests/test_ship.py -v` — 11 tests pass
- **Task 4**: `uv run kubani ship --list` — shows all 11 components
- **Task 4**: `uv run kubani ship temporal-mcp-server --dry-run` — runs tests, prints "Dry run complete"
- **Task 5**: `uv run pytest kubani/cli/tests/ -v -k "deploy or build" --tb=short` — existing tests still pass
- **Tasks 6-9**: `just --list | head -30` — no deprecated entries
- **Task 11**: `wc -l justfile` — approximately 990 lines
- **Task 12**: Read each modified file to confirm old `just build`/`kubani deploy` references are gone

### What NOT to Do

- Do NOT actually ship any components — this implements the ship command itself
- Do NOT modify any Earthfiles, deployment YAMLs, or pyproject.toml versions
- Do NOT delete the plan document after implementation
- Do NOT skip pre-commit hooks on any commit (`--no-verify` is never acceptable)
- Do NOT amend commits — always create new ones
