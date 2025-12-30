# Minecraft Bedrock Server

Family Minecraft server with playit.gg for external access.

## Setup Steps

### 1. Create playit.gg Account & Agent

1. Go to https://playit.gg and create an account
2. Navigate to https://playit.gg/account/agents/new-docker
3. Create a new Docker agent and copy the `SECRET_KEY`

### 2. Configure the Secret

Edit `secret.yaml` and replace `REPLACE_WITH_PLAYIT_SECRET_KEY` with your key:

```bash
# Edit the secret
vim gitops/apps/minecraft/secret.yaml

# Encrypt with SOPS
cd /home/al/git/kubani
SOPS_AGE_KEY_FILE=age.key sops -e -i gitops/apps/minecraft/secret.yaml
```

Rename to `.enc.yaml` after encryption:
```bash
mv gitops/apps/minecraft/secret.yaml gitops/apps/minecraft/secret.enc.yaml
```

Update `kustomization.yaml` to reference `secret.enc.yaml`.

### 3. Configure playit.gg Tunnel

After the pod starts, the playit agent will register. Go to https://playit.gg/account/tunnels to:

1. Create a new tunnel
2. Select "Minecraft Bedrock" as the game type
3. Set the local address to `127.0.0.1:19132`
4. Copy the tunnel address (e.g., `abc123.playit.gg:12345`)

### 4. Whitelist Players

To add players to the whitelist, exec into the pod:

```bash
KUBECONFIG=/home/al/.kube/config kubectl exec -it deploy/minecraft-bedrock -n minecraft -c bedrock -- /bin/bash

# Inside the container, the allowlist.json is at /data/allowlist.json
# Players are added by their Xbox/Microsoft gamertag
```

Or edit the ConfigMap to include `ALLOW_LIST_USERS` with comma-separated gamertags.

## Architecture

```
Internet Players
       │
       ▼
playit.gg Anycast Network (DDoS protected)
       │
       ▼ (encrypted tunnel)
┌──────────────────────────────────────┐
│ Kubernetes Pod                       │
│ ┌─────────────┐  ┌─────────────────┐ │
│ │ playit      │──│ minecraft       │ │
│ │ sidecar     │  │ bedrock server  │ │
│ └─────────────┘  └─────────────────┘ │
│        │                  │          │
│        └────localhost─────┘          │
└──────────────────────────────────────┘
       │
       ▼
    NAS PVC (world data)
```

## Security

- **NetworkPolicy**: Blocks all cluster-internal traffic; only allows outbound to playit.gg
- **Whitelist**: Only approved players can connect
- **No exposed ports**: All external access through playit.gg tunnel
- **Origin IP hidden**: Players never see your real IP

## Configuration

Edit `configmap.yaml` to change:

| Setting | Default | Description |
|---------|---------|-------------|
| SERVER_NAME | McKay Family Server | Server name shown to players |
| GAMEMODE | survival | survival, creative, adventure |
| DIFFICULTY | normal | peaceful, easy, normal, hard |
| MAX_PLAYERS | 10 | Max concurrent players |
| VIEW_DISTANCE | 10 | Render distance (chunks) |

## Troubleshooting

### Check server status
```bash
KUBECONFIG=/home/al/.kube/config kubectl logs deploy/minecraft-bedrock -n minecraft -c bedrock
```

### Check playit tunnel
```bash
KUBECONFIG=/home/al/.kube/config kubectl logs deploy/minecraft-bedrock -n minecraft -c playit
```

### Restart server
```bash
KUBECONFIG=/home/al/.kube/config kubectl rollout restart deploy/minecraft-bedrock -n minecraft
```
