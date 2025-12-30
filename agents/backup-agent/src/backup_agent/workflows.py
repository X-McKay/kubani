"""Temporal workflows for backup operations."""

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from backup_agent.activities import (
        backup_neo4j,
        backup_postgresql,
        backup_qdrant,
        cleanup_old_backups,
        post_backup_notification,
    )
    from backup_agent.models import (
        BackupConfig,
        DatabaseType,
        DEFAULT_BACKUP_CONFIGS,
    )


@workflow.defn
class DatabaseBackupWorkflow:
    """
    Workflow to backup a single database.

    This workflow:
    1. Runs the backup for the specified database type
    2. Optionally posts notification to Discord
    """

    @workflow.run
    async def run(
        self,
        database_type: str,
        notify: bool = True,
        config_override: dict | None = None,
    ) -> dict[str, Any]:
        """
        Execute backup for a single database.

        Args:
            database_type: Type of database (postgresql, qdrant, neo4j)
            notify: Whether to post Discord notification
            config_override: Optional config overrides

        Returns:
            Backup result dict
        """
        workflow.logger.info(f"Starting backup for {database_type}")

        db_type = DatabaseType(database_type)
        config = DEFAULT_BACKUP_CONFIGS[db_type].model_dump()
        if config_override:
            config.update(config_override)

        # Activity options with retry
        activity_options = {
            "start_to_close_timeout": timedelta(minutes=30),
            "retry_policy": RetryPolicy(
                initial_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=5),
                maximum_attempts=3,
            ),
        }

        # Select the appropriate backup activity
        backup_activities = {
            DatabaseType.POSTGRESQL: backup_postgresql,
            DatabaseType.QDRANT: backup_qdrant,
            DatabaseType.NEO4J: backup_neo4j,
        }

        backup_activity = backup_activities[db_type]

        # Execute backup
        result = await workflow.execute_activity(
            backup_activity,
            config,
            **activity_options,
        )

        # Post notification if requested
        if notify:
            discord_url = workflow.info().search_attributes.get("discord_webhook_url", [""])[0]
            if discord_url:
                await workflow.execute_activity(
                    post_backup_notification,
                    [[result], discord_url],
                    start_to_close_timeout=timedelta(minutes=1),
                )

        workflow.logger.info(f"Backup workflow completed: {result.get('status')}")
        return result


@workflow.defn
class AllBackupsWorkflow:
    """
    Workflow to backup all databases.

    This workflow runs backups for all configured databases
    and sends a consolidated notification.
    """

    @workflow.run
    async def run(self, discord_webhook_url: str | None = None) -> dict[str, Any]:
        """
        Execute backups for all databases.

        Args:
            discord_webhook_url: Optional Discord webhook URL for notifications

        Returns:
            Dict with all backup results
        """
        workflow.logger.info("Starting backup for all databases")

        results = []

        # Activity options
        activity_options = {
            "start_to_close_timeout": timedelta(minutes=30),
            "retry_policy": RetryPolicy(
                initial_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=5),
                maximum_attempts=3,
            ),
        }

        # Backup each database sequentially
        for db_type, config in DEFAULT_BACKUP_CONFIGS.items():
            workflow.logger.info(f"Backing up {db_type.value}")

            backup_activities = {
                DatabaseType.POSTGRESQL: backup_postgresql,
                DatabaseType.QDRANT: backup_qdrant,
                DatabaseType.NEO4J: backup_neo4j,
            }

            try:
                result = await workflow.execute_activity(
                    backup_activities[db_type],
                    config.model_dump(),
                    **activity_options,
                )
                results.append(result)
            except Exception as e:
                workflow.logger.error(f"Backup failed for {db_type.value}: {e}")
                results.append({
                    "database": db_type.value,
                    "status": "failed",
                    "error": str(e),
                })

        # Send consolidated notification
        if discord_webhook_url:
            await workflow.execute_activity(
                post_backup_notification,
                [results, discord_webhook_url],
                start_to_close_timeout=timedelta(minutes=1),
            )

        success_count = sum(1 for r in results if r.get("status") == "success")
        workflow.logger.info(f"All backups completed: {success_count}/{len(results)} successful")

        return {
            "results": results,
            "success_count": success_count,
            "total_count": len(results),
        }


@workflow.defn
class ScheduledBackupsWorkflow:
    """
    Long-running workflow that schedules daily backups.

    This workflow runs continuously and triggers backups
    at the configured hour each day.
    """

    @workflow.run
    async def run(
        self,
        schedule_hour: int = 2,
        retention_days: int = 7,
        discord_webhook_url: str | None = None,
    ) -> None:
        """
        Run scheduled backups indefinitely.

        Args:
            schedule_hour: Hour to run backups (UTC, default: 2 AM)
            retention_days: Days to keep backups (default: 7)
            discord_webhook_url: Discord webhook for notifications
        """
        workflow.logger.info(
            f"Starting scheduled backups at {schedule_hour}:00 UTC, "
            f"retention: {retention_days} days"
        )

        while True:
            # Calculate time until next backup
            now = workflow.now()
            next_backup = now.replace(hour=schedule_hour, minute=0, second=0, microsecond=0)

            if now.hour >= schedule_hour:
                # Already past schedule time today, schedule for tomorrow
                next_backup = next_backup + timedelta(days=1)

            wait_seconds = (next_backup - now).total_seconds()
            workflow.logger.info(f"Next backup in {wait_seconds/3600:.1f} hours")

            # Wait until backup time
            await workflow.sleep(timedelta(seconds=wait_seconds))

            # Run all backups
            workflow.logger.info("Triggering scheduled backup")
            try:
                await workflow.execute_child_workflow(
                    AllBackupsWorkflow.run,
                    discord_webhook_url,
                    id=f"backup-all-{workflow.now().strftime('%Y%m%d-%H%M%S')}",
                )
            except Exception as e:
                workflow.logger.error(f"Scheduled backup failed: {e}")

            # Cleanup old backups
            workflow.logger.info("Running backup cleanup")
            try:
                await workflow.execute_activity(
                    cleanup_old_backups,
                    ["/backups/databases", retention_days],
                    start_to_close_timeout=timedelta(minutes=10),
                )
            except Exception as e:
                workflow.logger.error(f"Backup cleanup failed: {e}")


@workflow.defn
class BackupCleanupWorkflow:
    """Workflow to clean up old backups."""

    @workflow.run
    async def run(self, backup_dir: str, retention_days: int) -> dict:
        """
        Clean up old backups.

        Args:
            backup_dir: Base backup directory
            retention_days: Days to keep backups

        Returns:
            Cleanup results
        """
        workflow.logger.info(f"Cleaning up backups older than {retention_days} days")

        result = await workflow.execute_activity(
            cleanup_old_backups,
            [backup_dir, retention_days],
            start_to_close_timeout=timedelta(minutes=10),
        )

        workflow.logger.info(f"Cleanup completed: {result}")
        return result
