#!/bin/bash
# Get Traefik LoadBalancer IP for DNS configuration
# Usage: ./scripts/get_traefik_ip.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 Traefik LoadBalancer IP Information${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Get Traefik service
echo -e "${YELLOW}Retrieving Traefik service information...${NC}"

if ! kubectl get svc traefik -n kube-system &>/dev/null; then
    echo -e "${RED}✗ Traefik service not found in kube-system namespace${NC}"
    exit 1
fi

# Get LoadBalancer IP
TRAEFIK_IP=$(kubectl get svc traefik -n kube-system -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)

if [ -z "$TRAEFIK_IP" ]; then
    echo -e "${RED}✗ LoadBalancer IP not assigned${NC}"
    echo ""
    echo -e "${YELLOW}💡 Troubleshooting:${NC}"
    echo -e "  1. Check if Traefik service is type LoadBalancer:"
    echo -e "     ${BLUE}kubectl get svc traefik -n kube-system${NC}"
    echo -e "  2. Check service events:"
    echo -e "     ${BLUE}kubectl describe svc traefik -n kube-system${NC}"
    echo -e "  3. Verify K3s servicelb is running:"
    echo -e "     ${BLUE}kubectl get pods -n kube-system -l app=svclb-traefik${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Traefik LoadBalancer IP: ${TRAEFIK_IP}${NC}"
echo ""

# Get service details
echo -e "${YELLOW}Service Details:${NC}"
SERVICE_TYPE=$(kubectl get svc traefik -n kube-system -o jsonpath='{.spec.type}')
echo -e "  Type: ${BLUE}$SERVICE_TYPE${NC}"

# Get ports
echo -e "  Ports:"
if command -v jq &>/dev/null; then
    kubectl get svc traefik -n kube-system -o json | jq -r '.spec.ports[] | "    - \(.name): \(.port)/\(.protocol) → \(.targetPort)"' | while read -r line; do
        echo -e "  ${BLUE}$line${NC}"
    done
else
    # Fallback without jq
    kubectl get svc traefik -n kube-system -o jsonpath='{range .spec.ports[*]}{.name}{": "}{.port}{"/"}{.protocol}{" → "}{.targetPort}{"\n"}{end}' | while read -r line; do
        echo -e "    ${BLUE}- $line${NC}"
    done
fi
echo ""

# Check if IP is on Tailscale network
echo -e "${YELLOW}Network Information:${NC}"
if [[ "$TRAEFIK_IP" == 100.* ]]; then
    echo -e "${GREEN}✓ IP is on Tailscale network (CGNAT range 100.64.0.0/10)${NC}"
else
    echo -e "${YELLOW}⚠ IP may not be on Tailscale network${NC}"
fi
echo ""

# DNS Configuration
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}📋 DNS Configuration${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Create the following A records in Cloudflare:${NC}"
echo ""
echo -e "  ${GREEN}postgres.almckay.io${NC} → ${BLUE}$TRAEFIK_IP${NC}"
echo -e "  ${GREEN}redis.almckay.io${NC} → ${BLUE}$TRAEFIK_IP${NC}"
echo -e "  ${GREEN}auth.almckay.io${NC} → ${BLUE}$TRAEFIK_IP${NC}"
echo ""
echo -e "${YELLOW}Important:${NC} Set Proxy status to ${BLUE}DNS only${NC} (gray cloud icon)"
echo ""

# Provide commands
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔧 Quick Actions${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}1. Manual DNS Configuration:${NC}"
echo -e "   ${BLUE}./scripts/setup_dns_records.sh${NC}"
echo ""
echo -e "${YELLOW}2. Automated DNS Configuration (requires Cloudflare API token):${NC}"
echo -e "   ${BLUE}uv run python scripts/configure_dns.py${NC}"
echo ""
echo -e "${YELLOW}3. Test connectivity to Traefik IP:${NC}"
echo -e "   ${BLUE}nc -zv $TRAEFIK_IP 5432${NC}  # PostgreSQL"
echo -e "   ${BLUE}nc -zv $TRAEFIK_IP 6379${NC}  # Redis"
echo -e "   ${BLUE}nc -zv $TRAEFIK_IP 443${NC}   # HTTPS"
echo ""
echo -e "${YELLOW}4. Verify DNS after configuration:${NC}"
echo -e "   ${BLUE}nslookup postgres.almckay.io${NC}"
echo -e "   ${BLUE}nslookup redis.almckay.io${NC}"
echo -e "   ${BLUE}nslookup auth.almckay.io${NC}"
echo ""

# Export for scripting
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}📝 For Scripting${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Export as environment variable:${NC}"
echo -e "  ${BLUE}export TRAEFIK_IP=$TRAEFIK_IP${NC}"
echo ""
echo -e "${YELLOW}Use in scripts:${NC}"
echo -e "  ${BLUE}TRAEFIK_IP=\$(kubectl get svc traefik -n kube-system -o jsonpath='{.status.loadBalancer.ingress[0].ip}')${NC}"
echo ""

exit 0
