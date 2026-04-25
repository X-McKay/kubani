# Ansible Automation

Ansible is the host-level control plane for the Kubani homelab cluster.

## What It Owns

- bootstrap prerequisites
- K3s control plane and worker installation
- node labels and topology metadata
- GPU node preparation
- Flux bootstrap and related host configuration

## Inventory

Start from the examples in `inventory/`:

```bash
cp infrastructure/ansible/inventory/hosts.yml.example infrastructure/ansible/inventory/hosts.yml
cp infrastructure/ansible/inventory/group_vars/all.yml.example infrastructure/ansible/inventory/group_vars/all.yml
```

## Running Playbooks

From the repo root:

```bash
just ansible-deps
just inventory
just ansible-ping
just provision
just provision-host strix
```

Direct invocation also works:

```bash
uv run ansible-playbook \
  -i infrastructure/ansible/inventory/hosts.yml \
  infrastructure/ansible/playbooks/provision_cluster.yml
```
