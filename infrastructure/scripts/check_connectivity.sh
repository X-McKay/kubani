#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INVENTORY_FILE="$REPO_ROOT/infrastructure/ansible/inventory/hosts.yml"
SSH_USER="${1:-$USER}"

if [[ ! -f "$INVENTORY_FILE" ]]; then
    echo "Inventory file not found: $INVENTORY_FILE"
    exit 1
fi

echo "Testing SSH access as $SSH_USER"
echo ""

ips=$(grep -E "ansible_host: [0-9.]+" "$INVENTORY_FILE" | awk '{print $2}')

for ip in $ips; do
    printf "%s ... " "$ip"
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_USER@$ip" "echo ok" >/dev/null 2>&1; then
        echo "ok"
    else
        echo "failed"
    fi
done

echo ""
uv run ansible all -i "$INVENTORY_FILE" -m ping -u "$SSH_USER"
