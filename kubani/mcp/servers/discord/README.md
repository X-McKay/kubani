# Discord MCP Server

A Model Context Protocol (MCP) server providing bidirectional Discord integration for Kubani AI agents.

## Features

- **Messages**: Send, read, delete messages; await replies
- **Reactions**: Add, remove, get reactions; await reaction responses
- **Channels**: List, create, delete text channels
- **Webhooks**: List, create, delete webhooks

## Installation

```bash
cd kubani/mcp/servers/discord
uv pip install -e .
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | Discord bot token |
| `DISCORD_GUILD_ID` | No | Default guild ID for operations |

### Creating a Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" → "Add Bot"
4. Copy the token
5. Enable "Message Content Intent" in bot settings
6. Use OAuth2 URL Generator to invite bot with required permissions:
   - Send Messages
   - Read Message History
   - Add Reactions
   - Manage Channels (if using channel tools)
   - Manage Webhooks (if using webhook tools)

## Usage

### As Standalone Server

```bash
export DISCORD_BOT_TOKEN=your_token
export DISCORD_GUILD_ID=your_guild_id  # optional
discord-mcp-server
```

### With Claude Code

Add to your MCP settings:

```json
{
  "mcpServers": {
    "discord": {
      "command": "discord-mcp-server",
      "env": {
        "DISCORD_BOT_TOKEN": "your_token",
        "DISCORD_GUILD_ID": "your_guild_id"
      }
    }
  }
}
```

### In Kubani Cluster

The server is configured in `mcp/servers/discord.json` and synced to the cluster via GitOps.

## Available Tools

### Message Tools

| Tool | Description |
|------|-------------|
| `send_message` | Send a message to a channel by ID |
| `send_message_to_channel_name` | Send a message to a channel by name |
| `get_messages` | Get recent messages from a channel |
| `get_message` | Get a specific message by ID |
| `delete_message` | Delete a message |
| `await_reply` | Wait for a reply in a channel |

### Reaction Tools

| Tool | Description |
|------|-------------|
| `add_reaction` | Add a reaction to a message |
| `remove_reaction` | Remove the bot's reaction |
| `get_reactions` | Get all reactions on a message |
| `await_reaction` | Wait for a reaction on a message |

### Channel Tools

| Tool | Description |
|------|-------------|
| `list_channels` | List all text channels in the guild |
| `create_channel` | Create a new text channel |
| `delete_channel` | Delete a channel |

### Webhook Tools

| Tool | Description |
|------|-------------|
| `list_webhooks` | List webhooks for a channel |
| `create_webhook` | Create a new webhook |
| `delete_webhook` | Delete a webhook |

## Examples

### Sending a Rich Embed

```python
await send_message(
    channel_id=123456789,
    embed={
        "title": "Cluster Health",
        "description": "All systems operational",
        "color": 0x57F287,  # Green
        "fields": [
            {"name": "Nodes", "value": "3/3 healthy", "inline": True},
            {"name": "Pods", "value": "42 running", "inline": True},
        ],
        "footer": "Kubani K8s Monitor",
    }
)
```

### Waiting for Approval

```python
# Send approval request
msg = await send_message(
    channel_id=123456789,
    content="Approve scaling deployment? React with ✅ or ❌"
)

# Add reaction options
await add_reaction(channel_id=123456789, message_id=msg.message_id, emoji="✅")
await add_reaction(channel_id=123456789, message_id=msg.message_id, emoji="❌")

# Wait for response
result = await await_reaction(
    channel_id=123456789,
    message_id=msg.message_id,
    valid_emojis=["✅", "❌"],
    timeout_seconds=300,
)

if result and result.emoji == "✅":
    # Approved!
    pass
```

### Conversational Approval

```python
# Send question
msg = await send_message(
    channel_id=123456789,
    content="Should I scale `api-server` to 5 replicas? Reply with yes/no."
)

# Wait for reply
reply = await await_reply(
    channel_id=123456789,
    to_message_id=msg.message_id,
    timeout_seconds=300,
)

if reply and "yes" in reply.content.lower():
    # Approved!
    pass
```

## Development

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Type check
ty check src/
```

## Architecture

```
discord-mcp-server/
├── src/discord_mcp/
│   ├── __init__.py      # Entry point
│   ├── server.py        # MCP server with all tools
│   ├── client.py        # Discord.py client wrapper
│   └── models.py        # Pydantic models for tool I/O
├── tests/
├── pyproject.toml
└── README.md
```

The server uses:
- **FastMCP** for MCP protocol handling
- **discord.py** for Discord Gateway connection
- **Pydantic** for input/output validation

## Network Requirements

The server connects **outbound** to Discord's Gateway API. No inbound connections required - works fine on Tailscale-only networks.
