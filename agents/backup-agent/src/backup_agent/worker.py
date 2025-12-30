"""
Temporal worker for the backup agent.

This module starts a Temporal worker that polls for workflow and
activity tasks from the Temporal server.
"""

import asyncio
import logging
import os
import sys

from temporalio.client import Client
from temporalio.worker import Worker

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Task queue name for this agent
TASK_QUEUE = "backup-agent"


async def run_worker() -> None:
    """
    Connect to Temporal and run the worker.

    The worker will poll for tasks on the backup-agent task queue
    and execute workflows and activities as assigned.
    """
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    logger.info(f"Starting worker on task queue: {TASK_QUEUE}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
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
    )

    logger.info("Worker started, polling for tasks...")
    await worker.run()


async def start_scheduled_workflow() -> None:
    """Start the scheduled backup workflow if not already running."""
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    schedule_hour = int(os.environ.get("BACKUP_SCHEDULE_HOUR", "2"))
    retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", "7"))
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")

    logger.info(f"Connecting to Temporal at {temporal_host}")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    workflow_id = "backup-agent-scheduled"

    try:
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status.name == "RUNNING":
            logger.info(f"Scheduled workflow already running: {workflow_id}")
            return
    except Exception:
        pass

    logger.info(
        f"Starting scheduled backup workflow at {schedule_hour}:00 UTC, "
        f"retention: {retention_days} days"
    )

    await client.start_workflow(
        ScheduledBackupsWorkflow.run,
        args=[schedule_hour, retention_days, discord_webhook],
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    logger.info(f"Scheduled workflow started: {workflow_id}")


async def run_single_backup(database_type: str) -> None:
    """Run a single backup for the specified database."""
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    logger.info(f"Starting backup for {database_type}")

    handle = await client.start_workflow(
        DatabaseBackupWorkflow.run,
        args=[database_type, False],  # Don't notify for manual runs
        id=f"backup-{database_type}-{asyncio.get_event_loop().time()}",
        task_queue=TASK_QUEUE,
    )

    result = await handle.result()
    logger.info(f"Backup completed: {result}")
    return result


async def run_all_backups() -> None:
    """Run backups for all databases."""
    temporal_host = os.environ.get(
        "TEMPORAL_HOST",
        "temporal-frontend.temporal.svc.cluster.local:7233",
    )
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")

    client = await Client.connect(
        temporal_host,
        namespace=temporal_namespace,
    )

    logger.info("Starting backup for all databases")

    handle = await client.start_workflow(
        AllBackupsWorkflow.run,
        discord_webhook,
        id=f"backup-all-manual-{asyncio.get_event_loop().time()}",
        task_queue=TASK_QUEUE,
    )

    result = await handle.result()
    logger.info(f"All backups completed: {result}")
    return result


def main() -> None:
    """
    Main entry point for the worker.

    Supports the following commands:
    - worker: Run the Temporal worker (default)
    - schedule: Start the scheduled workflow
    - backup <database>: Run a single backup
    - backup-all: Run all backups
    """
    command = sys.argv[1] if len(sys.argv) > 1 else "worker"

    if command == "worker":
        asyncio.run(run_worker())
    elif command == "schedule":
        asyncio.run(start_scheduled_workflow())
    elif command == "backup":
        if len(sys.argv) < 3:
            print("Usage: backup-agent-worker backup <postgresql|qdrant|neo4j>")
            sys.exit(1)
        asyncio.run(run_single_backup(sys.argv[2]))
    elif command == "backup-all":
        asyncio.run(run_all_backups())
    else:
        print(f"Unknown command: {command}")
        print("Usage: backup-agent-worker [worker|schedule|backup <db>|backup-all]")
        sys.exit(1)


if __name__ == "__main__":
    main()
