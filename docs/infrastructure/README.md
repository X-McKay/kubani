# Infrastructure Documentation

Operational documentation for the Kubani homelab cluster.

## Core References

- [Repository Scope](repository-scope.md)
- [Cluster Architecture](architecture.md)
- [Decision Record](decisions.md)
- [Cluster Stability Reference](cluster/cluster-stability.md)
- [Production Checklist](operations/production-checklist.md)
- [Scheduled Audit](operations/scheduled-audit.md)
- [Flannel Route Troubleshooting](../troubleshooting/flannel-routes-lost-after-tailscale-upgrade.md)
- [UFW Block Logs for Pod Traffic](../troubleshooting/ufw-block-logs-for-pod-traffic.md) — why these records are benign, and why iptables counters cannot be trusted on these hosts

## Configuration

- [DNS and Traefik](configuration/dns.md)
- [GPU Support](configuration/gpu.md)
- [Secrets Management](configuration/secrets.md)
- [Storage](configuration/storage.md)
- [Registry Access](configuration/registry.md)
- [Authentication](configuration/authentication.md)
- [Authentik App Access Pattern](configuration/authentik-app-access.md)

## GitOps

- [Deploying Services](gitops/guides/deploying-services.md)
- [Service Validation](gitops/guides/service-validation.md)
- [GitOps Validation](gitops/guides/validation.md)

## Operations

- [Authentik Upgrade And Recovery](operations/authentik-upgrade.md)
- [Production Checklist](operations/production-checklist.md)
