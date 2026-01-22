# ML Training Example

This example demonstrates how to run GPU-accelerated machine learning training jobs on your Kubernetes cluster.

## Overview

This Job uses PyTorch with CUDA support to verify GPU availability and simulate a training workload.

## Prerequisites

- At least one GPU node in the cluster with `gpu: "true"` label
- NVIDIA device plugin installed and running
- GPU node must tolerate `nvidia.com/gpu` taint

## Deployment

This application is automatically deployed via GitOps when committed to the repository.

### Manual Deployment

```bash
kubectl apply -k gitops/apps/base/ml-training/
```

## Verification

Check job status:

```bash
# View job status
kubectl get jobs

# View pod logs
kubectl logs -l app=ml-training

# Expected output:
# PyTorch version: 2.0.0
# CUDA available: True
# CUDA version: 11.7
# GPU count: 1
# GPU name: NVIDIA GeForce RTX 4090
# Starting training simulation...
# Epoch 1/5
# ...
# Training complete!
```

## Customization

### Use Your Own Training Script

Replace the inline Python script with your training code:

```yaml
containers:
- name: trainer
  image: your-registry/your-training-image:latest
  command: ["python", "train.py"]
  args:
    - --epochs=100
    - --batch-size=32
    - --learning-rate=0.001
```

### Request Multiple GPUs

For multi-GPU training:

```yaml
resources:
  limits:
    nvidia.com/gpu: 2  # Request 2 GPUs
```

### Add Persistent Storage

Mount a PVC for datasets and checkpoints:

```yaml
spec:
  template:
    spec:
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: training-data
      containers:
      - name: trainer
        volumeMounts:
        - name: data
          mountPath: /data
```

### Target Specific GPU Types

Use node affinity to select specific GPU models:

```yaml
spec:
  template:
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
```

## Monitoring

View GPU usage during training:

```bash
# SSH to GPU node
ssh user@gpu-node

# Monitor GPU in real-time
watch -n 1 nvidia-smi
```

## Cleanup

```bash
kubectl delete job pytorch-training-job
```

## Related Examples

- `gpu-inference/` - GPU inference service
- `gpu-test/` - Simple GPU availability test
