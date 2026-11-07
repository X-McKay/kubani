# Agent onboarding preflight implementation plan

Design: `docs/superpowers/specs/2026-11-07-agent-onboarding-preflight-design.md`.

1. Inspect Agent schema/runtime semantics for identity modes, owner, enabled defaults, MCP effects and delegation. Record the exact supported constraints before implementing comparison; ambiguous semantics must produce a blocker.
2. Add an isolated Kubani source adapter that invokes the existing source `preflight.check` with the current Python and explicit source tools path. Bound runtime/output, validate JSON, preserve source receipt, and sanitize failures. Do not change the source API or import its CLI.
3. Implement the single-agent offline orchestrator and versioned check model. Compare identity/owner/enabled; join MCP grants to registry entries; reuse registry check once, descriptors and existing tool policies. Distinguish legacy from missing and make no-MCP checks not applicable. Aggregate safe independent failures and record honest input hashes.
4. Add lazy `--live` support using existing registration status/KubeReader and SOPS operator authentication. Wrap the identity API with a GET-only guard, deduplicate dependencies and surface unavailable/incomplete results as required failures. Preserve metadata-only backend Secret checks; exclude all mutations and functional sessions.
5. Add `just agent-preflight AGENT --source PATH --tag TAG [--live]` and concise operator documentation covering offline default, output/exit semantics, operator credential use, remediation and excluded claims.
6. Verify using meaningful generic fixtures: no MCP, multiple registered backends, legacy backend, source/candidate identity/owner/enabled mismatches, tool/effect constraints, independent failure aggregation, malformed/oversize/timed-out bridge output, no live initialization offline, GET-only rejection, live unavailable/incomplete nonzero, and absence of secrets/raw exceptions in receipts. Run the existing registry regression suite and appropriate formatting/static checks after targeted tests pass.
7. Review the diff and evidence against the design. No network, live qualification, identity apply, provisioning, deployment or merge is part of this implementation plan. Root retains operations and integration ownership; qualifications remain paused.

Implementation boundary: keep adapters local and small, reuse existing validators, avoid new package dependencies and speculative legacy or live AgentRelease validators. If an existing API cannot prove a claim, emit an explicit non-required exclusion or required blocker according to the selected scope.

## Completion evidence

Implemented and independently reviewed. The focused suite passed 24 tests, with
66 existing registry and 19 db-admin regressions passing. Root actual offline and
`just` live invocations passed; live MCP evidence covered all 20 registration
layers while retaining functional/release/authorization exclusions. Unchanged
secret and pre-push scanners passed. No live mutation or new session occurred.
