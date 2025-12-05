# SOPS and Age Encryption Setup

This guide explains how to set up SOPS (Secrets OPerationS) with age encryption for managing encrypted secrets in your GitOps repository.

## Prerequisites

- `age` installed: `brew install age` (macOS) or see https://github.com/FiloSottile/age
- `sops` installed: `brew install sops` (macOS) or see https://github.com/getsops/sops
- `kubectl` configured to access your cluster
- Flux CD installed in your cluster

## Quick Setup

Run the automated setup script:

```bash
python scripts/setup_sops.py
```

This will:
1. Generate an age key pair
2. Create `.sops.yaml` configuration file
3. Create a Kubernetes secret manifest for Flux
4. Provide next steps

## Manual Setup

### 1. Generate Age Key Pair

```bash
age-keygen -o age.key
```

This creates a file with:
- Private key: `AGE-SECRET-KEY-1...`
- Public key: `age1...` (shown in comments)

**⚠️ IMPORTANT**: Keep `age.key` secure and backed up! Without it, you cannot decrypt your secrets.

### 2. Create .sops.yaml Configuration

Create `.sops.yaml` in your repository root:

```yaml
creation_rules:
  - path_regex: \.enc\.yaml$
    encrypted_regex: ^(data|stringData)$
    age: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p  # Your public key
```

This tells SOPS to:
- Encrypt files ending in `.enc.yaml`
- Only encrypt the `data` and `stringData` fields (leave metadata readable)
- Use your age public key for encryption

### 3. Create Kubernetes Secret for Flux

Create a secret containing your age private key:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: sops-age
  namespace: flux-system
type: Opaque
stringData:
  age.agekey: |
    # Your age private key from age.key
    AGE-SECRET-KEY-1...
```

Apply it to your cluster:

```bash
kubectl apply -f sops-age-secret.yaml
```

### 4. Configure Flux Kustomization

Update your Flux Kustomization resources to enable SOPS decryption:

```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: apps
  namespace: flux-system
spec:
  interval: 10m0s
  path: ./gitops/apps
  prune: true
  sourceRef:
    kind: GitRepository
    name: flux-system
  decryption:
    provider: sops
    secretRef:
      name: sops-age
```

## Using SOPS

### Encrypting a Secret

Create a plain Kubernetes secret:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgresql-credentials
  namespace: database
type: Opaque
stringData:
  postgres-password: supersecret123
  username: myapp
  password: myapppassword
```

Encrypt it with SOPS:

```bash
sops --encrypt secret.yaml > secret.enc.yaml
```

The encrypted file will have:
- Readable metadata (apiVersion, kind, metadata.name, etc.)
- Encrypted data fields
- SOPS metadata section with encryption details

### Editing Encrypted Secrets

Edit an encrypted secret in place:

```bash
sops secret.enc.yaml
```

SOPS will:
1. Decrypt the file
2. Open it in your editor
3. Re-encrypt it when you save and exit

### Decrypting for Viewing

View a decrypted secret without editing:

```bash
sops --decrypt secret.enc.yaml
```

### Rotating Keys

If you need to rotate your age key:

1. Generate a new age key pair
2. Update `.sops.yaml` with the new public key
3. Re-encrypt all secrets with the new key:

```bash
sops updatekeys secret.enc.yaml
```

4. Update the `sops-age` secret in your cluster with the new private key
5. Commit the re-encrypted secrets to Git

## File Naming Convention

- Encrypted secrets: `*.enc.yaml`
- Plain manifests: `*.yaml`

This allows SOPS to automatically detect which files to encrypt based on the `.sops.yaml` configuration.

## Example: PostgreSQL Credentials

1. Create the secret:

```yaml
# gitops/apps/postgresql/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgresql-credentials
  namespace: database
type: Opaque
stringData:
  postgres-password: changeme123
  username: postgres
  password: userpassword
  database: myapp
```

2. Encrypt it:

```bash
sops --encrypt gitops/apps/postgresql/secret.yaml > gitops/apps/postgresql/secret.enc.yaml
```

3. Delete the plain file:

```bash
rm gitops/apps/postgresql/secret.yaml
```

4. Commit the encrypted file:

```bash
git add gitops/apps/postgresql/secret.enc.yaml .sops.yaml
git commit -m "Add encrypted PostgreSQL credentials"
git push
```

5. Flux will automatically decrypt and apply the secret to your cluster.

## Troubleshooting

### "no key could be found to decrypt the data"

- Verify the `sops-age` secret exists in the `flux-system` namespace
- Verify the secret contains the correct private key
- Check Flux Kustomization has `decryption.provider: sops` configured

### "failed to get the data key"

- Verify your `.sops.yaml` configuration is correct
- Ensure you're using the correct age public key
- Try re-encrypting the secret

### "age: error: failed to decrypt"

- The private key doesn't match the public key used for encryption
- Re-encrypt the secret with the correct public key

## Security Best Practices

1. **Never commit unencrypted secrets** to Git
2. **Keep age.key secure** - store it in a password manager or secure vault
3. **Backup age.key** - without it, you cannot decrypt your secrets
4. **Rotate keys periodically** - update age keys every 6-12 months
5. **Use separate keys** for different environments (dev, staging, prod)
6. **Restrict access** to the `sops-age` secret in Kubernetes

## References

- [SOPS Documentation](https://github.com/getsops/sops)
- [Age Encryption](https://github.com/FiloSottile/age)
- [Flux SOPS Integration](https://fluxcd.io/flux/guides/mozilla-sops/)
