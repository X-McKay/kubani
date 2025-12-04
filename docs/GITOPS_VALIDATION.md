# GitOps Validation and Troubleshooting Guide

This guide helps you validate that Flux and Kustomize are functioning correctly and provides troubleshooting steps for common issues.

## Table of Contents

- [Quick Health Check](#quick-health-check)
- [Detailed Validation](#detailed-validation)
- [Common Issues and Solutions](#common-issues-and-solutions)
- [Troubleshooting Commands](#troubleshooting-commands)
- [Recovery Procedures](#recovery-procedures)
- [Monitoring and Alerts](#monitoring-and-alerts)

## Quick Health Check

Run these commands to quickly verify Flux is operational:

```bash
# Set kubeconfig
export KUBECONFIG=/tmp/homelab-kubeconfig

# Check Flux status (should show all ✔)
flux check

# Verify kustomizations are ready
flux get kustomizations

# Check Git repository sync
flux get sources git
```

**Expected Output:**
```
NAME            REVISION                SUSPENDED       READY   MESSAGE
flux-system     main@sha1:abc1234       False           True    Applied revision: main@sha1:abc1234
```

If you see `READY=True`, Flux is working correctly! ✅

## Detailed Validation

### Step 1: Verify Flux Installation

#### 1.1 Check Flux Controllers

```bash
# All 4 controllers should be running
kubectl get deployments -n flux-system

# Expected output:
# NAME                       READY   UP-TO-DATE   AVAILABLE
# helm-controller            1/1     1            1
# kustomize-controller       1/1     1            1
# notification-controller    1/1     1            1
# source-controller          1/1     1            1
```

#### 1.2 Check Controller Pods

```bash
# All pods should be Running
kubectl get pods -n flux-system

# Check for restarts (should be 0 or low)
kubectl get pods -n flux-system -o wide
```

**Healthy Status:**
- STATUS: `Running`
- READY: `1/1`
- RESTARTS: `0` (or very low number)

#### 1.3 Verify Flux Version

```bash
# Check Flux CLI version
flux version

# Check cluster version
flux version --client=false
```

### Step 2: Validate Git Repository Connection

#### 2.1 Check GitRepository Resource

```bash
# Should show READY=True
flux get sources git

# Detailed information
kubectl get gitrepository -n flux-system flux-system -o yaml
```

#### 2.2 Verify Git Sync

```bash
# Check last sync time and revision
flux get sources git flux-system

# Force a sync to test connectivity
flux reconcile source git flux-system

# Should see: "✔ fetched revision main@sha1:..."
```

#### 2.3 Check Git Credentials

```bash
# Verify secret exists
kubectl get secret -n flux-system flux-system

# Check secret has correct keys
kubectl get secret -n flux-system flux-system -o jsonpath='{.data}' | jq 'keys'
```

### Step 3: Validate Kustomization

#### 3.1 Check Kustomization Status

```bash
# Should show READY=True
flux get kustomizations

# Detailed status
kubectl describe kustomization -n flux-system flux-system
```

#### 3.2 Verify Applied Resources

```bash
# Check what resources Flux has applied
kubectl get kustomization -n flux-system flux-system -o yaml | grep -A 50 "status:"

# List all resources managed by Flux
kubectl get all -A -l kustomize.toolkit.fluxcd.io/name=flux-system
```

#### 3.3 Test Reconciliation

```bash
# Force reconciliation
flux reconcile kustomization flux-system --with-source

# Watch reconciliation progress
watch flux get kustomizations

# Should complete within 1-2 minutes
```

### Step 4: Validate Helm Repository (if using Helm)

```bash
# Check Helm repositories
flux get sources helm

# Should show READY=True for bitnami
# NAME     REVISION         SUSPENDED  READY  MESSAGE
# bitnami  sha256:abc123    False      True   stored artifact
```

### Step 5: End-to-End Test

Deploy a test service to verify the complete GitOps workflow:

```bash
# Create test service
mkdir -p gitops/apps/base/flux-test
cat > gitops/apps/base/flux-test/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flux-test
spec:
  replicas: 1
  selector:
    matchLabels:
      app: flux-test
  template:
    metadata:
      labels:
        app: flux-test
    spec:
      containers:
      - name: test
        image: nginx:alpine
        ports:
        - containerPort: 80
EOF

cat > gitops/apps/base/flux-test/kustomization.yaml << 'EOF'
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
EOF

# Commit and push
git add gitops/apps/base/flux-test/
git commit -m "Test Flux deployment"
git push

# Wait for Flux to sync (max 1 minute)
sleep 65

# Verify deployment
kubectl get deployment flux-test

# Should show: flux-test   1/1     1            1
```

**Cleanup:**
```bash
rm -rf gitops/apps/base/flux-test/
git add -A && git commit -m "Remove test" && git push
```

## Common Issues and Solutions

### Issue 1: Kustomization Not Ready

**Symptoms:**
```
NAME            REVISION    SUSPENDED    READY    MESSAGE
flux-system     main@...    False        False    kustomization path not found
```

**Diagnosis:**
```bash
# Check kustomization logs
kubectl logs -n flux-system deployment/kustomize-controller --tail=50

# Look for error messages
flux get kustomizations flux-system
```

**Solutions:**

1. **Path not found:**
```bash
# Verify path in gotk-sync.yaml
kubectl get kustomization -n flux-system flux-system -o yaml | grep path

# Should be: path: ./gitops
# Fix if incorrect:
kubectl edit kustomization -n flux-system flux-system
```

2. **Invalid Kustomization:**
```bash
# Test kustomization locally
kustomize build gitops/

# Fix any errors in kustomization.yaml files
```

3. **Resource conflicts:**
```bash
# Check for conflicting resources
kubectl get all -A | grep <resource-name>

# Delete conflicting resources
kubectl delete <resource-type> <resource-name>
```

### Issue 2: Git Repository Not Syncing

**Symptoms:**
```
NAME            REVISION    SUSPENDED    READY    MESSAGE
flux-system     Unknown     False        False    failed to checkout and determine revision
```

**Diagnosis:**
```bash
# Check source-controller logs
kubectl logs -n flux-system deployment/source-controller --tail=50

# Check Git repository status
flux get sources git flux-system
```

**Solutions:**

1. **Authentication failure:**
```bash
# Verify secret exists and is valid
kubectl get secret -n flux-system flux-system

# Re-create secret if needed (example for SSH)
flux create secret git flux-system \
  --url=ssh://git@github.com/your-org/your-repo \
  --ssh-key-algorithm=ecdsa \
  --ssh-ecdsa-curve=p521
```

2. **Wrong repository URL:**
```bash
# Check current URL
kubectl get gitrepository -n flux-system flux-system -o yaml | grep url

# Update if incorrect
kubectl edit gitrepository -n flux-system flux-system
```

3. **Branch doesn't exist:**
```bash
# Check branch name
kubectl get gitrepository -n flux-system flux-system -o yaml | grep branch

# Update to correct branch (usually 'main' or 'master')
kubectl edit gitrepository -n flux-system flux-system
```

### Issue 3: Controllers Not Running

**Symptoms:**
```bash
kubectl get pods -n flux-system
# Shows CrashLoopBackOff or ImagePullBackOff
```

**Diagnosis:**
```bash
# Check pod status
kubectl describe pod -n flux-system <pod-name>

# Check logs
kubectl logs -n flux-system <pod-name>
```

**Solutions:**

1. **Image pull issues:**
```bash
# Check if images are accessible
kubectl get pods -n flux-system -o yaml | grep image:

# Verify node can pull images
kubectl run test --image=ghcr.io/fluxcd/source-controller:v1.7.4 --rm -it -- sh
```

2. **Resource constraints:**
```bash
# Check node resources
kubectl top nodes

# Check if pods are pending due to resources
kubectl describe pod -n flux-system <pod-name> | grep -A 5 Events
```

3. **Reinstall Flux:**
```bash
# Uninstall
flux uninstall --silent

# Reinstall
flux bootstrap git \
  --url=ssh://git@github.com/your-org/your-repo \
  --branch=main \
  --path=./gitops
```

### Issue 4: Resources Not Being Applied

**Symptoms:**
- Flux shows READY=True but resources aren't created
- Changes in Git not reflected in cluster

**Diagnosis:**
```bash
# Check what Flux thinks it applied
kubectl logs -n flux-system deployment/kustomize-controller --tail=100 | grep "server-side apply"

# Check for prune issues
flux get kustomizations flux-system
```

**Solutions:**

1. **Namespace issues:**
```bash
# Verify namespace exists
kubectl get namespaces

# Create if missing
kubectl create namespace <namespace-name>
```

2. **RBAC permissions:**
```bash
# Check Flux service account permissions
kubectl get clusterrolebinding | grep flux

# Verify permissions
kubectl auth can-i create deployments --as=system:serviceaccount:flux-system:kustomize-controller
```

3. **Force reconciliation:**
```bash
# Force Flux to reapply everything
flux reconcile kustomization flux-system --with-source

# Suspend and resume
flux suspend kustomization flux-system
flux resume kustomization flux-system
```

### Issue 5: Slow Reconciliation

**Symptoms:**
- Changes take longer than 1 minute to apply
- Flux seems stuck

**Diagnosis:**
```bash
# Check reconciliation interval
kubectl get kustomization -n flux-system flux-system -o yaml | grep interval

# Check for rate limiting
kubectl logs -n flux-system deployment/source-controller --tail=50 | grep -i rate
```

**Solutions:**

1. **Adjust interval:**
```bash
# Edit kustomization
kubectl edit kustomization -n flux-system flux-system

# Change interval to 30s or 1m
spec:
  interval: 30s
```

2. **Force immediate sync:**
```bash
# Reconcile immediately
flux reconcile kustomization flux-system --with-source
```

## Troubleshooting Commands

### Essential Commands

```bash
# Complete Flux status
flux check

# All Flux resources
flux get all

# Kustomization status
flux get kustomizations

# Git repository status
flux get sources git

# Helm repository status
flux get sources helm

# Force reconciliation
flux reconcile kustomization flux-system --with-source

# Suspend reconciliation (for maintenance)
flux suspend kustomization flux-system

# Resume reconciliation
flux resume kustomization flux-system
```

### Log Analysis

```bash
# Kustomize controller logs (most important)
kubectl logs -n flux-system deployment/kustomize-controller --tail=100 -f

# Source controller logs (Git sync issues)
kubectl logs -n flux-system deployment/source-controller --tail=100 -f

# Helm controller logs (Helm chart issues)
kubectl logs -n flux-system deployment/helm-controller --tail=100 -f

# Notification controller logs
kubectl logs -n flux-system deployment/notification-controller --tail=100 -f

# All Flux logs
kubectl logs -n flux-system -l app.kubernetes.io/part-of=flux --tail=50

# Search for errors
kubectl logs -n flux-system deployment/kustomize-controller --tail=500 | grep -i error

# Search for specific resource
kubectl logs -n flux-system deployment/kustomize-controller --tail=500 | grep "my-service"
```

### Resource Inspection

```bash
# List all Flux CRDs
kubectl get crds | grep fluxcd

# Describe kustomization
kubectl describe kustomization -n flux-system flux-system

# Describe git repository
kubectl describe gitrepository -n flux-system flux-system

# View kustomization YAML
kubectl get kustomization -n flux-system flux-system -o yaml

# Check applied resources
kubectl get kustomization -n flux-system flux-system -o jsonpath='{.status.inventory}' | jq
```

### Network and Connectivity

```bash
# Test Git connectivity from cluster
kubectl run test-git --rm -it --image=alpine/git -- sh
# Inside pod:
git ls-remote https://github.com/your-org/your-repo

# Test DNS resolution
kubectl run test-dns --rm -it --image=busybox -- nslookup github.com

# Check network policies
kubectl get networkpolicies -n flux-system
```

### Performance Analysis

```bash
# Check controller resource usage
kubectl top pods -n flux-system

# Check reconciliation duration
kubectl get kustomization -n flux-system flux-system -o yaml | grep -A 5 "lastAppliedRevision"

# Count managed resources
kubectl get all -A -l kustomize.toolkit.fluxcd.io/name=flux-system | wc -l
```

## Recovery Procedures

### Procedure 1: Reset Flux State

If Flux is in a bad state:

```bash
# 1. Suspend reconciliation
flux suspend kustomization flux-system

# 2. Delete kustomization (will be recreated)
kubectl delete kustomization -n flux-system flux-system

# 3. Recreate from Git
flux reconcile source git flux-system

# 4. Resume
flux resume kustomization flux-system
```

### Procedure 2: Force Full Reconciliation

```bash
# 1. Delete all managed resources
kubectl delete kustomization -n flux-system flux-system

# 2. Wait for recreation
sleep 10

# 3. Force sync
flux reconcile kustomization flux-system --with-source

# 4. Verify
flux get kustomizations
```

### Procedure 3: Reinstall Flux

Complete reinstall (last resort):

```bash
# 1. Export current configuration
kubectl get gitrepository -n flux-system flux-system -o yaml > flux-git-backup.yaml
kubectl get kustomization -n flux-system flux-system -o yaml > flux-kustomization-backup.yaml

# 2. Uninstall Flux
flux uninstall --silent

# 3. Verify removal
kubectl get namespaces | grep flux-system

# 4. Reinstall
flux bootstrap git \
  --url=ssh://git@github.com/your-org/your-repo \
  --branch=main \
  --path=./gitops \
  --private-key-file=~/.ssh/id_rsa

# 5. Verify installation
flux check
flux get all
```

### Procedure 4: Clean Up Failed Resources

```bash
# Find stuck resources
kubectl get all -A | grep -E "Error|CrashLoop|ImagePull"

# Delete stuck resources
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0

# Clean up finalizers if stuck
kubectl patch <resource-type> <resource-name> -p '{"metadata":{"finalizers":[]}}' --type=merge
```

## Monitoring and Alerts

### Health Check Script

Create a monitoring script:

```bash
cat > scripts/check_flux_health.sh << 'EOF'
#!/bin/bash

export KUBECONFIG=/tmp/homelab-kubeconfig

echo "=== Flux Health Check ==="
echo

# Check controllers
echo "1. Controller Status:"
kubectl get deployments -n flux-system | grep -E "NAME|controller"
echo

# Check kustomizations
echo "2. Kustomization Status:"
flux get kustomizations
echo

# Check Git sync
echo "3. Git Repository Status:"
flux get sources git
echo

# Check for errors in logs
echo "4. Recent Errors:"
kubectl logs -n flux-system deployment/kustomize-controller --tail=50 | grep -i error | tail -5
echo

# Summary
if flux get kustomizations | grep -q "True"; then
    echo "✅ Flux is healthy"
    exit 0
else
    echo "❌ Flux has issues"
    exit 1
fi
EOF

chmod +x scripts/check_flux_health.sh
```

Run it:
```bash
./scripts/check_flux_health.sh
```

### Continuous Monitoring

```bash
# Watch Flux status
watch -n 10 flux get kustomizations

# Monitor logs continuously
kubectl logs -n flux-system deployment/kustomize-controller -f

# Monitor all Flux pods
kubectl get pods -n flux-system -w
```

### Metrics and Dashboards

```bash
# Check Flux metrics (if Prometheus installed)
kubectl port-forward -n flux-system svc/source-controller 8080:80
curl http://localhost:8080/metrics

# Key metrics to monitor:
# - gotk_reconcile_duration_seconds
# - gotk_reconcile_condition
# - gotk_suspend_status
```

## Validation Checklist

Use this checklist to verify Flux is fully operational:

- [ ] All 4 Flux controllers are running
- [ ] No pods in CrashLoopBackOff or Error state
- [ ] GitRepository shows READY=True
- [ ] Kustomization shows READY=True
- [ ] `flux check` passes (ignore k8s version warning)
- [ ] Test deployment succeeds within 1 minute
- [ ] Logs show no errors
- [ ] Resources are being applied correctly
- [ ] Changes in Git are reflected in cluster
- [ ] Reconciliation completes in < 2 minutes

## Quick Reference

```bash
# Health check
flux check && flux get kustomizations

# Force sync
flux reconcile kustomization flux-system --with-source

# View logs
kubectl logs -n flux-system deployment/kustomize-controller --tail=100

# Restart controllers
kubectl rollout restart deployment -n flux-system

# Complete status
flux get all

# Test deployment
git add . && git commit -m "test" && git push && sleep 65 && kubectl get pods
```

## Related Documentation

- [Service Deployment Guide](./GITOPS_SERVICE_DEPLOYMENT.md) - Deploy services via GitOps
- [Troubleshooting Guide](./TROUBLESHOOTING.md) - General cluster issues
- [Architecture Overview](./ARCHITECTURE.md) - System design

## Additional Resources

- [Flux Documentation](https://fluxcd.io/docs/)
- [Flux Troubleshooting](https://fluxcd.io/docs/troubleshooting/)
- [Kustomize Documentation](https://kustomize.io/)

## Support

If issues persist after following this guide:
1. Check Flux logs for specific error messages
2. Verify Git repository is accessible
3. Ensure cluster has sufficient resources
4. Review [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for cluster-level issues
5. Consider reinstalling Flux as last resort
