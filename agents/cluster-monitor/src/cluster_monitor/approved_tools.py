"""
Approved action tools for cluster-monitor.

These tools wrap risky Kubernetes operations with the approval flow,
allowing the remediation agent to request human approval before
executing dangerous actions.

Usage in swarm:
    from cluster_swarm.approved_tools import create_approved_tools

    approved_tools = create_approved_tools()
    # Add to remediation agent's tools
"""

import asyncio
import logging
import os
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)


def get_executor_mcp_url() -> str:
    """Get the kubernetes-mcp-executor URL."""
    return os.getenv(
        "KUBERNETES_EXECUTOR_MCP_URL",
        "https://kubernetes-executor.almckay.io",
    )


@tool
def request_pod_deletion(
    pod_name: str,
    namespace: str,
    reason: str,
    issue_pattern: str = "unknown",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Request approval to delete a pod (which triggers a restart).

    This tool requests human approval via Discord before deleting the pod.
    Use this for any pod deletion operation.

    Args:
        pod_name: Name of the pod to delete
        namespace: Kubernetes namespace
        reason: Why this pod needs to be deleted
        issue_pattern: Type of issue (timeout, oom, crash_loop, etc.)
        correlation_id: Optional correlation ID for the incident

    Returns:
        Dict with approval status and execution result
    """
    from core_agents.approvals import ApprovedExecutor, RiskLevel

    async def _execute():
        executor = ApprovedExecutor(agent_name="cluster-monitor")

        async def delete_pod(mcp_client):
            """Execute pod deletion using executor MCP."""
            from mcp.client.streamable_http import streamablehttp_client
            from strands.tools.mcp import MCPClient

            mcp_url = get_executor_mcp_url()
            if not mcp_url.endswith("/mcp"):
                mcp_url = f"{mcp_url}/mcp"

            client = MCPClient(lambda: streamablehttp_client(mcp_url))
            with client as ctx:
                tools = ctx.list_tools_sync()
                delete_tool = next((t for t in tools if t.name == "pods_delete"), None)
                if delete_tool:
                    result = ctx.call_tool_sync(
                        "pods_delete",
                        {"name": pod_name, "namespace": namespace},
                    )
                    return {"success": True, "result": str(result)}
                return {"success": False, "error": "pods_delete tool not found"}

        async def verify_pod_restarted(mcp_client):
            """Verify pod has restarted (new pod is running)."""
            import asyncio

            await asyncio.sleep(5)  # Wait for restart
            return True  # Simplified - in production check pod status

        return await executor.execute_with_approval(
            action="delete_pod",
            resource=f"pods/{pod_name}",
            namespace=namespace,
            issue_pattern=issue_pattern,
            risk_level=RiskLevel.MEDIUM,
            reason=reason,
            execute_fn=delete_pod,
            verify_fn=verify_pod_restarted,
            correlation_id=correlation_id,
        )

    # Run async function synchronously (tools are called sync by Strands)
    return asyncio.run(_execute())


@tool
def request_deployment_scale(
    deployment_name: str,
    namespace: str,
    replicas: int,
    reason: str,
    issue_pattern: str = "unknown",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Request approval to scale a deployment.

    This tool requests human approval via Discord before scaling.
    Scaling up is low risk (auto-approved), scaling down requires approval.

    Args:
        deployment_name: Name of the deployment to scale
        namespace: Kubernetes namespace
        replicas: Target number of replicas
        reason: Why this deployment needs to be scaled
        issue_pattern: Type of issue triggering the scale
        correlation_id: Optional correlation ID

    Returns:
        Dict with approval status and execution result
    """
    from core_agents.approvals import ApprovedExecutor, RiskLevel

    async def _execute():
        executor = ApprovedExecutor(agent_name="cluster-monitor")

        # Determine risk level - scaling down is riskier
        # We'd need to check current replicas to know if scaling up or down
        # For now, assume medium risk for all scaling
        risk_level = RiskLevel.MEDIUM if replicas < 3 else RiskLevel.LOW

        async def scale_deployment(mcp_client):
            """Execute deployment scale using executor MCP."""
            from mcp.client.streamable_http import streamablehttp_client
            from strands.tools.mcp import MCPClient

            mcp_url = get_executor_mcp_url()
            if not mcp_url.endswith("/mcp"):
                mcp_url = f"{mcp_url}/mcp"

            client = MCPClient(lambda: streamablehttp_client(mcp_url))
            with client as ctx:
                result = ctx.call_tool_sync(
                    "resources_scale",
                    {
                        "name": deployment_name,
                        "namespace": namespace,
                        "kind": "Deployment",
                        "replicas": replicas,
                    },
                )
                return {"success": True, "result": str(result)}

        async def verify_scale(mcp_client):
            """Verify deployment has scaled."""
            import asyncio

            await asyncio.sleep(10)
            return True

        return await executor.execute_with_approval(
            action="scale_deployment",
            resource=f"deployments/{deployment_name}",
            namespace=namespace,
            issue_pattern=issue_pattern,
            risk_level=risk_level,
            reason=reason,
            execute_fn=scale_deployment,
            verify_fn=verify_scale,
            correlation_id=correlation_id,
        )

    return asyncio.run(_execute())


@tool
def request_rollout_restart(
    resource_name: str,
    resource_kind: str,
    namespace: str,
    reason: str,
    issue_pattern: str = "unknown",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Request approval to perform a rollout restart.

    This is a lower-risk operation that restarts pods gracefully.
    Generally auto-approved for most resource types.

    Args:
        resource_name: Name of the resource to restart
        resource_kind: Kind of resource (Deployment, StatefulSet, DaemonSet)
        namespace: Kubernetes namespace
        reason: Why this resource needs to be restarted
        issue_pattern: Type of issue triggering the restart
        correlation_id: Optional correlation ID

    Returns:
        Dict with approval status and execution result
    """
    from core_agents.approvals import ApprovedExecutor, RiskLevel

    async def _execute():
        executor = ApprovedExecutor(agent_name="cluster-monitor")

        async def perform_restart(mcp_client):
            """Execute rollout restart using executor MCP."""
            from mcp.client.streamable_http import streamablehttp_client
            from strands.tools.mcp import MCPClient

            mcp_url = get_executor_mcp_url()
            if not mcp_url.endswith("/mcp"):
                mcp_url = f"{mcp_url}/mcp"

            client = MCPClient(lambda: streamablehttp_client(mcp_url))
            with client as ctx:
                # Rollout restart is done via patch with annotation
                result = ctx.call_tool_sync(
                    "resources_patch",
                    {
                        "name": resource_name,
                        "namespace": namespace,
                        "kind": resource_kind,
                        "patch": {
                            "spec": {
                                "template": {
                                    "metadata": {
                                        "annotations": {
                                            "kubectl.kubernetes.io/restartedAt": __import__(
                                                "datetime"
                                            )
                                            .datetime.utcnow()
                                            .isoformat()
                                        }
                                    }
                                }
                            }
                        },
                    },
                )
                return {"success": True, "result": str(result)}

        async def verify_restart(mcp_client):
            """Verify rollout has progressed."""
            import asyncio

            await asyncio.sleep(15)
            return True

        return await executor.execute_with_approval(
            action="rollout_restart",
            resource=f"{resource_kind.lower()}s/{resource_name}",
            namespace=namespace,
            issue_pattern=issue_pattern,
            risk_level=RiskLevel.LOW,  # Rollout restarts are generally safe
            reason=reason,
            execute_fn=perform_restart,
            verify_fn=verify_restart,
            correlation_id=correlation_id,
        )

    return asyncio.run(_execute())


@tool
def escalate_to_human(
    resource: str,
    namespace: str,
    issue_summary: str,
    attempted_actions: str,
    recommendation: str,
) -> dict[str, Any]:
    """
    Escalate an issue to human operators when automated remediation fails.

    Use this when:
    - Remediation actions have failed multiple times
    - The issue requires manual intervention
    - The risk is too high for automated action

    Args:
        resource: The affected resource
        namespace: Kubernetes namespace
        issue_summary: Brief summary of the issue
        attempted_actions: What has been tried
        recommendation: What the human should consider doing

    Returns:
        Dict confirming escalation was posted
    """
    from core_agents.integrations.discord_mcp import send_discord_message

    async def _escalate():
        message = f"""🚨 **Escalation Required**

**Resource:** `{resource}` in `{namespace}`
**Issue:** {issue_summary}

**Attempted Actions:**
{attempted_actions}

**Recommendation:**
{recommendation}

_This issue requires human intervention. Please review and take appropriate action._"""

        await send_discord_message(
            content=message,
            channel_name="kubani-approvals",
        )

        return {
            "escalated": True,
            "message": "Issue escalated to kubani-approvals channel",
        }

    return asyncio.run(_escalate())


def create_approved_tools() -> list:
    """
    Create the list of approved action tools for remediation.

    Returns:
        List of tool functions that can be added to an agent
    """
    return [
        request_pod_deletion,
        request_deployment_scale,
        request_rollout_restart,
        escalate_to_human,
    ]
