# Requirements Document

## Introduction

This document specifies the requirements for deploying production-ready services on a Kubernetes cluster with custom domain management, TLS certificate automation, encrypted secrets management, and core infrastructure services (PostgreSQL, Redis, and Authentik). The system integrates with Cloudflare for DNS management, uses cert-manager for automated TLS certificates, SOPS with age encryption for secrets, and follows GitOps practices for declarative service deployment.

## Glossary

- **Service Deployment System**: The complete solution for deploying and managing production services on Kubernetes
- **Cert-Manager**: A Kubernetes controller that automates TLS certificate issuance and renewal
- **SOPS**: Secrets OPerationS - a tool for encrypting secrets in Git repositories
- **Age Encryption**: A modern encryption tool used by SOPS for encrypting Kubernetes secrets
- **Cloudflare DNS**: The DNS provider managing the custom domain almckay.io
- **HelmRelease**: A Flux CD custom resource that defines a Helm chart deployment
- **Sealed Secret**: An encrypted Kubernetes secret that can be safely stored in Git
- **PostgreSQL Database**: A relational database service deployed in the cluster
- **Redis Cache**: An in-memory data store deployed in the cluster
- **Authentik**: An identity provider and authentication service
- **DNS Challenge**: An ACME challenge method that validates domain ownership via DNS records
- **ClusterIssuer**: A cert-manager resource that defines how to obtain TLS certificates
- **GitOps Repository**: The Git repository containing encrypted secrets and service manifests

## Requirements

### Requirement 1

**User Story:** As a cluster administrator, I want to configure cert-manager with Cloudflare DNS integration, so that I can automatically obtain and renew TLS certificates for services using the almckay.io domain.

#### Acceptance Criteria

1. WHEN cert-manager is deployed THEN the Service Deployment System SHALL install cert-manager CRDs and controllers via GitOps
2. WHEN configuring certificate issuance THEN the Service Deployment System SHALL create a ClusterIssuer that uses Let's Encrypt with DNS-01 challenge
3. WHEN the ClusterIssuer is created THEN the Service Deployment System SHALL configure it to use Cloudflare API credentials for DNS validation
4. WHEN a service requests a certificate THEN the Service Deployment System SHALL automatically create DNS records in Cloudflare to complete the challenge
5. WHEN a certificate is issued THEN the Service Deployment System SHALL store it as a Kubernetes secret accessible to the requesting service

### Requirement 2

**User Story:** As a cluster administrator, I want to encrypt sensitive secrets using SOPS with age encryption, so that I can safely store database passwords and API keys in my Git repository.

#### Acceptance Criteria

1. WHEN initializing secrets management THEN the Service Deployment System SHALL generate an age encryption key pair
2. WHEN the age key is generated THEN the Service Deployment System SHALL store the private key securely on the cluster
3. WHEN creating a secret manifest THEN the Service Deployment System SHALL provide templates for PostgreSQL, Redis, and Authentik secrets
4. WHEN a secret is encrypted THEN the Service Deployment System SHALL use SOPS to encrypt only the secret values while leaving metadata readable
5. WHEN Flux processes an encrypted secret THEN the Service Deployment System SHALL decrypt it using the age private key before applying to the cluster

### Requirement 3

**User Story:** As a cluster administrator, I want to deploy PostgreSQL with encrypted credentials, so that I have a production-ready database service with secure password management.

#### Acceptance Criteria

1. WHEN deploying PostgreSQL THEN the Service Deployment System SHALL create a HelmRelease manifest in the GitOps repository
2. WHEN PostgreSQL is configured THEN the Service Deployment System SHALL reference an encrypted secret containing the database password
3. WHEN PostgreSQL starts THEN the Service Deployment System SHALL configure persistent storage for database data
4. WHEN PostgreSQL is exposed THEN the Service Deployment System SHALL create a service accessible within the cluster
5. WHEN PostgreSQL is deployed THEN the Service Deployment System SHALL configure connection parameters including database name and user credentials

### Requirement 4

**User Story:** As a cluster administrator, I want to deploy Redis with encrypted credentials, so that I have a production-ready caching service with secure authentication.

#### Acceptance Criteria

1. WHEN deploying Redis THEN the Service Deployment System SHALL create a HelmRelease manifest in the GitOps repository
2. WHEN Redis is configured THEN the Service Deployment System SHALL reference an encrypted secret containing the Redis password
3. WHEN Redis starts THEN the Service Deployment System SHALL configure persistence for cache data
4. WHEN Redis is exposed THEN the Service Deployment System SHALL create a service accessible within the cluster
5. WHEN Redis is deployed THEN the Service Deployment System SHALL enable authentication using the encrypted password

### Requirement 5

**User Story:** As a cluster administrator, I want to deploy Authentik with custom domain and TLS, so that I have a centralized identity provider for authenticating users across my services.

#### Acceptance Criteria

1. WHEN deploying Authentik THEN the Service Deployment System SHALL create a HelmRelease manifest in the GitOps repository
2. WHEN Authentik is configured THEN the Service Deployment System SHALL reference encrypted secrets for database credentials and secret keys
3. WHEN Authentik is exposed THEN the Service Deployment System SHALL create an Ingress resource using the almckay.io domain
4. WHEN the Ingress is created THEN the Service Deployment System SHALL configure cert-manager annotations to automatically provision a TLS certificate
5. WHEN Authentik starts THEN the Service Deployment System SHALL configure it to use the deployed PostgreSQL instance as its database backend

### Requirement 6

**User Story:** As a cluster administrator, I want comprehensive documentation for secrets management, so that I can generate encryption keys, encrypt new secrets, and rotate credentials when needed.

#### Acceptance Criteria

1. WHEN setting up secrets management THEN the Service Deployment System SHALL provide documentation for generating the age key pair
2. WHEN encrypting secrets THEN the Service Deployment System SHALL provide step-by-step instructions for using SOPS with the age key
3. WHEN managing secrets THEN the Service Deployment System SHALL document the process for editing encrypted secrets in place
4. WHEN rotating credentials THEN the Service Deployment System SHALL provide procedures for updating encrypted secrets and triggering service restarts
5. WHEN troubleshooting THEN the Service Deployment System SHALL document common issues with decryption and Flux integration

### Requirement 7

**User Story:** As a cluster administrator, I want Flux configured to decrypt SOPS secrets automatically, so that encrypted manifests in Git are seamlessly applied to the cluster.

#### Acceptance Criteria

1. WHEN Flux is configured THEN the Service Deployment System SHALL create a Kubernetes secret containing the age private key
2. WHEN Flux processes manifests THEN the Service Deployment System SHALL configure the Flux Kustomization to enable SOPS decryption
3. WHEN an encrypted secret is committed THEN the Service Deployment System SHALL ensure Flux detects the change and applies the decrypted secret
4. WHEN decryption fails THEN the Service Deployment System SHALL report the error in the Flux Kustomization status
5. WHEN the age key is rotated THEN the Service Deployment System SHALL provide procedures for re-encrypting all secrets with the new key

### Requirement 8

**User Story:** As a developer, I want to access deployed services via custom subdomains, so that I can use memorable URLs like auth.almckay.io instead of IP addresses and ports.

#### Acceptance Criteria

1. WHEN a service requires external access THEN the Service Deployment System SHALL create an Ingress resource with a subdomain under almckay.io
2. WHEN the Ingress is created THEN the Service Deployment System SHALL automatically configure DNS records in Cloudflare
3. WHEN accessing the subdomain THEN the Service Deployment System SHALL route traffic to the appropriate service
4. WHEN TLS is required THEN the Service Deployment System SHALL ensure the Ingress uses the cert-manager issued certificate
5. WHEN multiple services are deployed THEN the Service Deployment System SHALL support multiple subdomains with independent TLS certificates

### Requirement 9

**User Story:** As a cluster administrator, I want all service configurations stored in the GitOps repository, so that I have a complete audit trail and can reproduce the entire deployment from Git.

#### Acceptance Criteria

1. WHEN services are deployed THEN the Service Deployment System SHALL store all HelmRelease manifests in the gitops/apps directory
2. WHEN secrets are created THEN the Service Deployment System SHALL store encrypted versions in the gitops/apps directory alongside service manifests
3. WHEN cert-manager is configured THEN the Service Deployment System SHALL store ClusterIssuer and certificate manifests in gitops/infrastructure
4. WHEN the repository is cloned THEN the Service Deployment System SHALL enable complete cluster recreation from the stored manifests
5. WHEN changes are made THEN the Service Deployment System SHALL ensure Flux automatically synchronizes the cluster state with Git

### Requirement 10

**User Story:** As a cluster administrator, I want validation checks for service deployments, so that I can verify PostgreSQL, Redis, and Authentik are running correctly with proper connectivity.

#### Acceptance Criteria

1. WHEN services are deployed THEN the Service Deployment System SHALL provide commands to check pod status for each service
2. WHEN validating PostgreSQL THEN the Service Deployment System SHALL verify database connectivity and authentication
3. WHEN validating Redis THEN the Service Deployment System SHALL verify cache connectivity and authentication
4. WHEN validating Authentik THEN the Service Deployment System SHALL verify the web interface is accessible via HTTPS
5. WHEN validating certificates THEN the Service Deployment System SHALL verify TLS certificates are issued and valid for all Ingress resources

### Requirement 11

**User Story:** As a Tailscale network user, I want to access deployed services from any machine on the Tailscale network using DNS names, so that I can use PostgreSQL, Redis, and Authentik from devices both inside and outside the Kubernetes cluster without worrying about IP addresses changing.

#### Acceptance Criteria

1. WHEN PostgreSQL is deployed THEN the Service Deployment System SHALL expose it at postgres.almckay.io on port 5432
2. WHEN Redis is deployed THEN the Service Deployment System SHALL expose it at redis.almckay.io on port 6379
3. WHEN Authentik is deployed THEN the Service Deployment System SHALL expose it at auth.almckay.io via HTTPS
4. WHEN DNS records are configured THEN the Service Deployment System SHALL create A records in Cloudflare pointing to the Ingress controller's Tailscale IP
5. WHEN services move between nodes THEN the Service Deployment System SHALL ensure DNS names continue to work without manual reconfiguration
