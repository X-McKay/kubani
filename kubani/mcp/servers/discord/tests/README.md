# Discord MCP Integration Tests

This directory contains integration tests for the Discord MCP server that test against a mock Discord API.

## Running Integration Tests

### Prerequisites

- Docker and Docker Compose installed
- Python environment with test dependencies

### Setup

1. Start the Discord API mock:
```bash
cd kubani/mcp/servers/discord
docker-compose -f docker-compose.integration.yml up -d
```

2. Wait for the mock server to be healthy (about 10 seconds):
```bash
docker-compose -f docker-compose.integration.yml ps
```

The mock server should show "healthy" status.

### Running Tests

Run integration tests with pytest:

```bash
# From the discord-mcp directory
uv run pytest tests/test_integration.py -v

# Or from the workspace root
uv run pytest kubani/mcp/servers/discord/tests/test_integration.py -v
```

### Cleanup

Stop and remove the mock server:

```bash
docker-compose -f docker-compose.integration.yml down -v
```

## Test Coverage

Integration tests cover:

- **Message Operations**:
  - Sending messages to channels
  - Retrieving messages from channels
  - Message retrieval by ID
  - Message deletion

- **Reaction Operations**:
  - Adding reactions to messages
  - Removing reactions
  - Getting reactions on messages

- **Channel Operations**:
  - Listing channels
  - Creating channels
  - Deleting channels

- **Webhook Operations**:
  - Creating webhooks
  - Listing webhooks
  - Deleting webhooks

## Mock Discord API

The integration tests use MockServer to simulate the Discord API. The mock is configured with:

- **Gateway endpoint**: Returns WebSocket URL
- **User endpoint**: Returns bot user information
- **Message endpoints**: Support creating, reading, and deleting messages
- **Channel endpoints**: Support channel operations
- **Webhook endpoints**: Support webhook management

Mock expectations are defined in `tests/mock-config/expectations.json`.

## Environment Variables

The integration tests use a mock Discord bot token:

- `DISCORD_BOT_TOKEN=mock-token-for-testing`
- `DISCORD_GUILD_ID=123456789`

These are set automatically in the test file and do not require real Discord credentials.

## Limitations

Since we're using a mock API, some Discord features are simplified:

- WebSocket gateway is not fully simulated
- Real-time events (reactions, replies) are mocked with timeouts
- Some Discord-specific validation is bypassed

For full end-to-end testing with real Discord, use a test Discord server with a real bot token.
