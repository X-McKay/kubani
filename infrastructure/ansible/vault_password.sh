#!/bin/bash
# Vault password retrieval script
# This reads the vault password from macOS Keychain

# Retrieve password from keychain
security find-generic-password -w -s "ansible-vault" -a "$USER" 2>/dev/null

# If not found, prompt user to set it up
if [ $? -ne 0 ]; then
    echo "Ansible vault password not found in keychain." >&2
    echo "Run: ./scripts/setup_vault.sh" >&2
    exit 1
fi
