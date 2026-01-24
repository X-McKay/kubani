# Node Bootstrap Guide

This guide explains how to use the bootstrap playbook to prepare new nodes for Kubernetes cluster membership.

## Overview

The bootstrap playbook (`ansible/playbooks/bootstrap_node.yml`) prepares a fresh Ubuntu/Debian node by:

- Updating system packages
- Installing required dependencies
- Installing and configuring Tailscale
- Setting up SSH key authentication
- Configuring system settings (timezone, hostname, kernel parameters)
- Setting up basic firewall rules
- Disabling swap (required for Kubernetes)

## Prerequisites

Before running the bootstrap playbook:

1. **Target node requirements:**
   - Ubuntu 20.04+ or Debian 11+ installed
   - Network connectivity (can reach the internet)
   - SSH server running
   - A user account with sudo privileges

2. **Management machine requirements:**
   - Ansible installed (via mise)
   - SSH access to the target node (password or key-based)
   - Your SSH public key available (typically `~/.ssh/id_ed25519.pub`)

## Quick Start

### 1. Add the Node to Inventory

Add the new node to `ansible/inventory/hosts.yml`:

```yaml
all:
  children:
    workers:
      hosts:
        new-node:
          ansible_host: <node-ip-or-hostname>
          tailscale_ip: <will-be-updated-after-tailscale-setup>
          reserved_cpu: "2"
          reserved_memory: "4Gi"
          node_labels:
            node-role: worker

    # Optional: Add to bootstrap group for easy targeting
    bootstrap:
      hosts:
        new-node: {}
```

### 2. Run the Bootstrap Playbook

**With password authentication (typical for first run):**

```bash
ansible-playbook -i ansible/inventory/hosts.yml \
  ansible/playbooks/bootstrap_node.yml \
  --limit new-node \
  --ask-pass \
  --ask-become-pass
```

**With existing SSH key:**

```bash
ansible-playbook -i ansible/inventory/hosts.yml \
  ansible/playbooks/bootstrap_node.yml \
  --limit new-node
```

**With Tailscale auth key (for fully automated setup):**

```bash
ansible-playbook -i ansible/inventory/hosts.yml \
  ansible/playbooks/bootstrap_node.yml \
  --limit new-node \
  -e "tailscale_authkey=tskey-auth-xxxxx"
```

### 3. Complete Tailscale Setup

If you didn't provide a Tailscale auth key, SSH to the node and authenticate:

```bash
ssh user@new-node
sudo tailscale up
```

Get the Tailscale IP:

```bash
tailscale ip -4
```

### 4. Update Inventory

Update the `tailscale_ip` in the inventory file with the actual Tailscale IP.

### 5. Validate and Provision

Run preflight checks:

```bash
ansible-playbook -i ansible/inventory/hosts.yml \
  ansible/playbooks/preflight_checks.yml \
  --limit new-node
```

Add the node to the cluster:

```bash
ansible-playbook -i ansible/inventory/hosts.yml \
  ansible/playbooks/add_node.yml \
  --limit new-node
```

Or use the CLI:

```bash
cluster-mgr provision --limit new-node
```

## Playbook Options

### Tags

Run specific parts of the bootstrap process:

```bash
# Only install packages
ansible-playbook ... --tags packages

# Only configure SSH
ansible-playbook ... --tags ssh

# Skip firewall configuration
ansible-playbook ... --skip-tags firewall
```

Available tags:
- `system` - System updates and configuration
- `update` - Package updates only
- `packages` - Package installation
- `tailscale` - Tailscale installation
- `ssh` - SSH configuration
- `security` - Security-related tasks (SSH hardening, firewall)
- `firewall` - UFW firewall setup
- `config` - System configuration
- `validation` - Final validation checks

### Variables

Override default behavior with extra variables:

```bash
# Use a different SSH key
ansible-playbook ... -e "ssh_public_key_file=~/.ssh/id_rsa.pub"

# Set timezone
ansible-playbook ... -e "system_timezone=UTC"

# Skip system upgrade
ansible-playbook ... -e "perform_system_upgrade=false"

# Auto-reboot if required after updates
ansible-playbook ... -e "auto_reboot_if_required=true"

# Disable firewall configuration
ansible-playbook ... -e "configure_ufw=false"

# Provide Tailscale auth key
ansible-playbook ... -e "tailscale_authkey=tskey-auth-xxxxx"
```

### Default Variables

See all configurable options in `ansible/roles/bootstrap/defaults/main.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ssh_public_key_file` | `~/.ssh/id_ed25519.pub` | SSH public key to deploy |
| `ssh_password_authentication` | `no` | Disable password auth after key setup |
| `tailscale_install` | `true` | Install Tailscale |
| `tailscale_authkey` | `""` | Tailscale auth key for automated setup |
| `system_timezone` | `America/New_York` | System timezone |
| `perform_system_upgrade` | `true` | Run apt upgrade |
| `auto_reboot_if_required` | `false` | Auto-reboot after kernel updates |
| `configure_ufw` | `true` | Configure UFW firewall |

## What the Bootstrap Playbook Does

### 1. System Update (`system_update.yml`)

- Updates apt cache
- Upgrades all packages (if `perform_system_upgrade` is true)
- Checks if reboot is required
- Optionally reboots (if `auto_reboot_if_required` is true)

### 2. Package Installation (`install_packages.yml`)

Installs essential packages:
- curl, wget, git, vim, htop, tmux, jq
- apt-transport-https, ca-certificates, gnupg
- python3, python3-pip
- net-tools, dnsutils
- iptables, ipset, conntrack, socat (for Kubernetes)
- nfs-common (for NFS storage)

### 3. Tailscale Installation (`install_tailscale.yml`)

- Downloads and runs the official Tailscale install script
- Starts and enables the tailscaled service
- Optionally authenticates with provided auth key

### 4. SSH Configuration (`ssh_setup.yml`)

- Deploys SSH public key to authorized_keys
- Configures SSH daemon (disables root login, enables pubkey auth)
- Optionally disables password authentication
- Configures passwordless sudo for the ansible user

### 5. System Configuration (`system_config.yml`)

- Sets hostname to match inventory name
- Configures timezone and locale
- Enables IP forwarding
- Loads kernel modules (br_netfilter, overlay)
- Configures bridge networking for Kubernetes
- Disables swap

### 6. Firewall Setup (`firewall_setup.yml`)

- Installs and enables UFW
- Sets default policies (deny incoming, allow outgoing)
- Opens required ports (SSH, Tailscale)
- Allows Tailscale network traffic

### 7. Validation (`validate.yml`)

- Verifies all services are running
- Checks Tailscale status
- Validates swap is disabled
- Reports system resources
- Provides next steps

## Troubleshooting

### SSH Connection Failed

If you can't connect via SSH:

```bash
# Test connectivity
ping <node-ip>

# Test SSH with verbose output
ssh -v user@<node-ip>

# Ensure SSH service is running on the node
sudo systemctl status ssh
```

### Tailscale Not Authenticating

If Tailscale fails to authenticate:

1. Check if the auth key is valid and not expired
2. SSH to the node and run manually:
   ```bash
   sudo tailscale up --authkey=<your-key>
   ```
3. Check Tailscale logs:
   ```bash
   sudo journalctl -u tailscaled -f
   ```

### Package Installation Failures

If packages fail to install:

```bash
# Check apt status
sudo apt update
sudo apt --fix-broken install

# Check disk space
df -h
```

### Firewall Blocking Traffic

If services are unreachable after bootstrap:

```bash
# Check UFW status
sudo ufw status verbose

# Temporarily disable to test
sudo ufw disable

# Re-enable and add rules
sudo ufw enable
sudo ufw allow from 100.64.0.0/10
```

## Security Considerations

The bootstrap playbook applies basic security hardening:

1. **SSH Hardening:**
   - Disables root login
   - Disables password authentication (after key is deployed)
   - Enables public key authentication only

2. **Firewall:**
   - Default deny incoming
   - Only allows SSH and Tailscale
   - Allows all traffic from Tailscale network

3. **Sudo:**
   - Configures passwordless sudo for ansible user
   - Required for automated provisioning

For production environments, consider additional hardening:
- Fail2ban for SSH brute-force protection
- Automatic security updates
- Log forwarding
- Intrusion detection

## Integration with Cluster Provisioning

The bootstrap playbook is designed to complement the existing provisioning workflow:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Fresh Node     │────▶│  bootstrap_node  │────▶│  Bootstrapped   │
│  (Ubuntu/Debian)│     │  .yml            │     │  Node           │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Cluster Node   │◀────│  add_node.yml /  │◀────│  preflight_     │
│  (K3s Worker)   │     │  site.yml        │     │  checks.yml     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

The bootstrap playbook handles everything needed before `preflight_checks.yml`:
- Tailscale installation (prerequisites role assumes it exists)
- SSH key setup (for passwordless automation)
- Basic system preparation

After bootstrap, the standard provisioning workflow takes over.
