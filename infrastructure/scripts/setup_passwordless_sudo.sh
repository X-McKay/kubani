#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INVENTORY_FILE="$REPO_ROOT/infrastructure/ansible/inventory/hosts.yml"
SSH_USER="${USER}"

if [[ ! -f "$INVENTORY_FILE" ]]; then
    echo "Inventory file not found: $INVENTORY_FILE"
    exit 1
fi

echo "Run the following on each node:"
echo ""

grep -B1 "ansible_host:" "$INVENTORY_FILE" | grep -E "^\s+[a-zA-Z0-9_-]+:" | sed 's/://g' | awk '{print $1}' | while read -r hostname; do
    ip=$(grep -A1 "^[[:space:]]*${hostname}:" "$INVENTORY_FILE" | grep "ansible_host:" | awk '{print $2}')
    echo "# $hostname ($ip)"
    echo "ssh $SSH_USER@$ip"
    echo "echo '$SSH_USER ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/$SSH_USER"
    echo "sudo chmod 0440 /etc/sudoers.d/$SSH_USER"
    echo "exit"
    echo ""
done

echo "Then validate with:"
echo "uv run ansible all -i $INVENTORY_FILE -m ping"
