# Backup Agent

Database backup agent with Temporal workflows and Discord notifications.

## Features

- Scheduled backups for PostgreSQL, Qdrant, and Neo4j
- Writes backups to NAS storage (`/volume1/kubani/backups/`)
- Discord notifications on success/failure
- Configurable retention policy
- Manual backup triggers

## Workflows

- `ScheduledBackupWorkflow` - Runs backups on a schedule (default: daily at 2 AM)
- `DatabaseBackupWorkflow` - Performs a single backup of a specified database
- `BackupCleanupWorkflow` - Removes old backups based on retention policy

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPORAL_HOST` | `temporal-frontend.temporal.svc.cluster.local:7233` | Temporal server address |
| `TEMPORAL_NAMESPACE` | `default` | Temporal namespace |
| `DISCORD_WEBHOOK_URL` | Required | Discord webhook for notifications |
| `BACKUP_RETENTION_DAYS` | `7` | Days to keep backups |
| `BACKUP_SCHEDULE_HOUR` | `2` | Hour to run daily backups (UTC) |

## Usage

```bash
# Run the worker
backup-agent-worker worker

# Start scheduled backups
backup-agent-worker schedule

# Run a single backup
backup-agent-worker backup postgresql
backup-agent-worker backup qdrant
backup-agent-worker backup neo4j

# Run all backups now
backup-agent-worker backup-all
```
