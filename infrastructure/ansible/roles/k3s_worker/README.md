# K3s Worker Role

This Ansible role installs and configures K3s agent on worker nodes to join an existing Kubernetes cluster.

## Requirements

- Tailscale must be installed and authenticated on the node
- Control plane node must be provisioned and running
- Join token must be available from control plane

## Role Variables

### Required Variables

- `tailscale_ip`: The Tailscale IP address of this worker node
- `k3s_control_plane_url`: URL of the control plane API server (e.g., https://100.64.0.1:6443)
- `k3s_join_token`: Token for joining the cluster (obtained from control plane)

### Optional Variables

- `k3s_version`: K3s version to install (default: v1.28.5+k3s1)
- `reserved_cpu`: CPU cores to reserve for system/user processes (default: "1")
- `reserved_memory`: Memory to reserve for system/user processes (default: "2Gi")
- `node_labels`: Dictionary of labels to apply to the node
- `node_taints`: List of taints to apply to the node

## Dependencies

- prerequisites role (for Tailscale validation)

## Example Playbook

```yaml
- hosts: workers
  roles:
    - role: k3s_worker
      vars:
        k3s_control_plane_url: "{{ hostvars[groups['control_plane'][0]]['k3s_control_plane_url'] }}"
        k3s_join_token: "{{ hostvars[groups['control_plane'][0]]['k3s_join_token'] }}"
```

## Tags

- `install`: K3s installation tasks
- `configure`: K3s configuration tasks
- `k3s`: All K3s related tasks

## Notes

- This role configures resource reservations to maintain workstation usability
- Node labels and taints are applied after the node joins the cluster
- The role is idempotent and can be safely re-run
