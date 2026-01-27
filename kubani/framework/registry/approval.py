"""Human approval workflow for skill promotion via Discord."""

import logging
from typing import Any

from kubani.framework.config import get_config

logger = logging.getLogger(__name__)


class ApprovalWorkflow:
    """
    Manages human approval workflow for skill promotions.

    Posts approval requests to Discord and waits for reactions.
    """

    APPROVE_EMOJI = "\u2705"  # ✅
    REJECT_EMOJI = "\u274c"  # ❌
    REVISION_EMOJI = "\U0001f504"  # 🔄

    def __init__(self, discord_mcp_client: Any = None):
        """
        Initialize the approval workflow.

        Args:
            discord_mcp_client: MCP client for Discord operations
        """
        self.config = get_config()
        self.discord = discord_mcp_client
        self.approval_channel = self.config.discord.approvals_channel or "skill-approvals"

    async def request_approval(
        self,
        skill_name: str,
        version: str,
        created_by: str,
        description: str,
        changelog: str | None = None,
        evaluation_results: dict | None = None,
    ) -> str:
        """
        Post an approval request to Discord.

        Args:
            skill_name: Name of the skill
            version: Version to approve
            created_by: Agent or user that created it
            description: Skill description
            changelog: What changed in this version
            evaluation_results: Optional evaluation summary

        Returns:
            Message ID for tracking
        """
        if self.discord is None:
            logger.warning("Discord MCP client not configured, skipping approval request")
            return "no-discord"

        # Build embed
        embed = {
            "title": f"\U0001f195 Skill Approval: {skill_name}:{version}",  # 🆕
            "description": description,
            "color": 0x5865F2,  # Discord blurple
            "fields": [
                {"name": "Created By", "value": created_by, "inline": True},
                {"name": "Version", "value": version, "inline": True},
                {"name": "Status", "value": "Pending Approval", "inline": True},
            ],
            "footer": {
                "text": f"React with {self.APPROVE_EMOJI} to approve, "
                f"{self.REJECT_EMOJI} to reject, {self.REVISION_EMOJI} for revisions"
            },
        }

        if changelog:
            embed["fields"].append({"name": "Changelog", "value": changelog, "inline": False})

        if evaluation_results:
            eval_summary = f"Accuracy: {evaluation_results.get('accuracy', 'N/A')}\n"
            eval_summary += (
                f"Tests: {evaluation_results.get('passed', 0)}/{evaluation_results.get('total', 0)}"
            )
            embed["fields"].append({"name": "Evaluation", "value": eval_summary, "inline": False})

        # Send to Discord
        result = await self.discord.send_message_to_channel_name(
            channel_name=self.approval_channel,
            embed=embed,
        )

        message_id = result.get("id", "unknown")
        channel_id = result.get("channel_id")

        # Add reaction options
        if channel_id:
            await self.discord.add_reaction(
                channel_id=channel_id,
                message_id=message_id,
                emoji=self.APPROVE_EMOJI,
            )
            await self.discord.add_reaction(
                channel_id=channel_id,
                message_id=message_id,
                emoji=self.REJECT_EMOJI,
            )
            await self.discord.add_reaction(
                channel_id=channel_id,
                message_id=message_id,
                emoji=self.REVISION_EMOJI,
            )

        logger.info(
            f"Posted approval request for {skill_name}:{version} (message_id: {message_id})"
        )
        return message_id

    async def wait_for_decision(
        self,
        channel_id: str,
        message_id: str,
        timeout_seconds: int = 86400,  # 24 hours
    ) -> str:
        """
        Wait for a human decision on an approval request.

        Args:
            channel_id: Discord channel ID
            message_id: Message ID of the approval request
            timeout_seconds: How long to wait

        Returns:
            Decision: "approved", "rejected", "revision", or "timeout"
        """
        if self.discord is None:
            return "no-discord"

        result = await self.discord.await_reaction(
            channel_id=channel_id,
            message_id=message_id,
            valid_emojis=[self.APPROVE_EMOJI, self.REJECT_EMOJI, self.REVISION_EMOJI],
            timeout_seconds=timeout_seconds,
        )

        if result is None:
            return "timeout"

        emoji = result.get("emoji", {}).get("name")

        if emoji == self.APPROVE_EMOJI:
            return "approved"
        elif emoji == self.REJECT_EMOJI:
            return "rejected"
        elif emoji == self.REVISION_EMOJI:
            return "revision"
        else:
            return "unknown"

    async def update_status(
        self,
        channel_id: str,
        message_id: str,
        new_status: str,
        by_user: str | None = None,
    ):
        """Update the approval request with a new status."""
        if self.discord is None:
            return

        status_text = {
            "approved": "\u2705 Approved",  # ✅
            "rejected": "\u274c Rejected",  # ❌
            "revision": "\U0001f504 Revision Requested",  # 🔄
            "promoted": "\U0001f680 Promoted to Production",  # 🚀
        }.get(new_status, new_status)

        reply_content = f"**Status Update:** {status_text}"
        if by_user:
            reply_content += f" by {by_user}"

        # Note: Discord MCP doesn't have edit_message, so we send a reply
        await self.discord.send_message(
            channel_id=channel_id,
            content=reply_content,
        )
