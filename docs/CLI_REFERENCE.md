# CLI Reference

Complete reference for the `cluster-mgr` command-line interface.

## Table of Contents

- [Installation](#installation)
- [Global Options](#global-options)
- [Commands](#commands)
  - [version](#version)
  - [discover](#discover)
  - [add-node](#add-node)
  - [remove-node](#remove-node)
  - [config-get](#config-get)
  - [config-set](#config-set)
  - [provision](#provision)
  - [status](#status)
- [Examples](#examples)
- [Exit Codes](#exit-codes)

## Installation

The `cluster-mgr` CLI is installed automatically when you run the setup script:

```bash
./setup.sh
```

Or manually with mise:

```bash
mise install
mise run install
```

## Global Options

These options are available for all commands:

- `--help` - Show help message and exit
- `--version` - Show version information

## Commands

### version

Show version information.

**Usage:**
```bash
cluster-mgr version
```

**Example:**
```bash
$ cluster-mgr version
Kubani version 0.1.0
```

---

### discover

Discover Tailscale nodes available for cluster membership.

**Usage:**
```bash
cluster-mgr discover [OPTIONS]
```

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--online-only` | `-o` | flag | false | Show only online nodes |
| `--filter` | `-f` | string | - | Filter nodes by hostname pattern |
| `--show-cluster-status` | - | flag | true | Show whether nodes are in the cluster |
| `--no-cluster-status` | - | flag | - | Hide cluster membership status |

**Examples:**

```bash
# Discover all Tailscale nodes
cluster-mgr discover

# Show only online nodes
cluster-mgr discover --online-only

# Filter by hostname pattern
cluster-mgr discover --filter "gpu-*"
cluster-mgr discover --filter "worker"

# Hide cluster membership status
cluster-mgr discover --no-cluster-status
```

**Output:**
```
┌─────────────────────────────────────────────────────────┐
│              Discovered Tailscale Nodes                 │
├──────────────┬─────────────────┬──────────┬────────────┤
│ Hostname     │ Tailscale IP    │ Status   │ In Cluster │
├──────────────┼─────────────────┼──────────┼────────────┤
│ control-1    │ 100.64.0.5      │ ✓ Online │ Yes        │
│ worker-1     │ 100.64.0.10     │ ✓ Online │ Yes        │
│ worker-2     │ 100.64.0.11     │ ✗ Offline│ No         │
└──────────────┴─────────────────┴──────────┴────────────┘

Total nodes found: 3
```

**Exit Codes:**
- `0` - Success
- `1` - Error (Tailscale not running, no nodes found, etc.)

---

### add-node

Add a node to the Ansible inventory.

**Usage:**
```bash
cluster-mgr add-node HOSTNAME TAILSCALE_IP [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `HOSTNAME` | Yes | Hostname of the node to add |
| `TAILSCALE_IP` | Yes | Tailscale IP address of the node |

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--role` | `-r` | string | worker | Node role: control-plane or worker |
| `--reserved-cpu` | - | string | - | CPU cores to reserve for local processes |
| `--reserved-memory` | - | string | - | Memory to reserve for local processes |
| `--gpu` | - | flag | false | Node has GPU capabilities |
| `--labels` | `-l` | string | - | Node labels as comma-separated key=value pairs |
| `--taints` | `-t` | string | - | Node taints as comma-separated key=value:effect |
| `--inventory` | `-i` | string | ansible/inventory/hosts.yml | Path to Ansible inventory file |

**Examples:**

```bash
# Add a basic worker node
cluster-mgr add-node worker-3 100.64.0.12 --role worker

# Add a control plane node
cluster-mgr add-node control-2 100.64.0.6 --role control-plane

# Add a workstation node with resource reservations
cluster-mgr add-node desktop 100.64.0.20 \
  --role worker \
  --reserved-cpu 2 \
  --reserved-memory 4Gi \
  --labels "workstation=true,env=dev"

# Add a GPU node with taints
cluster-mgr add-node gpu-server 100.64.0.30 \
  --role worker \
  --gpu \
  --reserved-cpu 4 \
  --reserved-memory 8Gi \
  --labels "gpu=true,gpu-type=nvidia" \
  --taints "nvidia.com/gpu=true:NoSchedule"

# Add node with multiple labels
cluster-mgr add-node web-1 100.64.0.15 \
  --role worker \
  --labels "tier=frontend,env=production,zone=us-east"

# Use custom inventory file
cluster-mgr add-node worker-4 100.64.0.13 \
  --inventory /path/to/custom/hosts.yml
```

**Label Format:**
- Comma-separated key=value pairs
- Example: `"key1=value1,key2=value2"`

**Taint Format:**
- Comma-separated key=value:effect
- Effects: `NoSchedule`, `PreferNoSchedule`, `NoExecute`
- Example: `"key1=value1:NoSchedule,key2=value2:PreferNoSchedule"`

**Output:**
```
✓ Successfully added node 'worker-3' to inventory
  Role: worker
  Tailscale IP: 100.64.0.12
  Reserved CPU: 2
  Reserved Memory: 4Gi
  Labels: workstation=true, env=dev
```

**Exit Codes:**
- `0` - Success
- `1` - Error (validation failed, node already exists, etc.)

---

### remove-node

Remove a node from the Ansible inventory.

**Usage:**
```bash
cluster-mgr remove-node HOSTNAME [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `HOSTNAME` | Yes | Hostname of the node to remove |

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--drain` | - | flag | true | Drain node before removal |
| `--no-drain` | - | flag | - | Skip draining the node |
| `--force` | `-f` | flag | false | Skip confirmation prompt |
| `--inventory` | `-i` | string | ansible/inventory/hosts.yml | Path to Ansible inventory file |

**Examples:**

```bash
# Remove a node (with drain and confirmation)
cluster-mgr remove-node worker-3

# Remove without draining
cluster-mgr remove-node worker-3 --no-drain

# Force removal without confirmation
cluster-mgr remove-node worker-3 --force

# Remove with custom inventory
cluster-mgr remove-node worker-3 --inventory /path/to/hosts.yml
```

**Interactive Confirmation:**
```
Warning: About to remove node 'worker-3' from inventory
  Role: worker
  Tailscale IP: 100.64.0.12
Are you sure you want to continue? [y/N]:
```

**Output:**
```
Draining node 'worker-3'...
✓ Node drained successfully
✓ Successfully removed node 'worker-3' from inventory

Note: To complete removal, you may need to:
  1. Delete the node from Kubernetes: kubectl delete node worker-3
  2. Stop K3s service on the node: systemctl stop k3s-agent
```

**Exit Codes:**
- `0` - Success
- `1` - Error (node not found, drain failed, etc.)

---

### config-get

Retrieve a configuration value from the Ansible inventory.

**Usage:**
```bash
cluster-mgr config-get KEY [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `KEY` | Yes | Configuration key to retrieve (supports dot notation) |

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--scope` | `-s` | string | all | Configuration scope: all, control_plane, or workers |
| `--inventory` | `-i` | string | ansible/inventory/hosts.yml | Path to Ansible inventory file |

**Examples:**

```bash
# Get a simple value
cluster-mgr config-get k3s_version
cluster-mgr config-get cluster_name

# Get value from specific scope
cluster-mgr config-get reserved_cpu --scope workers
cluster-mgr config-get node_labels --scope control_plane

# Get nested value using dot notation
cluster-mgr config-get flux.namespace
cluster-mgr config-get monitoring.retention

# Use custom inventory
cluster-mgr config-get k3s_version --inventory /path/to/hosts.yml
```

**Output:**

Simple value:
```
k3s_version (scope: all):
  v1.28.5+k3s1
```

Dictionary value:
```
node_labels (scope: workers):
{
  "node-role": "worker",
  "workstation": "true"
}
```

List value:
```
node_taints (scope: workers):
  - key: workstation
    value: true
    effect: NoSchedule
```

**Exit Codes:**
- `0` - Success
- `1` - Error (key not found, invalid scope, etc.)

---

### config-set

Set a configuration value in the Ansible inventory.

**Usage:**
```bash
cluster-mgr config-set KEY VALUE [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `KEY` | Yes | Configuration key to set (supports dot notation) |
| `VALUE` | Yes | Configuration value to set |

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--scope` | `-s` | string | all | Configuration scope: all, control_plane, or workers |
| `--type` | `-t` | string | string | Value type: string, int, bool, or json |
| `--inventory` | `-i` | string | ansible/inventory/hosts.yml | Path to Ansible inventory file |

**Examples:**

```bash
# Set string values
cluster-mgr config-set k3s_version v1.28.5+k3s1
cluster-mgr config-set cluster_name my-cluster

# Set integer values
cluster-mgr config-set worker_count 5 --type int
cluster-mgr config-set reserved_cpu 4 --type int --scope workers

# Set boolean values
cluster-mgr config-set monitoring_enabled true --type bool
cluster-mgr config-set gpu false --type bool

# Set JSON values
cluster-mgr config-set node_labels '{"env":"prod","tier":"backend"}' --type json

# Set nested values using dot notation
cluster-mgr config-set flux.namespace flux-system
cluster-mgr config-set monitoring.retention 15d

# Set value for specific scope
cluster-mgr config-set reserved_memory 8Gi --scope workers
cluster-mgr config-set api_server_port 6443 --scope control_plane

# Use custom inventory
cluster-mgr config-set k3s_version v1.29.0+k3s1 --inventory /path/to/hosts.yml
```

**Value Types:**

- `string` - Text value (default)
- `int` - Integer number
- `bool` - Boolean (true/false, yes/no, 1/0, on/off)
- `json` - JSON object or array

**Output:**
```
✓ Successfully set 'k3s_version' = v1.28.5+k3s1 (scope: all)

Updated configuration:
  k3s_version: v1.28.5+k3s1
```

**Exit Codes:**
- `0` - Success
- `1` - Error (invalid type, invalid scope, parse error, etc.)

---

### provision

Execute Ansible playbook to provision or update the cluster.

**Usage:**
```bash
cluster-mgr provision [OPTIONS]
```

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--playbook` | `-p` | string | provision_cluster.yml | Playbook to execute |
| `--inventory` | `-i` | string | ansible/inventory/hosts.yml | Path to Ansible inventory file |
| `--check` | `-c` | flag | false | Run in check mode (dry-run) |
| `--tags` | `-t` | string | - | Only run plays and tasks tagged with these values |
| `--skip-tags` | - | string | - | Skip plays and tasks tagged with these values |
| `--limit` | `-l` | string | - | Limit execution to specific hosts or groups |
| `--verbose` | `-v` | count | 0 | Increase verbosity (-v, -vv, -vvv) |
| `--extra-vars` | `-e` | string | - | Extra variables as JSON or key=value pairs |

**Examples:**

```bash
# Provision the entire cluster
cluster-mgr provision

# Run in check mode (dry-run, no changes)
cluster-mgr provision --check

# Run specific playbook
cluster-mgr provision --playbook add_node.yml
cluster-mgr provision --playbook site.yml

# Run only specific tags
cluster-mgr provision --tags "k3s,networking"
cluster-mgr provision --tags "prerequisites"

# Skip specific tags
cluster-mgr provision --skip-tags "gpu,monitoring"

# Limit to specific hosts
cluster-mgr provision --limit "worker-3"
cluster-mgr provision --limit "workers"
cluster-mgr provision --limit "control_plane"

# Combine options
cluster-mgr provision --tags "k3s" --limit "worker-3" --check

# Increase verbosity
cluster-mgr provision -v      # verbose
cluster-mgr provision -vv     # more verbose
cluster-mgr provision -vvv    # debug level

# Pass extra variables
cluster-mgr provision --extra-vars '{"k3s_version":"v1.28.5+k3s1"}'
cluster-mgr provision --extra-vars "k3s_version=v1.28.5+k3s1 cluster_name=test"

# Use custom inventory
cluster-mgr provision --inventory /path/to/hosts.yml
```

**Available Playbooks:**
- `provision_cluster.yml` - Initial cluster setup (default)
- `add_node.yml` - Add new nodes to existing cluster
- `site.yml` - Main entry point (runs all playbooks)

**Common Tags:**
- `prerequisites` - System preparation and validation
- `k3s` - K3s installation and configuration
- `k3s_control_plane` - Control plane specific tasks
- `k3s_worker` - Worker node specific tasks
- `gpu` - GPU support installation
- `gitops` - Flux CD installation
- `networking` - Network configuration
- `storage` - Storage configuration

**Output:**
```
Ansible Playbook Execution
Playbook: provision_cluster.yml
Inventory: ansible/inventory/hosts.yml

Starting playbook execution...

PLAY [Control Plane Nodes] *******************************************

TASK [Gathering Facts] ***********************************************
ok: [control-1]

...

PLAY RECAP ***********************************************************
control-1    : ok=45   changed=12   unreachable=0    failed=0
worker-1     : ok=38   changed=10   unreachable=0    failed=0
worker-2     : ok=38   changed=10   unreachable=0    failed=0

Host Statistics:
┌───────────┬────┬─────────┬─────────────┬────────┬─────────┐
│ Host      │ OK │ Changed │ Unreachable │ Failed │ Skipped │
├───────────┼────┼─────────┼─────────────┼────────┼─────────┤
│ control-1 │ 45 │ 12      │ 0           │ 0      │ 3       │
│ worker-1  │ 38 │ 10      │ 0           │ 0      │ 5       │
│ worker-2  │ 38 │ 10      │ 0           │ 0      │ 5       │
└───────────┴────┴─────────┴─────────────┴────────┴─────────┘

✓ Playbook execution completed successfully
```

**Exit Codes:**
- `0` - Success
- `1+` - Ansible error code (varies by failure type)
- `130` - Interrupted by user (Ctrl+C)

---

### status

Show cluster status and node health.

**Usage:**
```bash
cluster-mgr status [OPTIONS]
```

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--inventory` | `-i` | string | ansible/inventory/hosts.yml | Path to Ansible inventory file |
| `--pods` | `-p` | flag | false | Show pod information for each node |
| `--namespace` | `-n` | string | - | Filter pods by namespace (requires --pods) |

**Examples:**

```bash
# Show basic cluster status
cluster-mgr status

# Show status with pod information
cluster-mgr status --pods

# Show pods in specific namespace
cluster-mgr status --pods --namespace kube-system
cluster-mgr status --pods --namespace default

# Use custom inventory
cluster-mgr status --inventory /path/to/hosts.yml
```

**Output:**

Basic status:
```
Cluster Version: v1.28.5+k3s1

Cluster Nodes (3):
┌───────────┬───────────────┬─────────┬──────────────┬──────────────┬─────┐
│ Name      │ Role          │ Status  │ Version      │ Internal IP  │ Age │
├───────────┼───────────────┼─────────┼──────────────┼──────────────┼─────┤
│ control-1 │ Control Plane │ ✓ Ready │ v1.28.5+k3s1 │ 100.64.0.5   │ 5d  │
│ worker-1  │ Worker        │ ✓ Ready │ v1.28.5+k3s1 │ 100.64.0.10  │ 5d  │
│ worker-2  │ Worker        │ ✓ Ready │ v1.28.5+k3s1 │ 100.64.0.11  │ 5d  │
└───────────┴───────────────┴─────────┴──────────────┴──────────────┴─────┘

Summary:
  Total Nodes: 3
  Ready Nodes: 3
  Not Ready: 0

✓ All nodes are ready
```

With pods:
```
Pod Information:
┌─────────────┬──────────────────────────┬───────────┬─────────┬──────────┐
│ Namespace   │ Name                     │ Node      │ Status  │ Restarts │
├─────────────┼──────────────────────────┼───────────┼─────────┼──────────┤
│ kube-system │ coredns-xxx              │ control-1 │ Running │ 0        │
│ kube-system │ local-path-provisioner   │ control-1 │ Running │ 0        │
│ flux-system │ source-controller-xxx    │ worker-1  │ Running │ 0        │
│ default     │ hello-world-xxx          │ worker-2  │ Running │ 0        │
└─────────────┴──────────────────────────┴───────────┴─────────┴──────────┘

Total pods: 4
```

**Exit Codes:**
- `0` - Success
- `1` - Error (kubeconfig not found, API server unreachable, etc.)

---

## Examples

### Complete Workflow

```bash
# 1. Discover available nodes
cluster-mgr discover --online-only

# 2. Add nodes to inventory
cluster-mgr add-node control-1 100.64.0.5 --role control-plane
cluster-mgr add-node worker-1 100.64.0.10 --role worker --reserved-cpu 2
cluster-mgr add-node worker-2 100.64.0.11 --role worker --reserved-cpu 2

# 3. Configure cluster
cluster-mgr config-set cluster_name my-homelab
cluster-mgr config-set k3s_version v1.28.5+k3s1

# 4. Provision cluster (dry-run first)
cluster-mgr provision --check

# 5. Actual provisioning
cluster-mgr provision

# 6. Verify status
cluster-mgr status --pods

# 7. Add another node later
cluster-mgr add-node worker-3 100.64.0.12 --role worker
cluster-mgr provision --playbook add_node.yml --limit worker-3

# 8. Remove a node
cluster-mgr remove-node worker-3
```

### GPU Node Setup

```bash
# Add GPU node with proper configuration
cluster-mgr add-node gpu-server 100.64.0.30 \
  --role worker \
  --gpu \
  --reserved-cpu 4 \
  --reserved-memory 8Gi \
  --labels "gpu=true,gpu-type=nvidia,gpu-count=1" \
  --taints "nvidia.com/gpu=true:NoSchedule"

# Provision with GPU support
cluster-mgr provision --tags "prerequisites,k3s,gpu" --limit gpu-server

# Verify GPU is available
kubectl describe node gpu-server | grep nvidia.com/gpu
```

### Maintenance Operations

```bash
# Update K3s version
cluster-mgr config-set k3s_version v1.29.0+k3s1
cluster-mgr provision

# Update only worker nodes
cluster-mgr provision --limit workers

# Run only specific tasks
cluster-mgr provision --tags "k3s" --skip-tags "gpu,monitoring"

# Check what would change
cluster-mgr provision --check -vv
```

## Exit Codes

All commands use standard exit codes:

- `0` - Success
- `1` - General error (validation failed, resource not found, etc.)
- `2` - Command line syntax error
- `130` - Interrupted by user (Ctrl+C)

Ansible-specific exit codes (for `provision` command):
- `0` - Success, no changes
- `2` - Success, changes made
- `4` - Unreachable hosts
- `8` - Task failures

## Environment Variables

- `KUBECONFIG` - Path to kubeconfig file (default: `~/.kube/config`)
- `ANSIBLE_CONFIG` - Path to Ansible configuration file
- `ANSIBLE_INVENTORY` - Default inventory path

## Configuration Files

- `ansible/inventory/hosts.yml` - Main inventory file
- `ansible/inventory/group_vars/all.yml` - Global variables
- `ansible/ansible.cfg` - Ansible configuration
- `~/.kube/config` - Kubernetes configuration

## See Also

- [README.md](../README.md) - Main documentation
- [QUICKSTART.md](../QUICKSTART.md) - Quick start guide
- [Ansible README](../ansible/README.md) - Ansible-specific documentation
- [Design Document](../.kiro/specs/tailscale-k8s-cluster/design.md) - Architecture details

## Validation Scripts

In addition to the `cluster-mgr` CLI, several validation scripts are available for testing production services.

### Service Validation

**Comprehensive Validation:**
```bash
# Run all validation checks
./scripts/verify_services.sh
```

**Pod Status Validation:**
```bash
# Check all service pods
./scripts/validate_pods.sh

# Check specific service
./scripts/validate_pods.sh postgresql
./scripts/validate_pods.sh redis
./scripts/validate_pods.sh authentik
./scripts/validate_pods.sh cert-manager
```

**PostgreSQL Validation:**
```bash
# Test PostgreSQL connectivity and operations
./scripts/validate_postgresql.sh
```

Validates:
- DNS resolution (postgres.almckay.io)
- TCP connectivity (port 5432)
- Database authentication
- Basic CRUD operations (CREATE, INSERT, SELECT, DROP)

**Redis Validation:**
```bash
# Test Redis connectivity and operations
./scripts/validate_redis.sh
```

Validates:
- DNS resolution (redis.almckay.io)
- TCP connectivity (port 6379)
- Redis authentication
- Basic operations (PING, SET, GET, DEL)

**Authentik Validation:**
```bash
# Test Authentik HTTPS access
./scripts/validate_authentik.sh
```

Validates:
- DNS resolution (auth.almckay.io)
- HTTPS connectivity
- TLS certificate validity
- HTTP to HTTPS redirect
- Authentik API endpoint
- Web interface accessibility

**Certificate Validation:**
```bash
# Check TLS certificate status
./scripts/validate_certificates.sh
```

Validates:
- cert-manager deployment status
- ClusterIssuer configuration
- Certificate resources
- Certificate secrets
- Recent CertificateRequests

### DNS Configuration

**Get Traefik IP:**
```bash
# Display Traefik LoadBalancer IP and DNS instructions
./scripts/get_traefik_ip.sh
```

**Configure DNS Records:**
```bash
# Manual configuration (provides instructions)
./scripts/setup_dns_records.sh

# Automated configuration (requires Cloudflare API token)
uv run python scripts/configure_dns.py

# Configure specific services
uv run python scripts/configure_dns.py --services postgres redis

# Dry run (show what would be done)
uv run python scripts/configure_dns.py --dry-run
```

### Script Exit Codes

All validation scripts use consistent exit codes:
- `0` - All checks passed
- `1` - One or more checks failed

### Common Validation Workflow

```bash
# 1. Get Traefik IP
./scripts/get_traefik_ip.sh

# 2. Configure DNS records
./scripts/setup_dns_records.sh
# Or automated:
uv run python scripts/configure_dns.py

# 3. Wait for DNS propagation (1-2 minutes)
sleep 120

# 4. Validate all services
./scripts/verify_services.sh

# 5. Validate individual services if needed
./scripts/validate_postgresql.sh
./scripts/validate_redis.sh
./scripts/validate_authentik.sh
./scripts/validate_certificates.sh
```

### Troubleshooting with Validation Scripts

If a validation script fails, it will provide specific error messages and troubleshooting tips:

```bash
# Example: PostgreSQL validation failure
$ ./scripts/validate_postgresql.sh
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 PostgreSQL Connectivity Validation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Testing DNS resolution...
✗ DNS resolution failed
💡 Check DNS records in Cloudflare
```

Each script provides:
- Clear success/failure indicators (✓/✗)
- Specific error messages
- Troubleshooting suggestions
- Relevant commands to investigate further

### See Also

- [DNS Configuration Guide](DNS_CONFIGURATION.md) - Detailed DNS setup
- [Secrets Management Guide](SECRETS_MANAGEMENT.md) - Managing encrypted secrets
- [GitOps Service Deployment](GITOPS_SERVICE_DEPLOYMENT.md) - Deploying services
- [Troubleshooting Guide](TROUBLESHOOTING.md) - Common issues and solutions
