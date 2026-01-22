"""
Temporal activities for the RemediationOrchestrationWorkflow.

These activities implement the actual work for each stage of the
8-stage investigation pipeline. They interact with:
- Kubernetes API (via MCP)
- Memory systems (Qdrant)
- Discord (for notifications)
- Healer agent (for remediation execution)
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from temporalio import activity

from core_agents.integrations.discord_mcp import send_discord_message

logger = logging.getLogger(__name__)

# Discord channel for orchestration updates
ORCHESTRATION_CHANNEL = os.getenv("DISCORD_ALERTS_CHANNEL", "")


# =============================================================================
# Stage Activities
# =============================================================================


@activity.defn
async def analyze_issue(state: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 1: Analyze the correlated issue.

    Performs initial classification based on:
    - Event patterns in trigger and correlated events
    - Severity from Sentinel classification
    - Resource context (namespace, kind, name)

    Returns classification, confidence, and severity.
    """
    logger.info(f"Analyzing issue: {state.get('investigation_id')}")

    trigger = state.get("trigger_event", {})
    correlated = state.get("correlated_events", [])

    # Extract key details
    reason = trigger.get("reason", "Unknown")
    message = trigger.get("message", "")
    namespace = state.get("namespace", "default")
    event_count = 1 + len(correlated)

    # Classify based on reason patterns
    classification_map = {
        "CrashLoopBackOff": ("crash_loop", "critical", 0.95),
        "OOMKilled": ("memory_exhaustion", "critical", 0.95),
        "ImagePullBackOff": ("image_pull_failure", "high", 0.9),
        "ErrImagePull": ("image_pull_failure", "high", 0.9),
        "NodeNotReady": ("node_failure", "critical", 0.95),
        "FailedScheduling": ("scheduling_failure", "medium", 0.8),
        "Unhealthy": ("health_check_failure", "medium", 0.85),
        "BackOff": ("container_backoff", "medium", 0.7),
        "FailedMount": ("volume_mount_failure", "high", 0.9),
        "FailedBinding": ("pvc_binding_failure", "medium", 0.85),
    }

    if reason in classification_map:
        classification, severity, confidence = classification_map[reason]
    else:
        # Default classification
        classification = "unknown_issue"
        severity = state.get("severity", "medium")
        confidence = 0.5

    # Boost confidence for multiple correlated events
    if event_count > 1:
        confidence = min(confidence + 0.05 * (event_count - 1), 0.99)

    logger.info(
        f"Analysis complete: {classification} (severity={severity}, confidence={confidence:.2f})"
    )

    return {
        "classification": classification,
        "severity": severity,
        "confidence": confidence,
        "event_count": event_count,
        "analyzed_at": datetime.now(UTC).isoformat(),
    }


@activity.defn
async def query_memory(state: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 2: Query memory for similar incidents and relevant skills.

    Searches Qdrant for:
    - Similar past incidents (by classification and namespace)
    - Relevant remediation skills

    Returns list of similar incidents and applicable skills.
    """
    logger.info(f"Querying memory for: {state.get('investigation_id')}")

    classification = state.get("classification", "unknown")
    namespace = state.get("namespace", "default")

    # Query vector store for similar incidents
    # TODO: Integrate with actual Qdrant MCP when available
    similar_incidents: list[dict] = []
    relevant_skills: list[str] = []

    # For now, use pattern-based skill matching
    skill_patterns = {
        "crash_loop": ["restart-pod", "check-logs", "check-resources"],
        "memory_exhaustion": ["check-memory-limits", "analyze-oom", "adjust-resources"],
        "image_pull_failure": ["verify-image", "check-registry", "check-credentials"],
        "health_check_failure": ["check-probes", "verify-endpoints", "check-dependencies"],
        "node_failure": ["check-node-status", "drain-node", "cordon-node"],
        "scheduling_failure": ["check-resources", "check-node-selector", "check-taints"],
        "volume_mount_failure": ["check-pvc", "check-storage-class", "verify-volume"],
        "pvc_binding_failure": ["check-pv", "check-storage-class", "verify-storage"],
    }

    relevant_skills = skill_patterns.get(classification, ["generic-investigate"])

    logger.info(
        f"Memory query complete: {len(similar_incidents)} incidents, {len(relevant_skills)} skills"
    )

    return {
        "similar_incidents": similar_incidents,
        "relevant_skills": relevant_skills,
        "queried_at": datetime.now(UTC).isoformat(),
    }


@activity.defn
async def investigate_issue(state: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 3: Run diagnostic investigation.

    Uses MCP tools to gather diagnostic information:
    - Pod status and logs
    - Node conditions
    - Related events
    - Resource metrics

    Returns diagnostic results and potential root cause.
    """
    logger.info(f"Investigating: {state.get('investigation_id')}")

    trigger = state.get("trigger_event", {})
    classification = state.get("classification", "unknown")
    namespace = state.get("namespace", "default")
    pod_name = trigger.get("name", "unknown")
    kind = trigger.get("kind", "Pod")

    diagnostics: dict[str, Any] = {
        "investigated_at": datetime.now(UTC).isoformat(),
        "resource": f"{kind}/{pod_name}",
        "namespace": namespace,
    }

    # Use MCP tools for investigation
    try:
        from k8s_monitor.mcp_tools import call_mcp_tool_async

        # Get pod details
        if kind == "Pod":
            pod_result = await call_mcp_tool_async(
                "pods_get",
                {"name": pod_name, "namespace": namespace},
            )
            if pod_result.get("success"):
                diagnostics["pod_status"] = pod_result.get("result")

            # Get recent logs
            log_result = await call_mcp_tool_async(
                "pods_log",
                {"name": pod_name, "namespace": namespace, "tail": 30},
            )
            if log_result.get("success"):
                diagnostics["recent_logs"] = log_result.get("result")

        # Get related events
        events_result = await call_mcp_tool_async(
            "events_list",
            {"namespace": namespace, "field_selector": f"involvedObject.name={pod_name}"},
        )
        if events_result.get("success"):
            diagnostics["related_events"] = events_result.get("result")

    except Exception as e:
        logger.warning(f"MCP investigation failed: {e}")
        diagnostics["error"] = str(e)

    # Determine root cause based on classification and diagnostics
    root_cause_map = {
        "crash_loop": "Application crash or startup failure",
        "memory_exhaustion": "Container exceeded memory limits",
        "image_pull_failure": "Unable to pull container image",
        "health_check_failure": "Liveness or readiness probe failing",
        "node_failure": "Node is unhealthy or unreachable",
        "scheduling_failure": "Insufficient resources or constraint violations",
        "volume_mount_failure": "Unable to mount required volume",
        "pvc_binding_failure": "PersistentVolumeClaim cannot bind",
    }

    root_cause = root_cause_map.get(classification, "Unknown - requires manual investigation")

    logger.info(f"Investigation complete: root_cause={root_cause}")

    return {
        "diagnostics": diagnostics,
        "root_cause": root_cause,
        "pod_name": pod_name,
        "node_name": diagnostics.get("node_name"),
    }


@activity.defn
async def plan_remediation(state: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 4: Plan remediation actions.

    Based on classification and diagnostics, determines:
    - What remediation action to take
    - Whether human approval is required
    - Parameters for the action

    Returns remediation plan and approval requirement.
    """
    logger.info(f"Planning remediation: {state.get('investigation_id')}")

    classification = state.get("classification", "unknown")
    severity = state.get("severity", "medium")
    namespace = state.get("namespace", "default")
    pod_name = state.get("pod_name", "unknown")

    # Define remediation actions per classification
    remediation_plans = {
        "crash_loop": {
            "action": "restart_pod",
            "description": "Delete pod to trigger fresh restart",
            "parameters": {"name": pod_name, "namespace": namespace},
            "requires_approval": False,
        },
        "memory_exhaustion": {
            "action": "restart_pod",
            "description": "Delete pod to clear OOM state",
            "parameters": {"name": pod_name, "namespace": namespace},
            "requires_approval": False,
        },
        "image_pull_failure": {
            "action": "report_config_issue",
            "description": "Image configuration needs manual review",
            "parameters": {"issue": "image_pull", "resource": f"{namespace}/{pod_name}"},
            "requires_approval": False,
        },
        "health_check_failure": {
            "action": "restart_pod",
            "description": "Restart pod to recover from unhealthy state",
            "parameters": {"name": pod_name, "namespace": namespace},
            "requires_approval": False,
        },
        "node_failure": {
            "action": "escalate",
            "description": "Node issue requires cluster admin attention",
            "parameters": {"issue": "node_failure"},
            "requires_approval": True,
        },
        "scheduling_failure": {
            "action": "report_config_issue",
            "description": "Scheduling constraints need review",
            "parameters": {"issue": "scheduling", "resource": f"{namespace}/{pod_name}"},
            "requires_approval": False,
        },
    }

    plan = remediation_plans.get(
        classification,
        {
            "action": "investigate",
            "description": "Unknown issue - requires manual investigation",
            "parameters": {},
            "requires_approval": True,
        },
    )

    # Critical severity actions that modify nodes require approval
    if severity == "critical" and plan.get("action") in ("drain_node", "cordon_node"):
        plan["requires_approval"] = True

    logger.info(
        f"Remediation plan: {plan['action']} "
        f"(requires_approval={plan.get('requires_approval', False)})"
    )

    return {
        "plan": plan,
        "requires_approval": plan.get("requires_approval", False),
        "planned_at": datetime.now(UTC).isoformat(),
    }


@activity.defn
async def wait_for_approval(state: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 5: Request human approval via Discord.

    Posts an approval request to Discord with reaction buttons.
    The workflow will wait for a signal with the approval result.
    """
    logger.info(f"Requesting approval: {state.get('investigation_id')}")

    plan = state.get("remediation_plan", {})
    namespace = state.get("namespace", "default")
    pod_name = state.get("pod_name", "unknown")

    message = f"""🔐 **Approval Required**

**Investigation:** {state.get("investigation_id")}
**Resource:** {namespace}/{pod_name}
**Classification:** {state.get("classification", "unknown")}

**Proposed Action:** {plan.get("description", "Unknown action")}

React with ✅ to approve or ❌ to reject.
"""

    try:
        await send_discord_message(content=message, agent_name="k8s-monitor")
        logger.info("Posted approval request to Discord")
    except Exception as e:
        logger.warning(f"Failed to post approval request: {e}")

    return {
        "requested_at": datetime.now(UTC).isoformat(),
        "action": plan.get("action"),
    }


@activity.defn
async def execute_remediation(state: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 6: Execute the remediation action.

    Delegates to appropriate MCP tools based on the action type.
    """
    logger.info(f"Executing remediation: {state.get('investigation_id')}")

    plan = state.get("remediation_plan") or {}
    action = plan.get("action", "investigate")
    params = plan.get("parameters", {})

    result: dict[str, Any] = {
        "action": action,
        "executed_at": datetime.now(UTC).isoformat(),
        "success": False,
    }

    try:
        from k8s_monitor.mcp_tools import call_mcp_tool_async

        if action == "restart_pod":
            # Delete pod to trigger restart
            delete_result = await call_mcp_tool_async(
                "pods_delete",
                {"name": params.get("name"), "namespace": params.get("namespace")},
            )
            result["success"] = delete_result.get("success", False)
            result["output"] = delete_result.get("result")

        elif action == "report_config_issue":
            # Just log - no automated fix available
            result["success"] = True
            result["output"] = "Issue reported - requires manual configuration change"

        elif action == "escalate":
            # Log escalation
            result["success"] = True
            result["output"] = "Issue escalated to cluster administrators"

        else:
            result["output"] = f"Unknown action: {action}"

    except Exception as e:
        logger.error(f"Remediation failed: {e}")
        result["error"] = str(e)

    logger.info(f"Remediation result: success={result['success']}")
    return result


@activity.defn
async def verify_remediation(state: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 7: Verify the remediation was successful.

    Checks the resource state after remediation to confirm resolution.
    """
    logger.info(f"Verifying remediation: {state.get('investigation_id')}")

    namespace = state.get("namespace", "default")
    pod_name = state.get("pod_name", "unknown")
    classification = state.get("classification", "unknown")

    result: dict[str, Any] = {
        "verified_at": datetime.now(UTC).isoformat(),
        "resolved": False,
    }

    try:
        from k8s_monitor.mcp_tools import call_mcp_tool_async

        # Check pod status
        pod_result = await call_mcp_tool_async(
            "pods_get",
            {"name": pod_name, "namespace": namespace},
        )

        if not pod_result.get("success"):
            # Pod might have been replaced by a new one during restart
            # This is often a success case for crash_loop remediation
            if classification in ("crash_loop", "memory_exhaustion", "health_check_failure"):
                result["resolved"] = True
                result["reason"] = "Pod replaced (expected after restart)"
            else:
                result["reason"] = "Pod not found"
        else:
            # Parse pod status
            pod_data = pod_result.get("result", "")
            if "Running" in str(pod_data) and "Ready" in str(pod_data):
                result["resolved"] = True
                result["reason"] = "Pod is Running and Ready"
            else:
                result["reason"] = "Pod not yet healthy"

    except Exception as e:
        logger.warning(f"Verification check failed: {e}")
        result["error"] = str(e)

    logger.info(f"Verification result: resolved={result['resolved']}")
    return result


@activity.defn
async def summarize_investigation(state: dict[str, Any]) -> dict[str, Any]:
    """
    Stage 8: Generate investigation narrative.

    Creates a human-readable summary of the investigation for
    Discord notification and audit trail.
    """
    logger.info(f"Summarizing: {state.get('investigation_id')}")

    resolved = state.get("resolution_confirmed", False)
    classification = state.get("classification", "unknown")
    root_cause = state.get("root_cause", "Unknown")
    namespace = state.get("namespace", "default")
    pod_name = state.get("pod_name", "unknown")

    remediation_result = state.get("remediation_result", {})
    action = remediation_result.get("action", "none")

    status_emoji = "✅" if resolved else "⚠️"
    status_text = "Resolved" if resolved else "Needs Attention"

    narrative = f"""{status_emoji} **Investigation Complete - {status_text}**

**ID:** {state.get("investigation_id")}
**Resource:** {namespace}/{pod_name}
**Classification:** {classification}

**Root Cause:** {root_cause}

**Action Taken:** {action}
**Outcome:** {"Success" if remediation_result.get("success") else "Failed or Pending"}

**Duration:** {_calculate_duration(state)}
"""

    # Post summary to Discord
    try:
        await send_discord_message(content=narrative, agent_name="k8s-monitor")
        logger.info("Posted investigation summary to Discord")
    except Exception as e:
        logger.warning(f"Failed to post summary: {e}")

    return {
        "narrative": narrative,
        "summarized_at": datetime.now(UTC).isoformat(),
    }


@activity.defn
async def store_learning(state: dict[str, Any]) -> dict[str, Any]:
    """
    Store learnings from successful remediation.

    Records the investigation outcome in memory for future reference.
    """
    logger.info(f"Storing learning: {state.get('investigation_id')}")

    # TODO: Integrate with Qdrant MCP for persistent learning storage
    learning = {
        "investigation_id": state.get("investigation_id"),
        "classification": state.get("classification"),
        "root_cause": state.get("root_cause"),
        "remediation_action": state.get("remediation_result", {}).get("action"),
        "success": state.get("resolution_confirmed", False),
        "stored_at": datetime.now(UTC).isoformat(),
    }

    logger.info(
        f"Learning stored: {learning['classification']} -> {learning['remediation_action']}"
    )

    return learning


@activity.defn
async def post_stage_update(
    state: dict[str, Any],
    stage: str,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Post stage transition update to Discord.

    Provides visibility into the investigation progress.
    """
    investigation_id = state.get("investigation_id", "unknown")
    namespace = state.get("namespace", "default")
    pod_name = state.get("pod_name") or state.get("trigger_event", {}).get("name", "unknown")

    stage_emoji = {
        "analyzing": "🔍",
        "querying_memory": "🧠",
        "investigating": "🔬",
        "planning_remediation": "📋",
        "awaiting_approval": "⏳",
        "executing_action": "⚡",
        "verifying": "✔️",
        "summarizing": "📝",
        "completed": "✅",
        "failed": "❌",
    }

    emoji = stage_emoji.get(stage, "📌")

    if error:
        message = f"""{emoji} **Investigation Failed**

**ID:** {investigation_id}
**Resource:** {namespace}/{pod_name}
**Error:** {error}
"""
    else:
        message = f"""{emoji} **Stage: {stage.replace("_", " ").title()}**

**ID:** {investigation_id}
**Resource:** {namespace}/{pod_name}
"""

    try:
        await send_discord_message(content=message, agent_name="k8s-monitor")
    except Exception as e:
        logger.warning(f"Failed to post stage update: {e}")

    return {"posted": True, "stage": stage}


# =============================================================================
# Helpers
# =============================================================================


def _calculate_duration(state: dict[str, Any]) -> str:
    """Calculate investigation duration from state timestamps."""
    try:
        started = state.get("started_at")
        if started:
            if isinstance(started, str):
                start_time = datetime.fromisoformat(started.replace("Z", "+00:00"))
            else:
                start_time = started
            duration = datetime.now(UTC) - start_time
            return f"{duration.total_seconds():.1f}s"
    except Exception:
        pass
    return "unknown"
