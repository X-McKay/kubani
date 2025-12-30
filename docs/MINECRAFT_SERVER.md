# Minecraft Bedrock Server

This document describes the family Minecraft Bedrock server running on the Kubani cluster.

## Overview

The server runs Minecraft Bedrock Edition, which supports cross-platform play across:
- Windows 10/11
- Xbox One / Series X|S
- PlayStation 4/5
- Nintendo Switch
- iOS and Android devices

External access is provided through [playit.gg](https://playit.gg), a tunneling service that:
- Hides the cluster's real IP address
- Provides DDoS protection via their Anycast network
- Requires no port forwarding or firewall changes
- Works with Bedrock's UDP protocol

## Architecture

```
Players (any device)
       │
       ▼
playit.gg Anycast Network
       │
       ▼ (encrypted tunnel)
┌──────────────────────────────────────┐
│ Kubernetes Pod                       │
│ ┌─────────────┐  ┌─────────────────┐ │
│ │ playit      │◄─│ minecraft       │ │
│ │ agent       │  │ bedrock server  │ │
│ └─────────────┘  └─────────────────┘ │
└──────────────────────────────────────┘
       │
       ▼
    NAS Storage (world data)
```

## Security

### Network Isolation

The server is isolated from the rest of the cluster via NetworkPolicy:
- **No inbound** traffic from other cluster services
- **Outbound** only to external IPs (playit.gg tunnel + Minecraft downloads)
- **DNS** resolution to kube-dns only
- Cluster pod network (10.42.0.0/16) is blocked

### Whitelist

The server runs in whitelist-only mode. Players must be added to the allowlist before they can connect.

### playit.gg Security Notes

- playit.gg is a legitimate tunneling service but has been used by threat actors for C2 servers
- Servers on playit.gg are discoverable via port scanning
- The whitelist mitigates unauthorized access even if the server is discovered
- The server's origin IP remains hidden from players

## Server Configuration

| Setting | Value |
|---------|-------|
| Game Mode | Survival |
| Difficulty | Normal |
| Max Players | 10 |
| View Distance | 10 chunks |
| Whitelist | Enabled |
| Online Mode | Enabled (Xbox Live authentication) |

Configuration is managed via ConfigMap at `gitops/apps/minecraft/configmap.yaml`.

## Managing Players

### Adding Players to Whitelist

Players are identified by their Xbox/Microsoft gamertag. To add a player:

#### Method 1: Server Console

```bash
# Connect to the server pod
KUBECONFIG=/home/al/.kube/config kubectl exec -it deploy/minecraft-bedrock -n minecraft -c bedrock -- /bin/bash

# Use the allowlist command (inside the container)
# Note: You'll need to find their XUID (Xbox User ID)
```

#### Method 2: Edit allowlist.json

```bash
# View current allowlist
KUBECONFIG=/home/al/.kube/config kubectl exec deploy/minecraft-bedrock -n minecraft -c bedrock -- cat /data/allowlist.json

# The format is:
# [
#   {
#     "ignoresPlayerLimit": false,
#     "name": "PlayerGamertag",
#     "xuid": "1234567890123456"
#   }
# ]
```

#### Finding a Player's XUID

1. Have the player try to connect to the server
2. Check the server logs for their connection attempt:
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl logs deploy/minecraft-bedrock -n minecraft -c bedrock | grep -i "player"
   ```
3. The logs will show their gamertag and XUID

Alternatively, use an online XUID lookup tool (search "Xbox XUID lookup").

### Adding Operators (Admin Players)

Operators can use admin commands. Add them to the ops list in the ConfigMap or via:

```bash
KUBECONFIG=/home/al/.kube/config kubectl exec deploy/minecraft-bedrock -n minecraft -c bedrock -- cat /data/permissions.json
```

## Connecting to the Server

1. Open Minecraft Bedrock Edition
2. Go to **Play** > **Servers** > **Add Server**
3. Enter the playit.gg address provided (format: `region.playit.gg:port`)
4. The player must be on the whitelist to connect

## Operations

### View Server Logs

```bash
KUBECONFIG=/home/al/.kube/config kubectl logs deploy/minecraft-bedrock -n minecraft -c bedrock --tail=50
```

### Check Server Status

```bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n minecraft
```

### Restart Server

```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deploy/minecraft-bedrock -n minecraft
```

### Backup World Data

World data is stored on NAS via PVC. The NAS should have its own backup strategy.

Manual backup:
```bash
# Copy world data from pod
KUBECONFIG=/home/al/.kube/config kubectl cp minecraft/$(kubectl get pod -n minecraft -l app.kubernetes.io/name=minecraft-bedrock -o jsonpath='{.items[0].metadata.name}'):/data/worlds ./minecraft-backup -c bedrock
```

### Check playit.gg Tunnel Status

```bash
KUBECONFIG=/home/al/.kube/config kubectl logs deploy/minecraft-bedrock -n minecraft -c playit --tail=20
```

Look for `tunnel running, 1 tunnels registered` to confirm the tunnel is active.

## Troubleshooting

### Server Won't Start

1. Check pod status: `kubectl get pods -n minecraft`
2. Check events: `kubectl get events -n minecraft --sort-by='.lastTimestamp'`
3. Check logs: `kubectl logs deploy/minecraft-bedrock -n minecraft -c bedrock`

### Players Can't Connect

1. Verify they're on the whitelist
2. Check the playit.gg tunnel is running
3. Verify the tunnel address is correct in playit.gg dashboard
4. Ensure they're using Bedrock Edition (not Java Edition)

### Tunnel Not Connecting

1. Check playit sidecar logs for errors
2. Verify the secret key is valid
3. Check NetworkPolicy allows outbound traffic

## File Locations

| Path | Description |
|------|-------------|
| `/data/worlds/` | World save data |
| `/data/allowlist.json` | Whitelisted players |
| `/data/permissions.json` | Operator permissions |
| `/data/server.properties` | Server configuration |

## GitOps Files

| File | Purpose |
|------|---------|
| `gitops/apps/minecraft/namespace.yaml` | Namespace definition |
| `gitops/apps/minecraft/deployment.yaml` | Server + playit sidecar |
| `gitops/apps/minecraft/configmap.yaml` | Server settings |
| `gitops/apps/minecraft/secret.enc.yaml` | playit.gg credentials (encrypted) |
| `gitops/apps/minecraft/networkpolicy.yaml` | Network isolation |
| `gitops/apps/minecraft/pvc.yaml` | World data storage |
| `gitops/apps/minecraft/service.yaml` | Internal service |
