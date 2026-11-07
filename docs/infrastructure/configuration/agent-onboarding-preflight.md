# Agent onboarding preflight

Run one agent against an explicit trusted source checkout and the current Kubani
candidate before requesting a prospective release tag:

```sh
just agent-preflight investigator --source ../zetra-agents --tag investigator/v1.2.3
just agent-preflight db-admin --source ../zetra-agents --tag db-admin/v1.2.3 --live
```

The default checker is offline. It does not authenticate, fetch, generate GitOps,
provision or deploy. `uv run` may provision the Python environment or fetch missing
dependencies (including the existing live transport's pinned PyJWT dependency) before starting the checker; prepare that environment separately if
the entire invocation must be disconnected. A pre-provisioned equivalent is
`python -B infrastructure/scripts/ops/agent-preflight.py AGENT --source PATH --tag TAG`.
The pre-provisioned environment also needs PyJWT[crypto] 2.13.0 for `--live`;
the offline checker never imports that authentication dependency.

The source checkout is **trusted executable local input**: the adapter imports its
`zetra_agents.layout` and `zetra_agents.preflight` modules in an isolated Python
subprocess, with bounded execution time and output. This is not a security sandbox.
Use an updated reviewed source checkout containing the compatible version 1 checker
and its effective aggregate model-budget validation. Kubani reuses the implementation
from that checkout; the receipt's source HEAD identifies the implementation checked.
It does not establish that HEAD's remote freshness or that it is the latest version.
The source must be clean and the required prospective tag must be absent locally.
Candidate edits are allowed. Capabilities, configured model limits versus APS
reservation, signer configuration and local checkout provenance retain the existing
source checker semantics.

Kubani additionally compares source/candidate owner, enabled and identity semantics.
Defaults match `agents.agentplatform.io.yaml`: enabled is true, on-behalf-of required
is true and fallback is deny; identity mode must be explicit. MCP delegation defaults
to inherit, resolving to the agent identity mode; explicit agent and on-behalf-of
are also supported. MCP effect must be remote_read. No permission or consent is
inferred from these configuration values.

For registered MCP dependencies, the checker runs the full existing offline registry
validation once, validates the exact descriptor, and requires granted tools to be a
subset of the reviewed backend authorization. A handwritten legacy dependency emits
required `legacy_backend_not_checked`: obtain a supported reviewed adapter or migrate
registration. Agents with no MCP grants have no registry gate.

`--live` adds read-only evidence for each distinct registered MCP dependency, using
the existing registry status inspectors and Kubernetes transport. The existing
operator SOPS administrator authentication may read and decrypt the operator
credential and obtain an authentication token. Subsequent identity API requests are
guarded to allow GET only. Backend Kubernetes Secret references are checked with
name-only metadata reads; backend Secret values are never requested. The checker
never applies objects, bootstraps identities, runs tools, creates grants or sessions,
or reconciles configuration. Missing authorization returns unavailable evidence and
never initiates a privilege change.

The command emits one versioned JSON result. Each check has a stable code, state,
required flag, agent/backend, bounded explanation and remediation. Exit 0 means
all required checks passed or were not applicable. Required fail, unavailable and
not_checked states exit 1; incomplete or conflicting requested live evidence fails.
The complete validated source receipt is retained. Registry subprocess diagnostics
are sanitized rather than exposing raw responses; run `just mcp-check` locally to
investigate registry failures. The optional integration test can be selected with
`AGENT_PREFLIGHT_SOURCE=/trusted/source just test-agent-preflight`.

Input hashes cover local Agent and relevant registry, identity, backend and generated
configuration, including ciphertext where applicable. Together with the source
receipt's HEADs, dirty state and local-main relations, they document local input
provenance. They prove neither remote freshness nor an atomic snapshot of a changing
checkout.

A passing result is configuration compatibility, not deployment readiness or
qualification. The result always explicitly excludes live agent identity; human
consent/on-behalf-of authorization; AgentRelease signatures; the five attestations;
approval and NoDrift; actual tool behavior; remaining ledger allowance; remote
freshness; and general qualification. Live MCP registration evidence remains distinct
from functional success. No Agent Ready freshness claim is made. Existing release
and qualification gates are unchanged.
