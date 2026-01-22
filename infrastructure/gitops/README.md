# GitOps Repository Structure

This directory contains Kubernetes manifests managed by Flux CD for declarative application deployment.

## Directory Structure

```
gitops/
├── flux-system/          # Flux CD controllers and configuration
│   ├── gotk-components.yaml    # Flux controllers (auto-generated)
│   ├── gotk-sync.yaml          # Git sync configuration
│   └── kustomization.yaml      # Flux system kustomization
├── infrastructure/       # Infrastructure components
│   ├── sources/         # Helm repositories and Git sources
│   │   ├── bitnami.yaml
│   │   └── kustomization.yaml
│   ├── storage/         # Storage classes and persistent volumes
│   │   ├── local-path-storage.yaml
│   │   └── kustomization.yaml
│   └── networking/      # Network policies and ingress
│       ├── network-policy.yaml
│       └── kustomization.yaml
└── apps/                # Applications
    ├── base/            # Base application configurations
    │   ├── nginx/       # Example: nginx web server
    │   │   ├── deployment.yaml
    │   │   ├── service.yaml
    │   │   ├── ingress.yaml
    │   │   ├── configmap.yaml
    │   │   ├── secret.yaml
    │   │   └── kustomization.yaml
    │   └── hello-world/ # Example: simple app
    │       ├── deployment.yaml
    │       ├── service.yaml
    │       └── kustomization.yaml
    └── overlays/        # Environment-specific overlays
        └── production/  # Production environment
            ├── nginx-patch.yaml
            └── kustomization.yaml
```

## How It Works

1. **Flux CD monitors this directory** in the Git repository
2. **When changes are committed**, Flux automatically applies them to the cluster
3. **Applications are organized** using Kustomize for environment-specific configurations
4. **Infrastructure components** are separated from applications for better organization
5. **Each application** is isolated in its own directory to prevent conflicts

## GitOps Workflow

### 1. Bootstrap Flux (One-time Setup)

Bootstrap Flux to your cluster:

```bash
# With SSH
flux bootstrap git \
  --url=ssh://git@github.com/your-org/your-repo \
  --branch=main \
  --path=./gitops \
  --private-key-file=~/.ssh/id_rsa

# With HTTPS and token
export GITHUB_TOKEN=<your-token>
flux bootstrap github \
  --owner=your-org \
  --repository=your-repo \
  --branch=main \
  --path=./gitops \
  --personal
```

This will:
- Install Flux controllers in the cluster
- Create the `flux-system` namespace
- Configure Flux to watch this repository
- Commit Flux manifests to `gitops/flux-system/`

### 2. Add a New Application

Create a new application in `apps/base/`:

```bash
# Create application directory
mkdir -p apps/base/my-app

# Add Kubernetes manifests
cat > apps/base/my-app/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  labels:
    app: my-app
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
        image: my-app:v1.0.0
        ports:
        - containerPort: 8080
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
EOF

cat > apps/base/my-app/service.yaml << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: my-app
  labels:
    app: my-app
spec:
  type: ClusterIP
  ports:
  - port: 80
    targetPort: 8080
  selector:
    app: my-app
EOF

# Create kustomization
cat > apps/base/my-app/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml

commonLabels:
  app: my-app
  managed-by: flux

namespace: default
EOF
```

### 3. Commit and Deploy

```bash
git add apps/base/my-app
git commit -m "Add my-app application"
git push
```

Flux will automatically detect the changes and deploy your application within the configured sync interval (default: 1 minute).

### 4. Monitor Deployment

```bash
# Check Flux status
flux get kustomizations

# Watch application pods
kubectl get pods -l app=my-app -w

# View Flux logs
flux logs --all-namespaces --follow
```

### 5. Update Application

To update your application, simply modify the manifests and commit:

```bash
# Update image version
sed -i 's/v1.0.0/v1.1.0/' apps/base/my-app/deployment.yaml

git add apps/base/my-app/deployment.yaml
git commit -m "Update my-app to v1.1.0"
git push
```

Flux will automatically apply the changes.

### 6. Create Environment-Specific Configuration

For production-specific settings:

```bash
mkdir -p apps/overlays/production

cat > apps/overlays/production/my-app-patch.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 5
  template:
    spec:
      containers:
      - name: my-app
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
EOF

cat > apps/overlays/production/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

bases:
  - ../../base/my-app

namespace: production

patchesStrategicMerge:
  - my-app-patch.yaml

commonLabels:
  environment: production
EOF
```

## Managing Secrets

**⚠️ Important:** Never commit unencrypted secrets to Git!

### Option 1: Mozilla SOPS (Recommended)

```bash
# Install SOPS
brew install sops  # macOS
# or download from https://github.com/mozilla/sops/releases

# Create a secret
cat > apps/base/my-app/secret.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: my-app-secret
type: Opaque
stringData:
  api-key: "my-secret-key"
  database-password: "my-db-password"
EOF

# Encrypt the secret
sops --encrypt --in-place apps/base/my-app/secret.yaml

# Configure Flux to decrypt (one-time setup)
kubectl create secret generic sops-gpg \
  --namespace=flux-system \
  --from-file=sops.asc=/path/to/private.key
```

### Option 2: Sealed Secrets

```bash
# Install Sealed Secrets controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Install kubeseal CLI
brew install kubeseal  # macOS

# Seal a secret
kubeseal --format=yaml < secret.yaml > sealed-secret.yaml

# Commit the sealed secret
git add sealed-secret.yaml
git commit -m "Add sealed secret"
git push
```

## Flux Commands Reference

### Status and Information

```bash
# Check Flux installation
flux check

# Get all Flux resources
flux get all

# Get kustomizations
flux get kustomizations

# Get Helm releases
flux get helmreleases

# Get sources
flux get sources git
flux get sources helm
```

### Reconciliation

```bash
# Force immediate reconciliation
flux reconcile source git flux-system
flux reconcile kustomization flux-system

# Reconcile with source update
flux reconcile kustomization flux-system --with-source
```

### Suspend and Resume

```bash
# Suspend reconciliation
flux suspend kustomization my-app

# Resume reconciliation
flux resume kustomization my-app
```

### Logs and Debugging

```bash
# View all Flux logs
flux logs --all-namespaces --follow

# View specific component logs
flux logs --kind=Kustomization --name=flux-system --namespace=flux-system

# View Helm release logs
flux logs --kind=HelmRelease --name=my-release --namespace=my-namespace
```

## Best Practices

### Application Organization

1. **One directory per application**: Each application should have its own directory under `apps/base/`
2. **Use Kustomize**: Leverage Kustomize for environment-specific configurations
3. **Separate concerns**: Keep infrastructure separate from applications
4. **Consistent naming**: Use consistent naming conventions across all resources

### Security

1. **Encrypt secrets**: Always use SOPS or Sealed Secrets for sensitive data
2. **RBAC**: Implement proper RBAC policies
3. **Network policies**: Use network policies to restrict traffic
4. **Image scanning**: Scan container images for vulnerabilities
5. **Least privilege**: Run containers with minimal privileges

### Resource Management

1. **Resource limits**: Always specify CPU and memory limits
2. **Health checks**: Include liveness and readiness probes
3. **Graceful shutdown**: Configure proper termination grace periods
4. **Pod disruption budgets**: Use PDBs for high-availability applications

### Version Control

1. **Semantic versioning**: Use semantic versioning for images
2. **Avoid `latest` tag**: Pin specific image versions
3. **Meaningful commits**: Write clear commit messages
4. **Small changes**: Make small, incremental changes
5. **Review changes**: Use pull requests for code review

### Monitoring and Observability

1. **Monitor Flux**: Watch Flux controller health
2. **Application metrics**: Expose application metrics
3. **Logging**: Implement structured logging
4. **Alerting**: Set up alerts for failures
5. **Dashboards**: Create dashboards for visibility

## Troubleshooting

### Application Not Deploying

```bash
# Check Flux status
flux get kustomizations

# View Flux logs
flux logs --all-namespaces --follow

# Check for errors in kustomization
kubectl describe kustomization flux-system -n flux-system

# Force reconciliation
flux reconcile kustomization flux-system --with-source
```

### Secret Decryption Failing

```bash
# Check SOPS configuration
kubectl get secret sops-gpg -n flux-system

# View decryption errors
flux logs --kind=Kustomization --name=flux-system
```

### Image Pull Errors

```bash
# Check image pull secrets
kubectl get secrets

# Verify image exists
docker pull <image-name>

# Check pod events
kubectl describe pod <pod-name>
```

### Kustomize Build Errors

```bash
# Test kustomize build locally
kustomize build apps/base/my-app

# Check for syntax errors
kubectl apply --dry-run=client -k apps/base/my-app
```

## Examples

This repository includes example applications:

- **nginx**: Full-featured web server with ConfigMap, Secret, Ingress, and production overlay
- **hello-world**: Minimal application example

See the `apps/` directory for complete examples.

## Additional Resources

- [Flux Documentation](https://fluxcd.io/docs/)
- [Kustomize Documentation](https://kustomize.io/)
- [SOPS Documentation](https://github.com/mozilla/sops)
- [Sealed Secrets Documentation](https://github.com/bitnami-labs/sealed-secrets)
- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
