# Cert-Manager Configuration

This directory contains the cert-manager deployment and configuration for automated TLS certificate management.

## Components

- **namespace.yaml**: Creates the cert-manager namespace
- **helmrelease.yaml**: Deploys cert-manager using the Jetstack Helm chart
- **cloudflare-secret.yaml**: Contains the Cloudflare API token for DNS-01 challenges (should be encrypted with SOPS)
- **clusterissuer.yaml**: Let's Encrypt production issuer
- **clusterissuer-staging.yaml**: Let's Encrypt staging issuer (for testing)

## Setup Instructions

### 1. Encrypt the Cloudflare API Token

Before committing, encrypt the cloudflare-secret.yaml file:

```bash
# Ensure you have the age key configured in .sops.yaml
sops --encrypt --in-place gitops/infrastructure/cert-manager/cloudflare-secret.yaml

# Rename to indicate it's encrypted
mv gitops/infrastructure/cert-manager/cloudflare-secret.yaml \
   gitops/infrastructure/cert-manager/cloudflare-secret.enc.yaml
```

Update the kustomization.yaml to reference the encrypted file.

### 2. Obtain Cloudflare API Token

1. Log in to Cloudflare dashboard
2. Go to My Profile → API Tokens
3. Create a token with the following permissions:
   - Zone:DNS:Edit for the almckay.io zone
4. Copy the token and replace `REPLACE_WITH_YOUR_CLOUDFLARE_API_TOKEN` in cloudflare-secret.yaml

### 3. Verify Deployment

After Flux syncs the changes:

```bash
# Check cert-manager pods
kubectl get pods -n cert-manager

# Check ClusterIssuer status
kubectl get clusterissuer

# Describe to see detailed status
kubectl describe clusterissuer letsencrypt-prod
```

## Usage

### Request a Certificate

Create a Certificate resource in your application namespace:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: my-app-tls
  namespace: my-app
spec:
  secretName: my-app-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - myapp.almckay.io
```

### Use with Ingress

Add the cert-manager annotation to your Ingress:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - myapp.almckay.io
      secretName: my-app-tls
  rules:
    - host: myapp.almckay.io
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  number: 80
```

## Troubleshooting

### Check Certificate Status

```bash
kubectl get certificate -A
kubectl describe certificate <name> -n <namespace>
```

### Check CertificateRequest

```bash
kubectl get certificaterequest -A
kubectl describe certificaterequest <name> -n <namespace>
```

### Check Challenge Status

```bash
kubectl get challenge -A
kubectl describe challenge <name> -n <namespace>
```

### View Cert-Manager Logs

```bash
kubectl logs -n cert-manager -l app=cert-manager
```

### Common Issues

1. **Cloudflare API token invalid**: Verify token has correct permissions
2. **DNS propagation timeout**: Challenges may take a few minutes to complete
3. **Rate limit exceeded**: Use staging issuer for testing
