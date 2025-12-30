"""Tests for backup agent models."""

from datetime import datetime

import pytest

from backup_agent.models import (
    BackupConfig,
    BackupResult,
    BackupStatus,
    DatabaseType,
    DEFAULT_BACKUP_CONFIGS,
)


def test_database_type_enum():
    """Test DatabaseType enum values."""
    assert DatabaseType.POSTGRESQL.value == "postgresql"
    assert DatabaseType.QDRANT.value == "qdrant"
    assert DatabaseType.NEO4J.value == "neo4j"


def test_backup_status_enum():
    """Test BackupStatus enum values."""
    assert BackupStatus.SUCCESS.value == "success"
    assert BackupStatus.FAILED.value == "failed"


def test_backup_result_success():
    """Test BackupResult for successful backup."""
    result = BackupResult(
        database=DatabaseType.POSTGRESQL,
        status=BackupStatus.SUCCESS,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        backup_path="/backups/databases/postgresql/test.sql.gz",
        size_bytes=1024 * 1024,  # 1 MB
        duration_seconds=10.5,
    )

    assert result.status == BackupStatus.SUCCESS
    assert "✅" in result.format_for_discord()
    assert "postgresql" in result.format_for_discord()


def test_backup_result_failed():
    """Test BackupResult for failed backup."""
    result = BackupResult(
        database=DatabaseType.QDRANT,
        status=BackupStatus.FAILED,
        started_at=datetime.now(),
        error="Connection refused",
    )

    assert result.status == BackupStatus.FAILED
    assert "❌" in result.format_for_discord()
    assert "Connection refused" in result.format_for_discord()


def test_default_configs_exist():
    """Test that default configs exist for all database types."""
    for db_type in DatabaseType:
        assert db_type in DEFAULT_BACKUP_CONFIGS
        config = DEFAULT_BACKUP_CONFIGS[db_type]
        assert isinstance(config, BackupConfig)
        assert config.database == db_type
