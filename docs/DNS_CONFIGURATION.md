# DNS Configuration for Production Services

This guide explains how to configure DNS records in Cloudflare for PostgreSQL, Redis, and Authentik services.

## Overview

The production services are exposed via Traefik's LoadBalancer service on the Tailscale network. To access these services using friendly DNS names (e.g., `postgres.almckay.io`), you need to create A records in Cloudflare pointing to the Traefik LoadBalancer IP.

## Prerequisites

- Cloudflare API token with DNS edit permissions (stored in `cert-manager` namespace)
- Traefik deployed with TCP entry points for PostgreSQL (5432) and Redis (6379)
- Services deployed in the cluster

## Get Traefik LoadBalancer IP

```bash
kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

Expected output: `100.71.65.62` (or your Tailscale IP)

## Required DNS Records

Create the following A records in Cloudflare:

| Name | Type | Content | TTL | Proxy Status |
|------|------|---------|-----|--------------|
| postgres | A | 100.71.65.62 | Auto | DNS only (gray cloud) |
| redis | A | 100.71.65.62 | Auto | DNS only (gray cloud) |
| auth | A | 100.71.65.62 | Auto | DNS only (gray cloud) |

**Important**: Make sure "Proxy status" is set to "DNS only" (gray cloud icon), not "Proxied" (orange cloud). Cloudflare's proxy doesn't support non-HTTP protocols like PostgreSQL and Redis.

## Cloudflare API Configuration

DNS records are managed programmatically via the Cloudflare API. The API token is stored in the cluster and can be used for creating, updating, and deleting DNS records.

### Step 1: Create API Token

1. Go to https://dash.cloudflare.com/profile/api-tokens
2. Click **Create Token**
3. Use the **Edit zone DNS** template
4. Configure permissions:
   - **Zone** → **DNS** → **Edit**
   - **Zone Resources** → **Include** → **Specific zone** → `almckay.io`
5. Click **Continue to summary**
6. Click **Create Token**
7. **Copy the token** (you won't be able to see it again!)

### Step 2: Store API Token in Kubernetes

```bash
# Create or update the Cloudflare API token secret
kubectl create secret generic cloudflare-dns-token \
  --from-literal=api-token=<YOUR_API_TOKEN> \
  -n kube-system \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Step 3: Create DNS Record via API

The Cloudflare API token is stored in the `cert-manager` namespace (used for DNS-01 challenges):

```bash
# Get the Cloudflare API token
CF_TOKEN=$(kubectl get secret cloudflare-api-token -n cert-manager -o jsonpath='{.data.api-token}' | base64 -d)
```

#### Get Zone ID

First, retrieve the zone ID for your domain:

```bash
curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=almckay.io" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" | jq -r '.result[0].id'
```

#### Create A Record

Create a new DNS A record pointing to the Traefik LoadBalancer IP:

```bash
# Set variables
ZONE_ID="<zone-id-from-above>"
RECORD_NAME="myservice"  # e.g., temporal, grafana, etc.
TRAEFIK_IP=$(kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Create the DNS record
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  --data "{
    \"type\": \"A\",
    \"name\": \"${RECORD_NAME}\",
    \"content\": \"${TRAEFIK_IP}\",
    \"ttl\": 1,
    \"proxied\": false
  }" | jq .
```

#### List Existing DNS Records

To view all DNS records for the zone:

```bash
curl -s -X GET "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" \
  -H "Authorization: Bearer $CF_TOKEN" | jq '.results[] | {id, name, type, content}'
```

#### Update Existing Record

To update an existing DNS record:

```bash
RECORD_ID="<record-id>"
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/${RECORD_ID}" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  --data "{\"content\": \"${NEW_IP}\"}" | jq .
```

#### Delete a Record

To delete a DNS record:

```bash
RECORD_ID="<record-id>"
curl -s -X DELETE "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/${RECORD_ID}" \
  -H "Authorization: Bearer $CF_TOKEN" | jq .
```

## Verification

### Test DNS Resolution

Wait 1-2 minutes for DNS propagation, then test:

```bash
# Test DNS resolution
nslookup postgres.almckay.io
nslookup redis.almckay.io
nslookup auth.almckay.io
```

Expected output for each:
```
Server:         <your-dns-server>
Address:        <your-dns-server>#53

Non-authoritative answer:
Name:   postgres.almckay.io
Address: 100.71.65.62
```

### Test TCP Connectivity

```bash
# Test PostgreSQL port
nc -zv postgres.almckay.io 5432

# Test Redis port
nc -zv redis.almckay.io 6379

# Test HTTPS port (for Authentik)
nc -zv auth.almckay.io 443
```

### Test Service Connectivity

**PostgreSQL**:
```bash
# Get password from secret
PGPASSWORD=$(kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.password}' | base64 -d)

# Connect to PostgreSQL
psql -h postgres.almckay.io -p 5432 -U authentik -d authentik -c "SELECT version();"
```

**Redis**:
```bash
# Get password from secret
REDIS_PASSWORD=$(kubectl get secret redis-credentials -n cache -o jsonpath='{.data.redis-password}' | base64 -d)

# Connect to Redis
redis-cli -h redis.almckay.io -p 6379 -a "$REDIS_PASSWORD" PING
```

**Authentik**:
```bash
# Test HTTPS access
curl -I https://auth.almckay.io
```

## Troubleshooting

### DNS Not Resolving

**Problem**: `nslookup` returns "No answer" or "NXDOMAIN"

**Solutions**:
1. Wait 1-2 minutes for DNS propagation
2. Verify the DNS record exists in Cloudflare dashboard
3. Check that the record name is correct (e.g., `postgres`, not `postgres.almckay.io`)
4. Flush your local DNS cache:
   ```bash
   # macOS
   sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder

   # Linux
   sudo systemd-resolve --flush-caches
   ```

### Connection Refused

**Problem**: DNS resolves but connection is refused

**Solutions**:
1. Verify Traefik is running:
   ```bash
   kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik
   ```

2. Check Traefik service has the correct LoadBalancer IP:
   ```bash
   kubectl get svc -n kube-system traefik
   ```

3. Verify IngressRouteTCP exists:
   ```bash
   kubectl get ingressroutetcp -A
   ```

4. Check Traefik logs:
   ```bash
   kubectl logs -n kube-system -l app.kubernetes.io/name=traefik | grep -i error
   ```

### Wrong IP Address

**Problem**: DNS resolves to wrong IP address

**Solutions**:
1. Verify the A record in Cloudflare points to the correct IP
2. Check if Cloudflare proxy is enabled (should be DNS only/gray cloud)
3. Update the DNS record if the Traefik IP has changed

### Cloudflare Proxy Issues

**Problem**: Services not accessible when Cloudflare proxy is enabled

**Solution**: PostgreSQL and Redis require direct TCP connections and cannot work through Cloudflare's HTTP proxy. Make sure the proxy status is set to "DNS only" (gray cloud icon).

## Service Endpoints

Once DNS is configured, services are accessible at:

- **PostgreSQL**: `postgres.almckay.io:5432`
  - Connection string: `postgresql://authentik:<password>@postgres.almckay.io:5432/authentik`

- **Redis**: `redis.almckay.io:6379`
  - Connection string: `redis://:<password>@redis.almckay.io:6379`

- **Authentik**: `https://auth.almckay.io`
  - Web interface accessible via browser

## Security Considerations

1. **Network Access**: Services are only accessible from machines on the Tailscale network
2. **Authentication**: All services require authentication (passwords stored in encrypted secrets)
3. **TLS**: Authentik uses TLS certificates from Let's Encrypt
4. **DNS Only**: Using DNS-only mode (not proxied) ensures direct connections without Cloudflare intermediary

## Next Steps

After DNS configuration:

1. Test connectivity to all services
2. Configure applications to use the DNS names
3. Set up monitoring for DNS resolution and service availability
4. Document connection strings for developers
5. Consider setting up automated DNS updates if Traefik IP changes
