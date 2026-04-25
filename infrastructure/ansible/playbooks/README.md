# Playbooks

- `preflight_checks.yml` validates inventory and host prerequisites
- `setup_ssh.yml` helps bootstrap SSH access
- `bootstrap_node.yml` prepares a single host before joining it to the cluster
- `add_node.yml` joins a new host to an existing cluster
- `provision_cluster.yml` is the main provisioning entry point
- `site.yml` is the full orchestration entry point

Typical usage from the repo root:

```bash
uv run ansible-playbook \
  -i infrastructure/ansible/inventory/hosts.yml \
  infrastructure/ansible/playbooks/provision_cluster.yml
```
