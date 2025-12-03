# Kubani Quick Start Guide

This guide will walk you through setting up your first Kubernetes cluster with Kubani in about 15 minutes.

## What You'll Build

By the end of this guide, you'll have:
- A multi-node Kubernetes cluster running K3s
- Nodes communicating securely over Tailscale VPN
- GitOps-based application deployment with Flux CD
- CLI and TUI tools for cluster management
- A sample application deployed via GitOps

## Two Ways to Get Started

### Option 1: Automated Setup (Recommended)

Use our interactive quickstart script for guided setup:

```bash
# Clone the repository
git clone <your-repo-url>
cd kubani

# Run the quickstart script
./scripts/quickstart.sh
```

The script will:
- Check prerequisites
- Discover Tailscale nodes
- Generate inventory configuration
- Test SSH connectivity
- Provision the cluster
- Verify installation

**Time:** ~10-15 minutes (mostly automated)

### Option 2: Manual Setup

Follow the detailed steps below for full control over the setup process.

**Time:** ~15-20 minutes

---

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] **Management machine** with Linux, macOS, or WSL2
- [ ] **2+ machines** for cluster nodes (can be VMs, physical servers, or workstations)
- [ ] **Tailscale** installed and authenticated on all machines
- [ ] **SSH access** to all cluster nodes with sudo privileges
- [ ] **Git repository** for GitOps (GitHub, GitLab, etc.)
- [ ] **Internet connection** on all machines

### Minimum Hardware

- **Control Plane**: 2 CPU cores, 2GB RAM, 20GB disk
- **Worker Nodes**: 2 CPU cores, 2GB RAM, 20GB disk
- **Recommended**: 4 CPU cores, 8GB RAM, 40GB disk per node

## Step 1: Install Mise and Clone Repository

On your management machine:

```bash
# Install mise
curl https://mise.run | sh

# Add mise to your shell
echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
source ~/.bashrc

# Clone the repository
git clone <your-repo-url>
cd kubani

# Install tools and dependencies
chmod +x setup.sh
./setup.sh
```

**What this does:**
- Installs mise (runtime manager)
- Installs Python, UV, kubectl, and other tools
- Installs Python dependencies for cluster management

**Verify installation:**
```bash
mise --version
python --version
kubectl version --client
cluster-mgr version
```

## Step 2: Set Up Tailscale

On each cluster node:

```bash
# Install Tailscale (Ubuntu/Debian)
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate with Tailscale
sudo tailscale up

# Verify connection
tailscale status
```

**From your management machine, discover nodes:**

```bash
cluster-mgr discover
```

You should see output like:
```
┌─────────────────────────────────────────────────────────┐
│              Discovered Tailscale Nodes                 │
├──────────────┬─────────────────┬──────────┬────────────┤
│ Hostname     │ Tailscale IP    │ Status   │ In Cluster │
├──────────────┼─────────────────┼──────────┼────────────┤
│ control-1    │ 100.64.0.5      │ ✓ Online │ No         │
│ worker-1     │ 100.64.0.10     │ ✓ Online │ No         │
│ worker-2     │ 100.64.0.11     │ ✓ Online │ No         │
└──────────────┴─────────────────┴──────────┴────────────┘
```

**Note the Tailscale IPs** - you'll need them for the inventory.

## Step 3: Configure Your Cluster

Create your inventory file:

```bash
cp ansible/inventory/hosts.yml.example ansible/inventory/hosts.yml
```

Edit `ansible/inventory/hosts.yml` with your node information:

```yaml
all:
  vars:
    k3s_version: v1.28.5+k3s1
    cluster_name: my-homelab
    tailscale_network: 100.64.0.0/10

    # GitOps configuration
    git_repo_url: https://github.com/yourusername/kubani.git
    git_branch: main
    flux_namespace: flux-system

  children:
    control_plane:
      hosts:
        control-1:
          ansible_host: 100.64.0.5
          tailscale_ip: 100.64.0.5
          node_labels:
            node-role: control-plane

    workers:
      hosts:
        worker-1:
          ansible_host: 100.64.0.10
          tailscale_ip: 100.64.0.10
          reserved_cpu: "1"
          reserved_memory: "2Gi"
          node_labels:
            node-role: worker

        worker-2:
          ansible_host: 100.64.0.11
          tailscale_ip: 100.64.0.11
          reserved_cpu: "1"
          reserved_memory: "2Gi"
          node_labels:
            node-role: worker
```

**Key configuration points:**
- Replace Tailscale IPs with your actual node IPs
- Set `cluster_name` to your desired name
- Update `git_repo_url` to your Git repository
- Adjust `reserved_cpu` and `reserved_memory` based on your needs

**Optional: Configure group variables**

```bash
cp ansible/inventory/group_vars/all.yml.example ansible/inventory/group_vars/all.yml
vim ansible/inventory/group_vars/all.yml
```

## Step 4: Test SSH Connectivity

Before provisioning, verify SSH access:

```bash
# Test SSH to each node
ssh user@100.64.0.5 "echo 'Control plane OK'"
ssh user@100.64.0.10 "echo 'Worker 1 OK'"
ssh user@100.64.0.11 "echo 'Worker 2 OK'"

# Or use Ansible to test
ansible all -i ansible/inventory/hosts.yml -m ping
```

**If SSH fails:**
- Ensure SSH keys are set up: `ssh-copy-id user@<tailscale-ip>`
- Or configure password authentication in `ansible.cfg`

## Step 5: Provision the Cluster

Run the provisioning playbook:

```bash
# Dry-run first (recommended)
cluster-mgr provision --check

# Actual provisioning
cluster-mgr provision
```

**What happens during provisioning:**

1. **Prerequisites** (2-3 min)
   - Validates Tailscale connectivity
   - Installs system dependencies
   - Configures firewall rules

2. **Control Plane Setup** (3-4 min)
   - Installs K3s server
   - Configures API server with Tailscale IP
   - Generates kubeconfig and join token

3. **Worker Setup** (2-3 min per worker)
   - Installs K3s agent
   - Joins cluster using control plane Tailscale IP
   - Applies resource reservations and labels

4. **GitOps Setup** (1-2 min)
   - Installs Flux CD
   - Bootstraps Flux to Git repository
   - Configures automatic synchronization

**Expected output:**
```
PLAY RECAP *********************************************************
control-1    : ok=45   changed=12   unreachable=0    failed=0
worker-1     : ok=38   changed=10   unreachable=0    failed=0
worker-2     : ok=38   changed=10   unreachable=0    failed=0

✓ Playbook execution completed successfully
```

**Total time:** 5-10 minutes depending on node count and network speed.

## Step 6: Verify Cluster

Check cluster status:

```bash
# Using cluster-mgr
cluster-mgr status

# Using kubectl directly
export KUBECONFIG=~/.kube/config
kubectl get nodes
kubectl get pods -A
```

**Expected output:**
```
NAME        STATUS   ROLES                  AGE   VERSION
control-1   Ready    control-plane,master   5m    v1.28.5+k3s1
worker-1    Ready    <none>                 4m    v1.28.5+k3s1
worker-2    Ready    <none>                 4m    v1.28.5+k3s1
```

All nodes should show `Ready` status.

**Verify Flux is running:**
```bash
kubectl get pods -n flux-system
```

You should see Flux controllers running:
```
NAME                                       READY   STATUS    RESTARTS   AGE
source-controller-xxx                      1/1     Running   0          3m
kustomize-controller-xxx                   1/1     Running   0          3m
helm-controller-xxx                        1/1     Running   0          3m
notification-controller-xxx                1/1     Running   0          3m
```

## Step 7: Deploy Your First Application

Create a simple nginx deployment via GitOps:

```bash
# Create application directory
mkdir -p gitops/apps/base/hello-world

# Create deployment manifest
cat > gitops/apps/base/hello-world/deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hello-world
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hello-world
  template:
    metadata:
      labels:
        app: hello-world
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
EOF

# Create service manifest
cat > gitops/apps/base/hello-world/service.yaml <<EOF
apiVersion: v1
kind: Service
metadata:
  name: hello-world
  namespace: default
spec:
  selector:
    app: hello-world
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
EOF

# Create kustomization
cat > gitops/apps/base/hello-world/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - deployment.yaml
  - service.yaml
EOF

# Commit and push
git add gitops/apps/base/hello-world/
git commit -m "Add hello-world application"
git push
```

**Watch the deployment:**

```bash
# Flux will sync within 1 minute (default interval)
# Watch for pods to be created
kubectl get pods -w

# Or force immediate sync
flux reconcile source git flux-system
flux reconcile kustomization flux-system
```

**Verify deployment:**
```bash
kubectl get deployments
kubectl get pods
kubectl get services
```

**Test the application:**
```bash
# Port-forward to access the service
kubectl port-forward service/hello-world 8080:80

# In another terminal or browser
curl http://localhost:8080
```

## Step 8: Monitor Your Cluster

Launch the TUI for real-time monitoring:

```bash
cluster-tui
```

**TUI Features:**
- Real-time node status and resource usage
- Service health monitoring
- Pod information
- Cluster events

**Keyboard shortcuts:**
- `q` - Quit
- `r` - Refresh
- `↑/↓` - Navigate
- `Enter` - View details

## Next Steps

Now that your cluster is running, you can:

### Add More Nodes

```bash
# Discover new nodes
cluster-mgr discover

# Add a new worker
cluster-mgr add-node worker-3 100.64.0.12 --role worker

# Provision the new node
cluster-mgr provision --limit worker-3
```

### Deploy More Applications

```bash
# Create new application directories in gitops/apps/base/
# Commit and push - Flux will automatically deploy
```

### Configure GPU Support

If you have nodes with NVIDIA GPUs:

```bash
# Add GPU configuration to inventory
cluster-mgr add-node gpu-node 100.64.0.20 \
  --role worker \
  --gpu \
  --reserved-cpu 4 \
  --reserved-memory 8Gi \
  --taints "nvidia.com/gpu=true:NoSchedule"

# Provision with GPU support
cluster-mgr provision --tags gpu
```

### Set Up Monitoring

Add Prometheus and Grafana for cluster monitoring:

```bash
# Enable monitoring in group_vars
cluster-mgr config-set monitoring_enabled true --type bool

# Add monitoring manifests to gitops/infrastructure/monitoring/
# Commit and push
```

### Explore Advanced Features

- **High Availability**: Add multiple control plane nodes
- **Custom Storage**: Configure NFS, Ceph, or other storage providers
- **Network Policies**: Implement pod-to-pod communication restrictions
- **Ingress**: Set up Traefik ingress for external access
- **Secrets Management**: Use SOPS or sealed-secrets for encrypted secrets

## Troubleshooting

### Nodes Not Joining

```bash
# Check control plane is accessible
curl -k https://<control-plane-tailscale-ip>:6443

# View worker logs
ssh user@<worker-ip>
sudo journalctl -u k3s-agent -f
```

### Flux Not Syncing

```bash
# Check Flux status
flux check

# View Flux logs
kubectl logs -n flux-system -l app=source-controller
kubectl logs -n flux-system -l app=kustomize-controller

# Force reconciliation
flux reconcile source git flux-system
```

### SSH Connection Issues

```bash
# Test SSH manually
ssh -v user@<tailscale-ip>

# Copy SSH key
ssh-copy-id user@<tailscale-ip>
```

For more troubleshooting tips, see the [main README](README.md#troubleshooting).

## Getting Help

- **Documentation**: See [README.md](README.md) for detailed documentation
- **Architecture**: Review [design.md](.kiro/specs/tailscale-k8s-cluster/design.md)
- **Issues**: Check logs and error messages
- **Community**: Open an issue on GitHub

## Summary

Congratulations! You now have:
- ✅ A working Kubernetes cluster
- ✅ Secure communication over Tailscale
- ✅ GitOps-based deployment workflow
- ✅ Management tools (CLI and TUI)
- ✅ A sample application running

Your cluster is ready for production workloads. Happy clustering! 🚀
