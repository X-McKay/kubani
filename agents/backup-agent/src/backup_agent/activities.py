"""Temporal activities for backup operations."""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

import httpx
from temporalio import activity

from backup_agent.models import (
    BackupConfig,
    BackupResult,
    BackupStatus,
    DatabaseType,
    DEFAULT_BACKUP_CONFIGS,
)

logger = logging.getLogger(__name__)


def get_backup_path(database: DatabaseType, backup_dir: str) -> str:
    """Generate backup file path with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extensions = {
        DatabaseType.POSTGRESQL: "sql.gz",
        DatabaseType.QDRANT: "snapshot",
        DatabaseType.NEO4J: "dump",
    }
    ext = extensions.get(database, "bak")
    return f"{backup_dir}/{database.value}/{database.value}_{timestamp}.{ext}"


@activity.defn
async def backup_postgresql(config: dict) -> dict:
    """
    Backup PostgreSQL database using pg_dump.

    Args:
        config: Backup configuration as dict

    Returns:
        BackupResult as dict
    """
    cfg = BackupConfig.model_validate(config)
    started_at = datetime.now()
    backup_path = get_backup_path(DatabaseType.POSTGRESQL, cfg.backup_dir)

    activity.logger.info(f"Starting PostgreSQL backup to {backup_path}")

    try:
        # Ensure backup directory exists
        Path(backup_path).parent.mkdir(parents=True, exist_ok=True)

        # Get password from environment or secret
        pg_password = os.environ.get("PGPASSWORD", "")

        # Run pg_dump via kubectl exec into the PostgreSQL pod
        cmd = [
            "kubectl", "exec", "-n", cfg.namespace,
            "postgresql-0", "--",
            "pg_dump", "-U", cfg.pg_user or "postgres",
            "-d", cfg.pg_database or "postgres",
            "--format=custom",
        ]

        # For now, we'll use a simpler approach - run pg_dump from within cluster
        # The backup volume is mounted at /backups
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,  # 10 minute timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr.decode()}")

        # Write output to backup file (compressed)
        import gzip
        with gzip.open(backup_path, 'wb') as f:
            f.write(result.stdout)

        completed_at = datetime.now()
        size_bytes = Path(backup_path).stat().st_size

        return BackupResult(
            database=DatabaseType.POSTGRESQL,
            status=BackupStatus.SUCCESS,
            started_at=started_at,
            completed_at=completed_at,
            backup_path=backup_path,
            size_bytes=size_bytes,
            duration_seconds=(completed_at - started_at).total_seconds(),
        ).model_dump()

    except Exception as e:
        activity.logger.error(f"PostgreSQL backup failed: {e}")
        return BackupResult(
            database=DatabaseType.POSTGRESQL,
            status=BackupStatus.FAILED,
            started_at=started_at,
            completed_at=datetime.now(),
            error=str(e),
        ).model_dump()


@activity.defn
async def backup_qdrant(config: dict) -> dict:
    """
    Backup Qdrant using its snapshot API.

    Args:
        config: Backup configuration as dict

    Returns:
        BackupResult as dict
    """
    cfg = BackupConfig.model_validate(config)
    started_at = datetime.now()
    backup_path = get_backup_path(DatabaseType.QDRANT, cfg.backup_dir)

    activity.logger.info(f"Starting Qdrant backup to {backup_path}")

    try:
        Path(backup_path).parent.mkdir(parents=True, exist_ok=True)

        # Qdrant snapshot API - create snapshot for all collections
        qdrant_url = f"http://{cfg.host}:{cfg.port}"

        async with httpx.AsyncClient(timeout=300) as client:
            # Get list of collections
            collections_resp = await client.get(f"{qdrant_url}/collections")
            collections_resp.raise_for_status()
            collections = collections_resp.json().get("result", {}).get("collections", [])

            # Create snapshot for each collection
            snapshots = []
            for coll in collections:
                coll_name = coll["name"]
                activity.logger.info(f"Creating snapshot for collection: {coll_name}")

                snap_resp = await client.post(
                    f"{qdrant_url}/collections/{coll_name}/snapshots"
                )
                snap_resp.raise_for_status()
                snapshot_name = snap_resp.json().get("result", {}).get("name")
                snapshots.append({"collection": coll_name, "snapshot": snapshot_name})

            # Download snapshots
            total_size = 0
            for snap in snapshots:
                coll_name = snap["collection"]
                snap_name = snap["snapshot"]
                snap_path = f"{cfg.backup_dir}/{DatabaseType.QDRANT.value}/{coll_name}_{snap_name}"

                download_resp = await client.get(
                    f"{qdrant_url}/collections/{coll_name}/snapshots/{snap_name}",
                    follow_redirects=True,
                )
                download_resp.raise_for_status()

                with open(snap_path, 'wb') as f:
                    f.write(download_resp.content)

                total_size += len(download_resp.content)

        completed_at = datetime.now()

        return BackupResult(
            database=DatabaseType.QDRANT,
            status=BackupStatus.SUCCESS,
            started_at=started_at,
            completed_at=completed_at,
            backup_path=f"{cfg.backup_dir}/{DatabaseType.QDRANT.value}/",
            size_bytes=total_size,
            duration_seconds=(completed_at - started_at).total_seconds(),
        ).model_dump()

    except Exception as e:
        activity.logger.error(f"Qdrant backup failed: {e}")
        return BackupResult(
            database=DatabaseType.QDRANT,
            status=BackupStatus.FAILED,
            started_at=started_at,
            completed_at=datetime.now(),
            error=str(e),
        ).model_dump()


@activity.defn
async def backup_neo4j(config: dict) -> dict:
    """
    Backup Neo4j database.

    Args:
        config: Backup configuration as dict

    Returns:
        BackupResult as dict
    """
    cfg = BackupConfig.model_validate(config)
    started_at = datetime.now()
    backup_path = get_backup_path(DatabaseType.NEO4J, cfg.backup_dir)

    activity.logger.info(f"Starting Neo4j backup to {backup_path}")

    try:
        Path(backup_path).parent.mkdir(parents=True, exist_ok=True)

        # Neo4j backup via kubectl exec
        # Note: neo4j-admin backup requires enterprise edition
        # For community edition, we'll do a database dump
        cmd = [
            "kubectl", "exec", "-n", cfg.namespace,
            "neo4j-0", "--",
            "neo4j-admin", "database", "dump",
            cfg.neo4j_database or "neo4j",
            "--to-stdout",
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(f"neo4j dump failed: {result.stderr.decode()}")

        with open(backup_path, 'wb') as f:
            f.write(result.stdout)

        completed_at = datetime.now()
        size_bytes = Path(backup_path).stat().st_size

        return BackupResult(
            database=DatabaseType.NEO4J,
            status=BackupStatus.SUCCESS,
            started_at=started_at,
            completed_at=completed_at,
            backup_path=backup_path,
            size_bytes=size_bytes,
            duration_seconds=(completed_at - started_at).total_seconds(),
        ).model_dump()

    except Exception as e:
        activity.logger.error(f"Neo4j backup failed: {e}")
        return BackupResult(
            database=DatabaseType.NEO4J,
            status=BackupStatus.FAILED,
            started_at=started_at,
            completed_at=datetime.now(),
            error=str(e),
        ).model_dump()


@activity.defn
async def cleanup_old_backups(backup_dir: str, retention_days: int) -> dict:
    """
    Remove backups older than retention_days.

    Args:
        backup_dir: Base backup directory
        retention_days: Number of days to keep backups

    Returns:
        Dict with cleanup results
    """
    activity.logger.info(f"Cleaning up backups older than {retention_days} days")

    import time
    cutoff_time = time.time() - (retention_days * 86400)
    deleted_files = []
    deleted_bytes = 0

    try:
        backup_path = Path(backup_dir)
        if not backup_path.exists():
            return {"deleted_files": 0, "deleted_bytes": 0}

        for db_dir in backup_path.iterdir():
            if not db_dir.is_dir():
                continue

            for backup_file in db_dir.iterdir():
                if backup_file.is_file() and backup_file.stat().st_mtime < cutoff_time:
                    size = backup_file.stat().st_size
                    backup_file.unlink()
                    deleted_files.append(str(backup_file))
                    deleted_bytes += size
                    activity.logger.info(f"Deleted old backup: {backup_file}")

        return {
            "deleted_files": len(deleted_files),
            "deleted_bytes": deleted_bytes,
            "files": deleted_files,
        }

    except Exception as e:
        activity.logger.error(f"Cleanup failed: {e}")
        return {"error": str(e), "deleted_files": 0, "deleted_bytes": 0}


@activity.defn
async def post_backup_notification(results: list[dict], webhook_url: str) -> bool:
    """
    Post backup results to Discord.

    Args:
        results: List of BackupResult dicts
        webhook_url: Discord webhook URL

    Returns:
        True if notification was sent successfully
    """
    activity.logger.info("Posting backup notification to Discord")

    try:
        # Build notification message
        success_count = sum(1 for r in results if r.get("status") == "success")
        total_count = len(results)

        if success_count == total_count:
            emoji = "✅"
            title = "All Backups Completed Successfully"
        elif success_count > 0:
            emoji = "⚠️"
            title = f"Backups Partially Completed ({success_count}/{total_count})"
        else:
            emoji = "❌"
            title = "All Backups Failed"

        # Format individual results
        details = []
        for r in results:
            result = BackupResult.model_validate(r)
            details.append(result.format_for_discord())

        message = f"{emoji} **{title}**\n\n" + "\n\n".join(details)

        # Post to Discord
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json={"content": message},
            )
            response.raise_for_status()

        activity.logger.info("Discord notification sent successfully")
        return True

    except Exception as e:
        activity.logger.error(f"Failed to post Discord notification: {e}")
        return False
