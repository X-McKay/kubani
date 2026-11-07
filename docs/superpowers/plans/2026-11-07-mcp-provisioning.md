# MCP Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Prepare paired encrypted PostgreSQL backend credentials and preflight the reviewed Flux bootstrap dependencies explicitly.

**Architecture:** Add a strict optional declaration and narrowly staged registry loader, then a local provisioning module. Preserve Flux deployment and existing identity/gateway paths.

**Tech Stack:** Python, PyYAML, SOPS CLI, existing Kustomize/Flux manifests.

**Spec:** `docs/superpowers/specs/2026-11-07-mcp-provisioning-design.md`

## Global Constraints

No live writes or SQL execution; no secret plaintext on disk/argv/output. Existing complete pairs remain byte-identical. Partial pairs and collisions refuse. Existing strict render/check remains strict. PostgreSQL SQL/Job generation and role adoption are outside scope.

## Review Focus

- Missing credential pair must be plannable while ordinary check still fails.
- Duplicate Secret identities and symlink paths must refuse before encryption.
- Partial publication must be visible and retries must refuse automatic adoption.
- Existing SOPS files are preserved without decrypting or invoking SOPS.
- Bootstrap administrator references and source inclusions must be checked independently of workload readiness.

### Task 1: Strict schema and staged validation

Files: modify `infrastructure/scripts/ops/mcp_registry/model.py`; extend `tests/test_mcp_registry.py`.

- [x] Add failing tests for the exact provision schema, unknown fields/profile, mismatched Secret references, absent pair, partial pair, pair identity collisions, unsafe paths and unchanged strict default behavior.
- [x] Run focused tests and confirm failures are new missing behavior.
- [x] Add `load_registry(root, *, provisioning=False)` and propagate the narrow flag into validation; implement exact profile/reference validation. Never bypass SQL/hash/Job or existing-file checks. Keep all existing callers strict.
- [x] Run focused model tests and existing registry tests; commit the coherent change.

### Task 2: Read-only preflight and paired encryption

Files: create `infrastructure/scripts/ops/mcp_registry/provision.py`, `tests/test_mcp_registry_provision.py`.

Interfaces: `plan(root: Path, entry: dict) -> dict`; `apply(root: Path, entry: dict, *, run=None) -> dict`. Sanitized result includes status, operations, dependency issues and bootstrap metadata; apply accepts injectable subprocess runner for synthetic tests.

- [x] Test read-only/missing-pair plans, exact administrator references, missing source inclusions/config maps/SQL dependencies, revision reuse, duplicate metadata, bad SOPS policy, complete-pair preservation, partial-pair refusal and symlink refusal.
- [x] Implement metadata-only preflight using existing path/YAML helpers and inventory revision semantics; do not call Keycloak/kubectl or build an absent pair.
- [x] Test synthetic SOPS transport: one password in paired manifests, stdin only, correct destination filename, encryption failure leaves no published files, sanitized subprocess errors, exclusive publication and partial-publication refusal on retry. Assert no plaintext temporary files and no secret output.
- [x] Implement in-memory generation/encryption and exclusive encrypted publication. Validate returned ciphertext manifests before publishing; do not trust subprocess success alone.
- [x] Add a real SOPS round-trip integration test with a disposable age recipient/key and synthetic credentials in a temporary repository; verify ciphertext decrypts to the paired expected values within the test, never print them or read production keys/secrets. Skip explicitly if required binaries are unavailable.
- [x] Run the new focused tests and registry regressions; commit.

### Task 3: CLI, preserved migration and operator guide

Files: modify `infrastructure/scripts/ops/mcp-registry.py`, `infrastructure/mcp/backends/postgres-admin.yaml`, `tests/test_mcp_registry_cli.py`, `docs/infrastructure/configuration/mcp-backend-registry.md`.

- [x] Add failing CLI tests showing provision bypasses identity authentication/full strict prerequisite check only through staged validation, produces nonzero for conflicts, sanitizes failures and refuses unknown backends. Add add-definition regression for unrelated incomplete scaffold.
- [x] Wire `provision plan/apply NAME` directly to local provisioning before identity dispatch; keep render/check/status/identity behavior unchanged. Adjust add name/path collision checking without loading incomplete unrelated declarations.
- [x] Add postgres-admin provision stanza matching existing metadata and informational policy description. Assert its plan/apply preserve all credential bytes, bootstrap files and generated runtime configuration. Do not rewrite generated runtime merely to include provisioning metadata.
- [x] Document exact incremental flow, partial failure recovery boundary, missing-dependency output, preservation limits, separate identity/Flux/functional verification and reviewed SQL requirements.
- [x] Run `just test-mcp-registry`, `just mcp-check` and required GitOps/infra checks from existing repository CI. Review `git diff` and verify no secret/bootstrap/runtime artifact changed beyond intended declaration/docs/code/tests. Commit.

Implemented and independently reviewed. Registry regressions (64 tests) and db-admin regressions (19 tests) passed before two additional negative cases; the final provisioning suite (15 tests) and CLI suite (13 tests) passed after all fixes. Seven GitOps builds, 70 infrastructure tests and actual local preserve/no-op commands passed. No production credentials, bootstrap Jobs or runtime artifacts changed. Secret scanning remains unchanged; manifest references use roleManifest/workloadManifest.
