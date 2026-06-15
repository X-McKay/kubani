# Ansible Roles

This directory contains reusable Ansible roles for cluster components.

## Roles

### prerequisites
System preparation and validation:
- Verify Tailscale installation and connectivity
- Install system dependencies
- Configure firewall rules
- Validate node requirements

### k3s_control_plane
Control plane node setup:
- Install K3s server
- Configure API server with Tailscale IP
- Generate and distribute kubeconfig
- Extract join token for workers

### k3s_worker
Worker node setup:
- Install K3s agent
- Join cluster using control plane Tailscale IP
- Configure resource reservations
- Apply node labels and taints

### gpu_support
NVIDIA GPU support:
- Install NVIDIA drivers (conditional)
- Deploy NVIDIA device plugin
- Configure GPU time-slicing
- Validate GPU availability

### gitops
GitOps host tooling and explicit Flux bootstrap:
- Install or validate the Flux CLI on the control plane host
- Create missing Flux controllers only during explicit bootstrap runs
- Create or repair root Flux GitOps objects only during explicit bootstrap or repair runs
- Fail on Flux CLI, controller, or root-object drift unless an explicit upgrade or repair flag is set

## Role Structure

Each role follows standard Ansible structure:
```
role_name/
├── tasks/
│   └── main.yml
├── handlers/
│   └── main.yml
├── templates/
├── files/
├── vars/
│   └── main.yml
├── defaults/
│   └── main.yml
└── README.md
```
