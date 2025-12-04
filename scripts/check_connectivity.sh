#!/bin/bash
# Script to check SSH and Ansible connectivity to cluster nodes
# Usage: ./scripts/check_connectivity.sh [username]

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

INVENTORY_FILE="ansible/inventory/hosts.yml"
SSH_USER="${1:-$USER}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Cluster Connectivity Check${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check if inventory exists
if [ ! -f "$INVENTORY_FILE" ]; then
    echo -e "${RED}Error: Inventory file not found: $INVENTORY_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}Using inventory:${NC} $INVENTORY_FILE"
echo -e "${BLUE}SSH user:${NC} $SSH_USER\n"

# Extract nodes from inventory
echo -e "${BLUE}Extracting nodes from inventory...${NC}\n"

NODES=$(grep -E "^\s+[a-zA-Z0-9_-]+:" "$INVENTORY_FILE" | grep -v "hosts:" | sed 's/://g' | awk '{print $1}')
NODE_IPS=$(grep -E "ansible_host: [0-9.]+" "$INVENTORY_FILE" | awk '{print $2}')

if [ -z "$NODES" ] || [ -z "$NODE_IPS" ]; then
    echo -e "${RED}Error: No nodes found in inventory${NC}"
    exit 1
fi

# Create arrays
NODE_ARRAY=($NODES)
IP_ARRAY=($NODE_IPS)

echo -e "${BLUE}Found ${#NODE_ARRAY[@]} nodes:${NC}"
for i in "${!NODE_ARRAY[@]}"; do
    echo "  ${NODE_ARRAY[$i]} - ${IP_ARRAY[$i]}"
done
echo ""

# Test SSH connectivity to each node
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Testing SSH Connectivity${NC}"
echo -e "${BLUE}========================================${NC}\n"

SUCCESS_COUNT=0
FAIL_COUNT=0

for i in "${!NODE_ARRAY[@]}"; do
    NODE="${NODE_ARRAY[$i]}"
    IP="${IP_ARRAY[$i]}"

    echo -n "Testing ${NODE} (${IP})... "

    if ssh -o BatchMode=yes -o ConnectTimeout=5 "${SSH_USER}@${IP}" "echo 'OK'" >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Connected${NC}"
        ((SUCCESS_COUNT++))
    else
        echo -e "${RED}✗ Failed${NC}"
        ((FAIL_COUNT++))
    fi
done

echo ""

# Test Ansible connectivity
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Testing Ansible Connectivity${NC}"
echo -e "${BLUE}========================================${NC}\n"

if command -v ansible >/dev/null 2>&1; then
    if uv run ansible all -i "$INVENTORY_FILE" -m ping -u "$SSH_USER" 2>&1 | grep -q "SUCCESS"; then
        echo -e "\n${GREEN}✓ Ansible can reach all nodes${NC}\n"
    else
        echo -e "\n${YELLOW}⚠ Ansible connectivity issues detected${NC}\n"
    fi
else
    echo -e "${YELLOW}⚠ Ansible not found, skipping Ansible test${NC}\n"
fi

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Summary${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "Total nodes: ${#NODE_ARRAY[@]}"
echo -e "${GREEN}Successful: ${SUCCESS_COUNT}${NC}"
echo -e "${RED}Failed: ${FAIL_COUNT}${NC}\n"

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ All nodes are accessible!${NC}"
    echo -e "\nYou can now provision the cluster with:"
    echo -e "  ${BLUE}uv run cluster-mgr provision${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ Some nodes are not accessible${NC}"
    echo -e "\nTo set up SSH keys for a node, run:"
    echo -e "  ${BLUE}./scripts/setup_ssh_key_single.sh <ip_address> [username] [port]${NC}"
    exit 1
fi
