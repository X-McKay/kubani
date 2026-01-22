# Flannel Routes Lost After Tailscale Upgrade

## Problem Summary

After upgrading Tailscale on a K3s worker node, services became inaccessible. Pods on the upgraded node could not communicate with pods on other nodes, causing DNS resolution failures and application crash loops.

## Symptoms

- Web services (e.g., Authentik) returning connection errors or timeouts
- Application pods in crash loop with DNS resolution failures:
  ```
  PostgreSQL connection failed, retrying... ([Errno -3] Temporary failure in name resolution)
  ```
- `tailscale status` showing health warnings:
  ```
  # Health check:
  #     - Tailscale hasn't received a network map from the coordination server in 2m8s.
  #     - Tailscale can't reach the configured DNS servers.
  ```

## Investigation Steps

### 1. Check Cluster Node Status

```bash
kubectl get nodes -o wide
```

All nodes showed as `Ready`, so the issue wasn't node connectivity to the API server.

### 2. Check Pod Status

```bash
kubectl get pods -n <namespace>
```

Found application server pod in crash loop with 121+ restarts, while worker pod on same node was running (likely had cached connections).

### 3. Check Pod Logs

```bash
kubectl logs -n <namespace> <pod-name>
```

Revealed DNS resolution failures - pod couldn't resolve internal service names like `postgresql.database.svc.cluster.local`.

### 4. Test DNS from Within Cluster

```bash
kubectl run dns-test --rm -it --restart=Never --image=busybox:1.28 \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"<node-name>"}}}' \
  -- nslookup postgresql.database.svc.cluster.local
```

Result: DNS lookup timed out, confirming pods on the affected node couldn't reach CoreDNS.

### 5. Test Pod-to-Pod Connectivity

```bash
kubectl run dns-debug --rm -i --restart=Never --image=nicolaka/netshoot \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"<node-name>"}}}' \
  -- sh -c 'ping -c 2 <coredns-pod-ip>'
```

Result: 100% packet loss to CoreDNS pod on another node.

### 6. Check Routing Table

```bash
ip route show | grep 10.42
```

**Key Finding**: Only the local pod network route existed:
```
10.42.1.0/24 dev cni0 proto kernel scope link src 10.42.1.1
```

Missing routes to other nodes' pod networks:
- `10.42.0.0/24` (control plane)
- `10.42.2.0/24` (other worker)

### 7. Verify Expected Routes

```bash
kubectl get nodes -o custom-columns='NAME:.metadata.name,PODCIDR:.spec.podCIDR,INTERNAL-IP:.status.addresses[?(@.type=="InternalIP")].address'
```

Confirmed each node has a pod CIDR assigned and should have routes to reach other nodes' pod networks.

## Root Cause

The Tailscale upgrade caused a network interface change event. This triggered Tailscale to rebind its connections and update routing tables. During this process, the Flannel-managed routes for cross-node pod communication were cleared and not automatically restored by the K3s agent.

From Tailscale logs:
```
LinkChange: major, rebinding. New state: interfaces.State{...}
```

Flannel uses the `host-gw` backend (or VXLAN) to create routes between nodes. When the network state changed, these routes were lost.

## Solution

Restart the K3s agent to have Flannel recreate the routes:

```bash
# On worker nodes
sudo systemctl restart k3s-agent

# On control plane nodes
sudo systemctl restart k3s
```

After restart, verify routes are restored:
```bash
ip route show | grep 10.42
```

Expected output should show routes to all pod networks:
```
10.42.0.0/24 via 10.42.0.0 dev flannel.1 onlink
10.42.1.0/24 dev cni0 proto kernel scope link src 10.42.1.1
10.42.2.0/24 via 10.42.2.0 dev flannel.1 onlink
```

## Prevention

### Option 1: Manual Restart After Tailscale Upgrade

After upgrading Tailscale, always restart the K3s service:

```bash
sudo systemctl restart k3s-agent  # or k3s for control plane
```

### Option 2: Systemd Dependency (Automated)

Create a systemd drop-in to restart K3s when Tailscale restarts:

```bash
sudo mkdir -p /etc/systemd/system/k3s-agent.service.d/
sudo tee /etc/systemd/system/k3s-agent.service.d/tailscale.conf << 'EOF'
[Unit]
BindsTo=tailscaled.service
After=tailscaled.service
EOF
sudo systemctl daemon-reload
```

Note: This will cause K3s to restart whenever Tailscale restarts, which may cause brief pod disruptions.

### Option 3: Post-Upgrade Script

Create a script to run after Tailscale upgrades:

```bash
#!/bin/bash
# /usr/local/bin/post-tailscale-upgrade.sh

echo "Waiting for Tailscale to stabilize..."
sleep 10

echo "Restarting K3s agent to restore Flannel routes..."
if systemctl is-active --quiet k3s-agent; then
    sudo systemctl restart k3s-agent
elif systemctl is-active --quiet k3s; then
    sudo systemctl restart k3s
fi

echo "Verifying routes..."
ip route show | grep 10.42
```

## Verification

After applying the fix, verify everything is working:

```bash
# 1. Check routes exist
ip route show | grep 10.42

# 2. Test DNS resolution from affected node
kubectl run dns-test --rm -it --restart=Never --image=busybox:1.28 \
  --overrides='{"spec":{"nodeSelector":{"kubernetes.io/hostname":"<node-name>"}}}' \
  -- nslookup kubernetes.default.svc.cluster.local

# 3. Check pods are recovering
kubectl get pods -A | grep -v Running

# 4. Test service accessibility
curl -s -o /dev/null -w "%{http_code}" https://<your-service-url>/
```

## Related Issues

- Flannel routes can also be lost after:
  - Node reboots (though K3s usually handles this)
  - Network interface changes (e.g., switching between WiFi and Ethernet)
  - VPN reconnections
  - Kernel updates that affect networking

## References

- [K3s Networking Documentation](https://docs.k3s.io/networking)
- [Flannel Backend Options](https://github.com/flannel-io/flannel/blob/master/Documentation/backends.md)
- [Tailscale Changelog](https://tailscale.com/changelog)
