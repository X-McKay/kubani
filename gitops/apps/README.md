# Applications

This directory contains application manifests managed by Flux CD.

## Directory Structure

```
apps/
├── base/                    # Base application configurations
│   ├── nginx/              # Example: nginx web server
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── ingress.yaml
│   │   ├── configmap.yaml
│   │   ├── secret.yaml
│   │   └── kustomization.yaml
│   └── hello-world/        # Example: simple hello world app
│       ├── deployment.yaml
│       ├── service.yaml
│       └── kustomization.yaml
└── overlays/               # Environment-specific configurations
    └── production/         # Production environment
        ├── nginx-patch.yaml
        └── kustomization.yaml
```

## Adding a New Application

### 1. Create Base Configuration

Create a new directory under `base/` for your application:

```bash
mkdir -p apps/base/my-app
```

### 2. Add Kubernetes Manifests

Create the necessary Kubernetes resources:

**deployment.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: my-app
        image: my-app:latest
        ports:
        - containerPort: 8080
```

**service.yaml**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app
spec:
  selector:
    app: my-app
  ports:
  - port: 80
    targetPort: 8080
```

### 3. Create Kustomization

Create `kustomization.yaml` to tie everything together:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml

commonLabels:
  app: my-app
  managed-by: flux

namespace: default
```

### 4. (Optional) Create Environment Overlays

For environment-specific configurations, create overlays:

```bash
mkdir -p apps/overlays/production
```

Create a patch file `apps/overlays/production/my-app-patch.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 5
```

Create `apps/overlays/production/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

bases:
  - ../../base/my-app

namespace: production

patchesStrategicMerge:
  - my-app-patch.yaml
```

### 5. Commit and Push

```bash
git add apps/base/my-app
git commit -m "Add my-app application"
git push
```

Flux will automatically detect the changes and deploy your application!

## Managing Secrets

**Important:** Never commit unencrypted secrets to Git!

### Option 1: Mozilla SOPS

Install SOPS and configure it:

```bash
# Install SOPS
brew install sops  # macOS
# or
curl -LO https://github.com/mozilla/sops/releases/download/v3.8.1/sops-v3.8.1.linux.amd64
mv sops-v3.8.1.linux.amd64 /usr/local/bin/sops
chmod +x /usr/local/bin/sops

# Encrypt a secret
sops --encrypt --in-place apps/base/my-app/secret.yaml

# Configure Flux to decrypt
kubectl create secret generic sops-gpg \
  --namespace=flux-system \
  --from-file=sops.asc=/path/to/private.key
```

### Option 2: Sealed Secrets

Install Sealed Secrets controller:

```bash
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Install kubeseal CLI
brew install kubeseal  # macOS

# Seal a secret
kubeseal --format=yaml < secret.yaml > sealed-secret.yaml
```

### Option 3: External Secrets Operator

Use External Secrets Operator to sync from external secret stores (AWS Secrets Manager, HashiCorp Vault, etc.).

## ConfigMaps

ConfigMaps can be committed directly to Git as they contain non-sensitive configuration:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-app-config
data:
  app.properties: |
    environment=production
    log_level=info
  config.json: |
    {
      "feature_flags": {
        "new_ui": true
      }
    }
```

## Best Practices

1. **Organize by Application**: Each application should have its own directory
2. **Use Kustomize**: Leverage Kustomize for environment-specific configurations
3. **Encrypt Secrets**: Always encrypt secrets before committing
4. **Resource Limits**: Always specify resource requests and limits
5. **Health Checks**: Include liveness and readiness probes
6. **Labels**: Use consistent labeling for all resources
7. **Namespaces**: Use namespaces to isolate applications
8. **Image Tags**: Use specific image tags, not `latest`
9. **Documentation**: Document application-specific configuration in README files

## Troubleshooting

### Check Flux Status

```bash
flux get kustomizations
flux get helmreleases
```

### View Flux Logs

```bash
flux logs --all-namespaces --follow
```

### Force Reconciliation

```bash
flux reconcile kustomization flux-system --with-source
```

### Suspend/Resume

```bash
flux suspend kustomization my-app
flux resume kustomization my-app
```

## Examples

See the included example applications:
- `nginx/` - Full-featured web server with ConfigMap, Secret, and Ingress
- `hello-world/` - Minimal application example
