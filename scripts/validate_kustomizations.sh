#!/bin/bash
# Validate Flux Kustomization deployment order and status

set -e

echo "=================================================="
echo "Flux Kustomization Validation"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if a Kustomization is ready
check_kustomization() {
    local name=$1
    local namespace=${2:-flux-system}

    echo -n "Checking Kustomization '$name'... "

    if ! kubectl get kustomization "$name" -n "$namespace" &>/dev/null; then
        echo -e "${RED}NOT FOUND${NC}"
        return 1
    fi

    local ready=$(kubectl get kustomization "$name" -n "$namespace" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
    local message=$(kubectl get kustomization "$name" -n "$namespace" -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}')

    if [ "$ready" = "True" ]; then
        echo -e "${GREEN}READY${NC}"
        return 0
    elif [ "$ready" = "False" ]; then
        echo -e "${RED}NOT READY${NC}"
        echo "  Message: $message"
        return 1
    else
        echo -e "${YELLOW}UNKNOWN${NC}"
        echo "  Message: $message"
        return 1
    fi
}

# Function to check dependencies
check_dependencies() {
    local name=$1
    local namespace=${2:-flux-system}

    echo "  Dependencies:"
    local deps=$(kubectl get kustomization "$name" -n "$namespace" -o jsonpath='{.spec.dependsOn[*].name}')

    if [ -z "$deps" ]; then
        echo "    None (root level)"
    else
        for dep in $deps; do
            echo -n "    - $dep: "
            if check_kustomization "$dep" "$namespace" &>/dev/null; then
                echo -e "${GREEN}✓${NC}"
            else
                echo -e "${RED}✗${NC}"
            fi
        done
    fi
}

# Function to check SOPS decryption
check_sops() {
    local name=$1
    local namespace=${2:-flux-system}

    echo "  SOPS Decryption:"
    local provider=$(kubectl get kustomization "$name" -n "$namespace" -o jsonpath='{.spec.decryption.provider}')
    local secret=$(kubectl get kustomization "$name" -n "$namespace" -o jsonpath='{.spec.decryption.secretRef.name}')

    if [ "$provider" = "sops" ]; then
        echo -n "    Provider: sops, Secret: $secret "
        if kubectl get secret "$secret" -n "$namespace" &>/dev/null; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${RED}✗ (secret not found)${NC}"
        fi
    else
        echo "    Not configured"
    fi
}

# Function to check health checks
check_health_checks() {
    local name=$1
    local namespace=${2:-flux-system}

    echo "  Health Checks:"
    local health_checks=$(kubectl get kustomization "$name" -n "$namespace" -o json | jq -r '.spec.healthChecks[]? | "\(.kind):\(.name):\(.namespace)"')

    if [ -z "$health_checks" ]; then
        echo "    None configured"
    else
        while IFS=: read -r kind hc_name hc_namespace; do
            echo -n "    - $kind/$hc_name ($hc_namespace): "
            if kubectl get "$kind" "$hc_name" -n "$hc_namespace" &>/dev/null; then
                local ready=$(kubectl get "$kind" "$hc_name" -n "$hc_namespace" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
                if [ "$ready" = "True" ]; then
                    echo -e "${GREEN}✓${NC}"
                else
                    echo -e "${YELLOW}pending${NC}"
                fi
            else
                echo -e "${RED}✗ (not found)${NC}"
            fi
        done <<< "$health_checks"
    fi
}

echo "1. Infrastructure Layer"
echo "------------------------"
check_kustomization "infrastructure"
check_dependencies "infrastructure"
check_sops "infrastructure"
check_health_checks "infrastructure"
echo ""

echo "2. Databases Layer"
echo "------------------"
check_kustomization "databases"
check_dependencies "databases"
check_sops "databases"
check_health_checks "databases"
echo ""

echo "3. Applications Layer"
echo "---------------------"
check_kustomization "apps"
check_dependencies "apps"
check_sops "apps"
check_health_checks "apps"
echo ""

echo "=================================================="
echo "Summary"
echo "=================================================="
echo ""

# Get all Kustomizations
kubectl get kustomizations -n flux-system -o custom-columns=\
NAME:.metadata.name,\
READY:.status.conditions[?(@.type==\"Ready\")].status,\
STATUS:.status.conditions[?(@.type==\"Ready\")].message,\
AGE:.metadata.creationTimestamp

echo ""
echo "Deployment Order: infrastructure → databases → apps"
echo ""

# Check if all are ready
all_ready=true
for ks in infrastructure databases apps; do
    ready=$(kubectl get kustomization "$ks" -n flux-system -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")
    if [ "$ready" != "True" ]; then
        all_ready=false
        break
    fi
done

if [ "$all_ready" = true ]; then
    echo -e "${GREEN}✓ All Kustomizations are ready!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ Some Kustomizations are not ready yet${NC}"
    echo ""
    echo "To troubleshoot:"
    echo "  kubectl describe kustomization <name> -n flux-system"
    echo "  kubectl logs -n flux-system -l app=kustomize-controller --tail=50"
    exit 1
fi
