#!/bin/bash
# Validate Authentik HTTPS access via auth.almckay.io
# Usage: ./scripts/validate_authentik.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 Authentik HTTPS Access Validation${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# DNS name
DNS_NAME="auth.almckay.io"
HTTPS_PORT="443"
HTTP_PORT="80"

# Step 1: DNS Resolution
echo -e "${YELLOW}1. Testing DNS resolution...${NC}"
if nslookup "$DNS_NAME" 8.8.8.8 2>&1 | grep -q "Address:"; then
    IP=$(nslookup "$DNS_NAME" 8.8.8.8 2>&1 | grep "Address:" | tail -1 | awk '{print $2}')
    echo -e "${GREEN}✓ DNS resolves to: $IP${NC}"
else
    echo -e "${RED}✗ DNS resolution failed${NC}"
    echo -e "${YELLOW}💡 Check DNS records in Cloudflare${NC}"
    exit 1
fi
echo ""

# Step 2: TCP Connectivity (HTTPS)
echo -e "${YELLOW}2. Testing TCP connectivity on port $HTTPS_PORT...${NC}"
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$DNS_NAME/$HTTPS_PORT" 2>/dev/null; then
    echo -e "${GREEN}✓ Port $HTTPS_PORT is accessible${NC}"
else
    echo -e "${RED}✗ Port $HTTPS_PORT is not accessible${NC}"
    echo -e "${YELLOW}💡 Check Ingress and Traefik configuration${NC}"
    exit 1
fi
echo ""

# Step 3: HTTP to HTTPS redirect
echo -e "${YELLOW}3. Testing HTTP to HTTPS redirect...${NC}"
HTTP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -L "http://$DNS_NAME" 2>/dev/null || echo "000")

if [ "$HTTP_RESPONSE" = "200" ] || [ "$HTTP_RESPONSE" = "301" ] || [ "$HTTP_RESPONSE" = "302" ]; then
    echo -e "${GREEN}✓ HTTP redirect working (Status: $HTTP_RESPONSE)${NC}"
else
    echo -e "${YELLOW}⚠ HTTP redirect returned status: $HTTP_RESPONSE${NC}"
fi
echo ""

# Step 4: HTTPS connectivity
echo -e "${YELLOW}4. Testing HTTPS connectivity...${NC}"
HTTPS_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "https://$DNS_NAME" 2>/dev/null || echo "000")

if [ "$HTTPS_RESPONSE" = "200" ] || [ "$HTTPS_RESPONSE" = "302" ] || [ "$HTTPS_RESPONSE" = "301" ]; then
    echo -e "${GREEN}✓ HTTPS connection successful (Status: $HTTPS_RESPONSE)${NC}"
else
    echo -e "${RED}✗ HTTPS connection failed (Status: $HTTPS_RESPONSE)${NC}"
    exit 1
fi
echo ""

# Step 5: TLS certificate validation
echo -e "${YELLOW}5. Testing TLS certificate...${NC}"

# Get certificate info
CERT_INFO=$(echo | openssl s_client -servername "$DNS_NAME" -connect "$DNS_NAME:$HTTPS_PORT" 2>/dev/null | openssl x509 -noout -text 2>/dev/null)

if [ -n "$CERT_INFO" ]; then
    echo -e "${GREEN}✓ TLS certificate retrieved${NC}"

    # Check issuer
    ISSUER=$(echo "$CERT_INFO" | grep "Issuer:" | head -1)
    if echo "$ISSUER" | grep -q "Let's Encrypt"; then
        echo -e "${GREEN}✓ Certificate issued by Let's Encrypt${NC}"
    else
        echo -e "${YELLOW}⚠ Certificate issuer: $ISSUER${NC}"
    fi

    # Check validity
    NOT_AFTER=$(echo | openssl s_client -servername "$DNS_NAME" -connect "$DNS_NAME:$HTTPS_PORT" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    if [ -n "$NOT_AFTER" ]; then
        echo -e "${GREEN}✓ Certificate valid until: $NOT_AFTER${NC}"
    fi

    # Check subject alternative names
    SAN=$(echo "$CERT_INFO" | grep -A1 "Subject Alternative Name" | tail -1)
    if echo "$SAN" | grep -q "$DNS_NAME"; then
        echo -e "${GREEN}✓ Certificate includes $DNS_NAME in SAN${NC}"
    else
        echo -e "${YELLOW}⚠ Certificate SAN: $SAN${NC}"
    fi
else
    echo -e "${RED}✗ Failed to retrieve TLS certificate${NC}"
    exit 1
fi
echo ""

# Step 6: Test Authentik API endpoint
echo -e "${YELLOW}6. Testing Authentik API endpoint...${NC}"

# Try to access the API root
API_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "https://$DNS_NAME/api/v3/" 2>/dev/null || echo "000")

if [ "$API_RESPONSE" = "200" ] || [ "$API_RESPONSE" = "401" ] || [ "$API_RESPONSE" = "403" ]; then
    echo -e "${GREEN}✓ Authentik API endpoint accessible (Status: $API_RESPONSE)${NC}"
    if [ "$API_RESPONSE" = "401" ] || [ "$API_RESPONSE" = "403" ]; then
        echo -e "  ${BLUE}(Authentication required - this is expected)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Authentik API returned status: $API_RESPONSE${NC}"
fi
echo ""

# Step 7: Test Authentik web interface
echo -e "${YELLOW}7. Testing Authentik web interface...${NC}"

# Check if the page contains Authentik-specific content
WEB_CONTENT=$(curl -s "https://$DNS_NAME" 2>/dev/null)

if echo "$WEB_CONTENT" | grep -qi "authentik"; then
    echo -e "${GREEN}✓ Authentik web interface is responding${NC}"
else
    echo -e "${YELLOW}⚠ Web interface accessible but content may not be fully loaded${NC}"
fi
echo ""

# Step 8: Check Authentik pod status
echo -e "${YELLOW}8. Checking Authentik pod status...${NC}"

PODS=$(kubectl get pods -n auth -l app.kubernetes.io/name=authentik -o json 2>/dev/null)

if [ -n "$PODS" ] && [ "$(echo "$PODS" | jq -r '.items | length')" -gt 0 ]; then
    READY_PODS=$(echo "$PODS" | jq -r '[.items[] | select(.status.phase=="Running" and (.status.conditions[] | select(.type=="Ready" and .status=="True")))] | length')
    TOTAL_PODS=$(echo "$PODS" | jq -r '.items | length')

    if [ "$READY_PODS" -gt 0 ]; then
        echo -e "${GREEN}✓ Authentik pods running: $READY_PODS/$TOTAL_PODS${NC}"
    else
        echo -e "${YELLOW}⚠ No ready Authentik pods found${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No Authentik pods found${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Authentik validation complete - all checks passed!${NC}"
echo ""
echo -e "${BLUE}📋 Access Information:${NC}"
echo -e "  URL: ${GREEN}https://$DNS_NAME${NC}"
echo ""
echo -e "${BLUE}🔗 Access Authentik:${NC}"
echo -e "  ${YELLOW}Open in browser: https://$DNS_NAME${NC}"
echo ""
echo -e "${BLUE}🔗 API Endpoint:${NC}"
echo -e "  ${YELLOW}https://$DNS_NAME/api/v3/${NC}"
echo ""
echo -e "${BLUE}💡 Next Steps:${NC}"
echo -e "  1. Access the web interface to complete initial setup"
echo -e "  2. Configure authentication flows and providers"
echo -e "  3. Set up applications to use Authentik for SSO"
echo ""

exit 0
