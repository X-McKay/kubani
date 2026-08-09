# Traefik TCP Routing Configuration

This directory contains the Traefik configuration for TCP routing to enable DNS-based access to non-HTTP services.

## Components

- **traefik-config.yaml**: HelmChartConfig that extends K3s's built-in Traefik with additional TCP entry points

## TCP Entry Points

The configuration adds four TCP entry points to Traefik:

- **postgresql**: Port 5432 for PostgreSQL database access
- **redis**: Port 6379 for Redis cache access
- **temporal**: Port 7233 for the Temporal frontend gRPC API
- **falkordb**: Port 6380 for FalkorDB RESP access

FalkorDB speaks RESP and listens on 6379 inside the cluster, but the external
entry point is 6380 because the `redis` entry point above already owns 6379 on
the LoadBalancer.

## How It Works

1. K3s includes Traefik as the default ingress controller
2. This HelmChartConfig extends the default Traefik deployment
3. Additional ports are exposed on the Traefik LoadBalancer service
4. IngressRouteTCP resources (created with each service) route traffic to backend services

## DNS Configuration

After deployment, configure DNS records in Cloudflare to point to the Traefik LoadBalancer IP:

```bash
# Get the Traefik LoadBalancer IP (on Tailscale interface)
kubectl get svc -n kube-system traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Create A records in Cloudflare:
# postgres.almckay.io → <traefik-lb-ip>
# redis.almckay.io → <traefik-lb-ip>
# auth.almckay.io → <traefik-lb-ip>
```

## Verification

### Check Traefik Service

```bash
# Verify the service has the additional ports
kubectl get svc -n kube-system traefik -o yaml

# Look for ports 5432, 6379, 6380, and 7233 in the output
```

### Check Traefik Configuration

```bash
# View Traefik logs to confirm entry points are configured
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik | grep entrypoint
```

### Test Connectivity

Once services are deployed with IngressRouteTCP resources:

```bash
# Test PostgreSQL port
nc -zv postgres.almckay.io 5432

# Test Redis port
nc -zv redis.almckay.io 6379

# Test FalkorDB port
nc -zv falkordb.almckay.io 6380
```

## IngressRouteTCP Example

Services will use IngressRouteTCP resources to route traffic:

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRouteTCP
metadata:
  name: postgresql-tcp
  namespace: database
spec:
  entryPoints:
    - postgresql
  routes:
    - match: HostSNI(`*`)
      services:
        - name: postgresql
          port: 5432
```

## Security

- Services are only accessible from the Tailscale network
- Each service requires authentication (database password, Redis password,
  FalkorDB `requirepass`)
- Tailscale provides encrypted mesh networking (WireGuard)
- Additional TLS can be configured for database connections if needed

## Troubleshooting

### Ports Not Exposed

If the ports aren't showing up on the Traefik service:

```bash
# Check if the HelmChartConfig is applied
kubectl get helmchartconfig -n kube-system traefik -o yaml

# Restart Traefik to pick up changes
kubectl rollout restart deployment -n kube-system traefik
```

### Connection Refused

If connections are refused:

1. Verify the backend service exists and is running
2. Check IngressRouteTCP resource is created
3. Verify DNS resolves to the correct IP
4. Check firewall rules allow traffic on the ports
