#!/bin/bash

set -euo pipefail

OLD_KEY_FILE="${1:-age.key.old}"
NEW_KEY_FILE="${2:-age.key}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ ! -f "$OLD_KEY_FILE" ]]; then
    echo "Old key file not found: $OLD_KEY_FILE"
    exit 1
fi

if [[ ! -f "$NEW_KEY_FILE" ]]; then
    echo "New key file not found: $NEW_KEY_FILE"
    exit 1
fi

find "$REPO_ROOT/infrastructure/gitops" "$REPO_ROOT/infrastructure/ansible" \( -name "*.enc.yaml" -o -name "vault.yml" \) | while read -r file; do
    echo "Rotating $file"
    SOPS_AGE_KEY_FILE="$OLD_KEY_FILE" sops updatekeys --yes "$file"
done
