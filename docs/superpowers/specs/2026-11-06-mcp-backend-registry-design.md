# MCP backend registry

## Intent and selected approach

The user selected a declarative registry after the db-admin rollout exposed repeated deployment and registration edits. Implement this first; cross-repository agent preflight and bounded run/report retrieval follow as separate changes. Broader platform qualification remains paused.

Two approaches were considered: generate reviewed GitOps resources plus explicit identity bootstrap, or introduce a privileged continuously running controller. The user selected the registry approach. It fits Flux and keeps privileged identity changes explicit. No new controller or platform binary release is required.

## Outcome

An operator adds one non-secret backend definition, runs render and check, reviews a normal PR, applies the exact identity plan, and checks registration. CI catches missing gateway authentication, authorization, network wiring and bootstrap references before merge. Registration status distinguishes configuration completeness from an actual successful tool call.

The first migration is only `postgres-admin`. Its image, arguments, Deployment/Service names, Pod template, permissions, routes, role, audience, scope and optional APS attachment remain semantically identical. Other existing MCP backends remain handwritten and functional; they are included in collision and shared-policy checks. Do not migrate or remove them implicitly.

## Registry and commands

Proposed location: `infrastructure/mcp/backends/*.yaml`, with a versioned strict schema and Python tooling using the repository's existing dependencies. Unknown fields, duplicate YAML keys, unsupported versions and invalid types fail validation. Exact filenames/module layout are implementation choices.

Each entry declares:

- Stable backend name and management profile. V1 supports the existing container-hosted SSE profile used by postgres-admin; unknown transport/auth profiles fail rather than silently adapting other servers.
- Image pinned by digest, container arguments, resources, Service/container port, labels, existing security context/probes and Secret references. Secret values are prohibited. The generator has one supported workload template; exceptions must be explicit supported fields, not arbitrary YAML passthrough.
- Internal MCP endpoint and external OAuth resource identity, derived from backend name plus reviewed shared settings. Keep internal `mcp.agents.internal` routing distinct from external `https://mcp.almckay.io/<backend>/mcp` audience identity.
- Exact allowed tool names mapped to noncomposite backend roles. No wildcard tools, arbitrary CEL expressions or automatic agent grants. V1 postgres-admin permits only its existing execute_sql role/tool pair; it does not claim SQL-argument enforcement.
- Explicit upstream namespace, Pod selectors and destination ports for paired ingress/egress rules. Shared DNS and existing gateway connectivity are referenced and checked. No implicit internet access or namespace-wide upstream allow rule.
- References to bespoke SOPS Secret manifests and bootstrap resources, including an explicit bootstrap revision and declared SQL content hash. The initial baseline records the existing v1 Job without rerunning it.

Command interface, exact executable naming left to implementation:

- `mcp-registry render --check`: offline, verify checked-in generated output matches the definitions; do not modify files.
- `mcp-registry render --write`: deterministically update only owned generated output and its inventory. Validate everything before writing; use staged/atomic file replacement so errors cannot leave a partially rendered tree.
- `mcp-registry check`: offline structural and semantic validation of the registry and complete relevant Kustomize output.
- `mcp-registry identity plan <backend>`: read-only Keycloak comparison; return safe operation names, identities and conflicts, never credentials or raw responses.
- `mcp-registry identity apply <backend>`: explicit create/attach-only operation using the existing local SOPS admin authentication path. No cluster-admin credentials in Pods or new controller permissions.
- `mcp-registry status <backend>`: read-only Kubernetes and Keycloak registration checks, using the configured kubeconfig. Nonzero exit for incomplete/conflicting registration. Output identifies incomplete layers rather than reporting generic Ready.

## Generated ownership

Generate the Deployment, Service, backend-specific upstream network rules, AgentgatewayBackend, HTTPRoute, fail-closed APS extAuth policy, exact tool policy, identity descriptor and the registry's additions to JWT/agents-only targets. Wire generated directories/patches into existing Kustomizations once; future entries require no hand-editing of shared target lists.

Use stable object names and preserve Flux ownership and existing Pod templates during migration. Shared policies remain handwritten except for narrowly generated additions. Remove postgres-admin's old duplicate declarations in the same PR. Validate the final effective resources, not textual equality of intermediate patches.

The inventory identifies exactly which output paths/objects the generator owns. Refuse generated-path collisions, output outside approved roots, symlink traversal, duplicate object identities, and unaccounted stale output. V1 does not support removal or renaming: removing a previously inventoried backend fails and requires a separately reviewed migration design. Do not silently prune services, identities, credentials or references used by approved agents. No generic force option.

Keep database SQL, database role/bootstrap Job implementation, credential generation/rotation and SOPS ciphertext handwritten. The registry references them and validates their interface. Keep the existing db-admin helper entry point as a thin compatibility wrapper if needed; one implementation must drive identity semantics.

## Identity behavior

Generalize the existing db-admin bootstrap safeguards rather than replacing them with blind apply:

1. Inspect all existing objects and APS attachments before the first mutation.
2. Require exact resource/scope/role semantics, with only explicitly documented harmless Keycloak default normalization.
3. Create missing noncomposite role, bearer-only resource and audience scope; attach the scope optionally to the existing APS requester.
4. Read back each operation and verify unrelated attachments did not change.
5. Refuse conflicting or ambiguous state. A partial failure returns incomplete state and requires fresh inspection on retry; never overwrite conflicting objects or retry an ambiguous write blindly.

Do not edit the hashed realm-import ConfigMap, restart Keycloak, alter human delegation, change controller privileges, grant roles to agents, or modify release signer trust. Backend registration does not approve any AgentRelease.

## Validation and readiness

Offline checks cover duplicate names/paths/resource IDs; complete strict JWT and agents-only coverage; fail-closed extAuth and correct APS backend context; exact role/tool agreement; Service/selector/port/transport agreement; non-secret references; bootstrap revision/content-hash agreement; paired upstream rules; Kustomization inclusion; and absence of duplicate generated/legacy objects.

Analyze existing matching network policies as well as generated rules. An additive narrower rule does not narrow a broader allow. Preserve and explicitly account for current shared gateway/DNS access; reject newly introduced or unexplained overlaps and prove the migrated backend has the same effective permitted paths. Do not widen the old human gateway's access to postgres-admin.

A changed SQL hash cannot reuse the declared completed bootstrap revision silently. CI requires a reviewed new revision or refuses the mismatch; tooling never automatically reruns SQL or deletes Jobs. Runtime status checks the referenced Job's exact identity/spec against desired state and its completion condition, alongside workload readiness and accepted/resolved gateway resources. Record whether verification is structural, live registration, or functional. TCP readiness does not prove database permissions or tool success.

Live status checks exact Keycloak role, resource, scope, mapper and APS optional attachment. It never obtains an agent token merely to claim registration success. Functional verification is a separate ordinary agent session through agentgateway.

## Migration and acceptance

1. Capture the current rendered postgres-admin resources and identity plan as a semantic baseline; preserve all prior work and failed evidence.
2. Introduce the registry/tooling and migrate postgres-admin declarations in an isolated branch. Show no effective permission change and no Pod-template change.
3. Add focused tests for rendering determinism, malformed/unsupported entries, missing protection, collisions, broader network-policy overlaps, bootstrap hash/revision mismatches, identity conflicts, partial-write recovery, and no secret leakage. Add render/check to local validation and CI.
4. Independent review, required CI and normal gh PR merge. Observe Flux reconciliation; do not rollout restart workloads. Any unexpected need for engine/broker downtime remains a user decision.
5. Run read-only identity plan/status on postgres-admin: no identity mutations expected. Demonstrate repeatability and zero pending changes. If the baseline conflicts, stop migration and diagnose rather than repair automatically.
6. Run one bounded db-admin session using the existing approved v0.1.1 release. Require all four diagnostics available, report facts equal evidence, and confirmed sandbox cleanup. Preserve failed attempts.
7. Document the operator workflow and remaining profile limitations. Only then proceed to the next agreed item, agent pre-release checks, followed by bounded run/report retrieval.

Success means adding a backend of the supported profile requires one declaration plus its explicit credentials/bootstrap dependencies, generated changes are reviewable and checked, and postgres-admin continues to work with unchanged authority. It does not mean arbitrary MCP servers or automatic administrative remediation are supported.
