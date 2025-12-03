# Kubani - Kubernetes Cluster Automation for Tailscale Networks

Kubani is an infrastructure automation solution that provisions and manages multi-node Kubernetes clusters across heterogeneous hardware connected via Tailscale VPN. It enables you to build a production-ready Kubernetes cluster using your existing workstations, servers, and edge devices without complex networking setup.

## Features

- **Automated Provisioning**: Ansible-based automation for K3s cluster deployment
- **Tailscale Integration**: Secure mesh networking across different physical locations without port forwarding
- **GitOps Ready**: Built-in Flux CD integration for declarative application management
- **Workstation-Friendly**: Nodes can function as standalone workstations while participating in the cluster
- **GPU Support**: NVIDIA device plugin integration for GPU workloads with time-slicing
- **Management Tools**: CLI and TUI for cluster administration and real-time monitoring
- **Idempotent Operations**: Safe to re-run playbooks for updates and configuration changes
- **Property-Based Testing**: Comprehensive test suite with Hypothesis for correctness guarantees

## Prerequisites

### Required on Management Machine

- **[Mise](https://mise.jdx.dev/)** - Runtime and tool version manager
  ```bash
  curl https://mise.run | sh
  ```
- **Git** - For cloning the repository
- **SSH access** - To all cluster nodes with sudo privileges

### Required on All Cluster Nodes

- **[Tailscale](https://tailscale.com/)** - Installed and authenticated
  ```bash
  # Install Tailscale (Ubuntu/Debian)
  curl -fsSL https://tailscale.com/install.sh | sh

  # Authenticate
  sudo tailscale up
  ```
- **Operating System**: Ubuntu 20.04+ or Debian 11+ (other Linux distributions may work but are untested)
- **SSH Server**: OpenSSH server running and accessible
- **Sudo Access**: User account with passwordless sudo (or configure Ansible to prompt for password)

### Optional

- **GPU Nodes**: NVIDIA GPU with compatible drivers (will be installed by playbook if needed)
- **kubectl**: For manual cluster management (automatically installed via mise)

### Hardware Requirements

**Minimum per node:**
- 2 CPU cores (1 for Kubernetes, 1+ for workstation use)
- 2GB RAM (more recommended for workstation nodes)
- 20GB disk space

**Recommended for control plane:**
- 2+ CPU cores
- 4GB+ RAM
- 40GB+ disk space

**Recommended for worker nodes:**
- 4+ CPU cores (especially for workstation nodes)
- 8GB+ RAM
- 50GB+ disk space

Note: UV (Python package manager), Python, and kubectl are automatically installed via mise.

## Quick Start

This guide will get you from zero to a running Kubernetes cluster in about 15 minutes.

### 1. Install Development Tools

```bash
# Install mise (if not already installed)
curl https://mise.run | sh

# Add mise to your shell (follow the instructions from the install script)
# For bash: echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
# For zsh: echo 'eval "$(~/.local/bin/mise activate zsh)"' >> ~/.zshrc

# Clone the repository
git clone <repository-url>
cd kubani

# Run the setup script (installs all tools and dependencies)
chmod +x setup.sh
./setup.sh

# Or manually:
mise install          # Installs Python, UV, kubectl
mise run install      # Installs Python dependencies
```

### 2. Verify Tailscale Setup

Ensure all your nodes are connected to Tailscale:

```bash
# On each node, verify Tailscale is running
tailscale status

# Discover available nodes from your management machine
cluster-mgr discover
```

You should see all your nodes listed with their Tailscale IP addresses.

### 3. Configure Your Cluster

Create your inventory file from the example:

```bash
cp ansible/inventory/hosts.yml.example ansible/inventory/hosts.yml
vim ansible/inventory/hosts.yml
```

**Minimum configuration required:**
- Set `cluster_name` to your desired cluster name
- Add at least one control plane node with its Tailscale IP
- Add worker nodes with their Tailscale IPs
- Configure `git_repo_url` for GitOps (or disable GitOps in group_vars)

See [Inventory Configuration](#inventory-configuration) for detailed options.

### 4. Provision the Cluster

```bash
# Using the CLI (recommended)
cluster-mgr provision

# Or using Ansible directly
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/site.yml

# Or using mise task
mise run provision
```

The provisioning process will:
1. Validate Tailscale connectivity on all nodes
2. Install system dependencies
3. Install K3s on control plane and worker nodes
4. Configure networking to use Tailscale IPs
5. Set up GitOps with Flux CD (if enabled)
6. Apply node-specific configurations (GPU support, resource reservations, etc.)

**Expected duration:** 5-10 minutes depending on node count and network speed.

### 5. Verify Cluster Status

```bash
# Check cluster status
cluster-mgr status

# Or use kubectl directly
export KUBECONFIG=~/.kube/config
kubectl get nodes
kubectl get pods -A
```

All nodes should show as "Ready" status.

### 6. Monitor Your Cluster

```bash
# Launch the TUI for real-time monitoring
cluster-tui

# Or using mise task
mise run tui
```

The TUI provides:
- Real-time node status and resource usage
- Service health monitoring
- Pod information
- Cluster events

**Keyboard shortcuts:**
- `q` - Quit
- `r` - Refresh
- `↑/↓` - Navigate
- `Enter` - View details

### 7. Deploy Your First Application

```bash
# Create an application manifest in the GitOps repository
mkdir -p gitops/apps/base/my-app
cat > gitops/apps/base/my-app/deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80
EOF

# Commit and push (Flux will automatically deploy)
git add gitops/apps/base/my-app/
git commit -m "Add my-app deployment"
git push

# Watch the deployment
kubectl get pods -w
```

Flux will detect the changes and deploy your application within 1 minute (default sync interval).

## Project Structure

```
.
├── ansible/                    # Ansible automation
│   ├── inventory/             # Inventory and variables
│   ├── playbooks/             # Provisioning playbooks
│   └── roles/                 # Ansible roles
├── cluster_manager/           # Python management tools
│   ├── cli/                   # CLI commands
│   ├── tui/                   # Terminal UI
│   └── models/                # Data models
├── gitops/                    # GitOps manifests
│   ├── flux-system/          # Flux controllers
│   ├── infrastructure/       # Infrastructure components
│   └── apps/                 # Applications
└── tests/                     # Test suite
    ├── unit/                 # Unit tests
    ├── properties/           # Property-based tests
    └── integration/          # Integration tests
```

## CLI Usage

The `cluster-mgr` CLI provides commands for managing your Kubernetes cluster.

### Node Discovery

Discover nodes on your Tailscale network:

```bash
# Discover all Tailscale nodes
cluster-mgr discover

# Show only online nodes
cluster-mgr discover --online-only

# Filter by hostname pattern
cluster-mgr discover --filter "gpu-*"

# Hide cluster membership status
cluster-mgr discover --no-cluster-status
```

### Node Management

Add nodes to your cluster:

```bash
# Add a basic worker node
cluster-mgr add-node my-node 100.64.0.10 --role worker

# Add a control plane node
cluster-mgr add-node control-1 100.64.0.5 --role control-plane

# Add a GPU worker with resource reservations
cluster-mgr add-node gpu-node 100.64.0.20 \
  --role worker \
  --gpu \
  --reserved-cpu 4 \
  --reserved-memory 8Gi \
  --labels "gpu=true,workstation=true" \
  --taints "nvidia.com/gpu=true:NoSchedule"

# Add node with custom labels
cluster-mgr add-node web-1 100.64.0.15 \
  --role worker \
  --labels "tier=frontend,env=production"
```

Remove nodes from your cluster:

```bash
# Remove a node (with drain)
cluster-mgr remove-node my-node

# Remove without draining
cluster-mgr remove-node my-node --no-drain

# Force removal without confirmation
cluster-mgr remove-node my-node --force
```

### Configuration Management

Get and set configuration values:

```bash
# Get a configuration value
cluster-mgr config-get k3s_version
cluster-mgr config-get cluster_name --scope all

# Set configuration values
cluster-mgr config-set k3s_version v1.28.5+k3s1
cluster-mgr config-set cluster_name my-cluster --scope all

# Set typed values
cluster-mgr config-set monitoring_enabled true --type bool
cluster-mgr config-set worker_count 5 --type int

# Set nested configuration
cluster-mgr config-set flux.namespace flux-system --scope all

# Set JSON configuration
cluster-mgr config-set node_labels '{"env":"prod","tier":"backend"}' --type json
```

### Cluster Operations

Provision and manage your cluster:

```bash
# Provision the entire cluster
cluster-mgr provision

# Run in check mode (dry-run)
cluster-mgr provision --check

# Run specific playbook
cluster-mgr provision --playbook add_node.yml

# Run with tags (only specific tasks)
cluster-mgr provision --tags "k3s,networking"

# Skip specific tags
cluster-mgr provision --skip-tags "gpu,monitoring"

# Limit to specific hosts
cluster-mgr provision --limit "gpu-node"

# Run with extra variables
cluster-mgr provision --extra-vars '{"k3s_version":"v1.28.5+k3s1"}'

# Increase verbosity
cluster-mgr provision -v    # verbose
cluster-mgr provision -vv   # more verbose
cluster-mgr provision -vvv  # debug level
```

### Cluster Status

Check cluster health and status:

```bash
# Basic cluster status
cluster-mgr status

# Show pod information
cluster-mgr status --pods

# Show pods in specific namespace
cluster-mgr status --pods --namespace kube-system

# Use custom inventory
cluster-mgr status --inventory path/to/hosts.yml
```

### Version Information

```bash
# Show version
cluster-mgr version
```

## Development

### Running Tests

```bash
# All tests
mise run test

# Unit tests only
mise run test-unit

# Property-based tests only
mise run test-properties

# With coverage
pytest --cov=cluster_manager --cov-report=html
```

### Code Quality

```bash
# Lint code
mise run lint

# Format code
mise run format

# Type checking
mise run type-check
```

## Inventory Configuration

The Ansible inventory defines your cluster topology. Here's a detailed explanation of configuration options:

### Basic Structure

```yaml
all:
  vars:
    # Global variables for all nodes
    k3s_version: v1.28.5+k3s1
    cluster_name: homelab
    tailscale_network: 100.64.0.0/10

  children:
    control_plane:
      hosts:
        # Control plane nodes

    workers:
      hosts:
        # Worker nodes
```

### Node Configuration Options

**Required fields:**
- `ansible_host`: Tailscale IP address for SSH connection
- `tailscale_ip`: Tailscale IP address for Kubernetes networking

**Optional fields:**
- `reserved_cpu`: CPU cores to reserve for local processes (e.g., "2", "4")
- `reserved_memory`: Memory to reserve for local processes (e.g., "4Gi", "8Gi")
- `gpu`: Set to `true` for nodes with NVIDIA GPUs
- `node_labels`: Dictionary of Kubernetes labels to apply
- `node_taints`: List of taints to apply (prevents pod scheduling)

### Example Configurations

**Basic worker node:**
```yaml
simple-worker:
  ansible_host: 100.64.0.10
  tailscale_ip: 100.64.0.10
```

**Workstation node (reserves resources for local use):**
```yaml
desktop:
  ansible_host: 100.64.0.20
  tailscale_ip: 100.64.0.20
  reserved_cpu: "2"
  reserved_memory: "4Gi"
  node_labels:
    workstation: "true"
    node-role: worker
```

**GPU node:**
```yaml
gpu-server:
  ansible_host: 100.64.0.30
  tailscale_ip: 100.64.0.30
  reserved_cpu: "4"
  reserved_memory: "8Gi"
  gpu: true
  node_labels:
    gpu: "true"
    gpu-type: "nvidia"
  node_taints:
    - key: nvidia.com/gpu
      value: "true"
      effect: NoSchedule
```

**Control plane node:**
```yaml
control-1:
  ansible_host: 100.64.0.5
  tailscale_ip: 100.64.0.5
  node_labels:
    node-role: control-plane
```

### Global Variables

Configure these in `ansible/inventory/group_vars/all.yml`:

- `k3s_version`: K3s version to install (e.g., "v1.28.5+k3s1")
- `cluster_name`: Name of your cluster
- `cluster_domain`: Kubernetes cluster domain (default: "cluster.local")
- `cluster_cidr`: Pod network CIDR (default: "10.42.0.0/16")
- `service_cidr`: Service network CIDR (default: "10.43.0.0/16")
- `tailscale_network`: Tailscale network CIDR (default: "100.64.0.0/10")
- `gitops_enabled`: Enable Flux CD GitOps (default: true)
- `git_repo_url`: Git repository URL for GitOps
- `git_branch`: Git branch to monitor (default: "main")
- `flux_namespace`: Namespace for Flux controllers (default: "flux-system")

## Architecture

Kubani uses K3s (lightweight Kubernetes) with Tailscale for networking. All cluster communication occurs over Tailscale IPs, enabling secure operation across different physical locations without port forwarding or VPN server setup.

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Repository                          │
│  ├── ansible/          (Infrastructure as Code)             │
│  ├── gitops/           (Application Manifests)              │
│  └── cluster_manager/  (Management Tools)                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Management Workstation                          │
│  ├── cluster-mgr CLI   (Node & config management)           │
│  ├── cluster-tui       (Real-time monitoring)               │
│  └── Ansible           (Automation engine)                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Tailscale Network   │
              │   (Mesh VPN Layer)    │
              └───────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Control Plane│  │    Worker    │  │  GPU Worker  │
│              │  │              │  │              │
│ K3s Server   │  │ K3s Agent    │  │ K3s Agent    │
│ + Flux CD    │  │ + Workloads  │  │ + GPU Plugin │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Key Components

- **Ansible**: Infrastructure automation and node provisioning
- **K3s**: Lightweight Kubernetes distribution (single binary, low resource usage)
- **Tailscale**: Mesh VPN for secure node communication (automatic NAT traversal)
- **Flux CD**: GitOps controller for application deployment
- **Typer**: CLI framework for cluster management
- **Textual**: Terminal UI framework for real-time monitoring
- **containerd**: Container runtime (included with K3s)
- **Flannel**: CNI plugin for pod networking (included with K3s)

### Network Flow

1. **Management → Nodes**: Ansible connects via SSH over Tailscale IPs
2. **Node → Node**: Kubernetes API and pod traffic over Tailscale IPs
3. **Flux → Git**: GitOps controller pulls manifests from Git repository
4. **TUI → Cluster**: Real-time monitoring via Kubernetes API

### Security Model

- **Tailscale**: Encrypted mesh network (WireGuard protocol)
- **Kubernetes RBAC**: Role-based access control for cluster resources
- **Network Policies**: Pod-to-pod communication restrictions (optional)
- **Ansible Vault**: Encrypted storage for sensitive variables (optional)
- **SSH Keys**: Passwordless authentication for automation

## Troubleshooting

### Common Issues

#### Tailscale Connectivity Issues

**Problem:** Nodes not reachable via Tailscale IP

**Solutions:**
```bash
# On each node, check Tailscale status
tailscale status

# Verify Tailscale is running
sudo systemctl status tailscaled

# Check if node is authenticated
tailscale status | grep "logged in"

# Test connectivity from management machine
ping <tailscale-ip>
ssh user@<tailscale-ip>

# Restart Tailscale if needed
sudo systemctl restart tailscaled
```

#### SSH Connection Failures

**Problem:** Ansible cannot connect to nodes

**Solutions:**
```bash
# Test SSH connection manually
ssh user@<tailscale-ip>

# Check SSH key authentication
ssh -v user@<tailscale-ip>

# Ensure SSH key is in authorized_keys on target node
cat ~/.ssh/id_rsa.pub | ssh user@<tailscale-ip> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# Configure Ansible to use password authentication (temporary)
# Add to ansible.cfg:
# [defaults]
# ask_pass = True
```

#### K3s Installation Failures

**Problem:** K3s fails to install or start

**Solutions:**
```bash
# Check K3s service status on the node
sudo systemctl status k3s        # Control plane
sudo systemctl status k3s-agent  # Worker

# View K3s logs
sudo journalctl -u k3s -f        # Control plane
sudo journalctl -u k3s-agent -f  # Worker

# Check for port conflicts
sudo netstat -tulpn | grep -E ':(6443|10250|10251|10252)'

# Manually uninstall and retry
sudo /usr/local/bin/k3s-uninstall.sh        # Control plane
sudo /usr/local/bin/k3s-agent-uninstall.sh  # Worker

# Then re-run provisioning
cluster-mgr provision
```

#### Node Not Joining Cluster

**Problem:** Worker node fails to join control plane

**Solutions:**
```bash
# Verify control plane is accessible
curl -k https://<control-plane-tailscale-ip>:6443

# Check join token on control plane
sudo cat /var/lib/rancher/k3s/server/node-token

# Verify token in worker configuration
sudo cat /etc/rancher/k3s/config.yaml

# Check worker logs for connection errors
sudo journalctl -u k3s-agent -n 100

# Ensure firewall allows required ports
sudo ufw allow 6443/tcp   # API server
sudo ufw allow 10250/tcp  # Kubelet
```

#### GPU Not Detected

**Problem:** NVIDIA GPU not available in Kubernetes

**Solutions:**
```bash
# Verify GPU is detected by system
nvidia-smi

# Check if NVIDIA device plugin is running
kubectl get pods -n kube-system | grep nvidia

# View device plugin logs
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds

# Verify GPU resource is advertised
kubectl describe node <gpu-node-name> | grep nvidia.com/gpu

# Manually install NVIDIA drivers if needed
sudo apt update
sudo apt install -y nvidia-driver-535

# Reboot and re-run provisioning
sudo reboot
cluster-mgr provision --tags gpu
```

#### Flux GitOps Not Syncing

**Problem:** Applications not deploying from Git repository

**Solutions:**
```bash
# Check Flux controller status
kubectl get pods -n flux-system

# View Flux logs
kubectl logs -n flux-system -l app=source-controller
kubectl logs -n flux-system -l app=kustomize-controller

# Check Git repository source
kubectl get gitrepositories -n flux-system

# Verify Flux can access Git repository
kubectl describe gitrepository -n flux-system flux-system

# Force reconciliation
flux reconcile source git flux-system
flux reconcile kustomization flux-system

# Check for authentication issues (private repos)
kubectl get secret -n flux-system flux-system
```

#### High Resource Usage on Workstation Nodes

**Problem:** Kubernetes consuming too many resources

**Solutions:**
```bash
# Check current resource reservations
kubectl describe node <node-name> | grep -A 5 "Allocated resources"

# Increase resource reservations in inventory
# Edit ansible/inventory/hosts.yml:
# reserved_cpu: "4"      # Increase from 2
# reserved_memory: "8Gi" # Increase from 4Gi

# Re-run provisioning to apply changes
cluster-mgr provision --tags k3s_worker

# Add taints to prevent pod scheduling
cluster-mgr add-node <node-name> <ip> \
  --taints "workstation=true:NoSchedule"

# Manually drain and cordon node
kubectl drain <node-name> --ignore-daemonsets
kubectl cordon <node-name>
```

#### Playbook Fails Midway

**Problem:** Ansible playbook fails during execution

**Solutions:**
```bash
# Run in check mode to see what would change
cluster-mgr provision --check

# Increase verbosity to see detailed errors
cluster-mgr provision -vvv

# Run specific tags to isolate the issue
cluster-mgr provision --tags prerequisites
cluster-mgr provision --tags k3s

# Skip problematic tasks temporarily
cluster-mgr provision --skip-tags gpu,monitoring

# Check Ansible logs
cat ansible/artifacts/*/stdout

# Verify inventory syntax
ansible-inventory -i ansible/inventory/hosts.yml --list
```

#### TUI Not Connecting

**Problem:** cluster-tui cannot connect to cluster

**Solutions:**
```bash
# Verify kubeconfig exists
ls -la ~/.kube/config

# Test kubectl connection
kubectl get nodes

# Check kubeconfig context
kubectl config current-context
kubectl config get-contexts

# Set correct kubeconfig
export KUBECONFIG=~/.kube/config

# Verify API server is accessible
curl -k https://<control-plane-ip>:6443

# Check for certificate issues
kubectl cluster-info
```

### Getting Help

If you encounter issues not covered here:

1. **Check logs**: Most issues can be diagnosed from logs
   - Ansible: `ansible/artifacts/*/stdout`
   - K3s: `sudo journalctl -u k3s` or `sudo journalctl -u k3s-agent`
   - Kubernetes: `kubectl logs <pod-name>`

2. **Run in verbose mode**: Add `-v`, `-vv`, or `-vvv` to commands

3. **Verify prerequisites**: Ensure Tailscale is working and SSH access is configured

4. **Test manually**: Try manual steps to isolate the issue

5. **Check documentation**: Review the design and requirements documents

6. **Open an issue**: Provide logs, configuration, and steps to reproduce

## Advanced Topics

### High Availability Control Plane

To set up multiple control plane nodes for HA:

1. Add multiple nodes to the `control_plane` group in inventory
2. Configure an external load balancer or use Tailscale load balancing
3. Update `api_server_url` to point to the load balancer
4. Run provisioning playbook

### Custom Storage Classes

To add custom storage classes:

1. Create storage class manifests in `gitops/infrastructure/storage/`
2. Configure storage provider (NFS, Ceph, etc.)
3. Commit and push to Git repository
4. Flux will automatically apply the changes

### Monitoring Stack

To add Prometheus and Grafana:

1. Enable monitoring in `ansible/inventory/group_vars/all.yml`:
   ```yaml
   monitoring_enabled: true
   ```
2. Add monitoring manifests to `gitops/infrastructure/monitoring/`
3. Run provisioning playbook

### Backup and Restore

K3s stores state in SQLite by default:

```bash
# Backup control plane data
sudo tar czf k3s-backup.tar.gz /var/lib/rancher/k3s/server/db/

# Restore (on new control plane)
sudo systemctl stop k3s
sudo tar xzf k3s-backup.tar.gz -C /
sudo systemctl start k3s
```

### Upgrading K3s

To upgrade Kubernetes version:

```bash
# Update version in inventory
cluster-mgr config-set k3s_version v1.29.0+k3s1

# Run provisioning (will perform rolling upgrade)
cluster-mgr provision

# Verify upgrade
kubectl get nodes
```

## Documentation

### Getting Started
- [Quick Start Guide](docs/QUICKSTART.md) - Get up and running in 15 minutes
- [Quickstart Script](scripts/quickstart.sh) - Automated interactive setup
- [CLI Reference](docs/CLI_REFERENCE.md) - Complete command-line reference
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md) - Common issues and solutions

### Configuration Guides
- [GPU Configuration](docs/GPU_CONFIGURATION.md) - Complete guide for NVIDIA GPU setup
- [Example Inventories](ansible/inventory/) - Sample configurations for different scenarios

### Architecture and Design
- [Architecture Overview](docs/ARCHITECTURE.md) - System architecture and design decisions
- [Design Document](.kiro/specs/tailscale-k8s-cluster/design.md) - Detailed technical design
- [Requirements](.kiro/specs/tailscale-k8s-cluster/requirements.md) - Requirements and acceptance criteria

### Component Documentation
- [Ansible README](ansible/README.md) - Ansible playbooks and roles
- [GitOps README](gitops/README.md) - GitOps workflow and structure
- [Cluster Manager README](cluster_manager/README.md) - CLI and TUI tools

### Example Applications
- [Hello World](gitops/apps/base/hello-world/) - Simple nginx deployment
- [Web Application](gitops/apps/base/web-app-example/) - Full-stack web app with frontend and backend
- [GPU Test](gitops/apps/base/gpu-test/) - GPU availability verification
- [ML Training](gitops/apps/base/ml-training/) - GPU-accelerated training job
- [GPU Inference](gitops/apps/base/gpu-inference/) - GPU inference service with time-slicing

### Development
- [Contributing Guide](docs/CONTRIBUTING.md) - Development guidelines and workflow
- [Development Setup](docs/DEVELOPMENT.md) - Development environment setup
- [Testing Guide](docs/TESTING.md) - Running and writing tests
- [Implementation Tasks](.kiro/specs/tailscale-k8s-cluster/tasks.md) - Development task list

## License

MIT
