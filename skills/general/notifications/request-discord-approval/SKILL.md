---
name: request-discord-approval
description: >
  Request human approval for a critical operation via Discord. Posts a message
  with reaction buttons and waits for response. Use for destructive or
  irreversible operations. Keywords: approval, Discord, human-in-the-loop,
  confirmation, dangerous operation.
metadata:
  domain: general
  category: notifications
  requires-approval: false
  confidence: 0.9
  mcp-servers: []
---

# Request Discord Approval

## Preconditions

Before applying this skill, verify:

- Operation requires human review
- DISCORD_WEBHOOK_URL is configured
- Discord bot token available (for reactions)
- Timeout duration is acceptable (default: 5 minutes)

## Actions

### 1. Format Approval Request

Build the approval embed:
```yaml
color: 16753920  # Orange - attention required
title: "Approval Required"
description: $operation_description
fields:
  - name: Action
    value: $proposed_action
  - name: Resource
    value: $target_resource
  - name: Agent
    value: $requesting_agent
  - name: Reason
    value: $justification
footer:
  text: "React with ✅ to approve or ❌ to reject"
```

### 2. Post to Discord

Send the embed to the approval channel.

```yaml
method: POST
url: $DISCORD_WEBHOOK_URL
body:
  embeds: [$approval_embed]
  username: "Kubani Approval Bot"
```

### 3. Add Reaction Buttons

Add reactions to the message for voting:
- ✅ (white_check_mark) - Approve
- ❌ (x) - Reject

### 4. Wait for Response

Poll for reactions or wait for event:
- Timeout: 5 minutes default
- Accept first human reaction
- Log response with timestamp and user

## Success Criteria

The skill succeeds when:

- [ ] Approval request posted successfully
- [ ] Human response received within timeout
- [ ] Response recorded with audit trail

## Failure Handling

If approval request fails:

1. Log warning about failed approval request
2. Default to DENIED for safety
3. Escalate if critical operation blocked

If timeout:

1. Consider operation NOT approved
2. Notify that approval timed out
3. Allow retry with extended timeout

## Examples

**Input Context:**
```json
{
  "action": "Delete Pod",
  "resource": "production/api-server-abc123",
  "agent": "k8s-healer",
  "reason": "Pod stuck in CrashLoopBackOff, restart required",
  "timeout_seconds": 300
}
```

**Expected Output:**
```json
{
  "approved": true,
  "responder": "admin#1234",
  "response_time_seconds": 45,
  "reason": "Approved via Discord reaction"
}
```
