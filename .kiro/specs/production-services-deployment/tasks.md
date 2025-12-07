# Implementation Plan

- [x] 1. Set up SOPS and age encryption infrastructure
  - Create age key generation utility
  - Generate age key pair for the cluster
  - Create .sops.yaml configuration file with age public key
  - Create Kubernetes secret in flux-system namespace with age private key
  - Configure Flux Kustomization to enable SOPS decryption
  - _Requirements: 2.1, 2.2, 7.1, 7.2_

- [x] 1.1 Write property test for age key generation
  - **Property 1: Age key generation produces valid format**
  - **Validates: Requirements 2.1**

- [x] 1.2 Write property test for SOPS encryption metadata preservation
  - **Property 3: SOPS encryption preserves metadata readability**
  - **Validates: Requirements 2.4**

- [x] 2. Create secret template utilities and encrypted secrets
  - Implement credential dataclasses (PostgreSQL, Redis, Authentik, Cloudflare)
  - Implement template functions to generate Kubernetes secret manifests
  - Create encrypted secret for Cloudflare API token
  - Create encrypted secret for PostgreSQL credentials
  - Create encrypted secret for Redis credentials
  - Create encrypted secret for Authentik credentials
  - _Requirements: 2.3, 2.4_

- [x] 2.1 Write property test for secret template validation
  - **Property 2: Secret templates produce valid Kubernetes manifests**
  - **Validates: Requirements 2.3**

- [x] 3. Configure Traefik for TCP routing and deploy cert-manager
  - Configure Traefik with additional TCP entry points (postgresql:5432, redis:6379)
  - Update Traefik HelmChart or ConfigMap with custom ports
  - Create Helm repository source for Jetstack
  - Create cert-manager namespace
  - Create HelmRelease for cert-manager with CRD installation
  - Create ClusterIssuer for Let's Encrypt production with Cloudflare DNS-01 solver
  - Reference encrypted Cloudflare API token secret in ClusterIssuer
  - Organize manifests in gitops/infrastructure/
  - _Requirements: 1.1, 1.2, 1.3, 9.3, 11.3_

- [x] 4. Deploy PostgreSQL with encrypted credentials and DNS-based access
  - Create database namespace
  - Create HelmRelease for PostgreSQL using Bitnami chart
  - Configure HelmRelease to reference encrypted postgresql-credentials secret
  - Configure persistent storage with 20Gi volume
  - Configure ClusterIP service type for internal access
  - Create IngressRouteTCP for postgres.almckay.io routing to PostgreSQL service
  - Configure database name, username, and connection parameters
  - Organize manifests in gitops/apps/postgresql/
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 9.1, 9.2, 11.1_

- [x] 4.1 Write property test for HelmRelease secret references
  - **Property 4: HelmRelease manifests reference correct secrets**
  - **Validates: Requirements 3.2, 4.2, 5.2**

- [x] 4.2 Write property test for stateful service persistence
  - **Property 5: Stateful services have persistence configured**
  - **Validates: Requirements 3.3, 4.3**

- [x] 5. Deploy Redis with encrypted credentials and DNS-based access
  - Create cache namespace
  - Create HelmRelease for Redis using Bitnami chart
  - Configure HelmRelease to reference encrypted redis-credentials secret
  - Configure persistent storage with 8Gi volume
  - Configure ClusterIP service type for internal access
  - Create IngressRouteTCP for redis.almckay.io routing to Redis service
  - Enable authentication with password from secret
  - Organize manifests in gitops/apps/redis/
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 9.1, 9.2, 11.2_

- [x] 6. Deploy Authentik with custom domain and TLS
  - Create auth namespace
  - Create HelmRelease for Authentik
  - Configure HelmRelease to reference encrypted authentik-credentials secret
  - Configure PostgreSQL connection to use deployed PostgreSQL instance
  - Create Ingress resource for auth.almckay.io subdomain
  - Add cert-manager annotation to Ingress for automatic TLS
  - Create Certificate resource for auth.almckay.io
  - Organize manifests in gitops/apps/authentik/
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 8.1, 8.4, 9.1, 9.2_

- [x] 6.1 Write property test for Ingress TLS configuration
  - **Property 6: Ingress manifests have required TLS configuration**
  - **Validates: Requirements 5.3, 5.4, 8.1, 8.4**

- [x] 6.2 Write property test for multiple service Ingress independence
  - **Property 7: Multiple services have independent Ingress configurations**
  - **Validates: Requirements 8.5**

- [x] 6.3 Write property test for file organization consistency
  - **Property 8: Service manifests are organized in correct directories**
  - **Validates: Requirements 9.1, 9.2**

- [x] 6.4 Write property test for IngressRouteTCP configuration
  - **Property 9: Database services have IngressRouteTCP for DNS access**
  - **Validates: Requirements 11.1, 11.2**

- [x] 7. Create comprehensive secrets management documentation
  - Create docs/SECRETS_MANAGEMENT.md
  - Document age key generation process
  - Document SOPS encryption workflow with examples
  - Document editing encrypted secrets in place
  - Document credential rotation procedures
  - Document troubleshooting for common decryption issues
  - Document Flux SOPS integration configuration
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.5_

- [x] 8. Create service validation utilities and DNS configuration
  - Create validation script for checking pod status
  - Create validation script for PostgreSQL connectivity via postgres.almckay.io
  - Create validation script for Redis connectivity via redis.almckay.io
  - Create validation script for Authentik HTTPS access via auth.almckay.io
  - Create validation script for certificate status
  - Create script to retrieve Traefik LoadBalancer IP for DNS configuration
  - Document DNS record creation in Cloudflare (A records for postgres, redis, auth)
  - Document validation commands and DNS-based access in README or CLI
  - _Requirements: 10.1, 11.4, 11.5_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Create Flux Kustomization resources for deployment order
  - Create Kustomization for infrastructure components with SOPS decryption
  - Create Kustomization for applications with dependency on infrastructure
  - Configure proper dependency chain: infrastructure → databases → applications
  - _Requirements: 7.2, 9.5_

- [x] 11. Final integration and documentation
  - Update main README with production services deployment section
  - Add quickstart guide for deploying services
  - Document DNS configuration requirements for Cloudflare (A records for postgres, redis, auth)
  - Document Cloudflare API token creation and permissions
  - Document DNS-based access for PostgreSQL (postgres.almckay.io) and Redis (redis.almckay.io)
  - Document Traefik TCP routing configuration
  - Document how to retrieve Traefik LoadBalancer IP for DNS setup
  - Create troubleshooting guide for common deployment issues
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 11.4, 11.5_

- [x] 12. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
