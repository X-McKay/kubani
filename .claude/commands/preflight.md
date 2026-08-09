# Preflight

Run every gate that can pass or fail before code is pushed.

## Instructions

Run these in order and report the outcome of each. Do not summarise as "passing"
unless you have seen each command exit 0.

### 1. Are the local hooks actually installed?

```bash
just hooks-check
```

Hooks are per-clone state. If this fails, nothing else on this machine is
enforced automatically — run `uv run pre-commit install` before continuing.

### 2. Secrets

```bash
just secrets-check
```

Two scans: `.enc.yaml` files really are encrypted, and no `kind: Secret`
anywhere under `infrastructure/gitops/` holds an unencrypted value.

### 3. Manifests and inventory

```bash
just validate-local
```

### 4. Drift (advisory)

```bash
just drift
```

Compares the repo's claims against reality:
- script inventories vs manifests
- docs vs manifests
- docs vs cluster (skipped without a kubeconfig)

Drift never blocks a push. Report anything it finds, and either fix the claim
or fix the reality — do not silence it.

### 5. Changed-file hooks

```bash
just check
```

## Reporting

State clearly which gates passed, which failed, and what drift was reported.
If drift is found, say what is stale and which side is wrong: the documentation
or the cluster.
