# Node Configuration Role

This role handles node-specific configuration based on hardware capabilities and inventory attributes.

## Responsibilities

1. **Hardware Detection**: Detect node hardware capabilities (CPU, memory, storage, GPU)
2. **Storage Configuration**: Configure storage classes based on node attributes
3. **Custom Labels and Taints**: Apply custom labels and taints from inventory
4. **Resource Limits**: Configure resource limits for resource-constrained nodes
5. **Conditional Features**: Enable/disable features based on node capabilities

## Variables

### Required Variables
- `tailscale_ip`: Node's Tailscale IP address
- `ansible_hostname`: Node hostname

### Optional Variables
- `node_labels`: Dictionary of custom labels to apply to the node
- `node_taints`: List of taints to apply to the node
- `storage_class`: Storage class configuration for the node
- `max_pods`: Maximum number of pods allowed on the node
- `enable_local_storage`: Enable local path provisioner (default: false)

## Usage

This role is typically applied after the k3s_worker role to configure node-specific settings.

```yaml
- hosts: workers
  roles:
    - role: node_config
      tags:
        - node-config
```

## Tags

- `node-config`: All node configuration tasks
- `hardware-detection`: Hardware capability detection
- `storage`: Storage configuration
- `labels-taints`: Label and taint application
- `resource-limits`: Resource limit configuration
