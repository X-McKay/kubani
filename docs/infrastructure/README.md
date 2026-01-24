# Infrastructure Documentation

Infrastructure as code, deployment, and operations documentation.

## Quick Links

- [**Production Checklist**](operations/production-checklist.md) - Deploy to production
- [**DNS & Traefik**](configuration/dns.md) - DNS and ingress setup
- [**GitOps Deployment**](gitops/guides/deploying-services.md) - Deploy via Flux

## Cluster Management

Node provisioning and cluster operations:

- [**Troubleshooting**](cluster/troubleshooting/) - Common cluster issues
  - [Flannel Routes](cluster/troubleshooting/flannel-routes.md) - Networking issues

## GitOps

Flux-based GitOps deployment:

- **Architecture**
  - [CI/CD Pipeline](gitops/architecture/ci-cd.md) - Build and deploy flow
- **Guides**
  - [Deploying Services](gitops/guides/deploying-services.md) - Deploy applications
  - [Service Validation](gitops/guides/service-validation.md) - Validate deployments
  - [GitOps Validation](gitops/guides/validation.md) - Validate GitOps setup

## Ansible

Infrastructure automation:

- Playbooks for cluster provisioning
- Node configuration
- Service deployment

**Documentation:**
- Ansible playbooks are in `infrastructure/ansible/`
- See [Production Checklist](operations/production-checklist.md) for usage

## Configuration

Service configuration guides:

- [**DNS & Traefik**](configuration/dns.md) - DNS records and ingress
- [**GPU Setup**](configuration/gpu.md) - NVIDIA GPU configuration
- [**Secrets Management**](configuration/secrets.md) - SOPS and age encryption
- [**Authentication**](configuration/authentication.md) - Authentik SSO setup
- [**Storage (NAS)**](configuration/storage.md) - NFS and SMB storage

## Operations

Production operations and maintenance:

- [**Production Checklist**](operations/production-checklist.md) - Production deployment guide
- **Maintenance**
  - [PVC Migration](operations/maintenance/pvc-migration.md) - Storage migration
- **Specialty Services**
  - [Minecraft Server](operations/specialty/minecraft-server.md) - Game server setup

## Common Commands

### Cluster Operations
```bash
# Discover Tailscale nodes
kubani-dev cluster discover

# Add a new node
kubani-dev cluster add-node worker-3 100.64.0.12 --role worker

# Provision cluster
kubani-dev cluster provision

# Check cluster status
kubani-dev cluster status
```

### GitOps Operations
```bash
# Validate service manifests
./scripts/validate_service.sh postgres

# Check Flux status
flux check

# Force reconciliation
flux reconcile source git flux-system
```

### Configuration
```bash
# Set cluster configuration
kubani-dev config set k3s_version v1.28.5+k3s1

# Show effective configuration
kubani-dev config show
```

## Related Documentation

- [Platform CLI](../platform/cli/) - kubani-dev commands
- [Architecture](../architecture/) - System design
- [Troubleshooting](../troubleshooting/) - Problem solving
