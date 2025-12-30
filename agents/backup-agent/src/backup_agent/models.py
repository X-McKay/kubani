"""Pydantic models for backup agent."""

from datetime import datetime
from enum import Enum
from typing import Optional

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
    completed_at: Optional[datetime] = None
    backup_path: Optional[str] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None

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
            return (
                f"❌ **{self.database.value}** backup failed\n"
                f"⚠️ Error: {self.error}"
            )


class BackupConfig(BaseModel):
    """Configuration for a database backup."""

    database: DatabaseType
    host: str = Field(description="Database host")
    port: int = Field(description="Database port")
    namespace: str = Field(default="database", description="Kubernetes namespace")
    backup_dir: str = Field(default="/backups/databases", description="Backup directory path")

    # PostgreSQL specific
    pg_database: Optional[str] = None
    pg_user: Optional[str] = None

    # Qdrant specific (uses HTTP API for snapshots)
    qdrant_collection: Optional[str] = None

    # Neo4j specific
    neo4j_database: Optional[str] = None


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
