#!/bin/bash
# Validate TLS certificate status for production services
# Usage: ./scripts/validate_certificates.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 TLS Certificate Status Validation${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Function to check certificate resource
check_certificate() {
    local namespace=$1
    local cert_name=$2

    echo -e "${YELLOW}Checking certificate: ${cert_name} (namespace: ${namespace})${NC}"

    # Check if certificate exists
    if ! kubectl get certificate "$cert_name" -n "$namespace" &>/dev/null; then
        echo -e "${RED}✗ Certificate not found${NC}"
        return 1
    fi

    # Get certificate status
    CERT_JSON=$(kubectl get certificate "$cert_name" -n "$namespace" -o json)

    # Check ready condition
    if command -v jq &>/dev/null; then
        READY=$(echo "$CERT_JSON" | jq -r '.status.conditions[] | select(.type=="Ready") | .status')
        REASON=$(echo "$CERT_JSON" | jq -r '.status.conditions[] | select(.type=="Ready") | .reason')
        MESSAGE=$(echo "$CERT_JSON" | jq -r '.status.conditions[] | select(.type=="Ready") | .message')
    else
        # Fallback without jq
        READY=$(kubectl get certificate "$cert_name" -n "$namespace" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
        REASON=$(kubectl get certificate "$cert_name" -n "$namespace" -o jsonpath='{.status.conditions[?(@.type=="Ready")].reason}')
        MESSAGE=$(kubectl get certificate "$cert_name" -n "$namespace" -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}')
    fi

    if [ "$READY" = "True" ]; then
        echo -e "${GREEN}✓ Certificate is ready${NC}"
    else
        echo -e "${RED}✗ Certificate is not ready${NC}"
        echo -e "  Reason: ${YELLOW}$REASON${NC}"
        echo -e "  Message: ${YELLOW}$MESSAGE${NC}"
        return 1
    fi

    # Get certificate details
    if command -v jq &>/dev/null; then
        NOT_AFTER=$(echo "$CERT_JSON" | jq -r '.status.notAfter // "N/A"')
        NOT_BEFORE=$(echo "$CERT_JSON" | jq -r '.status.notBefore // "N/A"')
        RENEWAL_TIME=$(echo "$CERT_JSON" | jq -r '.status.renewalTime // "N/A"')
        DNS_NAMES=$(echo "$CERT_JSON" | jq -r '.spec.dnsNames[]' 2>/dev/null)
    else
        NOT_AFTER=$(kubectl get certificate "$cert_name" -n "$namespace" -o jsonpath='{.status.notAfter}' 2>/dev/null || echo "N/A")
        NOT_BEFORE=$(kubectl get certificate "$cert_name" -n "$namespace" -o jsonpath='{.status.notBefore}' 2>/dev/null || echo "N/A")
        RENEWAL_TIME=$(kubectl get certificate "$cert_name" -n "$namespace" -o jsonpath='{.status.renewalTime}' 2>/dev/null || echo "N/A")
        DNS_NAMES=$(kubectl get certificate "$cert_name" -n "$namespace" -o jsonpath='{.spec.dnsNames[*]}' 2>/dev/null | tr ' ' '\n')
    fi

    echo -e "  Valid from: ${BLUE}$NOT_BEFORE${NC}"
    echo -e "  Valid until: ${BLUE}$NOT_AFTER${NC}"
    echo -e "  Renewal time: ${BLUE}$RENEWAL_TIME${NC}"

    # Check DNS names
    if [ -n "$DNS_NAMES" ]; then
        echo -e "  DNS names:"
        echo "$DNS_NAMES" | while read -r name; do
            echo -e "    - ${BLUE}$name${NC}"
        done
    fi

    echo ""
    return 0
}

# Function to check ClusterIssuer
check_cluster_issuer() {
    local issuer_name=$1

    echo -e "${YELLOW}Checking ClusterIssuer: ${issuer_name}${NC}"

    # Check if ClusterIssuer exists
    if ! kubectl get clusterissuer "$issuer_name" &>/dev/null; then
        echo -e "${RED}✗ ClusterIssuer not found${NC}"
        return 1
    fi

    # Get ClusterIssuer status
    ISSUER_JSON=$(kubectl get clusterissuer "$issuer_name" -o json)

    # Check ready condition
    if command -v jq &>/dev/null; then
        READY=$(echo "$ISSUER_JSON" | jq -r '.status.conditions[] | select(.type=="Ready") | .status')
        REASON=$(echo "$ISSUER_JSON" | jq -r '.status.conditions[] | select(.type=="Ready") | .reason')
        MESSAGE=$(echo "$ISSUER_JSON" | jq -r '.status.conditions[] | select(.type=="Ready") | .message')
        ACME_SERVER=$(echo "$ISSUER_JSON" | jq -r '.spec.acme.server // "N/A"')
    else
        READY=$(kubectl get clusterissuer "$issuer_name" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')
        REASON=$(kubectl get clusterissuer "$issuer_name" -o jsonpath='{.status.conditions[?(@.type=="Ready")].reason}')
        MESSAGE=$(kubectl get clusterissuer "$issuer_name" -o jsonpath='{.status.conditions[?(@.type=="Ready")].message}')
        ACME_SERVER=$(kubectl get clusterissuer "$issuer_name" -o jsonpath='{.spec.acme.server}' 2>/dev/null || echo "N/A")
    fi

    if [ "$READY" = "True" ]; then
        echo -e "${GREEN}✓ ClusterIssuer is ready${NC}"
    else
        echo -e "${RED}✗ ClusterIssuer is not ready${NC}"
        echo -e "  Reason: ${YELLOW}$REASON${NC}"
        echo -e "  Message: ${YELLOW}$MESSAGE${NC}"
        return 1
    fi

    # Get ACME server
    echo -e "  ACME server: ${BLUE}$ACME_SERVER${NC}"

    echo ""
    return 0
}

# Track overall status
OVERALL_STATUS=0

# Step 1: Check cert-manager is running
echo -e "${YELLOW}1. Checking cert-manager deployment...${NC}"
if kubectl get deployment cert-manager -n cert-manager &>/dev/null; then
    READY=$(kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.status.readyReplicas}')
    DESIRED=$(kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.spec.replicas}')

    if [ "$READY" = "$DESIRED" ]; then
        echo -e "${GREEN}✓ cert-manager is running ($READY/$DESIRED replicas)${NC}"
    else
        echo -e "${RED}✗ cert-manager is not fully ready ($READY/$DESIRED replicas)${NC}"
        OVERALL_STATUS=1
    fi
else
    echo -e "${RED}✗ cert-manager deployment not found${NC}"
    OVERALL_STATUS=1
fi
echo ""

# Step 2: Check ClusterIssuer
echo -e "${YELLOW}2. Checking ClusterIssuer...${NC}"
if ! check_cluster_issuer "letsencrypt-prod"; then
    OVERALL_STATUS=1
fi

# Step 3: Check certificates
echo -e "${YELLOW}3. Checking certificates...${NC}"

# Authentik certificate
if ! check_certificate "auth" "authentik-tls"; then
    OVERALL_STATUS=1
fi

# Check for any other certificates
echo -e "${YELLOW}4. Listing all certificates in cluster...${NC}"

if command -v jq &>/dev/null; then
    ALL_CERTS=$(kubectl get certificates -A -o json 2>/dev/null)

    if [ -n "$ALL_CERTS" ]; then
        CERT_COUNT=$(echo "$ALL_CERTS" | jq -r '.items | length')
        echo -e "${BLUE}Found $CERT_COUNT certificate(s):${NC}"

        echo "$ALL_CERTS" | jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name) - Ready: \(.status.conditions[] | select(.type=="Ready") | .status)"' | while read -r line; do
            if echo "$line" | grep -q "Ready: True"; then
                echo -e "  ${GREEN}✓${NC} $line"
            else
                echo -e "  ${RED}✗${NC} $line"
            fi
        done
    else
        echo -e "${YELLOW}⚠ No certificates found${NC}"
    fi
else
    # Fallback without jq
    CERT_LIST=$(kubectl get certificates -A --no-headers 2>/dev/null)

    if [ -n "$CERT_LIST" ]; then
        CERT_COUNT=$(echo "$CERT_LIST" | wc -l)
        echo -e "${BLUE}Found $CERT_COUNT certificate(s):${NC}"

        echo "$CERT_LIST" | while read -r namespace name ready secret age; do
            if [ "$ready" = "True" ]; then
                echo -e "  ${GREEN}✓${NC} $namespace/$name - Ready: $ready"
            else
                echo -e "  ${RED}✗${NC} $namespace/$name - Ready: $ready"
            fi
        done
    else
        echo -e "${YELLOW}⚠ No certificates found${NC}"
    fi
fi
echo ""

# Step 5: Check certificate secrets
echo -e "${YELLOW}5. Checking certificate secrets...${NC}"

# Authentik TLS secret
if kubectl get secret authentik-tls -n auth &>/dev/null; then
    echo -e "${GREEN}✓ Secret 'authentik-tls' exists in namespace 'auth'${NC}"

    # Check secret data
    TLS_CRT=$(kubectl get secret authentik-tls -n auth -o jsonpath='{.data.tls\.crt}' 2>/dev/null)
    TLS_KEY=$(kubectl get secret authentik-tls -n auth -o jsonpath='{.data.tls\.key}' 2>/dev/null)

    if [ -n "$TLS_CRT" ] && [ -n "$TLS_KEY" ]; then
        echo -e "${GREEN}✓ Secret contains tls.crt and tls.key${NC}"
    else
        echo -e "${RED}✗ Secret is missing certificate data${NC}"
        OVERALL_STATUS=1
    fi
else
    echo -e "${RED}✗ Secret 'authentik-tls' not found in namespace 'auth'${NC}"
    OVERALL_STATUS=1
fi
echo ""

# Step 6: Check CertificateRequests
echo -e "${YELLOW}6. Checking recent CertificateRequests...${NC}"

if command -v jq &>/dev/null; then
    CERT_REQUESTS=$(kubectl get certificaterequests -A --sort-by=.metadata.creationTimestamp -o json 2>/dev/null | jq -r '.items[-5:] | .[] | "\(.metadata.namespace)/\(.metadata.name) - \(.status.conditions[] | select(.type=="Ready") | .status) - \(.status.conditions[] | select(.type=="Ready") | .reason)"')

    if [ -n "$CERT_REQUESTS" ]; then
        echo "$CERT_REQUESTS" | while read -r line; do
            if echo "$line" | grep -q "True"; then
                echo -e "  ${GREEN}✓${NC} $line"
            else
                echo -e "  ${YELLOW}⚠${NC} $line"
            fi
        done
    else
        echo -e "${YELLOW}⚠ No CertificateRequests found${NC}"
    fi
else
    # Fallback without jq - show last 5 requests
    CERT_REQUESTS=$(kubectl get certificaterequests -A --sort-by=.metadata.creationTimestamp --no-headers 2>/dev/null | tail -5)

    if [ -n "$CERT_REQUESTS" ]; then
        echo "$CERT_REQUESTS" | while read -r namespace name ready age; do
            if [ "$ready" = "True" ]; then
                echo -e "  ${GREEN}✓${NC} $namespace/$name - Ready: $ready"
            else
                echo -e "  ${YELLOW}⚠${NC} $namespace/$name - Ready: $ready"
            fi
        done
    else
        echo -e "${YELLOW}⚠ No CertificateRequests found${NC}"
    fi
fi
echo ""

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ $OVERALL_STATUS -eq 0 ]; then
    echo -e "${GREEN}✅ All certificates are valid and ready${NC}"
else
    echo -e "${RED}❌ Some certificates have issues${NC}"
    echo ""
    echo -e "${YELLOW}💡 Troubleshooting tips:${NC}"
    echo -e "  - Check cert-manager logs: ${BLUE}kubectl logs -n cert-manager -l app=cert-manager${NC}"
    echo -e "  - Describe certificate: ${BLUE}kubectl describe certificate <name> -n <namespace>${NC}"
    echo -e "  - Check ClusterIssuer: ${BLUE}kubectl describe clusterissuer letsencrypt-prod${NC}"
    echo -e "  - View certificate requests: ${BLUE}kubectl get certificaterequests -A${NC}"
    echo -e "  - Check Cloudflare API token: ${BLUE}kubectl get secret cloudflare-api-token -n cert-manager${NC}"
fi

echo ""

exit $OVERALL_STATUS
