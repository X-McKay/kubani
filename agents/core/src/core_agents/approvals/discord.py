"""
Discord-based approval flow using MCP.

Posts approval requests to Discord and uses await_reaction for responses.
This provides a clean, reliable approval mechanism without polling.
"""

import asyncio
import logging
import os
import uuid

from core_agents.approvals.schema import (
    ApprovalRequest,
    ApprovalResult,
    Approver,
)
from core_agents.integrations.discord_mcp import (
    add_reaction,
    await_reaction,
    is_mcp_discord_configured,
    send_discord_message,
)

logger = logging.getLogger(__name__)


class DiscordApprover(Approver):
    """
    Discord-based approval mechanism using MCP.

    Posts approval requests to a Discord channel and uses the
    await_reaction MCP tool to wait for human responses.
    """

    APPROVE_EMOJI = "✅"
    REJECT_EMOJI = "❌"

    def __init__(
        self,
        channel_name: str | None = None,
    ):
        """
        Initialize the Discord approver.

        Args:
            channel_name: Channel for approval requests (default: from env or kubani-alerts)
        """
        self.channel_name = channel_name or os.getenv(
            "DISCORD_APPROVAL_CHANNEL",
            os.getenv("DISCORD_CHANNEL", "kubani-alerts"),
        )

    async def request_approval(
        self,
        request: ApprovalRequest,
    ) -> ApprovalResult:
        """
        Request approval via Discord using MCP.

        Posts message, adds reaction options, waits for user reaction.

        Args:
            request: The approval request to post

        Returns:
            ApprovalResult with the decision
        """
        # Ensure request has an ID
        if not request.id:
            request.id = str(uuid.uuid4())

        # Check configuration
        if not is_mcp_discord_configured():
            return ApprovalResult.error_result(
                request, "Discord MCP not configured (DISCORD_MCP_URL not set)"
            )

        try:
            # Step 1: Post the approval request
            logger.info(f"Posting approval request for {request.action} on {request.resource}")

            embed = self._build_approval_embed(request)
            message_id = await send_discord_message(
                embed=embed,
                channel_name=self.channel_name,
            )

            if not message_id:
                return ApprovalResult.error_result(
                    request, "Failed to post approval request to Discord"
                )

            logger.info(f"Posted approval request, message_id={message_id}")

            # Step 2: Add reaction options
            await add_reaction(self.channel_name, message_id, self.APPROVE_EMOJI)
            await asyncio.sleep(0.3)  # Rate limit buffer
            await add_reaction(self.channel_name, message_id, self.REJECT_EMOJI)

            # Step 3: Wait for reaction
            logger.info(f"Waiting for reaction (timeout={request.timeout_seconds}s)")

            result = await await_reaction(
                channel_name=self.channel_name,
                message_id=message_id,
                valid_emojis=[self.APPROVE_EMOJI, self.REJECT_EMOJI],
                timeout_seconds=float(request.timeout_seconds),
            )

            # Step 4: Process result
            if result is None:
                logger.info(f"Approval request timed out after {request.timeout_seconds}s")
                await self._post_result_notification(request, "timeout", None)
                return ApprovalResult.timeout_result(request)

            emoji, user = result
            logger.info(f"Received reaction {emoji} from {user}")

            if emoji == self.APPROVE_EMOJI:
                await self._post_result_notification(request, "approved", user)
                return ApprovalResult.approved_result(request, user)
            else:
                await self._post_result_notification(request, "rejected", user)
                return ApprovalResult.rejected_result(request, user)

        except Exception as e:
            logger.error(f"Error during approval request: {e}")
            return ApprovalResult.error_result(request, str(e))

    def _build_approval_embed(self, request: ApprovalRequest) -> dict:
        """Build a Discord embed for the approval request."""
        fields = [
            {"name": "Action", "value": f"`{request.action}`", "inline": False},
            {"name": "Resource", "value": f"`{request.resource}`", "inline": True},
        ]

        if request.skill_id:
            fields.append({"name": "Skill", "value": f"`{request.skill_id}`", "inline": True})

        fields.append({"name": "Agent", "value": f"`{request.agent}`", "inline": True})
        fields.append({"name": "Reason", "value": request.reason, "inline": False})

        # Add context if present
        if request.context:
            context_lines = [f"• **{k}:** `{v}`" for k, v in request.context.items()]
            fields.append(
                {
                    "name": "Context",
                    "value": "\n".join(context_lines[:5]),  # Limit to 5 items
                    "inline": False,
                }
            )

        return {
            "title": "🔐 Approval Required",
            "description": f"A potentially dangerous action requires human approval.\n\n_Expires in {request.timeout_seconds // 60} minutes_",
            "color": 16753920,  # Orange - attention required
            "fields": fields,
            "footer": {"text": "React with ✅ to approve or ❌ to reject"},
        }

    async def _post_result_notification(
        self,
        request: ApprovalRequest,
        status: str,
        responder: str | None,
    ) -> None:
        """Post a follow-up message with the result."""
        status_config = {
            "approved": ("✅", "APPROVED", 0x57F287),
            "rejected": ("❌", "REJECTED", 0xED4245),
            "timeout": ("⏰", "TIMED OUT", 0x99AAB5),
        }

        emoji, label, color = status_config.get(status, ("❓", "UNKNOWN", 0x99AAB5))

        content_parts = [
            f"{emoji} **{label}**: `{request.action}` on `{request.resource}`",
        ]

        if responder:
            content_parts.append(f"_Responded by: {responder}_")

        try:
            await send_discord_message(
                content="\n".join(content_parts),
                channel_name=self.channel_name,
            )
        except Exception as e:
            logger.warning(f"Failed to post result notification: {e}")


# Singleton instance
_discord_approver: DiscordApprover | None = None


def get_discord_approver() -> DiscordApprover:
    """Get the singleton Discord approver instance."""
    global _discord_approver

    if _discord_approver is None:
        _discord_approver = DiscordApprover()

    return _discord_approver


async def request_discord_approval(request: ApprovalRequest) -> ApprovalResult:
    """
    Convenience function to request approval via Discord.

    Args:
        request: The approval request

    Returns:
        ApprovalResult with the decision
    """
    approver = get_discord_approver()
    return await approver.request_approval(request)
