#!/bin/bash
# Validate Redis connectivity via redis.almckay.io
# Usage: ./scripts/validate_redis.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 Redis Connectivity Validation${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# DNS name
DNS_NAME="redis.almckay.io"
PORT="6379"

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

# Step 2: TCP Connectivity
echo -e "${YELLOW}2. Testing TCP connectivity on port $PORT...${NC}"
if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$DNS_NAME/$PORT" 2>/dev/null; then
    echo -e "${GREEN}✓ Port $PORT is accessible${NC}"
else
    echo -e "${RED}✗ Port $PORT is not accessible${NC}"
    echo -e "${YELLOW}💡 Check IngressRouteTCP and Traefik configuration${NC}"
    exit 1
fi
echo ""

# Step 3: Get password from secret
echo -e "${YELLOW}3. Retrieving password from Kubernetes secret...${NC}"
if ! kubectl get secret redis-credentials -n cache &>/dev/null; then
    echo -e "${RED}✗ Secret 'redis-credentials' not found in namespace 'cache'${NC}"
    echo -e "${YELLOW}💡 Ensure the secret is created and decrypted by Flux${NC}"
    exit 1
fi

PASSWORD=$(kubectl get secret redis-credentials -n cache -o jsonpath='{.data.redis-password}' 2>/dev/null | base64 -d)

if [ -z "$PASSWORD" ]; then
    echo -e "${RED}✗ Failed to retrieve password from secret${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Password retrieved${NC}"
echo ""

# Step 4: Test Redis connection with PING
echo -e "${YELLOW}4. Testing Redis connection with PING...${NC}"

PING_TEST=$(kubectl run redis-test-$RANDOM \
    --image=redis:7-alpine \
    --restart=Never \
    --rm \
    -i \
    --quiet \
    --namespace=cache \
    --command -- \
    redis-cli -h "$DNS_NAME" -p "$PORT" -a "$PASSWORD" PING 2>&1)

if echo "$PING_TEST" | grep -q "PONG"; then
    echo -e "${GREEN}✓ Redis connection successful${NC}"
    echo -e "${GREEN}✓ Authentication successful${NC}"
else
    echo -e "${RED}✗ Redis connection failed${NC}"
    echo -e "${YELLOW}Error output:${NC}"
    echo "$PING_TEST"
    exit 1
fi
echo ""

# Step 5: Test Redis INFO command
echo -e "${YELLOW}5. Testing Redis INFO command...${NC}"

INFO_TEST=$(kubectl run redis-info-test-$RANDOM \
    --image=redis:7-alpine \
    --restart=Never \
    --rm \
    -i \
    --quiet \
    --namespace=cache \
    --command -- \
    redis-cli -h "$DNS_NAME" -p "$PORT" -a "$PASSWORD" INFO server 2>&1)

if echo "$INFO_TEST" | grep -q "redis_version"; then
    echo -e "${GREEN}✓ INFO command successful${NC}"
    VERSION=$(echo "$INFO_TEST" | grep "redis_version:" | cut -d: -f2 | tr -d '\r')
    echo -e "  Version: ${BLUE}$VERSION${NC}"
else
    echo -e "${RED}✗ INFO command failed${NC}"
    echo -e "${YELLOW}Error output:${NC}"
    echo "$INFO_TEST"
    exit 1
fi
echo ""

# Step 6: Test basic operations (SET/GET/DEL)
echo -e "${YELLOW}6. Testing basic Redis operations...${NC}"

# Generate random key to avoid conflicts
TEST_KEY="validation_test_$(date +%s)"
TEST_VALUE="test_value_$(date +%s)"

# SET operation
SET_TEST=$(kubectl run redis-set-test-$RANDOM \
    --image=redis:7-alpine \
    --restart=Never \
    --rm \
    -i \
    --quiet \
    --namespace=cache \
    --command -- \
    redis-cli -h "$DNS_NAME" -p "$PORT" -a "$PASSWORD" SET "$TEST_KEY" "$TEST_VALUE" 2>&1)

if echo "$SET_TEST" | grep -q "OK"; then
    echo -e "${GREEN}✓ SET operation successful${NC}"
else
    echo -e "${RED}✗ SET operation failed${NC}"
    exit 1
fi

# GET operation
GET_TEST=$(kubectl run redis-get-test-$RANDOM \
    --image=redis:7-alpine \
    --restart=Never \
    --rm \
    -i \
    --quiet \
    --namespace=cache \
    --command -- \
    redis-cli -h "$DNS_NAME" -p "$PORT" -a "$PASSWORD" GET "$TEST_KEY" 2>&1)

if echo "$GET_TEST" | grep -q "$TEST_VALUE"; then
    echo -e "${GREEN}✓ GET operation successful${NC}"
else
    echo -e "${RED}✗ GET operation failed${NC}"
    exit 1
fi

# DEL operation
DEL_TEST=$(kubectl run redis-del-test-$RANDOM \
    --image=redis:7-alpine \
    --restart=Never \
    --rm \
    -i \
    --quiet \
    --namespace=cache \
    --command -- \
    redis-cli -h "$DNS_NAME" -p "$PORT" -a "$PASSWORD" DEL "$TEST_KEY" 2>&1)

if echo "$DEL_TEST" | grep -q "1"; then
    echo -e "${GREEN}✓ DEL operation successful${NC}"
else
    echo -e "${RED}✗ DEL operation failed${NC}"
    exit 1
fi
echo ""

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Redis validation complete - all checks passed!${NC}"
echo ""
echo -e "${BLUE}📋 Connection Information:${NC}"
echo -e "  Host: ${GREEN}$DNS_NAME${NC}"
echo -e "  Port: ${GREEN}$PORT${NC}"
echo ""
echo -e "${BLUE}🔗 Connection Example:${NC}"
echo -e "  ${YELLOW}redis-cli -h $DNS_NAME -p $PORT -a <password>${NC}"
echo ""
echo -e "${BLUE}🔗 Connection String:${NC}"
echo -e "  ${YELLOW}redis://:<password>@$DNS_NAME:$PORT${NC}"
echo ""

exit 0
