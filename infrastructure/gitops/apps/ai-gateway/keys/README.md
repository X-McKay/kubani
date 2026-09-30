# Gateway keys (Phase 3, not staged yet)

This directory is a placeholder. No key material exists here and none should
be added except through the SOPS workflow described below.

Roadmap Phase 3 (`3.2` in
`docs/plans/ideas/2026-09-29-inference-platform-roadmap.md`) introduces
agentgateway virtual keys: one API key per agent/workstream, each with a
token budget, issued via the `just gateway-key <name>` recipe described in
the roadmap (section 10.2). That recipe generates a key, encrypts it with
SOPS straight into this directory as a `<name>.enc.yaml` Secret, and prints
the kustomize line to add.

Until that recipe exists and is run:

- **Never** write a plaintext key, token, or `kind: Secret` manifest in this
  directory or anywhere else in the repo (see `.claude/rules/secrets.md`).
- The `ai.almckay.io` listener runs without API-key auth through stage 2.5 of
  the rollout — the same posture `llm.almckay.io` has today (tailnet-only
  reachability is the mitigation; see
  `docs/infrastructure/decisions.md`'s "vLLM API key is deferred" entry).
- When Phase 3 lands, each key file here must be `.enc.yaml`, referenced from
  `kustomization.yaml` only after it exists, and verified with
  `SOPS_AGE_KEY_FILE=age.key sops -d <file>` before it is trusted to contain
  real ciphertext.
