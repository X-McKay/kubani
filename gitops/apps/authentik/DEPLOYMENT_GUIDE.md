# Authentik Deployment Guide

## Prerequisites

Before deploying Authentik, ensure the following are in place:

1. **PostgreSQL Database**: The PostgreSQL instance must be running in the `database` namespace
2. **cert-manager**: Must be deployed and configured with the `letsencrypt-prod` ClusterIssuer
3. **Traefik Ingress Controller**: Must be running and exposed on the Tailscale network
4. **SOPS/Age Encryption**: Flux must be configured to decrypt SOPS-encrypted secrets
5. **DNS Configuration**: An A record for `auth.almckay.io` pointing to the Traefik LoadBalancer IP

## Deployment Steps

### 1. Verify Prerequisites

Check that PostgreSQL is running:
```bash
kubectl get pods -n database
kubectl get svc -n database
```

Check that cert-manager is ready:
```bash
kubectl get pods -n cert-manager
kubectl get clusterissuer letsencrypt-prod
```

Check that Traefik is running:
```bash
kubectl get svc -n kube-system traefik
```

### 2. Configure DNS

Get the Traefik LoadBalancer IP:
```bash
kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

Create an A record in Cloudflare:
- **Name**: `auth`
- **Type**: `A`
- **Content**: `<traefik-loadbalancer-ip>`
- **TTL**: Auto
- **Proxy status**: DNS only (not proxied)

Verify DNS resolution:
```bash
nslookup auth.almckay.io
```

### 3. Verify Encrypted Secret

The encrypted secret should already exist at `gitops/apps/authentik/secret.enc.yaml`. Verify it contains the SOPS metadata:
```bash
grep "sops:" gitops/apps/authentik/secret.enc.yaml
```

### 4. Commit and Push Changes

If you've made any changes to the manifests:
```bash
git add gitops/apps/authentik/
git add gitops/infrastructure/sources/authentik.yaml
git add gitops/apps/kustomization.yaml
git commit -m "Add Authentik deployment with TLS"
git push
```

### 5. Monitor Deployment

Flux will automatically detect the changes and deploy Authentik. Monitor the deployment:

**Check Flux reconciliation**:
```bash
flux get kustomizations
flux get helmreleases -n auth
```

**Check namespace creation**:
```bash
kubectl get namespace auth
```

**Check secret decryption**:
```bash
kubectl get secret -n auth authentik-credentials
```

**Check HelmRelease status**:
```bash
kubectl get helmrelease -n auth authentik
kubectl describe helmrelease -n auth authentik
```

**Check pods**:
```bash
kubectl get pods -n auth
kubectl logs -n auth -l app.kubernetes.io/name=authentik --tail=50
```

**Check Ingress**:
```bash
kubectl get ingress -n auth
kubectl describe ingress -n auth authentik-ingress
```

**Check Certificate**:
```bash
kubectl get certificate -n auth
kubectl describe certificate -n auth authentik-cert
```

### 6. Verify TLS Certificate

Wait for the certificate to be issued (this may take a few minutes):
```bash
kubectl get certificate -n auth authentik-cert -w
```

The certificate should show `Ready: True` when issued.

Check certificate details:
```bash
kubectl describe certificate -n auth authentik-cert
kubectl get certificaterequest -n auth
```

### 7. Access Authentik

Once the certificate is issued and pods are running, access Authentik:

**Test HTTPS access**:
```bash
curl -I https://auth.almckay.io
```

**Open in browser**:
```
https://auth.almckay.io
```

### 8. Initial Login

Get the bootstrap password from the secret:
```bash
kubectl get secret -n auth authentik-credentials -o jsonpath='{.data.bootstrap-password}' | base64 -d
echo
```

Log in with:
- **Username**: `akadmin`
- **Password**: (from the command above)

## Troubleshooting

### Pods Not Starting

**Check pod status**:
```bash
kubectl get pods -n auth
kubectl describe pod -n auth <pod-name>
kubectl logs -n auth <pod-name>
```

**Common issues**:
- Database connection failure: Verify PostgreSQL is running and credentials are correct
- Secret not found: Ensure Flux has decrypted the secret
- Image pull errors: Check network connectivity and image availability

### Certificate Not Issued

**Check certificate status**:
```bash
kubectl describe certificate -n auth authentik-cert
kubectl get certificaterequest -n auth
kubectl describe certificaterequest -n auth <request-name>
```

**Common issues**:
- DNS challenge failure: Verify Cloudflare API token has DNS edit permissions
- DNS not propagated: Wait a few minutes for DNS to propagate
- Rate limit: Use `letsencrypt-staging` issuer for testing

### Ingress Not Routing

**Check Ingress status**:
```bash
kubectl describe ingress -n auth authentik-ingress
```

**Verify**:
- Traefik is running: `kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik`
- DNS resolves: `nslookup auth.almckay.io`
- Service exists: `kubectl get svc -n auth`
- Backend pods are ready: `kubectl get pods -n auth`

### Database Connection Issues

**Check PostgreSQL connectivity**:
```bash
kubectl exec -n auth <authentik-pod> -- nc -zv postgresql.database.svc.cluster.local 5432
```

**Verify credentials**:
```bash
kubectl get secret -n auth authentik-credentials -o yaml
kubectl get secret -n database postgresql-credentials -o yaml
```

Ensure the `postgres-password` in both secrets matches.

## Post-Deployment Configuration

After successful deployment:

1. **Change Admin Password**: Log in and change the default admin password
2. **Configure Email**: Set up email settings for notifications
3. **Create Applications**: Configure applications that will use Authentik for authentication
4. **Set Up Providers**: Configure OAuth2/OIDC or SAML providers as needed
5. **Create Users**: Add users or configure external user sources (LDAP, etc.)

## Updating Authentik

To update to a new version:

1. Edit `gitops/apps/authentik/helmrelease.yaml`
2. Change the `version` field to the desired version
3. Commit and push changes
4. Flux will automatically upgrade the deployment

Manual upgrade:
```bash
flux reconcile helmrelease authentik -n auth
```

## Backup and Recovery

Authentik data is stored in PostgreSQL. To backup:

```bash
kubectl exec -n database postgresql-0 -- pg_dump -U authentik authentik > authentik-backup.sql
```

To restore:
```bash
kubectl exec -i -n database postgresql-0 -- psql -U authentik authentik < authentik-backup.sql
```

## References

- [Authentik Documentation](https://goauthentik.io/docs/)
- [Authentik Helm Chart](https://github.com/goauthentik/helm)
- [cert-manager Documentation](https://cert-manager.io/docs/)
- [Traefik Ingress Documentation](https://doc.traefik.io/traefik/providers/kubernetes-ingress/)
