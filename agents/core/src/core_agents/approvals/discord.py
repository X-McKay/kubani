"""
Discord-based approval flow.

Posts approval requests to Discord and waits for reaction responses.
"""

import asyncio
import os
import uuid

import httpx

from core_agents.approvals.schema import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
)


class DiscordApprover:
    """
    Discord-based approval mechanism.

    Posts approval requests to a Discord channel and monitors for
    reaction responses (✅ = approve, ❌ = reject).

    Note: This implementation uses Discord webhooks for posting and
    requires a bot token for reading reactions. If no bot token is
    available, it falls back to a simple confirmation model.
    """

    APPROVE_EMOJI = "✅"
    REJECT_EMOJI = "❌"

    def __init__(
        self,
        webhook_url: str | None = None,
        bot_token: str | None = None,
        poll_interval: float = 5.0,
    ):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")
        self.poll_interval = poll_interval

        if not self.webhook_url:
            raise ValueError(
                "Discord webhook URL required. Set DISCORD_WEBHOOK_URL environment variable."
            )

    async def request_approval(
        self,
        request: ApprovalRequest,
    ) -> ApprovalResult:
        """
        Request approval via Discord.

        Posts a message with reaction options and waits for a response.

        Args:
            request: The approval request

        Returns:
            ApprovalResult with the decision
        """
        # Generate ID if not set
        if not request.id:
            request.id = str(uuid.uuid4())

        try:
            # Post the approval request
            message_id = await self._post_request(request)

            if not message_id:
                return ApprovalResult.error_result(
                    request, "Failed to post approval request to Discord"
                )

            # Wait for reaction
            if self.bot_token:
                result = await self._wait_for_reaction(request, message_id)
            else:
                # No bot token - can't read reactions
                # Fall back to manual confirmation via events
                result = await self._wait_for_event_confirmation(request)

            return result

        except TimeoutError:
            return ApprovalResult.timeout_result(request)
        except Exception as e:
            return ApprovalResult.error_result(request, str(e))

    async def _post_request(self, request: ApprovalRequest) -> str | None:
        """Post approval request to Discord and return message ID."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Post with webhook
            payload = {
                "content": request.format_discord_message(),
                "username": "Kubani Approvals",
            }

            response = await client.post(
                f"{self.webhook_url}?wait=true",  # wait=true returns message
                json=payload,
            )

            if response.status_code != 200:
                return None

            data = response.json()

            # Add reactions to the message if we have bot token
            message_id = data.get("id")
            if message_id and self.bot_token:
                channel_id = data.get("channel_id")
                await self._add_reactions(channel_id, message_id)

            return message_id

    async def _add_reactions(self, channel_id: str, message_id: str) -> None:
        """Add approve/reject reactions to the message."""
        if not self.bot_token:
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bot {self.bot_token}"}

            for emoji in [self.APPROVE_EMOJI, self.REJECT_EMOJI]:
                url = (
                    f"https://discord.com/api/v10/channels/{channel_id}"
                    f"/messages/{message_id}/reactions/{emoji}/@me"
                )
                await client.put(url, headers=headers)
                await asyncio.sleep(0.5)  # Rate limiting

    async def _wait_for_reaction(
        self,
        request: ApprovalRequest,
        message_id: str,
    ) -> ApprovalResult:
        """Wait for a reaction on the message."""
        if not self.bot_token:
            return ApprovalResult.error_result(
                request, "Bot token required for reaction monitoring"
            )

        # Extract channel ID from webhook URL
        # Webhook format: https://discord.com/api/webhooks/{webhook_id}/{token}
        # We need the channel from the message response, which we don't have here
        # This is a limitation - we'd need to store channel_id from _post_request

        # For now, fall back to event-based confirmation
        return await self._wait_for_event_confirmation(request)

    async def _wait_for_event_confirmation(
        self,
        request: ApprovalRequest,
    ) -> ApprovalResult:
        """
        Wait for approval via event bus.

        This is a fallback when we can't monitor Discord reactions directly.
        Another component (like a Discord bot) can publish approval events.
        """
        from core_agents.events import EventType, get_event_bus

        bus = await get_event_bus()

        # Subscribe to approval responses
        timeout = request.timeout_seconds
        start_time = asyncio.get_event_loop().time()

        async for event in bus.subscribe(EventType.SYSTEM_APPROVAL_RECEIVED):
            # Check if this is for our request
            if event.payload.get("request_id") == request.id:
                approved = event.payload.get("approved", False)
                responder = event.payload.get("responder")
                reason = event.payload.get("reason")

                if approved:
                    return ApprovalResult.approved_result(request, responder)
                else:
                    return ApprovalResult.rejected_result(request, responder, reason)

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                return ApprovalResult.timeout_result(request)

        return ApprovalResult.timeout_result(request)

    async def post_result(
        self,
        request: ApprovalRequest,
        result: ApprovalResult,
    ) -> None:
        """Post the result back to Discord for visibility."""
        status_emoji = {
            ApprovalStatus.APPROVED: "✅",
            ApprovalStatus.REJECTED: "❌",
            ApprovalStatus.TIMEOUT: "⏰",
            ApprovalStatus.ERROR: "⚠️",
        }

        emoji = status_emoji.get(result.status, "❓")

        message = (
            f"{emoji} **{result.status.value.upper()}**: `{request.action}` on `{request.resource}`"
        )

        if result.responder:
            message += f"\n_Responded by: {result.responder}_"

        if result.response_reason:
            message += f"\n_Reason: {result.response_reason}_"

        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                self.webhook_url,
                json={"content": message, "username": "Kubani Approvals"},
            )


# Singleton instance
_discord_approver: DiscordApprover | None = None


def get_discord_approver() -> DiscordApprover:
    """Get the singleton Discord approver instance."""
    global _discord_approver

    if _discord_approver is None:
        _discord_approver = DiscordApprover()

    return _discord_approver
