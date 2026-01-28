# Phase 1: Schema Migration

**Duration:** ~1 week
**Prerequisites:** None
**Outcome:** Database schema ready for registry-first architecture

## Overview

This phase adds new tables and columns to support OCI-based storage and version lifecycle management. The migration is non-breaking - existing tables remain functional during the transition.

---

## Task 1.1: Create Alembic Migration File

**File:** `platform/registry/alembic/versions/20260128_0003_registry_source_of_truth.py`

**Changes:**

### 1.1.1 Create `syndicates` Table

```python
op.create_table('syndicates',
    sa.Column('id', sa.String(255), primary_key=True),
    sa.Column('name', sa.String(255), nullable=False, unique=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('current_version', sa.String(50), nullable=True),
    sa.Column('oci_repository', sa.String(512), nullable=True),
    sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
    sa.Column('created_by', sa.String(255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
)
op.create_index('ix_syndicates_status', 'syndicates', ['status'])
```

### 1.1.2 Create `syndicate_versions` Table

```python
op.create_table('syndicate_versions',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('syndicate_id', sa.String(255), sa.ForeignKey('syndicates.id', ondelete='CASCADE'), nullable=False),
    sa.Column('version', sa.String(50), nullable=False),
    sa.Column('oci_tag', sa.String(100), nullable=True),
    sa.Column('oci_digest', sa.String(128), nullable=True),
    sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
    sa.Column('agent_refs', postgresql.JSONB(), nullable=False, server_default='[]'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.String(255), nullable=True),
    sa.Column('changelog', sa.Text(), nullable=True),
    sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('promoted_by', sa.String(255), nullable=True),
    sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
    sa.UniqueConstraint('syndicate_id', 'version', name='uq_syndicate_version'),
)
op.create_index('ix_syndicate_versions_status', 'syndicate_versions', ['status'])
```

### 1.1.3 Create `agent_versions` Table

```python
op.create_table('agent_versions',
    sa.Column('id', sa.Integer(), primary_key=True),
    sa.Column('agent_id', sa.String(255), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False),
    sa.Column('version', sa.String(50), nullable=False),
    sa.Column('oci_tag', sa.String(100), nullable=True),
    sa.Column('oci_digest', sa.String(128), nullable=True),
    sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.String(255), nullable=True),
    sa.Column('changelog', sa.Text(), nullable=True),
    sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('promoted_by', sa.String(255), nullable=True),
    sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
    sa.UniqueConstraint('agent_id', 'version', name='uq_agent_version'),
)
op.create_index('ix_agent_versions_status', 'agent_versions', ['status'])
```

### 1.1.4 Add OCI Columns to `agents` Table

```python
op.add_column('agents', sa.Column('current_version', sa.String(50), nullable=True))
op.add_column('agents', sa.Column('oci_repository', sa.String(512), nullable=True))
op.add_column('agents', sa.Column('created_by', sa.String(255), nullable=True))
# Note: 'status' column already exists but may need enum expansion
```

### 1.1.5 Add OCI Columns to `skills` Table

```python
op.add_column('skills', sa.Column('oci_repository', sa.String(512), nullable=True))
op.add_column('skills', sa.Column('domain', sa.String(100), nullable=True))
op.add_column('skills', sa.Column('confidence', sa.Float(), server_default='0.5'))
op.add_column('skills', sa.Column('success_count', sa.Integer(), server_default='0'))
op.add_column('skills', sa.Column('failure_count', sa.Integer(), server_default='0'))
op.add_column('skills', sa.Column('requires_approval', sa.Boolean(), server_default='false'))
op.add_column('skills', sa.Column('last_used', sa.DateTime(timezone=True), nullable=True))
op.add_column('skills', sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True))
```

### 1.1.6 Add OCI Columns to `skill_versions` Table

```python
op.add_column('skill_versions', sa.Column('oci_tag', sa.String(100), nullable=True))
op.add_column('skill_versions', sa.Column('oci_digest', sa.String(128), nullable=True))
op.add_column('skill_versions', sa.Column('status', sa.String(50), server_default='draft'))
op.add_column('skill_versions', sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True))
op.add_column('skill_versions', sa.Column('promoted_by', sa.String(255), nullable=True))
op.create_index('ix_skill_versions_status', 'skill_versions', ['status'])
```

**Acceptance Criteria:**
- [ ] Migration file created with proper revision chain
- [ ] All new tables have appropriate indexes
- [ ] Foreign key constraints with CASCADE delete
- [ ] Default values for status fields
- [ ] Downgrade function properly reverses all changes

---

## Task 1.2: Update SQLAlchemy Models

**File:** `platform/registry/src/kubani_registry/db/models.py`

### 1.2.1 Add `Syndicate` Model

```python
class Syndicate(Base):
    """Syndicate (multi-agent orchestration) definition."""

    __tablename__ = "syndicates"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[str | None] = mapped_column(String(50))
    oci_repository: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    versions: Mapped[list["SyndicateVersion"]] = relationship(
        back_populates="syndicate", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "current_version": self.current_version,
            "oci_repository": self.oci_repository,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata_ or {},
        }
```

### 1.2.2 Add `SyndicateVersion` Model

```python
class SyndicateVersion(Base):
    """Version of a syndicate."""

    __tablename__ = "syndicate_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    syndicate_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("syndicates.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    oci_tag: Mapped[str | None] = mapped_column(String(100))
    oci_digest: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    agent_refs: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255))
    changelog: Mapped[str | None] = mapped_column(Text)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_by: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    syndicate: Mapped["Syndicate"] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("syndicate_id", "version", name="uq_syndicate_version"),)
```

### 1.2.3 Add `AgentVersion` Model

```python
class AgentVersion(Base):
    """Version of an agent definition."""

    __tablename__ = "agent_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    oci_tag: Mapped[str | None] = mapped_column(String(100))
    oci_digest: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String(255))
    changelog: Mapped[str | None] = mapped_column(Text)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promoted_by: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    agent: Mapped["Agent"] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("agent_id", "version", name="uq_agent_version"),)
```

### 1.2.4 Update `Agent` Model

Add to existing `Agent` class:

```python
# Add these fields
current_version: Mapped[str | None] = mapped_column(String(50))
oci_repository: Mapped[str | None] = mapped_column(String(512))
created_by: Mapped[str | None] = mapped_column(String(255))

# Add relationship
versions: Mapped[list["AgentVersion"]] = relationship(
    back_populates="agent", cascade="all, delete-orphan"
)
```

### 1.2.5 Update `Skill` Model

Add to existing `Skill` class:

```python
# Add these fields
oci_repository: Mapped[str | None] = mapped_column(String(512))
domain: Mapped[str | None] = mapped_column(String(100))
confidence: Mapped[float] = mapped_column(Float, default=0.5)
success_count: Mapped[int] = mapped_column(Integer, default=0)
failure_count: Mapped[int] = mapped_column(Integer, default=0)
requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

### 1.2.6 Update `SkillVersion` Model

Add to existing `SkillVersion` class:

```python
# Add these fields
oci_tag: Mapped[str | None] = mapped_column(String(100))
oci_digest: Mapped[str | None] = mapped_column(String(128))
status: Mapped[str] = mapped_column(String(50), default="draft")
promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
promoted_by: Mapped[str | None] = mapped_column(String(255))
```

### 1.2.7 Update `__init__.py` Exports

**File:** `platform/registry/src/kubani_registry/db/__init__.py`

```python
from .models import (
    Agent,
    AgentCapability,
    AgentVersion,  # NEW
    Base,
    Deployment,
    Endpoint,
    EndpointDependency,
    MCPPolicy,
    MCPServer,
    Model,
    ModelEndpoint,
    Skill,
    SkillEvaluation,
    SkillMetadata,
    SkillSyncStatus,
    SkillVersion,
    Syndicate,  # NEW
    SyndicateVersion,  # NEW
)
```

**Acceptance Criteria:**
- [ ] All new models added with proper relationships
- [ ] Existing models updated with new fields
- [ ] `to_dict()` methods updated for all modified models
- [ ] Exports updated in `__init__.py`

---

## Task 1.3: Add Status Enum Constants

**File:** `platform/registry/src/kubani_registry/constants.py` (new file)

```python
"""Constants for the Kubani Registry."""

from enum import Enum


class ResourceStatus(str, Enum):
    """Lifecycle status for skills, agents, and syndicates."""

    DRAFT = "draft"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"

    @classmethod
    def promotion_order(cls) -> list["ResourceStatus"]:
        """Return the valid promotion order."""
        return [cls.DRAFT, cls.TESTING, cls.STAGING, cls.PRODUCTION]

    def can_promote_to(self, target: "ResourceStatus") -> bool:
        """Check if promotion to target status is valid."""
        order = self.promotion_order()
        if self not in order or target not in order:
            return False
        return order.index(target) == order.index(self) + 1


class ResourceType(str, Enum):
    """Types of resources in the registry."""

    SKILL = "skill"
    AGENT = "agent"
    SYNDICATE = "syndicate"
```

**Acceptance Criteria:**
- [ ] Constants file created
- [ ] Status enum with promotion logic
- [ ] Resource type enum

---

## Task 1.4: Run and Test Migration

### 1.4.1 Run Migration Locally

```bash
cd platform/registry

# Ensure database is running
# Apply migration
alembic upgrade head

# Verify tables exist
psql $DATABASE_URL -c "\dt"
psql $DATABASE_URL -c "\d syndicates"
psql $DATABASE_URL -c "\d syndicate_versions"
psql $DATABASE_URL -c "\d agent_versions"
```

### 1.4.2 Test Downgrade

```bash
# Test rollback
alembic downgrade -1

# Verify tables removed
psql $DATABASE_URL -c "\dt"

# Re-apply
alembic upgrade head
```

### 1.4.3 Add Migration Tests

**File:** `platform/registry/tests/test_migrations.py`

```python
"""Tests for database migrations."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


def test_upgrade_creates_new_tables(alembic_config, db_engine):
    """Test that upgrade creates syndicates and version tables."""
    command.upgrade(alembic_config, "head")

    inspector = inspect(db_engine)
    tables = inspector.get_table_names()

    assert "syndicates" in tables
    assert "syndicate_versions" in tables
    assert "agent_versions" in tables


def test_skills_has_oci_columns(alembic_config, db_engine):
    """Test that skills table has new OCI columns."""
    command.upgrade(alembic_config, "head")

    inspector = inspect(db_engine)
    columns = {c["name"] for c in inspector.get_columns("skills")}

    assert "oci_repository" in columns
    assert "domain" in columns
    assert "confidence" in columns


def test_downgrade_removes_tables(alembic_config, db_engine):
    """Test that downgrade removes new tables."""
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "-1")

    inspector = inspect(db_engine)
    tables = inspector.get_table_names()

    assert "syndicates" not in tables
    assert "syndicate_versions" not in tables
    assert "agent_versions" not in tables
```

**Acceptance Criteria:**
- [ ] Migration runs successfully
- [ ] Downgrade works correctly
- [ ] All tests pass
- [ ] No data loss in existing tables

---

## Task 1.5: Update Model Tests

**File:** `platform/registry/tests/test_models.py`

Add tests for new models:

```python
def test_syndicate_model(session):
    """Test Syndicate model creation and relationships."""
    syndicate = Syndicate(
        id="k8s-monitor",
        name="K8s Monitor",
        description="Kubernetes monitoring syndicate",
        status="draft",
        created_by="human",
    )
    session.add(syndicate)
    session.flush()

    assert syndicate.id == "k8s-monitor"
    assert syndicate.status == "draft"
    assert syndicate.versions == []


def test_syndicate_version_model(session):
    """Test SyndicateVersion model creation."""
    syndicate = Syndicate(id="k8s-monitor", name="K8s Monitor")
    session.add(syndicate)
    session.flush()

    version = SyndicateVersion(
        syndicate_id="k8s-monitor",
        version="1.0.0",
        oci_tag="v1.0.0",
        oci_digest="sha256:abc123",
        status="draft",
        agent_refs=[
            {"agent": "event-classifier", "version": "2.0.0"},
            {"agent": "remediator", "version": "1.5.0"},
        ],
        created_by="human",
    )
    session.add(version)
    session.flush()

    assert version.syndicate_id == "k8s-monitor"
    assert len(version.agent_refs) == 2
    assert version.syndicate.name == "K8s Monitor"


def test_agent_version_model(session):
    """Test AgentVersion model creation."""
    agent = Agent(id="event-classifier", name="Event Classifier")
    session.add(agent)
    session.flush()

    version = AgentVersion(
        agent_id="event-classifier",
        version="2.0.0",
        oci_tag="v2.0.0",
        oci_digest="sha256:def456",
        status="production",
        created_by="human",
    )
    session.add(version)
    session.flush()

    assert version.agent_id == "event-classifier"
    assert version.status == "production"


def test_resource_status_promotion():
    """Test status promotion logic."""
    from kubani_registry.constants import ResourceStatus

    assert ResourceStatus.DRAFT.can_promote_to(ResourceStatus.TESTING)
    assert ResourceStatus.TESTING.can_promote_to(ResourceStatus.STAGING)
    assert ResourceStatus.STAGING.can_promote_to(ResourceStatus.PRODUCTION)
    assert not ResourceStatus.DRAFT.can_promote_to(ResourceStatus.PRODUCTION)
    assert not ResourceStatus.PRODUCTION.can_promote_to(ResourceStatus.DRAFT)
```

**Acceptance Criteria:**
- [ ] Tests for all new models
- [ ] Tests for relationships
- [ ] Tests for status promotion logic
- [ ] All tests pass

---

## Commit Checkpoints

After completing each task, commit your changes:

```bash
# After Task 1.1
git add platform/registry/alembic/versions/
git commit -m "feat(registry): add schema migration for registry-first architecture

- Add syndicates and syndicate_versions tables
- Add agent_versions table
- Add OCI columns to skills, skill_versions, agents
- Includes downgrade support

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 1.2
git add platform/registry/src/kubani_registry/db/
git commit -m "feat(registry): add SQLAlchemy models for syndicates and versions

- Add Syndicate and SyndicateVersion models
- Add AgentVersion model
- Update Agent and Skill models with OCI fields
- Update SkillVersion with status and promotion fields

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 1.3
git add platform/registry/src/kubani_registry/constants.py
git commit -m "feat(registry): add status enum and constants

- Add ResourceStatus enum with promotion logic
- Add ResourceType enum

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Tasks 1.4-1.5
git add platform/registry/tests/
git commit -m "test(registry): add tests for new schema and models

- Add migration tests
- Add model tests for Syndicate, SyndicateVersion, AgentVersion
- Add status promotion tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Push to remote
git push origin elegant-chaum
```

---

## Phase 1 Completion Checklist

- [ ] Alembic migration file created and tested
- [ ] All SQLAlchemy models added/updated
- [ ] Constants file created
- [ ] Migration runs successfully (up and down)
- [ ] All model tests pass
- [ ] All changes committed and pushed
- [ ] Ready for Phase 2
