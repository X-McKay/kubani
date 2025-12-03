# Prerequisites Role

This Ansible role prepares nodes for Kubernetes cluster deployment by validating Tailscale connectivity, installing system dependencies, and configuring firewall rules.

## Requirements

- Tailscale must be installed and authenticated on all nodes before running this role
- Nodes must be running a supported Linux distribution (Debian/Ubuntu or RedHat/CentOS)
- Ansible 2.9 or higher
- Root or sudo access on target nodes

## Role Variables

### Tailscale Configuration

- `tailscale_network`: Tailscale network CIDR (default: `100.64.0.0/10`)
- `tailscale_status_timeout`: Timeout for Tailscale status checks (default: `10`)

### System Dependencies

- `system_packages`: List of required system packages
  - Default includes: curl, apt-transport-https, ca-certificates, software-properties-common, gnupg, lsb-release

### Firewall Configuration

- `manage_firewall`: Enable/disable firewall management (default: `true`)
- `firewall_backend`: Firewall backend to use (`ufw` or `firewalld`, auto-detected based on OS)

### Kubernetes Ports

The role automatically configures firewall rules for:

**Control Plane Ports:**
- 6443/tcp - Kubernetes API server
- 2379-2380/tcp - etcd server
- 10250/tcp - Kubelet API
- 10259/tcp - kube-scheduler
- 10257/tcp - kube-controller-manager

**Worker Node Ports:**
- 10250/tcp - Kubelet API
- 30000-32767/tcp - NodePort Services

**CNI Ports (Flannel):**
- 8472/udp - Flannel VXLAN
- 8285/udp - Flannel UDP backend

## Dependencies

This role requires the following Ansible collections:
- `ansible.posix`
- `community.general`

Install them with:
```bash
ansible-galaxy collection install ansible.posix community.general
```

## Example Playbook

```yaml
- hosts: all
  become: yes
  roles:
    - role: prerequisites
      vars:
        manage_firewall: true
        firewall_backend: ufw
```

## Tasks Overview

### 1. Tailscale Validation
- Verifies Tailscale is installed
- Checks authentication status
- Validates Tailscale IP matches inventory
- Ensures node is connected to Tailscale network

### 2. System Dependencies
- Updates package cache
- Installs required system packages
- Disables swap (required for Kubernetes)
- Enables IP forwarding
- Configures bridge networking

### 3. Firewall Configuration
- Installs and configures firewall (UFW or firewalld)
- Opens required Kubernetes ports
- Allows traffic from Tailscale network
- Configures role-specific ports (control plane vs worker)

### 4. Reachability Validation
- Tests connectivity to own Tailscale IP
- Validates reachability to control plane (from workers)
- Tests Tailscale peer connectivity
- Reports connectivity status

## Tags

The role supports the following tags:
- `tailscale` - Run only Tailscale validation tasks
- `validation` - Run validation tasks
- `dependencies` - Run system dependencies installation
- `packages` - Run package installation tasks
- `firewall` - Run firewall configuration tasks
- `networking` - Run networking configuration tasks
- `reachability` - Run reachability validation tasks

Example usage:
```bash
ansible-playbook playbook.yml --tags "tailscale,validation"
```

## Error Handling

The role will fail with descriptive error messages if:
- Tailscale is not installed
- Tailscale is not authenticated
- Tailscale IP doesn't match inventory
- Required packages cannot be installed
- Firewall configuration fails

## Testing

This role includes property-based tests to verify:
- Tailscale validation on all nodes (Property 5)
- Node reachability validation (Property 6)

Run tests with:
```bash
pytest tests/properties/test_prerequisites.py
```

## License

MIT

## Author Information

Created for the Tailscale Kubernetes Cluster project.
