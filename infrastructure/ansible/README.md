# Ansible Automation

This directory contains Ansible playbooks and roles for provisioning and managing the Kubernetes cluster.

## Table of Contents

- [Directory Structure](#directory-structure)
- [Getting Started](#getting-started)
- [Playbooks](#playbooks)
- [Roles](#roles)
- [Inventory Configuration](#inventory-configuration)
- [Variables](#variables)
- [Tags](#tags)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Directory Structure

```
ansible/
├── ansible.cfg                 # Ansible configuration
├── inventory/
│   ├── hosts.yml              # Main inventory file (create from example)
│   ├── hosts.yml.example      # Example inventory
│   └── group_vars/
│       ├── all.yml            # Global variables (create from example)
│       ├── all.yml.example    # Example global variables
│       ├── control_plane.yml  # Control plane variables
│       └── workers.yml        # Worker node variables
├── playbooks/
│   ├── site.yml              # Main entry point
│   ├── provision_cluster.yml # Initial cluster setup
│   └── add_node.yml          # Add new nodes
└── roles/
    ├── prerequisites/        # System preparation
    ├── k3s_control_plane/   # Control plane setup
    ├── k3s_worker/          # Worker node setup
    ├── gpu_support/         # GPU support
    ├── gitops/              # Flux CD setup
    └── node_config/         # Node-specific configuration
```

## Getting Started

### 1. Create Inventory

Copy the example inventory and customize it:

```bash
cp inventory/hosts.yml.example inventory/hosts.yml
vim inventory/hosts.yml
```

**Minimum required configuration:**
- At least one control plane node
- Tailscale IP addresses for all nodes
- Node roles (control-plane or worker)

### 2. Configure Variables

Copy and customize group variables:

```bash
cp inventory/group_vars/all.yml.example inventory/group_vars/all.yml
vim inventory/group_vars/all.yml
```

**Key variables to set:**
- `k3s_version` - K3s version to install
- `cluster_name` - Your cluster name
- `git_repo_url` - Git repository for GitOps
- `git_branch` - Git branch to monitor

### 3. Test Connectivity

Verify Ansible can connect to all nodes:

```bash
ansible all -i inventory/hosts.yml -m ping
```

### 4. Run Provisioning

Execute the main playbook:

```bash
# Using cluster-mgr CLI (recommended)
cluster-mgr provision

# Or directly with ansible-playbook
ansible-playbook -i inventory/hosts.yml playbooks/site.yml

# Or with check mode first (dry-run)
ansible-playbook -i inventory/hosts.yml playbooks/site.yml --check
```

## Playbooks

### site.yml

Main entry point that orchestrates the entire cluster setup.

**Usage:**
```bash
ansible-playbook -i inventory/hosts.yml playbooks/site.yml
```

**What it does:**
1. Runs prerequisites on all nodes
2. Sets up control plane
3. Configures worker nodes
4. Installs GPU support (if configured)
5. Sets up GitOps with Flux
6. Applies node-specific configurations

**Options:**
```bash
# Check mode (dry-run)
ansible-playbook playbooks/site.yml --check

# Limit to specific hosts
ansible-playbook playbooks/site.yml --limit "workers"

# Use specific tags
ansible-playbook playbooks/site.yml --tags "k3s,networking"

# Skip specific tags
ansible-playbook playbooks/site.yml --skip-tags "gpu,monitoring"

# Increase verbosity
ansible-playbook playbooks/site.yml -vvv
```

### provision_cluster.yml

Initial cluster provisioning playbook.

**Usage:**
```bash
ansible-playbook -i inventory/hosts.yml playbooks/provision_cluster.yml
```

**What it does:**
- Same as site.yml but optimized for initial setup
- Includes pre-flight validation
- Sets up cluster from scratch

### add_node.yml

Add new nodes to an existing cluster.

**Usage:**
```bash
# Add specific node
ansible-playbook -i inventory/hosts.yml playbooks/add_node.yml --limit "new-node"

# Or use cluster-mgr
cluster-mgr provision --playbook add_node.yml --limit "new-node"
```

**What it does:**
1. Validates new node prerequisites
2. Installs K3s agent
3. Joins node to existing cluster
4. Applies node-specific configuration
5. Verifies node is ready

## Roles

### prerequisites

System preparation and validation.

**Tasks:**
- Verify Tailscale installation and connectivity
- Install system dependencies (curl, apt-transport-https, etc.)
- Configure firewall rules for Kubernetes
- Validate node reachability

**Variables:**
- `tailscale_network` - Tailscale network CIDR
- `required_packages` - List of packages to install

**Tags:** `prerequisites`, `tailscale`, `firewall`, `dependencies`

### k3s_control_plane

Control plane node setup.

**Tasks:**
- Download and install K3s server
- Configure API server with Tailscale IP
- Generate kubeconfig file
- Extract and store join token
- Configure K3s service

**Variables:**
- `k3s_version` - K3s version to install
- `api_server_ip` - Tailscale IP for API server
- `cluster_cidr` - Pod network CIDR
- `service_cidr` - Service network CIDR

**Tags:** `k3s`, `k3s_control_plane`, `control_plane`

### k3s_worker

Worker node setup.

**Tasks:**
- Download and install K3s agent
- Configure worker to join cluster
- Set up resource reservations
- Apply node labels and taints
- Configure K3s agent service

**Variables:**
- `control_plane_url` - Control plane API URL
- `join_token` - Cluster join token
- `reserved_cpu` - CPU cores to reserve
- `reserved_memory` - Memory to reserve

**Tags:** `k3s`, `k3s_worker`, `worker`

### gpu_support

NVIDIA GPU support.

**Tasks:**
- Install NVIDIA drivers (if needed)
- Deploy NVIDIA device plugin
- Configure GPU time-slicing
- Validate GPU availability

**Variables:**
- `nvidia_driver_version` - Driver version to install
- `gpu_sharing_enabled` - Enable time-slicing

**Tags:** `gpu`, `nvidia`

**Conditions:** Only runs on nodes with `gpu: true`

### gitops

Flux CD installation and configuration.

**Tasks:**
- Install Flux CLI
- Bootstrap Flux to cluster
- Configure Git repository monitoring
- Create GitOps directory structure

**Variables:**
- `git_repo_url` - Git repository URL
- `git_branch` - Branch to monitor
- `flux_namespace` - Flux namespace

**Tags:** `gitops`, `flux`

### node_config

Node-specific configuration.

**Tasks:**
- Detect node hardware capabilities
- Apply conditional configurations
- Configure storage classes
- Set up resource limits

**Variables:**
- Node-specific variables from inventory

**Tags:** `node_config`, `hardware`

## Inventory Configuration

### Basic Structure

```yaml
all:
  vars:
    # Global variables
  children:
    control_plane:
      hosts:
        # Control plane nodes
    workers:
      hosts:
        # Worker nodes
```

### Node Definition

**Required fields:**
```yaml
node-name:
  ansible_host: 100.64.0.10      # Tailscale IP
  tailscale_ip: 100.64.0.10      # Tailscale IP
```

**Optional fields:**
```yaml
node-name:
  ansible_host: 100.64.0.10
  tailscale_ip: 100.64.0.10
  ansible_user: ubuntu            # SSH user (default: current user)
  ansible_port: 22                # SSH port (default: 22)
  reserved_cpu: "2"               # CPU cores to reserve
  reserved_memory: "4Gi"          # Memory to reserve
  gpu: true                       # Has GPU
  node_labels:                    # Kubernetes labels
    key: value
  node_taints:                    # Kubernetes taints
    - key: taint-key
      value: taint-value
      effect: NoSchedule
```

### Example Configurations

See [inventory/hosts.yml.example](inventory/hosts.yml.example) for complete examples.

## Variables

### Global Variables (all.yml)

```yaml
# K3s configuration
k3s_version: v1.28.5+k3s1
k3s_install_dir: /usr/local/bin
k3s_config_dir: /etc/rancher/k3s
k3s_data_dir: /var/lib/rancher/k3s

# Cluster configuration
cluster_name: homelab
cluster_domain: cluster.local
cluster_cidr: 10.42.0.0/16
service_cidr: 10.43.0.0/16

# Tailscale configuration
tailscale_network: 100.64.0.0/10

# GitOps configuration
gitops_enabled: true
git_repo_url: https://github.com/user/repo.git
git_branch: main
flux_namespace: flux-system

# Networking
cni: flannel
dns_service: coredns

# Storage
default_storage_class: local-path
```

### Control Plane Variables

```yaml
# API server configuration
api_server_port: 6443
api_server_extra_args: []

# etcd configuration (for HA)
etcd_snapshot_schedule: "0 */12 * * *"
etcd_snapshot_retention: 5
```

### Worker Variables

```yaml
# Default resource reservations
reserved_cpu: "1"
reserved_memory: "2Gi"

# Kubelet configuration
kubelet_extra_args: []
```

## Tags

Use tags to run specific parts of the playbook:

### Available Tags

- `prerequisites` - System preparation
- `tailscale` - Tailscale validation
- `firewall` - Firewall configuration
- `dependencies` - Package installation
- `k3s` - All K3s tasks
- `k3s_control_plane` - Control plane setup
- `k3s_worker` - Worker setup
- `gpu` - GPU support
- `nvidia` - NVIDIA specific tasks
- `gitops` - Flux CD setup
- `flux` - Flux specific tasks
- `networking` - Network configuration
- `storage` - Storage configuration
- `node_config` - Node-specific config

### Tag Usage Examples

```bash
# Run only prerequisites
ansible-playbook playbooks/site.yml --tags "prerequisites"

# Run K3s installation only
ansible-playbook playbooks/site.yml --tags "k3s"

# Skip GPU and monitoring
ansible-playbook playbooks/site.yml --skip-tags "gpu,monitoring"

# Run multiple specific tags
ansible-playbook playbooks/site.yml --tags "prerequisites,k3s,gitops"
```

## Best Practices

### 1. Version Control

- Keep inventory and variables in Git
- Use `.gitignore` to exclude sensitive files
- Document custom configurations

### 2. Testing

```bash
# Always test with check mode first
ansible-playbook playbooks/site.yml --check

# Test on a single node
ansible-playbook playbooks/site.yml --limit "test-node"

# Increase verbosity for debugging
ansible-playbook playbooks/site.yml -vvv
```

### 3. Idempotency

- All playbooks are designed to be idempotent
- Safe to re-run multiple times
- Only changes what's necessary

### 4. Secrets Management

```bash
# Use Ansible Vault for sensitive data
ansible-vault create inventory/group_vars/all/vault.yml

# Edit encrypted file
ansible-vault edit inventory/group_vars/all/vault.yml

# Run playbook with vault
ansible-playbook playbooks/site.yml --ask-vault-pass
```

### 5. Backup

```bash
# Backup control plane data before major changes
ssh user@control-plane "sudo tar czf k3s-backup.tar.gz /var/lib/rancher/k3s/server/db/"
```

### 6. Incremental Changes

```bash
# Use tags to apply specific changes
ansible-playbook playbooks/site.yml --tags "networking"

# Limit to specific nodes
ansible-playbook playbooks/site.yml --limit "workers"
```

## Troubleshooting

### Connection Issues

```bash
# Test connectivity
ansible all -i inventory/hosts.yml -m ping

# Test with verbose output
ansible all -i inventory/hosts.yml -m ping -vvv

# Test specific host
ansible control-1 -i inventory/hosts.yml -m ping
```

### Playbook Failures

```bash
# Run in check mode to see what would change
ansible-playbook playbooks/site.yml --check

# Increase verbosity
ansible-playbook playbooks/site.yml -vvv

# Run specific tags to isolate issue
ansible-playbook playbooks/site.yml --tags "prerequisites"
```

### Inventory Validation

```bash
# List all hosts
ansible-inventory -i inventory/hosts.yml --list

# Show specific host variables
ansible-inventory -i inventory/hosts.yml --host control-1

# Graph inventory structure
ansible-inventory -i inventory/hosts.yml --graph
```

### Common Issues

1. **SSH connection refused**
   - Verify SSH is running on target nodes
   - Check SSH keys are configured
   - Verify Tailscale connectivity

2. **Permission denied**
   - Ensure user has sudo privileges
   - Configure passwordless sudo or use `--ask-become-pass`

3. **Task failures**
   - Check logs: `ansible/artifacts/*/stdout`
   - Verify prerequisites are met
   - Check node resources (disk space, memory)

For more troubleshooting, see [docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md).

## See Also

- [Main README](../README.md) - Project overview
- [CLI Reference](../docs/CLI_REFERENCE.md) - CLI command documentation
- [Troubleshooting Guide](../docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Design Document](../.kiro/specs/tailscale-k8s-cluster/design.md) - Architecture details
