# Agent registry catalog feed

The catalog feed is one JSON file that describes this cluster to the agent
registry service: tenants and their signer pins, trusted source repositories,
tool servers, model engines and model aliases. The registry service reads the
file; this repository only renders it.

Inputs:

- `catalog.yaml` is the only hand-written input. It names what a manifest cannot
  say: which Deployment and container is each tool server, which backend and
  gateway name each one uses, and which engine each alias points at.
- Everything else is read from committed files: image references and
  digests from the named manifest, served model names from
  `apps/vllm/model-config.yaml`, gateway model routes from
  `apps/ai-gateway/agents/backends.yaml`, tenant pins and source repositories
  from `apps/agents/` and the Kyverno tenant-signers ConfigMap.

Render and check (the output is deterministic):

```bash
uv run --locked python infrastructure/scripts/ops/registry_feed.py render --write
uv run --locked python infrastructure/scripts/ops/registry_feed.py render --check
```

The generated file is
`infrastructure/gitops/apps/agent-platform/workloads/agent-registry-feed.json`.
Do not edit it by hand. A failed check names the entry and file in its message.

Rules the renderer enforces:

- every `infrastructure/mcp/backends/<x>.yaml` is named by exactly one tool
  server, and every tool server backend has its file;
- a model engine with a backend must match its gateway `agents-<backend>`
  model to its served name;
- an alias must name an engine that has a backend.

Tests: `tests/test_registry_feed.py`.
