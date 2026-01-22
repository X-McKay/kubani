#!/bin/bash
# Script to configure passwordless sudo on cluster nodes
# This is the standard approach for automation

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Setup Passwordless Sudo${NC}"
echo -e "${BLUE}========================================${NC}\n"

INVENTORY_FILE="ansible/inventory/hosts.yml"

if [ ! -f "$INVENTORY_FILE" ]; then
    echo -e "${RED}Error: Inventory file not found: $INVENTORY_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}This will configure passwordless sudo on all cluster nodes.${NC}"
echo -e "${BLUE}This is the standard approach for Kubernetes automation.${NC}\n"

# Extract node IPs and hostnames
echo -e "${BLUE}Nodes to configure:${NC}"
grep -B1 "ansible_host:" "$INVENTORY_FILE" | grep -E "^\s+[a-zA-Z0-9_-]+:" | sed 's/://g' | awk '{print $1}' | while read hostname; do
    ip=$(grep -A1 "^[[:space:]]*${hostname}:" "$INVENTORY_FILE" | grep "ansible_host:" | awk '{print $2}')
    echo "  - $hostname ($ip)"
done
echo ""

SSH_USER="${USER}"

echo -e "${YELLOW}For each node, run these commands:${NC}\n"

grep -B1 "ansible_host:" "$INVENTORY_FILE" | grep -E "^\s+[a-zA-Z0-9_-]+:" | sed 's/://g' | awk '{print $1}' | while read hostname; do
    ip=$(grep -A1 "^[[:space:]]*${hostname}:" "$INVENTORY_FILE" | grep "ansible_host:" | awk '{print $2}')

    echo -e "${BLUE}# Configure $hostname:${NC}"
    echo "ssh $SSH_USER@$ip"
    echo "echo '$SSH_USER ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/$SSH_USER"
    echo "sudo chmod 0440 /etc/sudoers.d/$SSH_USER"
    echo "exit"
    echo ""
done

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}After configuring all nodes, test with:${NC}"
echo -e "  ${BLUE}uv run ansible all -i ansible/inventory/hosts.yml -m ping${NC}"
echo ""
echo -e "${YELLOW}Then provision the cluster:${NC}"
echo -e "  ${BLUE}./scripts/provision_cluster.sh${NC}"
echo -e "${YELLOW}========================================${NC}"
