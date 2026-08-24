# Cluster Applications

This directory contains Flux-managed workloads that run on top of the cluster infrastructure.

## Database Layer

`databases/` is the aggregation layer used by Flux so PostgreSQL, Redis, and backup resources come up before the rest of the app tier.

## Current App Layer

- `authentik/`
- `monitoring/`
- `temporal/`
- `vllm/`

## Inactive proposed state

`starbase/` contains a deterministic, digest-pinned promotion bundle for
review. It is intentionally absent from this directory's Kustomization and is
not part of Flux desired state. See its local README for the evidence boundary
and remaining activation gates.
