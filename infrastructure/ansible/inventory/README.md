# Inventory Guide

Use the example inventories as templates for your homelab.

## Recommended Flow

1. Copy an example to `hosts.yml`.
2. Set Tailscale IPs and SSH users.
3. Adjust topology labels, resource reservations, and GPU flags.
4. Copy the example `group_vars` files you actually need.

```bash
cp infrastructure/ansible/inventory/hosts.yml.example infrastructure/ansible/inventory/hosts.yml
cp infrastructure/ansible/inventory/group_vars/all.yml.example infrastructure/ansible/inventory/group_vars/all.yml
```

Validate before provisioning:

```bash
just inventory
just ansible-ping
```
