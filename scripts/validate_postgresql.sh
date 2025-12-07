#!/bin/bash
# Validate PostgreSQL connectivity via postgres.almckay.io
# Usage: ./scripts/validate_postgresql.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 PostgreSQL Connectivity Validation${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# DNS name
DNS_NAME="postgres.almckay.io"
PORT="5432"

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

# Step 3: Get credentials from secret
echo -e "${YELLOW}3. Retrieving credentials from Kubernetes secret...${NC}"
if ! kubectl get secret postgresql-credentials -n database &>/dev/null; then
    echo -e "${RED}✗ Secret 'postgresql-credentials' not found in namespace 'database'${NC}"
    echo -e "${YELLOW}💡 Ensure the secret is created and decrypted by Flux${NC}"
    exit 1
fi

USERNAME=$(kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.username}' 2>/dev/null | base64 -d)
PASSWORD=$(kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.password}' 2>/dev/null | base64 -d)
DATABASE=$(kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.database}' 2>/dev/null | base64 -d)

if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ] || [ -z "$DATABASE" ]; then
    echo -e "${RED}✗ Failed to retrieve credentials from secret${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Credentials retrieved${NC}"
echo -e "  Username: ${BLUE}$USERNAME${NC}"
echo -e "  Database: ${BLUE}$DATABASE${NC}"
echo ""

# Step 4: Test database connection
echo -e "${YELLOW}4. Testing database connection and authentication...${NC}"

# Try to connect using psql in a temporary pod
CONNECTION_TEST=$(kubectl run postgresql-test-$RANDOM \
    --image=postgres:15-alpine \
    --restart=Never \
    --rm \
    -i \
    --quiet \
    --namespace=database \
    --env="PGPASSWORD=$PASSWORD" \
    --command -- \
    psql -h "$DNS_NAME" -p "$PORT" -U "$USERNAME" -d "$DATABASE" -c "SELECT version();" 2>&1)

if echo "$CONNECTION_TEST" | grep -q "PostgreSQL"; then
    echo -e "${GREEN}✓ Database connection successful${NC}"
    echo -e "${GREEN}✓ Authentication successful${NC}"
    VERSION=$(echo "$CONNECTION_TEST" | grep "PostgreSQL" | head -1 | awk '{print $2}')
    echo -e "  Version: ${BLUE}$VERSION${NC}"
else
    echo -e "${RED}✗ Database connection failed${NC}"
    echo -e "${YELLOW}Error output:${NC}"
    echo "$CONNECTION_TEST"
    exit 1
fi
echo ""

# Step 5: Test basic operations
echo -e "${YELLOW}5. Testing basic database operations...${NC}"

# Create test table, insert data, query, and cleanup
OPERATIONS_TEST=$(kubectl run postgresql-ops-test-$RANDOM \
    --image=postgres:15-alpine \
    --restart=Never \
    --rm \
    -i \
    --quiet \
    --namespace=database \
    --env="PGPASSWORD=$PASSWORD" \
    --command -- \
    psql -h "$DNS_NAME" -p "$PORT" -U "$USERNAME" -d "$DATABASE" <<EOF 2>&1
CREATE TABLE IF NOT EXISTS test_validation (id SERIAL PRIMARY KEY, test_value TEXT);
INSERT INTO test_validation (test_value) VALUES ('validation_test');
SELECT test_value FROM test_validation WHERE test_value = 'validation_test';
DROP TABLE test_validation;
EOF
)

if echo "$OPERATIONS_TEST" | grep -q "validation_test"; then
    echo -e "${GREEN}✓ CREATE TABLE successful${NC}"
    echo -e "${GREEN}✓ INSERT successful${NC}"
    echo -e "${GREEN}✓ SELECT successful${NC}"
    echo -e "${GREEN}✓ DROP TABLE successful${NC}"
else
    echo -e "${RED}✗ Database operations failed${NC}"
    echo -e "${YELLOW}Error output:${NC}"
    echo "$OPERATIONS_TEST"
    exit 1
fi
echo ""

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ PostgreSQL validation complete - all checks passed!${NC}"
echo ""
echo -e "${BLUE}📋 Connection Information:${NC}"
echo -e "  Host: ${GREEN}$DNS_NAME${NC}"
echo -e "  Port: ${GREEN}$PORT${NC}"
echo -e "  Database: ${GREEN}$DATABASE${NC}"
echo -e "  Username: ${GREEN}$USERNAME${NC}"
echo ""
echo -e "${BLUE}🔗 Connection Example:${NC}"
echo -e "  ${YELLOW}psql -h $DNS_NAME -p $PORT -U $USERNAME -d $DATABASE${NC}"
echo ""
echo -e "${BLUE}🔗 Connection String:${NC}"
echo -e "  ${YELLOW}postgresql://$USERNAME:<password>@$DNS_NAME:$PORT/$DATABASE${NC}"
echo ""

exit 0
