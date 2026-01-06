"""
Approval flow for human-in-the-loop decisions.

Provides a Discord-based approval mechanism where agents can request
human approval before executing dangerous actions.

Example:
    from core_agents.approvals import DiscordApprover, ApprovalRequest

    approver = DiscordApprover()

    request = ApprovalRequest(
        action="drain_node",
        resource="node/worker-1",
        reason="Node has disk pressure, need to drain for maintenance",
        skill_id="k8s-drain-node",
    )

    result = await approver.request_approval(request)
    if result.approved:
        # Proceed with action
        ...
"""

from core_agents.approvals.discord import (
    DiscordApprover,
    get_discord_approver,
)
from core_agents.approvals.schema import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    Approver,
)

__all__ = [
    # Schema
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalStatus",
    "Approver",
    # Discord
    "DiscordApprover",
    "get_discord_approver",
]
