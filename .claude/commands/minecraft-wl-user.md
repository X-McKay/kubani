# Minecraft Whitelist User

Add a player to the Minecraft Bedrock server whitelist.

## Arguments
- `$ARGUMENTS` - Required: Xbox/Microsoft gamertag of the player to add

## Instructions

1. **Parse the gamertag from arguments:**
   - The gamertag is the player's Xbox/Microsoft account name
   - Gamertags are case-insensitive but preserve the original casing

2. **Look up the player's XUID:**
   ```bash
   curl -s "https://api.geysermc.org/v2/xbox/xuid/<GAMERTAG>"
   ```
   - If found, extract the `xuid` field from the JSON response
   - If not found (message about cache), proceed without XUID - it will be resolved on first connection

3. **Get current allowlist:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl exec deploy/minecraft-bedrock -n minecraft -c bedrock -- cat /data/allowlist.json
   ```

4. **Add the new player to the allowlist:**
   - If XUID was found:
     ```json
     {
       "ignoresPlayerLimit": false,
       "name": "<GAMERTAG>",
       "xuid": "<XUID>"
     }
     ```
   - If XUID was not found:
     ```json
     {
       "ignoresPlayerLimit": false,
       "name": "<GAMERTAG>"
     }
     ```

5. **Write the updated allowlist:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl exec deploy/minecraft-bedrock -n minecraft -c bedrock -- /bin/sh -c 'cat > /data/allowlist.json << EOF
   <UPDATED_JSON>
   EOF'
   ```

6. **Verify the update:**
   ```bash
   KUBECONFIG=/home/al/.kube/config kubectl exec deploy/minecraft-bedrock -n minecraft -c bedrock -- cat /data/allowlist.json
   ```

7. **Report the result to the user:**
   - Confirm the player was added
   - Note if XUID was resolved or will be resolved on first connection
   - Remind that no server restart is needed

## Output Format

```
Added <GAMERTAG> to Minecraft whitelist.
XUID: <XUID> (or "will resolve on first connection")

Current whitelist:
- Player1
- Player2
- <GAMERTAG> (new)
```

## Examples

- `/minecraft-wl-user Littlebeebumble` - Add player with gamertag "Littlebeebumble"
- `/minecraft-wl-user X7Doom` - Add player with gamertag "X7Doom"

## Notes

- The server automatically picks up allowlist changes (no restart needed)
- XUIDs are immutable - they stay the same even if the player changes their gamertag
- If the GeyserMC API doesn't have the XUID cached, the server will resolve it when the player first connects
