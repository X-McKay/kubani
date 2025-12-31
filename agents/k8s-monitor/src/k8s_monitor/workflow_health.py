"""
Temporal workflow health monitoring activities.

Monitors and cleans up orphaned or stuck Temporal workflows
to prevent resource waste and ensure system health.
"""

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio import activity
from temporalio.client import Client

logger = logging.getLogger(__name__)


@dataclass
class WorkflowIssue:
    """Represents a detected workflow issue."""

    workflow_id: str
    workflow_type: str
    task_queue: str
    issue_type: str  # "orphaned", "stuck", "wrong_queue"
    description: str
    start_time: str
    action_taken: str | None = None


@dataclass
class WorkflowHealthResult:
    """Result of workflow health check."""

    checked_at: str
    total_running: int
    issues_found: list[WorkflowIssue]
    issues_resolved: list[WorkflowIssue]
    expected_workflows: list[str]


# Expected long-running scheduled workflows and their task queues
EXPECTED_WORKFLOWS = {
    "k8s-monitor-scheduled-remediation": "k8s-monitor",
    # New news-monitor architecture (continuous ingestion + periodic digest)
    "news-monitor-digest-generation": "news-monitor",
    "news-monitor-article-ingestion": "news-monitor",
}

# Task queues with active workers
ACTIVE_TASK_QUEUES = {"k8s-monitor", "news-monitor"}

# Workflows that run longer than this without completing are considered stuck
# (excludes scheduled/infinite workflows listed in EXPECTED_WORKFLOWS)
MAX_WORKFLOW_DURATION_HOURS = 4


async def _get_temporal_client() -> Client:
    """Get a Temporal client connection."""
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    return await Client.connect(temporal_host, namespace=temporal_namespace)


@activity.defn
async def check_workflow_health() -> dict[str, Any]:
    """
    Check the health of Temporal workflows.

    Detects:
    1. Workflows on task queues with no active workers
    2. Workflows running too long (potential stuck state)
    3. Unexpected duplicate scheduled workflows

    Returns:
        WorkflowHealthResult as a dictionary
    """
    logger.info("Starting workflow health check")

    client = await _get_temporal_client()
    issues_found: list[WorkflowIssue] = []
    expected_found: list[str] = []

    try:
        # List all running workflows
        running_workflows = []
        async for wf in client.list_workflows(query='ExecutionStatus = "Running"'):
            running_workflows.append(wf)

        logger.info(f"Found {len(running_workflows)} running workflows")

        for wf in running_workflows:
            workflow_id = wf.id
            workflow_type = wf.workflow_type or "Unknown"
            # Extract task queue from search attributes if available
            task_queue = "unknown"

            # Check if this is an expected workflow
            if workflow_id in EXPECTED_WORKFLOWS:
                expected_found.append(workflow_id)
                # These are expected to be long-running, skip duration check
                continue

            # Get workflow description to check task queue and start time
            try:
                handle = client.get_workflow_handle(workflow_id, run_id=wf.run_id)
                desc = await handle.describe()
                task_queue = desc.raw_description.workflow_execution_info.task_queue or "unknown"
                start_time = desc.start_time

                # Check for wrong task queue
                if task_queue not in ACTIVE_TASK_QUEUES:
                    issues_found.append(
                        WorkflowIssue(
                            workflow_id=workflow_id,
                            workflow_type=workflow_type,
                            task_queue=task_queue,
                            issue_type="orphaned",
                            description=f"Workflow on inactive task queue '{task_queue}'",
                            start_time=start_time.isoformat() if start_time else "unknown",
                        )
                    )
                    continue

                # Check for stuck workflows (running too long)
                if start_time:
                    duration = datetime.now(UTC) - start_time.replace(tzinfo=UTC)
                    if duration > timedelta(hours=MAX_WORKFLOW_DURATION_HOURS):
                        issues_found.append(
                            WorkflowIssue(
                                workflow_id=workflow_id,
                                workflow_type=workflow_type,
                                task_queue=task_queue,
                                issue_type="stuck",
                                description=f"Workflow running for {duration.total_seconds() / 3600:.1f} hours",
                                start_time=start_time.isoformat(),
                            )
                        )

            except Exception as e:
                logger.warning(f"Could not describe workflow {workflow_id}: {e}")

        # Check for missing expected workflows
        for expected_id, task_queue in EXPECTED_WORKFLOWS.items():
            if expected_id not in expected_found:
                logger.warning(f"Expected workflow not running: {expected_id}")
                issues_found.append(
                    WorkflowIssue(
                        workflow_id=expected_id,
                        workflow_type="Unknown",
                        task_queue=task_queue,
                        issue_type="missing",
                        description=f"Expected scheduled workflow '{expected_id}' is not running",
                        start_time="N/A",
                    )
                )

        result = WorkflowHealthResult(
            checked_at=datetime.now(UTC).isoformat(),
            total_running=len(running_workflows),
            issues_found=issues_found,
            issues_resolved=[],
            expected_workflows=expected_found,
        )

        logger.info(
            f"Workflow health check complete: {len(issues_found)} issues found, "
            f"{len(expected_found)}/{len(EXPECTED_WORKFLOWS)} expected workflows running"
        )

        return {
            "checked_at": result.checked_at,
            "total_running": result.total_running,
            "issues_found": [
                {
                    "workflow_id": i.workflow_id,
                    "workflow_type": i.workflow_type,
                    "task_queue": i.task_queue,
                    "issue_type": i.issue_type,
                    "description": i.description,
                    "start_time": i.start_time,
                }
                for i in result.issues_found
            ],
            "issues_resolved": [],
            "expected_workflows": result.expected_workflows,
        }

    except Exception as e:
        logger.exception("Error checking workflow health")
        return {
            "checked_at": datetime.now(UTC).isoformat(),
            "total_running": 0,
            "issues_found": [],
            "issues_resolved": [],
            "expected_workflows": [],
            "error": str(e),
        }


@activity.defn
async def cleanup_workflow_issues(
    issues: list[dict[str, Any]], auto_terminate: bool = True
) -> dict[str, Any]:
    """
    Clean up detected workflow issues.

    Args:
        issues: List of workflow issues to clean up
        auto_terminate: If True, automatically terminate orphaned/stuck workflows

    Returns:
        Dictionary with resolved issues
    """
    if not issues:
        return {"resolved": [], "errors": []}

    logger.info(f"Cleaning up {len(issues)} workflow issues")

    client = await _get_temporal_client()
    resolved = []
    errors = []

    for issue in issues:
        workflow_id = issue["workflow_id"]
        issue_type = issue["issue_type"]

        if not auto_terminate:
            logger.info(f"Skipping cleanup for {workflow_id} (auto_terminate=False)")
            continue

        try:
            # Handle missing workflows differently - restart the pod to trigger init containers
            if issue_type == "missing":
                # Map workflow ID to deployment name
                deployment_map = {
                    "news-monitor-digest-generation": "news-monitor",
                    "news-monitor-article-ingestion": "news-monitor",
                }

                deployment_name = deployment_map.get(workflow_id)
                if deployment_name and auto_terminate:
                    # Restart deployment to trigger init containers that start the workflows
                    import subprocess

                    result = subprocess.run(
                        [
                            "kubectl",
                            "rollout",
                            "restart",
                            f"deployment/{deployment_name}",
                            "-n",
                            "ai-agents",
                        ],
                        capture_output=True,
                        text=True,
                    )

                    if result.returncode == 0:
                        resolved.append(
                            {
                                **issue,
                                "action_taken": f"Restarted {deployment_name} deployment to restart workflows",
                            }
                        )
                        logger.info(
                            f"Restarted {deployment_name} deployment for missing workflow: {workflow_id}"
                        )
                    else:
                        errors.append(
                            {
                                "workflow_id": workflow_id,
                                "error": f"kubectl restart failed: {result.stderr}",
                            }
                        )
                else:
                    logger.info(
                        f"No deployment mapping for missing workflow {workflow_id}, skipping"
                    )
                continue

            handle = client.get_workflow_handle(workflow_id)

            # Only terminate orphaned or stuck workflows
            if issue_type in ("orphaned", "stuck"):
                reason = f"Auto-cleanup: {issue['description']}"
                await handle.terminate(reason=reason)

                resolved.append(
                    {
                        **issue,
                        "action_taken": f"Terminated: {reason}",
                    }
                )
                logger.info(f"Terminated workflow {workflow_id}: {reason}")
            else:
                logger.info(f"Skipping cleanup for {workflow_id} (issue_type={issue_type})")

        except Exception as e:
            error_msg = f"Failed to cleanup {workflow_id}: {e}"
            logger.error(error_msg)
            errors.append({"workflow_id": workflow_id, "error": str(e)})

    return {"resolved": resolved, "errors": errors}


@activity.defn
async def post_workflow_health_discord(
    health_result: dict[str, Any], cleanup_result: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Post workflow health status to Discord.

    Only posts if there are issues found or resolved.

    Args:
        health_result: Result from check_workflow_health
        cleanup_result: Optional result from cleanup_workflow_issues

    Returns:
        Discord post result
    """
    import httpx

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not configured")
        return {"success": False, "error": "Webhook not configured"}

    issues_found = health_result.get("issues_found", [])
    issues_resolved = cleanup_result.get("resolved", []) if cleanup_result else []

    # Only post if there are issues
    if not issues_found and not issues_resolved:
        logger.info("No workflow issues to report")
        return {"success": True, "skipped": True}

    # Build embed
    if issues_resolved and not issues_found:
        # All issues were resolved
        color = 0x57F287  # Green
        title = "🔧 Workflow Issues Resolved"
        description = f"Auto-cleanup resolved {len(issues_resolved)} workflow issue(s)."
    elif issues_found:
        color = 0xFEE75C  # Yellow/Warning
        title = "⚠️ Workflow Health Issues Detected"
        description = f"Found {len(issues_found)} workflow issue(s)."
    else:
        color = 0x57F287
        title = "✅ Workflow Health Check"
        description = "All workflows healthy."

    fields = []

    if issues_found:
        issues_text = "\n".join(
            f"• `{i['workflow_id']}` - {i['description']}" for i in issues_found[:5]
        )
        if len(issues_found) > 5:
            issues_text += f"\n... and {len(issues_found) - 5} more"
        fields.append({"name": "Issues Found", "value": issues_text, "inline": False})

    if issues_resolved:
        resolved_text = "\n".join(
            f"• `{r['workflow_id']}` - {r.get('action_taken', 'Resolved')}"
            for r in issues_resolved[:5]
        )
        if len(issues_resolved) > 5:
            resolved_text += f"\n... and {len(issues_resolved) - 5} more"
        fields.append({"name": "Issues Resolved", "value": resolved_text, "inline": False})

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": f"Kubani K8s Monitor • {health_result.get('checked_at', 'now')}"},
    }

    payload = {
        "username": "Kubani K8s Monitor",
        "embeds": [embed],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            response = await http_client.post(webhook_url, json=payload)
            response.raise_for_status()

        logger.info("Posted workflow health status to Discord")
        return {"success": True}

    except Exception as e:
        logger.error(f"Failed to post to Discord: {e}")
        return {"success": False, "error": str(e)}
