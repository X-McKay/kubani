# Error Handling Guide

This document describes the error handling mechanisms implemented across the cluster manager system.

## Overview

The cluster manager implements comprehensive error handling across all components:

1. **Python CLI/TUI**: Custom exceptions, logging, and user-friendly error messages
2. **Ansible Playbooks**: Rescue blocks, validation checks, and detailed error reporting
3. **Kubernetes Integration**: Connection error handling and graceful degradation

## Python Error Handling

### Custom Exceptions

All custom exceptions inherit from `ClusterManagerError` and support detailed error messages:

```python
from cluster_manager.exceptions import TailscaleError, KubernetesError, ValidationError

try:
    # Operation that might fail
    nodes = TailscaleDiscovery.discover_nodes()
except TailscaleError as e:
    # e.message contains the main error
    # e.details contains troubleshooting information
    print(f"Error: {e.message}")
    print(f"Details: {e.details}")
```

### Logging

All components use structured logging:

```python
from cluster_manager.logging_config import setup_logging, get_logger

# Set up logging (done automatically in CLI)
setup_logging(verbose=True, log_file=Path("debug.log"))

# Get a logger
logger = get_logger(__name__)

# Log at different levels
logger.debug("Detailed debugging information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error message", exc_info=True)  # Include stack trace
```

### CLI Error Handling

The CLI provides user-friendly error messages with troubleshooting steps:

```bash
# Enable verbose logging
cluster-mgr discover --verbose

# Save logs to file
cluster-mgr discover --log-file debug.log

# Both options
cluster-mgr provision --verbose --log-file provision.log
```

## Ansible Error Handling

### Pre-flight Validation

Run pre-flight checks before provisioning:

```bash
ansible-playbook ansible/playbooks/preflight_checks.yml -i ansible/inventory/hosts.yml
```

This validates:
- Ansible version
- Inventory structure
- Required variables
- SSH connectivity
- Tailscale installation and authentication
- Disk space and memory
- Port availability

### Rescue Blocks

All major playbook sections use rescue blocks to provide detailed error information:

```yaml
- name: Execute control plane setup
  block:
    - name: Include k3s_control_plane role
      ansible.builtin.include_role:
        name: k3s_control_plane

  rescue:
    - name: Gather diagnostic information
      # Collect service status, logs, etc.

    - name: Report failure with details
      ansible.builtin.fail:
        msg: |
          Detailed error message with:
          - Node information
          - Failed task
          - Service status
          - Recent logs
          - Troubleshooting steps
```

### Error Recovery

When a playbook fails:

1. **Review the error message**: Contains node, task, and error details
2. **Check service status**: `sudo systemctl status k3s` or `k3s-agent`
3. **View logs**: `sudo journalctl -u k3s -n 100`
4. **Fix the issue**: Based on troubleshooting steps
5. **Re-run the playbook**: Ansible is idempotent, safe to re-run

### Common Ansible Errors

#### Tailscale Not Authenticated

```
Error: Tailscale is not authenticated on node-name
```

**Solution**:
```bash
ssh node-name
sudo tailscale up
```

#### Control Plane API Not Responding

```
Error: Control plane API server did not become ready
```

**Solution**:
```bash
# Check K3s service
sudo systemctl status k3s

# View logs
sudo journalctl -u k3s -f

# Check if port is listening
sudo netstat -tlnp | grep 6443

# Verify Tailscale IP
ip addr show tailscale0
```

#### Worker Cannot Join Cluster

```
Error: Worker node setup failed - connection refused
```

**Solution**:
```bash
# Test control plane connectivity
curl -k https://CONTROL_PLANE_TAILSCALE_IP:6443

# Check K3s agent service
sudo systemctl status k3s-agent

# View agent logs
sudo journalctl -u k3s-agent -f

# Verify join token
cat /etc/rancher/k3s/k3s-agent.yaml
```

## TUI Error Handling

The TUI handles errors gracefully:

### Connection Errors

When Kubernetes API is unavailable:
- Shows warning notification (once)
- Displays last known state
- Continues auto-refresh attempts
- Reconnects automatically when API is available

### Display Errors

- Terminal too small: Shows minimum size requirements
- Missing data: Shows "N/A" instead of crashing
- Refresh failures: Keeps displaying last known state

### Logging

TUI logs to stderr by default:

```bash
# Run TUI with verbose logging
cluster-mgr tui --verbose 2> tui.log

# View logs in real-time
tail -f tui.log
```

## Validation Errors

### Inventory Validation

The inventory manager validates:
- File exists and is readable
- Valid YAML syntax
- Required structure (all, children, control_plane, workers)
- Required fields for each node (hostname, tailscale_ip)
- IP address format
- No duplicate hostnames or IPs

**Example Error**:
```
Inventory Error: Node 'worker-1' already exists in inventory

Use 'cluster-mgr remove-node worker-1' to remove it first,
or use a different hostname
```

### Node Validation

Node models validate:
- Hostname format
- IP address format
- Role (control-plane or worker)
- Resource reservation format (CPU, memory)
- Label and taint format

**Example Error**:
```
Validation Error:
  - tailscale_ip: value is not a valid IPv4 or IPv6 address
  - reserved_cpu: invalid format, expected number or string like '2'
```

## Best Practices

### For Users

1. **Always run pre-flight checks first**:
   ```bash
   ansible-playbook ansible/playbooks/preflight_checks.yml -i ansible/inventory/hosts.yml
   ```

2. **Use verbose mode when troubleshooting**:
   ```bash
   cluster-mgr provision --verbose --log-file provision.log
   ```

3. **Check logs when errors occur**:
   ```bash
   # Ansible logs
   cat provision.log

   # System logs
   sudo journalctl -u k3s -n 100
   sudo journalctl -u k3s-agent -n 100
   sudo journalctl -u tailscaled -n 100
   ```

4. **Verify Tailscale connectivity**:
   ```bash
   tailscale status
   tailscale ping OTHER_NODE_IP
   ```

5. **Test SSH connectivity**:
   ```bash
   ssh -i ~/.ssh/id_rsa user@TAILSCALE_IP
   ```

### For Developers

1. **Always use custom exceptions**:
   ```python
   from cluster_manager.exceptions import TailscaleError

   raise TailscaleError(
       "Main error message",
       "Detailed troubleshooting information"
   )
   ```

2. **Log at appropriate levels**:
   ```python
   logger.debug("Detailed info for debugging")
   logger.info("Important milestones")
   logger.warning("Recoverable issues")
   logger.error("Errors that need attention", exc_info=True)
   ```

3. **Provide context in error messages**:
   ```python
   raise InventoryError(
       f"Node '{hostname}' not found in inventory\n\n"
       f"Available nodes: {', '.join(existing_nodes)}\n"
       f"Check your inventory file at: {inventory_path}"
   )
   ```

4. **Use rescue blocks in Ansible**:
   ```yaml
   - name: Critical operation
     block:
       - name: Do something
         # ...
     rescue:
       - name: Gather diagnostics
         # ...
       - name: Report error with details
         ansible.builtin.fail:
           msg: "Detailed error message"
   ```

5. **Validate early**:
   ```python
   # Validate inputs before processing
   if not inventory_path.exists():
       raise InventoryError(f"File not found: {inventory_path}")

   # Use Pydantic for data validation
   node = Node(**data)  # Raises ValidationError if invalid
   ```

## Troubleshooting Workflow

When encountering an error:

1. **Read the error message carefully**
   - Contains node, task, and error details
   - Includes troubleshooting steps

2. **Check the logs**
   - CLI: `--log-file debug.log`
   - Ansible: Playbook output
   - System: `journalctl -u SERVICE_NAME`

3. **Verify prerequisites**
   - Tailscale running and authenticated
   - SSH connectivity
   - Required ports available
   - Sufficient disk space and memory

4. **Test connectivity**
   - Tailscale: `tailscale ping IP`
   - SSH: `ssh user@IP`
   - API: `curl -k https://IP:6443`

5. **Review configuration**
   - Inventory file syntax
   - Variable values
   - Node definitions

6. **Fix and retry**
   - Address the root cause
   - Re-run the playbook (idempotent)
   - Monitor logs for success

## Getting Help

If you encounter an error that's not covered here:

1. **Enable verbose logging**:
   ```bash
   cluster-mgr COMMAND --verbose --log-file debug.log
   ```

2. **Run pre-flight checks**:
   ```bash
   ansible-playbook ansible/playbooks/preflight_checks.yml -i ansible/inventory/hosts.yml
   ```

3. **Gather diagnostic information**:
   - Error message and stack trace
   - Relevant log files
   - System information (OS, versions)
   - Network configuration

4. **Check documentation**:
   - README.md
   - TROUBLESHOOTING.md
   - CLI_REFERENCE.md

5. **Search for similar issues**:
   - Check project issues
   - Search error messages online
   - Review Kubernetes/K3s documentation
