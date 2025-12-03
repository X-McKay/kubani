# GitOps Role

This role installs and configures Flux CD for GitOps-based application deployment.

## Requirements

- K3s control plane must be running
- kubectl must be available
- Git repository for GitOps manifests

## Role Variables

See `defaults/main.yml` for all available variables.

### Required Variables

- `git_repo_url`: Git repository URL for GitOps manifests
- `git_branch`: Git branch to monitor (default: main)

### Optional Variables

- `flux_version`: Flux CLI version to install
- `flux_namespace`: Kubernetes namespace for Flux controllers
- `flux_components`: Flux components to install

## Dependencies

- k3s_control_plane role must be executed first

## Example Playbook

```yaml
- hosts: control_plane
  roles:
    - role: gitops
      vars:
        git_repo_url: "https://github.com/user/repo.git"
        git_branch: "main"
```

## Tags

- `gitops`: All GitOps tasks
- `flux`: Flux installation tasks
- `bootstrap`: Flux bootstrap tasks
