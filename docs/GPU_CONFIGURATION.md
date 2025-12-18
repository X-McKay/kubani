# GPU Node Configuration Guide

This guide explains how to configure and use NVIDIA GPU nodes in your Kubernetes cluster using the NVIDIA GPU Operator.

## Overview

The cluster uses the **NVIDIA GPU Operator** for automated GPU management. This provides:
- Automated driver and runtime configuration
- GPU time-slicing for sharing GPUs across multiple pods
- DCGM metrics for GPU monitoring
- Node feature discovery for GPU capabilities
- Support for consumer GPUs, data center GPUs, and DGX systems

## Prerequisites

### Hardware Requirements

- NVIDIA GPU (GeForce, Quadro, Tesla, A-series, GB10/DGX Spark)
- Sufficient PCIe power and cooling
- Minimum 8GB system RAM (16GB+ recommended)
- 4+ CPU cores recommended

### Software Requirements

- Ubuntu 20.04+ or compatible Linux distribution
- Kernel headers installed: `sudo apt install linux-headers-$(uname -r)`
- NVIDIA drivers pre-installed (GPU Operator uses existing drivers)
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
```

### 2. Provision the Node

```bash
# Provision GPU node specifically
cluster-mgr provision --limit gpu-node
```

### 3. Verify GPU Availability

```bash
# Check node has GPU label
kubectl get nodes -L gpu

# Check GPU resources (time-sliced to 4 virtual GPUs)
kubectl describe node gpu-node | grep nvidia.com/gpu

# Verify GPU Operator pods are running
kubectl get pods -n gpu-operator
```

## GPU Operator Configuration

The GPU Operator is deployed via Flux CD using a HelmRelease. The configuration is located at `gitops/infrastructure/gpu-operator/`.

### HelmRelease Configuration

The GPU Operator HelmRelease (`helmrelease.yaml`) configures:

```yaml
spec:
  chart:
    spec:
      chart: gpu-operator
      version: "v25.10.1"  # Required for GB10/DGX Spark support

  values:
    # Use pre-installed drivers
    driver:
      enabled: false

    # CUDA toolkit for K3s containerd
    toolkit:
      enabled: true
      env:
        - name: CONTAINERD_CONFIG
          value: /var/lib/rancher/k3s/agent/etc/containerd/config.toml
        - name: CONTAINERD_SOCKET
          value: /run/k3s/containerd/containerd.sock

    # Device plugin with time-slicing
    devicePlugin:
      enabled: true
      config:
        name: time-slicing-config
        default: any
```

### Time-Slicing Configuration

Time-slicing allows multiple pods to share a single GPU. The configuration creates 4 virtual GPU slices per physical GPU.

**ConfigMap** (`time-slicing-config.yaml`):

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config
  namespace: gpu-operator
data:
  any: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        renameByDefault: false
        failRequestsGreaterThanOne: false
        resources:
        - name: nvidia.com/gpu
          replicas: 4
```

With this configuration, a node with 1 physical GPU will advertise `nvidia.com/gpu: 4`, allowing up to 4 pods to share the GPU.

### Important Notes on Time-Slicing

**What time-slicing does:**
- Shares GPU compute time among multiple pods via context switching
- Each pod gets a time slice of the GPU
- Good for inference, development, and small workloads

**What time-slicing does NOT do:**
- Does NOT partition GPU memory - all pods share the same memory pool
- Does NOT provide memory isolation
- Does NOT guarantee performance

**Memory Management with Time-Slicing:**

When running multiple workloads (e.g., main LLM + embeddings), you must ensure their combined memory usage fits within the GPU memory:

```yaml
# Main LLM (vLLM) - uses 76% of GPU memory
- --gpu-memory-utilization
- "0.76"

# Embeddings model - uses 10% of GPU memory
- --gpu-memory-utilization
- "0.10"
# Total: 86%, leaving headroom for fragmentation
```

## GB10 / DGX Spark Support

For NVIDIA GB10 (DGX Spark) systems with unified memory architecture (UMA):

### Requirements

- GPU Operator v25.10.0+ (we use v25.10.1)
- NVIDIA driver 580.95.05+
- Device plugin v0.18.0+

### Special Configuration

GB10 uses a unified memory architecture where GPU and CPU share the same memory pool. Additional configuration may be needed:

```yaml
# In vLLM deployments, disable Ray memory monitor
env:
  - name: RAY_memory_monitor_refresh_ms
    value: "0"
```

## Deploying GPU Workloads

### Basic GPU Pod

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  runtimeClassName: nvidia  # Required for GPU access
  nodeSelector:
    gpu: "true"
  containers:
  - name: cuda-test
    image: nvidia/cuda:12.0.0-base-ubuntu22.04
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1  # Request 1 virtual GPU slice
```

### GPU Deployment with Node Selection

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gpu-workload
spec:
  replicas: 2
  template:
    spec:
      runtimeClassName: nvidia
      nodeSelector:
        kubernetes.io/hostname: sparky  # Target specific GPU node
      containers:
      - name: app
        image: your-gpu-app:latest
        resources:
          requests:
            nvidia.com/gpu: 1
          limits:
            nvidia.com/gpu: 1
```

## vLLM LLM Inference

The cluster runs vLLM for LLM inference. Two deployments share the GPU:

### Main LLM (Qwen3-30B-A3B)

```yaml
# gitops/apps/vllm/deployment.yaml
spec:
  template:
    spec:
      runtimeClassName: nvidia
      containers:
      - name: vllm
        image: nvcr.io/nvidia/vllm:25.11-py3
        args:
          - /models/Qwen3-30B-A3B
          - --gpu-memory-utilization
          - "0.76"  # Use 76% of GPU memory
          - --enable-auto-tool-choice
          - --tool-call-parser
          - hermes
```

Accessible at:
- Internal: `http://llm-api.vllm.svc.cluster.local:8000/v1`
- External: `https://llm.almckay.io/v1`

### Embeddings (Qwen3-Embedding-0.6B)

```yaml
# gitops/apps/vllm/embeddings-deployment.yaml
spec:
  template:
    spec:
      runtimeClassName: nvidia
      containers:
      - name: embeddings
        args:
          - /models/Qwen3-Embedding-0.6B
          - --gpu-memory-utilization
          - "0.10"  # Use 10% of GPU memory
```

Accessible at:
- Internal: `http://embeddings-api.vllm.svc.cluster.local:8000/v1`
- External: `https://embeddings.almckay.io/v1`

## Monitoring GPU Usage

### Using nvidia-smi on Nodes

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
kubectl describe node -l gpu=true | grep -A 5 "Allocated resources"

# Check which pods are using GPUs
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.containers[].resources.limits."nvidia.com/gpu" != null) | {name: .metadata.name, namespace: .metadata.namespace}'

# View GPU Operator components
kubectl get pods -n gpu-operator
```

### DCGM Metrics

The GPU Operator includes DCGM exporter for Prometheus metrics:

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

**Problem:** `nvidia-smi` not working

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

### GPU Operator Pods Not Running

**Problem:** GPU Operator components failing to start

**Solutions:**

```bash
# Check GPU Operator pods
kubectl get pods -n gpu-operator

# View operator logs
kubectl logs -n gpu-operator -l app=gpu-operator

# Check device plugin
kubectl logs -n gpu-operator -l app=nvidia-device-plugin-daemonset

# Check toolkit installer
kubectl logs -n gpu-operator -l app=nvidia-container-toolkit-daemonset
```

### Pods Not Scheduling on GPU Node

**Problem:** GPU pods remain in Pending state

**Solutions:**

```bash
# Check why pod is pending
kubectl describe pod <pod-name>

# Verify GPU resources available
kubectl get nodes -o json | \
  jq '.items[] | {name: .metadata.name, gpu: .status.allocatable."nvidia.com/gpu"}'

# Check if runtimeClassName is set
kubectl get pod <pod-name> -o yaml | grep runtimeClassName
```

### CUDA Out of Memory

**Problem:** CUDA OOM errors when running multiple workloads

**Solutions:**

1. Reduce `--gpu-memory-utilization` for each workload
2. Ensure total utilization < 95% to leave headroom
3. Check if a previous pod is still consuming memory
4. Consider reducing time-slice replicas

```bash
# Check current GPU memory usage
nvidia-smi

# Restart pods to clear memory
kubectl rollout restart deployment/vllm -n vllm
kubectl rollout restart deployment/vllm-embeddings -n vllm
```

### Time-Slicing Not Working

**Problem:** Node shows 1 GPU instead of 4

**Solutions:**

```bash
# Verify time-slicing ConfigMap exists
kubectl get configmap time-slicing-config -n gpu-operator

# Check device plugin configuration
kubectl get pods -n gpu-operator -l app=nvidia-device-plugin-daemonset -o yaml | grep -A 20 "config"

# Restart device plugin to pick up config
kubectl rollout restart daemonset -n gpu-operator nvidia-device-plugin-daemonset
```

## Best Practices

### Resource Management

1. **Always set runtimeClassName**: Required for GPU access
   ```yaml
   spec:
     runtimeClassName: nvidia
   ```

2. **Use nodeSelector for GPU nodes**: Ensure pods land on GPU nodes
   ```yaml
   nodeSelector:
     gpu: "true"
   ```

3. **Set memory limits carefully**: For time-sliced workloads, ensure combined memory < GPU capacity

### Multi-Workload GPU Sharing

When running multiple workloads on the same GPU:

1. Calculate total memory needs
2. Leave 10-15% headroom for fragmentation
3. Use `Recreate` deployment strategy to avoid memory conflicts during updates
4. Consider startup order if workloads have different memory requirements

### Monitoring

1. Enable DCGM exporter for metrics
2. Monitor GPU memory and utilization
3. Set up alerts for OOM conditions
4. Track GPU temperature in high-load scenarios

## File Locations

- **GPU Operator HelmRelease**: `gitops/infrastructure/gpu-operator/helmrelease.yaml`
- **Time-Slicing ConfigMap**: `gitops/infrastructure/gpu-operator/time-slicing-config.yaml`
- **vLLM Deployment**: `gitops/apps/vllm/deployment.yaml`
- **Embeddings Deployment**: `gitops/apps/vllm/embeddings-deployment.yaml`

## References

- [NVIDIA GPU Operator Documentation](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/)
- [GPU Time-Slicing Guide](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/gpu-sharing.html)
- [vLLM Documentation](https://docs.vllm.ai/)
- [GB10/DGX Spark Support](https://github.com/NVIDIA/gpu-operator/issues/1794)
