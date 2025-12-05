# Design Document

## Overview

The Production Services Deployment system extends the existing Tailscale Kubernetes cluster with production-ready infrastructure services and secrets management. The system integrates cert-manager for automated TLS certificate management via Cloudflare DNS, SOPS with age encryption for secure secrets storage in Git, and deploys core services (PostgreSQL, Redis, Authentik) using GitOps practices with Flux CD.

The design prioritizes security through encrypted secrets, automation through cert-manager and GitOps, and maintainability through comprehensive documentation and validation tools.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Repository                          │
│  ├── gitops/infrastructure/                                 │
│  │   ├── cert-manager/                                      │
│  │   │   ├── helmrelease.yaml                               │
│  │   │   ├── cloudflare-secret.enc.yaml (SOPS encrypted)    │
│  │   │   └── clusterissuer.yaml                             │
│  │   └── sources/                                           │
│  │       └── jetstack.yaml                                  │
│  ├── gitops/apps/                                           │
│  │   ├── postgresql/                                        │
│  │   │   ├── helmrelease.yaml                               │
│  │   │   └── secret.enc.yaml (SOPS encrypted)               │
│  │   ├── redis/                                             │
│  │   │   ├── helmrelease.yaml                               │
│  │   │   └── secret.enc.yaml (SOPS encrypted)               │
│  │   └── authentik/                                         │
│  │       ├── helmrelease.yaml                               │
│  │       ├── secret.enc.yaml (SOPS encrypted)               │
│  │       ├── ingress.yaml                                   │
│  │       └── certificate.yaml                               │
│  └── docs/                                                  │
│      └── SECRETS_MANAGEMENT.md                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Flux CD (GitOps)                         │
│  ├── Source Controller (Git sync)                           │
│  ├── Kustomize Controller (manifest processing)             │
│  ├── Helm Controller (Helm releases)                        │
│  └── SOPS Decryption (age key)                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Kubernetes Cluster (K3s)                       │
│  ├── kube-system namespace                                  │
│  │   ├── Traefik Ingress Controller (LoadBalancer)          │
│  │   │   ├── HTTP/HTTPS (ports 80/443)                      │
│  │   │   ├── TCP: PostgreSQL (port 5432)                    │
│  │   │   └── TCP: Redis (port 6379)                         │
│  │   └── Exposed on Tailscale IP                            │
│  ├── cert-manager namespace                                 │
│  │   ├── cert-manager controller                            │
│  │   ├── ClusterIssuer (letsencrypt-prod)                   │
│  │   └── Cloudflare API credentials                         │
│  ├── database namespace                                     │
│  │   ├── PostgreSQL StatefulSet                             │
│  │   ├── PersistentVolumeClaim                              │
│  │   └── ClusterIP Service (internal)                       │
│  ├── cache namespace                                        │
│  │   ├── Redis StatefulSet                                  │
│  │   ├── PersistentVolumeClaim                              │
│  │   └── ClusterIP Service (internal)                       │
│  └── auth namespace                                         │
│      ├── Authentik Deployment                               │
│      ├── Ingress (auth.almckay.io)                          │
│      └── Certificate (TLS)                                  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              DNS-Based Access (almckay.io)                  │
│  ├── postgres.almckay.io → Traefik TCP (port 5432)          │
│  ├── redis.almckay.io → Traefik TCP (port 6379)             │
│  └── auth.almckay.io → Traefik HTTPS (port 443)             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Tailscale Network Clients                      │
│  ├── PostgreSQL: psql -h postgres.almckay.io -p 5432        │
│  ├── Redis: redis-cli -h redis.almckay.io -p 6379           │
│  └── Authentik: https://auth.almckay.io                     │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  External Services                          │
│  ├── Cloudflare DNS (almckay.io)                            │
│  │   ├── DNS records (A/CNAME)                              │
│  │   └── TXT records (ACME challenges)                      │
│  └── Let's Encrypt                                          │
│      └── Certificate Authority                              │
└─────────────────────────────────────────────────────────────┘
```


## Components and Interfaces

### 1. Cert-Manager Component

**Purpose**: Automates TLS certificate issuance and renewal using Let's Encrypt with Cloudflare DNS-01 challenges.

**Interfaces**:
- **Input**: Certificate requests via Kubernetes Certificate resources
- **Output**: TLS certificates stored as Kubernetes secrets
- **External**: Cloudflare API for DNS record management, Let's Encrypt ACME API

**Key Resources**:
- `HelmRelease`: Deploys cert-manager from Jetstack Helm repository
- `ClusterIssuer`: Configures Let's Encrypt production issuer with Cloudflare DNS solver
- `Secret`: Stores Cloudflare API token (SOPS encrypted in Git)
- `Certificate`: Defines TLS certificates to be issued

**Configuration**:
```yaml
# ClusterIssuer configuration
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@almckay.io
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
    - dns01:
        cloudflare:
          apiTokenSecretRef:
            name: cloudflare-api-token
            key: api-token
```

### 2. Traefik TCP/UDP Routing Component

**Purpose**: Exposes PostgreSQL and Redis via DNS names using Traefik's TCP routing capabilities.

**Interfaces**:
- **Input**: TCP connections to postgres.almckay.io:5432 and redis.almckay.io:6379
- **Output**: Routed connections to backend services
- **Configuration**: IngressRouteTCP custom resources

**Key Resources**:
- `IngressRouteTCP`: Traefik CRD for TCP routing (PostgreSQL and Redis)
- `Middleware`: Optional TCP middleware for connection handling
- Traefik configuration via HelmChart or ConfigMap

**Configuration**:
```yaml
# Traefik TCP routing for PostgreSQL
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRouteTCP
metadata:
  name: postgresql-tcp
  namespace: database
spec:
  entryPoints:
    - postgresql
  routes:
    - match: HostSNI(`*`)
      services:
        - name: postgresql
          port: 5432

# Traefik TCP routing for Redis
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRouteTCP
metadata:
  name: redis-tcp
  namespace: cache
spec:
  entryPoints:
    - redis
  routes:
    - match: HostSNI(`*`)
      services:
        - name: redis-master
          port: 6379
```

**Traefik Configuration**:
```yaml
# Additional ports for Traefik
ports:
  postgresql:
    port: 5432
    expose: true
    exposedPort: 5432
    protocol: TCP
  redis:
    port: 6379
    expose: true
    exposedPort: 6379
    protocol: TCP
```

**DNS Configuration**:
- `postgres.almckay.io` → A record → Traefik LoadBalancer IP (Tailscale)
- `redis.almckay.io` → A record → Traefik LoadBalancer IP (Tailscale)
- `auth.almckay.io` → A record → Traefik LoadBalancer IP (Tailscale)

### 3. SOPS Secrets Management Component

**Purpose**: Encrypts sensitive data in Git using age encryption, allowing secure storage of secrets in version control.

**Interfaces**:
- **Input**: Plain-text Kubernetes secrets
- **Output**: Encrypted secrets (SOPS format) safe for Git storage
- **Decryption**: Flux Kustomize controller with age private key

**Key Resources**:
- Age key pair (public key for encryption, private key stored in cluster)
- `.sops.yaml`: Configuration file defining encryption rules
- Encrypted secret manifests with `.enc.yaml` suffix
- Kubernetes secret in flux-system namespace containing age private key

**Encryption Flow**:
1. Administrator creates plain-text secret YAML
2. SOPS encrypts using age public key
3. Encrypted secret committed to Git
4. Flux detects change and decrypts using age private key
5. Decrypted secret applied to cluster

### 4. PostgreSQL Service Component

**Purpose**: Provides a production-ready relational database for applications.

**Interfaces**:
- **Input**: Database connection requests from applications (cluster-internal and Tailscale network via DNS)
- **Output**: SQL query responses
- **Storage**: PersistentVolumeClaim for data persistence
- **Network**: Accessible via postgres.almckay.io through Traefik TCP routing

**Key Resources**:
- `HelmRelease`: Deploys PostgreSQL using Bitnami Helm chart
- `Secret`: Database credentials (SOPS encrypted)
- `Service`: ClusterIP service for internal access (port 5432)
- `IngressRouteTCP`: Traefik TCP route for external access
- `PersistentVolumeClaim`: Storage for database files

**Configuration**:
```yaml
# HelmRelease values
auth:
  existingSecret: postgresql-credentials
  secretKeys:
    adminPasswordKey: postgres-password
    userPasswordKey: user-password
primary:
  persistence:
    enabled: true
    size: 20Gi
  service:
    type: ClusterIP
    ports:
      postgresql: 5432
```

**DNS-Based Access**:
- External access: `postgres.almckay.io:5432` (via Traefik TCP routing)
- Internal access: `postgresql.database.svc.cluster.local:5432`
- Clients on Tailscale network: `psql -h postgres.almckay.io -p 5432 -U <user> -d <database>`
- Connection string: `postgresql://<user>:<password>@postgres.almckay.io:5432/<database>`

### 5. Redis Service Component

**Purpose**: Provides an in-memory cache and data store for applications.

**Interfaces**:
- **Input**: Redis commands from applications (cluster-internal and Tailscale network via DNS)
- **Output**: Cached data responses
- **Storage**: Optional PersistentVolumeClaim for persistence
- **Network**: Accessible via redis.almckay.io through Traefik TCP routing

**Key Resources**:
- `HelmRelease`: Deploys Redis using Bitnami Helm chart
- `Secret`: Redis password (SOPS encrypted)
- `Service`: ClusterIP service for internal access (port 6379)
- `IngressRouteTCP`: Traefik TCP route for external access
- `PersistentVolumeClaim`: Optional persistence

**Configuration**:
```yaml
# HelmRelease values
auth:
  existingSecret: redis-credentials
  existingSecretPasswordKey: redis-password
master:
  persistence:
    enabled: true
    size: 8Gi
  service:
    type: ClusterIP
    ports:
      redis: 6379
```

**DNS-Based Access**:
- External access: `redis.almckay.io:6379` (via Traefik TCP routing)
- Internal access: `redis-master.cache.svc.cluster.local:6379`
- Clients on Tailscale network: `redis-cli -h redis.almckay.io -p 6379 -a <password>`
- Connection string: `redis://:<password>@redis.almckay.io:6379`

### 6. Authentik Service Component

**Purpose**: Provides centralized identity and access management with SSO capabilities.

**Interfaces**:
- **Input**: Authentication requests via HTTPS
- **Output**: Authentication tokens, user sessions
- **External**: PostgreSQL for data storage
- **Public**: HTTPS ingress at auth.almckay.io

**Key Resources**:
- `HelmRelease`: Deploys Authentik using official Helm chart
- `Secret`: Application secrets and database credentials (SOPS encrypted)
- `Ingress`: Routes traffic from auth.almckay.io
- `Certificate`: TLS certificate for HTTPS

**Configuration**:
```yaml
# HelmRelease values
authentik:
  secret_key: <from-secret>
  postgresql:
    host: postgresql.database.svc.cluster.local
    name: authentik
    user: authentik
    password: <from-secret>
ingress:
  enabled: true
  hosts:
    - host: auth.almckay.io
      paths:
        - path: /
  tls:
    - secretName: authentik-tls
      hosts:
        - auth.almckay.io
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
```

### 7. Flux SOPS Integration Component

**Purpose**: Enables Flux to automatically decrypt SOPS-encrypted secrets during reconciliation.

**Interfaces**:
- **Input**: Encrypted manifests from Git
- **Output**: Decrypted secrets applied to cluster
- **Configuration**: Kustomization with decryption enabled

**Key Resources**:
- `Secret`: Age private key in flux-system namespace
- `Kustomization`: Flux resource with SOPS decryption enabled

**Configuration**:
```yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: apps
  namespace: flux-system
spec:
  interval: 10m
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


## Data Models

### Age Key Pair

```python
@dataclass
class AgeKeyPair:
    """Represents an age encryption key pair for SOPS."""
    public_key: str  # Format: age1... (for encryption)
    private_key: str  # Format: AGE-SECRET-KEY-1... (for decryption)
    created_at: datetime

    def to_kubernetes_secret(self) -> dict:
        """Convert to Kubernetes secret format for Flux."""
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "sops-age",
                "namespace": "flux-system"
            },
            "type": "Opaque",
            "stringData": {
                "age.agekey": self.private_key
            }
        }
```

### Certificate Configuration

```python
@dataclass
class CertificateConfig:
    """Represents a TLS certificate configuration."""
    name: str
    namespace: str
    dns_names: List[str]  # e.g., ["auth.almckay.io"]
    issuer_ref: str  # e.g., "letsencrypt-prod"
    secret_name: str  # Where cert will be stored

    def to_manifest(self) -> dict:
        """Convert to Kubernetes Certificate manifest."""
        return {
            "apiVersion": "cert-manager.io/v1",
            "kind": "Certificate",
            "metadata": {
                "name": self.name,
                "namespace": self.namespace
            },
            "spec": {
                "secretName": self.secret_name,
                "issuerRef": {
                    "name": self.issuer_ref,
                    "kind": "ClusterIssuer"
                },
                "dnsNames": self.dns_names
            }
        }
```

### Service Credentials

```python
@dataclass
class PostgreSQLCredentials:
    """PostgreSQL database credentials."""
    postgres_password: str  # Admin password
    username: str  # Application user
    password: str  # Application password
    database: str  # Database name

    def to_secret_manifest(self) -> dict:
        """Convert to Kubernetes secret (to be encrypted with SOPS)."""
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "postgresql-credentials",
                "namespace": "database"
            },
            "type": "Opaque",
            "stringData": {
                "postgres-password": self.postgres_password,
                "username": self.username,
                "password": self.password,
                "database": self.database
            }
        }

@dataclass
class RedisCredentials:
    """Redis authentication credentials."""
    password: str

    def to_secret_manifest(self) -> dict:
        """Convert to Kubernetes secret (to be encrypted with SOPS)."""
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "redis-credentials",
                "namespace": "cache"
            },
            "type": "Opaque",
            "stringData": {
                "redis-password": self.password
            }
        }

@dataclass
class AuthentikCredentials:
    """Authentik application credentials."""
    secret_key: str  # Django secret key
    postgres_password: str  # Database password
    bootstrap_password: str  # Initial admin password
    bootstrap_token: str  # Initial API token

    def to_secret_manifest(self) -> dict:
        """Convert to Kubernetes secret (to be encrypted with SOPS)."""
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "authentik-credentials",
                "namespace": "auth"
            },
            "type": "Opaque",
            "stringData": {
                "secret-key": self.secret_key,
                "postgres-password": self.postgres_password,
                "bootstrap-password": self.bootstrap_password,
                "bootstrap-token": self.bootstrap_token
            }
        }
```

### Cloudflare API Configuration

```python
@dataclass
class CloudflareConfig:
    """Cloudflare API configuration for cert-manager."""
    api_token: str  # API token with DNS edit permissions
    email: str  # Cloudflare account email
    zone_id: str  # Zone ID for almckay.io

    def to_secret_manifest(self) -> dict:
        """Convert to Kubernetes secret (to be encrypted with SOPS)."""
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "cloudflare-api-token",
                "namespace": "cert-manager"
            },
            "type": "Opaque",
            "stringData": {
                "api-token": self.api_token
            }
        }
```

### SOPS Configuration

```yaml
# .sops.yaml - Defines encryption rules
creation_rules:
  - path_regex: \.enc\.yaml$
    encrypted_regex: ^(data|stringData)$
    age: age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Age key generation produces valid format

*For any* generated age key pair, the public key should start with "age1" and the private key should start with "AGE-SECRET-KEY-1", and both should be valid base64-encoded strings of the correct length.

**Validates: Requirements 2.1**

### Property 2: Secret templates produce valid Kubernetes manifests

*For any* valid credentials (PostgreSQL, Redis, Authentik, Cloudflare), the corresponding template function should produce a Kubernetes Secret manifest that passes kubectl validation and contains all required fields (apiVersion, kind, metadata, type, stringData).

**Validates: Requirements 2.3**

### Property 3: SOPS encryption preserves metadata readability

*For any* Kubernetes secret manifest, after SOPS encryption, the metadata fields (apiVersion, kind, metadata.name, metadata.namespace) should remain unencrypted and readable, while data/stringData fields should be encrypted.

**Validates: Requirements 2.4**

### Property 4: HelmRelease manifests reference correct secrets

*For any* service HelmRelease (PostgreSQL, Redis, Authentik), the values configuration should reference an existingSecret that matches the expected secret name for that service.

**Validates: Requirements 3.2, 4.2, 5.2**

### Property 5: Stateful services have persistence configured

*For any* stateful service HelmRelease (PostgreSQL, Redis), the values configuration should have persistence.enabled set to true and persistence.size specified.

**Validates: Requirements 3.3, 4.3**

### Property 6: Ingress manifests have required TLS configuration

*For any* Ingress resource for external services, the manifest should include a cert-manager.io/cluster-issuer annotation, a host under almckay.io domain, and a tls section referencing a secretName for the certificate.

**Validates: Requirements 5.3, 5.4, 8.1, 8.4**

### Property 7: Multiple services have independent Ingress configurations

*For any* set of services requiring external access, each service should have its own Ingress resource with a unique subdomain and unique TLS secret name, ensuring no conflicts.

**Validates: Requirements 8.5**

### Property 8: Service manifests are organized in correct directories

*For any* deployed service, its HelmRelease manifest should be located in gitops/apps/{service-name}/ and any encrypted secrets should be co-located in the same directory with .enc.yaml suffix.

**Validates: Requirements 9.1, 9.2**

### Property 9: Database services have IngressRouteTCP for DNS access

*For any* stateful data service (PostgreSQL, Redis), there should be a corresponding IngressRouteTCP resource that routes traffic from the DNS name (postgres.almckay.io, redis.almckay.io) to the ClusterIP service.

**Validates: Requirements 11.1, 11.2**


## Error Handling

### SOPS Encryption Errors

**Error**: Age key not found or invalid format
- **Detection**: Check for age key file existence and validate format before encryption
- **Recovery**: Generate new age key pair with proper format validation
- **User Feedback**: "Age key not found at expected location. Run 'age-keygen -o age.key' to generate a new key."

**Error**: SOPS encryption fails due to missing .sops.yaml configuration
- **Detection**: Check for .sops.yaml file before attempting encryption
- **Recovery**: Create .sops.yaml with default configuration pointing to age public key
- **User Feedback**: "SOPS configuration not found. Creating .sops.yaml with age encryption rules."

**Error**: Encrypted secret cannot be decrypted by Flux
- **Detection**: Flux Kustomization status shows decryption errors
- **Recovery**: Verify age private key secret exists in flux-system namespace
- **User Feedback**: "Decryption failed. Verify sops-age secret exists in flux-system namespace and contains the correct private key."

### Cert-Manager Errors

**Error**: Cloudflare API token invalid or lacks permissions
- **Detection**: ClusterIssuer status shows authentication errors
- **Recovery**: Verify API token has Zone:DNS:Edit permissions for almckay.io
- **User Feedback**: "Cloudflare authentication failed. Verify API token has DNS edit permissions for almckay.io zone."

**Error**: Certificate issuance fails due to DNS propagation timeout
- **Detection**: Certificate resource status shows challenge timeout
- **Recovery**: Increase DNS propagation timeout in ClusterIssuer configuration
- **User Feedback**: "Certificate challenge timed out. DNS records may need more time to propagate. Cert-manager will retry automatically."

**Error**: Let's Encrypt rate limit exceeded
- **Detection**: Certificate status shows rate limit error from ACME server
- **Recovery**: Use Let's Encrypt staging environment for testing, wait for rate limit reset
- **User Feedback**: "Let's Encrypt rate limit exceeded. Use letsencrypt-staging issuer for testing or wait 1 hour for limit reset."

### Service Deployment Errors

**Error**: PostgreSQL fails to start due to missing secret
- **Detection**: Pod status shows secret not found error
- **Recovery**: Verify encrypted secret is committed to Git and Flux has decrypted it
- **User Feedback**: "PostgreSQL secret not found. Verify postgresql-credentials secret exists in database namespace."

**Error**: Redis authentication fails with wrong password
- **Detection**: Application logs show Redis authentication errors
- **Recovery**: Verify secret contains correct password key (redis-password)
- **User Feedback**: "Redis authentication failed. Verify redis-credentials secret contains 'redis-password' key."

**Error**: Authentik cannot connect to PostgreSQL
- **Detection**: Authentik pod logs show database connection errors
- **Recovery**: Verify PostgreSQL service is running and credentials are correct
- **User Feedback**: "Authentik database connection failed. Verify PostgreSQL is running and credentials in authentik-credentials secret are correct."

**Error**: Ingress returns 404 for configured subdomain
- **Detection**: HTTP requests to subdomain return 404
- **Recovery**: Verify Ingress controller is running and service backend exists
- **User Feedback**: "Ingress not routing traffic. Verify service exists and Ingress controller is running."

### GitOps Synchronization Errors

**Error**: Flux cannot access Git repository
- **Detection**: GitRepository resource status shows authentication error
- **Recovery**: Verify Git credentials or SSH key is configured correctly
- **User Feedback**: "Flux cannot access Git repository. Verify SSH key or credentials are configured in flux-system namespace."

**Error**: Kustomization build fails due to invalid YAML
- **Detection**: Kustomization status shows build error
- **Recovery**: Validate YAML syntax locally with kubectl or kustomize
- **User Feedback**: "Kustomization build failed. Run 'kustomize build gitops/apps' locally to identify syntax errors."

**Error**: HelmRelease fails to install due to missing values
- **Detection**: HelmRelease status shows installation error
- **Recovery**: Verify all required values are provided in HelmRelease spec
- **User Feedback**: "Helm installation failed. Check HelmRelease status for missing required values."

### Validation Errors

**Error**: Certificate validation fails - certificate not issued
- **Detection**: Certificate resource status is not "Ready"
- **Recovery**: Check Certificate and CertificateRequest resources for errors
- **User Feedback**: "Certificate not ready. Check Certificate status: kubectl describe certificate <name> -n <namespace>"

**Error**: Service health check fails - pods not running
- **Detection**: Pod status is not "Running" or readiness probe fails
- **Recovery**: Check pod logs and events for startup errors
- **User Feedback**: "Service pods not ready. Check logs: kubectl logs -n <namespace> <pod-name>"

**Error**: DNS resolution fails for subdomain
- **Detection**: nslookup or dig returns NXDOMAIN
- **Recovery**: Verify DNS records exist in Cloudflare for the subdomain
- **User Feedback**: "DNS resolution failed for <subdomain>. Verify A/CNAME record exists in Cloudflare."


## Testing Strategy

The testing strategy employs both unit tests and property-based tests to ensure correctness of the production services deployment system.

### Unit Testing Approach

Unit tests verify specific examples, edge cases, and integration points:

**Manifest Generation Tests**:
- Test that cert-manager HelmRelease is generated with correct Jetstack repository reference
- Test that ClusterIssuer manifest includes Let's Encrypt production server URL
- Test that PostgreSQL HelmRelease references postgresql-credentials secret
- Test that Redis HelmRelease has authentication enabled
- Test that Authentik Ingress includes cert-manager annotation
- Test that .sops.yaml configuration file is created with correct age public key

**File Organization Tests**:
- Test that cert-manager manifests are created in gitops/infrastructure/cert-manager/
- Test that service manifests are created in gitops/apps/{service-name}/
- Test that encrypted secrets have .enc.yaml suffix

**Documentation Tests**:
- Test that SECRETS_MANAGEMENT.md exists and contains age key generation instructions
- Test that documentation includes SOPS encryption examples
- Test that troubleshooting section covers common decryption errors

**Edge Cases**:
- Test handling of empty or invalid Cloudflare API tokens
- Test handling of malformed age keys
- Test handling of missing secret references in HelmReleases
- Test handling of duplicate subdomain configurations

### Property-Based Testing Approach

Property-based tests verify universal properties across all inputs using Hypothesis (Python's PBT library). Each test will run a minimum of 100 iterations with randomly generated inputs.

**Test Configuration**:
```python
from hypothesis import given, settings
import hypothesis.strategies as st

# Configure to run 100 iterations minimum
@settings(max_examples=100)
```

**Property Test 1: Age key generation format validation**
- **Feature: production-services-deployment, Property 1: Age key generation produces valid format**
- Generate random age key pairs
- Verify public key starts with "age1" and is valid base64
- Verify private key starts with "AGE-SECRET-KEY-1" and is valid base64
- Verify keys can be used for encryption/decryption round-trip

**Property Test 2: Secret template validation**
- **Feature: production-services-deployment, Property 2: Secret templates produce valid Kubernetes manifests**
- Generate random credentials for each service type
- Apply template function to generate secret manifest
- Verify manifest passes kubectl validation (dry-run)
- Verify all required fields are present

**Property Test 3: SOPS encryption metadata preservation**
- **Feature: production-services-deployment, Property 3: SOPS encryption preserves metadata readability**
- Generate random Kubernetes secret manifests
- Encrypt with SOPS using test age key
- Verify metadata fields remain unencrypted
- Verify data/stringData fields are encrypted
- Verify encrypted manifest can be decrypted back to original

**Property Test 4: HelmRelease secret references**
- **Feature: production-services-deployment, Property 4: HelmRelease manifests reference correct secrets**
- Generate HelmRelease manifests for each service type
- Verify existingSecret field matches expected secret name pattern
- Verify secret name follows naming convention: {service}-credentials

**Property Test 5: Stateful service persistence**
- **Feature: production-services-deployment, Property 5: Stateful services have persistence configured**
- Generate HelmRelease manifests for stateful services
- Verify persistence.enabled is true
- Verify persistence.size is specified and valid (e.g., "20Gi")

**Property Test 6: Ingress TLS configuration**
- **Feature: production-services-deployment, Property 6: Ingress manifests have required TLS configuration**
- Generate Ingress manifests for various services
- Verify cert-manager annotation is present
- Verify host is under almckay.io domain
- Verify tls section references a secret name

**Property Test 7: Multiple service Ingress independence**
- **Feature: production-services-deployment, Property 7: Multiple services have independent Ingress configurations**
- Generate multiple Ingress resources for different services
- Verify each has unique subdomain
- Verify each has unique TLS secret name
- Verify no hostname or secret name collisions

**Property Test 8: File organization consistency**
- **Feature: production-services-deployment, Property 8: Service manifests are organized in correct directories**
- Generate manifests for various services
- Verify HelmRelease files are in gitops/apps/{service-name}/
- Verify encrypted secrets are co-located with .enc.yaml suffix
- Verify infrastructure components are in gitops/infrastructure/

### Integration Testing

While not part of the automated test suite, integration tests should be performed manually or in a test cluster:

- Deploy cert-manager and verify ClusterIssuer becomes ready
- Request a certificate and verify it's issued by Let's Encrypt
- Deploy PostgreSQL with encrypted secret and verify pod starts successfully
- Deploy Redis with encrypted secret and verify authentication works
- Deploy Authentik and verify HTTPS access via subdomain
- Verify Flux decrypts SOPS secrets correctly
- Verify DNS records are created in Cloudflare (if using external-dns)

### Test Execution

```bash
# Run all tests
uv run pytest tests/

# Run only unit tests
uv run pytest tests/unit/

# Run only property-based tests
uv run pytest tests/properties/

# Run with coverage
uv run pytest --cov=cluster_manager --cov-report=html

# Run specific property test
uv run pytest tests/properties/test_production_services.py::test_age_key_format -v
```

### Continuous Integration

Tests should run automatically on:
- Every commit to feature branches
- Pull requests to main branch
- Scheduled nightly runs for property tests with extended iterations

CI pipeline should:
1. Run linting (ruff)
2. Run type checking (mypy)
3. Run unit tests
4. Run property-based tests
5. Generate coverage report
6. Fail if coverage drops below threshold (e.g., 80%)



## DNS-Based Service Access via Traefik

### Overview

Services deployed in the cluster are accessible from any machine on the Tailscale network using DNS names (postgres.almckay.io, redis.almckay.io, auth.almckay.io). This approach provides location independence - services can move between nodes or scale across multiple nodes without requiring client reconfiguration.

### How It Works

1. **Traefik Ingress Controller**: K3s includes Traefik as the default ingress controller, exposed as a LoadBalancer service
2. **TCP Routing**: Traefik supports TCP routing via IngressRouteTCP custom resources for non-HTTP protocols
3. **DNS Resolution**: All service DNS names resolve to the Traefik LoadBalancer IP (on Tailscale interface)
4. **Traffic Routing**: Traefik routes incoming connections to the appropriate backend ClusterIP service based on port
5. **Tailscale Network**: Traefik LoadBalancer is exposed on the node's Tailscale IP, making it accessible to all Tailscale clients

### Service Exposure Strategy

**PostgreSQL (postgres.almckay.io:5432)**:
- Backend: ClusterIP service in database namespace
- Routing: IngressRouteTCP with entryPoint "postgresql" (port 5432)
- DNS: A record pointing to Traefik LoadBalancer IP
- Use case: Database connections from development machines, applications on Tailscale network
- Connection: `psql -h postgres.almckay.io -p 5432 -U <user> -d <database>`

**Redis (redis.almckay.io:6379)**:
- Backend: ClusterIP service in cache namespace
- Routing: IngressRouteTCP with entryPoint "redis" (port 6379)
- DNS: A record pointing to Traefik LoadBalancer IP
- Use case: Cache access from applications, development tools
- Connection: `redis-cli -h redis.almckay.io -p 6379 -a <password>`

**Authentik (auth.almckay.io:443)**:
- Backend: ClusterIP service in auth namespace
- Routing: Standard Ingress resource for HTTPS
- DNS: A record pointing to Traefik LoadBalancer IP
- TLS: Automatic certificate from Let's Encrypt via cert-manager
- Use case: Web-based authentication, SSO for applications
- Connection: `https://auth.almckay.io`

### Security Considerations

1. **Network Isolation**: Services are only accessible to machines on the Tailscale network (authenticated devices)
2. **Authentication**: All services require authentication (PostgreSQL password, Redis password, Authentik login)
3. **Encryption**:
   - Tailscale provides encrypted mesh networking (WireGuard)
   - Authentik uses TLS certificates from Let's Encrypt
   - Database connections can use TLS (optional configuration)
4. **Access Control**: Tailscale ACLs can restrict which devices can access specific services

### Traefik Configuration

**Custom Entry Points**:
Traefik needs to be configured with additional TCP entry points for PostgreSQL and Redis:

```yaml
# Traefik HelmChart values or ConfigMap
additionalArguments:
  - "--entrypoints.postgresql.address=:5432/tcp"
  - "--entrypoints.redis.address=:6379/tcp"

ports:
  postgresql:
    port: 5432
    expose: true
    exposedPort: 5432
    protocol: TCP
  redis:
    port: 6379
    expose: true
    exposedPort: 6379
    protocol: TCP
```

### DNS Configuration

After deployment, configure DNS records in Cloudflare:

```bash
# Get Traefik LoadBalancer IP (on Tailscale interface)
kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Create A records in Cloudflare:
# postgres.almckay.io → <traefik-lb-ip>
# redis.almckay.io → <traefik-lb-ip>
# auth.almckay.io → <traefik-lb-ip>
```

### Client Configuration Examples

**PostgreSQL Connection String**:
```bash
# From any Tailscale-connected machine
export PGHOST=postgres.almckay.io
export PGPORT=5432
export PGUSER=<username>
export PGPASSWORD=<password>
export PGDATABASE=<database>

psql
```

**Redis Connection**:
```bash
# From any Tailscale-connected machine
redis-cli -h redis.almckay.io -p 6379 -a <password>
```

**Application Configuration**:
```python
# Django settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': 'postgres.almckay.io',
        'PORT': 5432,
        'NAME': '<database>',
        'USER': '<username>',
        'PASSWORD': '<password>',
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://:<password>@redis.almckay.io:6379',
    }
}
```

**Node.js Configuration**:
```javascript
// PostgreSQL
const { Pool } = require('pg');
const pool = new Pool({
  host: 'postgres.almckay.io',
  port: 5432,
  database: '<database>',
  user: '<username>',
  password: '<password>',
});

// Redis
const redis = require('redis');
const client = redis.createClient({
  socket: {
    host: 'redis.almckay.io',
    port: 6379
  },
  password: '<password>'
});
```

### Benefits of DNS-Based Access

1. **Location Independence**: Services can move between nodes without client reconfiguration
2. **Multi-Node Support**: Future load balancing across multiple PostgreSQL/Redis instances
3. **Consistent Naming**: Same DNS names work from inside and outside the cluster
4. **Simplified Configuration**: No need to track individual node IPs
5. **High Availability**: Easy to add redundancy by deploying multiple replicas

### Monitoring and Troubleshooting

**Check Traefik Status**:
```bash
# Verify Traefik LoadBalancer IP
kubectl get svc -n kube-system traefik

# Check IngressRouteTCP resources
kubectl get ingressroutetcp -A

# View Traefik logs
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik
```

**Test DNS Resolution**:
```bash
# From Tailscale-connected machine
nslookup postgres.almckay.io
nslookup redis.almckay.io
nslookup auth.almckay.io
```

**Test Connectivity**:
```bash
# Test PostgreSQL
nc -zv postgres.almckay.io 5432
psql -h postgres.almckay.io -p 5432 -U <user> -d <database>

# Test Redis
nc -zv redis.almckay.io 6379
redis-cli -h redis.almckay.io -p 6379 -a <password> PING

# Test Authentik
curl -I https://auth.almckay.io
```

**Firewall Considerations**:
- K3s nodes should allow traffic on ports 5432, 6379, 80, 443 from Tailscale interface
- The existing cluster setup should already have appropriate firewall rules for Tailscale
- If connectivity fails, check firewall rules: `sudo ufw status` or `sudo iptables -L`
