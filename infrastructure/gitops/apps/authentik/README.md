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
- **blueprints-configmap.yaml**: Declarative Authentik applications and proxy providers
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

Never print secret values into a terminal transcript, shell history, CI log, or
PR. Retrieve a credential only through the approved owner-controlled secret or
password-manager workflow when an interactive login actually requires it.

### Blueprints

The HelmRelease mounts `authentik-blueprints` through
`values.blueprints.configMaps`. Authentik instantiates mounted blueprints with
`blueprints.goauthentik.io/instantiate: "true"`.

`blueprints-configmap.yaml` currently declares:
- `Kubani FalkorDB Browser` proxy provider and `falkordb` application
- `Kubani Qdrant` proxy provider and `qdrant` application
- embedded outpost assignment for both proxy providers
- the native OIDC `Starbase` application and public `starbase-kubani` provider,
  restricted to the Authorization Code grant and exact authorization callback,
  with a dedicated non-superuser `starbase-operators` access group, a 15-minute
  access/ID-token lifetime, and an eight-hour refresh-token ceiling

Keep proxy-provider state here instead of creating it manually in the Authentik
UI. Ingresses should only attach Authentik forward-auth middleware after the
matching proxy provider and outpost assignment are declared.

The Starbase blueprint creates the group empty. Adding a user to
`starbase-operators` remains a deliberate Authentik directory operation and
must be followed by member and non-member authorization checks. Starbase also
checks the exact `groups` claim; the Authentik binding is not its only
authorization layer.

The 15-minute access-token bound is part of the Starbase gateway contract;
Starbase fails closed on a longer identity lifetime. The eight-hour refresh
ceiling does not activate refresh capability. The Starbase deployment continues
to set `STARBASE_OIDC_REFRESH_ENABLED=false` until the separately required live
revocation evidence is accepted.

Mounted blueprint changes are applied by the Authentik worker as an
[atomic database transaction](https://docs.goauthentik.io/customize/blueprints/#blueprint-execution).
[Removing a file](https://docs.goauthentik.io/customize/blueprints/#as-a-local-file)
removes the blueprint instance but does **not** remove objects it created.
Rollback therefore uses a
reviewed forward GitOps change that first sets the Starbase binding,
application, provider, scope mapping, and finally the dedicated group to
`state: absent`. Verify the discovery endpoint returns 404 before removing the
file in a later cleanup revision. Do not delete the group until membership and
reuse have been checked.

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
kubectl describe certificate authentik-tls -n auth
```

## Deployment

The deployment is managed by Flux CD. After committing changes to Git:

1. Flux will detect the changes
2. Create the namespace
3. Decrypt and apply the secret
4. Deploy Authentik via Helm
5. Create the Ingress and request certificate
6. cert-manager will issue the TLS certificate

Changes to the Authentik version, replicas, migration resources, or database
state must follow the
[upgrade and recovery runbook](../../../../docs/infrastructure/operations/authentik-upgrade.md).
Do not perform a direct version jump or manually retry a failed migration.

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

5. **Check proxy blueprint behavior**:
   ```bash
   curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://falkordb.almckay.io/
   curl -skL -o /dev/null -w '%{http_code} %{url_effective}\n' https://qdrant.almckay.io/
   ```

   Both routes should land on the Authentik login flow for unauthenticated
   requests.

6. **Check Starbase OIDC without reading credentials**:
   ```bash
   ./infrastructure/scripts/validate-starbase-oidc.sh
   ```

   This read-only verifier checks the mounted owner ConfigMap, discovery, S256
   PKCE advertisement, JWKS, and the fail-closed Starbase workload state. Group
   membership and member/non-member denial remain explicit browser checks.

## Initial Setup

After deployment:

1. Navigate to https://auth.almckay.io
2. Log in with:
   - Username: `akadmin`
   - Password: From `bootstrap-password` secret
3. Complete the initial setup wizard
4. Configure applications and providers as needed

For an existing installation, do not repeat bootstrap setup or rotate existing
identity state merely because a workload was restarted.

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
kubectl describe certificate authentik-tls -n auth
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
