# Secrets Management Guide

This comprehensive guide covers secrets management for the Kubernetes cluster using SOPS (Secrets OPerationS) with age encryption. It provides step-by-step instructions for generating encryption keys, encrypting secrets, managing credentials, and troubleshooting common issues.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Age Key Generation](#age-key-generation)
- [SOPS Encryption Workflow](#sops-encryption-workflow)
- [Editing Encrypted Secrets](#editing-encrypted-secrets)
- [Credential Rotation](#credential-rotation)
- [Flux SOPS Integration](#flux-sops-integration)
- [Troubleshooting](#troubleshooting)
- [Security Best Practices](#security-best-practices)
- [Reference](#reference)

## Overview

SOPS (Secrets OPerationS) is a tool for encrypting secrets in Git repositories. It uses age encryption to ensure that sensitive data like passwords, API tokens, and certificates can be safely stored in version control while remaining secure.

**Key Benefits**:
- **GitOps-Friendly**: Encrypted secrets can be committed to Git safely
- **Selective Encryption**: Only encrypts sensitive fields, leaving metadata readable
- **Audit Trail**: Git history tracks all changes to secrets
- **Automated Decryption**: Flux automatically decrypts secrets during deployment
- **Key Management**: Simple age key pair management

**How It Works**:
1. Generate an age key pair (public key for encryption, private key for decryption)
2. Configure SOPS to use the age public key for encryption
3. Encrypt Kubernetes secrets using SOPS before committing to Git
4. Store the age private key in the cluster as a Kubernetes secret
5. Configure Flux to decrypt secrets automatically using the private key
6. Flux applies decrypted secrets to the cluster

## Prerequisites

Before you begin, ensure you have the following tools installed:

**Required Tools**:

- **age**: Modern encryption tool
  ```bash
  # macOS
  brew install age

  # Linux
  # Download from https://github.com/FiloSottile/age/releases
  ```

- **sops**: Secrets encryption tool
  ```bash
  # macOS
  brew install sops

  # Linux
  # Download from https://github.com/getsops/sops/releases
  ```

- **kubectl**: Kubernetes command-line tool (configured to access your cluster)
- **Python 3.11+**: For automation scripts (optional but recommended)

**Verify Installation**:
```bash
age --version
sops --version
kubectl version --client
```

## Age Key Generation

Age encryption uses a key pair: a public key for encryption and a private key for decryption. The public key can be shared freely, while the private key must be kept secure.

### Automated Setup (Recommended)

Use the provided setup script to generate keys and configure SOPS automatically:

```bash
# From the repository root
uv run python scripts/setup_sops.py
```

This script will:
1. Generate an age key pair
2. Save the private key to `age.key` (with restricted permissions)
3. Create `.sops.yaml` configuration file
4. Generate a Kubernetes secret manifest (`sops-age-secret.yaml`)
5. Provide next steps for applying the secret to your cluster

**Output Example**:
```
🔐 Setting up SOPS and age encryption infrastructure...

📝 Step 1: Generating age key pair...
✅ Age key pair generated successfully
   Public key: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p

📝 Step 2: Saving age private key to age.key...
✅ Private key saved to age.key
   ⚠️  Keep this file secure! It's needed to decrypt secrets.

📝 Step 3: Creating SOPS configuration at .sops.yaml...
✅ SOPS configuration created at .sops.yaml

📝 Step 4: Creating Kubernetes secret manifest at sops-age-secret.yaml...
✅ Kubernetes secret manifest created at sops-age-secret.yaml
```

### Manual Setup

If you prefer to set up manually or need to understand the process:

#### 1. Generate Age Key Pair

```bash
age-keygen -o age.key
```

**Output**:
```
# created: 2024-12-04T10:30:00Z
# public key: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQS
```

The file contains:
- **Public key**: Shown in the comment (starts with `age1`)
- **Private key**: The actual key content (starts with `AGE-SECRET-KEY-1`)

#### 2. Secure the Private Key

```bash
# Restrict file permissions (owner read/write only)
chmod 600 age.key

# Backup the key to a secure location
# IMPORTANT: Without this key, you cannot decrypt your secrets!
```

**Recommended Backup Locations**:
- Password manager (1Password, Bitwarden, etc.)
- Encrypted USB drive
- Secure cloud storage (encrypted)
- Hardware security module (HSM)

#### 3. Extract the Public Key

```bash
# Extract public key from age.key
grep "public key:" age.key | cut -d' ' -f4
```

Save this public key - you'll need it for the SOPS configuration.

### Key Format Validation

Age keys have specific formats that must be validated:

**Public Key Format**:
- Starts with `age1`
- Followed by bech32-encoded data
- Example: `age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p`

**Private Key Format**:
- Starts with `AGE-SECRET-KEY-1`
- Followed by bech32-encoded data (uppercase)
- Example: `AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQS`

**Validation Script**:
```python
from cluster_manager.secrets import is_valid_age_public_key, is_valid_age_private_key

# Validate keys
public_key = "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p"
private_key = "AGE-SECRET-KEY-1QYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQSZQGPQYQS"

assert is_valid_age_public_key(public_key)
assert is_valid_age_private_key(private_key)
```

## SOPS Encryption Workflow

This section covers the complete workflow for encrypting secrets with SOPS.

### 1. Configure SOPS

Create a `.sops.yaml` file in your repository root to define encryption rules:

```yaml
# .sops.yaml
creation_rules:
  - path_regex: \.enc\.yaml$
    encrypted_regex: ^(data|stringData)$
    age: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
```

**Configuration Explanation**:
- `path_regex`: Only encrypt files ending in `.enc.yaml`
- `encrypted_regex`: Only encrypt `data` and `stringData` fields (leave metadata readable)
- `age`: Your age public key for encryption

**Why This Matters**:
- Metadata remains readable in Git (apiVersion, kind, metadata.name, etc.)
- Only sensitive data is encrypted
- Easy to review changes in pull requests
- Tools can still parse the file structure

### 2. Create a Kubernetes Secret

Create a plain Kubernetes secret manifest:

```yaml
# Example: gitops/apps/postgresql/secret.yaml
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
  database: myapp
```

### 3. Encrypt the Secret

Encrypt the secret using SOPS:

```bash
sops --encrypt gitops/apps/postgresql/secret.yaml > gitops/apps/postgresql/secret.enc.yaml
```

**Alternative (using .sops.yaml config)**:
```bash
# SOPS will automatically use .sops.yaml configuration
sops --encrypt secret.yaml > secret.enc.yaml
```

**Encrypted Output Example**:
```yaml
apiVersion: v1
kind: Secret
metadata:
    name: postgresql-credentials
    namespace: database
type: Opaque
stringData:
    postgres-password: ENC[AES256_GCM,data:8h3j2k1...,iv:...,tag:...,type:str]
    username: ENC[AES256_GCM,data:m4y5a6p...,iv:...,tag:...,type:str]
    password: ENC[AES256_GCM,data:p7a8s9s...,iv:...,tag:...,type:str]
    database: ENC[AES256_GCM,data:d1a2t3a...,iv:...,tag:...,type:str]
sops:
    kms: []
    gcp_kms: []
    azure_kv: []
    hc_vault: []
    age:
        - recipient: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
          enc: |
            -----BEGIN AGE ENCRYPTED FILE-----
            ...
            -----END AGE ENCRYPTED FILE-----
    lastmodified: "2024-12-04T10:30:00Z"
    mac: ENC[AES256_GCM,data:...,iv:...,tag:...,type:str]
    pgp: []
    version: 3.8.1
```

**Notice**:
- Metadata fields are readable (apiVersion, kind, metadata)
- Only stringData values are encrypted
- SOPS metadata section contains encryption details

### 4. Delete the Plain Secret

**IMPORTANT**: Never commit unencrypted secrets to Git!

```bash
# Delete the plain secret file
rm gitops/apps/postgresql/secret.yaml

# Verify only encrypted file exists
ls gitops/apps/postgresql/
# Output: secret.enc.yaml
```

### 5. Commit to Git

```bash
# Add encrypted secret and SOPS config
git add gitops/apps/postgresql/secret.enc.yaml .sops.yaml

# Commit with descriptive message
git commit -m "Add encrypted PostgreSQL credentials"

# Push to repository
git push
```

### Automated Secret Generation

Use the provided script to generate all production service secrets:

```bash
# Generate all secrets with auto-generated passwords
uv run python scripts/create_encrypted_secrets.py \
  --cloudflare-token "your-api-token" \
  --cloudflare-email "your-email@example.com" \
  --cloudflare-zone-id "your-zone-id"
```

This creates encrypted secrets for:
- PostgreSQL (database credentials)
- Redis (authentication password)
- Authentik (application secrets)
- Cloudflare (API token for cert-manager)

**Output**:
```
📝 Creating service credentials...

1. Creating PostgreSQL credentials...
   ✅ Created encrypted secret at gitops/apps/postgresql/secret.enc.yaml
   Database: authentik
   Username: authentik
   Password: xK9mP2... (truncated)

2. Creating Redis credentials...
   ✅ Created encrypted secret at gitops/apps/redis/secret.enc.yaml
   Password: yL3nQ8... (truncated)

3. Creating Authentik credentials...
   ✅ Created encrypted secret at gitops/apps/authentik/secret.enc.yaml
   Secret key: zM4oR7... (truncated)
   Bootstrap password: aB5pS1... (truncated)

4. Creating Cloudflare API token secret...
   ✅ Created encrypted secret at gitops/infrastructure/cert-manager/cloudflare-secret.enc.yaml
```

## Editing Encrypted Secrets

SOPS provides a convenient way to edit encrypted secrets in place without manually decrypting and re-encrypting.

### Edit in Place

```bash
# Edit encrypted secret
sops gitops/apps/postgresql/secret.enc.yaml
```

**What Happens**:
1. SOPS decrypts the file using your age private key
2. Opens the decrypted content in your default editor (set via `$EDITOR`)
3. When you save and exit, SOPS re-encrypts the file automatically
4. The encrypted file is updated with your changes

### Set Your Editor

```bash
# Set default editor (add to ~/.bashrc or ~/.zshrc)
export EDITOR=vim        # or nano, emacs, code, etc.

# For VS Code
export EDITOR="code --wait"

# For Sublime Text
export EDITOR="subl --wait"
```

### View Without Editing

To view a decrypted secret without editing:

```bash
# Decrypt and display
sops --decrypt gitops/apps/postgresql/secret.enc.yaml

# Decrypt and pipe to less
sops --decrypt gitops/apps/postgresql/secret.enc.yaml | less

# Extract specific field
sops --decrypt --extract '["stringData"]["postgres-password"]' \
  gitops/apps/postgresql/secret.enc.yaml
```

### Edit Specific Fields

```bash
# Set a specific field value
sops --set '["stringData"]["postgres-password"] "newpassword123"' \
  gitops/apps/postgresql/secret.enc.yaml
```

### Validate After Editing

After editing, validate the secret is still valid:

```bash
# Validate YAML syntax
sops --decrypt gitops/apps/postgresql/secret.enc.yaml | kubectl apply --dry-run=client -f -

# Check if decryption works
sops --decrypt gitops/apps/postgresql/secret.enc.yaml > /dev/null && echo "✅ Valid"
```

## Credential Rotation

Regular credential rotation is a security best practice. This section covers procedures for rotating secrets.

### When to Rotate Credentials

**Scheduled Rotation**:
- Every 90 days for production secrets
- Every 180 days for development secrets
- Annually for age encryption keys

**Immediate Rotation Required**:
- Suspected credential compromise
- Employee/contractor offboarding
- Security incident or breach
- Compliance requirements

### Rotating Service Credentials

#### PostgreSQL Password Rotation

1. **Generate new password**:
```python
from cluster_manager.secrets import generate_secure_password
new_password = generate_secure_password()
print(new_password)
```

2. **Update encrypted secret**:
```bash
# Edit the secret
sops gitops/apps/postgresql/secret.enc.yaml

# Update the password field, save and exit
```

3. **Commit the change**:
```bash
git add gitops/apps/postgresql/secret.enc.yaml
git commit -m "Rotate PostgreSQL password"
git push
```

4. **Wait for Flux to apply** (or force reconciliation):
```bash
# Force Flux to reconcile immediately
flux reconcile kustomization apps --with-source
```

5. **Restart PostgreSQL pods** to pick up new secret:
```bash
kubectl rollout restart statefulset/postgresql -n database
```

6. **Update dependent services** (e.g., Authentik):
```bash
# Update Authentik's database password
sops gitops/apps/authentik/secret.enc.yaml
# Update postgres-password field to match new PostgreSQL password

# Commit and push
git add gitops/apps/authentik/secret.enc.yaml
git commit -m "Update Authentik database password"
git push

# Restart Authentik
kubectl rollout restart deployment/authentik -n auth
```

#### Redis Password Rotation

1. **Update encrypted secret**:
```bash
sops gitops/apps/redis/secret.enc.yaml
# Update redis-password field
```

2. **Commit and push**:
```bash
git add gitops/apps/redis/secret.enc.yaml
git commit -m "Rotate Redis password"
git push
```

3. **Restart Redis**:
```bash
kubectl rollout restart statefulset/redis-master -n cache
```

4. **Update client applications** with new password

#### Cloudflare API Token Rotation

1. **Generate new token in Cloudflare**:
   - Log in to Cloudflare dashboard
   - Go to My Profile → API Tokens
   - Create new token with Zone:DNS:Edit permissions
   - Copy the new token

2. **Update encrypted secret**:
```bash
sops gitops/infrastructure/cert-manager/cloudflare-secret.enc.yaml
# Update api-token field
```

3. **Commit and push**:
```bash
git add gitops/infrastructure/cert-manager/cloudflare-secret.enc.yaml
git commit -m "Rotate Cloudflare API token"
git push
```

4. **Restart cert-manager** (optional, it will pick up changes automatically):
```bash
kubectl rollout restart deployment/cert-manager -n cert-manager
```

### Rotating Age Encryption Keys

Rotating the age key pair requires re-encrypting all secrets.

**⚠️ WARNING**: This is a sensitive operation. Ensure you have backups before proceeding.

#### Step-by-Step Process

1. **Generate new age key pair**:
```bash
# Generate new key
age-keygen -o age-new.key

# Extract new public key
grep "public key:" age-new.key | cut -d' ' -f4
```

2. **Update .sops.yaml with new public key**:
```yaml
creation_rules:
  - path_regex: \.enc\.yaml$
    encrypted_regex: ^(data|stringData)$
    age: age1NEW_PUBLIC_KEY_HERE
```

3. **Re-encrypt all secrets**:
```bash
# Find all encrypted secrets
find gitops -name "*.enc.yaml" -type f | while read file; do
  echo "Re-encrypting $file..."

  # Decrypt with old key, encrypt with new key
  SOPS_AGE_KEY_FILE=age.key sops --decrypt "$file" | \
  SOPS_AGE_KEY_FILE=age-new.key sops --encrypt --age age1NEW_PUBLIC_KEY_HERE /dev/stdin > "$file.new"

  # Replace old file
  mv "$file.new" "$file"
done
```

4. **Update Kubernetes secret**:
```bash
# Create new secret manifest
kubectl create secret generic sops-age \
  --from-file=age.agekey=age-new.key \
  --namespace=flux-system \
  --dry-run=client -o yaml > sops-age-secret-new.yaml

# Apply to cluster
kubectl apply -f sops-age-secret-new.yaml
```

5. **Verify Flux can decrypt**:
```bash
# Check Flux Kustomization status
kubectl get kustomization -n flux-system

# Force reconciliation
flux reconcile kustomization apps --with-source
```

6. **Commit changes**:
```bash
git add .sops.yaml gitops/
git commit -m "Rotate age encryption key"
git push
```

7. **Backup and secure new key**:
```bash
# Backup new key
cp age-new.key age.key

# Securely delete old key
shred -u age-old.key  # Linux
# or
rm -P age-old.key     # macOS
```

## Flux SOPS Integration

Flux CD automatically decrypts SOPS-encrypted secrets during reconciliation.

### Configure Flux Kustomization

Update your Flux Kustomization resources to enable SOPS decryption:

```yaml
# gitops/flux-system/apps-kustomization.yaml
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

**Key Configuration**:
- `decryption.provider: sops`: Enable SOPS decryption
- `decryption.secretRef.name: sops-age`: Reference to secret containing age private key

### Create Age Private Key Secret

The age private key must be stored in the cluster as a Kubernetes secret:

```bash
# Create secret from age.key file
kubectl create secret generic sops-age \
  --from-file=age.agekey=age.key \
  --namespace=flux-system

# Verify secret exists
kubectl get secret sops-age -n flux-system
```

**Alternative: Apply from manifest**:
```bash
# Use the generated manifest from setup script
kubectl apply -f sops-age-secret.yaml
```

### Verify Flux Decryption

Check that Flux can decrypt secrets:

```bash
# Check Kustomization status
kubectl get kustomization apps -n flux-system

# View detailed status
kubectl describe kustomization apps -n flux-system

# Check for decryption errors
kubectl logs -n flux-system -l app=kustomize-controller
```

**Successful Output**:
```
NAME   READY   STATUS                       AGE
apps   True    Applied revision: main/abc123 5m
```

**Failed Decryption**:
```
NAME   READY   STATUS                                    AGE
apps   False   decryption failed: no key could be found  5m
```

### Force Reconciliation

To immediately apply changes after updating secrets:

```bash
# Reconcile with source update
flux reconcile kustomization apps --with-source

# Watch reconciliation progress
flux get kustomizations --watch
```

### Debugging Decryption Issues

If Flux cannot decrypt secrets:

1. **Verify age secret exists**:
```bash
kubectl get secret sops-age -n flux-system
```

2. **Check secret content**:
```bash
kubectl get secret sops-age -n flux-system -o jsonpath='{.data.age\.agekey}' | base64 -d
```

3. **Verify Kustomization configuration**:
```bash
kubectl get kustomization apps -n flux-system -o yaml | grep -A 5 decryption
```

4. **Check controller logs**:
```bash
kubectl logs -n flux-system -l app=kustomize-controller --tail=100
```

## Troubleshooting

Common issues and their solutions.

### Error: "no key could be found to decrypt the data"

**Cause**: Flux cannot find the age private key to decrypt secrets.

**Solutions**:

1. **Verify sops-age secret exists**:
```bash
kubectl get secret sops-age -n flux-system
```

If missing, create it:
```bash
kubectl create secret generic sops-age \
  --from-file=age.agekey=age.key \
  --namespace=flux-system
```

2. **Verify Kustomization references the secret**:
```bash
kubectl get kustomization apps -n flux-system -o yaml | grep -A 3 decryption
```

Should show:
```yaml
decryption:
  provider: sops
  secretRef:
    name: sops-age
```

3. **Verify secret contains correct key**:
```bash
# Extract and validate key format
kubectl get secret sops-age -n flux-system -o jsonpath='{.data.age\.agekey}' | \
  base64 -d | head -1
```

Should start with `AGE-SECRET-KEY-1`

### Error: "failed to get the data key"

**Cause**: The age public key in `.sops.yaml` doesn't match the private key in the cluster.

**Solutions**:

1. **Verify public key in .sops.yaml**:
```bash
grep "age:" .sops.yaml
```

2. **Extract public key from private key**:
```bash
# From age.key file
grep "public key:" age.key

# From cluster secret
kubectl get secret sops-age -n flux-system -o jsonpath='{.data.age\.agekey}' | \
  base64 -d | grep "public key:"
```

3. **Re-encrypt secrets with correct key**:
```bash
# Update .sops.yaml with correct public key
# Then re-encrypt all secrets
find gitops -name "*.enc.yaml" -exec sops updatekeys {} \;
```

### Error: "age: error: failed to decrypt"

**Cause**: The private key doesn't match the public key used for encryption.

**Solutions**:

1. **Verify you're using the correct age.key file**
2. **Check if keys were rotated** - you may need the old key to decrypt
3. **Re-encrypt with current key**:
```bash
# Decrypt with old key (if available)
SOPS_AGE_KEY_FILE=age-old.key sops --decrypt secret.enc.yaml > secret.yaml

# Encrypt with current key
sops --encrypt secret.yaml > secret.enc.yaml
```

### Error: "MAC mismatch"

**Cause**: The encrypted file has been corrupted or tampered with.

**Solutions**:

1. **Restore from Git history**:
```bash
git log --oneline -- gitops/apps/postgresql/secret.enc.yaml
git checkout <commit-hash> -- gitops/apps/postgresql/secret.enc.yaml
```

2. **Re-create the secret**:
```bash
# Create new plain secret
# Encrypt with SOPS
# Commit to Git
```

### Error: "sops: command not found"

**Cause**: SOPS is not installed or not in PATH.

**Solutions**:

```bash
# macOS
brew install sops

# Linux - download from GitHub
wget https://github.com/getsops/sops/releases/download/v3.8.1/sops-v3.8.1.linux.amd64
chmod +x sops-v3.8.1.linux.amd64
sudo mv sops-v3.8.1.linux.amd64 /usr/local/bin/sops

# Verify installation
sops --version
```

### Error: "age: command not found"

**Cause**: Age is not installed or not in PATH.

**Solutions**:

```bash
# macOS
brew install age

# Linux - download from GitHub
wget https://github.com/FiloSottile/age/releases/download/v1.1.1/age-v1.1.1-linux-amd64.tar.gz
tar xzf age-v1.1.1-linux-amd64.tar.gz
sudo mv age/age* /usr/local/bin/

# Verify installation
age --version
```

### Secrets Not Applied to Cluster

**Cause**: Flux hasn't reconciled or there's a decryption error.

**Solutions**:

1. **Check Kustomization status**:
```bash
flux get kustomizations
```

2. **Force reconciliation**:
```bash
flux reconcile kustomization apps --with-source
```

3. **Check for errors**:
```bash
kubectl describe kustomization apps -n flux-system
```

4. **Verify secret exists in namespace**:
```bash
kubectl get secret postgresql-credentials -n database
```

### Permission Denied When Reading age.key

**Cause**: File permissions are too restrictive or you don't own the file.

**Solutions**:

```bash
# Fix ownership
sudo chown $USER:$USER age.key

# Fix permissions
chmod 600 age.key
```

## Security Best Practices

Follow these best practices to maintain secure secrets management.

### Key Management

1. **Never commit unencrypted secrets** to Git
   ```bash
   # Add to .gitignore
   echo "age.key" >> .gitignore
   echo "*.yaml" >> .gitignore  # Only commit .enc.yaml files
   echo "!*.enc.yaml" >> .gitignore
   ```

2. **Keep age.key secure**
   - Store in password manager
   - Backup to encrypted storage
   - Never share via email or chat
   - Use separate keys for different environments

3. **Restrict access to age private key**
   ```bash
   chmod 600 age.key
   ```

4. **Rotate keys regularly**
   - Production: Every 90 days
   - Development: Every 180 days
   - After any suspected compromise

### Secret Hygiene

1. **Use strong passwords**
   ```python
   from cluster_manager.secrets import generate_secure_password
   password = generate_secure_password(length=32)
   ```

2. **Avoid default credentials**
   - Never use "admin", "password", "changeme"
   - Generate unique passwords for each service

3. **Minimize secret scope**
   - Use separate secrets for each service
   - Don't reuse passwords across services
   - Use namespace isolation

4. **Audit secret access**
   ```bash
   # Check who can access secrets
   kubectl auth can-i get secrets --namespace=database --as=system:serviceaccount:default:default
   ```

### Git Repository Security

1. **Enable branch protection**
   - Require pull request reviews
   - Require status checks to pass
   - Restrict who can push to main

2. **Use signed commits**
   ```bash
   git config --global commit.gpgsign true
   ```

3. **Review encrypted secret changes**
   ```bash
   # View decrypted diff
   git diff gitops/apps/postgresql/secret.enc.yaml | \
     sops --decrypt /dev/stdin
   ```

4. **Scan for leaked secrets**
   ```bash
   # Use tools like gitleaks or trufflehog
   gitleaks detect --source . --verbose
   ```

### Kubernetes Security

1. **Restrict secret access with RBAC**
   ```yaml
   apiVersion: rbac.authorization.k8s.io/v1
   kind: Role
   metadata:
     name: secret-reader
     namespace: database
   rules:
   - apiGroups: [""]
     resources: ["secrets"]
     resourceNames: ["postgresql-credentials"]
     verbs: ["get"]
   ```

2. **Use namespace isolation**
   - Deploy services in separate namespaces
   - Secrets are namespace-scoped by default

3. **Enable audit logging**
   ```bash
   # Check who accessed secrets
   kubectl logs -n kube-system -l component=kube-apiserver | \
     grep "secrets" | grep "get"
   ```

4. **Monitor secret changes**
   ```bash
   # Watch for secret modifications
   kubectl get events --all-namespaces --watch | grep Secret
   ```

### Backup and Recovery

1. **Backup age.key**
   - Store in multiple secure locations
   - Test recovery process regularly

2. **Document recovery procedures**
   - Keep this guide accessible
   - Document key locations
   - Maintain contact list for key holders

3. **Test disaster recovery**
   ```bash
   # Simulate key loss and recovery
   # Verify you can decrypt all secrets
   find gitops -name "*.enc.yaml" -exec sops --decrypt {} \; > /dev/null
   ```

4. **Version control everything**
   - All encrypted secrets in Git
   - Configuration files (.sops.yaml)
   - Documentation

### Compliance and Auditing

1. **Maintain audit trail**
   - Git history tracks all secret changes
   - Use descriptive commit messages
   - Tag releases with version numbers

2. **Regular security reviews**
   - Quarterly review of secret access
   - Annual key rotation
   - Compliance audits

3. **Document procedures**
   - Keep this guide updated
   - Document custom processes
   - Train team members

4. **Incident response plan**
   - Define steps for suspected compromise
   - Emergency key rotation procedures
   - Communication protocols

## Reference

### File Naming Conventions

- **Encrypted secrets**: `*.enc.yaml`
- **Plain manifests**: `*.yaml`
- **Age key file**: `age.key`
- **SOPS config**: `.sops.yaml`

### Directory Structure

```
gitops/
├── apps/
│   ├── postgresql/
│   │   ├── helmrelease.yaml
│   │   └── secret.enc.yaml          # Encrypted
│   ├── redis/
│   │   ├── helmrelease.yaml
│   │   └── secret.enc.yaml          # Encrypted
│   └── authentik/
│       ├── helmrelease.yaml
│       ├── secret.enc.yaml          # Encrypted
│       ├── ingress.yaml
│       └── certificate.yaml
├── infrastructure/
│   └── cert-manager/
│       ├── helmrelease.yaml
│       ├── cloudflare-secret.enc.yaml  # Encrypted
│       └── clusterissuer.yaml
└── flux-system/
    ├── apps-kustomization.yaml      # Has decryption config
    └── infrastructure-kustomization.yaml
```

### Common Commands

```bash
# Generate age key
age-keygen -o age.key

# Encrypt secret
sops --encrypt secret.yaml > secret.enc.yaml

# Decrypt secret
sops --decrypt secret.enc.yaml

# Edit encrypted secret
sops secret.enc.yaml

# Update encryption keys
sops updatekeys secret.enc.yaml

# Extract specific field
sops --decrypt --extract '["stringData"]["password"]' secret.enc.yaml

# Validate encrypted secret
sops --decrypt secret.enc.yaml | kubectl apply --dry-run=client -f -

# Create Kubernetes secret
kubectl create secret generic sops-age \
  --from-file=age.agekey=age.key \
  --namespace=flux-system

# Force Flux reconciliation
flux reconcile kustomization apps --with-source

# Check Flux status
flux get kustomizations
```

### Environment Variables

```bash
# Set default editor for SOPS
export EDITOR=vim

# Specify age key file location
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt

# Use age key from environment
export SOPS_AGE_KEY="AGE-SECRET-KEY-1..."
```

### Useful Scripts

**Encrypt all secrets in directory**:
```bash
#!/bin/bash
find gitops -name "secret.yaml" -type f | while read file; do
  dir=$(dirname "$file")
  sops --encrypt "$file" > "$dir/secret.enc.yaml"
  echo "Encrypted: $file -> $dir/secret.enc.yaml"
done
```

**Validate all encrypted secrets**:
```bash
#!/bin/bash
find gitops -name "*.enc.yaml" -type f | while read file; do
  if sops --decrypt "$file" > /dev/null 2>&1; then
    echo "✅ $file"
  else
    echo "❌ $file"
  fi
done
```

**Rotate all secrets**:
```bash
#!/bin/bash
# Re-encrypt all secrets with new key
find gitops -name "*.enc.yaml" -type f -exec sops updatekeys {} \;
```

### External Resources

- **SOPS Documentation**: https://github.com/getsops/sops
- **Age Encryption**: https://github.com/FiloSottile/age
- **Flux SOPS Guide**: https://fluxcd.io/flux/guides/mozilla-sops/
- **Kubernetes Secrets**: https://kubernetes.io/docs/concepts/configuration/secret/
- **Security Best Practices**: https://kubernetes.io/docs/concepts/security/secrets-good-practices/

### Support

For issues or questions:
1. Check this documentation
2. Review Flux logs: `kubectl logs -n flux-system -l app=kustomize-controller`
3. Check Kustomization status: `flux get kustomizations`
4. Consult the troubleshooting section above
5. Review SOPS and age documentation

---

**Last Updated**: December 4, 2024
**Version**: 1.0.0
