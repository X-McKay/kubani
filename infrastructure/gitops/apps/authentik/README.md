# Authentik Deployment

This directory contains the Kubernetes manifests for deploying Authentik, an open-source identity provider and authentication service.

## Overview

Authentik provides:
- Single Sign-On (SSO) for applications
- User authentication and authorization
- OAuth2/OIDC provider
- SAML provider
- LDAP provider
- User management and self-service portal

## Components

- **namespace.yaml**: Creates the `auth` namespace
- **secret.enc.yaml**: Encrypted credentials (SOPS encrypted)
- **helmrelease.yaml**: Flux HelmRelease for Authentik deployment
- **ingress.yaml**: Ingress resource for HTTPS access at auth.almckay.io
- **certificate.yaml**: cert-manager Certificate for TLS
- **kustomization.yaml**: Kustomize configuration

## Configuration

### Database Connection

Authentik is configured to use the PostgreSQL instance deployed in the `database` namespace:
- Host: `postgresql.database.svc.cluster.local`
- Database: `authentik`
- User: `authentik`
- Password: Retrieved from `authentik-credentials` secret

### Secrets

The `authentik-credentials` secret contains:
- `secret-key`: Django secret key for session encryption
- `postgres-password`: PostgreSQL database password
- `bootstrap-password`: Initial admin password
- `bootstrap-token`: Initial API token

### Access

Authentik is accessible at:
- **URL**: https://auth.almckay.io
- **Initial Admin**: `akadmin`
- **Initial Password**: From `bootstrap-password` in secret

## DNS Configuration

Create an A record in Cloudflare:
```
auth.almckay.io → <traefik-loadbalancer-ip>
```

Get the Traefik LoadBalancer IP:
```bash
kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

## TLS Certificate

The certificate is automatically issued by cert-manager using Let's Encrypt:
- Issuer: `letsencrypt-prod` ClusterIssuer
- DNS-01 challenge via Cloudflare
- Certificate stored in `authentik-tls` secret

Check certificate status:
```bash
kubectl get certificate -n auth
kubectl describe certificate authentik-cert -n auth
```

## Deployment

The deployment is managed by Flux CD. After committing changes to Git:

1. Flux will detect the changes
2. Create the namespace
3. Decrypt and apply the secret
4. Deploy Authentik via Helm
5. Create the Ingress and request certificate
6. cert-manager will issue the TLS certificate

Monitor deployment:
```bash
# Check HelmRelease status
kubectl get helmrelease -n auth

# Check pods
kubectl get pods -n auth

# Check Ingress
kubectl get ingress -n auth

# Check certificate
kubectl get certificate -n auth
```

## Verification

1. **Check pod status**:
   ```bash
   kubectl get pods -n auth
   ```

2. **Check logs**:
   ```bash
   kubectl logs -n auth -l app.kubernetes.io/name=authentik
   ```

3. **Test HTTPS access**:
   ```bash
   curl -I https://auth.almckay.io
   ```

4. **Access web interface**:
   Open https://auth.almckay.io in a browser

## Initial Setup

After deployment:

1. Navigate to https://auth.almckay.io
2. Log in with:
   - Username: `akadmin`
   - Password: From `bootstrap-password` secret
3. Complete the initial setup wizard
4. Configure applications and providers as needed

## Troubleshooting

### Pod not starting

Check pod events and logs:
```bash
kubectl describe pod -n auth <pod-name>
kubectl logs -n auth <pod-name>
```

Common issues:
- Database connection failure: Verify PostgreSQL is running and credentials are correct
- Secret not found: Ensure `authentik-credentials` secret exists and is decrypted

### Certificate not issued

Check certificate status:
```bash
kubectl describe certificate authentik-cert -n auth
kubectl get certificaterequest -n auth
```

Common issues:
- DNS challenge failure: Verify Cloudflare API token has DNS edit permissions
- Rate limit: Use `letsencrypt-staging` issuer for testing

### Ingress not routing

Check Ingress status:
```bash
kubectl describe ingress authentik-ingress -n auth
```

Verify:
- Traefik is running: `kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik`
- DNS resolves: `nslookup auth.almckay.io`
- Service exists: `kubectl get svc -n auth`

## Updating

To update Authentik:

1. Edit `helmrelease.yaml` to change the version
2. Commit and push changes
3. Flux will automatically upgrade the deployment

Manual upgrade:
```bash
flux reconcile helmrelease authentik -n auth
```

## Backup

Authentik data is stored in PostgreSQL. Backup the database regularly:
```bash
kubectl exec -n database postgresql-0 -- pg_dump -U authentik authentik > authentik-backup.sql
```

## References

- [Authentik Documentation](https://goauthentik.io/docs/)
- [Authentik Helm Chart](https://github.com/goauthentik/helm)
- [cert-manager Documentation](https://cert-manager.io/docs/)
