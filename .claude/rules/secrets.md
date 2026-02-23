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

## Pre-commit Hooks

The following hooks protect against secret leakage:
- `detect-private-key` - Catches PEM/SSH keys
- `gitleaks` - Comprehensive secret scanning
- `detect-secrets` - Pattern-based detection
- `forbid-sops-age-secret` - Blocks sops-age-secret.yaml
- `forbid-plain-age-keys` - Blocks age key files
- `check-sops-encryption` - Verifies .enc.yaml files are encrypted

## Patterns to Watch For

When writing YAML files in `infrastructure/gitops/`:
- NEVER write values that look like passwords, tokens, API keys, or connection strings
- If a value contains credentials, it MUST go in a SOPS-encrypted secret
- Connection strings with passwords (e.g., `postgresql://user:pass@host`) are ALWAYS secrets
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
