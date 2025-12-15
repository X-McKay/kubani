# Add New Node to Cluster

Help the user add a new node to the Kubernetes cluster. This command handles the full workflow:
1. Discover the node on Tailscale
2. Add it to the Ansible inventory
3. Run the bootstrap playbook
4. Run preflight checks
5. Add the node to the cluster

## Instructions

When the user runs this command, follow these steps:

### Step 1: Discover the Node

First, check if the node is visible on the Tailscale network:

```bash
tailscale status | grep -i <node_name>
```

If the node is not found, inform the user they need to:
1. Install Tailscale on the target node: `curl -fsSL https://tailscale.com/install.sh | sh`
2. Authenticate Tailscale: `sudo tailscale up`
3. Then retry this command

### Step 2: Get Node Details

Ask the user for any missing information:
- **Node name**: The hostname (should match Tailscale name)
- **Role**: worker (default) or control-plane
- **Reserved CPU**: CPU cores to reserve for local use (default: "2")
- **Reserved Memory**: Memory to reserve (default: "4Gi")
- **GPU**: Does the node have a GPU? (default: false)
- **Labels**: Any custom labels (optional)

### Step 3: Update Inventory

Add the node to `ansible/inventory/hosts.yml`:
- Add to the `workers` group (or `control_plane` if specified)
- Add to the `bootstrap` group for tracking
- Include the Tailscale IP from step 1
- Include any specified reserved resources and labels

### Step 4: Setup SSH Access

Check if SSH key access exists:
```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 <tailscale_ip> echo "SSH OK" 2>/dev/null
```

If SSH key access doesn't exist, instruct the user to run:
```bash
ssh-copy-id <user>@<tailscale_ip>
```

### Step 5: Run Bootstrap Playbook

Run the bootstrap playbook to prepare the node:
```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/bootstrap_node.yml --limit <node_name>
```

This will:
- Update system packages
- Install required dependencies
- Configure SSH hardening
- Set up firewall rules
- Configure kernel parameters for Kubernetes
- Disable swap

### Step 6: Run Preflight Checks

Validate the node is ready:
```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/preflight_checks.yml --limit <node_name>
```

### Step 7: Add Node to Cluster

Add the node to the Kubernetes cluster:
```bash
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/add_node.yml --limit "<node_name>,sparky"
```

Note: Include `sparky` (or the control plane node) to fetch the join token.

### Step 8: Verify

Confirm the node joined successfully:
```bash
KUBECONFIG=/home/al/.kube/config kubectl get nodes
```

## Example Usage

User: `/add-node strix`

This will guide through adding a node named "strix" to the cluster.

## Troubleshooting

If any step fails:

- **SSH connection failed**: Run `ssh-copy-id <user>@<ip>` manually
- **Bootstrap failed**: Check the error message, often it's a package or network issue
- **Preflight failed**: Usually indicates missing Tailscale auth or network issues
- **Add node failed**: Check control plane health with `kubectl get nodes`

## Files Modified

- `ansible/inventory/hosts.yml` - Node added to inventory
- Target node system configuration via Ansible
