# GitOps Role

This role manages the Ansible-owned side of GitOps:

- installs or validates the Flux CLI on the control plane host
- optionally bootstraps Flux controllers
- optionally creates or repairs the root Flux `GitRepository` and
  `Kustomization`

Normal cluster provisioning does not bootstrap Flux controllers or repair root
objects. Those actions are intentionally explicit so Ansible does not silently
rewrite GitOps state during routine host reconciliation.

## Requirements

- K3s control plane must be running
- kubectl must be available
- Git repository for GitOps manifests
- Flux authentication secret already present when `git_secret_ref` is set

## Role Variables

See `defaults/main.yml` for all available variables.

### Git Repository

- `git_repo_url`: Git repository URL for GitOps manifests
- `git_branch`: Git branch to monitor
- `git_secret_ref`: optional secret name referenced by the root
  `GitRepository`
- `git_repository_interval`: root source reconciliation interval
- `git_path`: repository path used by the root `Kustomization`

### Flux CLI

- `flux_cli_version`: Flux CLI version to install on the host
- `flux_cli_install_dir`: host install directory
- `flux_cli_allow_upgrade`: explicitly allow CLI version changes
- `flux_cli_arch`: archive architecture, derived from `ansible_architecture`

The role fails on CLI version drift unless `flux_cli_allow_upgrade=true`.

### Flux Controllers

- `gitops_bootstrap_enabled`: enable controller/root bootstrap tasks
- `flux_controller_version`: Flux controller version to install
- `gitops_allow_flux_upgrade`: explicitly allow controller version changes
- `flux_namespace`: Kubernetes namespace for Flux controllers
- `flux_components`: Flux components to install

The role creates missing controllers when bootstrap is enabled. Existing
controller version drift fails unless `gitops_allow_flux_upgrade=true`.

### Root Bootstrap Objects

- `gitops_root_kustomization`: root Kustomization name
- `gitops_root_interval`: root Kustomization interval
- `gitops_root_prune`: root Kustomization prune setting
- `gitops_allow_bootstrap_repair`: explicitly allow root-object repair

The role creates missing root objects when bootstrap is enabled. Existing root
object drift fails unless `gitops_allow_bootstrap_repair=true`.

## Dependencies

- k3s_control_plane role must be executed first

## Example Playbook

```yaml
- hosts: control_plane
  roles:
    - role: gitops
      vars:
        gitops_bootstrap_enabled: true
        git_repo_url: "ssh://git@github.com/X-McKay/kubani"
        git_branch: "main"
```

## Operational Commands

```bash
just bootstrap-flux
just repair-flux-bootstrap
just upgrade-flux-cli
just upgrade-flux-controllers
```
