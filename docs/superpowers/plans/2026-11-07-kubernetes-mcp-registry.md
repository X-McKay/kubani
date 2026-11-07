# Kubernetes MCP Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. No subagents; root separately assigns RBAC status work.

**Goal:** Register existing Kubernetes MCP for generic preflight without changing effective runtime objects.

**Architecture:** A bounded referenced-manifest profile freezes individual public object hashes and validates effective Kustomize equality. Generated SSE ownership stays separate; built-in view is a status-only external dependency.

**Tech Stack:** Python, PyYAML, pytest, existing kubectl kustomize checks.

**Spec:** `docs/superpowers/specs/2026-11-07-kubernetes-mcp-registry-design.md`

## Global Constraints

- No Secrets, SQL, bootstrap, provisioning, realm/sourceRealm extensions, workload restart, image update, gateway update or network update.
- Preserve existing image tag; no new digest-pin claim.
- Preserve all handwritten manifests, shared auth/network baselines, generated postgres-admin bytes, target patches and human exclusions.
- Root reviews this plan before implementation. Root owns live operations; RBAC implementer alone edits status.py and CLI KubeReader.

## Review Focus

- Multi-document files: exact selection must not absorb another backend; added workload documents fail.
- External aggregate view permissions: exact rules/aggregation drift fails status, never enters GitOps ownership.
- Existing Kubernetes human access survives registration unchanged.
- Kustomize omission or duplicate effective identity fails despite valid source hashes.
- Rehashing one changed object must not bypass the explicit bounded identity/path/profile contract or baseline protections.

### Task 1: Bound references and freeze declaration

**Files:** Modify `infrastructure/scripts/ops/mcp_registry/model.py`; create `infrastructure/mcp/backends/kubernetes.yaml`, `infrastructure/mcp/baseline/kubernetes-view.json`; test `tests/test_mcp_registry.py` (or focused `tests/test_mcp_registry_references.py`).

**Interfaces:** `canonical_sha256(document) -> str`; `referenced_objects(root, entry, *, external=False) -> list[dict]`; `validate` retains its signature and both profiles.

- [x] Add failing tests for exact ten references plus view projection, valid standard descriptor, unsupported fields/provision/bootstrap, changed source hashes, missing/duplicate selection, unsafe/symlink paths and added workload documents. Assert selected complete objects retain both capture/server images and every pod/config/permission field.
- [x] Run focused pytest file; verify failures reflect missing profile/reference support.
- [x] Implement strict profile branch, canonical hashing, bounded exact reference set and semantic linkage validation from spec; preserve SSE validation. Freeze object hashes from unchanged source. Project reviewed view evidence into the five-field snapshot; hash and reference it without adding it to any Kustomization.
- [x] Run focused tests; expect pass. Review declaration has no source file hash and no secret/bootstrap/provision fields.

### Task 2: Separate registration expectations from generated ownership

**Files:** Modify `infrastructure/scripts/ops/mcp_registry/render.py`; tests in focused reference suite and `tests/test_mcp_registry.py`.

**Interfaces:** `_registration_objects(root, entry) -> list[dict]` consumes Task 1 references. `_backend_objects` remains generated-only. `objects(root, name)` returns bounded deduplicated complete public expectations including external view for status.

- [x] Add failing tests asserting reference profile generates no runtime objects, adds only descriptor/inventory metadata, leaves SSE bytes/exclusions/target patches equal, and preserves handwritten Kubernetes shared-auth refs. Assert exact full effective before/after object equality and rejection of effective omission, duplicates, altered sidecar/config/SA/CRB/API egress/route/backend/extAuth/tools. Assert status expectations include all ten source objects, view snapshot and shared network/auth layers once each.
- [x] Run focused tests; confirm ownership assumptions fail before implementation.
- [x] Filter generated-only shared-auth targets, managed-source ownership checks and human exclusions by SSE profile. Keep exact baseline auth/network comparison. Use registration objects for effective equality and status, excluding external view from effective GitOps checks. Record profile/reference metadata under backend inventory record; preserve owned `objects` semantics.
- [x] Run focused tests plus existing registry/check/status tests; expect pass. Coordinate status interface with root's RBAC implementer without editing their files.

### Task 3: Generate, document and verify complete preservation

**Files:** Generated `infrastructure/mcp/generated/kubernetes.json`, `infrastructure/mcp/inventory.json`; update `docs/infrastructure/configuration/mcp-backend-registry.md`; relevant CLI/reference tests. No handwritten workload/gateway/network changes.

**Interfaces:** Existing `check.check(root)`, renderer write path and CLI render/check/status consume the new validated profile; identity descriptor remains standard.

- [x] Add regression for offline check with registered Kubernetes and immutable reviewed role snapshot. Assert source mutations fail stale hash; invalid external snapshot fails offline check. Assert default SSE scaffold/provision remains unchanged.
- [x] Run focused regression; confirm missing outputs fail.
- [x] Generate using existing CLI render after all owned tests pass; document reference ownership, review/hash update process, status-only view aggregation drift, existing image-tag limitation and nonfunctional status meaning. Do not run identity apply/live checks.
- [x] Run `pytest tests/test_mcp_registry*.py`; run existing registry offline check and complete Kustomize validation. Expect all pass with no live/network access. Compare canonical complete before/after effective object maps and generated postgres-admin bytes; expect exact equality.
- [x] Review `git diff --stat` and diff: only approved implementation/tests/docs/new declaration/snapshot/descriptor/inventory changes. Root reviews and chooses integration; do not commit or perform live operations automatically.

## Completion evidence

Native unittest discovery replaced pytest because the designated environment lacks
pytest and these suites use unittest. Combined validation passed 80 registry,
19 db-admin and 24 generic tests (one optional real-source test initially skipped).
After the observed Reloader-marker fix, 21 status and 14 CLI tests passed; the
generic suite also passed with its real-source integration enabled. Independent
whole-branch and scoped marker reviews were clear. All 529 rendered runtime objects
are identical. Offline agent matrix: ten passes, three preserved fixture budget
failures. Investigator live registration: 18 current layers; identity plan has no
operations, same IDs and unchanged Deployment/Pod/container/image/restart evidence.
No functional qualification, identity apply or runtime mutation was performed.
