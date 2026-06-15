# Ansible Automation

Ansible is the host-level control plane for the Kubani homelab cluster.

## What It Owns

- bootstrap prerequisites
- K3s control plane and worker installation
- node labels and topology metadata
- GPU node preparation
- Flux CLI host tooling
- explicit Flux controller and root GitOps bootstrap

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
just upgrade-k3s
just bootstrap-flux
just repair-flux-bootstrap
just upgrade-flux-cli
just upgrade-flux-controllers
just provision-host strix
```

Direct invocation also works:

```bash
uv run ansible-playbook \
  -i infrastructure/ansible/inventory/hosts.yml \
  infrastructure/ansible/playbooks/provision_cluster.yml
```

K3s version changes are intentionally not applied by normal provisioning. Use
`just upgrade-k3s` during a planned maintenance window after updating
`k3s_version` in inventory.

Flux bootstrap is also explicit. Normal provisioning installs or validates the
Flux CLI on the control plane host, but it does not install controllers or
rewrite the root `GitRepository`/`Kustomization`. Use `just bootstrap-flux` for
initial bootstrap, `just repair-flux-bootstrap` for intentional root-object
repair, and the Flux upgrade commands only during planned maintenance.
