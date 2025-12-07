# Kubani - Kubernetes Cluster Automation for Tailscale Networks

Kubani is an infrastructure automation solution that provisions and manages multi-node Kubernetes clusters across heterogeneous hardware connected via Tailscale VPN. It enables you to build a production-ready Kubernetes cluster using your existing workstations, servers, and edge devices without complex networking setup.

## Features

- **Automated Provisioning**: Ansible-based automation for K3s cluster deployment
- **Tailscale Integration**: Secure mesh networking across different physical locations without port forwarding
- **GitOps Ready**: Built-in Flux CD integration for declarative application management
- **Workstation-Friendly**: Nodes can function as standalone workstations while participating in the cluster
- **GPU Support**: NVIDIA device plugin integration for GPU workloads with time-slicing
- **Management Tools**: CLI and TUI for cluster administration and real-time monitoring
- **Idempotent Operations**: Safe to re-run playbooks for updates and configuration changes
- **Property-Based Testing**: Comprehensive test suite with Hypothesis for correctness guarantees

## Prerequisites

### Required on Management Machine

- **[Mise](https://mise.jdx.dev/)** - Runtime and tool version manager
  ```bash
  curl https://mise.run | sh
  ```
- **Git** - For cloning the repository
- **SSH access** - To all cluster nodes with sudo privileges

### Required on All Cluster Nodes

- **[Tailscale](https://tailscale.com/)** - Installed and authenticated
  ```bash
  # Install Tailscale (Ubuntu/Debian)
  curl -fsSL https://tailscale.com/install.sh | sh

  # Authenticate
  sudo tailscale up
  ```
- **Operating System**: Ubuntu 20.04+ or Debian 11+ (other Linux distributions may work but are untested)
- **SSH Server**: OpenSSH server running and accessible
- **Sudo Access**: User account with passwordless sudo (or configure Ansible to prompt for password)

### Optional

- **GPU Nodes**: NVIDIA GPU with compatible drivers (will be installed by playbook if needed)
- **kubectl**: For manual cluster management (automatically installed via mise)

### Hardware Requirements

**Minimum per node:**
- 2 CPU cores (1 for Kubernetes, 1+ for workstation use)
- 2GB RAM (more recommended for workstation nodes)
- 20GB disk space

**Recommended for control plane:**
- 2+ CPU cores
- 4GB+ RAM
- 40GB+ disk space

**Recommended for worker nodes:**
- 4+ CPU cores (especially for workstation nodes)
- 8GB+ RAM
- 50GB+ disk space

Note: UV (Python package manager), Python, and kubectl are automatically installed via mise.

## Quick Start

This guide will get you from zero to a running Kubernetes cluster in about 15 minutes.

### 1. Install Development Tools

```bash
# Install mise (if not already installed)
curl https://mise.run | sh

# Add mise to your shell (follow the instructions from the install script)
# For bash: echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc
# For zsh: echo 'eval "$(~/.local/bin/mise activate zsh)"' >> ~/.zshrc

# Clone the repository
git clone <repository-url>
cd kubani

# Run the setup script (installs all tools and dependencies)
chmod +x setup.sh
./setup.sh

# Or manually:
mise install          # Installs Python, UV, kubectl
mise run install      # Installs Python dependencies
```

### 2. Verify Tailscale Setup

Ensure all your nodes are connected to Tailscale:

```bash
# On each node, verify Tailscale is running
tailscale status

# Discover available nodes from your management machine
cluster-mgr discover
```

You should see all your nodes listed with their Tailscale IP addresses.

### 3. Configure Your Cluster

Create your inventory file from the example:

```bash
cp ansible/inventory/hosts.yml.example ansible/inventory/hosts.yml
vim ansible/inventory/hosts.yml
```

**Minimum configuration required:**
- Set `cluster_name` to your desired cluster name
- Add at least one control plane node with its Tailscale IP
- Add worker nodes with their Tailscale IPs
- Configure `git_repo_url` for GitOps (or disable GitOps in group_vars)

See [Inventory Configuration](#inventory-configuration) for detailed options.

### 4. Provision the Cluster

```bash
# Using the CLI (recommended)
cluster-mgr provision

# Or using Ansible directly
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/site.yml

# Or using mise task
mise run provision
```

The provisioning process will:
1. Validate Tailscale connectivity on all nodes
2. Install system dependencies
3. Install K3s on control plane and worker nodes
4. Configure networking to use Tailscale IPs
5. Set up GitOps with Flux CD (if enabled)
6. Apply node-specific configurations (GPU support, resource reservations, etc.)

**Expected duration:** 5-10 minutes depending on node count and network speed.

### 5. Verify Cluster Status

```bash
# Check cluster status
cluster-mgr status

# Or use kubectl directly
export KUBECONFIG=~/.kube/config
kubectl get nodes
kubectl get pods -A
```

All nodes should show as "Ready" status.

### 6. Monitor Your Cluster

```bash
# Launch the TUI for real-time monitoring
cluster-tui

# Or using mise task
mise run tui
```

The TUI provides:
- Real-time node status and resource usage
- Service health monitoring
- Pod information
- Cluster events

**Keyboard shortcuts:**
- `q` - Quit
- `r` - Refresh
- `↑/↓` - Navigate
- `Enter` - View details

### 7. Deploy Your First Application

```bash
# Create an application manifest in the GitOps repository
mkdir -p gitops/apps/base/my-app
cat > gitops/apps/base/my-app/deployment.yaml <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80
EOF

# Commit and push (Flux will automatically deploy)
git add gitops/apps/base/my-app/
git commit -m "Add my-app deployment"
git push

# Watch the deployment
kubectl get pods -w
```

Flux will detect the changes and deploy your application within 1 minute (default sync interval).

## Production Services Deployment

Once your cluster is running, you can deploy production-ready services with encrypted secrets management, automated TLS certificates, and DNS-based access.

### Overview

The production services stack includes:
- **PostgreSQL**: Production database with persistent storage
- **Redis**: In-memory cache with optional persistence
- **Authentik**: Identity provider and SSO platform
- **cert-manager**: Automated TLS certificate management via Let's Encrypt
- **SOPS**: Encrypted secrets management with age encryption
- **Traefik TCP Routing**: DNS-based access to database services

All services are deployed via GitOps with Flux CD and use encrypted secrets stored safely in Git.

### Prerequisites

Before deploying production services, ensure:

1. **Cluster is running**: Complete the Quick Start guide above
2. **Cloudflare account**: You'll need a Cloudflare account managing your domain
3. **Domain configured**: Your domain (e.g., almckay.io) must be managed by Cloudflare
4. **Flux is operational**: GitOps should be enabled and working

### Quick Start: Deploy Production Services

#### 1. Set Up Secrets Management

Generate an age encryption key for SOPS:

```bash
# Generate age key pair
uv run python scripts/setup_sops.py

# This creates:
# - age.key (private key - keep secure!)
# - .sops.yaml (encryption configuration)
# - sops-age-secret.yaml (Kubernetes secret for Flux)
```

Apply the age secret to your cluster:

```bash
kubectl apply -f sops-age-secret.yaml
```

#### 2. Create Encrypted Secrets

Generate and encrypt secrets for all services:

```bash
# Interactive script to create all encrypted secrets
uv run python scripts/create_encrypted_secrets.py

# This creates encrypted secrets for:
# - Cloudflare API token (for cert-manager)
# - PostgreSQL credentials
# - Redis credentials
# - Authentik credentials
```

The script will:
- Prompt you for credentials (or generate secure random passwords)
- Create Kubernetes secret manifests
- Encrypt them with SOPS
- Save them in the appropriate gitops directories

#### 3. Configure DNS Records

Get your Traefik LoadBalancer IP:

```bash
# Display Traefik IP and DNS instructions
./scripts/get_traefik_ip.sh
```

Create DNS A records in Cloudflare:

```bash
# Option 1: Automated (requires Cloudflare API token)
uv run python scripts/configure_dns.py

# Option 2: Manual (follow instructions from get_traefik_ip.sh)
./scripts/setup_dns_records.sh
```

Create these A records pointing to your Traefik IP:
- `postgres.almckay.io` → Traefik Tailscale IP
- `redis.almckay.io` → Traefik Tailscale IP
- `auth.almckay.io` → Traefik Tailscale IP

#### 4. Deploy Services via GitOps

Commit and push the encrypted secrets:

```bash
# Add encrypted secrets to Git
git add gitops/infrastructure/cert-manager/cloudflare-secret.enc.yaml
git add gitops/apps/postgresql/secret.enc.yaml
git add gitops/apps/redis/secret.enc.yaml
git add gitops/apps/authentik/secret.enc.yaml
git add .sops.yaml

# Commit and push
git commit -m "Add encrypted secrets for production services"
git push
```

Flux will automatically:
1. Detect the changes in Git
2. Decrypt the secrets using the age key
3. Deploy cert-manager with Cloudflare integration
4. Deploy PostgreSQL, Redis, and Authentik
5. Request TLS certificates from Let's Encrypt
6. Configure Traefik TCP routing for database access

#### 5. Verify Deployment

Wait for services to deploy (typically 2-5 minutes):

```bash
# Watch deployment progress
watch kubectl get pods -A

# Or use the comprehensive validation script
./scripts/verify_services.sh
```

Validate individual services:

```bash
# Check pod status
./scripts/validate_pods.sh

# Validate PostgreSQL
./scripts/validate_postgresql.sh

# Validate Redis
./scripts/validate_redis.sh

# Validate Authentik
./scripts/validate_authentik.sh

# Validate certificates
./scripts/validate_certificates.sh
```

#### 6. Access Your Services

Once validated, access services from any machine on your Tailscale network:

**PostgreSQL:**
```bash
# Connect via DNS name
psql -h postgres.almckay.io -p 5432 -U authentik -d authentik

# Connection string
postgresql://authentik:<password>@postgres.almckay.io:5432/authentik
```

**Redis:**
```bash
# Connect via DNS name
redis-cli -h redis.almckay.io -p 6379 -a <password>

# Connection string
redis://:<password>@redis.almckay.io:6379
```

**Authentik:**
```bash
# Open in browser
open https://auth.almckay.io

# Or test with curl
curl https://auth.almckay.io
```

### Detailed Guides

For more detailed information on specific topics:

- **[Secrets Management Guide](docs/SECRETS_MANAGEMENT.md)**: Complete guide to SOPS, age encryption, and credential rotation
- **[DNS Configuration Guide](docs/DNS_CONFIGURATION.md)**: Detailed DNS setup and Traefik TCP routing
- **[GitOps Service Deployment](docs/GITOPS_SERVICE_DEPLOYMENT.md)**: In-depth service deployment guide
- **[Service Validation](docs/SERVICE_VALIDATION.md)**: Comprehensive validation and troubleshooting

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Repository                          │
│  ├── Encrypted Secrets (SOPS + age)                         │
│  ├── Service Manifests (HelmReleases)                       │
│  └── Infrastructure Config (cert-manager, Traefik)          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Flux CD (GitOps)                         │
│  ├── Decrypts secrets with age key                          │
│  ├── Deploys infrastructure components                      │
│  └── Deploys applications                                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Kubernetes Cluster (K3s)                       │
│  ├── cert-manager (TLS automation)                          │
│  ├── Traefik (Ingress + TCP routing)                        │
│  ├── PostgreSQL (database namespace)                        │
│  ├── Redis (cache namespace)                                │
│  └── Authentik (auth namespace)                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              DNS-Based Access (Cloudflare)                  │
│  ├── postgres.almckay.io:5432 → PostgreSQL                  │
│  ├── redis.almckay.io:6379 → Redis                          │
│  └── auth.almckay.io:443 → Authentik (HTTPS)                │
└─────────────────────────────────────────────────────────────┘
```

### Key Features

**Encrypted Secrets Management:**
- Secrets encrypted with SOPS and age encryption
- Safe to store in Git repository
- Automatic decryption by Flux during deployment
- Easy credential rotation workflow

**Automated TLS Certificates:**
- Let's Encrypt integration via cert-manager
- Cloudflare DNS-01 challenge for validation
- Automatic certificate renewal
- Wildcard certificate support

**DNS-Based Access:**
- Memorable DNS names instead of IP addresses
- Traefik TCP routing for PostgreSQL and Redis
- HTTPS ingress for web services
- Works from any device on Tailscale network

**GitOps Workflow:**
- All configuration in Git
- Declarative service definitions
- Automatic synchronization
- Complete audit trail

### Cloudflare API Token Setup

To enable cert-manager to manage DNS records for certificate validation:

1. **Log in to Cloudflare Dashboard**: https://dash.cloudflare.com/

2. **Navigate to API Tokens**:
   - Click on your profile icon (top right)
   - Select "My Profile"
   - Go to "API Tokens" tab
   - Click "Create Token"

3. **Create Custom Token**:
   - Click "Create Custom Token"
   - Token name: `k8s-cert-manager`
   - Permissions:
     - Zone → DNS → Edit
     - Zone → Zone → Read
   - Zone Resources:
     - Include → Specific zone → `almckay.io` (your domain)
   - TTL: No expiry (or set as desired)

4. **Save Token**:
   - Click "Continue to summary"
   - Click "Create Token"
   - **Copy the token immediately** (you won't see it again!)

5. **Use Token in Setup**:
   ```bash
   # When running create_encrypted_secrets.py, paste the token when prompted
   uv run python scripts/create_encrypted_secrets.py
   ```

**Required Permissions:**
- `Zone:DNS:Edit` - Allows creating/updating DNS records for ACME challenges
- `Zone:Zone:Read` - Allows reading zone information

### Traefik TCP Routing Configuration

Traefik is configured to expose PostgreSQL and Redis via TCP routing:

**Entry Points:**
- `postgresql`: Port 5432 (TCP)
- `redis`: Port 6379 (TCP)
- `websecure`: Port 443 (HTTPS)

**IngressRouteTCP Resources:**
- PostgreSQL: Routes `postgres.almckay.io:5432` to PostgreSQL service
- Redis: Routes `redis.almckay.io:6379` to Redis service

**Configuration Location:**
- Traefik config: `gitops/infrastructure/traefik/`
- IngressRouteTCP: `gitops/apps/postgresql/ingressroutetcp.yaml`
- IngressRouteTCP: `gitops/apps/redis/ingressroutetcp.yaml`

The TCP routing allows database clients to connect using standard protocols:
```bash
# PostgreSQL uses standard PostgreSQL protocol
psql -h postgres.almckay.io -p 5432 -U user -d database

# Redis uses standard Redis protocol
redis-cli -h redis.almckay.io -p 6379 -a password
```

### Troubleshooting Production Services

**Secrets Decryption Issues:**
```bash
# Check if age secret exists
kubectl get secret sops-age -n flux-system

# Verify Flux can decrypt
kubectl logs -n flux-system -l app=kustomize-controller | grep -i sops

# Test decryption locally
sops -d gitops/apps/postgresql/secret.enc.yaml
```

**Certificate Issues:**
```bash
# Check cert-manager status
kubectl get pods -n cert-manager

# Check ClusterIssuer
kubectl describe clusterissuer letsencrypt-prod

# Check certificate status
kubectl get certificates -A
kubectl describe certificate authentik-tls -n auth

# View cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager
```

**DNS Resolution Issues:**
```bash
# Test DNS resolution
nslookup postgres.almckay.io
nslookup redis.almckay.io
nslookup auth.almckay.io

# Check Cloudflare DNS records
# Visit: https://dash.cloudflare.com/ → Select domain → DNS

# Verify Traefik IP
kubectl get svc -n kube-system traefik
```

**Service Connectivity Issues:**
```bash
# Test TCP connectivity
nc -zv postgres.almckay.io 5432
nc -zv redis.almckay.io 6379
nc -zv auth.almckay.io 443

# Check Traefik logs
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik

# Check IngressRouteTCP
kubectl get ingressroutetcp -A
kubectl describe ingressroutetcp postgresql-tcp -n database
```

**Pod Status Issues:**
```bash
# Check pod status
kubectl get pods -n database  # PostgreSQL
kubectl get pods -n cache     # Redis
kubectl get pods -n auth      # Authentik

# View pod logs
kubectl logs -n database -l app.kubernetes.io/name=postgresql
kubectl logs -n cache -l app.kubernetes.io/name=redis
kubectl logs -n auth -l app.kubernetes.io/name=authentik

# Describe pods for events
kubectl describe pod -n database <pod-name>
```

For more troubleshooting guidance, see:
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)
- [Secrets Management Guide](docs/SECRETS_MANAGEMENT.md)
- [DNS Configuration Guide](docs/DNS_CONFIGURATION.md)

## Project Structure

```
.
├── ansible/                    # Ansible automation
│   ├── inventory/             # Inventory and variables
│   ├── playbooks/             # Provisioning playbooks
│   └── roles/                 # Ansible roles
├── cluster_manager/           # Python management tools
│   ├── cli/                   # CLI commands
│   ├── tui/                   # Terminal UI
│   └── models/                # Data models
├── gitops/                    # GitOps manifests
│   ├── flux-system/          # Flux controllers
│   ├── infrastructure/       # Infrastructure components
│   └── apps/                 # Applications
└── tests/                     # Test suite
    ├── unit/                 # Unit tests
    ├── properties/           # Property-based tests
    └── integration/          # Integration tests
```

## CLI Usage

The `cluster-mgr` CLI provides commands for managing your Kubernetes cluster.

### Node Discovery

Discover nodes on your Tailscale network:

```bash
# Discover all Tailscale nodes
cluster-mgr discover

# Show only online nodes
cluster-mgr discover --online-only

# Filter by hostname pattern
cluster-mgr discover --filter "gpu-*"

# Hide cluster membership status
cluster-mgr discover --no-cluster-status
```

### Node Management

Add nodes to your cluster:

```bash
# Add a basic worker node
cluster-mgr add-node my-node 100.64.0.10 --role worker

# Add a control plane node
cluster-mgr add-node control-1 100.64.0.5 --role control-plane

# Add a GPU worker with resource reservations
cluster-mgr add-node gpu-node 100.64.0.20 \
  --role worker \
  --gpu \
  --reserved-cpu 4 \
  --reserved-memory 8Gi \
  --labels "gpu=true,workstation=true" \
  --taints "nvidia.com/gpu=true:NoSchedule"

# Add node with custom labels
cluster-mgr add-node web-1 100.64.0.15 \
  --role worker \
  --labels "tier=frontend,env=production"
```

Remove nodes from your cluster:

```bash
# Remove a node (with drain)
cluster-mgr remove-node my-node

# Remove without draining
cluster-mgr remove-node my-node --no-drain

# Force removal without confirmation
cluster-mgr remove-node my-node --force
```

### Configuration Management

Get and set configuration values:

```bash
# Get a configuration value
cluster-mgr config-get k3s_version
cluster-mgr config-get cluster_name --scope all

# Set configuration values
cluster-mgr config-set k3s_version v1.28.5+k3s1
cluster-mgr config-set cluster_name my-cluster --scope all

# Set typed values
cluster-mgr config-set monitoring_enabled true --type bool
cluster-mgr config-set worker_count 5 --type int

# Set nested configuration
cluster-mgr config-set flux.namespace flux-system --scope all

# Set JSON configuration
cluster-mgr config-set node_labels '{"env":"prod","tier":"backend"}' --type json
```

### Cluster Operations

Provision and manage your cluster:

```bash
# Provision the entire cluster
cluster-mgr provision

# Run in check mode (dry-run)
cluster-mgr provision --check

# Run specific playbook
cluster-mgr provision --playbook add_node.yml

# Run with tags (only specific tasks)
cluster-mgr provision --tags "k3s,networking"

# Skip specific tags
cluster-mgr provision --skip-tags "gpu,monitoring"

# Limit to specific hosts
cluster-mgr provision --limit "gpu-node"

# Run with extra variables
cluster-mgr provision --extra-vars '{"k3s_version":"v1.28.5+k3s1"}'

# Increase verbosity
cluster-mgr provision -v    # verbose
cluster-mgr provision -vv   # more verbose
cluster-mgr provision -vvv  # debug level
```

### Cluster Status

Check cluster health and status:

```bash
# Basic cluster status
cluster-mgr status

# Show pod information
cluster-mgr status --pods

# Show pods in specific namespace
cluster-mgr status --pods --namespace kube-system

# Use custom inventory
cluster-mgr status --inventory path/to/hosts.yml
```

### Version Information

```bash
# Show version
cluster-mgr version
```

## Development

### Running Tests

```bash
# All tests
mise run test

# Unit tests only
mise run test-unit

# Property-based tests only
mise run test-properties

# With coverage
pytest --cov=cluster_manager --cov-report=html
```

### Code Quality

```bash
# Lint code
mise run lint

# Format code
mise run format

# Type checking
mise run type-check
```

## Inventory Configuration

The Ansible inventory defines your cluster topology. Here's a detailed explanation of configuration options:

### Basic Structure

```yaml
all:
  vars:
    # Global variables for all nodes
    k3s_version: v1.28.5+k3s1
    cluster_name: homelab
    tailscale_network: 100.64.0.0/10

  children:
    control_plane:
      hosts:
        # Control plane nodes

    workers:
      hosts:
        # Worker nodes
```

### Node Configuration Options

**Required fields:**
- `ansible_host`: Tailscale IP address for SSH connection
- `tailscale_ip`: Tailscale IP address for Kubernetes networking

**Optional fields:**
- `reserved_cpu`: CPU cores to reserve for local processes (e.g., "2", "4")
- `reserved_memory`: Memory to reserve for local processes (e.g., "4Gi", "8Gi")
- `gpu`: Set to `true` for nodes with NVIDIA GPUs
- `node_labels`: Dictionary of Kubernetes labels to apply
- `node_taints`: List of taints to apply (prevents pod scheduling)

### Example Configurations

**Basic worker node:**
```yaml
simple-worker:
  ansible_host: 100.64.0.10
  tailscale_ip: 100.64.0.10
```

**Workstation node (reserves resources for local use):**
```yaml
desktop:
  ansible_host: 100.64.0.20
  tailscale_ip: 100.64.0.20
  reserved_cpu: "2"
  reserved_memory: "4Gi"
  node_labels:
    workstation: "true"
    node-role: worker
```

**GPU node:**
```yaml
gpu-server:
  ansible_host: 100.64.0.30
  tailscale_ip: 100.64.0.30
  reserved_cpu: "4"
  reserved_memory: "8Gi"
  gpu: true
  node_labels:
    gpu: "true"
    gpu-type: "nvidia"
  node_taints:
    - key: nvidia.com/gpu
      value: "true"
      effect: NoSchedule
```

**Control plane node:**
```yaml
control-1:
  ansible_host: 100.64.0.5
  tailscale_ip: 100.64.0.5
  node_labels:
    node-role: control-plane
```

### Global Variables

Configure these in `ansible/inventory/group_vars/all.yml`:

- `k3s_version`: K3s version to install (e.g., "v1.28.5+k3s1")
- `cluster_name`: Name of your cluster
- `cluster_domain`: Kubernetes cluster domain (default: "cluster.local")
- `cluster_cidr`: Pod network CIDR (default: "10.42.0.0/16")
- `service_cidr`: Service network CIDR (default: "10.43.0.0/16")
- `tailscale_network`: Tailscale network CIDR (default: "100.64.0.0/10")
- `gitops_enabled`: Enable Flux CD GitOps (default: true)
- `git_repo_url`: Git repository URL for GitOps
- `git_branch`: Git branch to monitor (default: "main")
- `flux_namespace`: Namespace for Flux controllers (default: "flux-system")

## Architecture

Kubani uses K3s (lightweight Kubernetes) with Tailscale for networking. All cluster communication occurs over Tailscale IPs, enabling secure operation across different physical locations without port forwarding or VPN server setup.

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Repository                          │
│  ├── ansible/          (Infrastructure as Code)             │
│  ├── gitops/           (Application Manifests)              │
│  └── cluster_manager/  (Management Tools)                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Management Workstation                          │
│  ├── cluster-mgr CLI   (Node & config management)           │
│  ├── cluster-tui       (Real-time monitoring)               │
│  └── Ansible           (Automation engine)                   │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Tailscale Network   │
              │   (Mesh VPN Layer)    │
              └───────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Control Plane│  │    Worker    │  │  GPU Worker  │
│              │  │              │  │              │
│ K3s Server   │  │ K3s Agent    │  │ K3s Agent    │
│ + Flux CD    │  │ + Workloads  │  │ + GPU Plugin │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Key Components

- **Ansible**: Infrastructure automation and node provisioning
- **K3s**: Lightweight Kubernetes distribution (single binary, low resource usage)
- **Tailscale**: Mesh VPN for secure node communication (automatic NAT traversal)
- **Flux CD**: GitOps controller for application deployment
- **Typer**: CLI framework for cluster management
- **Textual**: Terminal UI framework for real-time monitoring
- **containerd**: Container runtime (included with K3s)
- **Flannel**: CNI plugin for pod networking (included with K3s)

### Network Flow

1. **Management → Nodes**: Ansible connects via SSH over Tailscale IPs
2. **Node → Node**: Kubernetes API and pod traffic over Tailscale IPs
3. **Flux → Git**: GitOps controller pulls manifests from Git repository
4. **TUI → Cluster**: Real-time monitoring via Kubernetes API

### Security Model

- **Tailscale**: Encrypted mesh network (WireGuard protocol)
- **Kubernetes RBAC**: Role-based access control for cluster resources
- **Network Policies**: Pod-to-pod communication restrictions (optional)
- **Ansible Vault**: Encrypted storage for sensitive variables (optional)
- **SSH Keys**: Passwordless authentication for automation

## Troubleshooting

### Common Issues

#### Tailscale Connectivity Issues

**Problem:** Nodes not reachable via Tailscale IP

**Solutions:**
```bash
# On each node, check Tailscale status
tailscale status

# Verify Tailscale is running
sudo systemctl status tailscaled

# Check if node is authenticated
tailscale status | grep "logged in"

# Test connectivity from management machine
ping <tailscale-ip>
ssh user@<tailscale-ip>

# Restart Tailscale if needed
sudo systemctl restart tailscaled
```

#### SSH Connection Failures

**Problem:** Ansible cannot connect to nodes

**Solutions:**
```bash
# Test SSH connection manually
ssh user@<tailscale-ip>

# Check SSH key authentication
ssh -v user@<tailscale-ip>

# Ensure SSH key is in authorized_keys on target node
cat ~/.ssh/id_rsa.pub | ssh user@<tailscale-ip> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# Configure Ansible to use password authentication (temporary)
# Add to ansible.cfg:
# [defaults]
# ask_pass = True
```

#### K3s Installation Failures

**Problem:** K3s fails to install or start

**Solutions:**
```bash
# Check K3s service status on the node
sudo systemctl status k3s        # Control plane
sudo systemctl status k3s-agent  # Worker

# View K3s logs
sudo journalctl -u k3s -f        # Control plane
sudo journalctl -u k3s-agent -f  # Worker

# Check for port conflicts
sudo netstat -tulpn | grep -E ':(6443|10250|10251|10252)'

# Manually uninstall and retry
sudo /usr/local/bin/k3s-uninstall.sh        # Control plane
sudo /usr/local/bin/k3s-agent-uninstall.sh  # Worker

# Then re-run provisioning
cluster-mgr provision
```

#### Node Not Joining Cluster

**Problem:** Worker node fails to join control plane

**Solutions:**
```bash
# Verify control plane is accessible
curl -k https://<control-plane-tailscale-ip>:6443

# Check join token on control plane
sudo cat /var/lib/rancher/k3s/server/node-token

# Verify token in worker configuration
sudo cat /etc/rancher/k3s/config.yaml

# Check worker logs for connection errors
sudo journalctl -u k3s-agent -n 100

# Ensure firewall allows required ports
sudo ufw allow 6443/tcp   # API server
sudo ufw allow 10250/tcp  # Kubelet
```

#### GPU Not Detected

**Problem:** NVIDIA GPU not available in Kubernetes

**Solutions:**
```bash
# Verify GPU is detected by system
nvidia-smi

# Check if NVIDIA device plugin is running
kubectl get pods -n kube-system | grep nvidia

# View device plugin logs
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds

# Verify GPU resource is advertised
kubectl describe node <gpu-node-name> | grep nvidia.com/gpu

# Manually install NVIDIA drivers if needed
sudo apt update
sudo apt install -y nvidia-driver-535

# Reboot and re-run provisioning
sudo reboot
cluster-mgr provision --tags gpu
```

#### Flux GitOps Not Syncing

**Problem:** Applications not deploying from Git repository

**Solutions:**
```bash
# Check Flux controller status
kubectl get pods -n flux-system

# View Flux logs
kubectl logs -n flux-system -l app=source-controller
kubectl logs -n flux-system -l app=kustomize-controller

# Check Git repository source
kubectl get gitrepositories -n flux-system

# Verify Flux can access Git repository
kubectl describe gitrepository -n flux-system flux-system

# Force reconciliation
flux reconcile source git flux-system
flux reconcile kustomization flux-system

# Check for authentication issues (private repos)
kubectl get secret -n flux-system flux-system
```

#### High Resource Usage on Workstation Nodes

**Problem:** Kubernetes consuming too many resources

**Solutions:**
```bash
# Check current resource reservations
kubectl describe node <node-name> | grep -A 5 "Allocated resources"

# Increase resource reservations in inventory
# Edit ansible/inventory/hosts.yml:
# reserved_cpu: "4"      # Increase from 2
# reserved_memory: "8Gi" # Increase from 4Gi

# Re-run provisioning to apply changes
cluster-mgr provision --tags k3s_worker

# Add taints to prevent pod scheduling
cluster-mgr add-node <node-name> <ip> \
  --taints "workstation=true:NoSchedule"

# Manually drain and cordon node
kubectl drain <node-name> --ignore-daemonsets
kubectl cordon <node-name>
```

#### Playbook Fails Midway

**Problem:** Ansible playbook fails during execution

**Solutions:**
```bash
# Run in check mode to see what would change
cluster-mgr provision --check

# Increase verbosity to see detailed errors
cluster-mgr provision -vvv

# Run specific tags to isolate the issue
cluster-mgr provision --tags prerequisites
cluster-mgr provision --tags k3s

# Skip problematic tasks temporarily
cluster-mgr provision --skip-tags gpu,monitoring

# Check Ansible logs
cat ansible/artifacts/*/stdout

# Verify inventory syntax
ansible-inventory -i ansible/inventory/hosts.yml --list
```

#### TUI Not Connecting

**Problem:** cluster-tui cannot connect to cluster

**Solutions:**
```bash
# Verify kubeconfig exists
ls -la ~/.kube/config

# Test kubectl connection
kubectl get nodes

# Check kubeconfig context
kubectl config current-context
kubectl config get-contexts

# Set correct kubeconfig
export KUBECONFIG=~/.kube/config

# Verify API server is accessible
curl -k https://<control-plane-ip>:6443

# Check for certificate issues
kubectl cluster-info
```

### Getting Help

If you encounter issues not covered here:

1. **Check logs**: Most issues can be diagnosed from logs
   - Ansible: `ansible/artifacts/*/stdout`
   - K3s: `sudo journalctl -u k3s` or `sudo journalctl -u k3s-agent`
   - Kubernetes: `kubectl logs <pod-name>`

2. **Run in verbose mode**: Add `-v`, `-vv`, or `-vvv` to commands

3. **Verify prerequisites**: Ensure Tailscale is working and SSH access is configured

4. **Test manually**: Try manual steps to isolate the issue

5. **Check documentation**: Review the design and requirements documents

6. **Open an issue**: Provide logs, configuration, and steps to reproduce

## Advanced Topics

### High Availability Control Plane

To set up multiple control plane nodes for HA:

1. Add multiple nodes to the `control_plane` group in inventory
2. Configure an external load balancer or use Tailscale load balancing
3. Update `api_server_url` to point to the load balancer
4. Run provisioning playbook

### Custom Storage Classes

To add custom storage classes:

1. Create storage class manifests in `gitops/infrastructure/storage/`
2. Configure storage provider (NFS, Ceph, etc.)
3. Commit and push to Git repository
4. Flux will automatically apply the changes

### Monitoring Stack

To add Prometheus and Grafana:

1. Enable monitoring in `ansible/inventory/group_vars/all.yml`:
   ```yaml
   monitoring_enabled: true
   ```
2. Add monitoring manifests to `gitops/infrastructure/monitoring/`
3. Run provisioning playbook

### Backup and Restore

K3s stores state in SQLite by default:

```bash
# Backup control plane data
sudo tar czf k3s-backup.tar.gz /var/lib/rancher/k3s/server/db/

# Restore (on new control plane)
sudo systemctl stop k3s
sudo tar xzf k3s-backup.tar.gz -C /
sudo systemctl start k3s
```

### Upgrading K3s

To upgrade Kubernetes version:

```bash
# Update version in inventory
cluster-mgr config-set k3s_version v1.29.0+k3s1

# Run provisioning (will perform rolling upgrade)
cluster-mgr provision

# Verify upgrade
kubectl get nodes
```

## Production Services Validation

After deploying production services (PostgreSQL, Redis, Authentik), use these validation scripts to verify everything is working correctly.

### Quick Validation

Run all validation checks at once:

```bash
# Comprehensive service validation
./scripts/verify_services.sh
```

### Individual Service Validation

**Check Pod Status:**
```bash
# All services
./scripts/validate_pods.sh

# Specific service
./scripts/validate_pods.sh postgresql
./scripts/validate_pods.sh redis
./scripts/validate_pods.sh authentik
./scripts/validate_pods.sh cert-manager
```

**PostgreSQL Connectivity:**
```bash
# Test DNS, TCP connectivity, authentication, and basic operations
./scripts/validate_postgresql.sh
```

This script validates:
- DNS resolution for postgres.almckay.io
- TCP connectivity on port 5432
- Database authentication
- Basic CRUD operations

**Redis Connectivity:**
```bash
# Test DNS, TCP connectivity, authentication, and basic operations
./scripts/validate_redis.sh
```

This script validates:
- DNS resolution for redis.almckay.io
- TCP connectivity on port 6379
- Redis authentication
- Basic SET/GET/DEL operations

**Authentik HTTPS Access:**
```bash
# Test DNS, HTTPS connectivity, TLS certificates, and web interface
./scripts/validate_authentik.sh
```

This script validates:
- DNS resolution for auth.almckay.io
- HTTPS connectivity
- TLS certificate validity (Let's Encrypt)
- Authentik API endpoint
- Web interface accessibility

**Certificate Status:**
```bash
# Check all TLS certificates and cert-manager status
./scripts/validate_certificates.sh
```

This script validates:
- cert-manager deployment status
- ClusterIssuer configuration
- Certificate resources and their status
- Certificate secrets
- Recent CertificateRequests

### DNS Configuration

**Get Traefik LoadBalancer IP:**
```bash
# Display Traefik IP and DNS configuration instructions
./scripts/get_traefik_ip.sh
```

**Configure DNS Records:**
```bash
# Manual configuration (provides instructions)
./scripts/setup_dns_records.sh

# Automated configuration (requires Cloudflare API token)
uv run python scripts/configure_dns.py
```

### Service Endpoints

Once DNS is configured and services are validated:

- **PostgreSQL**: `postgres.almckay.io:5432`
  ```bash
  psql -h postgres.almckay.io -p 5432 -U authentik -d authentik
  ```

- **Redis**: `redis.almckay.io:6379`
  ```bash
  redis-cli -h redis.almckay.io -p 6379 -a <password>
  ```

- **Authentik**: `https://auth.almckay.io`
  ```bash
  curl https://auth.almckay.io
  # Or open in browser
  ```

### Troubleshooting Production Services

**DNS Issues:**
```bash
# Test DNS resolution
nslookup postgres.almckay.io
nslookup redis.almckay.io
nslookup auth.almckay.io

# Flush DNS cache (macOS)
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder
```

**Connectivity Issues:**
```bash
# Test TCP connectivity
nc -zv postgres.almckay.io 5432
nc -zv redis.almckay.io 6379
nc -zv auth.almckay.io 443

# Check Traefik status
kubectl get svc -n kube-system traefik
kubectl get ingressroutetcp -A
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik
```

**Certificate Issues:**
```bash
# Check certificate status
kubectl get certificates -A
kubectl describe certificate authentik-tls -n auth

# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager

# Check ClusterIssuer
kubectl describe clusterissuer letsencrypt-prod
```

**Service Issues:**
```bash
# Check pod status
kubectl get pods -n database  # PostgreSQL
kubectl get pods -n cache     # Redis
kubectl get pods -n auth      # Authentik

# View logs
kubectl logs -n database -l app.kubernetes.io/name=postgresql
kubectl logs -n cache -l app.kubernetes.io/name=redis
kubectl logs -n auth -l app.kubernetes.io/name=authentik

# Check secrets
kubectl get secret postgresql-credentials -n database
kubectl get secret redis-credentials -n cache
kubectl get secret authentik-credentials -n auth
```

For more detailed information, see:
- [DNS Configuration Guide](docs/DNS_CONFIGURATION.md)
- [Secrets Management Guide](docs/SECRETS_MANAGEMENT.md)
- [GitOps Service Deployment](docs/GITOPS_SERVICE_DEPLOYMENT.md)

## Documentation

### Getting Started
- [Quick Start Guide](docs/QUICKSTART.md) - Get up and running in 15 minutes
- [Quickstart Script](scripts/quickstart.sh) - Automated interactive setup
- [Production Services Quickstart](docs/PRODUCTION_SERVICES_QUICKSTART.md) - Deploy PostgreSQL, Redis, and Authentik in 15 minutes
- [CLI Reference](docs/CLI_REFERENCE.md) - Complete command-line reference
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md) - Common issues and solutions

### Production Services
- [Production Services Quickstart](docs/PRODUCTION_SERVICES_QUICKSTART.md) - Step-by-step deployment guide
- [Secrets Management Guide](docs/SECRETS_MANAGEMENT.md) - SOPS, age encryption, and credential rotation
- [DNS Configuration Guide](docs/DNS_CONFIGURATION.md) - DNS setup and Traefik TCP routing
- [Service Validation Guide](docs/SERVICE_VALIDATION.md) - Validation and troubleshooting procedures

### GitOps and Deployment
- [GitOps Service Deployment](docs/GITOPS_SERVICE_DEPLOYMENT.md) - Complete guide for deploying services via GitOps
- [GitOps Validation](docs/GITOPS_VALIDATION.md) - Verify Flux is working and troubleshoot issues
- [GitOps README](gitops/README.md) - GitOps workflow and structure

### Configuration Guides
- [GPU Configuration](docs/GPU_CONFIGURATION.md) - Complete guide for NVIDIA GPU setup
- [Example Inventories](ansible/inventory/) - Sample configurations for different scenarios

### Architecture and Design
- [Architecture Overview](docs/ARCHITECTURE.md) - System architecture and design decisions
- [Design Document](.kiro/specs/tailscale-k8s-cluster/design.md) - Detailed technical design
- [Requirements](.kiro/specs/tailscale-k8s-cluster/requirements.md) - Requirements and acceptance criteria

### Component Documentation
- [Ansible README](ansible/README.md) - Ansible playbooks and roles
- [Cluster Manager README](cluster_manager/README.md) - CLI and TUI tools
- [Error Handling Guide](docs/ERROR_HANDLING.md) - Error handling and recovery procedures

### Example Applications
- [Hello World](gitops/apps/base/hello-world/) - Simple nginx deployment
- [Web Application](gitops/apps/base/web-app-example/) - Full-stack web app with frontend and backend
- [GPU Test](gitops/apps/base/gpu-test/) - GPU availability verification
- [ML Training](gitops/apps/base/ml-training/) - GPU-accelerated training job
- [GPU Inference](gitops/apps/base/gpu-inference/) - GPU inference service with time-slicing

### Development
- [Contributing Guide](docs/CONTRIBUTING.md) - Development guidelines and workflow
- [Development Guide](docs/DEVELOPMENT.md) - Development environment and tooling
- [Testing Guide](docs/TESTING.md) - Running and writing tests
- [Implementation Tasks](.kiro/specs/tailscale-k8s-cluster/tasks.md) - Development task list

## License

MIT
