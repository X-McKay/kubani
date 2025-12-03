# Architecture Documentation

This document provides a detailed overview of the Kubani system architecture, component interactions, and design decisions.

## Table of Contents

- [System Overview](#system-overview)
- [Component Architecture](#component-architecture)
- [Network Architecture](#network-architecture)
- [Data Flow](#data-flow)
- [Security Model](#security-model)
- [Design Decisions](#design-decisions)
- [Scalability](#scalability)
- [High Availability](#high-availability)

## System Overview

Kubani is a Kubernetes cluster automation system designed for heterogeneous hardware connected via Tailscale VPN. The system enables users to build production-ready clusters using existing workstations, servers, and edge devices without complex networking setup.

### Key Characteristics

- **Distributed**: Nodes can be in different physical locations
- **Heterogeneous**: Supports different hardware types (desktop, server, GPU nodes)
- **Workstation-Friendly**: Nodes remain usable as standalone machines
- **GitOps-Native**: Declarative application management through Git
- **Automated**: Minimal manual intervention required
- **Idempotent**: Safe to re-run operations

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Kubernetes | K3s | Lightweight Kubernetes distribution |
| VPN | Tailscale | Mesh networking and NAT traversal |
| Automation | Ansible | Infrastructure as code |
| GitOps | Flux CD | Declarative application deployment |
| CLI | Typer + Rich | Command-line interface |
| TUI | Textual | Terminal user interface |
| Package Manager | UV | Python dependency management |
| Runtime Manager | Mise | Tool version management |
| Container Runtime | containerd | Container execution (included with K3s) |
| CNI | Flannel | Pod networking (included with K3s) |

## Component Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Repository                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Infrastructure as Code (Ansible)                     │   │
│  │ - Playbooks, Roles, Inventory                        │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Application Manifests (GitOps)                       │   │
│  │ - Deployments, Services, ConfigMaps                  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Management Tools (Python)                            │   │
│  │ - CLI, TUI, Data Models                              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Management Workstation                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ cluster-mgr CLI                                      │   │
│  │ - Node discovery and management                      │   │
│  │ - Configuration management                           │   │
│  │ - Playbook execution                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ cluster-tui                                          │   │
│  │ - Real-time cluster monitoring                       │   │
│  │ - Node and service status                            │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Ansible                                              │   │
│  │ - Playbook execution engine                          │   │
│  │ - SSH connection management                          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Tailscale Network   │
              │   (Mesh VPN Layer)    │
              │                       │
              │ - Encrypted tunnels   │
              │ - NAT traversal       │
              │ - Automatic routing   │
              └───────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Control Plane│  │    Worker    │  │  GPU Worker  │
│              │  │              │  │              │
│ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │
│ │ K3s      │ │  │ │ K3s      │ │  │ │ K3s      │ │
│ │ Server   │ │  │ │ Agent    │ │  │ │ Agent    │ │
│ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │
│ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │
│ │ Flux CD  │ │  │ │ Workloads│ │  │ │ NVIDIA   │ │
│ │ GitOps   │ │  │ │          │ │  │ │ Plugin   │ │
│ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │
│ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │
│ │ etcd/    │ │  │ │ Local    │ │  │ │ GPU      │ │
│ │ SQLite   │ │  │ │ Apps     │ │  │ │ Workloads│ │
│ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Component Responsibilities

#### Management Workstation

**Purpose**: Central control point for cluster management

**Components**:
- `cluster-mgr` CLI: Node management, configuration, provisioning
- `cluster-tui`: Real-time monitoring and status display
- Ansible: Automation execution engine
- kubectl: Direct Kubernetes API access

**Interactions**:
- Connects to nodes via SSH over Tailscale
- Queries Kubernetes API for cluster status
- Executes Ansible playbooks for provisioning
- Reads/writes inventory and configuration files

#### Control Plane Node

**Purpose**: Kubernetes control plane and cluster coordination

**Components**:
- K3s Server: API server, scheduler, controller manager
- etcd/SQLite: Cluster state storage
- Flux CD: GitOps controller
- CoreDNS: Cluster DNS
- Traefik: Ingress controller (optional)

**Responsibilities**:
- Kubernetes API endpoint
- Cluster state management
- Workload scheduling
- GitOps synchronization
- Certificate management

#### Worker Nodes

**Purpose**: Run application workloads

**Components**:
- K3s Agent: Kubelet, kube-proxy
- Container Runtime: containerd
- CNI Plugin: Flannel
- Local Applications: User workstation software

**Responsibilities**:
- Execute pods and containers
- Report node status to control plane
- Enforce resource reservations
- Maintain local workstation functionality

#### GPU Worker Nodes

**Purpose**: Run GPU-accelerated workloads

**Additional Components**:
- NVIDIA Drivers
- NVIDIA Device Plugin
- GPU Time-Slicing Configuration

**Responsibilities**:
- Expose GPU resources to Kubernetes
- Share GPU among multiple pods
- Maintain GPU access for local applications

## Network Architecture

### Tailscale Mesh Network

```
┌─────────────────────────────────────────────────────────────┐
│                    Tailscale Coordination Server            │
│                    (tailscale.com)                          │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ (Control plane only)
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Node A       │  │ Node B       │  │ Node C       │
│ 100.64.0.5   │  │ 100.64.0.10  │  │ 100.64.0.11  │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                (Direct encrypted tunnels)
                (Automatic NAT traversal)
```

**Key Features**:
- **Mesh Topology**: Every node can communicate directly with every other node
- **Encrypted**: WireGuard protocol for all traffic
- **NAT Traversal**: Automatic hole-punching through firewalls
- **Dynamic Routing**: Automatically finds best path between nodes
- **Stable IPs**: Nodes keep same IP even when moving networks

### Kubernetes Network Layers

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Service Network (ClusterIP, NodePort, LoadBalancer)│
│ CIDR: 10.43.0.0/16                                          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Pod Network (Flannel CNI)                          │
│ CIDR: 10.42.0.0/16                                          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Node Network (Tailscale)                           │
│ CIDR: 100.64.0.0/10                                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Physical Network (Internet, LAN, etc.)             │
└─────────────────────────────────────────────────────────────┘
```

### Network Traffic Flow

**Pod-to-Pod Communication**:
1. Pod A (10.42.1.5) wants to reach Pod B (10.42.2.10)
2. Flannel encapsulates packet with node IPs
3. Packet routed over Tailscale (100.64.0.x)
4. Tailscale encrypts and routes to destination node
5. Flannel decapsulates and delivers to Pod B

**External Access**:
1. User accesses service via Ingress
2. Traefik ingress controller receives request
3. Routes to appropriate service
4. Service load-balances to pods
5. Response follows reverse path

**API Server Access**:
1. kubectl/TUI connects to control plane Tailscale IP:6443
2. TLS authentication with client certificates
3. API server processes request
4. Response returned over same connection

## Data Flow

### Provisioning Flow

```
┌─────────────┐
│ User runs   │
│ cluster-mgr │
│ provision   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Ansible reads inventory and playbooks   │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ SSH to each node over Tailscale         │
└──────┬──────────────────────────────────┘
       │
       ├──────────────────────────────────┐
       │                                  │
       ▼                                  ▼
┌──────────────────┐            ┌──────────────────┐
│ Control Plane    │            │ Worker Nodes     │
│ 1. Prerequisites │            │ 1. Prerequisites │
│ 2. Install K3s   │            │ 2. Install K3s   │
│    Server        │            │    Agent         │
│ 3. Configure API │            │ 3. Join cluster  │
│ 4. Install Flux  │            │ 4. Apply labels  │
│ 5. Bootstrap     │            │ 5. Configure     │
│    GitOps        │            │    resources     │
└──────────────────┘            └──────────────────┘
       │                                  │
       └──────────────┬───────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Cluster Ready │
              └───────────────┘
```

### GitOps Deployment Flow

```
┌─────────────┐
│ Developer   │
│ commits to  │
│ Git         │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Git Repository                          │
│ gitops/apps/my-app/deployment.yaml      │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Flux Source Controller                  │
│ - Polls Git every 1 minute              │
│ - Detects changes                       │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Flux Kustomize Controller               │
│ - Builds manifests                      │
│ - Applies to cluster                    │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Kubernetes API Server                   │
│ - Creates/updates resources             │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Scheduler                               │
│ - Assigns pods to nodes                 │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Kubelet on Worker Node                  │
│ - Pulls container image                 │
│ - Starts containers                     │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────┐
│ Application │
│ Running     │
└─────────────┘
```

### Monitoring Flow

```
┌─────────────┐
│ User runs   │
│ cluster-tui │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Load kubeconfig                         │
│ (~/.kube/config)                        │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ Connect to API Server                   │
│ (Control Plane Tailscale IP:6443)       │
└──────┬──────────────────────────────────┘
       │
       ├──────────────────────────────────┐
       │                                  │
       ▼                                  ▼
┌──────────────────┐            ┌──────────────────┐
│ Query Nodes      │            │ Query Pods       │
│ - Status         │            │ - Status         │
│ - Resources      │            │ - Restarts       │
│ - Labels         │            │ - Node placement │
└──────────────────┘            └──────────────────┘
       │                                  │
       └──────────────┬───────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Display in TUI│
              │ - Tables      │
              │ - Colors      │
              │ - Auto-refresh│
              └───────────────┘
```

## Security Model

### Authentication and Authorization

**SSH Authentication**:
- Public key authentication for Ansible
- Passwordless sudo for automation
- User-specific SSH keys

**Kubernetes Authentication**:
- Client certificates for kubectl/TUI
- Service account tokens for pods
- RBAC for authorization

**Tailscale Authentication**:
- SSO integration (Google, GitHub, etc.)
- Per-device authentication
- ACLs for network access control

### Network Security

**Encryption**:
- All Tailscale traffic encrypted with WireGuard
- Kubernetes API over TLS
- etcd encryption at rest (optional)

**Isolation**:
- Tailscale provides network isolation
- Kubernetes namespaces for logical isolation
- Network policies for pod-to-pod restrictions (optional)

**Firewall**:
- Only required ports open on nodes
- Tailscale interface allowed
- Public interfaces can be restricted

### Secrets Management

**Options**:
1. **Ansible Vault**: Encrypt sensitive inventory variables
2. **Kubernetes Secrets**: Base64-encoded secrets in etcd
3. **SOPS**: Encrypted secrets in Git
4. **Sealed Secrets**: Encrypted secrets managed by controller
5. **External Secrets**: Integration with external secret stores

## Design Decisions

### Why K3s Instead of Full Kubernetes?

**Advantages**:
- Single binary installation (simpler automation)
- Lower resource footprint (better for workstations)
- Built-in components (Traefik, local-path-provisioner)
- Optimized for edge/IoT deployments
- Full Kubernetes API compatibility

**Trade-offs**:
- Less flexibility in component selection
- SQLite default (not suitable for large HA clusters)
- Some features require additional configuration

### Why Tailscale Instead of Traditional VPN?

**Advantages**:
- Zero-configuration mesh networking
- Automatic NAT traversal (no port forwarding)
- Encrypted by default (WireGuard)
- Works across different networks
- Simple authentication (SSO)
- Stable IP addresses

**Trade-offs**:
- Requires Tailscale account
- Dependency on Tailscale coordination server
- Limited to Tailscale network size limits

### Why Ansible Instead of Other Tools?

**Advantages**:
- Agentless (SSH-based)
- Idempotent by design
- Large ecosystem of modules
- Human-readable YAML
- Good for heterogeneous environments

**Trade-offs**:
- Slower than agent-based tools
- Limited real-time state management
- Requires SSH access

### Why Flux CD for GitOps?

**Advantages**:
- Kubernetes-native (runs in cluster)
- Pull-based model (more secure)
- Supports Kustomize and Helm
- Active development and community
- CNCF project

**Trade-offs**:
- Requires Git repository
- Learning curve for GitOps concepts
- Sync interval delay (default 1 minute)

## Scalability

### Current Limitations

- **Single Control Plane**: Not HA by default
- **SQLite Backend**: Limited to single control plane
- **Tailscale**: Network size limits (varies by plan)
- **Resource Reservations**: Manual configuration per node

### Scaling Strategies

**Horizontal Scaling** (Add more nodes):
```bash
# Add worker nodes
cluster-mgr add-node worker-N <ip> --role worker
cluster-mgr provision --limit worker-N
```

**Vertical Scaling** (Increase node resources):
- Adjust resource reservations in inventory
- Re-run provisioning to apply changes

**Control Plane HA**:
1. Add multiple control plane nodes to inventory
2. Configure external load balancer or Tailscale LB
3. Switch to embedded etcd (automatic with 3+ control planes)
4. Update worker nodes to use LB endpoint

### Performance Considerations

**Network**:
- Tailscale adds ~10-20ms latency
- Bandwidth limited by slowest link
- Direct connections when possible

**Storage**:
- Local storage by default (node-local)
- Consider distributed storage for HA (Longhorn, Rook)

**Compute**:
- Resource reservations reduce available capacity
- GPU sharing increases utilization
- Pod density limited by node resources

## High Availability

### Current State

- Single control plane (not HA)
- Worker nodes can fail without cluster failure
- GitOps continues from last known state

### HA Implementation

**Control Plane HA**:
```yaml
# Add multiple control plane nodes
control_plane:
  hosts:
    control-1:
      ansible_host: 100.64.0.5
      tailscale_ip: 100.64.0.5
    control-2:
      ansible_host: 100.64.0.6
      tailscale_ip: 100.64.0.6
    control-3:
      ansible_host: 100.64.0.7
      tailscale_ip: 100.64.0.7
```

**Load Balancer Options**:
1. External LB (HAProxy, nginx)
2. Tailscale load balancing
3. DNS round-robin (simple but not recommended)

**etcd Considerations**:
- Automatic with 3+ control planes
- Requires odd number of nodes (3, 5, 7)
- Quorum required for writes

### Disaster Recovery

**Backup**:
```bash
# Backup control plane data
sudo tar czf k3s-backup.tar.gz /var/lib/rancher/k3s/server/db/
```

**Restore**:
```bash
# On new control plane
sudo systemctl stop k3s
sudo tar xzf k3s-backup.tar.gz -C /
sudo systemctl start k3s
```

**GitOps Recovery**:
- All application state in Git
- Re-bootstrap Flux to restore applications
- Automatic reconciliation

## See Also

- [README.md](../README.md) - Project overview
- [Design Document](../.kiro/specs/tailscale-k8s-cluster/design.md) - Detailed design
- [CLI Reference](CLI_REFERENCE.md) - Command documentation
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues
