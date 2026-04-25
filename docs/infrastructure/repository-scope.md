# Repository Scope

This repository is being reduced to an infra-only Kubani codebase.

## In Scope

- `infrastructure/ansible/`
- `infrastructure/gitops/`
- `infrastructure/scripts/`
- cluster runbooks and troubleshooting docs

## Out of Scope

These concerns are intentionally moving into separate workstreams and should not return here as source-of-truth application code:

- runtime and agent source
- MCP server implementations
- UI code
- runtime registry and skill-development tooling

## Why

The previous monorepo mixed cluster operations with first-party application source. That made the repo harder to review, harder to maintain, and harder to split cleanly. The infra repo should be able to provision and operate the cluster without needing local copies of runtime code.

## Target End State

1. This repo owns host automation, GitOps, and operational docs.
2. First-party apps are built and released elsewhere.
3. GitOps consumes versioned artifacts rather than scanning local runtime trees.

## Follow-On Work

- split remaining runtime-facing deployment ownership into separate repos
- publish first-party workloads as versioned artifacts
- keep this repo focused on cluster services and homelab operations
