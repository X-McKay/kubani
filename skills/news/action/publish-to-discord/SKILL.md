---
name: publish-to-discord
description: >
  Publish news digests and breaking alerts to Discord via webhook.
  Handles message chunking for Discord's 2000 character limit.
  Uses embeds for breaking alerts to make them stand out.
metadata:
  domain: news
  category: action
  mcp-servers: []
  requires-approval: true  # External side effect
  confidence: 0.95
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
output:
  - name: message_id
    type: str
    description: Discord message ID if successful
  - name: published
    type: bool
    description: Whether publish succeeded
---

# Publish to Discord

Publish content to Discord via webhook.

## Preconditions

- `DISCORD_WEBHOOK_URL` environment variable set
- Content formatted for Discord (markdown)

## Actions

### Step 1: Validate Webhook Configuration

Check that `DISCORD_WEBHOOK_URL` is configured. If not:
- Log warning
- Return published=false
- Skip remaining steps

### Step 2: Route by Content Type

**For digest:**
1. Split message if > 1900 characters (Discord limit is 2000)
2. Post each chunk as separate message
3. Return message ID of first chunk

**For breaking_alert:**
1. Build Discord embed with red color (15158332)
2. Include @here mention for notification
3. Structure embed with fields:
   - Title: `BREAKING: {article.title}`
   - Description: Article summary
   - URL: Link to article
   - Source field (inline)
   - Category field (inline)
   - Footer: "AI News Monitor - Breaking Alert"

### Step 3: Post to Webhook

Make HTTP POST to webhook URL:
- Add `?wait=true` parameter to get message details back
- Set username to "AI News Monitor"
- Handle errors gracefully

### Step 4: Handle Chunking (Digest only)

If content exceeds 1900 characters:
1. Split by paragraphs (double newline)
2. If paragraph too long, split by lines
3. Post chunks sequentially
4. Maintain logical breaks

## Success Criteria

- Content posted to Discord
- Message ID returned for tracking
- Breaking alerts trigger notifications
- Long content properly chunked

## Error Handling

On HTTP error:
- Log error details
- Return published=false
- Do not retry (caller decides)

## Idempotency

This operation is NOT idempotent:
- Same content posted multiple times creates multiple messages
- Use breaking news claim system to prevent duplicate alerts
- Digest deduplication handled by workflow scheduling
