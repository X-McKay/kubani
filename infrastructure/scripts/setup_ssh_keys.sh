#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INVENTORY_FILE="$REPO_ROOT/infrastructure/ansible/inventory/hosts.yml"

if [[ ! -f "$HOME/.ssh/id_ed25519.pub" ]]; then
    ssh-keygen -t ed25519 -f "$HOME/.ssh/id_ed25519" -N ""
fi

if [[ ! -f "$INVENTORY_FILE" ]]; then
    echo "Inventory file not found: $INVENTORY_FILE"
    exit 1
fi

read -r -p "SSH username [$USER]: " SSH_USER
SSH_USER="${SSH_USER:-$USER}"
read -r -p "SSH port [22]: " SSH_PORT
SSH_PORT="${SSH_PORT:-22}"

ips=$(grep -E "ansible_host: [0-9.]+" "$INVENTORY_FILE" | awk '{print $2}')

for ip in $ips; do
    ssh-copy-id -i "$HOME/.ssh/id_ed25519.pub" -p "$SSH_PORT" "$SSH_USER@$ip"
done

uv run ansible all -i "$INVENTORY_FILE" -m ping -u "$SSH_USER"
