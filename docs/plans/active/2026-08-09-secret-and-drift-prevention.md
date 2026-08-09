# Secret Leak and Documentation Drift Prevention

- **Date:** 2026-08-09
- **Status:** active
- **Scope:** repo tooling, git hooks, CI, Claude Code hooks and commands

---

## Why

Two real credentials reached `main` in this repository:

- `infrastructure/gitops/infrastructure/neo4j/secret.yaml` carried `neo4j/changeme`,
  and that was the live cluster password.
- `infrastructure/gitops/infrastructure/qdrant/secret.yaml` carried a live
  `api-key` whose value contained the string `changeme`, meaning it derived from
  a bootstrap default nobody rotated.

Neither was catchable by the tooling that existed:

- `check-sops-encryption.sh` validates files already named `*.enc.yaml`. It can
  only police files someone already intended to encrypt, so a Secret committed
  as a plain `secret.yaml` is invisible to it by construction.
- `just check` runs pre-commit against changed files only, so a plaintext Secret
  that is already committed is never rescanned.
- `just setup` installs pre-commit as a git hook (justfile:13), but nothing ever
  verified the hook was actually installed. On this clone it was not, so no scan
  ran unless a human typed `just check`.

The same blindness produced documentation drift that survived for months:

- The Service Tiers table called Prometheus and Grafana "Always on" while both
  sat at `replicas: 0`.
- `validate_cluster.sh` checked `chat.almckay.io` and `gitops.almckay.io` long
  after those services were deleted in `ceec977`, reporting six failures against
  a healthy cluster.
- The Traefik README described two TCP entry points when there were four.

The shared root cause is that nothing compared a claim against reality, and
nothing ran unless invoked by hand.

## Principles

1. **Start from the artifact, not the filename.** Detection keys off
   `kind: Secret` in parsed YAML, so naming a file badly cannot hide it.
2. **Defence in depth, with one non-bypassable layer.** Local hooks catch honest
   mistakes; CI catches `--no-verify`.
3. **Drift warns, it never blocks.** Drift often needs cluster access or a
   judgement call. A blocking check that needs a kubeconfig strands you offline.
4. **The tooling must police its own installation.** A scheme that depends on
   someone having run `just setup` repeats the failure it is meant to fix.

## Design

### Shared check layer

| Tool | Cluster required | Purpose |
|---|---|---|
| `infrastructure/scripts/pre-commit/check-plaintext-secrets.py` | no | every `kind: Secret` must be SOPS-encrypted or hold no real value |
| `infrastructure/scripts/check_drift.py` | optional | three independent comparators, degrades gracefully offline |
| existing pre-commit hooks | no | gitleaks, detect-secrets, SOPS verification, yamllint |

### Drift comparators

| # | Comparison | Cluster | Catches |
|---|---|---|---|
| 1 | script inventories vs manifests | no | `validate_cluster.sh` listing retired services |
| 2 | docs vs manifests | no | READMEs naming hosts or entry points nothing defines |
| 3 | docs vs cluster | yes | tier table claiming "Always on" at `replicas: 0` |

Comparators 1 and 2 are deterministic and offline, so they run in CI.
Comparator 3 is skipped when no cluster is reachable.

### Enforcement layers

| Layer | Trigger | Blocks on | Bypass |
|---|---|---|---|
| pre-commit git hook | `git commit`, changed files | secrets | `--no-verify` |
| pre-push git hook | `git push`, whole tree | secrets | `--no-verify` |
| GitHub Actions | push and PR | secrets, `validate-local` | none |
| Claude `PreToolUse` guard | agent runs `git commit`/`git push` | secrets | n/a |

Drift is warn-only at every layer.

The Claude guard runs only the fast Python secret scan rather than full
pre-commit, so it stays inside the hook timeout.

### Credential handling

SOPS remains the single source of truth for the FalkorDB and Qdrant credentials.
They are not copied into any other store. Retrieval is documented in
`.claude/rules/secrets.md`:

```bash
SOPS_AGE_KEY_FILE=age.key sops -d \
  infrastructure/gitops/infrastructure/falkordb/secret.enc.yaml
```

## Explicitly out of scope

- **External Secrets Operator / Vault.** SOPS works; this would be a large
  migration for unclear benefit at homelab scale.
- **`git-filter-repo` history purge.** The old Neo4j and Qdrant values remain in
  history. Both are now rotated and inert, so this is a separate decision.
- **Branch protection on `main`.** Flux tracks `main`, so requiring pull requests
  changes the deployment model and deserves its own discussion.

## Known limitations

- `--no-verify` bypasses both git hooks. CI is the backstop.
- CI runs without `age.key`, so it can prove files are encrypted but can never
  verify they decrypt. Decryption is proven by Flux reconciling successfully.
- Comparator 3 cannot run in CI without cluster access, so a tier-table drift is
  caught locally and by scheduled runs, not on pull requests.
