# Agent onboarding preflight

## Outcome and scope

Add the Kubani-owned command `just agent-preflight AGENT --source PATH --tag AGENT/vVERSION [--live]`. It checks one agent against an explicit source checkout and the current Kubani candidate. Offline is the default: no authentication, network, fetching, generation writes, provisioning, or deployment. A passing result means the checked candidate configuration is compatible; it never means deployment-ready or qualified.

The existing source `zetra_agents.preflight.check(repo, kubani, agent, tag)` API and semantics remain unchanged. A required prospective tag retains the source preflight's clean-source, absent-local-tag, capabilities, model reservation, signer, checkout provenance and input-hash checks. Candidate edits remain allowed.

## Architecture

Use a small Kubani orchestration script with an isolated source adapter, not a new cross-repository package dependency. Run a bounded subprocess bridge under the current Python with the explicit source `tools` directory on its import path; import only `zetra_agents.layout` and `zetra_agents.preflight`, avoiding the source CLI's contracts dependency. Validate bounded JSON output and retain the complete source receipt. Treat the explicitly selected source checkout as executable trusted local input; timeout and output limits bound accidental failure, not hostile Python execution.

Reuse `infrastructure/scripts/ops/mcp_registry` checks and models rather than duplicating them. Reuse the existing `mcp-registry.py` `KubeReader` through an isolated loader. Keep live authentication lazy. Aggregate independent source and registry errors when inputs permit; a failed source check must not hide an independently diagnosable registration failure.

## Required offline checks

- Run existing source compatibility preflight once for the selected agent and prospective tag.
- Compare source and candidate Agent identity, owner and enabled semantics; supported identity modes are `agent` and `on-behalf-of`. Use the actual Agent schema defaults when normalizing omitted fields; do not invent defaults. Unsupported or ambiguous identity semantics block.
- Compare capabilities using the existing source check. Model budget checks concern configured per-session/per-day limits versus APS reservation, not remaining allowance.
- For every candidate MCP grant, resolve its backend against `model.load_registry(root)`. For registered dependencies, run `check.check(root)` once and reuse its full offline validation result. Validate `model.descriptor(entry)` through existing exact identity descriptor validation. Require granted tools to be a subset of `authorization.tools`, and validate effect/delegation constraints against the supported registry and Agent contracts. Do not infer authorization from backend name or tool name alone.
- An unresolved backend may be a handwritten legacy backend. Report `legacy_backend_not_checked` as a required blocker with remediation to obtain a supported reviewed adapter or migrate registration; do not mislabel it missing or silently force migration.
- An agent without MCP grants receives `not_applicable` for registry/dependency checks and has no irrelevant registry gate.

Human consent and permissions for on-behalf-of execution remain explicitly `not_checked`; configuration compatibility does not prove them.

## Optional read-only live evidence

For `--live`, inspect each distinct registered MCP dependency once using `render.objects`, `model.descriptor` and `status.inspect_registration`. Reuse the existing operator SOPS administrator authentication transport, wrapped to reject every method other than GET before dispatch. This authentication can read/decrypt the existing operator credential; the command must describe this honestly. It does not read backend Secret values. Kubernetes Secret-reference checks use existing name-only metadata transport. No apply, identity bootstrap, tool execution, grant creation, session creation, or reconciliation is allowed.

Unavailable/conflicting/incomplete live evidence fails the requested live scope and exits nonzero. Missing authorization is a bounded unavailable result, never an automatic privilege escalation or mutation. Registration evidence remains distinct from functional success.

## Result and evidence

Emit a versioned JSON result with agent, tag, scope, overall success, source receipt, input evidence and checks. Each check includes a stable code, state (`pass`, `fail`, `not_checked`, `unavailable`, `not_applicable`), required flag, affected agent/backend, bounded explanation and actionable remediation. Required `fail`, `not_checked` or `unavailable` results make overall success false. Explicitly excluded checks are non-required, so their honest `not_checked` status does not prevent offline compatibility success. Live checks become required only with `--live`.

Retain source checkout HEADs, dirty state, local-main relations and file hashes from the source receipt. Hash relevant Kubani Agent, identity and backend configuration inputs used by the orchestrator. State the exact evidence coverage: these hashes are local input provenance, not proof of remote freshness or an atomic snapshot of a changing checkout. Do not emit secret contents, credentials, raw API/process responses, or unbounded exceptions.

Always report these exclusions: live agent identity, human consent/on-behalf-of authorization, AgentRelease signatures, five attestations, approval and NoDrift, actual tool behavior, remaining ledger allowance, remote freshness, and general qualification. Do not add an Agent Ready freshness check: current conditions lack observedGeneration sufficient to support that claim. This command does not change existing release or qualification gates.

## Acceptance

Generic tests cover agents with zero, multiple and legacy dependencies; identity/owner/enabled and capability/tool/effect mismatches; aggregated failures; deterministic structured output; offline refusal to initialize live transports; GET-only enforcement; requested live unavailability producing nonzero exit; metadata-only Secret handling and safe error output. Documentation includes one offline and one live invocation and explains the operator-authentication boundary and all excluded claims.
