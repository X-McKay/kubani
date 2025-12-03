# Ansible Inventory Examples

This directory contains example inventory files for different cluster configurations. Choose the example that best matches your setup and customize it for your environment.

## Quick Start

1. Copy an example file:
   ```bash
   cp hosts-minimal.yml.example hosts.yml
   ```

2. Edit `hosts.yml` with your node information:
   - Replace Tailscale IP addresses
   - Update hostnames
   - Adjust resource reservations
   - Configure node labels and taints

3. Copy group variables:
   ```bash
   cp group_vars/all.yml.example group_vars/all.yml
   cp group_vars/control_plane.yml.example group_vars/control_plane.yml
   cp group_vars/workers.yml.example group_vars/workers.yml
   ```

4. Customize group variables as needed

## Available Examples

### hosts-minimal.yml.example

**Use case:** Testing, small home labs, learning

**Configuration:**
- 1 control plane node
- 1 worker node
- Minimal resource requirements
- No GPU support

**Best for:**
- First-time users
- Development environments
- Resource-constrained setups

### hosts.yml.example

**Use case:** Standard home lab, mixed workstation cluster

**Configuration:**
- 1 control plane node (NUC)
- 2 worker nodes (desktop + DGX Spark)
- Resource reservations for workstation use
- GPU support on DGX Spark
- Demonstrates heterogeneous hardware

**Best for:**
- Home labs with mixed hardware
- Workstations that need to remain usable
- GPU workloads alongside general compute

### hosts-gpu.yml.example

**Use case:** GPU-focused clusters, ML/AI workloads

**Configuration:**
- 1 control plane node
- 1 standard worker node
- 2 GPU worker nodes with different GPU types
- GPU-specific labels and taints
- Resource reservations for local GPU work

**Best for:**
- Machine learning workloads
- GPU-accelerated applications
- Multiple GPU types in same cluster
- Workstations with high-end GPUs

### hosts-ha.yml.example

**Use case:** High availability, production environments

**Configuration:**
- 3 control plane nodes (HA setup)
- 3+ worker nodes
- Load balancing for API server
- Distributed control plane

**Best for:**
- Production deployments
- Critical workloads
- Maximum uptime requirements
- Larger clusters (5+ nodes)

### hosts-mixed.yml.example

**Use case:** Complex heterogeneous environments

**Configuration:**
- Multiple control plane nodes
- Mix of standard and GPU workers
- Different resource profiles per node
- Custom labels for workload targeting
- Various taints for scheduling control

**Best for:**
- Large home labs
- Mixed workload types
- Advanced scheduling requirements
- Demonstrating all features

## Inventory Structure

### Basic Structure

```yaml
all:
  vars:
    # Global variables for all nodes
    k3s_version: v1.28.5+k3s1
    cluster_name: my-cluster
    tailscale_network: 100.64.0.0/10
    git_repo_url: https://github.com/user/repo.git
    git_branch: main

  children:
    control_plane:
      hosts:
        control-node:
          ansible_host: 100.64.0.10
          tailscale_ip: 100.64.0.10
          node_labels:
            node-role: control-plane

    workers:
      hosts:
        worker-node:
          ansible_host: 100.64.0.20
          tailscale_ip: 100.64.0.20
          reserved_cpu: "2"
          reserved_memory: "4Gi"
          node_labels:
            node-role: worker
```

### Required Variables

#### Global (all.vars)

- `k3s_version`: K3s version to install (e.g., "v1.28.5+k3s1")
- `cluster_name`: Name for your cluster
- `tailscale_network`: Tailscale network CIDR (usually 100.64.0.0/10)

#### Per Host

- `ansible_host`: Tailscale IP address for SSH connection
- `tailscale_ip`: Tailscale IP address for Kubernetes networking

### Optional Variables

#### Global

- `git_repo_url`: Git repository for GitOps (enables Flux CD)
- `git_branch`: Git branch to monitor (default: main)
- `flux_namespace`: Namespace for Flux controllers (default: flux-system)
- `cluster_cidr`: Pod network CIDR (default: 10.42.0.0/16)
- `service_cidr`: Service network CIDR (default: 10.43.0.0/16)

#### Per Host

- `reserved_cpu`: CPU cores to reserve for local use (e.g., "2", "4")
- `reserved_memory`: Memory to reserve for local use (e.g., "4Gi", "8Gi")
- `gpu`: Set to `true` for nodes with NVIDIA GPUs
- `node_labels`: Dictionary of Kubernetes labels
- `node_taints`: List of taints to prevent pod scheduling

## Node Configuration Examples

### Standard Worker Node

```yaml
worker-1:
  ansible_host: 100.64.0.20
  tailscale_ip: 100.64.0.20
  reserved_cpu: "2"
  reserved_memory: "4Gi"
  node_labels:
    node-role: worker
    workload-type: general
```

### GPU Worker Node

```yaml
gpu-worker:
  ansible_host: 100.64.0.30
  tailscale_ip: 100.64.0.30
  reserved_cpu: "4"
  reserved_memory: "8Gi"
  gpu: true
  node_labels:
    node-role: worker
    gpu: "true"
    gpu-type: nvidia-rtx-4090
    workstation: "true"
  node_taints:
    - key: nvidia.com/gpu
      value: "true"
      effect: NoSchedule
```

### High-Memory Worker Node

```yaml
memory-worker:
  ansible_host: 100.64.0.40
  tailscale_ip: 100.64.0.40
  reserved_cpu: "2"
  reserved_memory: "16Gi"
  node_labels:
    node-role: worker
    memory: high
    workload-type: memory-intensive
```

### Edge Node (Low Resources)

```yaml
edge-node:
  ansible_host: 100.64.0.50
  tailscale_ip: 100.64.0.50
  reserved_cpu: "1"
  reserved_memory: "1Gi"
  node_labels:
    node-role: worker
    location: edge
    resources: limited
  node_taints:
    - key: resources
      value: limited
      effect: PreferNoSchedule
```

## Node Labels

Labels help with pod scheduling and organization:

### Common Labels

- `node-role`: Role of the node (control-plane, worker)
- `workstation`: "true" for nodes that are also workstations
- `gpu`: "true" for GPU-enabled nodes
- `gpu-type`: Specific GPU model (nvidia-rtx-4090, nvidia-a100, etc.)
- `workload-type`: Type of workloads (general, gpu, memory-intensive, etc.)
- `location`: Physical location (home, office, edge, etc.)
- `environment`: Environment type (production, staging, development)

### Custom Labels

Add any labels that help with your scheduling needs:

```yaml
node_labels:
  team: ml-research
  cost-center: engineering
  backup-priority: high
  maintenance-window: weekend
```

## Node Taints

Taints prevent pods from scheduling unless they have matching tolerations:

### Common Taints

**GPU Nodes:**
```yaml
node_taints:
  - key: nvidia.com/gpu
    value: "true"
    effect: NoSchedule
```

**High-Performance Nodes:**
```yaml
node_taints:
  - key: high-performance
    value: "true"
    effect: PreferNoSchedule
```

**Maintenance Mode:**
```yaml
node_taints:
  - key: maintenance
    value: "true"
    effect: NoExecute
```

### Taint Effects

- `NoSchedule`: Pods won't schedule unless they tolerate the taint
- `PreferNoSchedule`: Scheduler tries to avoid, but will schedule if needed
- `NoExecute`: Existing pods are evicted if they don't tolerate the taint

## Resource Reservations

Reserve resources for local workstation use:

### Light Workstation Use

```yaml
reserved_cpu: "1"
reserved_memory: "2Gi"
```

### Moderate Workstation Use

```yaml
reserved_cpu: "2"
reserved_memory: "4Gi"
```

### Heavy Workstation Use (Development, GPU Work)

```yaml
reserved_cpu: "4"
reserved_memory: "8Gi"
```

### Server (No Local Use)

```yaml
# No reservations needed
# Or minimal:
reserved_cpu: "500m"
reserved_memory: "1Gi"
```

## Group Variables

### group_vars/all.yml

Global settings for all nodes:

```yaml
k3s_version: v1.28.5+k3s1
cluster_name: homelab
cluster_cidr: 10.42.0.0/16
service_cidr: 10.43.0.0/16
gitops_enabled: true
monitoring_enabled: false
```

### group_vars/control_plane.yml

Control plane specific settings:

```yaml
k3s_server_args:
  - "--disable=traefik"
  - "--write-kubeconfig-mode=644"
  - "--tls-san={{ tailscale_ip }}"
backup_enabled: true
backup_schedule: "0 2 * * *"
```

### group_vars/workers.yml

Worker node specific settings:

```yaml
reserved_cpu: "1"
reserved_memory: "2Gi"
nvidia_driver_version: "535"
gpu_time_slicing_enabled: true
gpu_replicas: 4
```

## Validation

Before provisioning, validate your inventory:

```bash
# Test SSH connectivity
ansible all -i hosts.yml -m ping

# Check inventory structure
ansible-inventory -i hosts.yml --list

# Validate YAML syntax
yamllint hosts.yml

# Dry-run provisioning
cluster-mgr provision --check
```

## Common Patterns

### Development Cluster

- 1 control plane
- 1-2 workers
- Minimal resources
- No GPU
- Local storage

### Home Lab

- 1 control plane
- 2-4 workers
- Mixed hardware
- Optional GPU
- GitOps enabled

### ML/AI Cluster

- 1 control plane
- Multiple GPU workers
- High memory
- GPU time-slicing
- Dedicated storage

### Production Cluster

- 3 control planes (HA)
- 5+ workers
- No workstation use
- Monitoring enabled
- Backup configured

## Troubleshooting

### SSH Connection Issues

```bash
# Test SSH manually
ssh user@100.64.0.20

# Copy SSH key
ssh-copy-id user@100.64.0.20

# Check Tailscale connectivity
tailscale ping 100.64.0.20
```

### Inventory Syntax Errors

```bash
# Validate YAML
python -c "import yaml; yaml.safe_load(open('hosts.yml'))"

# Use ansible-inventory
ansible-inventory -i hosts.yml --list
```

### Variable Precedence

Variables are applied in this order (later overrides earlier):
1. group_vars/all.yml
2. group_vars/control_plane.yml or group_vars/workers.yml
3. Host-specific variables in hosts.yml

## References

- [Ansible Inventory Documentation](https://docs.ansible.com/ansible/latest/user_guide/intro_inventory.html)
- [K3s Configuration](https://docs.k3s.io/installation/configuration)
- [Kubernetes Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
- [Kubernetes Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)
- [GPU Configuration Guide](../../docs/GPU_CONFIGURATION.md)

## Getting Help

- Check example files for reference configurations
- Review [QUICKSTART.md](../../QUICKSTART.md) for step-by-step guide
- See [TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md) for common issues
- Run `cluster-mgr --help` for CLI assistance
