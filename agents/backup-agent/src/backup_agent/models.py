"""Pydantic models for backup agent."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DatabaseType(str, Enum):
    """Supported database types for backup."""

    POSTGRESQL = "postgresql"
    QDRANT = "qdrant"
    NEO4J = "neo4j"


class BackupStatus(str, Enum):
    """Status of a backup operation."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class BackupResult(BaseModel):
    """Result of a backup operation."""

    database: DatabaseType
    status: BackupStatus
    started_at: datetime
    completed_at: datetime | None = None
    backup_path: str | None = None
    size_bytes: int | None = None
    error: str | None = None
    duration_seconds: float | None = None

    def format_for_discord(self) -> str:
        """Format the result for Discord notification."""
        if self.status == BackupStatus.SUCCESS:
            size_mb = (self.size_bytes or 0) / (1024 * 1024)
            return (
                f"✅ **{self.database.value}** backup completed\n"
                f"📁 Size: {size_mb:.1f} MB\n"
                f"⏱️ Duration: {self.duration_seconds:.1f}s\n"
                f"📍 Path: `{self.backup_path}`"
            )
        else:
            return f"❌ **{self.database.value}** backup failed\n⚠️ Error: {self.error}"


class BackupConfig(BaseModel):
    """Configuration for a database backup."""

    database: DatabaseType
    host: str = Field(description="Database host")
    port: int = Field(description="Database port")
    namespace: str = Field(default="database", description="Kubernetes namespace")
    backup_dir: str = Field(default="/backups/databases", description="Backup directory path")

    # PostgreSQL specific
    pg_database: str | None = None
    pg_user: str | None = None

    # Qdrant specific (uses HTTP API for snapshots)
    qdrant_collection: str | None = None

    # Neo4j specific
    neo4j_database: str | None = None


# Default backup configurations
DEFAULT_BACKUP_CONFIGS = {
    DatabaseType.POSTGRESQL: BackupConfig(
        database=DatabaseType.POSTGRESQL,
        host="postgresql.database.svc.cluster.local",
        port=5432,
        namespace="database",
        pg_database="temporal",
        pg_user="temporal",
    ),
    DatabaseType.QDRANT: BackupConfig(
        database=DatabaseType.QDRANT,
        host="qdrant.database.svc.cluster.local",
        port=6333,
        namespace="database",
    ),
    DatabaseType.NEO4J: BackupConfig(
        database=DatabaseType.NEO4J,
        host="neo4j.database.svc.cluster.local",
        port=7687,
        namespace="database",
        neo4j_database="neo4j",
    ),
}
