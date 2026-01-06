"""
K8s domain skills - knowledge about when/how to use MCP tools.

Skills are KNOWLEDGE, not executable code. They define:
- Preconditions: When to apply this skill
- Actions: Which MCP tools to use (references, not code)
- Success criteria: How to verify it worked
- Failure handling: What to do if it doesn't work

These skills are bootstrapped into the skill library (Qdrant) at startup.
"""

from core_agents.skills import (
    MCPToolReference,
    Skill,
    SkillAction,
    SkillCategory,
    SkillDomain,
    get_skill_library,
)

# Initial K8s skills extracted from existing k8s-monitor patterns
K8S_SKILLS: list[Skill] = [
    # Remediation skills
    Skill(
        id="k8s-restart-crashloop",
        name="Restart CrashLoopBackOff Pod",
        domain=SkillDomain.K8S,
        category=SkillCategory.REMEDIATION,
        description=(
            "Restart a pod that is stuck in CrashLoopBackOff state. "
            "This is appropriate when the pod has been crashing repeatedly "
            "and a simple restart might resolve a transient issue."
        ),
        preconditions=[
            "Pod status is CrashLoopBackOff",
            "Pod has restarted more than 3 times",
            "Pod is not part of a Job or CronJob",
            "No OOMKilled events in last 10 minutes",
        ],
        actions=[
            SkillAction(
                description="Delete the pod to trigger recreation",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="pods_delete",
                    params={"name": "$pod_name", "namespace": "$namespace"},
                ),
                timeout_seconds=30,
            ),
        ],
        success_criteria=[
            "New pod created within 30 seconds",
            "New pod reaches Running state within 2 minutes",
            "No CrashLoopBackOff within 5 minutes of restart",
        ],
        failure_handling=(
            "If pod does not reach Running state:\n"
            "1. Check events for the new pod\n"
            "2. Check logs from the new pod\n"
            "3. Escalate to human if pattern repeats 3 times"
        ),
        requires_approval=False,
        confidence=0.85,
        tags=["pod", "crashloop", "restart", "remediation"],
    ),
    Skill(
        id="k8s-restart-imagepullbackoff",
        name="Handle ImagePullBackOff",
        domain=SkillDomain.K8S,
        category=SkillCategory.REMEDIATION,
        description=(
            "Handle a pod stuck in ImagePullBackOff state. "
            "First investigates the image pull error, then restarts to retry."
        ),
        preconditions=[
            "Pod status is ImagePullBackOff or ErrImagePull",
            "Pod has been in this state for more than 2 minutes",
        ],
        actions=[
            SkillAction(
                description="Get pod events to understand the image pull failure",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="events_list",
                    params={"namespace": "$namespace"},
                ),
                timeout_seconds=30,
            ),
            SkillAction(
                description="Delete the pod to trigger recreation and retry image pull",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="pods_delete",
                    params={"name": "$pod_name", "namespace": "$namespace"},
                ),
                timeout_seconds=30,
            ),
        ],
        success_criteria=[
            "New pod created and image pull succeeds",
            "Pod reaches Running state within 5 minutes",
        ],
        failure_handling=(
            "If image pull continues to fail:\n"
            "1. Verify image name and tag are correct\n"
            "2. Check image registry connectivity\n"
            "3. Verify image pull secrets are configured\n"
            "4. Escalate to human with registry details"
        ),
        requires_approval=False,
        confidence=0.70,
        tags=["pod", "imagepull", "registry", "remediation"],
    ),
    Skill(
        id="k8s-scale-deployment",
        name="Scale Deployment Replicas",
        domain=SkillDomain.K8S,
        category=SkillCategory.REMEDIATION,
        description=(
            "Scale a deployment to a specified number of replicas. "
            "Used for both scaling up (to handle load) and scaling down."
        ),
        preconditions=[
            "Resource is a Deployment or StatefulSet",
            "Target replica count is within configured limits (1-10)",
            "Current replica count differs from target",
        ],
        actions=[
            SkillAction(
                description="Scale the deployment to target replicas",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="resources_scale",
                    params={
                        "apiVersion": "apps/v1",
                        "kind": "$resource_kind",
                        "name": "$deployment_name",
                        "namespace": "$namespace",
                        "scale": "$target_replicas",
                    },
                ),
                timeout_seconds=60,
            ),
        ],
        success_criteria=[
            "Deployment shows target replica count",
            "All replicas become Ready within 5 minutes",
        ],
        failure_handling=(
            "If scaling fails:\n"
            "1. Check resource quotas in namespace\n"
            "2. Verify node capacity\n"
            "3. Check for PVC binding issues\n"
            "4. Escalate if pods cannot schedule"
        ),
        requires_approval=True,  # Scaling requires approval
        confidence=0.90,
        tags=["deployment", "scale", "replicas", "remediation"],
    ),
    # Diagnostic skills
    Skill(
        id="k8s-investigate-pod-failure",
        name="Investigate Pod Failure",
        domain=SkillDomain.K8S,
        category=SkillCategory.DIAGNOSTIC,
        description=(
            "Deep investigation of a failing pod. Gathers logs, events, "
            "and resource status to identify root cause."
        ),
        preconditions=[
            "Pod is in a failed or error state",
            "Pod has been created (not stuck in Pending)",
        ],
        actions=[
            SkillAction(
                description="Get pod status and details",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="pods_get",
                    params={"name": "$pod_name", "namespace": "$namespace"},
                ),
                timeout_seconds=30,
            ),
            SkillAction(
                description="Get pod logs",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="pods_log",
                    params={
                        "name": "$pod_name",
                        "namespace": "$namespace",
                        "tail": 100,
                    },
                ),
                timeout_seconds=30,
            ),
            SkillAction(
                description="Get recent events for the pod",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="events_list",
                    params={"namespace": "$namespace"},
                ),
                timeout_seconds=30,
            ),
        ],
        success_criteria=[
            "Root cause identified from logs or events",
            "Investigation produces actionable findings",
        ],
        failure_handling=(
            "If investigation is inconclusive:\n"
            "1. Check previous container logs (--previous flag)\n"
            "2. Describe the pod for more context\n"
            "3. Check node events if pod failed to schedule\n"
            "4. Escalate with all gathered data"
        ),
        requires_approval=False,
        confidence=0.95,  # Pure diagnostic, very reliable
        tags=["pod", "investigation", "logs", "events", "diagnostic"],
    ),
    Skill(
        id="k8s-check-node-resources",
        name="Check Node Resource Usage",
        domain=SkillDomain.K8S,
        category=SkillCategory.DIAGNOSTIC,
        description=(
            "Check resource usage (CPU, memory) on cluster nodes. "
            "Used to identify nodes under pressure."
        ),
        preconditions=[
            "Metrics server is available",
            "Need to understand cluster resource status",
        ],
        actions=[
            SkillAction(
                description="Get resource usage for all nodes",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="nodes_top",
                    params={},
                ),
                timeout_seconds=30,
            ),
        ],
        success_criteria=[
            "Node resource metrics retrieved successfully",
            "Resource pressure identified if present",
        ],
        failure_handling=(
            "If metrics unavailable:\n"
            "1. Check if metrics-server is deployed\n"
            "2. Request prometheus-mcp-server deployment"
        ),
        requires_approval=False,
        confidence=0.95,
        tags=["node", "resources", "cpu", "memory", "diagnostic"],
    ),
    Skill(
        id="k8s-check-pod-resources",
        name="Check Pod Resource Usage",
        domain=SkillDomain.K8S,
        category=SkillCategory.DIAGNOSTIC,
        description=(
            "Check resource usage (CPU, memory) for pods. "
            "Used to identify pods consuming excessive resources."
        ),
        preconditions=[
            "Metrics server is available",
            "Need to understand pod resource consumption",
        ],
        actions=[
            SkillAction(
                description="Get resource usage for pods in namespace",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="pods_top",
                    params={"namespace": "$namespace"},
                ),
                timeout_seconds=30,
            ),
        ],
        success_criteria=[
            "Pod resource metrics retrieved successfully",
            "High resource consumers identified if present",
        ],
        failure_handling=(
            "If metrics unavailable:\n"
            "1. Check if metrics-server is deployed\n"
            "2. Fall back to resource requests/limits from pod spec"
        ),
        requires_approval=False,
        confidence=0.95,
        tags=["pod", "resources", "cpu", "memory", "diagnostic"],
    ),
    # Collection skills
    Skill(
        id="k8s-list-recent-events",
        name="List Recent Cluster Events",
        domain=SkillDomain.K8S,
        category=SkillCategory.COLLECTION,
        description=(
            "Collect recent Kubernetes events to identify issues. "
            "Events reveal warnings, errors, and state changes."
        ),
        preconditions=[
            "Need to understand recent cluster activity",
            "Looking for warnings or errors",
        ],
        actions=[
            SkillAction(
                description="List events from all namespaces",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="events_list",
                    params={},
                ),
                timeout_seconds=60,
            ),
        ],
        success_criteria=[
            "Events retrieved successfully",
            "Warnings/errors identified and categorized",
        ],
        failure_handling="If events unavailable, check API server connectivity",
        requires_approval=False,
        confidence=0.95,
        tags=["events", "warnings", "errors", "collection"],
    ),
    Skill(
        id="k8s-list-pods-in-namespace",
        name="List Pods in Namespace",
        domain=SkillDomain.K8S,
        category=SkillCategory.COLLECTION,
        description=(
            "List all pods in a specific namespace with their status. "
            "Used to get an overview of workload health."
        ),
        preconditions=[
            "Namespace is specified",
            "Need overview of pods in namespace",
        ],
        actions=[
            SkillAction(
                description="List pods in the namespace",
                mcp_tool=MCPToolReference(
                    server="kubernetes-mcp-server",
                    tool="pods_list_in_namespace",
                    params={"namespace": "$namespace"},
                ),
                timeout_seconds=30,
            ),
        ],
        success_criteria=[
            "Pod list retrieved with status",
            "Unhealthy pods identified",
        ],
        failure_handling="If list fails, check namespace existence and permissions",
        requires_approval=False,
        confidence=0.95,
        tags=["pods", "namespace", "list", "collection"],
    ),
]


async def bootstrap_k8s_skills() -> list[str]:
    """
    Bootstrap initial K8s skills into the skill library.

    Adds all predefined K8s skills to Qdrant for semantic retrieval.
    Skips skills that already exist (by ID).

    Returns:
        List of skill IDs that were added
    """
    library = await get_skill_library()
    added_ids = []

    for skill in K8S_SKILLS:
        existing = await library.get(skill.id)
        if existing is None:
            await library.add(skill)
            added_ids.append(skill.id)

    return added_ids


async def get_k8s_skill(skill_id: str) -> Skill | None:
    """Get a K8s skill by ID from the library."""
    library = await get_skill_library()
    return await library.get(skill_id)
