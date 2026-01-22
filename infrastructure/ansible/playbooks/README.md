# Ansible Playbooks

This directory contains Ansible playbooks for cluster operations.

## Playbooks

- **site.yml** - Main entry point for cluster provisioning
- **provision_cluster.yml** - Initial cluster provisioning with pre-flight checks
- **add_node.yml** - Add new nodes to existing cluster
- **update_cluster.yml** - Update cluster configuration and components (to be implemented)

## Usage

Run playbooks using ansible-playbook:

```bash
# Provision entire cluster
ansible-playbook playbooks/site.yml

# Add a new node
ansible-playbook playbooks/add_node.yml --limit new-node

# Check mode (dry run)
ansible-playbook playbooks/site.yml --check

# Use specific tags
ansible-playbook playbooks/site.yml --tags prerequisites,k3s
```

## Tags

Common tags used across playbooks:
- `prerequisites` - System preparation
- `k3s` - Kubernetes installation
- `networking` - Network configuration
- `storage` - Storage configuration
- `gpu` - GPU support
- `gitops` - GitOps setup
