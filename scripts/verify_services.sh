#!/bin/bash
# Verify production services are accessible via DNS

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 Verifying Production Services${NC}"
echo ""

# Test DNS resolution
echo -e "${YELLOW}1. Testing DNS Resolution...${NC}"
echo ""

for service in postgres redis auth; do
    echo -n "  ${service}.almckay.io: "
    if nslookup ${service}.almckay.io 8.8.8.8 2>&1 | grep -q "100.71.65.62"; then
        echo -e "${GREEN}✓ Resolves to 100.71.65.62${NC}"
    else
        echo -e "${RED}✗ DNS resolution failed${NC}"
    fi
done

echo ""

# Test TCP connectivity
echo -e "${YELLOW}2. Testing TCP Connectivity...${NC}"
echo ""

echo -n "  PostgreSQL (5432): "
if nc -zv -w 2 postgres.almckay.io 5432 2>&1 | grep -q "succeeded"; then
    echo -e "${GREEN}✓ Port accessible${NC}"
else
    echo -e "${RED}✗ Port not accessible${NC}"
fi

echo -n "  Redis (6379): "
if nc -zv -w 2 redis.almckay.io 6379 2>&1 | grep -q "succeeded"; then
    echo -e "${GREEN}✓ Port accessible${NC}"
else
    echo -e "${RED}✗ Port not accessible${NC}"
fi

echo -n "  Authentik (443): "
if nc -zv -w 2 auth.almckay.io 443 2>&1 | grep -q "succeeded"; then
    echo -e "${GREEN}✓ Port accessible${NC}"
else
    echo -e "${RED}✗ Port not accessible${NC}"
fi

echo ""

# Test PostgreSQL authentication
echo -e "${YELLOW}3. Testing PostgreSQL Authentication...${NC}"
echo ""

PGPASSWORD=$(kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.password}' | base64 -d 2>/dev/null)

if [ -n "$PGPASSWORD" ]; then
    echo -n "  Database connection: "
    if kubectl run psql-verify --image=postgres:15-alpine --restart=Never --rm -it \
        --namespace=database --env="PGPASSWORD=$PGPASSWORD" \
        --command -- psql -h postgres.almckay.io -p 5432 -U authentik -d authentik \
        -c "SELECT 1;" &>/dev/null; then
        echo -e "${GREEN}✓ Authentication successful${NC}"
    else
        echo -e "${RED}✗ Authentication failed${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ Could not retrieve password from secret${NC}"
fi

echo ""

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}✅ Service Verification Complete${NC}"
echo ""
echo -e "${BLUE}📋 Service Endpoints:${NC}"
echo -e "  ${GREEN}PostgreSQL:${NC} postgres.almckay.io:5432"
echo -e "  ${GREEN}Redis:${NC} redis.almckay.io:6379"
echo -e "  ${GREEN}Authentik:${NC} https://auth.almckay.io"
echo ""
echo -e "${BLUE}🔗 Connection Examples:${NC}"
echo -e "  ${YELLOW}psql -h postgres.almckay.io -p 5432 -U authentik -d authentik${NC}"
echo -e "  ${YELLOW}redis-cli -h redis.almckay.io -p 6379${NC}"
echo -e "  ${YELLOW}curl https://auth.almckay.io${NC}"
echo ""
