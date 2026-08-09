# Secret Management Rules

When working with secrets and encryption:

## Critical Rules

- **NEVER** create or modify files containing plaintext secrets
- **NEVER** commit `sops-age-secret.yaml` - it must only be applied via kubectl from stdin
- **NEVER** commit age key files (`age.key`, `*.agekey`, etc.)
- **ALWAYS** encrypt secrets with SOPS before committing (use `.enc.yaml` extension)
- **ALWAYS** verify SOPS files contain `sops:` and `age:` metadata before committing

## Age Key Management

- Age private keys live in `age.key` (gitignored)
- Age public keys go in `.sops.yaml`
- To apply SOPS key to cluster: `cat <<EOF | kubectl apply -f -` (stdin only, never write to file)
- Backup old keys with date suffix: `age.key.old.YYYYMMDD` (gitignored via `*.key.*`)

## SOPS Workflow

```bash
# Encrypt a new secret
SOPS_AGE_KEY_FILE=age.key sops --encrypt secret.yaml > secret.enc.yaml

# Edit encrypted secret
SOPS_AGE_KEY_FILE=age.key sops secret.enc.yaml

# Rotate keys (after key compromise)
./scripts/rotate_sops_keys.sh
```

## Enforcement Layers

Four layers, because each catches what the others cannot:

| Layer | Runs | Blocks on | Bypass |
|---|---|---|---|
| pre-commit git hook | `git commit`, changed files | secrets | `--no-verify` |
| pre-push git hook | `git push`, whole tree | secrets | `--no-verify` |
| GitHub Actions | push and PR | secrets, kustomize, inventory | none |
| Claude `pre-git.sh` guard | agent runs `git commit`/`git push` | secrets | n/a |

Drift reporting is advisory at every layer and never blocks.

Hooks are per-clone state. `just hooks-check` (also part of `just validate-local`)
asserts they are installed, because on at least one clone they were not and every
scan silently depended on someone typing `just check`.

## Pre-commit Hooks

The following hooks protect against secret leakage:
- `detect-private-key` - Catches PEM/SSH keys
- `gitleaks` - Comprehensive secret scanning
- `detect-secrets` - Pattern-based detection
- `forbid-sops-age-secret` - Blocks sops-age-secret.yaml
- `forbid-plain-age-keys` - Blocks age key files
- `check-sops-encryption` - Verifies `.enc.yaml` files are encrypted
- `check-plaintext-secrets` - Verifies **any** `kind: Secret` is encrypted,
  regardless of filename

The last two are not redundant. `check-sops-encryption` starts from the
filename, so it only ever polices files someone already meant to encrypt; a
Secret committed as a plain `secret.yaml` is invisible to it. That is exactly
how a live Qdrant API key and a Neo4j password reached this repository.
`check-plaintext-secrets` starts from `kind: Secret` in parsed YAML instead.

## Retrieving a Secret Value

SOPS is the single source of truth. Values are not duplicated into any other
store, so read them from the encrypted file when needed:

```bash
SOPS_AGE_KEY_FILE=age.key sops -d \
  infrastructure/gitops/infrastructure/falkordb/secret.enc.yaml

SOPS_AGE_KEY_FILE=age.key sops -d \
  infrastructure/gitops/infrastructure/qdrant/secret.enc.yaml
```

Never redirect that output into a file inside the repository.

## Rotating a Credential

1. Generate an alphanumeric value. Some consumers word-split their config —
   FalkorDB's entrypoint expands `REDIS_ARGS` unquoted — so shell
   metacharacters can break the container.
2. Write the plaintext **outside** the repo, named `secret.enc.yaml` so the
   `.sops.yaml` creation rule matches on the input filename.
3. `SOPS_AGE_KEY_FILE=age.key sops --encrypt <staged> > <target>.enc.yaml`
4. `shred -u <staged>`
5. Reference the `.enc.yaml` from `kustomization.yaml` and delete any plaintext.
6. Commit, push, reconcile, then **restart the consuming workload**. Env vars
   from `secretKeyRef` do not hot-reload, so Flux updating the Secret alone
   leaves the old value live in the running pod.
7. Verify the new credential is accepted and the old one is rejected.

## Patterns to Watch For

When writing YAML files in `infrastructure/gitops/`:
- NEVER write values that look like passwords, tokens, API keys, or connection strings
- If a value contains credentials, it MUST go in a SOPS-encrypted secret
- Connection strings with passwords (e.g., `postgresql://user:pass@host`) are ALWAYS secrets  # pragma: allowlist secret
- Base64-encoded data in Kubernetes secrets MUST use SOPS encryption

Common secret locations:
- `infrastructure/gitops/apps/*/secret*.yaml` — Must be `.enc.yaml`
- `config/local.yaml` — Gitignored, but never commit credentials even here
- `.env` files — Gitignored, credentials belong here for local dev only

## When Creating New Secrets

1. Create the secret YAML with placeholder values
2. Encrypt with SOPS: `SOPS_AGE_KEY_FILE=age.key sops --encrypt secret.yaml > secret.enc.yaml`
3. Delete the plaintext file
4. Commit only the `.enc.yaml` file

## If You Discover a Secret in Git

1. **STOP** - Do not push if not already pushed
2. Rotate the compromised secret immediately
3. Use `git-filter-repo` to purge from history
4. Force push the cleaned history
5. Update the secret in the cluster
6. Review and strengthen pre-commit hooks
