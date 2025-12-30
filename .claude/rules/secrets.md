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

## If You Discover a Secret in Git

1. **STOP** - Do not push if not already pushed
2. Rotate the compromised secret immediately
3. Use `git-filter-repo` to purge from history
4. Force push the cleaned history
5. Update the secret in the cluster
6. Review and strengthen pre-commit hooks
