# Infrastructure Services

This directory contains core infrastructure services deployed via Helm releases through Flux CD.

## Services Overview

### cert-manager

Certificate management controller for Kubernetes. Automates the management and issuance of TLS certificates from various certificate authorities (Let's Encrypt, Vault, etc.).

**Namespace:** `cert-manager`

**Features:**
- Automatic TLS certificate provisioning
- Certificate renewal
- Integration with Let's Encrypt and other CAs

**Configuration:**

To issue certificates, you'll need to create a ClusterIssuer or Issuer. Example:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: traefik
```

### PostgreSQL

Bitnami PostgreSQL database for persistent data storage.

**Namespace:** `postgres`

**Features:**
- Persistent storage (8Gi by default)
- Resource limits configured
- Security context enabled

**Connection Details:**
- Host: `postgresql.postgres.svc.cluster.local`
- Port: `5432`

**Important:** Configure a password by either:
1. Setting `auth.postgresPassword` in values
2. Creating a secret and referencing it via `auth.existingSecret`

### Redis

Bitnami Redis in-memory data store for caching and session management.

**Namespace:** `redis`

**Features:**
- Standalone architecture (no replication by default)
- Persistent storage (2Gi by default)
- Resource limits configured

**Connection Details:**
- Host: `redis-master.redis.svc.cluster.local`
- Port: `6379`

**Important:** Configure a password by either:
1. Setting `auth.password` in values
2. Creating a secret and referencing it via `auth.existingSecret`

### Authentik

Open-source Identity Provider with support for OAuth2, SAML, LDAP, and more.

**Namespace:** `authentik`

**Features:**
- Single Sign-On (SSO)
- OAuth2/OpenID Connect provider
- SAML provider
- LDAP provider
- User and group management
- Multi-factor authentication

**Dependencies:**
- PostgreSQL (external - using postgres namespace)
- Redis (external - using redis namespace)

**Important Configuration:**

Before deploying, you must configure:

1. **Secret Key:** Set `authentik.secret_key` with a secure random string
2. **PostgreSQL credentials:** Create the `authentik` database and user in PostgreSQL
3. **Redis password:** Ensure Redis password matches if authentication is enabled

**Initial Setup:**

After deployment, access Authentik at `https://authentik.<your-domain>/if/flow/initial-setup/` to create the admin user.

## Configuration

### Secrets Management

For production deployments, use one of these approaches:

1. **SOPS:** Encrypt secrets in Git with Mozilla SOPS
2. **External Secrets:** Use External Secrets Operator with Vault/AWS Secrets Manager
3. **Sealed Secrets:** Use Bitnami Sealed Secrets

Example secret for PostgreSQL:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgresql-credentials
  namespace: postgres
type: Opaque
stringData:
  postgres-password: "your-secure-password"
```

### Resource Customization

To customize resources, modify the HelmRelease values in the corresponding YAML file:

```yaml
values:
  primary:
    resources:
      requests:
        cpu: 200m
        memory: 512Mi
      limits:
        cpu: 1000m
        memory: 1Gi
```

## Troubleshooting

### Check HelmRelease Status

```bash
flux get helmreleases -n <namespace>
kubectl describe helmrelease <name> -n <namespace>
```

### View Logs

```bash
kubectl logs -n <namespace> -l app.kubernetes.io/name=<service>
```

### Force Reconciliation

```bash
flux reconcile helmrelease <name> -n <namespace>
```

## Dependencies

The services have the following dependency order:

1. **cert-manager** - No dependencies (can be deployed first)
2. **PostgreSQL** - No dependencies
3. **Redis** - No dependencies
4. **Authentik** - Depends on PostgreSQL and Redis
