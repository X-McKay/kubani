---
name: send-discord-notification
description: >
  Send a notification to Discord with rich formatting. Supports different
  notification types: health reports, issue alerts, investigation results,
  and escalations. Keywords: Discord, notification, alert, message, webhook.
metadata:
  domain: general
  category: notifications
  requires-approval: false
  confidence: 0.95
  mcp-servers: []
---

# Send Discord Notification

## Preconditions

Before applying this skill, verify:

- DISCORD_WEBHOOK_URL environment variable is set
- Message content or embed data is available
- Network access to Discord API

## Actions

### 1. Determine Notification Type

Classify the notification:
- **health**: Healthy status reports (green)
- **issue**: Issue detection alerts (yellow/orange)
- **investigation**: Analysis findings with evidence (blue)
- **success**: Successful resolutions (green)
- **failure**: Failed operations (red)
- **escalation**: Manual intervention required (purple)

### 2. Format Discord Embed

Build the embed structure:
```yaml
color: $type_color
title: $notification_title
description: $summary
fields:
  - name: Resource
    value: $resource_info
    inline: true
  - name: Status
    value: $status
    inline: true
timestamp: $current_timestamp
footer:
  text: "Kubani Agent"
```

### 3. Send to Webhook

POST the embed to the Discord webhook endpoint.

```yaml
method: POST
url: $DISCORD_WEBHOOK_URL
headers:
  Content-Type: application/json
body:
  embeds: [$formatted_embed]
  username: "Kubani AI"
```

## Success Criteria

The skill succeeds when:

- [ ] HTTP 204 response from Discord
- [ ] No rate limit errors
- [ ] Message appears in channel

## Failure Handling

If notification fails:

1. Retry with exponential backoff (3 attempts)
2. Log failure for debugging
3. Queue for later delivery if persistent failure

## Examples

**Input Context:**
```json
{
  "type": "issue",
  "title": "CrashLoopBackOff Detected",
  "resource": "nginx-deployment-abc123",
  "namespace": "production",
  "severity": "high",
  "description": "Pod has restarted 5 times in the last 10 minutes"
}
```

**Expected Output:**
Discord embed with orange border, issue title, resource details, and timestamp.
