#!/bin/bash
# Quickstart script for Kubani - Automated cluster setup
# This script guides you through the initial cluster configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Prompt for user input
prompt() {
    local prompt_text="$1"
    local default_value="$2"
    local result

    if [ -n "$default_value" ]; then
        read -p "$(echo -e ${BLUE}${prompt_text}${NC} [${default_value}]: )" result
        echo "${result:-$default_value}"
    else
        read -p "$(echo -e ${BLUE}${prompt_text}${NC}: )" result
        echo "$result"
    fi
}

# Confirm action
confirm() {
    local prompt_text="$1"
    local response
    read -p "$(echo -e ${YELLOW}${prompt_text}${NC} [y/N]: )" response
    case "$response" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

print_header "Kubani Quickstart Setup"

echo "This script will help you set up your Kubernetes cluster with Kubani."
echo "It will guide you through:"
echo "  1. Prerequisites check"
echo "  2. Tailscale node discovery"
echo "  3. Inventory configuration"
echo "  4. Cluster provisioning"
echo ""

if ! confirm "Continue with setup?"; then
    echo "Setup cancelled."
    exit 0
fi

# Step 1: Check prerequisites
print_header "Step 1: Checking Prerequisites"

# Check for mise
if command_exists mise; then
    print_success "Mise is installed"
else
    print_error "Mise is not installed"
    echo ""
    echo "Install mise with:"
    echo "  curl https://mise.run | sh"
    echo ""
    echo "Then add to your shell:"
    echo "  echo 'eval \"\$(~/.local/bin/mise activate bash)\"' >> ~/.bashrc"
    echo "  source ~/.bashrc"
    exit 1
fi

# Check if tools are installed via mise
print_info "Checking mise tools..."
if mise list | grep -q python; then
    print_success "Python is installed via mise"
else
    print_warning "Python not installed via mise, installing..."
    mise install python
fi

if mise list | grep -q uv; then
    print_success "UV is installed via mise"
else
    print_warning "UV not installed via mise, installing..."
    mise install
fi

# Install Python dependencies
print_info "Installing Python dependencies..."
mise exec -- uv sync
print_success "Python dependencies installed"

# Check for Tailscale
if command_exists tailscale; then
    print_success "Tailscale is installed"

    # Check if Tailscale is running
    if tailscale status >/dev/null 2>&1; then
        print_success "Tailscale is running"
    else
        print_error "Tailscale is not running"
        echo "Start Tailscale with: sudo tailscale up"
        exit 1
    fi
else
    print_error "Tailscale is not installed"
    echo ""
    echo "Install Tailscale:"
    echo "  curl -fsSL https://tailscale.com/install.sh | sh"
    echo "  sudo tailscale up"
    exit 1
fi

# Check for Ansible
print_info "Checking Ansible..."
if mise exec -- ansible --version >/dev/null 2>&1; then
    print_success "Ansible is available"
else
    print_warning "Ansible not found, installing..."
    mise exec -- uv pip install ansible
fi

print_success "All prerequisites met!"

# Step 2: Discover Tailscale nodes
print_header "Step 2: Discovering Tailscale Nodes"

print_info "Scanning Tailscale network for available nodes..."
echo ""

# Run discovery
mise exec -- cluster-mgr discover

echo ""
print_info "These are the nodes available on your Tailscale network."
echo ""

if ! confirm "Did you see your nodes listed above?"; then
    print_error "Please ensure all nodes are connected to Tailscale and try again."
    exit 1
fi

# Step 3: Configure inventory
print_header "Step 3: Configuring Inventory"

INVENTORY_FILE="ansible/inventory/hosts.yml"

if [ -f "$INVENTORY_FILE" ]; then
    print_warning "Inventory file already exists: $INVENTORY_FILE"
    if confirm "Do you want to overwrite it?"; then
        rm "$INVENTORY_FILE"
    else
        print_info "Using existing inventory file"
        if ! confirm "Continue with existing inventory?"; then
            echo "Setup cancelled."
            exit 0
        fi
        SKIP_INVENTORY_CREATION=true
    fi
fi

if [ "$SKIP_INVENTORY_CREATION" != "true" ]; then
    print_info "Let's create your inventory file..."
    echo ""

    # Cluster configuration
    CLUSTER_NAME=$(prompt "Cluster name" "homelab")
    K3S_VERSION=$(prompt "K3s version" "v1.28.5+k3s1")
    GIT_REPO=$(prompt "Git repository URL" "https://github.com/yourusername/kubani.git")
    GIT_BRANCH=$(prompt "Git branch" "main")

    echo ""
    print_info "Control Plane Configuration"
    CONTROL_PLANE_HOST=$(prompt "Control plane hostname")
    CONTROL_PLANE_IP=$(prompt "Control plane Tailscale IP")

    echo ""
    print_info "Worker Nodes Configuration"
    WORKER_COUNT=$(prompt "Number of worker nodes" "1")

    # Create inventory file
    cat > "$INVENTORY_FILE" << EOF
# Kubani Cluster Inventory
# Generated by quickstart script on $(date)

all:
  vars:
    k3s_version: ${K3S_VERSION}
    cluster_name: ${CLUSTER_NAME}
    tailscale_network: 100.64.0.0/10

    # GitOps configuration
    git_repo_url: ${GIT_REPO}
    git_branch: ${GIT_BRANCH}
    flux_namespace: flux-system

  children:
    control_plane:
      hosts:
        ${CONTROL_PLANE_HOST}:
          ansible_host: ${CONTROL_PLANE_IP}
          tailscale_ip: ${CONTROL_PLANE_IP}
          node_labels:
            node-role: control-plane

    workers:
      hosts:
EOF

    # Add worker nodes
    for i in $(seq 1 $WORKER_COUNT); do
        echo ""
        print_info "Worker Node $i"
        WORKER_HOST=$(prompt "  Hostname")
        WORKER_IP=$(prompt "  Tailscale IP")
        WORKER_CPU=$(prompt "  Reserved CPU cores" "2")
        WORKER_MEM=$(prompt "  Reserved memory (e.g., 4Gi)" "4Gi")

        if confirm "  Does this node have a GPU?"; then
            HAS_GPU=true
            GPU_TYPE=$(prompt "  GPU type (e.g., nvidia-rtx-4090)" "nvidia")
        else
            HAS_GPU=false
        fi

        cat >> "$INVENTORY_FILE" << EOF
        ${WORKER_HOST}:
          ansible_host: ${WORKER_IP}
          tailscale_ip: ${WORKER_IP}
          reserved_cpu: "${WORKER_CPU}"
          reserved_memory: "${WORKER_MEM}"
EOF

        if [ "$HAS_GPU" = true ]; then
            cat >> "$INVENTORY_FILE" << EOF
          gpu: true
          node_labels:
            node-role: worker
            gpu: "true"
            gpu-type: ${GPU_TYPE}
            workstation: "true"
          node_taints:
            - key: nvidia.com/gpu
              value: "true"
              effect: NoSchedule
EOF
        else
            cat >> "$INVENTORY_FILE" << EOF
          node_labels:
            node-role: worker
            workstation: "true"
EOF
        fi

        echo "" >> "$INVENTORY_FILE"
    done

    print_success "Inventory file created: $INVENTORY_FILE"
fi

# Copy group_vars examples if they don't exist
print_info "Setting up group variables..."

for file in all.yml control_plane.yml workers.yml; do
    if [ ! -f "ansible/inventory/group_vars/$file" ]; then
        if [ -f "ansible/inventory/group_vars/${file}.example" ]; then
            cp "ansible/inventory/group_vars/${file}.example" "ansible/inventory/group_vars/$file"
            print_success "Created group_vars/$file"
        fi
    else
        print_info "group_vars/$file already exists"
    fi
done

# Step 4: Test SSH connectivity
print_header "Step 4: Testing SSH Connectivity"

print_info "Testing SSH access to all nodes..."
echo ""

if mise exec -- ansible all -i "$INVENTORY_FILE" -m ping; then
    print_success "All nodes are reachable via SSH"
else
    print_error "Some nodes are not reachable"
    echo ""
    echo "Troubleshooting steps:"
    echo "  1. Ensure SSH keys are set up:"
    echo "     ssh-copy-id user@<node-tailscale-ip>"
    echo ""
    echo "  2. Or configure password authentication in ansible.cfg"
    echo ""
    if ! confirm "Continue anyway?"; then
        exit 1
    fi
fi

# Step 5: Review configuration
print_header "Step 5: Review Configuration"

echo "Your cluster configuration:"
echo ""
echo "  Cluster Name: $CLUSTER_NAME"
echo "  K3s Version: $K3S_VERSION"
echo "  Control Plane: $CONTROL_PLANE_HOST ($CONTROL_PLANE_IP)"
echo "  Worker Nodes: $WORKER_COUNT"
echo "  Git Repository: $GIT_REPO"
echo ""

if [ -f "$INVENTORY_FILE" ]; then
    echo "Inventory file: $INVENTORY_FILE"
    echo ""
    if confirm "View inventory file?"; then
        cat "$INVENTORY_FILE"
        echo ""
    fi
fi

# Step 6: Provision cluster
print_header "Step 6: Cluster Provisioning"

echo "Ready to provision your cluster!"
echo ""
echo "This will:"
echo "  1. Install K3s on all nodes"
echo "  2. Configure networking over Tailscale"
echo "  3. Set up GitOps with Flux CD"
echo "  4. Apply node-specific configurations"
echo ""
echo "Expected duration: 5-10 minutes"
echo ""

if confirm "Start cluster provisioning?"; then
    print_info "Starting provisioning..."
    echo ""

    # Run provisioning
    if mise exec -- cluster-mgr provision; then
        print_success "Cluster provisioned successfully!"
    else
        print_error "Provisioning failed"
        echo ""
        echo "Check the error messages above for details."
        echo "You can re-run provisioning with: cluster-mgr provision"
        exit 1
    fi
else
    print_info "Skipping provisioning"
    echo ""
    echo "You can provision later with:"
    echo "  cluster-mgr provision"
    exit 0
fi

# Step 7: Verify cluster
print_header "Step 7: Verifying Cluster"

print_info "Checking cluster status..."
echo ""

# Wait a moment for cluster to stabilize
sleep 5

if mise exec -- cluster-mgr status; then
    print_success "Cluster is running!"
else
    print_warning "Could not verify cluster status"
    echo "You can check manually with: cluster-mgr status"
fi

# Final summary
print_header "Setup Complete! 🎉"

echo "Your Kubernetes cluster is ready!"
echo ""
echo "Next steps:"
echo ""
echo "  1. View cluster status:"
echo "     cluster-mgr status"
echo ""
echo "  2. Launch the TUI for monitoring:"
echo "     cluster-tui"
echo ""
echo "  3. Deploy an example application:"
echo "     kubectl apply -k gitops/apps/base/hello-world/"
echo ""
echo "  4. Access your cluster:"
echo "     export KUBECONFIG=~/.kube/config"
echo "     kubectl get nodes"
echo ""
echo "Documentation:"
echo "  - README.md - Full documentation"
echo "  - QUICKSTART.md - Detailed quickstart guide"
echo "  - docs/GPU_CONFIGURATION.md - GPU setup guide"
echo ""
echo "Useful commands:"
echo "  cluster-mgr --help    - CLI help"
echo "  cluster-tui           - Launch TUI"
echo "  kubectl get pods -A   - View all pods"
echo ""

print_success "Happy clustering! 🚀"
