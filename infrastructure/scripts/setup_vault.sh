#!/bin/bash
# Script to set up Ansible Vault for secure password storage

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Ansible Vault Setup${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${BLUE}This script will:${NC}"
echo "  1. Store your vault password in macOS Keychain"
echo "  2. Create an encrypted vault file for your sudo password"
echo "  3. Configure Ansible to use the vault"
echo ""

# Step 1: Store vault password in keychain
echo -e "${BLUE}Step 1: Setting up vault password${NC}"
echo "Enter a password to encrypt your Ansible vault (this will be stored in Keychain):"
read -s VAULT_PASSWORD
echo ""

# Store in keychain (delete existing first if present)
security delete-generic-password -s "ansible-vault" -a "$USER" 2>/dev/null || true
security add-generic-password -s "ansible-vault" -a "$USER" -w "$VAULT_PASSWORD"

echo -e "${GREEN}✓ Vault password stored in Keychain${NC}\n"

# Step 2: Create vault file with sudo password
echo -e "${BLUE}Step 2: Creating encrypted vault for sudo password${NC}"
echo "Enter your sudo password (for cluster nodes):"
read -s SUDO_PASSWORD
echo ""

# Create vault file
VAULT_FILE="ansible/group_vars/all/vault.yml"
mkdir -p "$(dirname "$VAULT_FILE")"

cat > /tmp/vault_temp.yml << EOF
---
# Encrypted vault file - DO NOT COMMIT UNENCRYPTED
ansible_become_password: "$SUDO_PASSWORD"
EOF

# Encrypt the file
uv run ansible-vault encrypt /tmp/vault_temp.yml --vault-password-file=ansible/vault_password.sh --output="$VAULT_FILE"
rm /tmp/vault_temp.yml

echo -e "${GREEN}✓ Encrypted vault created at $VAULT_FILE${NC}\n"

# Step 3: Update ansible.cfg
echo -e "${BLUE}Step 3: Configuring Ansible${NC}"

# Make vault_password.sh executable
chmod +x ansible/vault_password.sh

# Update ansible.cfg to use vault
if ! grep -q "vault_password_file" ansible/ansible.cfg; then
    sed -i.bak '/\[defaults\]/a\
vault_password_file = vault_password.sh
' ansible/ansible.cfg
    echo -e "${GREEN}✓ Updated ansible.cfg${NC}\n"
else
    echo -e "${YELLOW}⚠ ansible.cfg already configured${NC}\n"
fi

# Update .gitignore
if [ -f .gitignore ]; then
    if ! grep -q "vault_password.sh" .gitignore; then
        echo "" >> .gitignore
        echo "# Ansible vault password script (uses keychain)" >> .gitignore
        echo "ansible/vault_password.sh" >> .gitignore
    fi
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Vault setup complete!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "${BLUE}What was configured:${NC}"
echo "  • Vault password stored in macOS Keychain (service: ansible-vault)"
echo "  • Sudo password encrypted in: $VAULT_FILE"
echo "  • Ansible configured to auto-decrypt using Keychain"
echo ""
echo -e "${BLUE}Usage:${NC}"
echo "  • Run playbooks normally - no password prompts needed"
echo "  • To update sudo password: uv run ansible-vault edit $VAULT_FILE"
echo "  • To view vault: uv run ansible-vault view $VAULT_FILE"
echo "  • To remove from Keychain: security delete-generic-password -s ansible-vault -a $USER"
echo ""
echo -e "${YELLOW}Security notes:${NC}"
echo "  • The vault file is encrypted and safe to commit to git"
echo "  • The vault password is stored in your macOS Keychain"
echo "  • Only your user account can access the Keychain password"
echo ""
