#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INVENTORY_FILE="$REPO_ROOT/infrastructure/ansible/inventory/hosts.yml"
KNOWN_HOSTS="${HOME}/.ssh/known_hosts"

if [[ ! -f "$INVENTORY_FILE" ]]; then
    echo "Inventory file not found: $INVENTORY_FILE"
    exit 1
fi

mkdir -p "${HOME}/.ssh"
touch "$KNOWN_HOSTS"

ips=$(ansible-inventory -i "$INVENTORY_FILE" --list | jq -r '._meta.hostvars | to_entries[] | .value.ansible_host // empty' | sort -u)

if [[ -z "$ips" ]]; then
    echo "No ansible_host entries found in inventory"
    exit 1
fi

for ip in $ips; do
    ssh-keygen -R "$ip" >/dev/null 2>&1 || true
    ssh-keyscan -H "$ip" >> "$KNOWN_HOSTS"
done

echo "Updated known_hosts for inventory IPs"
