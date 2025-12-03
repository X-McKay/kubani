# GPU Test Application

A simple test deployment to verify GPU availability and NVIDIA device plugin functionality.

## Purpose

This deployment helps you:
- Verify NVIDIA GPU is detected by Kubernetes
- Test GPU resource allocation
- Validate NVIDIA device plugin installation
- Check GPU driver compatibility

## Prerequisites

- At least one GPU node with `gpu: "true"` label
- NVIDIA device plugin installed and running
- GPU node must tolerate `nvidia.com/gpu` taint

## Deployment

This application is automatically deployed via GitOps when committed to the repository.

### Manual Deployment

```bash
kubectl apply -k gitops/apps/base/gpu-test/
```

## Verification

Check if the pod is running and has GPU access:

```bash
# Check pod status
kubectl get pods -l app=gpu-test

# View pod logs
kubectl logs -l app=gpu-test

# Execute nvidia-smi in the pod
kubectl exec -it $(kubectl get pod -l app=gpu-test -o jsonpath='{.items[0].metadata.name}') -- nvidia-smi
```

### Expected Output

If GPU is working correctly, you should see:

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.xx.xx    Driver Version: 535.xx.xx    CUDA Version: 12.0   |
|-------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|===============================+======================+======================|
|   0  NVIDIA GeForce ...  Off  | 00000000:01:00.0 Off |                  N/A |
| 30%   45C    P0    50W / 350W |      0MiB / 24576MiB |      0%      Default |
+-------------------------------+----------------------+----------------------+
```

## Troubleshooting

### Pod Stuck in Pending

```bash
# Check why pod is pending
kubectl describe pod -l app=gpu-test

# Common issues:
# 1. No GPU resources available
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, gpu: .status.capacity."nvidia.com/gpu"}'

# 2. Missing toleration (should be in deployment already)
# 3. Node selector not matching
kubectl get nodes -L gpu
```

### GPU Not Detected

```bash
# Check if device plugin is running
kubectl get pods -n kube-system -l name=nvidia-device-plugin-ds

# View device plugin logs
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds

# SSH to GPU node and check driver
ssh user@gpu-node
nvidia-smi
```

### Pod Running but No GPU

```bash
# Check resource allocation
kubectl describe pod -l app=gpu-test | grep -A 5 "Limits:"

# Verify environment variables
kubectl exec -it $(kubectl get pod -l app=gpu-test -o jsonpath='{.items[0].metadata.name}') -- env | grep NVIDIA
```

## Customization

### Test Different CUDA Versions

```yaml
containers:
- name: cuda-test
  image: nvidia/cuda:11.8.0-base-ubuntu22.04  # Change CUDA version
```

### Run Specific GPU Tests

```yaml
containers:
- name: cuda-test
  image: nvidia/cuda:12.0.0-devel-ubuntu22.04
  command:
  - /bin/bash
  - -c
  - |
    # Compile and run CUDA sample
    cd /usr/local/cuda/samples/1_Utilities/deviceQuery
    make
    ./deviceQuery
```

### Request Multiple GPUs

```yaml
resources:
  limits:
    nvidia.com/gpu: 2  # Request 2 GPUs
```

## Cleanup

```bash
kubectl delete -k gitops/apps/base/gpu-test/
```

## Related Examples

- `ml-training/` - GPU training job example
- `gpu-inference/` - GPU inference service example

## References

- [NVIDIA Device Plugin](https://github.com/NVIDIA/k8s-device-plugin)
- [CUDA Docker Images](https://hub.docker.com/r/nvidia/cuda)
- [GPU Configuration Guide](../../../docs/GPU_CONFIGURATION.md)
