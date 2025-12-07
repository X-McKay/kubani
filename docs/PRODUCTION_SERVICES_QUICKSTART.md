# Production Services Deployment - Quick Start Guide

This guide walks you through deploying production-ready services (PostgreSQL, Redis, Authentik) with encrypted secrets management and automated TLS certificates.

## Overview

You'll deploy:
- **PostgreSQL**: Production database accessible at `postgres.almckay.io:5432`
- **Redis**: In-memory cache accessible at `redis.almckay.io:6379`
- **Authentik**: Identity provider accessible at `https://auth.almckay.io`
- **cert-manager**: Automated TLS certificate management
- **SOPS**: Encrypted secrets in Git

**Time required**: 15-20 minutes

## Prerequisites

Before starting, ensure:

✅ **Kubernetes cluster is running**
```bash
kubectl get nodes
# All nodes should show "Ready"
```

✅ **Flux CD is operational**
```bash
flux check
# Should show all components healthy
```

✅ **Cloudflare account with domain**
- You have a Cloudflare account
- Your domain (e.g., almckay.io) is managed by Cloudflare
- You can create API tokens

✅ **Required tools installed**
```bash
# Check tools
kubectl version --client
flux --version
sops --version

# If missing, mise will install them
mise install
```

## Step 1: Set Up Secrets Management (5 minutes)

### Generate Age Encryption Key

```bash
# Run the SOPS setup script
uv run python scripts/setup_sops.py
```

This creates:
- `age.key` - Private key (keep secure, don't commit!)
- `.sops.yaml` - Encryption configuration (commit this)
- `sops-age-secret.yaml` - Kubernetes secret for Flux (apply this)

### Apply Age Secret to Cluster

```bash
# Apply the age secret so Flux can decrypt secrets
kubectl apply -f sops-age-secret.yaml

# Verify it was created
kubectl get secret sops-age -n flux-system
```

**Important**: Keep `age.key` secure! Store it in a password manager or secure vault.

## Step 2: Create Cloudflare API Token (3 minutes)

### Create Token in Cloudflare Dashboard

1. **Log in to Cloudflare**: https://dash.cloudflare.com/

2. **Navigate to API Tokens**:
   - Click your profile icon (top right)
   - Select "My Profile"
   - Go to "API Tokens" tab
   - Click "Create Token"

3. **Create Custom Token**:
   - Click "Create Custom Token"
   - **Token name**: `k8s-cert-manager`
   - **Permissions**:
     - Zone → DNS → Edit
     - Zone → Zone → Read
   - **Zone Resources**:
     - Include → Specific zone → Select your domain (e.g., `almckay.io`)
   - **TTL**: No expiry (or set as desired)

4. **Save Token**:
   - Click "Continue to summary"
   - Click "Create Token"
   - **Copy the token immediately** (you won't see it again!)

### Why These Permissions?

- **Zone:DNS:Edit** - Allows cert-manager to create DNS TXT records for ACME challenges
- **Zone:Zone:Read** - Allows cert-manager to read zone information

## Step 3: Create Encrypted Secrets (5 minutes)

### Run the Secret Creation Script

```bash
# Interactive script to create all encrypted secrets
uv run python scripts/create_encrypted_secrets.py
```

### What You'll Be Asked

The script will prompt you for:

1. **Cloudflare API Token** (paste the token from Step 2)
2. **PostgreSQL Credentials**:
   - Admin password (or press Enter to generate)
   - Application username (default: `authentik`)
   - Application password (or press Enter to generate)
   - Database name (default: `authentik`)

3. **Redis Credentials**:
   - Password (or press Enter to generate)

4. **Authentik Credentials**:
   - Secret key (or press Enter to generate)
   - PostgreSQL password (reuses from above)
   - Bootstrap admin password (or press Enter to generate)
   - Bootstrap API token (or press Enter to generate)

**Tip**: Press Enter to auto-generate secure random passwords for all credentials.

### What Gets Created

The script creates encrypted secrets in:
- `gitops/infrastructure/cert-manager/cloudflare-secret.enc.yaml`
- `gitops/apps/postgresql/secret.enc.yaml`
- `gitops/apps/redis/secret.enc.yaml`
- `gitops/apps/authentik/secret.enc.yaml`

These files are **safe to commit to Git** because they're encrypted with SOPS.

## Step 4: Configure DNS Records (3 minutes)

### Get Traefik LoadBalancer IP

```bash
# Display Traefik IP and DNS instructions
./scripts/get_traefik_ip.sh
```

This shows your Traefik LoadBalancer IP (typically a Tailscale IP).

### Create DNS A Records

You have two options:

#### Option 1: Automated (Recommended)

```bash
# Requires Cloudflare API token
uv run python scripts/configure_dns.py
```

This automatically creates the required DNS A records.

#### Option 2: Manual

1. Log in to Cloudflare Dashboard: https://dash.cloudflare.com/
2. Select your domain (e.g., almckay.io)
3. Go to "DNS" → "Records"
4. Create three A records:

| Type | Name     | Content              | Proxy Status | TTL  |
|------|----------|----------------------|--------------|------|
| A    | postgres | `<traefik-ip>`       | DNS only     | Auto |
| A    | redis    | `<traefik-ip>`       | DNS only     | Auto |
| A    | auth     | `<traefik-ip>`       | DNS only     | Auto |

**Important**: Set "Proxy status" to "DNS only" (gray cloud), not "Proxied" (orange cloud).

### Verify DNS Propagation

```bash
# Test DNS resolution (may take 1-2 minutes)
nslookup postgres.almckay.io
nslookup redis.almckay.io
nslookup auth.almckay.io

# All should resolve to your Traefik IP
```

## Step 5: Deploy Services via GitOps (2 minutes)

### Commit and Push Encrypted Secrets

```bash
# Add encrypted secrets to Git
git add .sops.yaml
git add gitops/infrastructure/cert-manager/cloudflare-secret.enc.yaml
git add gitops/apps/postgresql/secret.enc.yaml
git add gitops/apps/redis/secret.enc.yaml
git add gitops/apps/authentik/secret.enc.yaml

# Commit
git commit -m "Add encrypted secrets for production services"

# Push to trigger Flux deployment
git push
```

### What Happens Next

Flux will automatically:
1. Detect the changes in Git (within 1 minute)
2. Decrypt the secrets using the age key
3. Deploy cert-manager with Cloudflare integration
4. Deploy PostgreSQL, Redis, and Authentik
5. Request TLS certificates from Let's Encrypt
6. Configure Traefik TCP routing

**Deployment time**: 3-5 minutes

## Step 6: Monitor Deployment (3 minutes)

### Watch Deployment Progress

```bash
# Watch all pods across namespaces
watch kubectl get pods -A

# Or watch specific namespaces
watch kubectl get pods -n cert-manager,database,cache,auth
```

### Expected Pod States

After 3-5 minutes, you should see:

```
NAMESPACE      NAME                                       READY   STATUS
cert-manager   cert-manager-...                           1/1     Running
cert-manager   cert-manager-cainjector-...                1/1     Running
cert-manager   cert-manager-webhook-...                   1/1     Running
database       postgresql-0                               1/1     Running
cache          redis-master-0                             1/1     Running
auth           authentik-server-...                       1/1     Running
auth           authentik-worker-...                       1/1     Running
```

### Check Flux Status

```bash
# Check Flux Kustomizations
flux get kustomizations

# Should show:
# NAME            READY   MESSAGE
# flux-system     True    Applied revision: main/...
# infrastructure  True    Applied revision: main/...
# apps            True    Applied revision: main/...
```

## Step 7: Validate Deployment (2 minutes)

### Run Comprehensive Validation

```bash
# Run all validation checks
./scripts/verify_services.sh
```

This validates:
- ✅ Pod status for all services
- ✅ PostgreSQL connectivity and authentication
- ✅ Redis connectivity and authentication
- ✅ Authentik HTTPS access and TLS certificate
- ✅ Certificate issuance and validity

### Run Individual Validations

If you prefer to check services individually:

```bash
# Check pod status
./scripts/validate_pods.sh

# Validate PostgreSQL
./scripts/validate_postgresql.sh

# Validate Redis
./scripts/validate_redis.sh

# Validate Authentik
./scripts/validate_authentik.sh

# Validate certificates
./scripts/validate_certificates.sh
```

### Expected Output

All validation scripts should show:
```
✅ All checks passed
```

If any checks fail, see the [Troubleshooting](#troubleshooting) section below.

## Step 8: Access Your Services

### PostgreSQL

Connect from any machine on your Tailscale network:

```bash
# Using psql
psql -h postgres.almckay.io -p 5432 -U authentik -d authentik

# Connection string
postgresql://authentik:<password>@postgres.almckay.io:5432/authentik
```

**Get the password:**
```bash
kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.password}' | base64 -d
```

### Redis

Connect from any machine on your Tailscale network:

```bash
# Using redis-cli
redis-cli -h redis.almckay.io -p 6379 -a <password>

# Test connection
redis-cli -h redis.almckay.io -p 6379 -a <password> PING
# Should return: PONG

# Connection string
redis://:<password>@redis.almckay.io:6379
```

**Get the password:**
```bash
kubectl get secret redis-credentials -n cache -o jsonpath='{.data.redis-password}' | base64 -d
```

### Authentik

Access from any browser:

```bash
# Open in browser
open https://auth.almckay.io

# Or test with curl
curl https://auth.almckay.io
```

**Initial login:**
- Username: `akadmin`
- Password: (bootstrap password from secret creation)

**Get the bootstrap password:**
```bash
kubectl get secret authentik-credentials -n auth -o jsonpath='{.data.bootstrap-password}' | base64 -d
```

## Troubleshooting

### Pods Not Starting

**Check pod status:**
```bash
kubectl get pods -n database
kubectl get pods -n cache
kubectl get pods -n auth
```

**View pod logs:**
```bash
kubectl logs -n database -l app.kubernetes.io/name=postgresql
kubectl logs -n cache -l app.kubernetes.io/name=redis
kubectl logs -n auth -l app.kubernetes.io/name=authentik
```

**Common issues:**
- **ImagePullBackOff**: Check internet connectivity
- **CrashLoopBackOff**: Check logs for errors
- **Pending**: Check for resource constraints

### Secrets Not Decrypted

**Check age secret:**
```bash
kubectl get secret sops-age -n flux-system
```

**Check Flux logs:**
```bash
kubectl logs -n flux-system -l app=kustomize-controller | grep -i sops
```

**Test local decryption:**
```bash
sops -d gitops/apps/postgresql/secret.enc.yaml
```

**Solution:**
```bash
# Recreate age secret
kubectl delete secret sops-age -n flux-system
kubectl apply -f sops-age-secret.yaml

# Force Flux reconciliation
flux reconcile kustomization apps --with-source
```

### Certificate Not Issued

**Check certificate status:**
```bash
kubectl get certificate -n auth
kubectl describe certificate authentik-tls -n auth
```

**Check cert-manager logs:**
```bash
kubectl logs -n cert-manager -l app=cert-manager
```

**Common issues:**
- **Invalid Cloudflare token**: Update secret and restart cert-manager
- **DNS propagation**: Wait 2-5 minutes for DNS to propagate
- **Rate limit**: Use staging issuer for testing

**Solution:**
```bash
# Check ClusterIssuer
kubectl describe clusterissuer letsencrypt-prod

# Force certificate renewal
kubectl delete certificaterequest -n auth --all
```

### Cannot Connect to Services

**Test DNS resolution:**
```bash
nslookup postgres.almckay.io
nslookup redis.almckay.io
nslookup auth.almckay.io
```

**Test TCP connectivity:**
```bash
nc -zv postgres.almckay.io 5432
nc -zv redis.almckay.io 6379
nc -zv auth.almckay.io 443
```

**Check Traefik:**
```bash
kubectl get svc -n kube-system traefik
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik
```

**Check IngressRouteTCP:**
```bash
kubectl get ingressroutetcp -A
kubectl describe ingressroutetcp postgresql-tcp -n database
kubectl describe ingressroutetcp redis-tcp -n cache
```

### Flux Not Syncing

**Check Flux status:**
```bash
flux check
flux get kustomizations
```

**Force reconciliation:**
```bash
flux reconcile source git flux-system
flux reconcile kustomization infrastructure
flux reconcile kustomization apps
```

**Check for errors:**
```bash
kubectl logs -n flux-system -l app=source-controller
kubectl logs -n flux-system -l app=kustomize-controller
```

## Next Steps

### Secure Your Credentials

1. **Store age.key securely**:
   ```bash
   # Copy to password manager or secure vault
   cat age.key

   # Remove from local filesystem (optional)
   # rm age.key
   ```

2. **Save service passwords**:
   ```bash
   # Extract all passwords
   kubectl get secret postgresql-credentials -n database -o yaml
   kubectl get secret redis-credentials -n cache -o yaml
   kubectl get secret authentik-credentials -n auth -o yaml
   ```

### Configure Authentik

1. **Log in to Authentik**: https://auth.almckay.io
2. **Change admin password**: Go to Admin Interface → User Settings
3. **Configure applications**: Set up SSO for your services
4. **Create users**: Add users and groups

### Set Up Backups

**PostgreSQL backups:**
```bash
# Create backup job
kubectl create job postgresql-backup --from=cronjob/postgresql-backup -n database

# Or manually backup
kubectl exec -n database postgresql-0 -- pg_dump -U postgres authentik > backup.sql
```

**Redis backups:**
```bash
# Redis persistence is enabled by default
# Check persistence
kubectl exec -n cache redis-master-0 -- redis-cli CONFIG GET save
```

### Monitor Your Services

**Set up monitoring:**
- Deploy Prometheus and Grafana
- Configure alerts for service health
- Monitor certificate expiration

**Useful commands:**
```bash
# Check resource usage
kubectl top pods -n database
kubectl top pods -n cache
kubectl top pods -n auth

# Check certificate expiration
kubectl get certificate -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,READY:.status.conditions[0].status,EXPIRY:.status.notAfter
```

## Additional Resources

- **[Secrets Management Guide](SECRETS_MANAGEMENT.md)**: Detailed SOPS and age encryption guide
- **[DNS Configuration Guide](DNS_CONFIGURATION.md)**: Advanced DNS and Traefik configuration
- **[Service Validation Guide](SERVICE_VALIDATION.md)**: Comprehensive validation procedures
- **[Troubleshooting Guide](TROUBLESHOOTING.md)**: Detailed troubleshooting for all issues
- **[GitOps Service Deployment](GITOPS_SERVICE_DEPLOYMENT.md)**: In-depth GitOps workflow

## Summary

You've successfully deployed:

✅ **PostgreSQL** at `postgres.almckay.io:5432`
- Production-ready database with persistent storage
- Encrypted credentials in Git
- Accessible from any Tailscale device

✅ **Redis** at `redis.almckay.io:6379`
- In-memory cache with optional persistence
- Encrypted credentials in Git
- Accessible from any Tailscale device

✅ **Authentik** at `https://auth.almckay.io`
- Identity provider with SSO capabilities
- Automated TLS certificate from Let's Encrypt
- Accessible from any browser

✅ **Secrets Management**
- SOPS encryption with age
- Safe to store secrets in Git
- Automatic decryption by Flux

✅ **Certificate Management**
- Automated TLS via cert-manager
- Let's Encrypt integration
- Automatic renewal

**Total deployment time**: ~15-20 minutes

Enjoy your production-ready Kubernetes services! 🚀
