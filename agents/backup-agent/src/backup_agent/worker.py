"""
Temporal worker for the backup agent.

This module starts a Temporal worker that polls for workflow and
activity tasks from the Temporal server.

Uses the generic AgentWorker class from core_agents for standardized
worker setup and command handling.
"""

import logging
import os
import sys

from backup_agent.activities import (
    backup_neo4j,
    backup_postgresql,
    backup_qdrant,
    cleanup_old_backups,
    post_backup_notification,
)
from backup_agent.workflows import (
    AllBackupsWorkflow,
    BackupCleanupWorkflow,
    DatabaseBackupWorkflow,
    ScheduledBackupsWorkflow,
)
from core_agents.worker import (
    AgentWorker,
    AgentWorkerConfig,
    CommandConfig,
    ScheduledWorkflowConfig,
)

logger = logging.getLogger(__name__)


# Custom command handlers
async def handle_backup(worker: AgentWorker) -> None:
    """Handle 'backup <database>' command."""
    if len(sys.argv) < 3:
        print("Usage: backup-agent-worker backup <postgresql|qdrant|neo4j>")
        sys.exit(1)

    database_type = sys.argv[2]
    result = await worker.run_single_workflow(
        DatabaseBackupWorkflow,
        f"backup-{database_type}",
        args=[database_type, False],  # Don't notify for manual runs
    )
    logger.info(f"Backup completed: {result}")


async def handle_backup_all(worker: AgentWorker) -> None:
    """Handle 'backup-all' command."""
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    result = await worker.run_single_workflow(
        AllBackupsWorkflow,
        "backup-all-manual",
        args=[discord_webhook],
    )
    logger.info(f"All backups completed: {result}")


async def handle_schedule(worker: AgentWorker) -> None:
    """Handle 'schedule' command with custom args from environment."""
    schedule_hour = int(os.environ.get("BACKUP_SCHEDULE_HOUR", "2"))
    retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", "7"))
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")

    sw_config = ScheduledWorkflowConfig(
        workflow_class=ScheduledBackupsWorkflow,
        workflow_id="backup-agent-scheduled",
        default_args=[schedule_hour, retention_days, discord_webhook],
    )

    await worker.start_scheduled_workflow(sw_config)


def create_worker() -> AgentWorker:
    """Create the backup agent worker."""
    config = AgentWorkerConfig(
        task_queue="backup-agent",
        name="backup-agent",
        description="Database backup agent",
        workflows=[
            DatabaseBackupWorkflow,
            AllBackupsWorkflow,
            ScheduledBackupsWorkflow,
            BackupCleanupWorkflow,
        ],
        activities=[
            backup_postgresql,
            backup_qdrant,
            backup_neo4j,
            cleanup_old_backups,
            post_backup_notification,
        ],
        custom_commands=[
            CommandConfig(
                name="schedule",
                description="Start the scheduled backup workflow",
                handler=handle_schedule,
            ),
            CommandConfig(
                name="backup",
                description="Run a single backup",
                handler=handle_backup,
                args=["database"],
            ),
            CommandConfig(
                name="backup-all",
                description="Run all backups",
                handler=handle_backup_all,
            ),
        ],
    )
    return AgentWorker(config)


def main() -> None:
    """Main entry point for the worker."""
    worker = create_worker()
    worker.run()


if __name__ == "__main__":
    main()
