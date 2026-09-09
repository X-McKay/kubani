#!/bin/bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INVENTORY_FILE="$REPO_ROOT/infrastructure/ansible/inventory/hosts.yml"
PLAYBOOK="$REPO_ROOT/infrastructure/ansible/playbooks/provision_cluster.yml"

if [[ ! -f "$INVENTORY_FILE" ]]; then
    echo "Inventory file not found: $INVENTORY_FILE"
    exit 1
fi

export ANSIBLE_ROLES_PATH="$REPO_ROOT/infrastructure/ansible/roles"

uv run ansible-playbook \
    -i "$INVENTORY_FILE" \
    "$PLAYBOOK" \
    "$@"
