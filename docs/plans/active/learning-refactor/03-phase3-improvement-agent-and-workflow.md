# Phase 3: Improvement Agent and Workflow

**Depends on:** Phase 2 (CriticAgent evaluations + ReflectionAgent insights in Memory MCP)
**Produces:** `ImprovementAgent`, `ImprovementWorkflow`, Discord publishing activity

---

## 3.1 ImprovementAgent

This agent replaces the old SkillSynthesizerAgent. Instead of only proposing new skills, it can propose any kind of improvement: skills, prompt changes, config updates, or architectural recommendations.

### Agent Directory Structure

```
kubani/agents/improvement_agent/
├── agent.py        # ImprovementAgent class
├── config.yaml     # Skills, MCP servers, limits
└── prompt.md       # System prompt
```

### config.yaml

Create `kubani/agents/improvement_agent/config.yaml`:

```yaml
name: improvement-agent
description: >
  Reviews analyzed execution data, identifies actionable improvements,
  and proposes specific changes to agent skills, prompts, and configurations.
version: "1.0.0"

# No skills — this agent uses MCP tools for data access
skills:
  allowed: []
  denied: ["*"]

# MCP servers this agent uses
mcp_servers:
  - memory-mcp
  - skills-mcp

# Agent limits
limits:
  max_tokens: 8192   # Needs more tokens for generating improvement content
  max_turns: 12

# Improvement configuration
improvements:
  # Minimum confidence to auto-approve (without Discord review)
  auto_approve_threshold: 0.95

  # Minimum number of supporting executions for a proposal
  min_evidence_count: 3

  # Maximum proposals per run (to avoid flooding)
  max_proposals_per_run: 5

  # Discord approval settings
  approval_timeout_hours: 72
  approval_threshold: 2  # Number of approvals needed

  # Improvement type priorities (higher = more important to address)
  type_priorities:
    config_update: 1       # Easiest to apply, lowest risk
    skill_update: 2        # Moderate risk
    skill_new: 3           # Moderate effort
    prompt_update: 4       # Requires careful review
    architecture: 5        # Informational only, highest effort
```

### prompt.md

Create `kubani/agents/improvement_agent/prompt.md`:

```markdown
You are the Improvement Agent for the Kubani AI agent platform. Your job is to review execution analysis data and propose concrete, actionable improvements.

## Your Role

You receive:
1. Recent ReflectionInsights (cross-execution patterns from the Reflection Agent).
2. Recent CriticEvaluations (individual scores and suggestions from the Critic Agent).
3. Historical improvement proposals (to avoid duplicates).
4. Current skill inventory (to know what exists).

You must propose specific improvements that will measurably improve agent performance.

## What You Can Propose

### 1. Config Updates (`config_update`)
Changes to agent or syndicate configuration. These are the safest and easiest to apply.

Examples:
- "Add `FailedMount` to k8s-monitor skip_reasons — it self-resolves in 95% of cases"
- "Increase news-digest ArxivIngestWorkflow timeout from 2min to 4min — 3 timeouts this week"
- "Reduce k8s-monitor schedule from 5min to 15min — most runs find nothing actionable"

Output format:
```yaml
# Target: kubani/agents/k8s_coordinator/config.yaml
# Change: Add to skip_reasons list
skip_reasons:
  - ... (existing)
  - FailedMount    # Self-resolves 95% of cases (evidence: exec-001, exec-005, exec-012)
```

### 2. Skill Updates (`skill_update`)
Modifications to existing skills. Include the specific changes.

Examples:
- "Update k8s/diagnostic/pod-crashloop to check init containers first — 4 cases where root cause was init container"
- "Add timeout retry logic to general/mcp/call-tool skill — MCP timeouts are the #1 failure category"

### 3. New Skills (`skill_new`)
Create new skills from successful patterns. Include full skill markdown.

Examples:
- "Create k8s/diagnostic/mcp-recovery skill — agents successfully recovered from MCP timeouts 8 times using the same approach"

Output format:
```markdown
---
name: mcp-recovery
domain: general
category: resilience
description: Recover from MCP server connection failures
---

# mcp-recovery

## When to use
When an MCP tool call fails with a connection error or timeout.

## Steps
1. Wait 5 seconds
2. Retry the tool call
3. If still failing, try alternative MCP server URL
4. If no alternative, report the specific tool and error
```

### 4. Prompt Updates (`prompt_update`)
Changes to agent system prompts. These require careful review.

Examples:
- "Add instruction to k8s-coordinator prompt: 'When dispatching diagnostics for CrashLoopBackOff, check if it's an init container issue first'"
- "Clarify in news-digest content-analyst prompt that importance score of 1-3 should be reserved for truly minor items"

### 5. Architecture Recommendations (`architecture`)
Structural changes. These are informational — they won't be auto-applied.

Examples:
- "Consider splitting k8s-monitor scheduled and reactive workflows into separate task queues"
- "The learning system should also monitor Nexus heartbeat workflow success rates"

## Output Format

Return a JSON array of improvement proposals:

```json
[
  {
    "improvement_type": "config_update",
    "target_agent": "k8s-monitor",
    "title": "Add FailedMount to skip_reasons",
    "description": "FailedMount events self-resolve in 95% of observed cases. Currently k8s-monitor dispatches diagnostics for these, wasting resources.",
    "rationale": "Observed 12 FailedMount events in the past week. 11 self-resolved within 2 minutes. Only 1 required investigation (and that was due to a PVC issue, not the mount itself).",
    "evidence_ids": ["analysis-001", "analysis-005", "analysis-012"],
    "confidence": 0.92,
    "estimated_impact": "Reduce unnecessary diagnostic dispatches by ~15%",
    "content": "skip_reasons:\n  - FailedMount",
    "target_file": "kubani/agents/k8s_coordinator/config.yaml"
  }
]
```

## Rules

1. **Evidence-based only.** Every proposal must cite specific analyzed executions.
2. **No duplicates.** Check existing proposals and skills before proposing.
3. **Minimum evidence.** Need at least 3 supporting executions unless the issue is critical (failure rate > 50%).
4. **Conservative confidence.** Only score > 0.9 if you have strong evidence and the change is low-risk.
5. **Actionable content.** Include the actual change (code, config, text) — not just a description.
6. **One concern per proposal.** Don't bundle unrelated changes.
7. **Prioritize by impact.** Address the most impactful issues first.

## What NOT to Propose

- Changes without evidence from analyzed executions
- Improvements for one-off failures (need recurring pattern)
- Breaking changes to agent APIs or workflow interfaces
- Changes to infrastructure (Temporal, Kubernetes, etc.)
- Proposals that duplicate existing pending proposals
```

### agent.py

Create `kubani/agents/improvement_agent/agent.py`:

```python
"""
Improvement Agent.

Reviews analyzed execution data and proposes specific, actionable
improvements to agent skills, prompts, and configurations.

Replaces the old SkillSynthesizerAgent with broader improvement scope.

Usage:
    from kubani.agents.improvement_agent import ImprovementAgent

    agent = ImprovementAgent()
    result = await agent.run(improvement_prompt)
"""

from pathlib import Path

from kubani.agents._base import KubaniAgent


class ImprovementAgent(KubaniAgent):
    """Proposes improvements based on execution analysis data."""

    AGENT_DIR = Path(__file__).parent

    async def on_skill_complete(self, skill_name: str, result: dict) -> None:
        """No skills used — this agent works with MCP tools only."""
        pass

    def get_additional_tools(self) -> list:
        """Provide Memory MCP and Skills MCP clients as tools.

        The improvement agent needs:
        - Memory MCP: To query analyzed executions, past proposals, and learnings
        - Skills MCP: To check existing skills and avoid duplicates
        """
        from mcp.client.sse import sse_client
        from strands.tools.mcp import MCPClient

        from kubani.framework.config import get_config

        tools = []
        config = get_config()

        # Memory MCP
        memory_url = getattr(config.mcp, "memory_url", None)
        if memory_url:
            sse_url = memory_url.rstrip("/") + "/sse"
            tools.append(MCPClient(lambda u=sse_url: sse_client(u)))

        # Skills MCP
        skills_url = getattr(config.mcp, "skills_url", None)
        if skills_url:
            sse_url = skills_url.rstrip("/") + "/sse"
            tools.append(MCPClient(lambda u=sse_url: sse_client(u)))

        return tools
```

Create `kubani/agents/improvement_agent/__init__.py`:

```python
from kubani.agents.improvement_agent.agent import ImprovementAgent

__all__ = ["ImprovementAgent"]
```

---

## 3.2 Improvement Activities

Add to `kubani/syndicates/learning_system/activities.py` (append):

```python
# =============================================================================
# Stage 3: Improvement Activities
# =============================================================================


@activity.defn
async def propose_improvements_activity(input_data: dict) -> dict[str, Any]:
    """Run the ImprovementAgent to propose improvements from analyzed data.

    This activity:
    1. Queries Memory MCP for recent analyzed executions.
    2. Queries Memory MCP for existing proposals (to avoid duplicates).
    3. Queries Skills MCP for current skill inventory.
    4. Builds a prompt with all context.
    5. Runs the ImprovementAgent.
    6. Parses proposals from agent output.
    7. Stores proposals in Memory MCP.

    Args:
        input_data: Dict with keys:
            - lookback_hours: How far back to query analyses (default 24).
            - max_proposals: Maximum proposals to generate (default 5).

    Returns:
        Dict with:
            - success: bool
            - proposals_count: int
            - proposal_ids: list of proposal IDs
            - proposals: list of ProposedImprovement dicts
            - errors: list of error messages
    """
    import json
    import time

    from kubani.agents.improvement_agent import ImprovementAgent
    from kubani.syndicates.learning_system._mcp import get_memory_mcp_client, get_skills_mcp_client
    from kubani.syndicates.learning_system.models import (
        ProposedImprovement,
        ImprovementType,
        make_proposal_id,
    )

    lookback_hours = input_data.get("lookback_hours", 24)
    max_proposals = input_data.get("max_proposals", 5)
    start = time.monotonic()
    errors: list[str] = []

    activity.heartbeat("Gathering context for improvements")

    # -------------------------------------------------------------------------
    # Step 1: Query recent insights and evaluations from Memory MCP
    # -------------------------------------------------------------------------
    memory = get_memory_mcp_client()

    # Get ReflectionInsights (primary input — cross-execution patterns)
    try:
        insights_result = await memory.call_tool(
            "search",
            {
                "query": "reflection insight",
                "type": "reflection_insight",
                "namespace": "learning",
                "limit": 30,
            },
        )
        recent_insights = insights_result.get("results", [])
    except Exception as e:
        logger.error(f"Failed to query insights: {e}")
        recent_insights = []

    # Get CriticEvaluations (secondary input — individual scores)
    try:
        evals_result = await memory.call_tool(
            "search",
            {
                "query": "critic evaluation",
                "type": "critic_evaluation",
                "namespace": "learning",
                "limit": 30,
            },
        )
        recent_evaluations = evals_result.get("results", [])
    except Exception as e:
        logger.warning(f"Failed to query evaluations: {e}")
        recent_evaluations = []

    if not recent_insights and not recent_evaluations:
        return {"success": True, "proposals_count": 0, "proposal_ids": [], "proposals": []}

    # -------------------------------------------------------------------------
    # Step 2: Query existing proposals (for dedup)
    # -------------------------------------------------------------------------
    try:
        existing_result = await memory.call_tool(
            "search",
            {
                "query": "improvement proposal",
                "type": "improvement_proposal",
                "namespace": "learning",
                "limit": 20,
            },
        )
        existing_proposals = existing_result.get("results", [])
    except Exception:
        existing_proposals = []

    # -------------------------------------------------------------------------
    # Step 3: Query skill inventory
    # -------------------------------------------------------------------------
    skills_inventory = []
    try:
        skills = get_skills_mcp_client()
        skill_result = await skills.call_tool("list_skills", {})
        skills_inventory = skill_result.get("skills", [])
    except Exception as e:
        logger.warning(f"Failed to query skills: {e}")

    # -------------------------------------------------------------------------
    # Step 4: Build improvement prompt
    # -------------------------------------------------------------------------
    prompt = _build_improvement_prompt(
        recent_analyses,
        existing_proposals,
        skills_inventory,
        max_proposals,
    )

    # -------------------------------------------------------------------------
    # Step 5: Run ImprovementAgent
    # -------------------------------------------------------------------------
    activity.heartbeat("Running ImprovementAgent")

    try:
        agent = ImprovementAgent()
        raw_output = await agent.run(prompt)
    except Exception as e:
        logger.error(f"ImprovementAgent failed: {e}", exc_info=True)
        return {"success": False, "proposals_count": 0, "errors": [f"agent: {e}"]}

    # -------------------------------------------------------------------------
    # Step 6: Parse proposals
    # -------------------------------------------------------------------------
    activity.heartbeat("Parsing proposals")

    proposals = _parse_proposals(raw_output)

    # Limit to max_proposals
    proposals = proposals[:max_proposals]

    # -------------------------------------------------------------------------
    # Step 7: Store proposals in Memory MCP
    # -------------------------------------------------------------------------
    proposal_ids = []
    proposal_dicts = []

    for proposal in proposals:
        try:
            await memory.call_tool(
                "add",
                {
                    "type": "improvement_proposal",
                    "namespace": "learning",
                    "data": proposal.to_dict(),
                    "metadata": {
                        "improvement_type": proposal.improvement_type.value,
                        "target_agent": proposal.target_agent,
                        "confidence": proposal.confidence,
                        "status": proposal.status.value,
                    },
                },
            )
            proposal_ids.append(proposal.proposal_id)
            proposal_dicts.append(proposal.to_dict())
        except Exception as e:
            errors.append(f"store:{proposal.proposal_id}: {e}")

    duration_ms = int((time.monotonic() - start) * 1000)

    return {
        "success": True,
        "proposals_count": len(proposals),
        "proposal_ids": proposal_ids,
        "proposals": proposal_dicts,
        "duration_ms": duration_ms,
        "errors": errors,
    }


@activity.defn
async def publish_proposals_activity(input_data: dict) -> dict[str, Any]:
    """Publish improvement proposals to Discord and the UI activity feed.

    Args:
        input_data: Dict with keys:
            - proposals: List of ProposedImprovement dicts.

    Returns:
        Dict with "success" bool and "published_count" int.
    """
    import os

    proposals = input_data.get("proposals", [])
    published = 0

    if not proposals:
        return {"success": True, "published_count": 0}

    # -------------------------------------------------------------------------
    # Publish to UI activity feed
    # -------------------------------------------------------------------------
    try:
        from kubani.framework.ui_events import publish_activity, publish_approval

        # Summary activity
        summary_parts = []
        for p in proposals:
            summary_parts.append(
                f"- **{p['title']}** ({p['improvement_type']}) "
                f"→ {p['target_agent']} (confidence: {p['confidence']:.0%})"
            )

        await publish_activity(
            source="learning-system",
            event_type="learning",
            title=f"Improvement proposals: {len(proposals)} new",
            content="\n".join(summary_parts),
            severity="info",
            metadata={"proposals_count": len(proposals)},
        )

        # Individual approval requests
        for p in proposals:
            try:
                await publish_approval(
                    approval_type="improvement_proposal",
                    source="learning-system",
                    title=p["title"],
                    summary=p["description"][:200],
                    spec=p.get("content", ""),
                    metadata={
                        "proposal_id": p["proposal_id"],
                        "improvement_type": p["improvement_type"],
                        "target_agent": p["target_agent"],
                        "confidence": p["confidence"],
                    },
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to publish to UI: {e}")

    # -------------------------------------------------------------------------
    # Publish to Discord
    # -------------------------------------------------------------------------
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if discord_webhook:
        try:
            import httpx

            for p in proposals:
                message = _format_discord_proposal(p)
                async with httpx.AsyncClient() as client:
                    await client.post(
                        discord_webhook,
                        json={"content": message},
                        timeout=10.0,
                    )
                published += 1
        except Exception as e:
            logger.warning(f"Failed to publish to Discord: {e}")

    return {"success": True, "published_count": published}


def _build_improvement_prompt(
    analyses: list[dict],
    existing_proposals: list[dict],
    skills: list[dict],
    max_proposals: int,
) -> str:
    """Build the improvement prompt with all context."""
    import json

    parts = [
        f"Review the following {len(analyses)} analyzed executions and propose "
        f"up to {max_proposals} improvements.\n\n",
    ]

    # Recent analyses (most relevant context)
    parts.append("## Recent Analyzed Executions\n\n")
    for a in analyses[:30]:  # Limit to avoid token overflow
        data = a.get("data", a)
        parts.append(
            f"- **{data.get('syndicate', '?')}/{data.get('workflow_type', '?')}**: "
            f"score={data.get('overall_score', '?')}, "
            f"status={data.get('status', '?')}, "
            f"patterns={data.get('patterns', [])}, "
            f"suggestions={data.get('suggestions', [])}\n"
        )

    # Existing proposals (for dedup)
    if existing_proposals:
        parts.append("\n## Existing Proposals (do NOT duplicate)\n\n")
        for p in existing_proposals[:10]:
            data = p.get("data", p)
            parts.append(
                f"- [{data.get('status', '?')}] **{data.get('title', '?')}** "
                f"→ {data.get('target_agent', '?')}\n"
            )

    # Current skills (for context)
    if skills:
        parts.append("\n## Current Skills Inventory\n\n")
        for s in skills[:20]:
            parts.append(f"- {s.get('path', s.get('name', '?'))}\n")

    parts.append(
        f"\n## Instructions\n\n"
        f"Propose up to {max_proposals} improvements as a JSON array. "
        f"Each proposal must include improvement_type, target_agent, title, "
        f"description, rationale, evidence_ids, confidence, estimated_impact, "
        f"content, and target_file.\n"
    )

    return "".join(parts)


def _parse_proposals(raw_output: str) -> list:
    """Parse ImprovementAgent output into ProposedImprovement objects."""
    import json

    from kubani.syndicates.learning_system.models import (
        ImprovementType,
        ProposedImprovement,
        make_proposal_id,
    )

    proposals = []

    try:
        text = raw_output
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        parsed = json.loads(text.strip())
        if not isinstance(parsed, list):
            parsed = [parsed]

        for item in parsed:
            try:
                proposal = ProposedImprovement(
                    proposal_id=make_proposal_id(
                        item.get("title", "untitled"),
                        item.get("target_agent", "unknown"),
                    ),
                    improvement_type=ImprovementType(item.get("improvement_type", "config_update")),
                    target_agent=item.get("target_agent", "unknown"),
                    title=item.get("title", "Untitled"),
                    description=item.get("description", ""),
                    rationale=item.get("rationale", ""),
                    evidence_ids=item.get("evidence_ids", []),
                    confidence=float(item.get("confidence", 0.5)),
                    estimated_impact=item.get("estimated_impact", ""),
                    content=item.get("content", ""),
                    target_file=item.get("target_file", ""),
                )
                proposals.append(proposal)
            except Exception as e:
                logger.warning(f"Failed to parse proposal: {e}")

    except (json.JSONDecodeError, IndexError) as e:
        logger.warning(f"Failed to parse improvement proposals: {e}")

    return proposals


def _format_discord_proposal(proposal: dict) -> str:
    """Format a proposal for Discord posting."""
    parts = [
        f"## Improvement Proposal: {proposal.get('title', 'Untitled')}",
        f"**Type:** {proposal.get('improvement_type', '?')}",
        f"**Target:** {proposal.get('target_agent', '?')}",
        f"**Confidence:** {proposal.get('confidence', 0):.0%}",
        "",
        proposal.get("description", ""),
        "",
        f"**Rationale:** {proposal.get('rationale', '')}",
        f"**Expected Impact:** {proposal.get('estimated_impact', '')}",
    ]

    content = proposal.get("content", "")
    if content:
        # Truncate for Discord 2000 char limit
        if len(content) > 500:
            content = content[:500] + "... (truncated)"
        parts.extend(["", "**Proposed Change:**", f"```\n{content}\n```"])

    message = "\n".join(parts)
    # Discord message limit
    if len(message) > 1900:
        message = message[:1900] + "\n... (truncated)"

    return message
```

---

## 3.3 ImprovementWorkflow

Create `kubani/syndicates/learning_system/workflows/improve.py`:

```python
"""Stage 3: Improvement Workflow.

Scheduled daily. Reviews accumulated analyses and proposes
actionable improvements to agent skills, prompts, and configs.

Publishes proposals to Discord and the UI activity feed for review.
"""

from dataclasses import dataclass
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus


@dataclass
class ImprovementInput:
    """Input for the improvement workflow.

    Attributes:
        lookback_hours: How far back to query analyses (default 24).
        max_proposals: Maximum proposals to generate (default 5).
    """

    lookback_hours: int = 24
    max_proposals: int = 5


@workflow.defn
class ImprovementWorkflow(ObservableWorkflowMixin):
    """Propose improvements from analyzed execution data.

    Two activities:
    1. propose_improvements_activity: Run ImprovementAgent
    2. publish_proposals_activity: Post to Discord + UI

    Queries:
        get_status: Inherited from ObservableWorkflowMixin.
        get_improvement_stats: Returns proposal statistics.
    """

    def __init__(self) -> None:
        self._init_observability("ImprovementWorkflow")
        self._stats: dict[str, Any] = {}

    @workflow.run
    async def run(self, input: ImprovementInput | dict | None = None) -> dict[str, Any]:
        """Execute an improvement cycle.

        Args:
            input: Optional configuration. Defaults to 24h lookback, 5 max proposals.

        Returns:
            Improvement result dict.
        """
        if isinstance(input, dict):
            lookback_hours = input.get("lookback_hours", 24)
            max_proposals = input.get("max_proposals", 5)
        elif input is not None:
            lookback_hours = input.lookback_hours
            max_proposals = input.max_proposals
        else:
            lookback_hours = 24
            max_proposals = 5

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Reviewing analyses from past {lookback_hours}h",
            phase="propose",
        )

        try:
            # Step 1: Generate proposals
            from kubani.syndicates.learning_system.activities import (
                propose_improvements_activity,
                publish_proposals_activity,
            )

            result = await workflow.execute_activity(
                propose_improvements_activity,
                {
                    "lookback_hours": lookback_hours,
                    "max_proposals": max_proposals,
                },
                start_to_close_timeout=workflow.timedelta(minutes=15),
                heartbeat_timeout=workflow.timedelta(minutes=5),
                retry_policy=workflow.RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=workflow.timedelta(seconds=10),
                ),
            )

            self._stats = result

            # Step 2: Publish proposals (if any)
            proposals = result.get("proposals", [])
            if proposals:
                self._set_status(
                    WorkflowStatus.RUNNING,
                    f"Publishing {len(proposals)} proposals",
                    phase="publish",
                )

                await workflow.execute_activity(
                    publish_proposals_activity,
                    {"proposals": proposals},
                    start_to_close_timeout=workflow.timedelta(minutes=5),
                )

            self._set_status(
                WorkflowStatus.COMPLETED,
                f"Proposed {result.get('proposals_count', 0)} improvements",
            )

            return result

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Improvement cycle failed: {e}")
            raise

    @workflow.query
    def get_improvement_stats(self) -> dict[str, Any]:
        """Query improvement statistics."""
        return self._stats
```

### Update workflows/__init__.py (final version)

```python
"""Learning System workflows.

Stage 1: CollectExecutionsWorkflow (hourly) — collects from Temporal
Stage 2: AnalyzeExecutionsWorkflow (triggered) — evaluates with LearningAnalystAgent
Stage 3: ImprovementWorkflow (daily) — proposes improvements with ImprovementAgent
"""

from kubani.syndicates.learning_system.workflows.analyze import AnalyzeExecutionsWorkflow
from kubani.syndicates.learning_system.workflows.collect import CollectExecutionsWorkflow
from kubani.syndicates.learning_system.workflows.improve import ImprovementWorkflow

__all__ = [
    "CollectExecutionsWorkflow",
    "AnalyzeExecutionsWorkflow",
    "ImprovementWorkflow",
]
```

---

## 3.4 Tests

Create `kubani/syndicates/learning_system/tests/test_improve_workflow.py`:

```python
"""Tests for the improvement pipeline."""

import json

import pytest

from kubani.syndicates.learning_system.activities import (
    _build_improvement_prompt,
    _format_discord_proposal,
    _parse_proposals,
)
from kubani.syndicates.learning_system.models import ImprovementType


@pytest.fixture
def sample_analyses():
    """Sample analyzed execution data."""
    return [
        {
            "data": {
                "analysis_id": "analysis-001",
                "syndicate": "k8s-monitor",
                "workflow_type": "K8sMonitorWorkflow",
                "overall_score": 0.9,
                "status": "completed",
                "patterns": ["successful_remediation"],
                "suggestions": [],
            }
        },
        {
            "data": {
                "analysis_id": "analysis-002",
                "syndicate": "k8s-monitor",
                "workflow_type": "K8sMonitorWorkflow",
                "overall_score": 0.2,
                "status": "failed",
                "patterns": ["mcp_timeout_recurring"],
                "suggestions": ["Increase MCP timeout"],
            }
        },
        {
            "data": {
                "analysis_id": "analysis-003",
                "syndicate": "k8s-monitor",
                "workflow_type": "K8sMonitorWorkflow",
                "overall_score": 0.3,
                "status": "failed",
                "patterns": ["mcp_timeout_recurring"],
                "suggestions": ["Increase MCP timeout"],
            }
        },
    ]


def test_build_improvement_prompt(sample_analyses):
    """Test prompt building."""
    prompt = _build_improvement_prompt(
        analyses=sample_analyses,
        existing_proposals=[],
        skills=[{"path": "k8s/diagnostic/pod-crashloop"}],
        max_proposals=3,
    )

    assert "3 analyzed executions" in prompt
    assert "k8s-monitor" in prompt
    assert "mcp_timeout_recurring" in prompt
    assert "k8s/diagnostic/pod-crashloop" in prompt


def test_parse_proposals_valid():
    """Test parsing valid JSON proposals."""
    output = json.dumps([
        {
            "improvement_type": "config_update",
            "target_agent": "k8s-monitor",
            "title": "Increase MCP timeout",
            "description": "MCP timeouts are recurring",
            "rationale": "3 failures in past 24h",
            "evidence_ids": ["analysis-002", "analysis-003"],
            "confidence": 0.88,
            "estimated_impact": "Reduce failures by 30%",
            "content": "timeout: 300",
            "target_file": "kubani/agents/k8s_coordinator/config.yaml",
        }
    ])

    proposals = _parse_proposals(output)

    assert len(proposals) == 1
    assert proposals[0].improvement_type == ImprovementType.CONFIG_UPDATE
    assert proposals[0].target_agent == "k8s-monitor"
    assert proposals[0].confidence == 0.88
    assert len(proposals[0].evidence_ids) == 2


def test_parse_proposals_empty_output():
    """Test handling of non-JSON output."""
    proposals = _parse_proposals("No improvements needed at this time.")
    assert len(proposals) == 0


def test_format_discord_proposal():
    """Test Discord message formatting."""
    proposal = {
        "title": "Increase MCP timeout",
        "improvement_type": "config_update",
        "target_agent": "k8s-monitor",
        "confidence": 0.88,
        "description": "MCP timeouts are recurring",
        "rationale": "3 failures in 24h",
        "estimated_impact": "Reduce failures by 30%",
        "content": "timeout: 300",
    }

    message = _format_discord_proposal(proposal)

    assert "Increase MCP timeout" in message
    assert "config_update" in message
    assert "88%" in message
    assert len(message) <= 2000
```

---

## 3.5 Verification Checklist

After implementing Phase 3:

- [ ] `kubani/agents/improvement_agent/config.yaml` — Config with thresholds and priorities
- [ ] `kubani/agents/improvement_agent/prompt.md` — Detailed prompt with output format
- [ ] `kubani/agents/improvement_agent/agent.py` — `ImprovementAgent(KubaniAgent)` with MCP tools
- [ ] `kubani/agents/improvement_agent/__init__.py` — Module exports
- [ ] `activities.py` updated with `propose_improvements_activity` and `publish_proposals_activity`
- [ ] `workflows/improve.py` — `ImprovementWorkflow` with two-step propose→publish
- [ ] `workflows/__init__.py` — All three workflows exported
- [ ] `tests/test_improve_workflow.py` — Tests for prompt, parsing, formatting
- [ ] All tests pass: `pytest kubani/syndicates/learning_system/tests/`
- [ ] Agent can be instantiated locally: `ImprovementAgent()` loads config and prompt
