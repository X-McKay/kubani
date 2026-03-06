"""Temporal integration for Kubani framework.

This module provides shared infrastructure for Temporal workflows and activities.

Components:
- activities: Base activities for wrapping agents as Temporal activities
- workflows: Base workflow classes for both Workflow and Swarm patterns
- schedules: Utilities for creating and managing Temporal schedules

Usage:
    from kubani.framework.temporal import (
        # Activities
        run_agent_activity,
        classify_event_activity,
        DEFAULT_AGENT_RETRY_POLICY,
        # Workflows
        ObservableWorkflowMixin,
        WorkflowPatternBase,
        RequestTrackerWorkflow,
        SwarmTask,
        # Schedules
        ScheduleConfig,
        create_schedule,
        EVERY_15_MINUTES,
    )

    # In workflow
    result = await workflow.execute_activity(
        run_agent_activity,
        args=["event-classifier", "Classify this event"],
        start_to_close_timeout=timedelta(minutes=5),
        retry_policy=DEFAULT_AGENT_RETRY_POLICY,
    )

    # Create a schedule
    config = ScheduleConfig(
        schedule_id="my-schedule",
        workflow_type=MyWorkflow,
        workflow_id_prefix="my-workflow",
        task_queue="my-queue",
        interval_minutes=EVERY_15_MINUTES,
    )
    await create_schedule(config)
"""

from .activities import (
    DEFAULT_AGENT_RETRY_POLICY,
    AgentExecutionError,
    AgentInput,
    AgentNotFoundError,
    AgentOutput,
    classify_event_activity,
    collect_arxiv_activity,
    collect_feeds_activity,
    publish_ui_activity,
    remediate_issue_activity,
    run_agent_activity,
    run_agent_for_swarm_activity,
)
from .bridge import (
    BridgeConfig,
    EventBridge,
    WorkflowResultPublisher,
    WorkflowTrigger,
    create_k8s_triggers,
    create_news_triggers,
    start_event_bridge,
)
from .discord import (
    send_breaking_news_activity,
)
from .memory import (
    SwarmContext,
    cache_workflow_state_activity,
    check_article_exists_activity,
    check_paper_exists_activity,
    check_repo_exists_activity,
    get_cached_workflow_state_activity,
    get_swarm_context_activity,
    get_trend_snapshot_activity,
    query_articles_activity,
    query_knowledge_activity,
    query_learnings_activity,
    store_article_activity,
    store_knowledge_activity,
    store_learning_activity,
    store_paper_activity,
    store_repo_activity,
    store_trend_snapshot_activity,
    update_swarm_context_activity,
)
from .schedules import (
    CRON_DAILY_EVENING,
    CRON_DAILY_MORNING,
    CRON_TWICE_DAILY_9AM_9PM,
    CRON_WEEKLY_MONDAY,
    EVERY_6_HOURS,
    EVERY_15_MINUTES,
    EVERY_30_MINUTES,
    EVERY_HOUR,
    TWICE_DAILY,
    ScheduleConfig,
    close_schedule_client,
    create_schedule,
    delete_schedule,
    get_schedule_client,
    get_schedule_info,
    list_schedules,
    pause_schedule,
    resume_schedule,
    setup_syndicate_schedules,
    teardown_syndicate_schedules,
    trigger_schedule,
)
from .workflows import (
    ObservableWorkflowMixin,
    RequestTrackerWorkflow,
    StatusInfo,
    SwarmStatus,
    SwarmTask,
    WorkflowEvent,
    WorkflowPatternBase,
    WorkflowPatternInput,
    WorkflowPatternResult,
    WorkflowStatus,
)

__all__ = [
    # Activity Types
    "AgentInput",
    "AgentOutput",
    "AgentNotFoundError",
    "AgentExecutionError",
    # Activities
    "run_agent_activity",
    "classify_event_activity",
    "collect_arxiv_activity",
    "collect_feeds_activity",
    "remediate_issue_activity",
    "run_agent_for_swarm_activity",
    "publish_ui_activity",
    # Activity Utilities
    "DEFAULT_AGENT_RETRY_POLICY",
    # Workflow Types
    "WorkflowStatus",
    "StatusInfo",
    "WorkflowEvent",
    "SwarmTask",
    "SwarmStatus",
    "WorkflowPatternInput",
    "WorkflowPatternResult",
    # Workflow Base Classes
    "ObservableWorkflowMixin",
    "WorkflowPatternBase",
    "RequestTrackerWorkflow",
    # Schedule Configuration
    "ScheduleConfig",
    # Schedule Patterns
    "EVERY_15_MINUTES",
    "EVERY_30_MINUTES",
    "EVERY_HOUR",
    "EVERY_6_HOURS",
    "TWICE_DAILY",
    "CRON_TWICE_DAILY_9AM_9PM",
    "CRON_DAILY_MORNING",
    "CRON_DAILY_EVENING",
    "CRON_WEEKLY_MONDAY",
    # Schedule Client
    "get_schedule_client",
    "close_schedule_client",
    # Schedule Operations
    "create_schedule",
    "delete_schedule",
    "pause_schedule",
    "resume_schedule",
    "trigger_schedule",
    "get_schedule_info",
    "list_schedules",
    # Syndicate Helpers
    "setup_syndicate_schedules",
    "teardown_syndicate_schedules",
    # Memory Context Types
    "SwarmContext",
    # Memory Learning Activities
    "store_learning_activity",
    "query_learnings_activity",
    # Memory Knowledge Activities
    "store_knowledge_activity",
    "query_knowledge_activity",
    # Memory Article Activities
    "store_article_activity",
    "check_article_exists_activity",
    "query_articles_activity",
    # Memory Repo Activities
    "store_repo_activity",
    "check_repo_exists_activity",
    # Memory Paper Activities
    "store_paper_activity",
    "check_paper_exists_activity",
    # Memory Trend Activities
    "store_trend_snapshot_activity",
    "get_trend_snapshot_activity",
    # Swarm Context Activities
    "get_swarm_context_activity",
    "update_swarm_context_activity",
    # Cache Activities
    "cache_workflow_state_activity",
    "get_cached_workflow_state_activity",
    # Event Bridge
    "EventBridge",
    "BridgeConfig",
    "WorkflowTrigger",
    "WorkflowResultPublisher",
    "start_event_bridge",
    "create_k8s_triggers",
    "create_news_triggers",
    # Discord Activities
    "send_breaking_news_activity",
]
