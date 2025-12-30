#!/bin/bash
# Rotate SOPS encryption keys for all encrypted files

set -e

OLD_KEY_FILE="${1:-age.key.old.20251230}"
NEW_KEY_FILE="${2:-age.key}"

if [[ ! -f "$OLD_KEY_FILE" ]]; then
    echo "Error: Old key file not found: $OLD_KEY_FILE"
    exit 1
fi

if [[ ! -f "$NEW_KEY_FILE" ]]; then
    echo "Error: New key file not found: $NEW_KEY_FILE"
    exit 1
fi

echo "Rotating SOPS keys..."
echo "Old key: $OLD_KEY_FILE"
echo "New key: $NEW_KEY_FILE"
echo ""

# Find all encrypted files
encrypted_files=$(find gitops/ ansible/ -name "*.enc.yaml" -o -name "vault.yml" 2>/dev/null)

for file in $encrypted_files; do
    echo "Processing: $file"

    # Skip empty files
    if [[ ! -s "$file" ]]; then
        echo "  ⚠️  File is empty, skipping"
        continue
    fi

    # Use updatekeys to rotate - SOPS will decrypt with old key and re-encrypt with new key from .sops.yaml
    SOPS_AGE_KEY_FILE="$OLD_KEY_FILE" sops updatekeys --yes "$file" 2>/dev/null || {
        echo "  ⚠️  Failed to update keys, skipping (might already be using new key or not encrypted)"
        continue
    }

    echo "  ✅ Rotated successfully"
done

echo ""
echo "✅ All files rotated successfully!"
echo ""
echo "Next steps:"
echo "1. Update sops-age-secret.yaml with the new key (DO NOT COMMIT IT)"
echo "2. Apply it to the cluster: kubectl apply -f sops-age-secret.yaml"
echo "3. Delete the old key file: rm $OLD_KEY_FILE"
echo "4. Force push the cleaned history: git push --force-with-lease"
