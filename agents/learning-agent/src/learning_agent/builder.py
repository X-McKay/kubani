"""
Execution Record Builder.

Converts passive observations from various sources into ExecutionRecord
format compatible with the learning pipeline.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from learning_agent.observers.discord import AgentMessage
from learning_agent.observers.events import AgentEvent, ExecutionChain
from learning_agent.observers.temporal import WorkflowResult

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    """
    Record of an agent execution for learning.

    This mirrors the structure in core_agents.learning.voyager.manager
    but is defined here to avoid circular imports.
    """

    id: str
    agent_name: str
    task: str
    trace: list[dict[str, Any]]
    outcome: dict[str, Any]
    success: bool
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "passive"  # "passive", "explicit", "event", "discord"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "task": self.task,
            "trace": self.trace,
            "outcome": self.outcome,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "metadata": self.metadata,
        }


class ExecutionRecordBuilder:
    """
    Builds ExecutionRecords from passive observations.

    Converts data from:
    - Temporal workflow results and history
    - Redis event chains
    - Discord messages
    """

    def from_workflow(
        self,
        workflow: WorkflowResult,
        history: list[dict[str, Any]] | None = None,
    ) -> ExecutionRecord:
        """
        Build an ExecutionRecord from a Temporal workflow.

        Args:
            workflow: The workflow result
            history: Optional workflow history events

        Returns:
            ExecutionRecord for the learning pipeline
        """
        # Build trace from workflow history
        trace = self._build_trace_from_history(history or workflow.history)

        # Add workflow metadata to trace
        trace.insert(
            0,
            {
                "type": "workflow_started",
                "timestamp": workflow.start_time.isoformat(),
                "workflow_type": workflow.workflow_type,
                "task_queue": workflow.task_queue,
            },
        )

        if workflow.close_time:
            trace.append(
                {
                    "type": "workflow_completed",
                    "timestamp": workflow.close_time.isoformat(),
                    "status": workflow.status,
                }
            )

        # Build outcome from workflow result
        outcome = workflow.result or {}
        if workflow.duration_seconds is not None:
            outcome["duration_seconds"] = workflow.duration_seconds

        return ExecutionRecord(
            id=f"wf-{workflow.workflow_id}",
            agent_name=workflow.agent_name,
            task=self._extract_task_description(workflow),
            trace=trace,
            outcome=outcome,
            success=workflow.is_success,
            timestamp=workflow.start_time,
            source="temporal",
            metadata={
                "workflow_id": workflow.workflow_id,
                "run_id": workflow.run_id,
                "workflow_type": workflow.workflow_type,
                "task_queue": workflow.task_queue,
            },
        )

    def from_event_chain(self, chain: ExecutionChain) -> ExecutionRecord:
        """
        Build an ExecutionRecord from an event chain.

        Args:
            chain: Correlated chain of agent events

        Returns:
            ExecutionRecord for the learning pipeline
        """
        # Build trace from events
        trace = [
            {
                "type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "source": event.source,
                "payload": event.payload,
            }
            for event in chain.events
        ]

        # Build outcome from final event
        outcome = {}
        if chain.events:
            final_event = chain.events[-1]
            outcome = {
                "final_event_type": final_event.event_type,
                **final_event.payload,
            }

        if chain.start_time and chain.end_time:
            outcome["duration_seconds"] = (chain.end_time - chain.start_time).total_seconds()

        return ExecutionRecord(
            id=f"ev-{chain.correlation_id}",
            agent_name=chain.agent_name,
            task=self._extract_task_from_events(chain.events),
            trace=trace,
            outcome=outcome,
            success=chain.is_success,
            timestamp=chain.start_time or datetime.now(UTC),
            source="event",
            metadata={
                "correlation_id": chain.correlation_id,
                "event_count": len(chain.events),
            },
        )

    def from_discord_message(
        self,
        message: AgentMessage,
        related_workflow: WorkflowResult | None = None,
    ) -> ExecutionRecord:
        """
        Build an ExecutionRecord from a Discord message.

        This is useful when workflows don't emit to Temporal but do post to Discord.

        Args:
            message: The Discord message
            related_workflow: Optional workflow that produced this message

        Returns:
            ExecutionRecord for the learning pipeline
        """
        # Build trace
        trace = [
            {
                "type": "discord_posted",
                "timestamp": message.created_at.isoformat(),
                "channel": message.channel_name,
                "content_length": len(message.content),
            }
        ]

        # Build outcome
        outcome = {
            "message_id": message.message_id,
            "channel": message.channel_name,
            "content_preview": message.content_preview,
        }

        if message.reactions:
            outcome["reactions"] = {
                "total": message.reactions.total_reactions,
                "positive": message.reactions.positive_count,
                "negative": message.reactions.negative_count,
                "engagement_score": message.reactions.engagement_score,
            }

        # Determine success from reactions
        success = True
        if message.reactions:
            # Consider negative if engagement score is below 0.3
            if message.reactions.engagement_score < 0.3:
                success = False

        return ExecutionRecord(
            id=f"dc-{message.message_id}",
            agent_name=message.agent_name,
            task=self._extract_task_from_message(message),
            trace=trace,
            outcome=outcome,
            success=success,
            timestamp=message.created_at,
            source="discord",
            metadata={
                "message_id": message.message_id,
                "channel_id": message.channel_id,
                "channel_name": message.channel_name,
                "author": message.author_name,
            },
        )

    def enrich_with_discord(
        self,
        record: ExecutionRecord,
        messages: list[AgentMessage],
    ) -> ExecutionRecord:
        """
        Enrich an ExecutionRecord with Discord message data.

        Links Discord output to the execution and adds reaction feedback.

        Args:
            record: The execution record to enrich
            messages: Related Discord messages

        Returns:
            Enriched execution record
        """
        if not messages:
            return record

        # Find messages that match the execution timeframe
        relevant_messages = [
            m
            for m in messages
            if m.agent_name == record.agent_name
            and abs((m.created_at - record.timestamp).total_seconds()) < 300  # 5 min window
        ]

        if not relevant_messages:
            return record

        # Add Discord events to trace
        for msg in relevant_messages:
            record.trace.append(
                {
                    "type": "discord_posted",
                    "timestamp": msg.created_at.isoformat(),
                    "channel": msg.channel_name,
                    "message_id": msg.message_id,
                }
            )

        # Update outcome with reaction feedback
        total_reactions = sum(m.reactions.total_reactions for m in relevant_messages if m.reactions)
        total_positive = sum(m.reactions.positive_count for m in relevant_messages if m.reactions)
        total_negative = sum(m.reactions.negative_count for m in relevant_messages if m.reactions)

        record.outcome["discord_feedback"] = {
            "message_count": len(relevant_messages),
            "total_reactions": total_reactions,
            "positive_reactions": total_positive,
            "negative_reactions": total_negative,
        }

        record.metadata["discord_message_ids"] = [m.message_id for m in relevant_messages]

        return record

    def _build_trace_from_history(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert Temporal history events to trace format."""
        trace = []

        for event in history:
            event_type = event.get("eventType", "")
            timestamp = event.get("eventTime", "")

            # Map Temporal events to trace events
            if "ActivityScheduled" in event_type:
                attrs = event.get("activityTaskScheduledEventAttributes", {})
                trace.append(
                    {
                        "type": "activity_scheduled",
                        "timestamp": timestamp,
                        "activity": attrs.get("activityType", {}).get("name", "unknown"),
                    }
                )
            elif "ActivityCompleted" in event_type:
                attrs = event.get("activityTaskCompletedEventAttributes", {})
                trace.append(
                    {
                        "type": "activity_completed",
                        "timestamp": timestamp,
                        "result": self._safe_parse_result(attrs.get("result")),
                    }
                )
            elif "ActivityFailed" in event_type:
                attrs = event.get("activityTaskFailedEventAttributes", {})
                trace.append(
                    {
                        "type": "activity_failed",
                        "timestamp": timestamp,
                        "failure": attrs.get("failure", {}).get("message", ""),
                    }
                )
            elif "WorkflowExecutionFailed" in event_type:
                attrs = event.get("workflowExecutionFailedEventAttributes", {})
                trace.append(
                    {
                        "type": "workflow_failed",
                        "timestamp": timestamp,
                        "failure": attrs.get("failure", {}).get("message", ""),
                    }
                )

        return trace

    def _extract_task_description(self, workflow: WorkflowResult) -> str:
        """Extract a human-readable task description from workflow."""
        workflow_type = workflow.workflow_type

        # Map workflow types to descriptions
        descriptions = {
            "ClusterHealthCheckWorkflow": "Check Kubernetes cluster health",
            "ScheduledHealthCheckWorkflow": "Scheduled cluster health check",
            "ArticleIngestionWorkflow": "Ingest news articles from feeds",
            "DigestGenerationWorkflow": "Generate news digest",
            "ScheduledArticleIngestionWorkflow": "Scheduled article ingestion",
            "ScheduledDigestGenerationWorkflow": "Scheduled digest generation",
        }

        return descriptions.get(workflow_type, f"Execute {workflow_type}")

    def _extract_task_from_events(self, events: list[AgentEvent]) -> str:
        """Extract task description from event chain."""
        if not events:
            return "Unknown task"

        first_event = events[0]
        event_type = first_event.event_type

        descriptions = {
            "K8S_ISSUE_DETECTED": "Investigate and remediate Kubernetes issue",
            "NEWS_ARTICLE_INGESTED": "Process and store news articles",
            "NEWS_BREAKING_DETECTED": "Process breaking news alert",
            "SYSTEM_SKILL_PROPOSED": "Review skill proposal",
        }

        return descriptions.get(event_type, f"Handle {event_type}")

    def _extract_task_from_message(self, message: AgentMessage) -> str:
        """Extract task description from Discord message."""
        channel_tasks = {
            "ai-news": "Publish news digest",
            "kubani-alerts": "Send cluster alert",
            "ai-breaking-news": "Send breaking news alert",
            "kubani-learning": "Post learning insight",
            "kubani-approvals": "Request skill approval",
        }

        return channel_tasks.get(message.channel_name, "Post to Discord")

    def _safe_parse_result(self, result: Any) -> dict[str, Any]:
        """Safely parse a result payload."""
        if result is None:
            return {}

        if isinstance(result, dict):
            return result

        if isinstance(result, str):
            try:
                import json

                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return {"raw": result}

        return {"value": str(result)}


def merge_records(records: list[ExecutionRecord]) -> list[ExecutionRecord]:
    """
    Merge duplicate execution records from different sources.

    If the same execution is captured by both Temporal and events,
    merge them into a single comprehensive record.

    Args:
        records: List of execution records

    Returns:
        Deduplicated and merged records
    """
    # Group by approximate timestamp and agent
    groups: dict[str, list[ExecutionRecord]] = {}

    for record in records:
        # Create a key based on agent and 1-minute time bucket
        bucket = record.timestamp.replace(second=0, microsecond=0)
        key = f"{record.agent_name}:{bucket.isoformat()}"

        if key not in groups:
            groups[key] = []
        groups[key].append(record)

    # Merge groups
    merged = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
        else:
            # Prefer temporal source, then event, then discord
            priority = {"temporal": 0, "event": 1, "discord": 2, "passive": 3}
            group.sort(key=lambda r: priority.get(r.source, 99))
            primary = group[0]

            # Merge traces from other sources
            for secondary in group[1:]:
                for trace_item in secondary.trace:
                    if trace_item not in primary.trace:
                        primary.trace.append(trace_item)

                # Merge metadata
                primary.metadata.update(secondary.metadata)

            # Sort trace by timestamp
            primary.trace.sort(key=lambda t: t.get("timestamp", ""))
            merged.append(primary)

    return merged
