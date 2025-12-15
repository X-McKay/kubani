# Bootstrap a New Node

Prepare a new node for Kubernetes cluster membership without actually adding it to the cluster.

This is useful when you want to:
- Prepare multiple nodes before adding them
- Test the bootstrap process
- Set up a node that will be added later

## Instructions

### Step 1: Verify Tailscale Connectivity

Check the node is on the Tailscale network:
```bash
tailscale status | grep -i <node_name>
```

Get the Tailscale IP address for the node.

### Step 2: Ensure Node is in Inventory

Check if the node exists in `ansible/inventory/hosts.yml`. If not, add it:

```yaml
workers:
  hosts:
    <node_name>:
      ansible_host: <tailscale_ip>
      tailscale_ip: <tailscale_ip>
      reserved_cpu: "2"
      reserved_memory: "4Gi"
      node_labels:
        node-role: worker
        workstation: "true"

bootstrap:
  hosts:
    <node_name>: {}
```

### Step 3: Setup SSH Access

Test SSH connectivity:
```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 <tailscale_ip> echo "SSH OK" 2>/dev/null
```

If it fails, have the user run: `ssh-copy-id <user>@<tailscale_ip>`

### Step 4: Run Bootstrap Playbook

```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap_node.yml --limit <node_name>
```

### Step 5: Validate

Run preflight checks to confirm the node is ready:
```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/preflight_checks.yml --limit <node_name>
```

## What Bootstrap Does

- Updates system packages
- Installs: curl, git, vim, htop, jq, iptables, conntrack, etc.
- Configures Tailscale (installs if missing)
- Sets up SSH key authentication
- Hardens SSH (disables password auth, root login)
- Configures passwordless sudo
- Sets hostname and timezone
- Enables IP forwarding and bridge netfilter
- Loads kernel modules (br_netfilter, overlay)
- Disables swap
- Configures UFW firewall

## Next Steps

After bootstrap, add the node to the cluster with:
```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/add_node.yml --limit "<node_name>,sparky"
```

Or use the `/add-node` command.
