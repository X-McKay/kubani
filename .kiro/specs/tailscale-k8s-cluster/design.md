# Design Document

## Overview

The Tailscale Kubernetes Cluster system is an infrastructure automation solution that provisions and manages a multi-node Kubernetes cluster across heterogeneous hardware connected via Tailscale VPN. The system consists of three main components:

1. **Ansible Automation Layer**: Idempotent playbooks and roles that provision Kubernetes components, configure networking, and manage node lifecycle
2. **Management CLI/TUI**: Python-based tools built with Typer and Rich/Textual for cluster administration and monitoring
3. **GitOps Integration**: Flux CD controller that synchronizes cluster state with a Git repository

The design prioritizes ease of use, reproducibility, and the ability to maintain nodes as functional workstations while participating in the cluster.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Repository                          │
│  ├── ansible/                                               │
│  │   ├── inventory/                                         │
│  │   ├── playbooks/                                         │
│  │   └── roles/                                             │
│  ├── gitops/                                                │
│  │   ├── apps/                                              │
│  │   └── infrastructure/                                    │
│  └── cli/                                                   │
│      └── cluster_manager/                                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  Management Workstation                      │
│  ├── CLI Tool (Typer)                                       │
│  ├── TUI (Textual)                                          │
│  ├── Ansible                                                │
│  └── kubectl                                                │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Tailscale Network   │
              └───────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Desktop    │  │     NUC      │  │  DGX Spark   │
│ (Worker/CP)  │  │  (Worker/CP) │  │   (Worker)   │
│              │  │              │  │              │
│ K8s + Local  │  │ K8s + Local  │  │ K8s + Local  │
│ Workstation  │  │ Workstation  │  │ GPU Work     │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
              ┌───────────────────────┐
              │   Flux CD Controller  │
              │  (GitOps Sync)        │
              └───────────────────────┘
```

### Technology Stack

- **Kubernetes Distribution**: K3s (lightweight, suitable for edge/hybrid deployments)
- **VPN**: Tailscale (mesh networking, NAT traversal)
- **Automation**: Ansible (infrastructure as code)
- **GitOps**: Flux CD (Kubernetes-native GitOps)
- **CLI Framework**: Typer (Python CLI with type hints)
- **TUI Framework**: Textual (modern Python TUI framework)
- **Package Management**: UV (fast Python package manager)
- **Runtime Management**: Mise (polyglot runtime manager)
- **Container Runtime**: containerd (included with K3s)

### Network Architecture

All cluster communication occurs over Tailscale IPs:
- API Server: Exposed on control plane node's Tailscale IP
- Pod Network: Flannel CNI with Tailscale as underlay
- Service Network: ClusterIP services accessible within cluster
- Ingress: Optional Traefik ingress controller (included with K3s)

## Components and Interfaces

### 1. Ansible Automation Layer

#### Directory Structure
```
ansible/
├── inventory/
│   ├── hosts.yml                 # Main inventory file
│   └── group_vars/
│       ├── all.yml              # Global variables
│       ├── control_plane.yml    # Control plane specific
│       └── workers.yml          # Worker node specific
├── playbooks/
│   ├── site.yml                 # Main playbook
│   ├── provision_cluster.yml    # Initial cluster setup
│   ├── add_node.yml            # Add new node
│   └── update_cluster.yml      # Update existing cluster
└── roles/
    ├── prerequisites/          # System prep, Tailscale check
    ├── k3s_control_plane/     # Control plane installation
    ├── k3s_worker/            # Worker node installation
    ├── gpu_support/           # NVIDIA device plugin
    ├── gitops/                # Flux CD installation
    └── monitoring/            # Optional monitoring stack
```

#### Key Roles

**prerequisites**
- Tasks: Verify Tailscale connectivity, install dependencies, configure firewall
- Variables: `tailscale_network`, `required_packages`
- Handlers: Restart networking services

**k3s_control_plane**
- Tasks: Install K3s server, configure API server with Tailscale IP, generate kubeconfig
- Variables: `k3s_version`, `api_server_ip`, `cluster_cidr`
- Handlers: Restart K3s service

**k3s_worker**
- Tasks: Install K3s agent, join cluster, configure resource reservations
- Variables: `control_plane_url`, `join_token`, `reserved_cpu`, `reserved_memory`
- Handlers: Restart K3s agent

**gpu_support**
- Tasks: Install NVIDIA drivers, deploy device plugin, configure runtime
- Variables: `nvidia_driver_version`, `gpu_sharing_enabled`
- Conditions: Only runs on nodes with `gpu: true` label

**gitops**
- Tasks: Install Flux CLI, bootstrap Flux to cluster, configure Git repository
- Variables: `git_repo_url`, `git_branch`, `flux_namespace`

#### Inventory Schema

```yaml
all:
  vars:
    k3s_version: v1.28.5+k3s1
    cluster_name: homelab
    tailscale_network: 100.64.0.0/10
  children:
    control_plane:
      hosts:
        nuc:
          ansible_host: 100.x.x.1
          tailscale_ip: 100.x.x.1
          node_labels:
            node-role: control-plane
    workers:
      hosts:
        desktop:
          ansible_host: 100.x.x.2
          tailscale_ip: 100.x.x.2
          reserved_cpu: "2"
          reserved_memory: "4Gi"
          node_labels:
            node-role: worker
            workstation: "true"
        dgx-spark:
          ansible_host: 100.x.x.3
          tailscale_ip: 100.x.x.3
          reserved_cpu: "4"
          reserved_memory: "8Gi"
          gpu: true
          node_labels:
            node-role: worker
            gpu: "true"
            workstation: "true"
          node_taints:
            - key: nvidia.com/gpu
              value: "true"
              effect: NoSchedule
```

### 2. Management CLI

#### CLI Structure (Typer)

```python
# cluster_manager/cli.py
import typer
from typing import Optional

app = typer.Typer(name="cluster-mgr", help="Kubernetes cluster management CLI")

# Node management commands
@app.command()
def discover(
    network: str = "100.64.0.0/10",
    show_all: bool = False
):
    """Discover Tailscale nodes available for cluster membership."""
    pass

@app.command()
def add_node(
    hostname: str,
    role: str = typer.Option(..., help="control-plane or worker"),
    gpu: bool = False,
    reserved_cpu: Optional[str] = None,
    reserved_memory: Optional[str] = None
):
    """Add a discovered node to the Ansible inventory."""
    pass

@app.command()
def remove_node(hostname: str, drain: bool = True):
    """Remove a node from the cluster and inventory."""
    pass

# Configuration commands
@app.command()
def config_set(key: str, value: str, scope: str = "all"):
    """Update Ansible configuration variables."""
    pass

@app.command()
def config_get(key: str, scope: str = "all"):
    """Retrieve Ansible configuration values."""
    pass

# Cluster operations
@app.command()
def provision(
    check: bool = False,
    tags: Optional[str] = None
):
    """Run Ansible playbook to provision the cluster."""
    pass

@app.command()
def status():
    """Show cluster status and node health."""
    pass
```

#### CLI Implementation Details

- **Tailscale Discovery**: Uses `tailscale status --json` to enumerate network nodes
- **Inventory Management**: Parses and updates YAML inventory files using `ruamel.yaml`
- **Validation**: Checks for required fields, IP conflicts, and Tailscale connectivity
- **Ansible Integration**: Executes playbooks via `ansible-runner` library
- **Configuration**: Stores CLI preferences in `~/.config/cluster-manager/config.toml`

### 3. Terminal User Interface (TUI)

#### TUI Layout (Textual)

```
┌─────────────────────────────────────────────────────────────┐
│ Cluster: homelab                    [Q]uit [R]efresh [H]elp │
├─────────────────────────────────────────────────────────────┤
│ Nodes (3)                                                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Name       Role    Status  CPU    Memory   Tailscale IP │ │
│ │ nuc        CP      Ready   45%    2.1/8Gi  100.x.x.1    │ │
│ │ desktop    Worker  Ready   23%    4.5/12Gi 100.x.x.2    │ │
│ │ dgx-spark  Worker  Ready   67%    12/32Gi  100.x.x.3    │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ Services (5)                                                 │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Namespace   Name           Pods    Status               │ │
│ │ default     nginx          3/3     Running              │ │
│ │ monitoring  prometheus     1/1     Running              │ │
│ │ flux-system flux-cd        2/2     Running              │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ Events                                                       │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 2m ago: Pod nginx-abc123 started on desktop             │ │
│ │ 5m ago: Node dgx-spark joined cluster                   │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

#### TUI Implementation

- **Framework**: Textual (reactive TUI framework)
- **Data Source**: Kubernetes Python client (`kubernetes` library)
- **Refresh Rate**: Configurable (default 5 seconds)
- **Navigation**: Arrow keys, Tab, Enter for selection
- **Detail Views**: Press Enter on node/service for detailed information
- **Filtering**: Type to filter nodes/services by name

### 4. GitOps Integration

#### Repository Structure

```
gitops/
├── flux-system/
│   ├── gotk-components.yaml    # Flux controllers
│   └── gotk-sync.yaml          # Git sync configuration
├── infrastructure/
│   ├── sources/                # Helm repositories
│   ├── storage/                # Storage classes, PVs
│   └── networking/             # Ingress, network policies
└── apps/
    ├── base/                   # Base application configs
    │   └── nginx/
    │       ├── deployment.yaml
    │       ├── service.yaml
    │       └── kustomization.yaml
    └── overlays/               # Environment-specific overlays
        └── production/
```

#### Flux Configuration

- **Source Controller**: Monitors Git repository for changes
- **Kustomize Controller**: Applies Kustomize overlays
- **Helm Controller**: Manages Helm releases
- **Notification Controller**: Sends alerts on sync failures
- **Sync Interval**: 1 minute (configurable)
- **Prune**: Enabled (removes resources deleted from Git)

## Data Models

### Inventory Node Model

```python
from typing import Optional, Dict, List
from pydantic import BaseModel, IPvAnyAddress

class NodeTaint(BaseModel):
    key: str
    value: str
    effect: str  # NoSchedule, PreferNoSchedule, NoExecute

class Node(BaseModel):
    hostname: str
    ansible_host: str
    tailscale_ip: IPvAnyAddress
    role: str  # control-plane or worker
    reserved_cpu: Optional[str] = None
    reserved_memory: Optional[str] = None
    gpu: bool = False
    node_labels: Dict[str, str] = {}
    node_taints: List[NodeTaint] = []

    def to_inventory_dict(self) -> dict:
        """Convert to Ansible inventory format."""
        pass

    @classmethod
    def from_inventory_dict(cls, data: dict) -> "Node":
        """Parse from Ansible inventory format."""
        pass
```

### Cluster State Model

```python
from typing import List
from datetime import datetime

class PodStatus(BaseModel):
    name: str
    namespace: str
    node: str
    status: str
    restarts: int

class NodeStatus(BaseModel):
    name: str
    role: str
    status: str  # Ready, NotReady, Unknown
    cpu_usage: float
    memory_usage: float
    tailscale_ip: str
    kubelet_version: str
    last_heartbeat: datetime

class ClusterState(BaseModel):
    name: str
    nodes: List[NodeStatus]
    pods: List[PodStatus]
    api_server: str
    flux_status: str

    @classmethod
    def from_kubernetes_api(cls, api_client) -> "ClusterState":
        """Fetch current state from Kubernetes API."""
        pass
```

### Configuration Model

```python
class ClusterConfig(BaseModel):
    cluster_name: str
    k3s_version: str
    tailscale_network: str
    git_repo_url: str
    git_branch: str = "main"
    flux_namespace: str = "flux-system"

    def save(self, path: str):
        """Save configuration to YAML file."""
        pass

    @classmethod
    def load(cls, path: str) -> "ClusterConfig":
        """Load configuration from YAML file."""
        pass
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Complete component installation
*For any* valid Ansible inventory with specified nodes, when the provisioning playbook executes, all nodes in the inventory should have Kubernetes components installed and exactly one node should be configured as control plane with remaining nodes as workers.
**Validates: Requirements 1.1, 1.2**

### Property 2: Tailscale IP configuration consistency
*For any* node in the cluster, all Kubernetes networking configuration (API server endpoint, node addresses) should use the node's Tailscale IP address rather than any other network interface.
**Validates: Requirements 1.3, 2.2**

### Property 3: Credential distribution completeness
*For any* cluster provisioning operation, all nodes in the inventory should receive authentication credentials (kubeconfig, join tokens) upon successful completion.
**Validates: Requirements 1.4**

### Property 4: Error reporting completeness
*For any* provisioning error, the error message should contain both the node identifier and the specific step that failed.
**Validates: Requirements 1.5**

### Property 5: Tailscale validation on all nodes
*For any* playbook execution, the system should verify Tailscale installation and authentication status on every node before proceeding with Kubernetes installation.
**Validates: Requirements 2.1**

### Property 6: Node reachability validation
*For any* node joining the cluster, the system should validate that the node is reachable via its Tailscale IP address before completing the join operation.
**Validates: Requirements 2.4**

### Property 7: Node addition uses consistent provisioning
*For any* new node added to the Ansible inventory, the provisioning logic applied should be identical to the logic used for initial cluster nodes (same playbook, same roles).
**Validates: Requirements 3.1**

### Property 8: Minimal node definition requirements
*For any* node definition in the inventory, only hostname, Tailscale IP, and role should be required fields, with all other fields being optional.
**Validates: Requirements 3.3**

### Property 9: Configuration consistency across nodes
*For any* new node joining the cluster, the networking and storage configuration applied should match the configuration of existing nodes with the same role.
**Validates: Requirements 3.4**

### Property 10: Node readiness verification
*For any* completed node addition operation, the system should verify that the node reports "Ready" status in the cluster before considering the operation successful.
**Validates: Requirements 3.5**

### Property 11: Resource reservation configuration
*For any* node where Kubernetes is installed, the system should configure CPU and memory reservations to prevent Kubernetes from consuming all available resources.
**Validates: Requirements 4.1**

### Property 12: Worker node resource protection
*For any* node configured as a worker node, the system should apply labels or taints that prevent system pods from monopolizing node resources.
**Validates: Requirements 4.2**

### Property 13: GitOps controller installation
*For any* cluster provisioning operation, the system should install and configure a GitOps controller (Flux CD) as part of the provisioning process.
**Validates: Requirements 5.1**

### Property 14: GitOps repository configuration
*For any* GitOps controller installation, the controller should be configured to monitor the specified Git repository URL and branch for application manifests.
**Validates: Requirements 5.2**

### Property 15: Dependency format compliance
*For any* Python dependency added to the project, it should be documented in UV-compatible format (pyproject.toml) to ensure reproducible installations.
**Validates: Requirements 6.4**

### Property 16: Application directory isolation
*For any* set of applications in the GitOps repository, each application should be organized in a separate directory to maintain isolation.
**Validates: Requirements 7.5**

### Property 17: Playbook idempotency
*For any* Ansible playbook, executing it multiple times against the same inventory should produce the same cluster state without errors, with subsequent runs skipping tasks already in the desired state.
**Validates: Requirements 8.1, 8.4**

### Property 18: Node-specific configuration application
*For any* node with specific hardware attributes (GPU, storage capabilities, resource constraints), the system should apply appropriate configuration (device plugins, storage classes, resource limits) based on those attributes.
**Validates: Requirements 10.1, 10.2, 10.3, 10.5**

### Property 19: Tailscale node discovery
*For any* execution of the CLI discover command, the system should query the Tailscale network and return a list of available nodes with their hostnames, IP addresses, and cluster membership status.
**Validates: Requirements 11.2, 11.3**

### Property 20: Inventory update correctness
*For any* node added via the CLI, the Ansible inventory file should be updated to include the node's information in the correct format and location (control_plane or workers group).
**Validates: Requirements 11.4**

### Property 21: Configuration validation before write
*For any* configuration modification via the CLI, the system should validate the changes against the schema and reject invalid configurations before writing to files.
**Validates: Requirements 11.5**

### Property 22: TUI node information completeness
*For any* cluster state, the TUI should display all nodes with their role, status, CPU usage, memory usage, and Tailscale IP address.
**Validates: Requirements 12.1, 12.2**

### Property 23: TUI service information completeness
*For any* set of running services in the cluster, the TUI should display each service with its namespace, name, pod count, and health status.
**Validates: Requirements 12.3**

### Property 24: TUI state synchronization
*For any* change in cluster state (node status change, pod creation/deletion), the TUI should update its display to reflect the new state within the configured refresh interval.
**Validates: Requirements 12.4**

### Property 25: TUI keyboard navigation
*For any* TUI session, all documented keyboard shortcuts should be registered and should trigger their corresponding actions (view details, refresh, quit, etc.).
**Validates: Requirements 12.5**

## Error Handling

### Ansible Playbook Errors

**Pre-flight Validation Failures**
- Missing Tailscale installation: Fail with clear message and installation instructions
- Unreachable nodes: Report which nodes are unreachable via Tailscale
- Insufficient permissions: Report which privilege escalation failed and where

**Installation Failures**
- Package installation errors: Capture package manager output and report
- Service start failures: Include systemd journal logs in error output
- Network configuration errors: Report specific networking component that failed

**Recovery Strategy**
- All tasks should be idempotent to allow re-running after fixing issues
- Failed nodes should not prevent other nodes from completing
- State should be preserved to allow resuming from failure point

### CLI Tool Errors

**Input Validation Errors**
- Invalid IP addresses: Report format requirements
- Missing required fields: List all missing fields
- Conflicting configurations: Explain the conflict

**File Operation Errors**
- Permission denied: Report which file and suggest solutions
- File not found: Report expected location
- YAML parsing errors: Report line number and syntax issue

**Tailscale API Errors**
- Tailscale not running: Provide command to start service
- Authentication required: Provide authentication instructions
- Network timeout: Suggest checking connectivity

### TUI Errors

**Kubernetes API Errors**
- Connection refused: Display message and retry automatically
- Authentication failed: Prompt for kubeconfig path
- Timeout: Show loading indicator and retry

**Display Errors**
- Terminal too small: Show minimum size requirements
- Unsupported terminal: List supported terminal types

**Graceful Degradation**
- If metrics unavailable, show "N/A" instead of crashing
- If node unreachable, mark as "Unknown" status
- If refresh fails, keep displaying last known state

## Testing Strategy

### Unit Testing

The system will use pytest for unit testing Python components:

**CLI Module Tests**
- Test command parsing and validation
- Test inventory file parsing and generation
- Test configuration file updates
- Mock Tailscale API calls and Ansible execution

**TUI Module Tests**
- Test widget rendering with mock data
- Test keyboard event handling
- Test state updates
- Mock Kubernetes API calls

**Data Model Tests**
- Test Pydantic model validation
- Test serialization/deserialization
- Test inventory format conversion

**Ansible Role Tests**
- Use molecule for role testing
- Test task execution with different variables
- Test idempotency
- Test error conditions

### Property-Based Testing

The system will use Hypothesis for property-based testing in Python:

**Configuration Requirements**
- Minimum 100 iterations per property test
- Use appropriate strategies for generating test data (IP addresses, hostnames, etc.)
- Each property test must reference its corresponding design property

**Test Organization**
- Property tests in `tests/properties/` directory
- Each test file corresponds to a component (inventory, cli, tui, etc.)
- Use descriptive test names that reference property numbers

**Example Property Test Structure**
```python
from hypothesis import given, strategies as st
import pytest

@given(
    nodes=st.lists(
        st.builds(Node,
            hostname=st.text(min_size=1, max_size=63),
            tailscale_ip=st.ip_addresses(v=4),
            role=st.sampled_from(['control-plane', 'worker'])
        ),
        min_size=1,
        max_size=10
    )
)
def test_property_1_complete_component_installation(nodes):
    """
    Feature: tailscale-k8s-cluster, Property 1: Complete component installation

    For any valid Ansible inventory with specified nodes, when the provisioning
    playbook executes, all nodes should have Kubernetes components installed.
    """
    inventory = create_inventory(nodes)
    result = provision_cluster(inventory)  # Mock or integration

    assert all(node.has_kubernetes_installed() for node in result.nodes)
    control_plane_count = sum(1 for n in result.nodes if n.role == 'control-plane')
    assert control_plane_count == 1
```

### Integration Testing

**Cluster Provisioning Tests**
- Use Vagrant or Docker to create test VMs
- Test full provisioning workflow
- Verify cluster functionality
- Test node addition and removal

**GitOps Integration Tests**
- Deploy test applications via GitOps
- Verify synchronization
- Test update and delete operations

**End-to-End Tests**
- Test complete workflow from CLI to deployed application
- Verify TUI displays correct information
- Test error recovery scenarios

### Test Execution

**Local Development**
- Unit tests: `pytest tests/unit`
- Property tests: `pytest tests/properties`
- Integration tests: `pytest tests/integration` (requires test environment)

**CI/CD Pipeline**
- Run unit and property tests on every commit
- Run integration tests on pull requests
- Use GitHub Actions or similar

**Test Coverage**
- Target 80% code coverage for Python modules
- Focus on critical paths and error handling
- Use `pytest-cov` for coverage reporting

## Implementation Notes

### K3s vs K8s

K3s is chosen over full Kubernetes for several reasons:
- Smaller resource footprint (important for workstation nodes)
- Single binary installation (simpler Ansible automation)
- Built-in Traefik ingress controller
- Optimized for edge/IoT deployments
- Full Kubernetes API compatibility

### Tailscale Integration

Tailscale provides several advantages:
- Automatic NAT traversal (nodes can be on different networks)
- Encrypted mesh networking
- Simple authentication via SSO
- No need for port forwarding or VPN server setup
- Works across firewalls and NAT

### Resource Reservations

To maintain workstation usability:
- Reserve at least 2 CPU cores for system/user processes
- Reserve at least 4GB RAM for system/user processes
- Use kubelet flags: `--system-reserved` and `--kube-reserved`
- Apply taints to prevent pod scheduling on workstation nodes by default
- Use node affinity to explicitly schedule workloads on workstation nodes

### GPU Sharing

For DGX Spark GPU access:
- Install NVIDIA device plugin for Kubernetes
- Configure time-slicing for GPU sharing
- Use resource limits to prevent single pod from monopolizing GPU
- Maintain direct CUDA access for local applications
- Consider using MIG (Multi-Instance GPU) if supported

### GitOps Repository Structure

Recommended structure:
- Separate infrastructure and applications
- Use Kustomize for environment-specific overlays
- Store secrets encrypted with SOPS or sealed-secrets
- Use Flux image automation for automatic updates
- Implement branch-based environments (main = production)

### Development Workflow

1. Clone repository
2. Install mise: `curl https://mise.run | sh`
3. Install tools: `mise install`
4. Install dependencies: `uv sync`
5. Activate environment: `mise shell`
6. Configure inventory: Edit `ansible/inventory/hosts.yml`
7. Run provisioning: `cluster-mgr provision`
8. Monitor cluster: `cluster-mgr tui`

### Security Considerations

- Store sensitive variables in Ansible Vault
- Use RBAC for cluster access control
- Implement network policies for pod-to-pod communication
- Enable audit logging on API server
- Regularly update K3s and system packages
- Use Tailscale ACLs to restrict node access
- Rotate join tokens periodically

### Monitoring and Observability

Optional monitoring stack (via GitOps):
- Prometheus for metrics collection
- Grafana for visualization
- Loki for log aggregation
- Node exporter for node metrics
- kube-state-metrics for cluster metrics

### Backup and Disaster Recovery

- K3s stores state in SQLite by default (easy to backup)
- Backup `/var/lib/rancher/k3s/server/db/` on control plane
- Store backups in Git LFS or external storage
- Document recovery procedure
- Test recovery process regularly

### Scaling Considerations

- Current design supports single control plane
- For HA, add multiple control plane nodes with embedded etcd
- Use external load balancer for API server (or Tailscale load balancing)
- Consider resource limits as cluster grows
- Monitor Tailscale bandwidth usage

### Future Enhancements

- Support for multiple control plane nodes (HA)
- Automatic backup scheduling
- Integration with external storage (NFS, Ceph)
- Support for ARM nodes (Raspberry Pi)
- Web UI in addition to TUI
- Metrics and alerting integration
- Automatic certificate rotation
- Support for other Kubernetes distributions (k0s, microk8s)
