# GPU Support Role

This Ansible role installs and configures NVIDIA GPU support for Kubernetes nodes with GPUs.

## Requirements

- Node must have NVIDIA GPU hardware
- K3s must be installed and running on the node
- Internet connectivity for downloading NVIDIA drivers and device plugin

## Role Variables

### Optional Variables

- `nvidia_driver_version`: NVIDIA driver version to install (default: auto-detect latest)
- `nvidia_device_plugin_version`: NVIDIA device plugin version (default: v0.14.3)
- `gpu_time_slicing_enabled`: Enable GPU time-slicing for sharing (default: true)
- `gpu_time_slicing_replicas`: Number of virtual GPU replicas per physical GPU (default: 4)
- `skip_driver_install`: Skip NVIDIA driver installation if already present (default: true)

## Dependencies

- k3s_worker or k3s_control_plane role (K3s must be installed)

## Example Playbook

```yaml
- hosts: gpu_nodes
  roles:
    - role: gpu_support
      vars:
        gpu_time_slicing_enabled: true
        gpu_time_slicing_replicas: 4
```

## Tags

- `gpu`: All GPU-related tasks
- `nvidia-driver`: NVIDIA driver installation
- `device-plugin`: NVIDIA device plugin deployment
- `time-slicing`: GPU time-slicing configuration

## Notes

- This role only runs on nodes with `gpu: true` in inventory
- Driver installation is skipped if drivers are already present
- GPU time-slicing allows multiple pods to share a single GPU
- The role validates GPU availability after installation

## GPU Time-Slicing

Time-slicing allows multiple workloads to share a single GPU by time-multiplexing. This is useful for:
- Development and testing workloads
- Inference workloads with low GPU utilization
- Maximizing GPU utilization on resource-constrained nodes

Note: Time-slicing does not provide memory isolation between workloads.
