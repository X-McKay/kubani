#!/bin/bash
# Validate pod status for production services
# Usage: ./scripts/validate_pods.sh [service]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Function to check pod status
check_pod_status() {
    local namespace=$1
    local label=$2
    local service_name=$3

    echo -e "${BLUE}Checking ${service_name} pods in namespace ${namespace}...${NC}"

    # Get pod status
    pods=$(kubectl get pods -n "$namespace" -l "$label" -o json 2>/dev/null)

    if [ -z "$pods" ]; then
        echo -e "${RED}✗ No pods found${NC}"
        return 1
    fi

    # Check if jq is available
    if command -v jq &>/dev/null; then
        if [ "$(echo "$pods" | jq -r '.items | length')" -eq 0 ]; then
            echo -e "${RED}✗ No pods found${NC}"
            return 1
        fi

        # Check each pod
        local all_ready=true
        echo "$pods" | jq -r '.items[] | "\(.metadata.name) \(.status.phase) \(.status.conditions[] | select(.type=="Ready") | .status)"' | while read -r name phase ready; do
            if [ "$phase" = "Running" ] && [ "$ready" = "True" ]; then
                echo -e "  ${GREEN}✓${NC} $name: Running and Ready"
            else
                echo -e "  ${RED}✗${NC} $name: $phase (Ready: $ready)"
                all_ready=false
            fi
        done

        if [ "$all_ready" = false ]; then
            return 1
        fi
    else
        # Fallback without jq - use kubectl directly
        local pod_count=$(kubectl get pods -n "$namespace" -l "$label" --no-headers 2>/dev/null | wc -l)
        if [ "$pod_count" -eq 0 ]; then
            echo -e "${RED}✗ No pods found${NC}"
            return 1
        fi

        local all_ready=true
        kubectl get pods -n "$namespace" -l "$label" --no-headers 2>/dev/null | while read -r name ready status restarts age; do
            if [ "$status" = "Running" ] && [[ "$ready" == *"/"* ]]; then
                local ready_count=$(echo "$ready" | cut -d/ -f1)
                local total_count=$(echo "$ready" | cut -d/ -f2)
                if [ "$ready_count" = "$total_count" ]; then
                    echo -e "  ${GREEN}✓${NC} $name: Running and Ready ($ready)"
                else
                    echo -e "  ${RED}✗${NC} $name: $status (Ready: $ready)"
                    all_ready=false
                fi
            else
                echo -e "  ${RED}✗${NC} $name: $status (Ready: $ready)"
                all_ready=false
            fi
        done

        if [ "$all_ready" = false ]; then
            return 1
        fi
    fi

    return 0
}

# Main validation
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 Production Services Pod Status Validation${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if specific service requested
SERVICE="${1:-all}"

# Track overall status
OVERALL_STATUS=0

# PostgreSQL
if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "postgresql" ]; then
    if check_pod_status "database" "app.kubernetes.io/name=postgresql" "PostgreSQL"; then
        echo -e "${GREEN}✅ PostgreSQL pods are healthy${NC}"
    else
        echo -e "${RED}❌ PostgreSQL pods have issues${NC}"
        OVERALL_STATUS=1
    fi
    echo ""
fi

# Redis
if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "redis" ]; then
    if check_pod_status "cache" "app.kubernetes.io/name=redis" "Redis"; then
        echo -e "${GREEN}✅ Redis pods are healthy${NC}"
    else
        echo -e "${RED}❌ Redis pods have issues${NC}"
        OVERALL_STATUS=1
    fi
    echo ""
fi

# Authentik
if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "authentik" ]; then
    if check_pod_status "auth" "app.kubernetes.io/name=authentik" "Authentik"; then
        echo -e "${GREEN}✅ Authentik pods are healthy${NC}"
    else
        echo -e "${RED}❌ Authentik pods have issues${NC}"
        OVERALL_STATUS=1
    fi
    echo ""
fi

# Cert-Manager
if [ "$SERVICE" = "all" ] || [ "$SERVICE" = "cert-manager" ]; then
    if check_pod_status "cert-manager" "app.kubernetes.io/instance=cert-manager" "Cert-Manager"; then
        echo -e "${GREEN}✅ Cert-Manager pods are healthy${NC}"
    else
        echo -e "${RED}❌ Cert-Manager pods have issues${NC}"
        OVERALL_STATUS=1
    fi
    echo ""
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ $OVERALL_STATUS -eq 0 ]; then
    echo -e "${GREEN}✅ All pods are healthy${NC}"
else
    echo -e "${RED}❌ Some pods have issues${NC}"
    echo ""
    echo -e "${YELLOW}💡 Troubleshooting tips:${NC}"
    echo -e "  - Check pod logs: ${BLUE}kubectl logs -n <namespace> <pod-name>${NC}"
    echo -e "  - Describe pod: ${BLUE}kubectl describe pod -n <namespace> <pod-name>${NC}"
    echo -e "  - Check events: ${BLUE}kubectl get events -n <namespace> --sort-by='.lastTimestamp'${NC}"
fi

echo ""

exit $OVERALL_STATUS
