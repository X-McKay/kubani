# K3s Control Plane Role

This Ansible role installs and configures K3s as a Kubernetes control plane node with Tailscale networking integration.

## Requirements

- Tailscale must be installed and authenticated on the target node
- Target node must be reachable via its Tailscale IP address
- Root or sudo access on the target node
- Prerequisites role must be run first

## Role Variables

### Required Variables

- `tailscale_ip`: The Tailscale IP address of the control plane node

### Optional Variables

- `k3s_version`: K3s version to install (default: `v1.28.5+k3s1`)
- `cluster_name`: Name of the cluster (default: `homelab`)
- `cluster_cidr`: Pod network CIDR (default: `10.42.0.0/16`)
- `service_cidr`: Service network CIDR (default: `10.43.0.0/16`)
- `api_server_port`: Kubernetes API server port (default: `6443`)
- `node_labels`: Dictionary of labels to apply to the node
- `node_taints`: List of taints to apply to the node

### Advanced Variables

See `defaults/main.yml` for a complete list of configurable variables.

## Dependencies

- `prerequisites` role (for Tailscale validation and system dependencies)

## Example Playbook

```yaml
- hosts: control_plane
  roles:
    - role: prerequisites
    - role: k3s_control_plane
```

## Example Inventory

```yaml
control_plane:
  hosts:
    nuc:
      ansible_host: 100.64.0.1
      tailscale_ip: 100.64.0.1
      node_labels:
        node-role: control-plane
```

## Tasks Overview

1. **Install**: Downloads and installs K3s server with Tailscale configuration
2. **Configure**: Sets up K3s configuration and applies node labels/taints
3. **Kubeconfig**: Generates and fetches kubeconfig with Tailscale IP
4. **Join Token**: Extracts and stores the join token for worker nodes

## Handlers

- `restart k3s`: Restarts the K3s service
- `reload k3s`: Reloads the K3s service configuration
- `enable k3s`: Enables the K3s service to start on boot

## Tags

- `install`: K3s installation tasks
- `configure`: K3s configuration tasks
- `kubeconfig`: Kubeconfig management tasks
- `join_token`: Join token extraction tasks
- `k3s`: All K3s-related tasks
- `credentials`: Credential management tasks

## Post-Installation

After running this role:

1. The kubeconfig file will be available at `/tmp/{{ cluster_name }}-kubeconfig` on the Ansible controller
2. The join token and control plane URL will be stored in hostvars for worker nodes to use
3. The Kubernetes API server will be accessible at `https://{{ tailscale_ip }}:6443`

## Verification

To verify the installation:

```bash
# On the control plane node
sudo k3s kubectl get nodes

# From the Ansible controller (using fetched kubeconfig)
export KUBECONFIG=/tmp/{{ cluster_name }}-kubeconfig
kubectl get nodes
```

## License

MIT

## Author Information

Generated for Tailscale Kubernetes Cluster project
