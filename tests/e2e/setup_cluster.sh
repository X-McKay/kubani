#!/usr/bin/env bash
#
# Setup E2E test cluster using kind
#
# This script:
# 1. Creates a kind cluster for E2E tests
# 2. Installs minimal dependencies (Redis, etc.)
# 3. Creates test namespaces
# 4. Optionally deploys mock agents for testing
#
# Usage:
#   ./setup_cluster.sh          # Create cluster with all dependencies
#   ./setup_cluster.sh --quick  # Create minimal cluster only
#   ./setup_cluster.sh --delete # Delete the cluster
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="kubani-e2e"
NAMESPACE="kubani-e2e-test"
AGENTS_NAMESPACE="ai-agents"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v kind &> /dev/null; then
        log_error "kind is not installed. Install with: brew install kind"
        exit 1
    fi

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Install with: brew install kubectl"
        exit 1
    fi

    if ! command -v docker &> /dev/null; then
        log_error "docker is not installed"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker is not running"
        exit 1
    fi

    log_info "All prerequisites met"
}

# Create the kind cluster
create_cluster() {
    log_info "Creating kind cluster: $CLUSTER_NAME"

    # Check if cluster already exists
    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log_warn "Cluster $CLUSTER_NAME already exists"
        read -p "Delete and recreate? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            delete_cluster
        else
            log_info "Using existing cluster"
            return 0
        fi
    fi

    # Create cluster with config
    kind create cluster \
        --name "$CLUSTER_NAME" \
        --config "$SCRIPT_DIR/kind-config.yaml" \
        --wait 60s

    # Set kubectl context
    kubectl cluster-info --context "kind-$CLUSTER_NAME"

    log_info "Cluster created successfully"
}

# Delete the cluster
delete_cluster() {
    log_info "Deleting kind cluster: $CLUSTER_NAME"

    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        kind delete cluster --name "$CLUSTER_NAME"
        log_info "Cluster deleted"
    else
        log_warn "Cluster $CLUSTER_NAME does not exist"
    fi
}

# Create namespaces
create_namespaces() {
    log_info "Creating namespaces..."

    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
    kubectl create namespace "$AGENTS_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Label namespaces for identification
    kubectl label namespace "$NAMESPACE" app.kubernetes.io/part-of=kubani-e2e --overwrite
    kubectl label namespace "$AGENTS_NAMESPACE" app.kubernetes.io/part-of=kubani --overwrite

    log_info "Namespaces created"
}

# Install Redis for Event Bus
install_redis() {
    log_info "Installing Redis..."

    kubectl apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: database
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: database
spec:
  ports:
    - port: 6379
      targetPort: 6379
  selector:
    app: redis
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: database
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          ports:
            - containerPort: 6379
          resources:
            limits:
              memory: 128Mi
              cpu: 100m
          readinessProbe:
            exec:
              command:
                - redis-cli
                - ping
            initialDelaySeconds: 5
            periodSeconds: 5
EOF

    # Wait for Redis to be ready
    log_info "Waiting for Redis to be ready..."
    kubectl rollout status deployment/redis -n database --timeout=60s

    log_info "Redis installed"
}

# Install mock agents for testing (simplified versions)
install_mock_agents() {
    log_info "Installing mock agents..."

    kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: mock-agent-config
  namespace: $AGENTS_NAMESPACE
data:
  KUBANI_REDIS_URL: "redis://redis.database.svc.cluster.local:6379"
  KUBANI_LOG_LEVEL: "DEBUG"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mock-k8s-monitor
  namespace: $AGENTS_NAMESPACE
  labels:
    app: k8s-monitor
    app.kubernetes.io/part-of: kubani
spec:
  replicas: 1
  selector:
    matchLabels:
      app: k8s-monitor
  template:
    metadata:
      labels:
        app: k8s-monitor
        app.kubernetes.io/part-of: kubani
    spec:
      containers:
        - name: agent
          image: busybox:latest
          command: ["sleep", "infinity"]
          envFrom:
            - configMapRef:
                name: mock-agent-config
          resources:
            limits:
              memory: 64Mi
              cpu: 50m
EOF

    log_info "Mock agents installed"
}

# Port forward Redis for local access
port_forward_redis() {
    log_info "Setting up port forward for Redis..."

    # Kill any existing port forwards
    pkill -f "kubectl.*port-forward.*redis" || true

    # Start port forward in background
    kubectl port-forward -n database svc/redis 6379:6379 &

    log_info "Redis available at localhost:6379"
}

# Print cluster info
print_info() {
    echo
    echo "=============================================="
    echo "  E2E Test Cluster Ready"
    echo "=============================================="
    echo
    echo "Cluster:    $CLUSTER_NAME"
    echo "Context:    kind-$CLUSTER_NAME"
    echo "Namespaces: $NAMESPACE, $AGENTS_NAMESPACE"
    echo
    echo "Redis:      redis://localhost:6379 (port-forwarded)"
    echo
    echo "To run E2E tests:"
    echo "  just test-e2e"
    echo
    echo "To delete cluster:"
    echo "  $0 --delete"
    echo
}

# Main
main() {
    case "${1:-}" in
        --delete)
            delete_cluster
            exit 0
            ;;
        --quick)
            check_prerequisites
            create_cluster
            create_namespaces
            print_info
            ;;
        *)
            check_prerequisites
            create_cluster
            create_namespaces
            install_redis
            install_mock_agents
            port_forward_redis
            print_info
            ;;
    esac
}

main "$@"
