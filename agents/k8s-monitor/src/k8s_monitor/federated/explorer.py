"""
Explorer Agent - Simple skill proposal from unmatched incidents.

When the Healer encounters issues it can't handle, the Explorer:
1. Records the unmatched incident
2. Groups similar incidents by reason
3. Proposes new SKILL.md files for human review

This is a simplified Voyager-inspired learning pattern.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core_agents.events import EventBus, EventType, get_event_bus
from core_agents.integrations.discord_mcp import send_discord_message

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


class ExplorerAgent:
    """
    Simple skill learner - proposes new markdown skills from failures.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        source_name: str = "k8s-explorer",
        min_cluster_size: int = 3,
        lookback_days: int = 7,
        skills_dir: Path | str | None = None,
    ):
        self._event_bus = event_bus
        self.source_name = source_name
        self.min_cluster_size = min_cluster_size
        self.lookback_days = lookback_days
        self._unmatched: list[UnmatchedIncident] = []

        if skills_dir is None:
            skills_dir = Path(os.getenv("SKILLS_DIR", "skills"))
        self.skills_dir = Path(skills_dir)
        self.proposed_dir = self.skills_dir / "proposed" / "k8s"

    async def _ensure_initialized(self) -> None:
        if self._event_bus is None:
            self._event_bus = await get_event_bus()

    async def start(self) -> None:
        """Start listening for failed remediations."""
        await self._ensure_initialized()
        logger.info("Explorer starting, listening for remediation failures")

        async for event in self._event_bus.subscribe(
            EventType.K8S_REMEDIATION_FAILED,
            consumer_group="k8s-explorer",
            consumer_name=self.source_name,
        ):
            payload = event.payload
            if payload.get("escalated"):
                await self._record_unmatched(payload)

    async def _record_unmatched(self, payload: dict[str, Any]) -> None:
        """Record an unmatched incident."""
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

    def _cluster_incidents(self) -> list[IncidentCluster]:
        """Group incidents by normalized reason."""
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
        """Analyze incidents and propose new skills. Returns count of proposals."""
        await self._ensure_initialized()

        clusters = self._cluster_incidents()
        if not clusters:
            logger.info("No incident clusters found for skill proposals")
            return 0

        proposals_created = 0
        for cluster in clusters[:3]:  # Max 3 proposals per cycle
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
            await send_discord_message(content=message)
        except Exception as e:
            logger.warning(f"Failed to notify about proposal: {e}")

        # Also publish event
        await self._event_bus.publish(
            event_type=EventType.AGENT_SKILL_LEARNED,
            payload={
                "skill_id": path.parent.name,
                "status": "proposed",
                "based_on_incidents": cluster.count,
                "path": str(path),
            },
            source=self.source_name,
        )


async def run_explorer_cycle(explorer: ExplorerAgent | None = None) -> int:
    """Run one exploration cycle. Returns number of proposals created."""
    if explorer is None:
        explorer = ExplorerAgent()
    await explorer._ensure_initialized()
    return await explorer.analyze_and_propose()
