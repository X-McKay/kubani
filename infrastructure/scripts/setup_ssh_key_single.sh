#!/bin/bash
# Script to copy SSH key to a single cluster node
# Usage: ./scripts/setup_ssh_key_single.sh <ip_address> [username] [port]

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check arguments
if [ $# -lt 1 ]; then
    echo -e "${RED}Error: IP address required${NC}"
    echo "Usage: $0 <ip_address> [username] [port]"
    echo "Example: $0 100.71.65.62"
    echo "Example: $0 100.71.65.62 myuser"
    echo "Example: $0 100.71.65.62 myuser 2222"
    exit 1
fi

NODE_IP="$1"
SSH_USER="${2:-$USER}"
SSH_PORT="${3:-22}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}SSH Key Setup for Single Node${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${BLUE}Target:${NC} ${SSH_USER}@${NODE_IP}:${SSH_PORT}\n"

# Check if SSH key exists
if [ ! -f ~/.ssh/id_ed25519.pub ]; then
    echo -e "${YELLOW}No SSH key found. Generating one...${NC}"
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
    echo -e "${GREEN}✓ SSH key generated${NC}\n"
fi

# Copy key to node
echo -e "${BLUE}Copying SSH key to node...${NC}"
echo -e "${YELLOW}You will be prompted for the password.${NC}\n"

if ssh-copy-id -i ~/.ssh/id_ed25519.pub -p "$SSH_PORT" "${SSH_USER}@${NODE_IP}"; then
    echo -e "\n${GREEN}✓ Successfully copied key to ${NODE_IP}${NC}\n"

    # Test connection
    echo -e "${BLUE}Testing SSH connection...${NC}"
    if ssh -p "$SSH_PORT" -o BatchMode=yes -o ConnectTimeout=5 "${SSH_USER}@${NODE_IP}" "echo 'Connection successful'" 2>/dev/null; then
        echo -e "${GREEN}✓ SSH connection verified!${NC}\n"
    else
        echo -e "${YELLOW}⚠ Could not verify connection${NC}\n"
    fi
else
    echo -e "\n${RED}✗ Failed to copy key to ${NODE_IP}${NC}\n"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo -e "${BLUE}========================================${NC}"
