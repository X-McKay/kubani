# GPU Node Configuration Guide

This guide explains how to configure and use NVIDIA GPU nodes in your Kubernetes cluster.

## Overview

The cluster system supports NVIDIA GPUs through the NVIDIA device plugin for Kubernetes. This enables:
- GPU resource scheduling and allocation
- GPU time-slicing for sharing GPUs across multiple pods
- Automatic GPU driver installation (optional)
- GPU workload isolation with taints and tolerations

## Prerequisites

### Hardware Requirements

- NVIDIA GPU (GeForce, Quadro, Tesla, or A-series)
- Sufficient PCIe power and cooling
- Minimum 8GB system RAM (16GB+ recommended)
- 4+ CPU cores recommended

### Software Requirements

- Ubuntu 20.04+ or compatible Linux distribution
- Kernel headers installed: `sudo apt install linux-headers-$(uname -r)`
- Secure Boot disabled (or MOK keys configured for NVIDIA drivers)

## Quick Start

### 1. Add GPU Node to Inventory

Edit `ansible/inventory/hosts.yml`:

```yaml
workers:
  hosts:
    gpu-node:
      ansible_host: 100.64.0.30
      tailscale_ip: 100.64.0.30
      reserved_cpu: "4"
      reserved_memory: "8Gi"
      gpu: true
      node_labels:
        node-role: worker
        gpu: "true"
        gpu-type: nvidia
        workstation: "true"
      node_taints:
        - key: nvidia.com/gpu
          value: "true"
          effect: NoSchedule
```

### 2. Configure GPU Settings

Edit `ansible/inventory/group_vars/workers.yml`:

```yaml
# GPU configuration (only applies to nodes with gpu: true)
nvidia_driver_version: "535"  # LTS driver version
nvidia_device_plugin_version: "v0.14.3"
gpu_time_slicing_enabled: true
gpu_replicas: 4  # Number of time-sliced GPU instances
```

### 3. Provision the Node

```bash
# Provision GPU node specifically
cluster-mgr provision --limit gpu-node

# Or provision entire cluster
cluster-mgr provision
```

### 4. Verify GPU Availability

```bash
# Check node has GPU label
kubectl get nodes -L gpu

# Check GPU resources
kubectl describe node gpu-node | grep nvidia.com/gpu

# Verify device plugin is running
kubectl get pods -n kube-system -l name=nvidia-device-plugin-ds
```

## Configuration Options

### Node-Level Configuration

#### Basic GPU Node

Minimal configuration for a dedicated GPU node:

```yaml
gpu-node:
  ansible_host: 100.64.0.30
  tailscale_ip: 100.64.0.30
  gpu: true
  node_labels:
    gpu: "true"
```

#### GPU Workstation Node

Configuration for a node that serves as both workstation and cluster member:

```yaml
gpu-workstation:
  ansible_host: 100.64.0.31
  tailscale_ip: 100.64.0.31
  reserved_cpu: "6"        # Reserve cores for local work
  reserved_memory: "16Gi"  # Reserve RAM for local work
  gpu: true
  node_labels:
    gpu: "true"
    gpu-type: nvidia-rtx-4090
    workstation: "true"
  node_taints:
    - key: nvidia.com/gpu
      value: "true"
      effect: NoSchedule  # Prevent non-GPU pods from scheduling
```

#### Multi-GPU Node

Configuration for nodes with multiple GPUs:

```yaml
dgx-station:
  ansible_host: 100.64.0.32
  tailscale_ip: 100.64.0.32
  reserved_cpu: "8"
  reserved_memory: "32Gi"
  gpu: true
  node_labels:
    gpu: "true"
    gpu-type: nvidia-a100
    gpu-count: "4"
    high-performance: "true"
  node_taints:
    - key: nvidia.com/gpu
      value: "true"
      effect: NoSchedule
    - key: high-performance
      value: "true"
      effect: PreferNoSchedule  # Prefer this node for HP workloads
```

### Group-Level Configuration

Configure GPU settings for all GPU nodes in `group_vars/workers.yml`:

```yaml
# NVIDIA Driver Configuration
nvidia_driver_version: "535"  # Options: 470, 510, 525, 535, 545
nvidia_driver_install: true   # Auto-install if not present
nvidia_driver_persistence: true  # Enable persistence mode

# Device Plugin Configuration
nvidia_device_plugin_version: "v0.14.3"
nvidia_device_plugin_namespace: kube-system

# GPU Time-Slicing Configuration
gpu_time_slicing_enabled: true
gpu_replicas: 4  # Each physical GPU appears as 4 virtual GPUs
gpu_time_slice_interval: "default"  # Options: default, short, medium, long

# GPU Monitoring
gpu_monitoring_enabled: true
dcgm_exporter_enabled: true  # Prometheus metrics for GPUs
```

## GPU Time-Slicing

Time-slicing allows multiple pods to share a single GPU by time-multiplexing access.

### Benefits

- **Resource Efficiency**: Run multiple small workloads on one GPU
- **Cost Savings**: Maximize GPU utilization
- **Development**: Multiple developers can share GPU resources

### Limitations

- **No Memory Isolation**: Pods share GPU memory
- **Performance**: Context switching overhead
- **Best For**: Inference, development, small training jobs
- **Not For**: Large models, real-time applications

### Configuration

Enable time-slicing in `group_vars/workers.yml`:

```yaml
gpu_time_slicing_enabled: true
gpu_replicas: 4  # Creates 4 virtual GPUs per physical GPU
```

### Usage in Pods

Request a time-sliced GPU:

```yaml
resources:
  requests:
    nvidia.com/gpu: 1  # Request 1 virtual GPU
  limits:
    nvidia.com/gpu: 1
```

With `gpu_replicas: 4`, you can run 4 pods simultaneously on one physical GPU.

## Deploying GPU Workloads

### Basic GPU Pod

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  nodeSelector:
    gpu: "true"
  tolerations:
  - key: nvidia.com/gpu
    operator: Equal
    value: "true"
    effect: NoSchedule
  containers:
  - name: cuda-test
    image: nvidia/cuda:12.0.0-base-ubuntu22.04
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1
```

### GPU Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gpu-workload
spec:
  replicas: 2
  selector:
    matchLabels:
      app: gpu-workload
  template:
    metadata:
      labels:
        app: gpu-workload
    spec:
      nodeSelector:
        gpu: "true"
      tolerations:
      - key: nvidia.com/gpu
        operator: Equal
        value: "true"
        effect: NoSchedule
      containers:
      - name: app
        image: your-gpu-app:latest
        resources:
          requests:
            cpu: 2
            memory: 4Gi
            nvidia.com/gpu: 1
          limits:
            cpu: 4
            memory: 8Gi
            nvidia.com/gpu: 1
```

### Specific GPU Type Selection

Use node affinity to target specific GPU types:

```yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: gpu-type
            operator: In
            values:
            - nvidia-a100
            - nvidia-rtx-4090
  tolerations:
  - key: nvidia.com/gpu
    operator: Equal
    value: "true"
    effect: NoSchedule
```

## Example Applications

### Machine Learning Training

See `gitops/apps/base/ml-training/` for a complete example:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: pytorch-training
spec:
  template:
    spec:
      nodeSelector:
        gpu: "true"
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
      containers:
      - name: trainer
        image: pytorch/pytorch:2.0.0-cuda11.7-cudnn8-runtime
        command: ["python", "train.py"]
        resources:
          limits:
            nvidia.com/gpu: 1
      restartPolicy: Never
```

### GPU Inference Service

See `gitops/apps/base/gpu-inference/` for a complete example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-service
spec:
  replicas: 4  # With time-slicing enabled
  template:
    spec:
      nodeSelector:
        gpu: "true"
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
      containers:
      - name: inference
        image: your-inference-service:latest
        resources:
          requests:
            nvidia.com/gpu: 1
          limits:
            nvidia.com/gpu: 1
```

## Monitoring GPU Usage

### Using nvidia-smi

SSH into the GPU node:

```bash
# Real-time monitoring
watch -n 1 nvidia-smi

# Detailed GPU info
nvidia-smi -q

# Process list
nvidia-smi pmon
```

### Using kubectl

```bash
# Check GPU allocation
kubectl describe nodes -l gpu=true

# View GPU resource usage
kubectl top nodes -l gpu=true

# Check which pods are using GPUs
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.containers[].resources.limits."nvidia.com/gpu" != null) | {name: .metadata.name, namespace: .metadata.namespace}'
```

### Prometheus Metrics

If DCGM exporter is enabled, GPU metrics are available in Prometheus:

```promql
# GPU utilization
DCGM_FI_DEV_GPU_UTIL

# GPU memory usage
DCGM_FI_DEV_FB_USED / DCGM_FI_DEV_FB_FREE

# GPU temperature
DCGM_FI_DEV_GPU_TEMP
```

## Troubleshooting

### GPU Not Detected

**Problem:** `nvidia-smi` not working or GPU not visible

**Solutions:**

```bash
# Check if GPU is detected by system
lspci | grep -i nvidia

# Verify driver is loaded
lsmod | grep nvidia

# Check driver version
nvidia-smi

# Reinstall driver if needed
sudo apt purge nvidia-*
sudo apt autoremove
sudo apt install nvidia-driver-535
sudo reboot
```

### Device Plugin Not Running

**Problem:** NVIDIA device plugin pods not starting

**Solutions:**

```bash
# Check device plugin status
kubectl get pods -n kube-system -l name=nvidia-device-plugin-ds

# View logs
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds

# Common issues:
# 1. Driver not installed - install NVIDIA driver
# 2. containerd not configured - check /etc/containerd/config.toml
# 3. Wrong plugin version - update nvidia_device_plugin_version
```

### Pods Not Scheduling on GPU Nodes

**Problem:** GPU pods remain in Pending state

**Solutions:**

```bash
# Check why pod is pending
kubectl describe pod <pod-name>

# Common issues:
# 1. Missing toleration - add nvidia.com/gpu toleration
# 2. No GPU resources - check node GPU allocation
# 3. Wrong node selector - verify gpu label exists

# Check node GPU capacity
kubectl get nodes -o json | \
  jq '.items[] | {name: .metadata.name, gpu: .status.capacity."nvidia.com/gpu"}'
```

### GPU Memory Errors

**Problem:** CUDA out of memory errors

**Solutions:**

```bash
# Check GPU memory usage
nvidia-smi

# Reduce batch size in application
# Reduce number of time-sliced replicas
# Add more physical GPUs
# Use gradient checkpointing in training
```

### Time-Slicing Not Working

**Problem:** Can't run multiple pods on same GPU

**Solutions:**

```bash
# Verify time-slicing is enabled
kubectl get configmap -n kube-system nvidia-device-plugin-config -o yaml

# Check device plugin version (must be v0.12.0+)
kubectl get daemonset -n kube-system nvidia-device-plugin-daemonset -o yaml | grep image:

# Restart device plugin
kubectl rollout restart daemonset -n kube-system nvidia-device-plugin-daemonset
```

## Best Practices

### Resource Reservations

Always reserve resources on GPU workstation nodes:

```yaml
reserved_cpu: "4"      # Reserve for local work
reserved_memory: "8Gi" # Reserve for local work
```

### Taints and Tolerations

Use taints to prevent non-GPU workloads from consuming GPU node resources:

```yaml
node_taints:
  - key: nvidia.com/gpu
    value: "true"
    effect: NoSchedule
```

### Node Labels

Use descriptive labels for GPU targeting:

```yaml
node_labels:
  gpu: "true"
  gpu-type: nvidia-rtx-4090
  gpu-memory: 24gb
  gpu-count: "1"
```

### Resource Limits

Always set resource limits for GPU pods:

```yaml
resources:
  requests:
    nvidia.com/gpu: 1
    memory: 4Gi
  limits:
    nvidia.com/gpu: 1
    memory: 8Gi
```

### Monitoring

- Enable DCGM exporter for metrics
- Set up alerts for GPU temperature and utilization
- Monitor GPU memory usage
- Track pod GPU allocation

### Driver Management

- Use LTS driver versions (470, 535)
- Test driver updates on non-production nodes first
- Keep driver version consistent across GPU nodes
- Enable driver persistence mode

## Advanced Topics

### MIG (Multi-Instance GPU)

For A100 and H100 GPUs, consider using MIG for hardware-level GPU partitioning:

```bash
# Enable MIG mode
sudo nvidia-smi -mig 1

# Create MIG instances
sudo nvidia-smi mig -cgi 9,9,9,9,9,9,9 -C

# Configure device plugin for MIG
# See NVIDIA documentation for details
```

### GPU Operator

For advanced GPU management, consider the NVIDIA GPU Operator:

```bash
# Install via Helm
helm repo add nvidia https://nvidia.github.io/gpu-operator
helm install gpu-operator nvidia/gpu-operator \
  --namespace gpu-operator \
  --create-namespace
```

### Custom GPU Scheduling

Implement custom scheduling logic using:
- Kubernetes scheduler extenders
- Custom schedulers
- Admission webhooks

## References

- [NVIDIA Device Plugin Documentation](https://github.com/NVIDIA/k8s-device-plugin)
- [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/overview.html)
- [CUDA Compatibility](https://docs.nvidia.com/deploy/cuda-compatibility/)
- [Time-Slicing GPUs](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/gpu-sharing.html)
- [MIG User Guide](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/)

## Support

For GPU-specific issues:
1. Check NVIDIA driver logs: `dmesg | grep nvidia`
2. Review device plugin logs: `kubectl logs -n kube-system -l name=nvidia-device-plugin-ds`
3. Consult NVIDIA documentation
4. Open an issue with GPU model, driver version, and error logs
