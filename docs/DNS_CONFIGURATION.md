# DNS Configuration for Production Services

This guide explains how to configure DNS records in Cloudflare for PostgreSQL, Redis, and Authentik services.

## Overview

The production services are exposed via Traefik's LoadBalancer service on the Tailscale network. To access these services using friendly DNS names (e.g., `postgres.almckay.io`), you need to create A records in Cloudflare pointing to the Traefik LoadBalancer IP.

## Prerequisites

- Access to Cloudflare dashboard for `almckay.io` domain
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

## Manual Configuration (Cloudflare Dashboard)

### Step 1: Log in to Cloudflare

1. Go to https://dash.cloudflare.com/
2. Log in with your credentials
3. Select the `almckay.io` domain

### Step 2: Navigate to DNS Settings

1. Click on **DNS** in the left sidebar
2. Click on **Records** tab

### Step 3: Add DNS Records

For each service (postgres, redis, auth):

1. Click **Add record** button
2. Fill in the details:
   - **Type**: A
   - **Name**: `postgres` (or `redis`, `auth`)
   - **IPv4 address**: `100.71.65.62`
   - **Proxy status**: Click the cloud icon to make it gray (DNS only)
   - **TTL**: Auto
3. Click **Save**

### Step 4: Verify DNS Records

After creating the records, they should appear in your DNS records list:

```
postgres.almckay.io  A  100.71.65.62  Auto  DNS only
redis.almckay.io     A  100.71.65.62  Auto  DNS only
auth.almckay.io      A  100.71.65.62  Auto  DNS only
```

## Automated Configuration (Cloudflare API)

If you prefer to automate DNS record creation, you can use the Cloudflare API.

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

### Step 3: Run DNS Configuration Script

```bash
# Using the script with automatic token retrieval
./scripts/setup_dns_records.sh

# Or use the Python script for API-based configuration
uv run python scripts/configure_dns.py --services postgres redis auth
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
