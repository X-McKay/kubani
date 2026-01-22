# Nginx Example Application

This is a simple example application that demonstrates GitOps deployment with Flux CD.

## What's Included

- **Deployment**: 2 replicas of nginx:1.25-alpine
- **Service**: ClusterIP service exposing port 80
- **Resource Limits**: CPU and memory limits configured
- **Health Checks**: Liveness and readiness probes

## Deployment

This application is automatically deployed by Flux CD when committed to the Git repository.

### Manual Deployment (for testing)

```bash
kubectl apply -k gitops/apps/base/nginx-example/
```

### Verify Deployment

```bash
# Check pods
kubectl get pods -l app=nginx-example

# Check service
kubectl get svc nginx-example

# Test the service
kubectl port-forward svc/nginx-example 8080:80
curl http://localhost:8080
```

## Customization

To customize this application for different environments, create overlays:

```bash
mkdir -p gitops/apps/overlays/production/nginx-example
```

Create `gitops/apps/overlays/production/nginx-example/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: production
resources:
  - ../../../base/nginx-example
replicas:
  - name: nginx-example
    count: 3
```

## Scaling

To scale the deployment, modify the `replicas` field in `deployment.yaml` and commit:

```yaml
spec:
  replicas: 3  # Change from 2 to 3
```

Flux will automatically apply the change within 1 minute (default sync interval).

## Removal

To remove this application, delete the directory and commit:

```bash
git rm -r gitops/apps/base/nginx-example/
git commit -m "Remove nginx-example application"
git push
```

Flux will automatically remove the resources from the cluster.
