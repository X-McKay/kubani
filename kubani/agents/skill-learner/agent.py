"""
Skill Learner Agent - Learns from failures and proposes new skills.

Records unmatched incidents, clusters similar patterns, and proposes
new SKILL.md files for human review. Can be used for any domain.

Usage:
    from kubani.agents.skill_learner import SkillLearnerAgent

    agent = SkillLearnerAgent()
    count = await agent.analyze_and_propose()
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from kubani.agents._base import KubaniAgent

logger = logging.getLogger(__name__)


@dataclass
class UnmatchedIncident:
    """An incident that couldn't be handled."""

    timestamp: datetime
    reason: str
    message: str
    namespace: str
    resource_name: str
    resource_kind: str


@dataclass
class IncidentCluster:
    """A group of similar unmatched incidents."""

    pattern: str
    incidents: list[UnmatchedIncident] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.incidents)

    @property
    def sample(self) -> UnmatchedIncident | None:
        return self.incidents[0] if self.incidents else None


class SkillLearnerAgent(KubaniAgent):
    """
    Learns from failures and proposes new skills.

    Records unmatched incidents, clusters similar patterns, and
    generates SKILL.md proposals for human review.
    """

    AGENT_DIR = Path(__file__).parent

    def __init__(self, agent_dir: Path | None = None):
        """Initialize the Skill Learner agent."""
        super().__init__(agent_dir)

        # Learner-specific configuration
        learner_config = self.config.get("learner", {})
        self.min_cluster_size = learner_config.get("min_cluster_size", 3)
        self.lookback_days = learner_config.get("lookback_days", 7)
        self.max_proposals = learner_config.get("max_proposals_per_cycle", 3)

        # Skills directory
        skills_dir = learner_config.get("skills_dir", "kubani/skills")
        proposed_subdir = learner_config.get("proposed_subdir", "proposed/k8s")
        self.skills_dir = Path(skills_dir)
        self.proposed_dir = self.skills_dir / proposed_subdir

        # In-memory incident storage
        self._unmatched: list[UnmatchedIncident] = []

    def record_incident(self, payload: dict[str, Any]) -> None:
        """
        Record an unmatched incident.

        Args:
            payload: Event payload from K8S_REMEDIATION_FAILED
        """
        resource = payload.get("resource", "unknown/unknown")
        parts = resource.split("/", 1)
        kind = parts[0] if len(parts) > 1 else "Pod"
        name = parts[1] if len(parts) > 1 else resource

        incident = UnmatchedIncident(
            timestamp=datetime.now(UTC),
            reason=payload.get("reason", "Unknown"),
            message=payload.get("message", ""),
            namespace=payload.get("namespace", "default"),
            resource_name=name,
            resource_kind=kind,
        )
        self._unmatched.append(incident)

        # Prune old incidents
        cutoff = datetime.now(UTC) - timedelta(days=self.lookback_days)
        self._unmatched = [i for i in self._unmatched if i.timestamp > cutoff]

        logger.info(f"Recorded unmatched incident: {incident.reason}")

    def cluster_incidents(self) -> list[IncidentCluster]:
        """
        Group incidents by normalized reason pattern.

        Returns:
            List of incident clusters meeting minimum size
        """
        groups: dict[str, IncidentCluster] = {}

        for incident in self._unmatched:
            # Normalize: replace numbers and hashes
            normalized = re.sub(r"\d+", "N", incident.reason)
            normalized = re.sub(r"[a-f0-9]{8,}", "HASH", normalized, flags=re.IGNORECASE)

            if normalized not in groups:
                groups[normalized] = IncidentCluster(pattern=normalized)
            groups[normalized].incidents.append(incident)

        # Return clusters meeting minimum size
        clusters = [c for c in groups.values() if c.count >= self.min_cluster_size]
        clusters.sort(key=lambda c: c.count, reverse=True)
        return clusters

    async def analyze_and_propose(self) -> int:
        """
        Analyze incidents and propose new skills.

        Returns:
            Number of proposals created
        """
        clusters = self.cluster_incidents()
        if not clusters:
            logger.info("No incident clusters found for skill proposals")
            return 0

        proposals_created = 0
        for cluster in clusters[: self.max_proposals]:
            try:
                path = self._create_skill_proposal(cluster)
                await self._notify_proposal(cluster, path)
                proposals_created += 1
            except Exception as e:
                logger.error(f"Failed to create proposal for {cluster.pattern}: {e}")

        return proposals_created

    def _create_skill_proposal(self, cluster: IncidentCluster) -> Path:
        """Create a SKILL.md proposal file."""
        sample = cluster.sample
        pattern_id = cluster.pattern[:30].lower()
        pattern_id = "".join(c if c.isalnum() or c == "-" else "-" for c in pattern_id)
        pattern_id = "-".join(filter(None, pattern_id.split("-")))
        skill_id = f"proposed-{pattern_id}"

        # Ensure directory exists
        skill_dir = self.proposed_dir / skill_id
        skill_dir.mkdir(parents=True, exist_ok=True)

        content = f"""---
name: {skill_id}
version: "1.0.0"
description: >
  Handle incidents matching pattern: {cluster.pattern}.
  Auto-generated from {cluster.count} similar incidents.
metadata:
  domain: k8s
  category: remediation
  requires-approval: true
  confidence: 0.3
  mcp-servers:
    - kubernetes-mcp-server
---

# Handle {cluster.pattern.replace("-", " ").title()}

## Preconditions

- Event reason matches: {cluster.pattern}
- Resource kind is: {sample.resource_kind if sample else "Pod"}

## Actions

### 1. Investigate

```yaml
mcp_tool: kubernetes-mcp-server/events_list
params:
  namespace: $namespace
```

### 2. Get Logs

```yaml
mcp_tool: kubernetes-mcp-server/pods_log
params:
  name: $pod_name
  namespace: $namespace
  tail: 100
```

### 3. Take Action

Based on investigation, determine appropriate remediation.
(This section needs human review)

## Success Criteria

- [ ] Issue resolved
- [ ] No recurrence within 5 minutes

## Failure Handling

Escalate to human with gathered context.

---
*Auto-generated from {cluster.count} incidents. Please review before approving.*
"""

        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(content)
        logger.info(f"Created skill proposal: {skill_path}")
        return skill_path

    async def _notify_proposal(self, cluster: IncidentCluster, path: Path) -> None:
        """Notify via Discord about new proposal."""
        message = (
            f"**New Skill Proposal**\n"
            f"Pattern: `{cluster.pattern}`\n"
            f"Based on: {cluster.count} incidents\n"
            f"Path: `{path}`\n\n"
            f"Please review and customize before approving."
        )

        try:
            from kubani.framework.mcp import get_mcp_client

            client = get_mcp_client()
            await client.discord.send_message(content=message)
        except Exception as e:
            logger.warning(f"Failed to notify about proposal: {e}")

    async def on_skill_complete(self, skill_name: str, result: dict[str, Any]) -> None:
        """Record skill outcomes for learning."""
        await self.record_outcome(skill_name, result)
