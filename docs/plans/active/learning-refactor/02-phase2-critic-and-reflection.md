# Phase 2: Critic Agent, Reflection Agent, and Workflows

**Depends on:** Phase 1 (models, collection pipeline, activities)
**Produces:** `CriticAgent`, `ReflectionAgent`, `EvaluateExecutionsWorkflow`, `ReflectWorkflow`, evaluation + reflection activities

---

## Design: Why Two Separate Agents

The Critic and Reflection agents have fundamentally different concerns:

| | CriticAgent | ReflectionAgent |
|-|-------------|-----------------|
| **Input** | Individual ExecutionRecords | Batch of CriticEvaluations |
| **Scope** | "How did THIS run go?" | "What patterns emerge ACROSS runs?" |
| **Output** | CriticEvaluation (per-execution scores) | ReflectionInsight (cross-execution patterns) |
| **LLM focus** | Scoring, failure classification | Pattern recognition, trend analysis |
| **Triggered by** | Stage 1 (collection) | Stage 2 (evaluation completion) |

Keeping them separate means:
- Each agent has a focused prompt that does one thing well
- The Critic can run frequently (every collection) without worrying about cross-execution analysis
- The Reflection agent gets pre-scored data, so it can focus purely on pattern synthesis
- Either can be disabled independently for debugging

---

## 2.1 CriticAgent

### Agent Directory Structure

```
kubani/agents/critic/
├── agent.py        # CriticAgent class (modernized KubaniAgent)
├── config.yaml     # Score weights, duration baselines, failure categories
└── prompt.md       # System prompt focused on individual execution evaluation
```

### config.yaml

Create `kubani/agents/critic/config.yaml` (replaces old version):

```yaml
name: critic
description: >
  Evaluates individual workflow executions. Scores each run on success,
  efficiency, and quality. Classifies failures. Produces structured
  CriticEvaluation output for the ReflectionAgent to synthesize.
version: "2.0.0"

# No skills — works purely with structured LLM output
skills:
  allowed: []
  denied: ["*"]

# MCP servers (provided via get_additional_tools)
mcp_servers:
  - temporal-mcp-server   # For querying workflow history details
  - memory-mcp            # For checking past evaluations of same workflow type

# Agent limits
limits:
  max_tokens: 4096
  max_turns: 8

# Evaluation configuration
evaluation:
  # Score weights for composite overall_score
  weights:
    success: 0.40
    efficiency: 0.30
    quality: 0.30

  # Duration baselines (ms) — execution is "efficient" if under this value
  # Used by the agent AND the heuristic fallback
  duration_baselines:
    K8sMonitorWorkflow: 120000         # 2 min expected
    RSSIngestWorkflow: 60000           # 1 min expected
    ArxivIngestWorkflow: 120000        # 2 min expected
    GitHubIngestWorkflow: 180000       # 3 min expected
    NewsDigestWorkflow: 300000         # 5 min expected
    AnalyzeDocumentWorkflow: 60000     # 1 min expected
    NexusOrchestratorWorkflow: 60000   # 1 min per turn
    CollectExecutionsWorkflow: 60000   # 1 min expected
    default: 120000                    # 2 min fallback

  # Known failure categories for classification
  failure_categories:
    - timeout
    - mcp_connection_error
    - llm_error
    - activity_failure
    - workflow_cancelled
    - resource_exhaustion
    - unknown
```

### prompt.md

Create `kubani/agents/critic/prompt.md`:

```markdown
You are the Critic Agent for the Kubani AI agent platform. You evaluate individual workflow executions and produce structured quality scores.

## Your Role

You receive a batch of workflow execution records. For EACH execution, produce an independent evaluation. Do NOT compare executions to each other — that is the Reflection Agent's job.

Focus on: Did this specific execution accomplish its goal? Was it efficient? Was the output useful?

## Scoring Guide

### Success Score (0.0 - 1.0)
- 1.0: Completed successfully with meaningful output
- 0.7: Completed but with warnings or partial results
- 0.3: Completed but output indicates the task wasn't fully accomplished
- 0.0: Failed, timed out, or was cancelled

### Efficiency Score (0.0 - 1.0)
Score relative to the expected duration for this workflow type:
- 1.0: Completed well under the expected duration
- 0.7: Completed near the expected duration
- 0.3: Took 2-3x longer than expected
- 0.0: Timed out or took >5x longer than expected

Duration baselines (for reference):
- K8sMonitorWorkflow: ~2 min
- RSSIngestWorkflow: ~1 min
- NewsDigestWorkflow: ~5 min
- Other workflows: ~2 min

### Quality Score (0.0 - 1.0)
- 1.0: Output is comprehensive, accurate, and actionable
- 0.7: Output is useful but could be more detailed
- 0.3: Output is minimal or partially relevant
- 0.0: No useful output or output indicates confusion

## Output Format

Return a JSON array where each element evaluates one execution:

```json
[
  {
    "record_id": "exec-...",
    "overall_score": 0.85,
    "success_score": 1.0,
    "efficiency_score": 0.7,
    "quality_score": 0.85,
    "summary": "K8s health check completed successfully, found 2 issues and dispatched diagnostics.",
    "strengths": ["Correctly identified pod CrashLoopBackOff", "Dispatched remediation promptly"],
    "weaknesses": ["Took longer than baseline due to MCP latency"],
    "failure_category": null,
    "suggestions": ["Consider increasing MCP timeout for kubernetes tools"]
  }
]
```

## Failure Classification

When an execution failed, classify the failure into one of:
- `timeout` — Activity or workflow timed out
- `mcp_connection_error` — MCP server was unreachable or returned errors
- `llm_error` — LLM call failed (rate limit, context too long, etc.)
- `activity_failure` — A Temporal activity raised an exception
- `workflow_cancelled` — Workflow was cancelled externally
- `resource_exhaustion` — OOM, disk full, etc.
- `unknown` — Cannot determine from available data

## Rules

- Evaluate each execution independently. Do NOT look for patterns across executions.
- Be objective. Score based on evidence, not speculation.
- Keep summaries to 1-2 sentences.
- If an execution has no output data, score quality based on status alone.
- Failed executions are still valuable — understanding WHY they failed matters.
- A successful execution with trivial output (e.g., "cluster healthy, no issues") still gets a high success score if that IS the correct output.
```

### agent.py

Create `kubani/agents/critic/agent.py` (replaces old version):

```python
"""
Critic Agent — evaluates individual workflow executions.

Modernized as a KubaniAgent subclass. Replaces the old CriticAgent
that used custom classes and direct LLM calls.

Usage:
    from kubani.agents.critic import CriticAgent

    agent = CriticAgent()
    result = await agent.run(evaluation_prompt)
"""

from pathlib import Path

from kubani.agents._base import KubaniAgent


class CriticAgent(KubaniAgent):
    """Evaluates individual workflow executions with structured scores."""

    AGENT_DIR = Path(__file__).parent

    async def on_skill_complete(self, skill_name: str, result: dict) -> None:
        """No skills used — this agent produces structured LLM output."""
        pass

    def get_additional_tools(self) -> list:
        """Provide Temporal MCP and Memory MCP as tools.

        The Critic uses:
        - Temporal MCP: To fetch workflow history details when execution
          records lack sufficient context for scoring
        - Memory MCP: To check how past evaluations of the same workflow
          type scored (for consistent scoring calibration)
        """
        from mcp.client.sse import sse_client
        from strands.tools.mcp import MCPClient

        from kubani.framework.config import get_config

        tools = []
        config = get_config()

        temporal_url = getattr(config.mcp, "temporal_url", None)
        if temporal_url:
            sse_url = temporal_url.rstrip("/") + "/sse"
            tools.append(MCPClient(lambda u=sse_url: sse_client(u)))

        memory_url = getattr(config.mcp, "memory_url", None)
        if memory_url:
            sse_url = memory_url.rstrip("/") + "/sse"
            tools.append(MCPClient(lambda u=sse_url: sse_client(u)))

        return tools
```

Create `kubani/agents/critic/__init__.py`:

```python
from kubani.agents.critic.agent import CriticAgent

__all__ = ["CriticAgent"]
```

---

## 2.2 ReflectionAgent

### Agent Directory Structure

```
kubani/agents/reflection/
├── agent.py        # ReflectionAgent class (modernized KubaniAgent)
├── config.yaml     # Pattern thresholds, insight types
└── prompt.md       # System prompt focused on cross-execution pattern synthesis
```

### config.yaml

Create `kubani/agents/reflection/config.yaml` (replaces old version):

```yaml
name: reflection
description: >
  Synthesizes cross-execution patterns from CriticEvaluations. Identifies
  recurring failures, performance trends, skill opportunities, and
  cross-agent issues. Produces ReflectionInsights for the ImprovementAgent.
version: "2.0.0"

# No skills — works with structured LLM output
skills:
  allowed: []
  denied: ["*"]

# MCP servers (provided via get_additional_tools)
mcp_servers:
  - memory-mcp    # For querying past insights and evaluations

# Agent limits
limits:
  max_tokens: 6144   # Needs more tokens for synthesizing across many evaluations
  max_turns: 10

# Reflection configuration
reflection:
  # Minimum evaluations needed before a pattern is considered significant
  min_occurrences: 3

  # Minimum success rate for a pattern to qualify as a skill opportunity
  min_success_rate_for_skill: 0.80

  # Insight types and their detection rules
  insight_types:
    pattern:
      description: "Successful approach recurring across executions"
      min_occurrences: 3
    anti_pattern:
      description: "Failure mode occurring repeatedly"
      min_occurrences: 2   # Lower threshold — failures are more urgent
    trend:
      description: "Performance metric changing over time"
      min_data_points: 5
    skill_opportunity:
      description: "Pattern suitable for codifying as a reusable skill"
      min_occurrences: 5
      min_success_rate: 0.80
    cross_agent:
      description: "Issue or pattern spanning multiple syndicates"
      min_syndicates: 2
```

### prompt.md

Create `kubani/agents/reflection/prompt.md`:

```markdown
You are the Reflection Agent for the Kubani AI agent platform. You synthesize patterns across multiple workflow execution evaluations.

## Your Role

You receive a batch of CriticEvaluations — individual execution scores produced by the Critic Agent. Your job is to look ACROSS these evaluations and identify:

1. **Patterns** — Successful approaches that recur (≥3 occurrences)
2. **Anti-patterns** — Failure modes that keep happening (≥2 occurrences)
3. **Trends** — Performance getting better or worse over time
4. **Skill opportunities** — Patterns with ≥5 occurrences and ≥80% success rate that could become reusable skills
5. **Cross-agent issues** — Problems affecting multiple syndicates (shared MCP issues, LLM performance, etc.)

## What You Do NOT Do

- You do NOT score individual executions (the Critic already did that)
- You do NOT propose specific fixes (the Improvement Agent does that)
- You ONLY identify patterns and provide evidence

## Output Format

Return a JSON array of insights:

```json
[
  {
    "insight_type": "anti_pattern",
    "title": "Recurring MCP timeout in k8s-monitor",
    "description": "The kubernetes MCP server times out during pod listing operations, causing K8sMonitorWorkflow failures. This has occurred 4 times in the past 24 hours, always during high-traffic periods.",
    "affected_syndicates": ["k8s-monitor"],
    "affected_workflow_types": ["K8sMonitorWorkflow"],
    "evidence_ids": ["eval-001", "eval-003", "eval-007", "eval-012"],
    "occurrence_count": 4,
    "confidence": 0.92,
    "impact": "high",
    "suggested_action": "Increase MCP timeout or add retry logic for kubernetes tool calls"
  },
  {
    "insight_type": "trend",
    "title": "News digest duration increasing",
    "description": "NewsDigestWorkflow average duration has increased from 180s to 320s over the past week. This correlates with growing article counts.",
    "affected_syndicates": ["news-digest"],
    "affected_workflow_types": ["NewsDigestWorkflow"],
    "evidence_ids": ["eval-020", "eval-025", "eval-030", "eval-035", "eval-040"],
    "occurrence_count": 5,
    "confidence": 0.78,
    "impact": "medium",
    "suggested_action": "Consider batching or limiting articles per digest cycle"
  },
  {
    "insight_type": "cross_agent",
    "title": "Memory MCP latency affecting multiple syndicates",
    "description": "Both k8s-monitor and news-digest show elevated Memory MCP response times. This suggests a shared infrastructure issue rather than an agent-specific problem.",
    "affected_syndicates": ["k8s-monitor", "news-digest"],
    "affected_workflow_types": ["K8sMonitorWorkflow", "RSSIngestWorkflow"],
    "evidence_ids": ["eval-002", "eval-008", "eval-022", "eval-028"],
    "occurrence_count": 4,
    "confidence": 0.85,
    "impact": "high",
    "suggested_action": "Investigate Memory MCP server performance and resource allocation"
  }
]
```

## Insight Type Thresholds

- **pattern**: ≥3 successful executions with similar approaches
- **anti_pattern**: ≥2 failed executions with the same root cause
- **trend**: ≥5 data points showing directional change (duration, score, etc.)
- **skill_opportunity**: ≥5 occurrences with ≥80% success rate — good candidate for a reusable skill
- **cross_agent**: Same issue affecting ≥2 different syndicates

## Rules

1. **Evidence-based only.** Every insight must cite specific evaluation IDs.
2. **No speculation.** Only flag patterns you can clearly see in the data.
3. **Distinguish correlation from causation.** "X and Y both failed" is not the same as "X caused Y to fail."
4. **Aggregate, don't repeat.** If 10 evaluations show the same MCP timeout, that's ONE anti_pattern insight with occurrence_count=10, not 10 separate insights.
5. **Use impact levels correctly:**
   - `low`: Cosmetic or minor efficiency issue
   - `medium`: Noticeable degradation but service still functional
   - `high`: Significant failures or performance issues
   - `critical`: Service-affecting outage or data loss risk
6. **Confidence scoring:**
   - 0.9+: Clear pattern with strong evidence
   - 0.7-0.9: Likely pattern but some ambiguity
   - 0.5-0.7: Possible pattern, needs more data
   - <0.5: Too speculative to include (don't return these)

## Context

You may receive past insights for deduplication. If you see the same pattern again:
- Update the occurrence_count and evidence_ids
- Note whether it's getting better or worse
- Don't create duplicate insights for known patterns
```

### agent.py

Create `kubani/agents/reflection/agent.py` (replaces old version):

```python
"""
Reflection Agent — synthesizes cross-execution patterns.

Modernized as a KubaniAgent subclass. Operates on batches of
CriticEvaluations to identify patterns, trends, and opportunities.

Usage:
    from kubani.agents.reflection import ReflectionAgent

    agent = ReflectionAgent()
    result = await agent.run(reflection_prompt)
"""

from pathlib import Path

from kubani.agents._base import KubaniAgent


class ReflectionAgent(KubaniAgent):
    """Synthesizes cross-execution patterns from critic evaluations."""

    AGENT_DIR = Path(__file__).parent

    async def on_skill_complete(self, skill_name: str, result: dict) -> None:
        """No skills used — this agent produces structured LLM output."""
        pass

    def get_additional_tools(self) -> list:
        """Provide Memory MCP as a tool.

        The Reflection agent uses:
        - Memory MCP: To query past insights (for dedup), past evaluations
          (for trend analysis), and knowledge graph (for relationship context)
        """
        from mcp.client.sse import sse_client
        from strands.tools.mcp import MCPClient

        from kubani.framework.config import get_config

        tools = []
        config = get_config()

        memory_url = getattr(config.mcp, "memory_url", None)
        if memory_url:
            sse_url = memory_url.rstrip("/") + "/sse"
            tools.append(MCPClient(lambda u=sse_url: sse_client(u)))

        return tools
```

Create `kubani/agents/reflection/__init__.py`:

```python
from kubani.agents.reflection.agent import ReflectionAgent

__all__ = ["ReflectionAgent"]
```

---

## 2.3 Evaluation Activity (Critic)

Add to `kubani/syndicates/learning_system/activities.py` (append after Stage 1 activities):

```python
# =============================================================================
# Stage 2: Evaluation Activities (Critic)
# =============================================================================


@activity.defn
async def run_critic_activity(input_data: dict) -> dict[str, Any]:
    """Run the CriticAgent on a batch of execution records.

    This activity:
    1. Retrieves ExecutionRecord dicts from Memory MCP by record_id.
    2. Formats them into an evaluation prompt.
    3. Runs the CriticAgent.
    4. Parses the agent's JSON output into CriticEvaluation dicts.
    5. Stores each evaluation in Memory MCP.

    Args:
        input_data: Dict with keys:
            - record_ids: List of ExecutionRecord IDs to evaluate.

    Returns:
        Dict with:
            - success: bool
            - evaluations_count: int
            - evaluation_ids: list of evaluation IDs
            - errors: list of error messages
    """
    import json
    import time

    from kubani.agents.critic import CriticAgent
    from kubani.syndicates.learning_system._mcp import get_memory_mcp_client
    from kubani.syndicates.learning_system.models import (
        CriticEvaluation,
        make_evaluation_id,
    )

    record_ids = input_data["record_ids"]
    start = time.monotonic()
    errors: list[str] = []
    evaluation_ids: list[str] = []

    activity.heartbeat(f"Evaluating {len(record_ids)} records")

    # -------------------------------------------------------------------------
    # Step 1: Retrieve execution records from Memory MCP
    # -------------------------------------------------------------------------
    memory = get_memory_mcp_client()
    records: list[dict[str, Any]] = []

    for record_id in record_ids:
        try:
            result = await memory.call_tool(
                "search",
                {
                    "query": record_id,
                    "type": "execution_record",
                    "namespace": "learning",
                    "limit": 1,
                },
            )
            items = result.get("results", [])
            if items:
                records.append(items[0].get("data", items[0]))
        except Exception as e:
            logger.warning(f"Failed to retrieve record {record_id}: {e}")
            errors.append(f"retrieve:{record_id}: {e}")

    if not records:
        return {"success": False, "evaluations_count": 0, "evaluation_ids": [], "errors": errors}

    # -------------------------------------------------------------------------
    # Step 2: Build evaluation prompt
    # -------------------------------------------------------------------------
    prompt = _build_critic_prompt(records)

    # -------------------------------------------------------------------------
    # Step 3: Run the CriticAgent
    # -------------------------------------------------------------------------
    activity.heartbeat("Running CriticAgent")

    try:
        agent = CriticAgent()
        raw_output = await agent.run(prompt)
    except Exception as e:
        logger.error(f"CriticAgent failed: {e}", exc_info=True)
        return {
            "success": False,
            "evaluations_count": 0,
            "evaluation_ids": [],
            "errors": [f"agent_error: {e}"],
        }

    # -------------------------------------------------------------------------
    # Step 4: Parse agent output into CriticEvaluation objects
    # -------------------------------------------------------------------------
    activity.heartbeat("Parsing evaluation results")

    evaluations = _parse_critic_evaluations(raw_output, records)

    # -------------------------------------------------------------------------
    # Step 5: Store evaluations in Memory MCP
    # -------------------------------------------------------------------------
    for evaluation in evaluations:
        try:
            await memory.call_tool(
                "add",
                {
                    "type": "critic_evaluation",
                    "namespace": "learning",
                    "data": evaluation.to_dict(),
                    "metadata": {
                        "syndicate": evaluation.syndicate,
                        "workflow_type": evaluation.workflow_type,
                        "overall_score": evaluation.overall_score,
                    },
                },
            )
            evaluation_ids.append(evaluation.evaluation_id)
        except Exception as e:
            logger.warning(f"Failed to store evaluation: {e}")
            errors.append(f"store:{evaluation.evaluation_id}: {e}")

    # Also store as learnings for cross-session retrieval
    for evaluation in evaluations:
        try:
            await memory.call_tool(
                "store_learning",
                {
                    "agent_id": evaluation.syndicate,
                    "learning_type": "critic_evaluation",
                    "content": evaluation.summary,
                    "confidence": evaluation.overall_score,
                },
            )
        except Exception:
            pass  # Best-effort

    duration_ms = int((time.monotonic() - start) * 1000)
    activity.heartbeat(f"Evaluation complete: {len(evaluations)} results in {duration_ms}ms")

    return {
        "success": True,
        "evaluations_count": len(evaluations),
        "evaluation_ids": evaluation_ids,
        "duration_ms": duration_ms,
        "errors": errors,
    }


def _build_critic_prompt(records: list[dict[str, Any]]) -> str:
    """Build the Critic evaluation prompt from execution records."""
    import json

    header = (
        f"Evaluate the following {len(records)} workflow executions. "
        "For each execution, provide scores (0.0-1.0) for success, efficiency, "
        "and quality. Classify any failures.\n\n"
        "Return your evaluations as a JSON array.\n\n"
        "## Executions\n\n"
    )

    entries = []
    for i, record in enumerate(records, 1):
        entry = (
            f"### Execution {i}\n"
            f"- **Record ID:** {record.get('record_id', 'unknown')}\n"
            f"- **Syndicate:** {record.get('syndicate', 'unknown')}\n"
            f"- **Workflow:** {record.get('workflow_type', 'unknown')}\n"
            f"- **Status:** {record.get('status', 'unknown')}\n"
            f"- **Duration:** {record.get('duration_ms', 0)}ms\n"
            f"- **Started:** {record.get('started_at', 'unknown')}\n"
        )

        if record.get("error_message"):
            entry += f"- **Error:** {record['error_message']}\n"

        if record.get("input_data"):
            input_str = json.dumps(record["input_data"], indent=2)[:500]
            entry += f"- **Input:** ```json\n{input_str}\n```\n"

        if record.get("output_data"):
            output_str = json.dumps(record["output_data"], indent=2)[:1000]
            entry += f"- **Output:** ```json\n{output_str}\n```\n"

        entries.append(entry)

    return header + "\n".join(entries)


def _parse_critic_evaluations(
    raw_output: str,
    records: list[dict[str, Any]],
) -> list:
    """Parse the CriticAgent's JSON output into CriticEvaluation objects.

    Falls back to heuristic scoring if the agent output isn't valid JSON.
    """
    import json

    from kubani.syndicates.learning_system.models import CriticEvaluation, make_evaluation_id

    evaluations = []

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
            record_id = item.get("record_id", "")
            source = next((r for r in records if r.get("record_id") == record_id), {})

            evaluation = CriticEvaluation(
                evaluation_id=make_evaluation_id(record_id),
                record_id=record_id,
                syndicate=source.get("syndicate", "unknown"),
                workflow_type=source.get("workflow_type", "unknown"),
                status=source.get("status", "unknown"),
                duration_ms=source.get("duration_ms", 0),
                overall_score=float(item.get("overall_score", 0.5)),
                success_score=float(item.get("success_score", 0.5)),
                efficiency_score=float(item.get("efficiency_score", 0.5)),
                quality_score=float(item.get("quality_score", 0.5)),
                summary=item.get("summary", ""),
                strengths=item.get("strengths", []),
                weaknesses=item.get("weaknesses", []),
                failure_category=item.get("failure_category"),
                suggestions=item.get("suggestions", []),
            )
            evaluations.append(evaluation)

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning(f"Failed to parse Critic output as JSON, using heuristics: {e}")
        for record in records:
            evaluations.append(_heuristic_evaluation(record))

    return evaluations


def _heuristic_evaluation(record: dict[str, Any]):
    """Create a basic evaluation using heuristics when LLM output fails."""
    from kubani.syndicates.learning_system.models import CriticEvaluation, make_evaluation_id

    status = record.get("status", "unknown")
    duration_ms = record.get("duration_ms", 0)
    record_id = record.get("record_id", "unknown")

    success_score = 1.0 if status == "completed" else 0.0

    baseline_ms = 120_000
    if duration_ms <= 0:
        efficiency_score = 0.5
    elif duration_ms <= baseline_ms:
        efficiency_score = 1.0
    elif duration_ms <= baseline_ms * 2:
        efficiency_score = 0.7
    elif duration_ms <= baseline_ms * 5:
        efficiency_score = 0.3
    else:
        efficiency_score = 0.0

    overall = success_score * 0.4 + efficiency_score * 0.3 + 0.5 * 0.3

    return CriticEvaluation(
        evaluation_id=make_evaluation_id(record_id),
        record_id=record_id,
        syndicate=record.get("syndicate", "unknown"),
        workflow_type=record.get("workflow_type", "unknown"),
        status=status,
        duration_ms=duration_ms,
        overall_score=round(overall, 3),
        success_score=success_score,
        efficiency_score=efficiency_score,
        quality_score=0.5,
        summary=f"{record.get('workflow_type', 'Unknown')} {status} in {duration_ms}ms",
        failure_category=record.get("error_message", "").split(":")[0] if status == "failed" else None,
    )
```

---

## 2.4 Reflection Activity

Add to `kubani/syndicates/learning_system/activities.py` (append after Critic activities):

```python
# =============================================================================
# Stage 3: Reflection Activities
# =============================================================================


@activity.defn
async def run_reflection_activity(input_data: dict) -> dict[str, Any]:
    """Run the ReflectionAgent on a batch of CriticEvaluations.

    This activity:
    1. Queries Memory MCP for recent CriticEvaluations.
    2. Queries Memory MCP for existing insights (dedup).
    3. Builds a reflection prompt.
    4. Runs the ReflectionAgent.
    5. Parses insights and stores them in Memory MCP.

    Args:
        input_data: Dict with keys:
            - evaluation_ids: List of CriticEvaluation IDs to reflect on.
              If empty, queries recent evaluations from Memory MCP.
            - lookback_hours: How far back to query evaluations (default 24).

    Returns:
        Dict with:
            - success: bool
            - insights_count: int
            - insight_ids: list of insight IDs
            - insight_types: dict of type -> count
            - errors: list of error messages
    """
    import json
    import time

    from kubani.agents.reflection import ReflectionAgent
    from kubani.syndicates.learning_system._mcp import get_memory_mcp_client
    from kubani.syndicates.learning_system.models import (
        InsightType,
        ReflectionInsight,
        make_insight_id,
    )

    evaluation_ids = input_data.get("evaluation_ids", [])
    lookback_hours = input_data.get("lookback_hours", 24)
    start = time.monotonic()
    errors: list[str] = []
    insight_ids: list[str] = []
    insight_type_counts: dict[str, int] = {}

    activity.heartbeat("Gathering evaluations for reflection")

    # -------------------------------------------------------------------------
    # Step 1: Retrieve CriticEvaluations
    # -------------------------------------------------------------------------
    memory = get_memory_mcp_client()
    evaluations: list[dict[str, Any]] = []

    if evaluation_ids:
        for eval_id in evaluation_ids:
            try:
                result = await memory.call_tool(
                    "search",
                    {"query": eval_id, "type": "critic_evaluation", "namespace": "learning", "limit": 1},
                )
                items = result.get("results", [])
                if items:
                    evaluations.append(items[0].get("data", items[0]))
            except Exception as e:
                errors.append(f"retrieve:{eval_id}: {e}")
    else:
        try:
            result = await memory.call_tool(
                "search",
                {"query": "critic evaluation", "type": "critic_evaluation", "namespace": "learning", "limit": 50},
            )
            evaluations = [item.get("data", item) for item in result.get("results", [])]
        except Exception as e:
            logger.error(f"Failed to query evaluations: {e}")
            return {"success": False, "insights_count": 0, "errors": [str(e)]}

    if len(evaluations) < 3:
        logger.info(f"Only {len(evaluations)} evaluations — not enough for pattern synthesis")
        return {"success": True, "insights_count": 0, "insight_ids": [], "insight_types": {}}

    # -------------------------------------------------------------------------
    # Step 2: Query existing insights (for dedup)
    # -------------------------------------------------------------------------
    existing_insights = []
    try:
        result = await memory.call_tool(
            "search",
            {"query": "reflection insight", "type": "reflection_insight", "namespace": "learning", "limit": 20},
        )
        existing_insights = [item.get("data", item) for item in result.get("results", [])]
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # Step 3: Build reflection prompt
    # -------------------------------------------------------------------------
    prompt = _build_reflection_prompt(evaluations, existing_insights)

    # -------------------------------------------------------------------------
    # Step 4: Run the ReflectionAgent
    # -------------------------------------------------------------------------
    activity.heartbeat("Running ReflectionAgent")

    try:
        agent = ReflectionAgent()
        raw_output = await agent.run(prompt)
    except Exception as e:
        logger.error(f"ReflectionAgent failed: {e}", exc_info=True)
        return {"success": False, "insights_count": 0, "errors": [f"agent: {e}"]}

    # -------------------------------------------------------------------------
    # Step 5: Parse and store insights
    # -------------------------------------------------------------------------
    activity.heartbeat("Parsing reflection insights")

    insights = _parse_reflection_insights(raw_output)

    for insight in insights:
        try:
            await memory.call_tool(
                "add",
                {
                    "type": "reflection_insight",
                    "namespace": "learning",
                    "data": insight.to_dict(),
                    "metadata": {
                        "insight_type": insight.insight_type.value,
                        "impact": insight.impact,
                        "confidence": insight.confidence,
                        "affected_syndicates": ",".join(insight.affected_syndicates),
                    },
                },
            )
            insight_ids.append(insight.insight_id)
            t = insight.insight_type.value
            insight_type_counts[t] = insight_type_counts.get(t, 0) + 1
        except Exception as e:
            errors.append(f"store:{insight.insight_id}: {e}")

    duration_ms = int((time.monotonic() - start) * 1000)

    return {
        "success": True,
        "insights_count": len(insights),
        "insight_ids": insight_ids,
        "insight_types": insight_type_counts,
        "evaluations_analyzed": len(evaluations),
        "duration_ms": duration_ms,
        "errors": errors,
    }


def _build_reflection_prompt(
    evaluations: list[dict[str, Any]],
    existing_insights: list[dict[str, Any]],
) -> str:
    """Build the Reflection prompt from CriticEvaluations."""
    parts = [
        f"Analyze the following {len(evaluations)} CriticEvaluations and identify "
        f"cross-execution patterns.\n\n",
        "## CriticEvaluations\n\n",
    ]

    by_syndicate: dict[str, list] = {}
    for e in evaluations:
        s = e.get("syndicate", "unknown")
        by_syndicate.setdefault(s, []).append(e)

    for syndicate, evals in by_syndicate.items():
        parts.append(f"### {syndicate} ({len(evals)} evaluations)\n\n")
        for e in evals:
            score = e.get("overall_score", "?")
            status = e.get("status", "?")
            wf_type = e.get("workflow_type", "?")
            summary = e.get("summary", "")
            eval_id = e.get("evaluation_id", "?")
            fc = e.get("failure_category", "")
            parts.append(
                f"- [{eval_id}] **{wf_type}** score={score} status={status}"
                f"{' failure=' + fc if fc else ''}"
                f" — {summary}\n"
            )
        parts.append("\n")

    if existing_insights:
        parts.append("## Existing Insights (do NOT duplicate)\n\n")
        for i in existing_insights[:10]:
            parts.append(f"- [{i.get('insight_type', '?')}] {i.get('title', '?')}\n")

    parts.append(
        "\n## Instructions\n\n"
        "Return a JSON array of ReflectionInsight objects. Each must have: "
        "insight_type, title, description, affected_syndicates, affected_workflow_types, "
        "evidence_ids (evaluation IDs), occurrence_count, confidence, impact, suggested_action.\n"
    )

    return "".join(parts)


def _parse_reflection_insights(raw_output: str) -> list:
    """Parse ReflectionAgent output into ReflectionInsight objects."""
    import json

    from kubani.syndicates.learning_system.models import (
        InsightType,
        ReflectionInsight,
        make_insight_id,
    )

    insights = []

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
                insight = ReflectionInsight(
                    insight_id=make_insight_id(
                        item.get("title", "untitled"),
                        item.get("insight_type", "pattern"),
                    ),
                    insight_type=InsightType(item.get("insight_type", "pattern")),
                    title=item.get("title", "Untitled"),
                    description=item.get("description", ""),
                    affected_syndicates=item.get("affected_syndicates", []),
                    affected_workflow_types=item.get("affected_workflow_types", []),
                    evidence_ids=item.get("evidence_ids", []),
                    occurrence_count=int(item.get("occurrence_count", 0)),
                    confidence=float(item.get("confidence", 0.5)),
                    impact=item.get("impact", "medium"),
                    suggested_action=item.get("suggested_action", ""),
                )
                insights.append(insight)
            except Exception as e:
                logger.warning(f"Failed to parse insight: {e}")

    except (json.JSONDecodeError, IndexError) as e:
        logger.warning(f"Failed to parse Reflection output: {e}")

    return insights
```

---

## 2.5 EvaluateExecutionsWorkflow (Critic)

Create `kubani/syndicates/learning_system/workflows/evaluate.py`:

```python
"""Stage 2: Evaluate Executions Workflow (Critic).

Triggered by Stage 1 (CollectExecutionsWorkflow) after new records are stored.
Runs the CriticAgent to score each execution, then triggers the ReflectWorkflow.

NOT scheduled — triggered programmatically as a child workflow.
"""

from dataclasses import dataclass, field
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus


@dataclass
class EvaluateInput:
    """Input for the evaluation workflow."""
    record_ids: list[str] = field(default_factory=list)


@workflow.defn
class EvaluateExecutionsWorkflow(ObservableWorkflowMixin):
    """Evaluate collected executions with the CriticAgent.

    Runs run_critic_activity, then triggers ReflectWorkflow as a
    child workflow (fire-and-forget) so the Reflection Agent can
    synthesize patterns from the new evaluations.

    Queries:
        get_status: Inherited from ObservableWorkflowMixin.
        get_evaluation_stats: Returns evaluation statistics.
    """

    def __init__(self) -> None:
        self._init_observability("EvaluateExecutionsWorkflow")
        self._stats: dict[str, Any] = {}

    @workflow.run
    async def run(self, input: EvaluateInput | dict | None = None) -> dict[str, Any]:
        if isinstance(input, dict):
            record_ids = input.get("record_ids", [])
        elif input is not None:
            record_ids = input.record_ids
        else:
            record_ids = []

        if not record_ids:
            self._set_status(WorkflowStatus.COMPLETED, "No records to evaluate")
            return {"success": True, "evaluations_count": 0}

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Evaluating {len(record_ids)} execution records",
            phase="evaluate",
        )

        try:
            from kubani.syndicates.learning_system.activities import run_critic_activity

            result = await workflow.execute_activity(
                run_critic_activity,
                {"record_ids": record_ids},
                start_to_close_timeout=workflow.timedelta(minutes=10),
                heartbeat_timeout=workflow.timedelta(minutes=3),
                retry_policy=workflow.RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=workflow.timedelta(seconds=10),
                    maximum_interval=workflow.timedelta(minutes=2),
                ),
            )

            self._stats = result

            # Trigger reflection as a child workflow (fire-and-forget)
            evaluation_ids = result.get("evaluation_ids", [])
            if evaluation_ids:
                self._set_status(
                    WorkflowStatus.RUNNING,
                    "Triggering reflection",
                    phase="trigger_reflection",
                )
                try:
                    from kubani.syndicates.learning_system.workflows.reflect import (
                        ReflectWorkflow,
                    )

                    await workflow.start_child_workflow(
                        ReflectWorkflow.run,
                        {"evaluation_ids": evaluation_ids},
                        id=f"learning-reflect-{workflow.now().strftime('%Y%m%dT%H%M%S')}",
                    )
                except Exception as e:
                    # Non-fatal: reflection can also run independently
                    self._log_event("reflect_trigger_failed", str(e))

            if result.get("success"):
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    f"Evaluated {result.get('evaluations_count', 0)} executions",
                )
            else:
                self._set_status(
                    WorkflowStatus.FAILED,
                    f"Evaluation failed: {result.get('errors', [])}",
                )

            return result

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Evaluation failed: {e}")
            raise

    @workflow.query
    def get_evaluation_stats(self) -> dict[str, Any]:
        return self._stats
```

---

## 2.6 ReflectWorkflow (Reflection)

Create `kubani/syndicates/learning_system/workflows/reflect.py`:

```python
"""Stage 3: Reflect Workflow (Reflection Agent).

Triggered by Stage 2 (EvaluateExecutionsWorkflow) after new evaluations
are stored. Runs the ReflectionAgent to synthesize cross-execution patterns.

Can also be triggered independently to re-analyze accumulated evaluations.

NOT scheduled by default — triggered as a child workflow.
"""

from dataclasses import dataclass, field
from typing import Any

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from kubani.framework.temporal.workflows import ObservableWorkflowMixin, WorkflowStatus


@dataclass
class ReflectInput:
    """Input for the reflection workflow."""
    evaluation_ids: list[str] = field(default_factory=list)
    lookback_hours: int = 24


@workflow.defn
class ReflectWorkflow(ObservableWorkflowMixin):
    """Synthesize cross-execution patterns with the ReflectionAgent.

    Runs run_reflection_activity on a batch of CriticEvaluations.
    The resulting ReflectionInsights are stored in Memory MCP for
    the ImprovementAgent to consume.

    Queries:
        get_status: Inherited from ObservableWorkflowMixin.
        get_reflection_stats: Returns reflection statistics.
    """

    def __init__(self) -> None:
        self._init_observability("ReflectWorkflow")
        self._stats: dict[str, Any] = {}

    @workflow.run
    async def run(self, input: ReflectInput | dict | None = None) -> dict[str, Any]:
        if isinstance(input, dict):
            evaluation_ids = input.get("evaluation_ids", [])
            lookback_hours = input.get("lookback_hours", 24)
        elif input is not None:
            evaluation_ids = input.evaluation_ids
            lookback_hours = input.lookback_hours
        else:
            evaluation_ids = []
            lookback_hours = 24

        self._set_status(
            WorkflowStatus.RUNNING,
            f"Reflecting on {'specific' if evaluation_ids else 'recent'} evaluations",
            phase="reflect",
        )

        try:
            from kubani.syndicates.learning_system.activities import run_reflection_activity

            result = await workflow.execute_activity(
                run_reflection_activity,
                {
                    "evaluation_ids": evaluation_ids,
                    "lookback_hours": lookback_hours,
                },
                start_to_close_timeout=workflow.timedelta(minutes=10),
                heartbeat_timeout=workflow.timedelta(minutes=3),
                retry_policy=workflow.RetryPolicy(
                    maximum_attempts=2,
                    initial_interval=workflow.timedelta(seconds=10),
                ),
            )

            self._stats = result

            if result.get("success"):
                count = result.get("insights_count", 0)
                types = result.get("insight_types", {})
                type_summary = ", ".join(f"{k}: {v}" for k, v in types.items()) if types else "none"
                self._set_status(
                    WorkflowStatus.COMPLETED,
                    f"Generated {count} insights ({type_summary})",
                )
            return result

        except Exception as e:
            self._set_status(WorkflowStatus.FAILED, f"Reflection failed: {e}")
            raise

    @workflow.query
    def get_reflection_stats(self) -> dict[str, Any]:
        return self._stats
```

### Update workflows/__init__.py

```python
"""Learning System workflows.

Stage 1: CollectExecutionsWorkflow (hourly) — collects from Temporal
Stage 2: EvaluateExecutionsWorkflow (triggered) — scores with CriticAgent
Stage 3: ReflectWorkflow (triggered) — synthesizes patterns with ReflectionAgent
Stage 4: ImprovementWorkflow (daily) — proposes improvements with ImprovementAgent
"""

from kubani.syndicates.learning_system.workflows.collect import CollectExecutionsWorkflow
from kubani.syndicates.learning_system.workflows.evaluate import EvaluateExecutionsWorkflow
from kubani.syndicates.learning_system.workflows.reflect import ReflectWorkflow

__all__ = [
    "CollectExecutionsWorkflow",
    "EvaluateExecutionsWorkflow",
    "ReflectWorkflow",
]
```

---

## 2.7 Tests

Create `kubani/syndicates/learning_system/tests/test_evaluate_workflow.py`:

```python
"""Tests for the Critic evaluation pipeline."""

import json

import pytest

from kubani.syndicates.learning_system.activities import (
    _build_critic_prompt,
    _heuristic_evaluation,
    _parse_critic_evaluations,
)


@pytest.fixture
def sample_records():
    return [
        {
            "record_id": "exec-001",
            "syndicate": "k8s-monitor",
            "workflow_type": "K8sMonitorWorkflow",
            "status": "completed",
            "duration_ms": 90000,
            "started_at": "2026-03-09T12:00:00Z",
            "input_data": {"trigger": "scheduled"},
            "output_data": {"success": True, "result": "Cluster healthy"},
        },
        {
            "record_id": "exec-002",
            "syndicate": "k8s-monitor",
            "workflow_type": "K8sMonitorWorkflow",
            "status": "failed",
            "duration_ms": 30000,
            "started_at": "2026-03-09T12:05:00Z",
            "error_message": "MCP timeout: kubernetes tools unavailable",
        },
    ]


def test_build_critic_prompt(sample_records):
    prompt = _build_critic_prompt(sample_records)
    assert "2 workflow executions" in prompt
    assert "exec-001" in prompt
    assert "MCP timeout" in prompt


def test_parse_critic_evaluations_valid_json(sample_records):
    agent_output = json.dumps([
        {
            "record_id": "exec-001",
            "overall_score": 0.9,
            "success_score": 1.0,
            "efficiency_score": 0.8,
            "quality_score": 0.9,
            "summary": "Successful health check",
            "strengths": ["Fast execution"],
            "weaknesses": [],
            "failure_category": None,
            "suggestions": [],
        },
        {
            "record_id": "exec-002",
            "overall_score": 0.1,
            "success_score": 0.0,
            "efficiency_score": 0.7,
            "quality_score": 0.0,
            "summary": "Failed due to MCP timeout",
            "strengths": [],
            "weaknesses": ["MCP connection failed"],
            "failure_category": "mcp_connection_error",
            "suggestions": ["Increase MCP timeout"],
        },
    ])

    evaluations = _parse_critic_evaluations(agent_output, sample_records)

    assert len(evaluations) == 2
    assert evaluations[0].overall_score == 0.9
    assert evaluations[0].syndicate == "k8s-monitor"
    assert evaluations[1].failure_category == "mcp_connection_error"


def test_parse_critic_evaluations_fallback(sample_records):
    evaluations = _parse_critic_evaluations("Not valid JSON", sample_records)
    assert len(evaluations) == 2
    assert evaluations[0].success_score == 1.0
    assert evaluations[1].success_score == 0.0


def test_heuristic_evaluation_completed():
    record = {
        "record_id": "exec-001",
        "syndicate": "k8s-monitor",
        "workflow_type": "K8sMonitorWorkflow",
        "status": "completed",
        "duration_ms": 60000,
    }
    evaluation = _heuristic_evaluation(record)
    assert evaluation.success_score == 1.0
    assert evaluation.efficiency_score == 1.0
    assert evaluation.overall_score > 0.7
```

Create `kubani/syndicates/learning_system/tests/test_reflect_workflow.py`:

```python
"""Tests for the Reflection pipeline."""

import json

import pytest

from kubani.syndicates.learning_system.activities import (
    _build_reflection_prompt,
    _parse_reflection_insights,
)
from kubani.syndicates.learning_system.models import InsightType


@pytest.fixture
def sample_evaluations():
    return [
        {
            "evaluation_id": "eval-001",
            "syndicate": "k8s-monitor",
            "workflow_type": "K8sMonitorWorkflow",
            "overall_score": 0.9,
            "status": "completed",
            "summary": "Successful health check",
            "failure_category": None,
        },
        {
            "evaluation_id": "eval-002",
            "syndicate": "k8s-monitor",
            "workflow_type": "K8sMonitorWorkflow",
            "overall_score": 0.2,
            "status": "failed",
            "summary": "MCP timeout",
            "failure_category": "mcp_connection_error",
        },
        {
            "evaluation_id": "eval-003",
            "syndicate": "k8s-monitor",
            "workflow_type": "K8sMonitorWorkflow",
            "overall_score": 0.1,
            "status": "failed",
            "summary": "MCP timeout again",
            "failure_category": "mcp_connection_error",
        },
    ]


def test_build_reflection_prompt(sample_evaluations):
    prompt = _build_reflection_prompt(sample_evaluations, [])
    assert "3 CriticEvaluations" in prompt
    assert "k8s-monitor" in prompt
    assert "eval-001" in prompt


def test_parse_reflection_insights_valid():
    output = json.dumps([
        {
            "insight_type": "anti_pattern",
            "title": "Recurring MCP timeout",
            "description": "MCP timeouts in k8s-monitor",
            "affected_syndicates": ["k8s-monitor"],
            "affected_workflow_types": ["K8sMonitorWorkflow"],
            "evidence_ids": ["eval-002", "eval-003"],
            "occurrence_count": 2,
            "confidence": 0.88,
            "impact": "high",
            "suggested_action": "Increase timeout",
        }
    ])

    insights = _parse_reflection_insights(output)

    assert len(insights) == 1
    assert insights[0].insight_type == InsightType.ANTI_PATTERN
    assert insights[0].occurrence_count == 2
    assert "k8s-monitor" in insights[0].affected_syndicates


def test_parse_reflection_insights_empty():
    insights = _parse_reflection_insights("No patterns found.")
    assert len(insights) == 0
```

---

## 2.8 Verification Checklist

After implementing Phase 2:

- [ ] `kubani/agents/critic/config.yaml` — Config with score weights and duration baselines
- [ ] `kubani/agents/critic/prompt.md` — Focused prompt for individual execution evaluation
- [ ] `kubani/agents/critic/agent.py` — `CriticAgent(KubaniAgent)` with Temporal + Memory MCP
- [ ] `kubani/agents/critic/__init__.py` — Module exports
- [ ] `kubani/agents/reflection/config.yaml` — Config with pattern thresholds and insight types
- [ ] `kubani/agents/reflection/prompt.md` — Focused prompt for cross-execution pattern synthesis
- [ ] `kubani/agents/reflection/agent.py` — `ReflectionAgent(KubaniAgent)` with Memory MCP
- [ ] `kubani/agents/reflection/__init__.py` — Module exports
- [ ] `activities.py` updated with `run_critic_activity` and `run_reflection_activity`
- [ ] `workflows/evaluate.py` — `EvaluateExecutionsWorkflow` that triggers `ReflectWorkflow`
- [ ] `workflows/reflect.py` — `ReflectWorkflow` with `ObservableWorkflowMixin`
- [ ] `workflows/__init__.py` updated with all three workflows
- [ ] `tests/test_evaluate_workflow.py` — Critic prompt, parsing, heuristic tests
- [ ] `tests/test_reflect_workflow.py` — Reflection prompt and parsing tests
- [ ] All tests pass: `pytest kubani/syndicates/learning_system/tests/`
- [ ] Both agents instantiate locally: `CriticAgent()`, `ReflectionAgent()` load config + prompt
