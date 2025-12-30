#!/bin/bash
# Verify that files matching *.enc.yaml are actually encrypted with SOPS

set -e

EXIT_CODE=0

for file in "$@"; do
    # Check if file contains SOPS metadata
    if ! grep -q "sops:" "$file" || ! grep -q "age:" "$file"; then
        echo "ERROR: $file appears to be unencrypted (missing SOPS metadata)"
        echo "  Files with .enc.yaml extension MUST be encrypted with SOPS"
        echo "  Run: SOPS_AGE_KEY_FILE=age.key sops --encrypt $file > ${file}.tmp && mv ${file}.tmp $file"
        EXIT_CODE=1
    fi

    # Check if file contains obvious plaintext secrets
    if grep -qiE "(password|secret|token|key).*:.*[A-Za-z0-9]{8,}" "$file" | grep -v "ENC\[AES256_GCM"; then
        # Only flag if it looks like an unencrypted secret (not wrapped in ENC[])
        if grep -qiE "(password|secret|token|key).*:\s*['\"]?[A-Za-z0-9]{8,}['\"]?\s*$" "$file"; then
            echo "WARNING: $file may contain plaintext secrets"
            echo "  Please verify the file is properly encrypted"
            EXIT_CODE=1
        fi
    fi
done

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "SOPS encryption check FAILED"
    echo "See https://github.com/mozilla/sops for encryption instructions"
fi

exit $EXIT_CODE
