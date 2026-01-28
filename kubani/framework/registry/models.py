"""Data models for registry resources."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ResourceStatus(str, Enum):
    """Lifecycle status for resources."""

    DRAFT = "draft"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"


@dataclass
class VersionInfo:
    """Information about a resource version."""

    version: str
    oci_tag: str | None
    oci_digest: str | None
    status: ResourceStatus
    created_at: datetime
    created_by: str | None
    promoted_at: datetime | None = None
    promoted_by: str | None = None


@dataclass
class ResourceInfo:
    """Information about a resource."""

    id: str
    name: str
    resource_type: str  # skill, agent, syndicate
    description: str | None
    current_version: str | None
    oci_repository: str | None
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillContent:
    """Loaded skill content."""

    name: str
    version: str
    description: str
    instructions: str  # The markdown body
    domain: str
    category: str
    scripts: dict[str, str]  # filename -> content
    references: dict[str, str]  # filename -> content
    metadata: dict[str, Any]

    @property
    def skill_id(self) -> str:
        """Get the skill ID."""
        return f"{self.domain}/{self.category}/{self.name}"
