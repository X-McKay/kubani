"""
Approval flow for human-in-the-loop decisions.

Provides a Discord-based approval mechanism where agents can request
human approval before executing dangerous actions, with learning integration.

Example - Simple approval:
    from core_agents.approvals import DiscordApprover, ApprovalRequest

    approver = DiscordApprover()
    request = ApprovalRequest(
        action="drain_node",
        resource="node/worker-1",
        reason="Node has disk pressure",
    )
    result = await approver.request_approval(request)

Example - Approval with execution and learning:
    from core_agents.approvals import ApprovedExecutor, RiskLevel

    executor = ApprovedExecutor(agent_name="cluster-swarm")

    result = await executor.execute_with_approval(
        action="delete_pod",
        resource="pods/my-pod",
        namespace="monitoring",
        issue_pattern="timeout",
        risk_level=RiskLevel.MEDIUM,
        reason="Pod failing readiness probe",
        execute_fn=lambda client: client.call_tool("pods_delete", {...}),
        verify_fn=lambda client: check_pod_healthy(...),
    )
"""

from core_agents.approvals.discord import (
    DiscordApprover,
    get_discord_approver,
)
from core_agents.approvals.executor import (
    ApprovedExecutor,
    execute_with_approval,
)
from core_agents.approvals.learning import (
    ActionOutcome,
    ApprovalLearning,
    PastApprovalMatch,
    PastApprovalSummary,
    RiskLevel,
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
    # Executor
    "ApprovedExecutor",
    "execute_with_approval",
    # Learning
    "RiskLevel",
    "ActionOutcome",
    "ApprovalLearning",
    "PastApprovalMatch",
    "PastApprovalSummary",
]
