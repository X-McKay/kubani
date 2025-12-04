#!/bin/bash
# Script to provision the Kubernetes cluster
# This wraps the Ansible playbook execution with proper environment setup

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Kubernetes Cluster Provisioning${NC}"
echo -e "${BLUE}========================================${NC}\n"

INVENTORY_FILE="ansible/inventory/hosts.yml"

# Check if inventory exists
if [ ! -f "$INVENTORY_FILE" ]; then
    echo -e "${RED}Error: Inventory file not found: $INVENTORY_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}Using inventory:${NC} $INVENTORY_FILE\n"

# Show nodes that will be provisioned
echo -e "${BLUE}Nodes to be provisioned:${NC}"
grep -E "^\s+[a-zA-Z0-9_-]+:" "$INVENTORY_FILE" | grep -v "hosts:" | sed 's/://g' | awk '{print "  - " $1}'
echo ""

# Run the playbook
echo -e "${BLUE}Starting cluster provisioning...${NC}\n"

# Set Ansible environment variables
export ANSIBLE_ROLES_PATH="$(pwd)/ansible/roles"

uv run ansible-playbook \
    -i "$INVENTORY_FILE" \
    ansible/playbooks/provision_cluster.yml \
    "$@"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Cluster provisioned successfully!${NC}"
    echo -e "${GREEN}========================================${NC}\n"

    echo -e "${BLUE}Next steps:${NC}"
    echo -e "  1. Check cluster status:"
    echo -e "     ${BLUE}uv run cluster-mgr status${NC}"
    echo -e ""
    echo -e "  2. Launch the TUI:"
    echo -e "     ${BLUE}uv run cluster-tui${NC}"
    echo -e ""
    echo -e "  3. Use kubectl:"
    echo -e "     ${BLUE}export KUBECONFIG=~/.kube/config${NC}"
    echo -e "     ${BLUE}kubectl get nodes${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Cluster provisioning failed${NC}"
    echo -e "${RED}========================================${NC}\n"

    echo -e "${YELLOW}Check the error messages above for details.${NC}"
    echo -e "${YELLOW}You can re-run provisioning - it's idempotent.${NC}\n"
fi

exit $EXIT_CODE
