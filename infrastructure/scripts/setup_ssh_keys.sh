#!/bin/bash
# Script to copy SSH keys to cluster nodes
# This uses ssh-copy-id which will prompt for password interactively

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}SSH Key Setup for Cluster Nodes${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check if SSH key exists
if [ ! -f ~/.ssh/id_ed25519.pub ]; then
    echo -e "${YELLOW}No SSH key found. Generating one...${NC}"
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
    echo -e "${GREEN}✓ SSH key generated${NC}\n"
fi

# Read nodes from inventory
INVENTORY_FILE="ansible/inventory/hosts.yml"

if [ ! -f "$INVENTORY_FILE" ]; then
    echo "Error: Inventory file not found: $INVENTORY_FILE"
    exit 1
fi

# Extract node IPs from inventory (simple grep approach)
echo -e "${BLUE}Nodes found in inventory:${NC}"
NODES=$(grep -E "ansible_host: [0-9.]+" "$INVENTORY_FILE" | awk '{print $2}')

if [ -z "$NODES" ]; then
    echo "Error: No nodes found in inventory"
    exit 1
fi

echo "$NODES" | while read -r ip; do
    echo "  - $ip"
done
echo ""

# Prompt for username
read -p "Enter SSH username for the nodes [default: $USER]: " SSH_USER
SSH_USER=${SSH_USER:-$USER}

# Prompt for SSH port
read -p "Enter SSH port [default: 22]: " SSH_PORT
SSH_PORT=${SSH_PORT:-22}

echo ""
echo -e "${BLUE}Copying SSH key to each node...${NC}"
echo -e "${YELLOW}You will be prompted for the password for each node.${NC}\n"

# Copy key to each node
echo "$NODES" | while read -r ip; do
    echo -e "${BLUE}Copying key to $ip:$SSH_PORT...${NC}"
    if ssh-copy-id -i ~/.ssh/id_ed25519.pub -p "$SSH_PORT" "${SSH_USER}@${ip}"; then
        echo -e "${GREEN}✓ Successfully copied key to $ip${NC}\n"
    else
        echo -e "${YELLOW}⚠ Failed to copy key to $ip${NC}\n"
    fi
done

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}SSH key setup complete!${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo "Testing connectivity..."
if uv run ansible all -i "$INVENTORY_FILE" -m ping -u "$SSH_USER"; then
    echo -e "\n${GREEN}✓ All nodes are accessible!${NC}"
else
    echo -e "\n${YELLOW}⚠ Some nodes may not be accessible. Check the output above.${NC}"
fi
