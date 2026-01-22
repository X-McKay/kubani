# Ansible Roles

This directory contains reusable Ansible roles for cluster components.

## Roles

Roles will be implemented in subsequent tasks:

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
Flux CD installation:
- Install Flux CLI
- Bootstrap Flux to cluster
- Configure Git repository monitoring
- Create GitOps directory structure

### monitoring (optional)
Monitoring stack:
- Deploy Prometheus
- Deploy Grafana
- Configure node exporters
- Set up dashboards

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
