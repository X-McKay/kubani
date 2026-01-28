"""K8s Investigation Swarm - Emergent investigation behavior.

This workflow implements the Swarm pattern for investigating complex K8s issues
that require multiple specialist agents working together:

- DiagnosticsAgent: Gathers cluster state, logs, metrics
- RootCauseAgent: Analyzes data to find root causes
- ImpactAgent: Assesses blast radius and dependencies
- RecommendationAgent: Proposes remediation strategies

The swarm uses a shared context (via Memory MCP) and the agents can
dynamically spawn subtasks based on their findings. A RequestTrackerWorkflow
runs alongside to provide real-time visibility into swarm progress.

Usage:
    # Start investigation
    workflow_id = await client.start_workflow(
        K8sInvestigationSwarm.run,
        InvestigationInput(
            trigger_event_id="event-123",
            resource_kind="Pod",
            resource_name="api-server-xyz",
            namespace="production",
        ),
        id="investigation-123",
        task_queue="k8s-monitor",
    )

    # Query swarm status
    status = await handle.query(K8sInvestigationSwarm.get_swarm_status)
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import (
        ObservableWorkflowMixin,
        SwarmStatus,
        SwarmTask,
        WorkflowStatus,
    )


# =============================================================================
# Input/Output Types
# =============================================================================


@dataclass
class InvestigationInput:
    """Input for K8s investigation swarm.

    Attributes:
        trigger_event_id: Event that triggered the investigation
        resource_kind: Kind of resource being investigated
        resource_name: Name of the resource
        namespace: Kubernetes namespace
        symptoms: Initial symptoms observed
        priority: Investigation priority (1-5, 1 is highest)
        max_depth: Maximum investigation depth (prevents runaway)
        timeout_minutes: Overall timeout for investigation
        notify_channel: Discord channel for updates
        correlation_id: Optional ID for tracking
    """

    trigger_event_id: str
    resource_kind: str
    resource_name: str
    namespace: str
    symptoms: list[str] = field(default_factory=list)
    priority: int = 3
    max_depth: int = 5
    timeout_minutes: int = 30
    notify_channel: str = "k8s-alerts"
    correlation_id: str | None = None


@dataclass
class InvestigationResult:
    """Result of K8s investigation swarm.

    Attributes:
        trigger_event_id: The triggering event
        root_causes: Identified root causes
        impact_assessment: Blast radius and affected resources
        recommendations: Proposed remediation strategies
        evidence: Supporting evidence collected
        agents_invoked: Agents that participated
        tasks_completed: Number of completed tasks
        tasks_failed: Number of failed tasks
        confidence: Overall confidence in findings
        success: Whether investigation completed successfully
        error: Error message if failed
    """

    trigger_event_id: str
    root_causes: list[dict[str, Any]] = field(default_factory=list)
    impact_assessment: dict[str, Any] = field(default_factory=dict)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    agents_invoked: list[str] = field(default_factory=list)
    tasks_completed: int = 0
    tasks_failed: int = 0
    confidence: float = 0.0
    success: bool = True
    error: str | None = None


# =============================================================================
# Swarm Agent Definitions
# =============================================================================


SWARM_AGENTS = {
    "diagnostics": {
        "name": "k8s-diagnostics",
        "description": "Gathers cluster state, logs, metrics, and events",
        "can_spawn": ["root-cause", "impact"],
    },
    "root-cause": {
        "name": "k8s-root-cause",
        "description": "Analyzes diagnostic data to identify root causes",
        "can_spawn": ["diagnostics", "impact"],
    },
    "impact": {
        "name": "k8s-impact",
        "description": "Assesses blast radius and dependency impacts",
        "can_spawn": ["diagnostics"],
    },
    "recommendation": {
        "name": "k8s-recommendation",
        "description": "Proposes remediation strategies based on findings",
        "can_spawn": [],
    },
}


# =============================================================================
# Activity Retry Policies
# =============================================================================


SWARM_AGENT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=10),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=3,
)


# =============================================================================
# Workflow Definition
# =============================================================================


@workflow.defn
class K8sInvestigationSwarm(ObservableWorkflowMixin):
    """Emergent K8s investigation swarm.

    Multiple specialist agents collaborate to investigate complex issues.
    Agents can spawn subtasks based on their findings, creating emergent
    investigation behavior bounded by max_depth and timeout.

    Architecture:
    - Shared context via Memory MCP (SwarmContext)
    - Task queue for pending agent work
    - Each agent can spawn work for other agents
    - Results aggregated into final report

    Signals:
        - pause: Pause investigation
        - resume: Resume investigation
        - cancel: Cancel investigation
        - add_symptom: Add a new symptom to investigate

    Queries:
        - get_status: Current swarm status
        - get_swarm_status: Detailed swarm task status
        - get_findings: Current investigation findings
    """

    def __init__(self) -> None:
        """Initialize the swarm workflow."""
        self._init_observability("K8sInvestigationSwarm")
        self._result = InvestigationResult(trigger_event_id="")
        self._tasks: list[SwarmTask] = []
        self._pending_tasks: list[SwarmTask] = []
        self._completed_tasks: list[SwarmTask] = []
        self._failed_tasks: list[SwarmTask] = []
        self._context_id: str = ""
        self._current_depth: int = 0
        self._additional_symptoms: list[str] = []

    @workflow.run
    async def run(self, input: InvestigationInput) -> dict[str, Any]:
        """Execute the investigation swarm.

        Args:
            input: Investigation configuration

        Returns:
            InvestigationResult as dict
        """
        self._result.trigger_event_id = input.trigger_event_id
        self._set_status(
            WorkflowStatus.RUNNING,
            f"Investigating {input.resource_kind}/{input.resource_name}",
            phase="init",
            resource=f"{input.namespace}/{input.resource_kind}/{input.resource_name}",
        )

        try:
            # Phase 1: Initialize swarm context
            await self._initialize_context(input)

            # Phase 2: Spawn initial diagnostics task
            await self._spawn_initial_tasks(input)

            # Phase 3: Process task queue until empty or timeout
            await self._process_swarm_tasks(input)

            if await self._wait_if_paused():
                return self._build_result()

            # Phase 4: Generate recommendations based on findings
            await self._generate_recommendations(input)

            # Phase 5: Publish investigation report
            await self._publish_report(input)

            self._set_status(WorkflowStatus.COMPLETED, "Investigation complete")
            self._result.success = True

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Investigation failed: {e}")
            self._result.success = False
            self._result.error = str(e)

        return self._build_result()

    async def _initialize_context(self, input: InvestigationInput) -> None:
        """Initialize shared swarm context in Memory MCP."""
        from kubani.framework.temporal import update_swarm_context_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Initializing investigation context",
            phase="init_context",
        )

        # Create context ID from workflow info
        self._context_id = f"investigation-{workflow.info().workflow_id}"

        initial_context = {
            "trigger_event_id": input.trigger_event_id,
            "resource": f"{input.namespace}/{input.resource_kind}/{input.resource_name}",
            "symptoms": input.symptoms + self._additional_symptoms,
            "priority": input.priority,
            "findings": [],
            "evidence": [],
            "agents_invoked": [],
        }

        result = await workflow.execute_activity(
            update_swarm_context_activity,
            args=[self._context_id, initial_context, 3600],  # 1 hour TTL
            start_to_close_timeout=timedelta(seconds=30),
        )

        if result.get("success"):
            self._log_event("context_initialized", f"Context ID: {self._context_id}")
        else:
            raise RuntimeError(f"Failed to initialize context: {result.get('error')}")

    async def _spawn_initial_tasks(self, input: InvestigationInput) -> None:
        """Spawn the initial diagnostics task."""
        self._set_status(
            WorkflowStatus.RUNNING,
            "Spawning initial investigation tasks",
            phase="spawn_initial",
        )

        # Create initial diagnostics task
        diagnostics_task = SwarmTask(
            task_id=f"{self._context_id}-diagnostics-0",
            agent_type="diagnostics",
            description=f"Gather diagnostics for {input.resource_kind}/{input.resource_name}",
            input_data={
                "resource_kind": input.resource_kind,
                "resource_name": input.resource_name,
                "namespace": input.namespace,
                "symptoms": input.symptoms,
            },
            depth=0,
            parent_task_id=None,
        )

        self._pending_tasks.append(diagnostics_task)
        self._tasks.append(diagnostics_task)
        self._log_event("task_spawned", f"Initial task: {diagnostics_task.task_id}")

    async def _process_swarm_tasks(self, input: InvestigationInput) -> None:
        """Process the swarm task queue."""
        self._set_status(
            WorkflowStatus.RUNNING,
            "Processing investigation tasks",
            phase="process_tasks",
        )

        # Set deadline
        deadline = workflow.now() + timedelta(minutes=input.timeout_minutes)
        task_counter = 0

        while self._pending_tasks and workflow.now() < deadline:
            # Check for pause/cancel
            if await self._wait_if_paused():
                return

            # Get next task
            task = self._pending_tasks.pop(0)
            task.status = SwarmStatus.RUNNING
            task_counter += 1

            self._log_event(
                "task_started",
                f"Task {task.task_id} (depth={task.depth})",
            )

            try:
                # Execute the task
                result = await self._execute_swarm_task(task, input)

                # Update task with result
                task.status = SwarmStatus.COMPLETED
                task.result = result
                self._completed_tasks.append(task)
                self._result.tasks_completed += 1

                # Record agent invocation
                if task.agent_type not in self._result.agents_invoked:
                    self._result.agents_invoked.append(task.agent_type)

                # Process spawned tasks (if under max depth)
                if task.depth < input.max_depth:
                    await self._process_spawn_requests(task, result, input)

                self._log_event(
                    "task_completed",
                    f"Task {task.task_id} completed",
                )

            except Exception as e:
                task.status = SwarmStatus.FAILED
                task.error = str(e)
                self._failed_tasks.append(task)
                self._result.tasks_failed += 1
                self._log_event("task_failed", f"Task {task.task_id}: {e}")

        # Log completion stats
        self._log_event(
            "swarm_complete",
            f"Completed {self._result.tasks_completed} tasks, {self._result.tasks_failed} failed",
        )

    async def _execute_swarm_task(
        self,
        task: SwarmTask,
        input: InvestigationInput,
    ) -> dict[str, Any]:
        """Execute a single swarm task."""
        from kubani.framework.temporal import (
            get_swarm_context_activity,
            run_agent_for_swarm_activity,
            update_swarm_context_activity,
        )

        agent_config = SWARM_AGENTS.get(task.agent_type, {})
        agent_name = agent_config.get("name", f"k8s-{task.agent_type}")

        # Get current context
        context_result = await workflow.execute_activity(
            get_swarm_context_activity,
            args=[self._context_id],
            start_to_close_timeout=timedelta(seconds=30),
        )

        current_context = context_result.get("context", {})

        # Build prompt for the agent
        prompt = self._build_agent_prompt(task, current_context, input)

        # Execute agent
        result = await workflow.execute_activity(
            run_agent_for_swarm_activity,
            args=[
                agent_name,
                prompt,
                self._context_id,
                task.task_id,
            ],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=SWARM_AGENT_RETRY_POLICY,
        )

        if not result.get("success"):
            raise RuntimeError(result.get("error", "Agent execution failed"))

        # Parse agent result
        agent_output = self._parse_json_from_result(result.get("result", ""))

        # Update context with findings
        new_findings = agent_output.get("findings", [])
        new_evidence = agent_output.get("evidence", [])

        if new_findings or new_evidence:
            await workflow.execute_activity(
                update_swarm_context_activity,
                args=[
                    self._context_id,
                    {
                        "findings": current_context.get("findings", []) + new_findings,
                        "evidence": current_context.get("evidence", []) + new_evidence,
                        "agents_invoked": list(
                            set(current_context.get("agents_invoked", []) + [task.agent_type])
                        ),
                    },
                    3600,
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

            # Also update local result
            self._result.evidence.extend(new_evidence)

        return agent_output

    def _build_agent_prompt(
        self,
        task: SwarmTask,
        context: dict[str, Any],
        input: InvestigationInput,
    ) -> str:
        """Build the prompt for a swarm agent."""
        import json

        agent_config = SWARM_AGENTS.get(task.agent_type, {})
        can_spawn = agent_config.get("can_spawn", [])

        prompt = f"""You are investigating a Kubernetes issue as part of a multi-agent swarm.

## Your Role
{agent_config.get("description", "Investigate the issue")}

## Task
{task.description}

## Investigation Context
Resource: {input.namespace}/{input.resource_kind}/{input.resource_name}
Symptoms: {", ".join(input.symptoms)}
Priority: {input.priority}/5

## Current Findings
{json.dumps(context.get("findings", []), indent=2)}

## Evidence Collected
{json.dumps(context.get("evidence", [])[:10], indent=2)}

## Task Input
{json.dumps(task.input_data, indent=2)}

## Instructions
1. Perform your investigation based on your role
2. Record any new findings with confidence scores
3. Collect supporting evidence
4. Identify if other agents should be involved

## Response Format
Return JSON with:
- findings: array of {{finding, confidence: 0-1, category}}
- evidence: array of {{type, source, content, timestamp}}
- spawn_requests: array of {{agent_type, reason, input_data}} where agent_type is one of {can_spawn}
- root_causes: array of {{cause, confidence: 0-1, evidence_refs}} (if you've identified any)
- summary: brief summary of what you found"""

        return prompt

    async def _process_spawn_requests(
        self,
        parent_task: SwarmTask,
        result: dict[str, Any],
        input: InvestigationInput,
    ) -> None:
        """Process spawn requests from a completed task."""
        spawn_requests = result.get("spawn_requests", [])
        agent_config = SWARM_AGENTS.get(parent_task.agent_type, {})
        allowed_spawns = agent_config.get("can_spawn", [])

        for request in spawn_requests[:3]:  # Limit spawns per task
            agent_type = request.get("agent_type")
            if agent_type not in allowed_spawns:
                continue

            # Create new task
            new_task = SwarmTask(
                task_id=f"{self._context_id}-{agent_type}-{len(self._tasks)}",
                agent_type=agent_type,
                description=request.get("reason", f"Investigate {agent_type}"),
                input_data=request.get("input_data", {}),
                depth=parent_task.depth + 1,
                parent_task_id=parent_task.task_id,
            )

            self._pending_tasks.append(new_task)
            self._tasks.append(new_task)
            self._log_event(
                "task_spawned",
                f"Spawned {new_task.task_id} from {parent_task.task_id}",
            )

    async def _generate_recommendations(self, input: InvestigationInput) -> None:
        """Generate remediation recommendations based on findings."""
        from kubani.framework.temporal import get_swarm_context_activity, run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Generating recommendations",
            phase="recommendations",
        )

        # Get final context
        context_result = await workflow.execute_activity(
            get_swarm_context_activity,
            args=[self._context_id],
            start_to_close_timeout=timedelta(seconds=30),
        )

        context = context_result.get("context", {})
        findings = context.get("findings", [])

        # Extract root causes from completed tasks
        for task in self._completed_tasks:
            if task.result and task.result.get("root_causes"):
                for rc in task.result["root_causes"]:
                    if rc not in self._result.root_causes:
                        self._result.root_causes.append(rc)

        # Run recommendation agent
        import json

        result = await workflow.execute_activity(
            run_agent_activity,
            args=[
                "k8s-recommendation",
                f"""Generate remediation recommendations for this investigation.

## Resource
{input.namespace}/{input.resource_kind}/{input.resource_name}

## Root Causes Identified
{json.dumps(self._result.root_causes, indent=2)}

## All Findings
{json.dumps(findings, indent=2)}

## Symptoms
{", ".join(input.symptoms)}

## Instructions
For each root cause, propose:
1. Immediate remediation steps
2. Long-term prevention measures
3. Monitoring improvements

Return JSON with:
- recommendations: array of {{
    root_cause: string,
    immediate_steps: array,
    prevention_measures: array,
    monitoring: array,
    priority: 1-5,
    confidence: 0-1
  }}
- impact_assessment: {{
    affected_services: array,
    affected_users: string,
    severity: critical/high/medium/low,
    blast_radius: string
  }}
- overall_confidence: 0-1""",
            ],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=SWARM_AGENT_RETRY_POLICY,
        )

        if result.get("success"):
            output = self._parse_json_from_result(result.get("result", ""))
            self._result.recommendations = output.get("recommendations", [])
            self._result.impact_assessment = output.get("impact_assessment", {})
            self._result.confidence = output.get("overall_confidence", 0.5)
            self._result.agents_invoked.append("recommendation")
            self._log_event(
                "recommendations_generated",
                f"Generated {len(self._result.recommendations)} recommendations",
            )

    async def _publish_report(self, input: InvestigationInput) -> None:
        """Publish investigation report to Discord."""
        from kubani.framework.temporal import run_agent_activity

        self._set_status(
            WorkflowStatus.RUNNING,
            "Publishing investigation report",
            phase="publish",
        )

        import json

        report = {
            "resource": f"{input.namespace}/{input.resource_kind}/{input.resource_name}",
            "trigger_event": input.trigger_event_id,
            "root_causes": self._result.root_causes,
            "impact": self._result.impact_assessment,
            "recommendations": self._result.recommendations,
            "confidence": self._result.confidence,
            "agents_invoked": self._result.agents_invoked,
            "tasks_completed": self._result.tasks_completed,
        }

        await workflow.execute_activity(
            run_agent_activity,
            args=[
                "discord-notifier",
                f"""Publish an investigation report to channel: {input.notify_channel}

Report:
{json.dumps(report, indent=2)}

Format as a detailed Discord embed with:
- Title: 🔍 K8s Investigation Report
- Color based on severity from impact assessment
- Sections for: Root Causes, Impact, Recommendations
- Footer with confidence score and agents invoked

Return JSON with: message_id, success""",
            ],
            start_to_close_timeout=timedelta(minutes=1),
        )

        self._log_event("report_published", f"Published to {input.notify_channel}")

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_json_from_result(self, result: str) -> dict[str, Any]:
        """Parse JSON object from agent result."""
        import json

        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except json.JSONDecodeError:
            pass
        return {}

    def _build_result(self) -> dict[str, Any]:
        """Build result dictionary."""
        return {
            "trigger_event_id": self._result.trigger_event_id,
            "root_causes": self._result.root_causes,
            "impact_assessment": self._result.impact_assessment,
            "recommendations": self._result.recommendations,
            "evidence": self._result.evidence[:20],  # Limit evidence in result
            "agents_invoked": self._result.agents_invoked,
            "tasks_completed": self._result.tasks_completed,
            "tasks_failed": self._result.tasks_failed,
            "confidence": self._result.confidence,
            "success": self._result.success,
            "error": self._result.error,
        }

    # =========================================================================
    # Signals
    # =========================================================================

    @workflow.signal
    async def add_symptom(self, symptom: str) -> None:
        """Add a new symptom to investigate."""
        self._additional_symptoms.append(symptom)
        self._log_event("symptom_added", symptom)

    # =========================================================================
    # Queries
    # =========================================================================

    @workflow.query
    def get_swarm_status(self) -> dict[str, Any]:
        """Query detailed swarm task status."""
        return {
            "total_tasks": len(self._tasks),
            "pending": len(self._pending_tasks),
            "completed": len(self._completed_tasks),
            "failed": len(self._failed_tasks),
            "agents_invoked": self._result.agents_invoked,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "agent_type": t.agent_type,
                    "status": t.status.value if t.status else "unknown",
                    "depth": t.depth,
                }
                for t in self._tasks[:20]  # Limit to 20
            ],
        }

    @workflow.query
    def get_findings(self) -> dict[str, Any]:
        """Query current investigation findings."""
        return {
            "root_causes": self._result.root_causes,
            "evidence_count": len(self._result.evidence),
            "recommendations": self._result.recommendations,
            "confidence": self._result.confidence,
        }
