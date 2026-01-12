---
name: publish-to-discord
version: "2.0.0"
description: >
  Publish news digests and breaking alerts to Discord via the Discord MCP server.
  Handles message chunking for Discord's 2000 character limit.
  Uses embeds for breaking alerts to make them stand out.
  Keywords: publish, discord, news, digest, breaking, alert.
metadata:
  domain: news
  category: action
  requires-approval: true  # External side effect
  confidence: 0.95
dependencies:
  mcp-servers:
    - discord-mcp-server
  skills: []
  tools: []
execution:
  timeout: 60s
  retries: 2
  backoff: exponential
input:
  - name: content
    type: str
    description: Formatted content to publish
  - name: content_type
    type: str
    enum: [digest, breaking_alert]
    description: Type of content being published
  - name: article
    type: ProcessedArticle
    optional: true
    description: Article for breaking alerts (required if content_type=breaking_alert)
  - name: channel_name
    type: str
    optional: true
    description: "Target channel (default: ai-news)"
output:
  - name: message_id
    type: str
    description: Discord message ID if successful
  - name: published
    type: bool
    description: Whether publish succeeded
---

# Publish to Discord

Publish news content to Discord via the Discord MCP server.

## When to Use

- Publishing regular news digests
- Alerting about breaking news
- Sharing formatted news summaries
- Keywords: publish, post, discord, news, digest, breaking

## Prerequisites

- DISCORD_MCP_URL environment variable set (or use default)
- Target channel exists (default: ai-news)
- Content formatted for Discord (markdown)

## Input Schema

```json
{
  "content": "string - Formatted content to publish",
  "content_type": "string - 'digest' or 'breaking_alert'",
  "article": {
    "title": "string - Article title (for breaking alerts)",
    "url": "string - Article URL",
    "source": "string - News source",
    "category": "string - Article category",
    "ai_summary": "string - AI-generated summary"
  },
  "channel_name": "string - Target channel (default: ai-news)"
}
```

## Actions

### Step 1: Validate Configuration

Check that Discord MCP is accessible. If not:
- Log warning
- Return published=false
- Skip remaining steps

### Step 2: Route by Content Type

**For digest:**
1. Split message if > 1900 characters (Discord limit is 2000)
2. Post each chunk as separate message
3. Return message ID of first chunk

**For breaking_alert:**
1. Build Discord embed with red color (0xED4245)
2. Include @here mention for notification
3. Structure embed with article details

### Step 3: Post Content

**For digest (plain text with chunking):**

```yaml
# For each chunk:
mcp_tool: discord-mcp-server/send_message_to_channel_name
params:
  channel_name: $channel_name
  content: $chunk_content
```

**For breaking_alert (rich embed):**

```yaml
mcp_tool: discord-mcp-server/send_message_to_channel_name
params:
  channel_name: $channel_name
  content: "@here **Breaking AI News**"
  embed:
    title: "BREAKING: $article.title"
    description: $article.ai_summary
    url: $article.url
    color: 15158332  # Red
    fields:
      - name: "Source"
        value: $article.source
        inline: true
      - name: "Category"
        value: $article.category
        inline: true
    footer:
      text: "AI News Monitor - Breaking Alert"
    timestamp: $current_timestamp
```

### Step 4: Handle Chunking (Digest only)

If content exceeds 1900 characters:
1. Split by paragraphs (double newline)
2. If paragraph too long, split by lines
3. Post chunks sequentially with small delay
4. Maintain logical breaks

**Chunking algorithm:**
```
max_chunk_size = 1900
chunks = []
current_chunk = ""

for paragraph in content.split("\n\n"):
    if len(current_chunk) + len(paragraph) + 2 <= max_chunk_size:
        current_chunk += paragraph + "\n\n"
    else:
        if current_chunk:
            chunks.append(current_chunk.strip())
        current_chunk = paragraph + "\n\n"

if current_chunk:
    chunks.append(current_chunk.strip())
```

## Output Schema

```json
{
  "published": "boolean - Whether publish succeeded",
  "message_id": "string - Discord message ID (first chunk for digests)",
  "chunks_sent": "number - Number of message chunks sent (digest only)",
  "channel": "string - Channel where content was posted",
  "error": "string - Error message if failed"
}
```

## Success Criteria

- Content posted to Discord
- Message ID returned for tracking
- Breaking alerts trigger @here notifications
- Long content properly chunked

## Failure Handling

| Error Type | Handling Strategy |
|------------|-------------------|
| MCP server unavailable | Retry with backoff |
| Channel not found | Log error, return published=false |
| Rate limited | Wait and retry |
| Content too long | Auto-chunk and retry |

## Idempotency

This operation is NOT idempotent:
- Same content posted multiple times creates multiple messages
- Use breaking news claim system to prevent duplicate alerts
- Digest deduplication handled by workflow scheduling

## Examples

### Example 1: News Digest

**Input:**
```json
{
  "content": "# AI News Digest - Jan 11, 2025\n\n## Top Stories\n\n1. **OpenAI announces GPT-5**...\n\n2. **Google releases Gemini 2.0**...",
  "content_type": "digest",
  "channel_name": "ai-news"
}
```

**MCP Tool Call:**
```yaml
mcp_tool: discord-mcp-server/send_message_to_channel_name
params:
  channel_name: ai-news
  content: "# AI News Digest - Jan 11, 2025\n\n## Top Stories\n\n1. **OpenAI announces GPT-5**..."
```

**Output:**
```json
{
  "published": true,
  "message_id": "1234567890",
  "chunks_sent": 1,
  "channel": "ai-news"
}
```

### Example 2: Breaking News Alert

**Input:**
```json
{
  "content_type": "breaking_alert",
  "article": {
    "title": "Major AI Breakthrough: AGI Achieved",
    "url": "https://example.com/agi-breakthrough",
    "source": "TechCrunch",
    "category": "research",
    "ai_summary": "Researchers announce successful demonstration of artificial general intelligence..."
  },
  "channel_name": "ai-news"
}
```

**MCP Tool Call:**
```yaml
mcp_tool: discord-mcp-server/send_message_to_channel_name
params:
  channel_name: ai-news
  content: "@here **Breaking AI News**"
  embed:
    title: "BREAKING: Major AI Breakthrough: AGI Achieved"
    description: "Researchers announce successful demonstration of artificial general intelligence..."
    url: "https://example.com/agi-breakthrough"
    color: 15158332
    fields:
      - name: "Source"
        value: "TechCrunch"
        inline: true
      - name: "Category"
        value: "Research"
        inline: true
    footer:
      text: "AI News Monitor - Breaking Alert"
```

**Output:**
```json
{
  "published": true,
  "message_id": "9876543210",
  "channel": "ai-news"
}
```

## Related Skills

- [send-discord-notification](../../../general/notifications/send-discord-notification/SKILL.md) - Generic notifications
- [compose-digest](../compose-digest/SKILL.md) - Create digest content
- [detect-breaking-news](../../diagnostic/detect-breaking-news/SKILL.md) - Identify breaking news

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2025-01-11 | Migrated to Discord MCP server from webhooks |
| 1.0.0 | 2025-01-09 | Initial version with webhook support |
