# Troubleshooting Guide

This guide covers common issues and their solutions when working with Kubani.

## Table of Contents

- [Tailscale Issues](#tailscale-issues)
- [SSH and Connectivity](#ssh-and-connectivity)
- [K3s Installation](#k3s-installation)
- [Cluster Joining](#cluster-joining)
- [GPU Support](#gpu-support)
- [GitOps and Flux](#gitops-and-flux)
- [Production Services](#production-services)
- [Resource Management](#resource-management)
- [Ansible Playbooks](#ansible-playbooks)
- [TUI and Monitoring](#tui-and-monitoring)
- [Networking](#networking)
- [Storage](#storage)
- [Debugging Tools](#debugging-tools)

## Tailscale Issues

### Nodes Not Reachable via Tailscale

**Symptoms:**
- `cluster-mgr discover` shows nodes as offline
- Cannot ping Tailscale IP addresses
- SSH connection fails to Tailscale IPs

**Diagnosis:**

```bash
# On each node, check Tailscale status
tailscale status

# Check if Tailscale daemon is running
sudo systemctl status tailscaled

# View Tailscale logs
sudo journalctl -u tailscaled -n 50

# Test connectivity
ping <tailscale-ip>
```

**Solutions:**

1. **Tailscale not running:**
   ```bash
   sudo systemctl start tailscaled
   sudo systemctl enable tailscaled
   ```

2. **Node not authenticated:**
   ```bash
   sudo tailscale up
   # Follow the authentication link
   ```

3. **Tailscale network issues:**
   ```bash
   # Restart Tailscale
   sudo systemctl restart tailscaled

   # Force re-authentication
   sudo tailscale down
   sudo tailscale up
   ```

4. **Firewall blocking Tailscale:**
   ```bash
   # Allow Tailscale through firewall
   sudo ufw allow in on tailscale0
   ```

### Tailscale IP Address Changed

**Symptoms:**
- Nodes were working but now unreachable
- Inventory has old IP addresses

**Solutions:**

1. **Discover new IPs:**
   ```bash
   cluster-mgr discover
   ```

2. **Update inventory:**
   ```bash
   # Remove old node
   cluster-mgr remove-node <hostname> --no-drain

   # Add with new IP
   cluster-mgr add-node <hostname> <new-ip> --role worker
   ```

3. **Or manually edit inventory:**
   ```bash
   vim ansible/inventory/hosts.yml
   # Update ansible_host and tailscale_ip fields
   ```

## SSH and Connectivity

### SSH Connection Refused

**Symptoms:**
- `ansible all -m ping` fails
- `cluster-mgr provision` cannot connect to nodes

**Diagnosis:**

```bash
# Test SSH manually
ssh -v user@<tailscale-ip>

# Check if SSH server is running on target
ssh user@<tailscale-ip> "systemctl status sshd"

# Verify SSH port
ssh user@<tailscale-ip> -p 22
```

**Solutions:**

1. **SSH server not running:**
   ```bash
   # On target node
   sudo systemctl start sshd
   sudo systemctl enable sshd
   ```

2. **SSH key not authorized:**
   ```bash
   # Copy SSH key to target
   ssh-copy-id user@<tailscale-ip>

   # Or manually
   cat ~/.ssh/id_rsa.pub | ssh user@<tailscale-ip> \
     "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
   ```

3. **Wrong username:**
   ```bash
   # Specify correct user in inventory
   vim ansible/inventory/hosts.yml
   # Add: ansible_user: your-username
   ```

4. **Use password authentication temporarily:**
   ```bash
   # Edit ansible.cfg
   vim ansible/ansible.cfg
   # Add:
   # [defaults]
   # ask_pass = True
   ```

### Permission Denied (sudo)

**Symptoms:**
- Ansible tasks fail with "permission denied"
- Cannot execute sudo commands

**Solutions:**

1. **Configure passwordless sudo:**
   ```bash
   # On target node
   echo "$USER ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/$USER
   ```

2. **Or configure Ansible to prompt for password:**
   ```bash
   # Edit ansible.cfg
   vim ansible/ansible.cfg
   # Add:
   # [privilege_escalation]
   # become_ask_pass = True
   ```

3. **Run with sudo password:**
   ```bash
   cluster-mgr provision --extra-vars "ansible_become_pass=your-password"
   ```

## K3s Installation

### K3s Installation Fails

**Symptoms:**
- Provisioning fails during K3s installation
- K3s service won't start

**Diagnosis:**

```bash
# Check K3s service status
sudo systemctl status k3s        # Control plane
sudo systemctl status k3s-agent  # Worker

# View K3s logs
sudo journalctl -u k3s -n 100        # Control plane
sudo journalctl -u k3s-agent -n 100  # Worker

# Check K3s installation script
ls -la /usr/local/bin/k3s
```

**Solutions:**

1. **Port already in use:**
   ```bash
   # Check for port conflicts
   sudo netstat -tulpn | grep -E ':(6443|10250)'

   # Kill conflicting process or change K3s port
   ```

2. **Insufficient disk space:**
   ```bash
   # Check disk space
   df -h

   # Clean up if needed
   sudo apt clean
   sudo docker system prune -a  # If Docker is installed
   ```

3. **Previous installation remnants:**
   ```bash
   # Completely uninstall K3s
   sudo /usr/local/bin/k3s-uninstall.sh        # Control plane
   sudo /usr/local/bin/k3s-agent-uninstall.sh  # Worker

   # Clean up directories
   sudo rm -rf /var/lib/rancher/k3s
   sudo rm -rf /etc/rancher/k3s

   # Re-run provisioning
   cluster-mgr provision
   ```

4. **Network configuration issues:**
   ```bash
   # Check network interfaces
   ip addr show

   # Ensure Tailscale interface exists
   ip addr show tailscale0
   ```

### K3s Service Won't Start

**Symptoms:**
- `systemctl status k3s` shows failed state
- API server not responding

**Diagnosis:**

```bash
# View detailed logs
sudo journalctl -u k3s -xe

# Check configuration
sudo cat /etc/rancher/k3s/config.yaml

# Test K3s binary
sudo /usr/local/bin/k3s server --help
```

**Solutions:**

1. **Configuration error:**
   ```bash
   # Validate configuration
   sudo k3s server --config /etc/rancher/k3s/config.yaml --dry-run

   # Fix configuration and restart
   sudo systemctl restart k3s
   ```

2. **Certificate issues:**
   ```bash
   # Remove old certificates
   sudo rm -rf /var/lib/rancher/k3s/server/tls

   # Restart to regenerate
   sudo systemctl restart k3s
   ```

3. **Database corruption:**
   ```bash
   # Backup and reset database
   sudo systemctl stop k3s
   sudo mv /var/lib/rancher/k3s/server/db /var/lib/rancher/k3s/server/db.backup
   sudo systemctl start k3s
   ```

## Cluster Joining

### Worker Cannot Join Control Plane

**Symptoms:**
- Worker node stays in "NotReady" state
- Worker logs show connection errors

**Diagnosis:**

```bash
# On worker, check logs
sudo journalctl -u k3s-agent -n 100

# Test control plane connectivity
curl -k https://<control-plane-tailscale-ip>:6443

# Check join token
sudo cat /etc/rancher/k3s/config.yaml | grep token
```

**Solutions:**

1. **Control plane not accessible:**
   ```bash
   # On control plane, verify API server is running
   sudo systemctl status k3s
   kubectl get nodes

   # Check firewall
   sudo ufw allow 6443/tcp
   sudo ufw allow 10250/tcp
   ```

2. **Wrong join token:**
   ```bash
   # On control plane, get correct token
   sudo cat /var/lib/rancher/k3s/server/node-token

   # Update worker configuration
   # Re-run provisioning for that worker
   cluster-mgr provision --limit <worker-hostname>
   ```

3. **Certificate validation issues:**
   ```bash
   # On worker, check if using correct server URL
   sudo cat /etc/rancher/k3s/config.yaml

   # Should use Tailscale IP, not localhost
   ```

4. **Network policy blocking:**
   ```bash
   # Temporarily disable network policies
   kubectl delete networkpolicies --all
   ```

### Node Stuck in "NotReady" State

**Symptoms:**
- `kubectl get nodes` shows node as NotReady
- Pods won't schedule on the node

**Diagnosis:**

```bash
# Check node status
kubectl describe node <node-name>

# Check kubelet logs
ssh user@<node-ip> "sudo journalctl -u k3s-agent -n 100"

# Check node conditions
kubectl get node <node-name> -o jsonpath='{.status.conditions}'
```

**Solutions:**

1. **Kubelet not running:**
   ```bash
   # On the node
   sudo systemctl restart k3s-agent
   ```

2. **Network plugin issues:**
   ```bash
   # Check CNI plugins
   ssh user@<node-ip> "ls -la /opt/cni/bin/"

   # Restart networking
   ssh user@<node-ip> "sudo systemctl restart k3s-agent"
   ```

3. **Resource pressure:**
   ```bash
   # Check node resources
   kubectl describe node <node-name> | grep -A 5 "Conditions"

   # Free up resources or increase reservations
   ```

## GPU Support

### GPU Not Detected in Kubernetes

**Symptoms:**
- `kubectl describe node` doesn't show `nvidia.com/gpu` resource
- GPU pods fail to schedule

**Diagnosis:**

```bash
# On GPU node, check if GPU is detected
nvidia-smi

# Check if device plugin is running
kubectl get pods -n kube-system | grep nvidia

# View device plugin logs
kubectl logs -n kube-system -l name=nvidia-device-plugin-ds
```

**Solutions:**

1. **NVIDIA drivers not installed:**
   ```bash
   # On GPU node
   nvidia-smi

   # If command not found, install drivers
   sudo apt update
   sudo apt install -y nvidia-driver-535
   sudo reboot
   ```

2. **Device plugin not deployed:**
   ```bash
   # Re-run GPU provisioning
   cluster-mgr provision --tags gpu --limit <gpu-node>

   # Or manually deploy
   kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml
   ```

3. **Container runtime not configured:**
   ```bash
   # Check containerd configuration
   ssh user@<gpu-node> "sudo cat /etc/containerd/config.toml | grep nvidia"

   # Should have nvidia runtime configured
   # Re-run provisioning if missing
   ```

4. **GPU already in use:**
   ```bash
   # Check GPU processes
   nvidia-smi

   # Kill processes if needed
   sudo kill <pid>
   ```

### GPU Time-Slicing Not Working

**Symptoms:**
- Only one pod can use GPU at a time
- GPU resource shows count of 1

**Solutions:**

```bash
# Check device plugin configuration
kubectl get configmap -n kube-system nvidia-device-plugin-config -o yaml

# Update time-slicing configuration
# Re-run provisioning with GPU tags
cluster-mgr provision --tags gpu --limit <gpu-node>

# Restart device plugin
kubectl delete pod -n kube-system -l name=nvidia-device-plugin-ds
```

## GitOps and Flux

### Flux Not Syncing from Git

**Symptoms:**
- Applications not deploying
- Changes in Git not reflected in cluster

**Diagnosis:**

```bash
# Check Flux status
flux check

# View Flux controllers
kubectl get pods -n flux-system

# Check Git repository source
kubectl get gitrepositories -n flux-system

# View source controller logs
kubectl logs -n flux-system -l app=source-controller

# View kustomize controller logs
kubectl logs -n flux-system -l app=kustomize-controller
```

**Solutions:**

1. **Flux not installed:**
   ```bash
   # Re-run GitOps provisioning
   cluster-mgr provision --tags gitops
   ```

2. **Git repository not accessible:**
   ```bash
   # Check repository configuration
   kubectl describe gitrepository -n flux-system flux-system

   # For private repos, check SSH key
   kubectl get secret -n flux-system flux-system

   # Recreate secret if needed
   flux create secret git flux-system \
     --url=ssh://git@github.com/user/repo \
     --ssh-key-algorithm=rsa \
     --ssh-rsa-bits=4096
   ```

3. **Wrong branch or path:**
   ```bash
   # Check Flux configuration
   kubectl get gitrepository -n flux-system flux-system -o yaml

   # Update if needed
   flux create source git flux-system \
     --url=<repo-url> \
     --branch=main \
     --interval=1m
   ```

4. **Kustomization errors:**
   ```bash
   # Check kustomization status
   kubectl get kustomizations -n flux-system

   # View errors
   kubectl describe kustomization -n flux-system flux-system

   # Fix kustomization.yaml in Git and push
   ```

5. **Force reconciliation:**
   ```bash
   # Force Flux to sync immediately
   flux reconcile source git flux-system
   flux reconcile kustomization flux-system
   ```

### Flux Bootstrap Failed

**Symptoms:**
- `cluster-mgr provision` fails during Flux installation
- Flux controllers not running

**Solutions:**

```bash
# Check if Flux CLI is installed
flux --version

# Manually bootstrap Flux
flux bootstrap github \
  --owner=<github-user> \
  --repository=<repo-name> \
  --branch=main \
  --path=gitops \
  --personal

# Or for GitLab
flux bootstrap gitlab \
  --owner=<gitlab-user> \
  --repository=<repo-name> \
  --branch=main \
  --path=gitops
```

## Production Services

### SOPS Secrets Decryption Failures

**Symptoms:**
- Flux Kustomization shows decryption errors
- Pods fail to start due to missing secrets
- "failed to decrypt" errors in Flux logs

**Diagnosis:**

```bash
# Check if age secret exists in flux-system namespace
kubectl get secret sops-age -n flux-system

# View Flux kustomize-controller logs
kubectl logs -n flux-system -l app=kustomize-controller | grep -i sops

# Check Kustomization status
kubectl get kustomizations -n flux-system
kubectl describe kustomization apps -n flux-system

# Test local decryption
sops -d gitops/apps/postgresql/secret.enc.yaml
```

**Solutions:**

1. **Age secret not created:**
   ```bash
   # Create age secret from age.key file
   kubectl create secret generic sops-age \
     --namespace=flux-system \
     --from-file=age.agekey=age.key

   # Or apply the generated secret
   kubectl apply -f sops-age-secret.yaml
   ```

2. **Wrong age key:**
   ```bash
   # Verify age public key in .sops.yaml matches your age.key
   cat .sops.yaml
   cat age.key | grep "public key:"

   # If mismatch, re-encrypt all secrets with correct key
   find gitops -name "*.enc.yaml" -exec sops updatekeys {} \;
   ```

3. **Kustomization not configured for decryption:**
   ```bash
   # Check Kustomization has decryption enabled
   kubectl get kustomization apps -n flux-system -o yaml | grep -A 5 decryption

   # Should show:
   # decryption:
   #   provider: sops
   #   secretRef:
   #     name: sops-age
   ```

4. **Secrets not encrypted properly:**
   ```bash
   # Re-encrypt a secret
   sops -e -i gitops/apps/postgresql/secret.enc.yaml

   # Verify encryption
   cat gitops/apps/postgresql/secret.enc.yaml | grep "sops:"
   ```

### Certificate Issuance Failures

**Symptoms:**
- Certificate stuck in "Pending" or "Failed" state
- Ingress shows no TLS certificate
- HTTPS access fails with certificate errors

**Diagnosis:**

```bash
# Check cert-manager pods
kubectl get pods -n cert-manager

# Check ClusterIssuer status
kubectl get clusterissuer
kubectl describe clusterissuer letsencrypt-prod

# Check Certificate status
kubectl get certificates -A
kubectl describe certificate authentik-tls -n auth

# Check CertificateRequest
kubectl get certificaterequest -A
kubectl describe certificaterequest -n auth

# View cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager
kubectl logs -n cert-manager -l app=cert-manager-webhook
```

**Solutions:**

1. **Cloudflare API token invalid:**
   ```bash
   # Check if secret exists
   kubectl get secret cloudflare-api-token -n cert-manager

   # Verify token has correct permissions
   # Token needs: Zone:DNS:Edit and Zone:Zone:Read

   # Update secret with new token
   kubectl delete secret cloudflare-api-token -n cert-manager
   # Re-run create_encrypted_secrets.py or manually create
   ```

2. **DNS propagation timeout:**
   ```bash
   # Check challenge status
   kubectl get challenges -A
   kubectl describe challenge -n auth

   # Verify DNS record was created in Cloudflare
   # Visit: https://dash.cloudflare.com/ → DNS

   # Wait for DNS propagation (can take 1-5 minutes)
   # cert-manager will retry automatically
   ```

3. **Let's Encrypt rate limit:**
   ```bash
   # Check for rate limit errors
   kubectl describe certificate authentik-tls -n auth | grep -i "rate limit"

   # Use staging issuer for testing
   kubectl patch certificate authentik-tls -n auth \
     --type merge -p '{"spec":{"issuerRef":{"name":"letsencrypt-staging"}}}'

   # Wait 1 hour for rate limit to reset, then switch back to prod
   ```

4. **cert-manager not running:**
   ```bash
   # Check cert-manager deployment
   kubectl get deployment -n cert-manager

   # Restart cert-manager
   kubectl rollout restart deployment -n cert-manager

   # Re-deploy if needed
   flux reconcile kustomization infrastructure
   ```

### PostgreSQL Connection Failures

**Symptoms:**
- Cannot connect to postgres.almckay.io
- Connection timeout or refused
- Authentication failures

**Diagnosis:**

```bash
# Test DNS resolution
nslookup postgres.almckay.io

# Test TCP connectivity
nc -zv postgres.almckay.io 5432

# Check PostgreSQL pod status
kubectl get pods -n database

# Check PostgreSQL service
kubectl get svc -n database

# Check IngressRouteTCP
kubectl get ingressroutetcp -n database
kubectl describe ingressroutetcp postgresql-tcp -n database

# View PostgreSQL logs
kubectl logs -n database -l app.kubernetes.io/name=postgresql
```

**Solutions:**

1. **DNS not configured:**
   ```bash
   # Get Traefik IP
   ./scripts/get_traefik_ip.sh

   # Create DNS A record in Cloudflare
   # postgres.almckay.io → <traefik-tailscale-ip>

   # Or use automated script
   uv run python scripts/configure_dns.py
   ```

2. **Traefik not routing TCP:**
   ```bash
   # Check Traefik configuration
   kubectl get svc -n kube-system traefik

   # Verify TCP ports are exposed
   kubectl get svc traefik -n kube-system -o yaml | grep -A 5 "5432"

   # Check IngressRouteTCP exists
   kubectl get ingressroutetcp -A

   # View Traefik logs
   kubectl logs -n kube-system -l app.kubernetes.io/name=traefik
   ```

3. **PostgreSQL not ready:**
   ```bash
   # Check pod status
   kubectl get pods -n database

   # Wait for pod to be ready
   kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql -n database --timeout=300s

   # Check for errors
   kubectl describe pod -n database -l app.kubernetes.io/name=postgresql
   ```

4. **Wrong credentials:**
   ```bash
   # Check if secret exists
   kubectl get secret postgresql-credentials -n database

   # View secret (base64 encoded)
   kubectl get secret postgresql-credentials -n database -o yaml

   # Decode password
   kubectl get secret postgresql-credentials -n database -o jsonpath='{.data.password}' | base64 -d

   # Update secret if needed
   # Re-run create_encrypted_secrets.py
   ```

5. **Firewall blocking connection:**
   ```bash
   # Ensure Tailscale allows traffic
   tailscale status

   # Test from within cluster
   kubectl run psql-test --rm -it --image=postgres:15 -- \
     psql -h postgresql.database.svc.cluster.local -U authentik -d authentik
   ```

### Redis Connection Failures

**Symptoms:**
- Cannot connect to redis.almckay.io
- Connection timeout or refused
- Authentication failures

**Diagnosis:**

```bash
# Test DNS resolution
nslookup redis.almckay.io

# Test TCP connectivity
nc -zv redis.almckay.io 6379

# Check Redis pod status
kubectl get pods -n cache

# Check Redis service
kubectl get svc -n cache

# Check IngressRouteTCP
kubectl get ingressroutetcp -n cache
kubectl describe ingressroutetcp redis-tcp -n cache

# View Redis logs
kubectl logs -n cache -l app.kubernetes.io/name=redis
```

**Solutions:**

1. **DNS not configured:**
   ```bash
   # Get Traefik IP
   ./scripts/get_traefik_ip.sh

   # Create DNS A record in Cloudflare
   # redis.almckay.io → <traefik-tailscale-ip>

   # Or use automated script
   uv run python scripts/configure_dns.py
   ```

2. **Traefik not routing TCP:**
   ```bash
   # Check Traefik configuration
   kubectl get svc -n kube-system traefik

   # Verify TCP ports are exposed
   kubectl get svc traefik -n kube-system -o yaml | grep -A 5 "6379"

   # Check IngressRouteTCP exists
   kubectl get ingressroutetcp -A

   # View Traefik logs
   kubectl logs -n kube-system -l app.kubernetes.io/name=traefik
   ```

3. **Redis not ready:**
   ```bash
   # Check pod status
   kubectl get pods -n cache

   # Wait for pod to be ready
   kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=redis -n cache --timeout=300s

   # Check for errors
   kubectl describe pod -n cache -l app.kubernetes.io/name=redis
   ```

4. **Wrong password:**
   ```bash
   # Check if secret exists
   kubectl get secret redis-credentials -n cache

   # Decode password
   kubectl get secret redis-credentials -n cache -o jsonpath='{.data.redis-password}' | base64 -d

   # Test with correct password
   redis-cli -h redis.almckay.io -p 6379 -a <password> PING
   ```

5. **Test from within cluster:**
   ```bash
   # Run redis-cli in cluster
   kubectl run redis-test --rm -it --image=redis:7 -- \
     redis-cli -h redis-master.cache.svc.cluster.local -p 6379 -a <password> PING
   ```

### Authentik HTTPS Access Failures

**Symptoms:**
- Cannot access https://auth.almckay.io
- Certificate errors in browser
- Connection timeout or refused

**Diagnosis:**

```bash
# Test DNS resolution
nslookup auth.almckay.io

# Test HTTPS connectivity
curl -v https://auth.almckay.io

# Check Authentik pod status
kubectl get pods -n auth

# Check Ingress
kubectl get ingress -n auth
kubectl describe ingress authentik -n auth

# Check Certificate
kubectl get certificate -n auth
kubectl describe certificate authentik-tls -n auth

# View Authentik logs
kubectl logs -n auth -l app.kubernetes.io/name=authentik
```

**Solutions:**

1. **DNS not configured:**
   ```bash
   # Get Traefik IP
   ./scripts/get_traefik_ip.sh

   # Create DNS A record in Cloudflare
   # auth.almckay.io → <traefik-tailscale-ip>

   # Or use automated script
   uv run python scripts/configure_dns.py
   ```

2. **Certificate not issued:**
   ```bash
   # Check certificate status
   kubectl get certificate authentik-tls -n auth

   # If not ready, check cert-manager
   kubectl logs -n cert-manager -l app=cert-manager

   # Force certificate renewal
   kubectl delete certificaterequest -n auth --all
   kubectl delete certificate authentik-tls -n auth
   # Flux will recreate it
   ```

3. **Ingress not configured:**
   ```bash
   # Check Ingress exists
   kubectl get ingress -n auth

   # Verify Ingress has TLS configured
   kubectl get ingress authentik -n auth -o yaml | grep -A 5 tls

   # Check Traefik is routing
   kubectl logs -n kube-system -l app.kubernetes.io/name=traefik | grep auth.almckay.io
   ```

4. **Authentik not ready:**
   ```bash
   # Check pod status
   kubectl get pods -n auth

   # Wait for pods to be ready
   kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=authentik -n auth --timeout=300s

   # Check for errors
   kubectl describe pod -n auth -l app.kubernetes.io/name=authentik
   ```

5. **Database connection issues:**
   ```bash
   # Authentik requires PostgreSQL
   # Check PostgreSQL is running
   kubectl get pods -n database

   # Check Authentik can connect to PostgreSQL
   kubectl logs -n auth -l app.kubernetes.io/name=authentik | grep -i postgres

   # Verify database credentials
   kubectl get secret authentik-credentials -n auth
   ```

### Service Validation Failures

**Symptoms:**
- Validation scripts report failures
- Services appear running but not accessible

**Solutions:**

```bash
# Run comprehensive validation
./scripts/verify_services.sh

# Run individual validations
./scripts/validate_pods.sh
./scripts/validate_postgresql.sh
./scripts/validate_redis.sh
./scripts/validate_authentik.sh
./scripts/validate_certificates.sh

# Check Flux synchronization
flux get kustomizations
flux get helmreleases -A

# Force reconciliation
flux reconcile kustomization infrastructure
flux reconcile kustomization apps

# Check for pending changes in Git
git status
git pull
```

### Traefik LoadBalancer IP Not Assigned

**Symptoms:**
- `kubectl get svc traefik` shows `<pending>` for EXTERNAL-IP
- Cannot determine IP for DNS configuration

**Solutions:**

```bash
# Check Traefik service
kubectl get svc -n kube-system traefik

# K3s uses servicelb by default
# Check servicelb pods
kubectl get pods -n kube-system | grep svclb

# If using Tailscale, IP should be assigned automatically
# Check Tailscale status on nodes
tailscale status

# Manually patch service if needed
kubectl patch svc traefik -n kube-system -p '{"spec":{"externalIPs":["<tailscale-ip>"]}}'

# Or use NodePort as fallback
kubectl patch svc traefik -n kube-system -p '{"spec":{"type":"NodePort"}}'
```

### Flux Not Applying Encrypted Secrets

**Symptoms:**
- Secrets exist in Git but not in cluster
- Flux shows "reconciliation succeeded" but secrets missing

**Diagnosis:**

```bash
# Check Flux Kustomization status
kubectl get kustomizations -n flux-system
kubectl describe kustomization apps -n flux-system

# Check for decryption errors
kubectl logs -n flux-system -l app=kustomize-controller | grep -i error

# Verify age secret exists
kubectl get secret sops-age -n flux-system

# Test local decryption
sops -d gitops/apps/postgresql/secret.enc.yaml
```

**Solutions:**

```bash
# Ensure Kustomization has decryption enabled
kubectl get kustomization apps -n flux-system -o yaml

# Should have:
# spec:
#   decryption:
#     provider: sops
#     secretRef:
#       name: sops-age

# If missing, update Flux Kustomization
# Edit gitops/flux-system/apps-kustomization.yaml
# Add decryption section and commit

# Force reconciliation
flux reconcile kustomization apps --with-source
```

## Resource Management

### High CPU/Memory Usage on Workstation Nodes

**Symptoms:**
- Workstation becomes slow
- Kubernetes consuming too many resources
- Local applications laggy

**Diagnosis:**

```bash
# Check resource usage
kubectl top nodes
kubectl top pods --all-namespaces

# Check resource reservations
kubectl describe node <node-name> | grep -A 10 "Allocated resources"

# Check running pods on node
kubectl get pods --all-namespaces --field-selector spec.nodeName=<node-name>
```

**Solutions:**

1. **Increase resource reservations:**
   ```bash
   # Edit inventory
   vim ansible/inventory/hosts.yml

   # Increase reserved_cpu and reserved_memory
   # For example:
   # reserved_cpu: "4"      # Was 2
   # reserved_memory: "8Gi" # Was 4Gi

   # Re-run provisioning
   cluster-mgr provision --tags k3s_worker --limit <node-name>
   ```

2. **Add taints to prevent scheduling:**
   ```bash
   # Taint node to prevent new pods
   kubectl taint nodes <node-name> workstation=true:NoSchedule

   # Or update inventory and re-provision
   cluster-mgr add-node <node-name> <ip> \
     --taints "workstation=true:NoSchedule"
   ```

3. **Drain and cordon node:**
   ```bash
   # Move pods to other nodes
   kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

   # Prevent new pods
   kubectl cordon <node-name>

   # When ready to use again
   kubectl uncordon <node-name>
   ```

4. **Limit pod resources:**
   ```bash
   # Create resource quotas
   kubectl create quota workstation-quota \
     --hard=cpu=2,memory=4Gi \
     --namespace=default
   ```

### Pods Evicted Due to Resource Pressure

**Symptoms:**
- Pods show "Evicted" status
- Node conditions show memory/disk pressure

**Solutions:**

```bash
# Check node conditions
kubectl describe node <node-name> | grep -A 5 "Conditions"

# Free up disk space
ssh user@<node-ip> "sudo docker system prune -a"
ssh user@<node-ip> "sudo journalctl --vacuum-time=3d"

# Increase resource reservations
# See "High CPU/Memory Usage" above

# Delete evicted pods
kubectl get pods --all-namespaces | grep Evicted | \
  awk '{print $2 " -n " $1}' | xargs -L1 kubectl delete pod
```

## Ansible Playbooks

### Playbook Fails Midway

**Symptoms:**
- Ansible playbook stops with error
- Some nodes configured, others not

**Diagnosis:**

```bash
# Run in check mode to see what would change
cluster-mgr provision --check

# Increase verbosity
cluster-mgr provision -vvv

# Check Ansible logs
ls -la ansible/artifacts/
cat ansible/artifacts/*/stdout
```

**Solutions:**

1. **Syntax error in inventory:**
   ```bash
   # Validate inventory
   ansible-inventory -i ansible/inventory/hosts.yml --list

   # Check for YAML syntax errors
   yamllint ansible/inventory/hosts.yml
   ```

2. **Task-specific failure:**
   ```bash
   # Run only specific tags to isolate issue
   cluster-mgr provision --tags prerequisites
   cluster-mgr provision --tags k3s

   # Skip problematic tasks temporarily
   cluster-mgr provision --skip-tags gpu,monitoring
   ```

3. **Network timeout:**
   ```bash
   # Increase timeout in ansible.cfg
   vim ansible/ansible.cfg
   # Add:
   # [defaults]
   # timeout = 60
   ```

4. **Idempotency issues:**
   ```bash
   # Clean up and retry
   # For K3s issues, uninstall first
   ansible all -i ansible/inventory/hosts.yml \
     -m shell -a "/usr/local/bin/k3s-uninstall.sh || /usr/local/bin/k3s-agent-uninstall.sh || true" \
     --become

   # Then re-run provisioning
   cluster-mgr provision
   ```

### Playbook Hangs or Times Out

**Symptoms:**
- Playbook execution stops responding
- Tasks take very long time

**Solutions:**

```bash
# Interrupt with Ctrl+C

# Check if nodes are responsive
ansible all -i ansible/inventory/hosts.yml -m ping

# Run with increased timeout
cluster-mgr provision --extra-vars "ansible_timeout=120"

# Run tasks in serial instead of parallel
# Edit playbook to add: serial: 1
```

## TUI and Monitoring

### TUI Cannot Connect to Cluster

**Symptoms:**
- `cluster-tui` shows connection error
- "Failed to load kubeconfig" message

**Diagnosis:**

```bash
# Check if kubeconfig exists
ls -la ~/.kube/config

# Test kubectl connection
kubectl get nodes

# Check kubeconfig content
kubectl config view
```

**Solutions:**

1. **Kubeconfig not found:**
   ```bash
   # Copy kubeconfig from control plane
   scp user@<control-plane-ip>:/etc/rancher/k3s/k3s.yaml ~/.kube/config

   # Update server URL to use Tailscale IP
   sed -i 's/127.0.0.1/<control-plane-tailscale-ip>/' ~/.kube/config
   ```

2. **Wrong context:**
   ```bash
   # List contexts
   kubectl config get-contexts

   # Switch context
   kubectl config use-context <context-name>
   ```

3. **Certificate issues:**
   ```bash
   # Skip TLS verification (temporary)
   kubectl get nodes --insecure-skip-tls-verify

   # Or regenerate certificates on control plane
   ```

4. **API server not accessible:**
   ```bash
   # Test API server
   curl -k https://<control-plane-tailscale-ip>:6443

   # Check if control plane is running
   ssh user@<control-plane-ip> "sudo systemctl status k3s"
   ```

### TUI Shows Stale Data

**Symptoms:**
- TUI not updating
- Node/pod information outdated

**Solutions:**

```bash
# Press 'r' to force refresh

# Check if API server is responsive
kubectl get nodes

# Restart TUI
# Exit with 'q' and restart: cluster-tui

# Check for network issues
ping <control-plane-tailscale-ip>
```

## Networking

### Pods Cannot Communicate

**Symptoms:**
- Pod-to-pod communication fails
- Services not reachable

**Diagnosis:**

```bash
# Test pod-to-pod connectivity
kubectl run test-pod --image=busybox --rm -it -- sh
# Inside pod:
# ping <other-pod-ip>
# wget <service-name>

# Check CNI plugin
kubectl get pods -n kube-system | grep flannel

# Check network policies
kubectl get networkpolicies --all-namespaces
```

**Solutions:**

1. **CNI plugin issues:**
   ```bash
   # Restart CNI pods
   kubectl delete pod -n kube-system -l app=flannel

   # Check CNI configuration
   ssh user@<node-ip> "ls -la /etc/cni/net.d/"
   ```

2. **Network policies blocking:**
   ```bash
   # List network policies
   kubectl get networkpolicies --all-namespaces

   # Delete restrictive policies
   kubectl delete networkpolicy <policy-name> -n <namespace>
   ```

3. **Firewall rules:**
   ```bash
   # On each node, allow pod network
   sudo ufw allow from 10.42.0.0/16
   sudo ufw allow from 10.43.0.0/16
   ```

### DNS Resolution Fails

**Symptoms:**
- Pods cannot resolve service names
- `nslookup` fails inside pods

**Diagnosis:**

```bash
# Check CoreDNS
kubectl get pods -n kube-system | grep coredns

# Test DNS from pod
kubectl run test-dns --image=busybox --rm -it -- nslookup kubernetes.default

# Check CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns
```

**Solutions:**

```bash
# Restart CoreDNS
kubectl delete pod -n kube-system -l k8s-app=kube-dns

# Check CoreDNS configuration
kubectl get configmap -n kube-system coredns -o yaml

# Verify DNS service
kubectl get svc -n kube-system kube-dns
```

## Storage

### Persistent Volumes Not Binding

**Symptoms:**
- PVC stuck in "Pending" state
- Pods cannot start due to volume issues

**Diagnosis:**

```bash
# Check PVC status
kubectl get pvc --all-namespaces

# Describe PVC
kubectl describe pvc <pvc-name>

# Check storage classes
kubectl get storageclass

# Check PV
kubectl get pv
```

**Solutions:**

```bash
# Check if local-path provisioner is running
kubectl get pods -n kube-system | grep local-path

# Restart provisioner
kubectl delete pod -n kube-system -l app=local-path-provisioner

# Check node has available storage
ssh user@<node-ip> "df -h /var/lib/rancher/k3s/storage"

# Manually create PV if needed
# See K3s documentation for PV creation
```

## Debugging Tools

### Useful Commands

```bash
# Check cluster health
kubectl get componentstatuses
kubectl get nodes
kubectl get pods --all-namespaces

# View events
kubectl get events --all-namespaces --sort-by='.lastTimestamp'

# Check resource usage
kubectl top nodes
kubectl top pods --all-namespaces

# View logs
kubectl logs <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous  # Previous container

# Describe resources
kubectl describe node <node-name>
kubectl describe pod <pod-name> -n <namespace>

# Execute commands in pods
kubectl exec -it <pod-name> -n <namespace> -- sh

# Port forwarding
kubectl port-forward <pod-name> 8080:80 -n <namespace>

# Check API server
kubectl cluster-info
kubectl cluster-info dump

# Ansible debugging
ansible all -i ansible/inventory/hosts.yml -m ping
ansible all -i ansible/inventory/hosts.yml -m setup
ansible-inventory -i ansible/inventory/hosts.yml --list

# Tailscale debugging
tailscale status
tailscale ping <hostname>
tailscale netcheck
```

### Log Locations

```bash
# K3s logs
sudo journalctl -u k3s -f              # Control plane
sudo journalctl -u k3s-agent -f        # Worker

# Tailscale logs
sudo journalctl -u tailscaled -f

# Ansible logs
ansible/artifacts/*/stdout

# Kubernetes logs
/var/log/pods/
/var/log/containers/

# System logs
/var/log/syslog
/var/log/messages
```

## Getting More Help

If you're still stuck:

1. **Gather information:**
   - Exact error messages
   - Relevant logs
   - Configuration files (sanitized)
   - Steps to reproduce

2. **Check documentation:**
   - [README.md](../README.md)
   - [Design Document](../.kiro/specs/tailscale-k8s-cluster/design.md)
   - [K3s Documentation](https://docs.k3s.io/)
   - [Tailscale Documentation](https://tailscale.com/kb/)

3. **Search for similar issues:**
   - GitHub issues
   - Stack Overflow
   - K3s discussions

4. **Open an issue:**
   - Provide all gathered information
   - Include steps to reproduce
   - Mention what you've already tried

## Prevention Tips

- **Regular backups:** Backup `/var/lib/rancher/k3s/server/db/` on control plane
- **Monitor resources:** Use TUI or Prometheus to watch resource usage
- **Test changes:** Use `--check` mode before applying changes
- **Version control:** Keep inventory and configurations in Git
- **Documentation:** Document custom configurations and changes
- **Updates:** Keep K3s, Tailscale, and system packages updated
- **Validation:** Run `cluster-mgr status` regularly to catch issues early
