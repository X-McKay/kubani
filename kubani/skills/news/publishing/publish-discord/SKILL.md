---
name: publish-discord
description: >
  Publish formatted content to Discord channels using webhooks or MCP server.
  Handles message splitting for character limits, supports embeds and formatting.
  Use after composing digests or detecting breaking news to notify Discord channels.
license: MIT
compatibility: Requires Discord webhook URL or Discord MCP server
metadata:
  kubani:
    domain: news
    category: publishing
    requires_approval: true
    confidence: 0.98
    mcp_servers: ["discord"]
    version: "1.0.0"
---

# Publish to Discord

Publish formatted content to Discord channels.

## When to Use

Use this skill when you need to:
- Post news digests to Discord channels
- Send breaking news alerts
- Notify teams of important updates
- Share formatted content with Discord communities

## Prerequisites

**Required:**
- Discord webhook URL OR Discord MCP server access
- Channel permissions to post messages

**Optional:**
- `requests` Python package (for webhook approach)
- Discord MCP server configured (for MCP approach)

## Instructions

### Step 1: Choose Publishing Method

Two approaches available:

**Method A: Webhook (Simple)**
- Direct HTTP POST to webhook URL
- No authentication needed beyond webhook URL
- Limited to basic messages and embeds

**Method B: MCP Server (Advanced)**
- Uses Discord MCP server for full API access
- Supports advanced features (threads, reactions, etc.)
- Requires MCP server configuration

```python
from enum import Enum

class PublishMethod(Enum):
    WEBHOOK = "webhook"
    MCP = "mcp"

def choose_publish_method(
    webhook_url: str | None = None,
    mcp_available: bool = False
) -> PublishMethod:
    """
    Choose publishing method based on availability.
    
    Args:
        webhook_url: Discord webhook URL
        mcp_available: Whether Discord MCP is available
    
    Returns:
        Preferred publishing method
    """
    if mcp_available:
        return PublishMethod.MCP
    elif webhook_url:
        return PublishMethod.WEBHOOK
    else:
        raise ValueError("No Discord publishing method available")
```

### Step 2: Split Long Messages

Discord has 2000 character limit per message:

```python
def split_message(content: str, max_length: int = 2000) -> list[str]:
    """
    Split long content into Discord-compatible chunks.
    
    Preserves markdown formatting and splits at logical boundaries.
    
    Args:
        content: Content to split
        max_length: Maximum characters per chunk
    
    Returns:
        List of message chunks
    """
    if len(content) <= max_length:
        return [content]
    
    chunks = []
    current_chunk = ""
    
    # Split by lines to preserve formatting
    lines = content.split("\n")
    
    for line in lines:
        # If single line is too long, split it
        if len(line) > max_length:
            # Save current chunk
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # Split long line by sentences
            sentences = line.split(". ")
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 2 > max_length - 100:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence + ". "
                else:
                    current_chunk += sentence + ". "
        else:
            # Check if adding line exceeds limit
            if len(current_chunk) + len(line) + 1 > max_length - 100:
                chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
    
    # Add remaining content
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks
```

### Step 3: Publish via Webhook

Simple HTTP POST approach:

```python
import requests
from typing import Dict, Any

def publish_via_webhook(
    webhook_url: str,
    content: str,
    username: str = "Kubani News Bot",
    avatar_url: str | None = None
) -> bool:
    """
    Publish content to Discord via webhook.
    
    Args:
        webhook_url: Discord webhook URL
        content: Message content (will be split if needed)
        username: Bot username to display
        avatar_url: Optional bot avatar URL
    
    Returns:
        True if successful, False otherwise
    """
    # Split content if needed
    chunks = split_message(content)
    
    for i, chunk in enumerate(chunks):
        payload = {
            "content": chunk,
            "username": username,
        }
        
        if avatar_url:
            payload["avatar_url"] = avatar_url
        
        # Add part indicator for multi-part messages
        if len(chunks) > 1:
            payload["content"] = f"**[Part {i+1}/{len(chunks)}]**\n\n{chunk}"
        
        try:
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            
            # Rate limit: Discord allows 5 messages per 2 seconds
            if i < len(chunks) - 1:
                import time
                time.sleep(0.5)
        
        except requests.RequestException as e:
            print(f"Failed to publish chunk {i+1}: {e}")
            return False
    
    return True
```

### Step 4: Create Rich Embeds

Use embeds for better formatting:

```python
def create_embed(
    title: str,
    description: str,
    url: str | None = None,
    color: int = 0x0099ff,
    fields: list[dict] | None = None,
    footer: str | None = None
) -> dict:
    """
    Create Discord embed object.
    
    Args:
        title: Embed title
        description: Embed description
        url: Optional URL for title link
        color: Embed color (hex)
        fields: Optional list of {name, value, inline} dicts
        footer: Optional footer text
    
    Returns:
        Embed dictionary
    """
    embed = {
        "title": title,
        "description": description,
        "color": color,
    }
    
    if url:
        embed["url"] = url
    
    if fields:
        embed["fields"] = fields
    
    if footer:
        embed["footer"] = {"text": footer}
    
    # Add timestamp
    from datetime import datetime, UTC
    embed["timestamp"] = datetime.now(UTC).isoformat()
    
    return embed

def publish_embed_via_webhook(
    webhook_url: str,
    embed: dict,
    content: str | None = None
) -> bool:
    """
    Publish embed to Discord via webhook.
    
    Args:
        webhook_url: Discord webhook URL
        embed: Embed object
        content: Optional message content
    
    Returns:
        True if successful
    """
    payload = {"embeds": [embed]}
    
    if content:
        payload["content"] = content
    
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Failed to publish embed: {e}")
        return False
```

### Step 5: Publish via MCP Server

Use Discord MCP for advanced features:

```python
async def publish_via_mcp(
    mcp_client,
    channel_id: str,
    content: str,
    thread_name: str | None = None
) -> bool:
    """
    Publish content via Discord MCP server.
    
    Args:
        mcp_client: MCP client instance
        channel_id: Discord channel ID
        content: Message content
        thread_name: Optional thread name for creating thread
    
    Returns:
        True if successful
    """
    try:
        # Split content if needed
        chunks = split_message(content)
        
        # Create thread if requested
        thread_id = None
        if thread_name:
            result = await mcp_client.call_tool(
                "discord_create_thread",
                {
                    "channel_id": channel_id,
                    "name": thread_name,
                    "auto_archive_duration": 1440  # 24 hours
                }
            )
            thread_id = result.get("thread_id")
        
        # Post messages
        target_id = thread_id or channel_id
        
        for chunk in chunks:
            await mcp_client.call_tool(
                "discord_send_message",
                {
                    "channel_id": target_id,
                    "content": chunk
                }
            )
        
        return True
    
    except Exception as e:
        print(f"Failed to publish via MCP: {e}")
        return False
```

### Step 6: Format Breaking News Alerts

Create urgent-looking alerts:

```python
def format_breaking_alert(article: dict) -> dict:
    """
    Format breaking news as Discord embed.
    
    Args:
        article: Breaking news article
    
    Returns:
        Embed dictionary
    """
    title = article.get("title", "")
    summary = article.get("ai_summary", "")
    url = article.get("url", "")
    source = article.get("source", "")
    importance = article.get("importance_score", 0)
    breaking_reason = article.get("breaking_reason", "")
    
    # Red color for breaking news
    embed = create_embed(
        title=f"🚨 {title}",
        description=summary,
        url=url,
        color=0xff0000,  # Red
        fields=[
            {"name": "Source", "value": source, "inline": True},
            {"name": "Importance", "value": f"{importance}/10", "inline": True},
        ],
        footer=f"Breaking: {breaking_reason}" if breaking_reason else "Breaking News"
    )
    
    return embed

def publish_breaking_alert(
    webhook_url: str,
    article: dict
) -> bool:
    """
    Publish breaking news alert to Discord.
    
    Args:
        webhook_url: Discord webhook URL
        article: Breaking news article
    
    Returns:
        True if successful
    """
    embed = format_breaking_alert(article)
    
    return publish_embed_via_webhook(
        webhook_url,
        embed,
        content="@here **BREAKING NEWS**"  # Mention everyone
    )
```

## Discord Formatting

### Markdown Support
- **Bold:** `**text**`
- *Italic:* `*text*`
- ***Bold Italic:*** `***text***`
- Underline: `__text__`
- ~~Strikethrough:~~ `~~text~~`
- Code: `` `code` ``
- Code block: ` ```code block``` `

### Mentions
- User: `<@user_id>`
- Role: `<@&role_id>`
- Channel: `<#channel_id>`
- Everyone: `@everyone`
- Here: `@here`

### Emojis
- Standard: `:emoji_name:`
- Custom: `<:emoji_name:emoji_id>`

### Links
- Markdown: `[text](url)`
- Masked: `[text](url "hover text")`

## Webhook vs MCP Comparison

| Feature | Webhook | MCP Server |
|---------|---------|------------|
| **Setup** | Simple (just URL) | Complex (MCP config) |
| **Authentication** | URL-based | OAuth/token |
| **Message sending** | ✅ Yes | ✅ Yes |
| **Embeds** | ✅ Yes | ✅ Yes |
| **Threads** | ❌ No | ✅ Yes |
| **Reactions** | ❌ No | ✅ Yes |
| **Message editing** | ❌ No | ✅ Yes |
| **Rate limits** | 5/2s per webhook | 50/s per bot |
| **Use case** | Simple notifications | Advanced bot features |

## Common Issues

**Issue: Messages truncated**
- **Cause:** Exceeding 2000 character limit
- **Solution:** Use split_message() function

**Issue: Webhook rate limited**
- **Cause:** Sending too many messages too fast
- **Solution:** Add delays between messages (0.5s)

**Issue: Embed not displaying**
- **Cause:** Invalid embed structure
- **Solution:** Validate embed fields, check color format

**Issue: Mentions not working**
- **Cause:** Webhook can't mention @everyone by default
- **Solution:** Enable mentions in webhook settings or use MCP

## Output Format

Return success status and message IDs:
```python
{
    "success": true,
    "messages_sent": 3,
    "message_ids": ["123456789", "123456790", "123456791"],
    "channel_id": "987654321",
    "thread_id": null
}
```

## Performance Considerations

- **Rate limits:** Respect Discord's 5 messages per 2 seconds limit
- **Message splitting:** Pre-split content to avoid failures
- **Retries:** Implement exponential backoff for rate limit errors
- **Batching:** Group related messages into embeds when possible
- **Webhooks:** Faster than MCP for simple messages

## Success Criteria

- Messages are delivered to correct channel
- Long content is properly split
- Formatting is preserved
- Rate limits are respected
- Breaking alerts are visually distinct
- No message truncation or loss
