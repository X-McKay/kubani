# MCP Backend Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add one supported MCP server from one non-secret definition, with complete platform registration and unchanged existing authority.

**Architecture:** A strict registry generates checked-in GitOps resources and identity descriptors. Explicit identity plan/apply and read-only status use existing administrative authentication; Flux remains deployment owner. Migrate postgres-admin first and prove a second synthetic backend can be added independently.

**Tech Stack:** Python, existing PyYAML/unittest, Kustomize/Flux, agentgateway, Keycloak, APS.

**Spec:** `docs/superpowers/specs/2026-11-06-mcp-backend-registry-design.md`

## Global Constraints

- Only `postgres-admin` migrates live. Existing approved db-admin v0.1.1 is the functional check.
- Preserve its effective permissions, object identities and Pod template; no broad qualification work.
- No secret values in definitions/output/logs; retain SOPS and explicit bespoke database bootstrap.
- No agent grants, signer changes, release approvals, human delegation changes or Keycloak restart.
- Root owns live operations, gh PRs/merges and cleanup. Use `/home/al/.kube/config`; never rollout restart.
- V1 supports the existing container-hosted SSE profile. Unsupported profiles fail explicitly.
- Adding a definition must generate shared registration additions automatically; no implicit removal/rename.
- Preserve failed evidence and all earlier branches/worktrees. User selected Sol delegation; independent implementations use isolated clones and disjoint files.

## Review Focus

- A second server must receive every auth layer without changing the first server's authority (Task 1 regression).
- Shared broad policies must not bypass the intended human-gateway exclusion or upstream restrictions (Task 1 negative mutation tests).
- Partial Keycloak create/attach failures must be inspectable without blind overwrite or unrelated writes (Task 2 fake-transport tests).
- Completed bootstrap Jobs must not certify changed SQL or stale deployment/route status (Tasks 1/2 hash and observed-generation tests).
- A normal completed runtime workflow must still fail acceptance if evidence/report or cleanup is incomplete (Task 4 existing strict verifier).

### Task 1: Registry, deterministic generation and incremental addition

**Owner/files:** Sol implementer in isolated clone. Own `infrastructure/mcp/`, `infrastructure/scripts/ops/mcp_registry/{__init__,model,render,check}.py`, generated GitOps resources and required migration/Kustomization edits, `tests/test_mcp_registry.py`, and existing db-admin manifest-test adaptations. Do not edit identity/status modules, CLI, CI/justfile or operator docs.

**Interfaces:** `model.load_registry(root: Path) -> list[dict]` returns validated entries; `model.scaffold(name: str) -> str` returns non-secret YAML requiring explicit values before deployment; `model.descriptor(entry: dict) -> dict` returns existing role/resource/scope/requester/attachment descriptor shape. `render.render(root: Path, entries: list[dict]) -> dict[str, bytes]` returns all owned repository-relative generated files; `render.write(root: Path) -> None` validates and safely writes; `check.check(root: Path) -> list[str]` returns bounded actionable findings, empty on success. `render.objects(root: Path, name: str) -> list[dict]` returns complete desired backend objects plus referenced bootstrap Job/ConfigMap (never Secret data) for status. Freeze these interfaces; implementation may split internal helpers.

- [ ] Capture semantic baseline of postgres-admin resources and Pod template in test fixtures; do not include secret plaintext.
- [ ] Write failing tests for strict parsing, deterministic render, unsupported profile, duplicate keys/names/paths, missing auth, route/Service collisions, shared-policy overlap, bootstrap hash/revision mismatch, stale/removed inventory and unsafe output paths.
- [ ] Write a second synthetic-backend test: scaffold and complete definition, render two entries, assert original backend object specs unchanged and all required protections on the second. No production deployment.
- [ ] Implement schema and entry using exact current postgres-admin values. Handwritten SQL/Job/Secrets remain referenced. Support explicit optional upstream/bootstrap dependencies so a new server need not pretend to be PostgreSQL.
- [ ] Implement generated resource ownership/inventory, one-time Kustomization integration and shared JWT/agents-only/human-gateway exclusion additions. Preserve legacy protections. Validate complete rendered output rather than checking only generated file text.
- [ ] Adapt existing db-admin manifest tests to generated/rendered paths without weakening assertions. Run focused unit tests and required Kustomize builds once; retain red/green evidence. Commit and report exact SHA/tests/remaining concerns.

### Task 2: Generic identity bootstrap and layered live status

**Owner/files:** Different Sol implementer in isolated clone. Own `infrastructure/scripts/ops/mcp_registry/{identity,status}.py`, compatibility `db-admin-backend.py`, `tests/test_mcp_registry_identity.py`, `tests/test_mcp_registry_status.py`. No registry/render files, deployment edits, CLI or live operations.

**Interfaces:** `identity.configure(api, descriptor: dict, *, apply: bool=False) -> dict` generalizes existing exact helper; `identity.admin()` uses the existing local SOPS Admin transport. Descriptor shape is exactly `apps/keycloak/db-admin-backend.json` (role/resource/scope/requester/attachment); validate it rather than trust arbitrary raw admin bodies. `status.inspect_registration(expected: list[dict], descriptor: dict, *, read_object, api) -> dict` receives desired public resource objects and `read_object(apiVersion, kind, namespace, name) -> dict|None`; return bounded per-layer status with overall `complete` boolean and `functional: 'not-tested'`. Do not fetch Secret contents. CLI will inject kubectl transport and desired objects.

- [ ] Write failing tests for a second descriptor, preserved exact db-admin behavior, conflict-before-write, partial failure/readback, unexpected attachment change and safe failure output.
- [ ] Generalize existing helper without mutable global backend constants. Preserve db-admin entry point/API for old tests via a descriptor-backed wrapper; generated descriptor stays inert, outside realm import.
- [ ] Write failing live-status fixture tests for missing/stale Deployment, Service/route mismatch, Accepted/ResolvedRefs freshness, bootstrap Job/ConfigMap mismatch or incomplete Job, policy/identity gaps and unavailable resources. Structural success must not imply functional success.
- [ ] Implement read-only status comparison. Compare desired fields while accounting explicitly for server defaults/controller metadata; do not claim exact equality by dropping meaningful fields. Require relevant observed generations and current conditions.
- [ ] Run focused new/old identity and status suites only; no credentials, cluster calls or duplicate generator testing. Commit and report exact SHA/tests/concerns.

### Task 3: CLI, CI and integrated migration checks

**Owner/files:** Root integration with Sol review. `infrastructure/scripts/ops/mcp-registry.py`, `justfile`, `.github/workflows/validate.yml`, `docs/infrastructure/configuration/mcp-backend-registry.md`, CLI tests.

- [ ] Integrate reviewed Task 1/2 commits; record rulings for interface discrepancies, preserve author branches.
- [ ] Implement commands `add NAME`, `render --check|--write`, `check`, `identity plan|apply NAME`, `status NAME`. Root-relative paths explicit; add refuses overwrite and has no network/live effects. Registry failures occur before auth or cluster access.
- [ ] Inject bounded kubectl read transport for status using selected kubeconfig, no secret-content reads. Output only safe structured summaries. Identity apply is explicit; default tooling is read-only.
- [ ] Add focused CLI tests for incremental add, no overwrite, no implicit auth/writes, safe failure, exit status and help.
- [ ] Add render/check/new unit suites to local validation and CI; retain existing checks. Document exact author/operator sequence and unsupported profiles.
- [ ] Run integrated targeted suites, all GitOps builds and required checks once. Review whole branch independently, fix material findings and open gh PR. No live mutation until merged.

### Task 4: Live integration and evidence

**Owner:** Root only.

- [ ] Before merge, capture existing backend rendered/live identities and Pod template, read-only identity plan, approved release spec and successful prior evidence. Never print credentials.
- [ ] Merge green reviewed PR, reconcile Flux and prove same backend object/Pod-template semantics and existing workload remains available. No forced restarts.
- [ ] Run new read-only identity plan/status: zero planned identity changes, current registration complete, functional explicitly not-tested until the ordinary session.
- [ ] Run one bounded normal db-admin v0.1.1 session. Require four latest available diagnostics, report facts equal hash-verified evidence and CLEANED/OK/DELETED with no remaining sandbox Pods. Preserve any failed attempt.
- [ ] Record actual outcome, incremental-add instructions and remaining constraints. Then plan the next user-requested item, pre-release checks, separately; do not silently resume qualification.
