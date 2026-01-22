#!/bin/bash
# Setup DNS records for production services
# This script provides instructions and commands to create DNS records in Cloudflare

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 DNS Configuration for Production Services${NC}"
echo ""

# Get Traefik LoadBalancer IP
echo -e "${YELLOW}📍 Getting Traefik LoadBalancer IP...${NC}"
TRAEFIK_IP=$(kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

if [ -z "$TRAEFIK_IP" ]; then
    echo -e "${RED}❌ Failed to get Traefik IP${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Traefik IP: $TRAEFIK_IP${NC}"
echo ""

# Domain
DOMAIN="almckay.io"

echo -e "${BLUE}📋 DNS Records to Create in Cloudflare:${NC}"
echo ""
echo -e "${YELLOW}Domain: $DOMAIN${NC}"
echo -e "${YELLOW}Target IP: $TRAEFIK_IP${NC}"
echo ""

# Services
declare -a services=("postgres" "redis" "auth")

echo -e "${BLUE}Required A Records:${NC}"
echo ""
for service in "${services[@]}"; do
    echo -e "  ${GREEN}●${NC} Name: ${YELLOW}$service${NC}"
    echo -e "    Type: ${YELLOW}A${NC}"
    echo -e "    Content: ${YELLOW}$TRAEFIK_IP${NC}"
    echo -e "    TTL: ${YELLOW}Auto${NC}"
    echo -e "    Proxy: ${YELLOW}No (DNS only)${NC}"
    echo ""
done

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if we have a Cloudflare API token
echo -e "${YELLOW}🔐 Checking for Cloudflare API token...${NC}"
if kubectl get secret cloudflare-api-token -n cert-manager &>/dev/null; then
    echo -e "${GREEN}✓ Cloudflare secret exists in cert-manager namespace${NC}"
    echo -e "${YELLOW}  Note: This token is used for cert-manager DNS-01 challenges${NC}"
    echo ""
else
    echo -e "${RED}✗ No Cloudflare API token found${NC}"
    echo ""
fi

echo -e "${BLUE}📝 Manual Configuration Steps:${NC}"
echo ""
echo -e "1. Log in to Cloudflare Dashboard: ${YELLOW}https://dash.cloudflare.com/${NC}"
echo -e "2. Select your domain: ${YELLOW}$DOMAIN${NC}"
echo -e "3. Go to ${YELLOW}DNS${NC} → ${YELLOW}Records${NC}"
echo -e "4. Click ${YELLOW}Add record${NC} for each service:"
echo ""

for service in "${services[@]}"; do
    echo -e "   ${GREEN}$service.$DOMAIN${NC}"
    echo -e "   - Type: A"
    echo -e "   - Name: $service"
    echo -e "   - IPv4 address: $TRAEFIK_IP"
    echo -e "   - Proxy status: DNS only (gray cloud)"
    echo -e "   - TTL: Auto"
    echo ""
done

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${BLUE}🔍 Verification Commands:${NC}"
echo ""
echo -e "After creating the DNS records, wait 1-2 minutes for propagation, then test:"
echo ""
for service in "${services[@]}"; do
    echo -e "  ${YELLOW}nslookup $service.$DOMAIN${NC}"
done
echo ""

echo -e "${BLUE}🔗 Service Endpoints:${NC}"
echo ""
echo -e "  ${GREEN}PostgreSQL:${NC} psql -h postgres.$DOMAIN -p 5432 -U authentik -d authentik"
echo -e "  ${GREEN}Redis:${NC} redis-cli -h redis.$DOMAIN -p 6379"
echo -e "  ${GREEN}Authentik:${NC} https://auth.$DOMAIN"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Offer to test connectivity
echo -e "${YELLOW}Would you like to test TCP connectivity to the Traefik IP? (y/n)${NC}"
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${BLUE}Testing connectivity...${NC}"
    echo ""

    # Test PostgreSQL port
    if nc -zv -w 2 "$TRAEFIK_IP" 5432 2>&1 | grep -q "succeeded"; then
        echo -e "${GREEN}✓ PostgreSQL port 5432 is accessible${NC}"
    else
        echo -e "${RED}✗ PostgreSQL port 5432 is not accessible${NC}"
    fi

    # Test Redis port
    if nc -zv -w 2 "$TRAEFIK_IP" 6379 2>&1 | grep -q "succeeded"; then
        echo -e "${GREEN}✓ Redis port 6379 is accessible${NC}"
    else
        echo -e "${RED}✗ Redis port 6379 is not accessible${NC}"
    fi

    # Test HTTPS port
    if nc -zv -w 2 "$TRAEFIK_IP" 443 2>&1 | grep -q "succeeded"; then
        echo -e "${GREEN}✓ HTTPS port 443 is accessible${NC}"
    else
        echo -e "${RED}✗ HTTPS port 443 is not accessible${NC}"
    fi

    echo ""
fi

echo -e "${GREEN}✅ DNS configuration guide complete!${NC}"
echo ""
echo -e "${YELLOW}💡 Tip: You can also use the Cloudflare API to automate this.${NC}"
echo -e "${YELLOW}   See scripts/configure_dns.py for API-based configuration.${NC}"
echo ""
