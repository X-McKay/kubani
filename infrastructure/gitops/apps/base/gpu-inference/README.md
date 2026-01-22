# GPU Inference Service Example

This example demonstrates a GPU-accelerated inference service that can handle multiple concurrent requests using GPU time-slicing.

## Overview

This deployment creates a simple inference service that:
- Uses GPU acceleration for model inference
- Supports multiple replicas with GPU time-slicing
- Exposes an HTTP API for inference requests
- Demonstrates efficient GPU resource sharing

## Prerequisites

- GPU node with time-slicing enabled (`gpu_time_slicing_enabled: true`)
- NVIDIA device plugin with time-slicing support (v0.12.0+)
- GPU node labeled with `gpu: "true"`

## Architecture

```
┌─────────────────────────────────────────┐
│         Service (ClusterIP)             │
│         gpu-inference:8080              │
└─────────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌─────────┐  ┌─────────┐  ┌─────────┐
│ Pod 1   │  │ Pod 2   │  │ Pod 3   │
│ GPU 1/4 │  │ GPU 2/4 │  │ GPU 3/4 │
└─────────┘  └─────────┘  └─────────┘
         All on same physical GPU
```

## Deployment

Automatically deployed via GitOps when committed.

### Manual Deployment

```bash
kubectl apply -k gitops/apps/base/gpu-inference/
```

## Testing

### Port Forward

```bash
kubectl port-forward service/gpu-inference 8080:8080
```

### Send Test Request

```bash
# Health check
curl http://localhost:8080/health

# Inference request
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"input": "test data"}'
```

## Scaling

### Horizontal Scaling

With time-slicing enabled (e.g., `gpu_replicas: 4`), you can run up to 4 replicas per physical GPU:

```bash
kubectl scale deployment gpu-inference --replicas=4
```

### Vertical Scaling

For larger models, increase resource requests:

```yaml
resources:
  requests:
    cpu: 4
    memory: 8Gi
    nvidia.com/gpu: 1
  limits:
    cpu: 8
    memory: 16Gi
    nvidia.com/gpu: 1
```

## Customization

### Use Your Own Model

Replace the example container with your inference service:

```yaml
containers:
- name: inference
  image: your-registry/your-inference-service:latest
  ports:
  - containerPort: 8080
  env:
  - name: MODEL_PATH
    value: /models/your-model
  resources:
    limits:
      nvidia.com/gpu: 1
```

### Add Model Storage

Mount a PVC with your model files:

```yaml
spec:
  template:
    spec:
      volumes:
      - name: models
        persistentVolumeClaim:
          claimName: model-storage
      containers:
      - name: inference
        volumeMounts:
        - name: models
          mountPath: /models
          readOnly: true
```

### Configure Autoscaling

Add HPA for automatic scaling based on load:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: gpu-inference-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: gpu-inference
  minReplicas: 2
  maxReplicas: 4  # Limited by GPU time-slicing replicas
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Monitoring

### Check Pod Status

```bash
kubectl get pods -l app=gpu-inference
```

### View Logs

```bash
kubectl logs -l app=gpu-inference --tail=50 -f
```

### GPU Usage

```bash
# SSH to GPU node
ssh user@gpu-node

# Monitor GPU usage
nvidia-smi
```

## Performance Considerations

### Time-Slicing Overhead

- Context switching adds ~5-10% overhead
- Best for inference workloads with short execution times
- Not recommended for real-time applications (<10ms latency)

### Batch Size

Optimize batch size for your GPU:
- Larger batches = better GPU utilization
- Smaller batches = lower latency
- Test different batch sizes to find optimal balance

### Memory Management

- Monitor GPU memory usage
- Reduce batch size if OOM errors occur
- Consider model quantization for memory savings

## Troubleshooting

### Pods Not Scheduling

```bash
# Check pod events
kubectl describe pod -l app=gpu-inference

# Common issues:
# - Insufficient GPU resources
# - Missing tolerations
# - Wrong node selector
```

### High Latency

```bash
# Check if too many replicas on one GPU
kubectl get pods -l app=gpu-inference -o wide

# Reduce replicas or add more physical GPUs
kubectl scale deployment gpu-inference --replicas=2
```

### GPU Memory Errors

```bash
# Check GPU memory usage
nvidia-smi

# Reduce batch size or model size
# Or disable time-slicing for exclusive GPU access
```

## Related Examples

- `ml-training/` - GPU training jobs
- `gpu-test/` - Simple GPU availability test

## References

- [NVIDIA Triton Inference Server](https://github.com/triton-inference-server/server)
- [TorchServe](https://pytorch.org/serve/)
- [TensorFlow Serving](https://www.tensorflow.org/tfx/guide/serving)
