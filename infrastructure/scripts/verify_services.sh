#!/bin/bash
# Verify production services are accessible via DNS
# Usage: ./scripts/verify_services.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Set KUBECONFIG if not set
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

echo -e "${BLUE}🔍 Verifying Production Services${NC}"
echo ""

# Get Traefik LoadBalancer IP dynamically
TRAEFIK_IP=$(kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)

if [ -z "$TRAEFIK_IP" ]; then
    echo -e "${RED}✗ Could not determine Traefik LoadBalancer IP${NC}"
    echo -e "  Check: kubectl get svc -n kube-system traefik"
    exit 1
fi

echo -e "${BLUE}Traefik LoadBalancer IP: ${TRAEFIK_IP}${NC}"
echo ""

# Test DNS resolution
echo -e "${YELLOW}1. Testing DNS Resolution...${NC}"
echo ""

for service in postgres redis auth grafana prometheus chat llm temporal gitops; do
    echo -n "  ${service}.almckay.io: "
    resolved_ip=$(nslookup "${service}.almckay.io" 2>/dev/null | grep -A1 "Name:" | grep "Address:" | awk '{print $2}' | head -1)

    if [ "$resolved_ip" = "$TRAEFIK_IP" ]; then
        echo -e "${GREEN}✓ Resolves to ${resolved_ip}${NC}"
    elif [ -n "$resolved_ip" ]; then
        echo -e "${YELLOW}⚠ Resolves to ${resolved_ip} (expected ${TRAEFIK_IP})${NC}"
    else
        echo -e "${RED}✗ DNS resolution failed${NC}"
    fi
done

echo ""

# Test TCP connectivity
echo -e "${YELLOW}2. Testing TCP Connectivity...${NC}"
echo ""

# TCP services
declare -A TCP_SERVICES=(
    ["PostgreSQL"]="postgres.almckay.io:5432"
    ["Redis"]="redis.almckay.io:6379"
)

for name in "${!TCP_SERVICES[@]}"; do
    endpoint="${TCP_SERVICES[$name]}"
    host=$(echo "$endpoint" | cut -d: -f1)
    port=$(echo "$endpoint" | cut -d: -f2)

    echo -n "  $name ($port): "
    if nc -z -w 3 "$host" "$port" 2>/dev/null; then
        echo -e "${GREEN}✓ Port accessible${NC}"
    else
        echo -e "${RED}✗ Port not accessible${NC}"
    fi
done

# HTTPS services
echo ""
echo -e "${YELLOW}3. Testing HTTPS Connectivity...${NC}"
echo ""

# Grafana and Prometheus are omitted: the monitoring stack is scaled to zero,
# so their Ingresses answer 503 with no backend.
HTTPS_HOSTS=(
    "auth.almckay.io"
    "temporal.almckay.io"
    "falkordb.almckay.io"
    "qdrant.almckay.io"
)

for host in "${HTTPS_HOSTS[@]}"; do
    echo -n "  $host: "
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "https://$host" 2>/dev/null || echo "000")

    if [ "$http_code" = "200" ] || [ "$http_code" = "302" ] || [ "$http_code" = "301" ] || [ "$http_code" = "303" ]; then
        echo -e "${GREEN}✓ HTTP $http_code${NC}"
    elif [ "$http_code" = "401" ] || [ "$http_code" = "403" ]; then
        echo -e "${GREEN}✓ HTTP $http_code (auth required)${NC}"
    elif [ "$http_code" = "000" ]; then
        echo -e "${RED}✗ Connection failed${NC}"
    else
        echo -e "${YELLOW}⚠ HTTP $http_code${NC}"
    fi
done

echo ""

# Summary
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}✅ Service Verification Complete${NC}"
echo ""
echo -e "${BLUE}📋 Service Endpoints:${NC}"
echo -e "  ${GREEN}PostgreSQL:${NC} postgres.almckay.io:5432"
echo -e "  ${GREEN}Redis:${NC} redis.almckay.io:6379"
echo -e "  ${GREEN}Authentik:${NC} https://auth.almckay.io"
echo -e "  ${GREEN}Grafana:${NC} https://grafana.almckay.io"
echo -e "  ${GREEN}Prometheus:${NC} https://prometheus.almckay.io"
echo -e "  ${GREEN}Temporal:${NC} https://temporal.almckay.io"
echo -e "  ${GREEN}FalkorDB:${NC} https://falkordb.almckay.io (browser), falkordb.almckay.io:6380 (RESP)"
echo -e "  ${GREEN}Qdrant:${NC} https://qdrant.almckay.io"
echo ""
echo -e "${BLUE}🔗 Connection Examples:${NC}"
echo -e "  ${YELLOW}psql -h postgres.almckay.io -p 5432 -U authentik -d authentik${NC}"
echo -e "  ${YELLOW}redis-cli -h redis.almckay.io -p 6379${NC}"
echo -e "  ${YELLOW}curl https://auth.almckay.io${NC}"
echo ""
echo -e "${BLUE}💡 For comprehensive validation, run:${NC}"
echo -e "  ${YELLOW}./scripts/validate_cluster.sh --full${NC}"
echo ""
