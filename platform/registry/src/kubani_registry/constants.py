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
