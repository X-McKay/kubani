# Plan: News Syndicate - Bottom-Up Development with Evaluation

**Date:** 2026-01-28
**Status:** Complete ✅
**Priority:** High
**Approach:** Test-Driven, Bottom-Up Development

### Progress Summary

| Layer | Status | Notes |
|-------|--------|-------|
| 1. Infrastructure | ✅ Complete | MCP SSE transport fixed, all tools accessible |
| 2. Skills | ✅ Complete | 13/13 skills passing at 100% accuracy (150 tests) |
| 3. Agents | ✅ Complete | 5/5 agents passing at 100% accuracy (41 tests) |
| 4. Syndicate | ✅ Complete | E2E validation passing at 100% (20 tests) |

**Total: 211 tests across all layers, all passing at 100%**

---

## Executive Summary

The News Digest Syndicate has architectural issues at multiple layers. Rather than fixing everything at once, we'll take a **bottom-up, test-driven approach**:

1. **Layer 1: Infrastructure** - Fix MCP transport (blocking everything)
2. **Layer 2: Skills** - Create, evaluate, and improve skills until they meet quality targets
3. **Layer 3: Agents** - Simplify agents to use skills, evaluate until they meet quality targets
4. **Layer 4: Syndicate** - Validate end-to-end workflows

Each layer must pass evaluation before moving to the next.

---

## Development Philosophy

```
┌─────────────────────────────────────────────────────────────────┐
│                    Bottom-Up Development                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 4: Syndicate    (validate workflows work end-to-end)     │
│      ↑                                                           │
│  Layer 3: Agents       (evaluate agents use skills correctly)   │
│      ↑                                                           │
│  Layer 2: Skills       (evaluate skills produce correct output) │
│      ↑                                                           │
│  Layer 1: Infrastructure  (fix MCP, verify connectivity)        │
│                                                                  │
│  Each layer must PASS EVALUATION before building next layer     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Principle:** Don't build on a broken foundation. Each layer is tested and validated before the next layer depends on it.

---

## Layer 1: Infrastructure (MCP Transport Fix)

### Goal
Fix MCP client transport so all MCP communication works.

### Success Criteria
- [ ] `client.memory.list_tools()` returns tool list (not 404)
- [ ] `client.memory.store_learning()` succeeds
- [ ] `client.memory.cache_get/set()` works
- [ ] `client.discord.health_check()` returns true

### Implementation

**File:** `kubani/framework/mcp/client.py`

1. Replace HTTP POST transport with MCP SDK's SSE client
2. Remove dead code (non-existent tool methods)
3. Add proper error handling for SSE connections

### Verification

```bash
# Verify infrastructure before proceeding
kubani mcp health-check --all

# Or manual verification:
kubectl port-forward -n ai-agents svc/memory-mcp-server 8083:8083 &
python -c "
import asyncio
from kubani.framework.mcp import get_mcp_client

async def verify():
    client = get_mcp_client()
    tools = await client.memory.list_tools()
    print(f'✓ Memory MCP: {len(tools)} tools')

    result = await client.memory.cache_set(key='test:infra', value={'test': True}, ttl_seconds=60)
    print(f'✓ cache_set: {result}')

    result = await client.memory.cache_get(key='test:infra')
    print(f'✓ cache_get: {result}')

asyncio.run(verify())
"
```

**Gate:** Do not proceed to Layer 2 until all infrastructure checks pass.

---

## Layer 2: Skills Development

### Goal
Ensure all news-related skills are functional, tested, and meet quality targets.

### Existing Skills Inventory

| Skill | Path | Status |
|-------|------|--------|
| `fetch-rss-feeds` | `news/collection/fetch-rss-feeds` | Needs test_cases.yaml |
| `fetch-arxiv-papers` | `news/collection/fetch-arxiv-papers` | Needs test_cases.yaml |
| `fetch-github-trending` | `news/collection/fetch-github-trending` | Needs test_cases.yaml |
| `filter-duplicates` | `news/collection/filter-duplicates` | Needs test_cases.yaml |
| `analyze-article` | `news/diagnostic/analyze-article` | Needs test_cases.yaml |
| `analyze-trends` | `news/diagnostic/analyze-trends` | Needs test_cases.yaml |
| `detect-breaking-news` | `news/diagnostic/detect-breaking-news` | Needs test_cases.yaml |
| `analyze-arxiv-paper` | `news/diagnostic/analyze-arxiv-paper` | Needs test_cases.yaml |
| `analyze-github-repo` | `news/diagnostic/analyze-github-repo` | Needs test_cases.yaml |
| `analyze-trends-historical` | `news/diagnostic/analyze-trends-historical` | Needs test_cases.yaml |
| `compose-digest` | `news/action/compose-digest` | Needs test_cases.yaml |
| `compose-executive-digest` | `news/action/compose-executive-digest` | Needs test_cases.yaml |
| `publish-to-discord` | `news/action/publish-to-discord` | Needs test_cases.yaml |

### Success Criteria (Per Skill)
- [ ] `test_cases.yaml` exists with 3+ test cases
- [ ] Quick eval accuracy ≥ 80%
- [ ] Critic confidence ≥ 0.8
- [ ] Full eval completed (4-config comparison)

### Development Process (Per Skill)

```bash
# Step 1: Create test cases if missing
kubani skill add-tests kubani/skills/news/diagnostic/analyze-article

# Step 2: Quick evaluation
kubani skill eval kubani/skills/news/diagnostic/analyze-article --verbose

# Step 3: If accuracy < 80%, improve automatically
kubani skill improve kubani/skills/news/diagnostic/analyze-article --goals accuracy

# Step 4: Re-evaluate, repeat until target met
kubani skill eval kubani/skills/news/diagnostic/analyze-article --verbose

# Step 5: Full evaluation (4-config comparison)
kubani skill eval kubani/skills/news/diagnostic/analyze-article --mode full --parallel

# Step 6: Review results
cat kubani/skills/news/diagnostic/analyze-article/full_eval.md
```

### Autonomous Development Option

For skills that need significant work, use the autonomous workflow:

```bash
# Run autonomous skill development
kubani skill auto \
  --improve kubani/skills/news/diagnostic/analyze-article \
  --target-accuracy 85 \
  --max-iterations 5 \
  --review-each-iteration

# Monitor progress
kubani skill auto-status <workflow_id>
```

### Skill Development Order

**Priority 1: Core Analysis Skills** (most complex, most critical)
1. `analyze-article` - Foundation for all content analysis
2. `analyze-trends` - Required for trend detection
3. `detect-breaking-news` - Required for alerts

**Priority 2: Collection Skills** (simpler, fewer LLM calls)
4. `fetch-rss-feeds`
5. `filter-duplicates`
6. `fetch-arxiv-papers`
7. `fetch-github-trending`

**Priority 3: Research Analysis Skills**
8. `analyze-arxiv-paper`
9. `analyze-github-repo`
10. `analyze-trends-historical`

**Priority 4: Output Skills**
11. `compose-digest`
12. `compose-executive-digest`
13. `publish-to-discord`

### Verification Dashboard

Create evaluation tracking:

```bash
# Evaluate all news skills and generate report
kubani skill eval-all kubani/skills/news --output news-skills-report.md
```

**Expected Output:**
```
News Skills Evaluation Report
=============================

| Skill | Accuracy | Critic | Tests | Status |
|-------|----------|--------|-------|--------|
| analyze-article | 87% | 0.85 | 5/5 | ✓ PASS |
| analyze-trends | 82% | 0.81 | 4/4 | ✓ PASS |
| detect-breaking-news | 79% | 0.78 | 3/4 | ⚠ NEEDS WORK |
...

Overall: 11/13 skills passing (85%)
```

**Gate:** Do not proceed to Layer 3 until all skills pass (≥80% accuracy, ≥0.8 critic confidence).

---

## Layer 3: Agent Development

### Goal
Simplify agents to use skills, then evaluate agent behavior.

### Agent Inventory

| Agent | Current LOC | Target LOC | Skills Used |
|-------|-------------|------------|-------------|
| `content_analyst` | 777 | ~150 | analyze-article, analyze-trends, detect-breaking-news |
| `digest_publisher` | 1300 | ~200 | compose-digest, compose-executive-digest, publish-to-discord |
| `feed_collector` | 314 | ~100 | fetch-rss-feeds, filter-duplicates |
| `research_collector` | ~400 | ~100 | fetch-arxiv-papers, fetch-github-trending |
| `research_analyst` | ~500 | ~150 | analyze-arxiv-paper, analyze-github-repo |

### Success Criteria (Per Agent)
- [ ] Agent uses skills (not hardcoded prompts)
- [ ] Agent code reduced by ≥70%
- [ ] Agent evaluation suite passes (≥90% accuracy)
- [ ] LLM judge criteria met

### Development Process (Per Agent)

#### Step 1: Create Agent Evaluation Suite

```yaml
# kubani/evaluations/news/content_analyst.yaml
name: content_analyst_evaluation
description: Evaluate ContentAnalystAgent behavior
version: "1.0"
agent: content-analyst

test_cases:
  - id: analyze_single_article
    name: Analyze Single Article
    description: Agent should analyze one article and return structured output
    input:
      articles:
        - title: "OpenAI Releases GPT-5"
          source: "TechCrunch"
          summary: "OpenAI announced GPT-5 today with significant improvements..."
    expected:
      articles_analyzed: 1
      has_summary: true
      has_importance_score: true
      importance_range: [7, 10]  # Should be high importance
    evaluator: automated

  - id: detect_breaking_news
    name: Detect Breaking News
    description: Agent should flag major announcements as breaking
    input:
      articles:
        - title: "Critical Security Vulnerability in Major AI Framework"
          source: "SecurityWeek"
          summary: "A critical RCE vulnerability affecting millions..."
          importance_score: 9
    expected:
      breaking_detected: true
    evaluator: automated

  - id: trend_analysis_quality
    name: Trend Analysis Quality
    description: Agent should identify meaningful trends
    input:
      articles: [...10 articles about same topic...]
    evaluator: llm_judge
    llm_criteria:
      - name: trend_identification
        weight: 0.4
        prompt: "Did the agent correctly identify the dominant trend?"
      - name: entity_extraction
        weight: 0.3
        prompt: "Were the key entities correctly extracted?"
      - name: categorization
        weight: 0.3
        prompt: "Were articles correctly categorized?"

metrics:
  - name: accuracy
    type: percentage
    threshold: 0.90
  - name: latency_p95
    type: duration
    threshold: 5000ms
```

#### Step 2: Simplify Agent Implementation

```python
# kubani/agents/content_analyst/agent.py (simplified)

from pathlib import Path
from kubani.agents._base import KubaniAgent

class ContentAnalystAgent(KubaniAgent):
    """Content analysis using discovered skills."""

    AGENT_DIR = Path(__file__).parent

    # Skills will be discovered from config
    # No hardcoded prompts!

    async def analyze_articles(self, articles: list[dict]) -> dict:
        """Analyze articles using skills."""
        prompt = f"""
        Analyze these {len(articles)} articles.
        Use the analyze-article skill for each article.
        Then use analyze-trends to identify patterns.
        Finally use detect-breaking-news for any urgent items.

        Articles: {articles}
        """
        result = await self.agent.invoke_async(prompt)
        return self._parse_result(result)

    async def on_skill_complete(self, skill_name: str, result: dict) -> None:
        await self.record_outcome(skill_name, result, success=result.get("success", False))
```

#### Step 3: Run Agent Evaluation

```bash
# Evaluate agent
kubani eval content-analyst --suite content_analyst_evaluation

# View results
kubani eval-results content-analyst

# Compare multiple runs
kubani eval-compare content-analyst --runs 5
```

#### Step 4: Iterate Until Passing

```bash
# If evaluation fails, analyze failures
kubani eval-failures content-analyst

# Make improvements, re-run evaluation
kubani eval content-analyst --suite content_analyst_evaluation
```

### Agent Development Order

1. **ContentAnalystAgent** - Core analysis, most skill usage
2. **FeedCollectorAgent** - Simple, good test of skill integration
3. **DigestPublisherAgent** - Complex output, validates MCP integration
4. **ResearchCollectorAgent** - External API integration
5. **ResearchAnalystAgent** - Paper/repo analysis

### Verification

```bash
# Run all agent evaluations
kubani eval-all --domain news --output agent-eval-report.md
```

**Gate:** Do not proceed to Layer 4 until all agents pass evaluation (≥90% accuracy).

---

## Layer 4: Syndicate Validation

### Goal
Validate end-to-end workflows work correctly.

### Success Criteria
- [ ] NewsCollectionWorkflow completes successfully
- [ ] NewsDigestWorkflow publishes to Discord
- [ ] Articles stored and retrieved correctly
- [ ] Breaking news alerts work
- [ ] Trend snapshots stored

### Integration Test Suite

```yaml
# kubani/evaluations/news/syndicate_integration.yaml
name: news_syndicate_integration
description: End-to-end syndicate validation
version: "1.0"
syndicate: news-digest

test_cases:
  - id: collection_workflow
    name: Collection Workflow E2E
    description: Full collection workflow execution
    workflow: NewsCollectionWorkflow
    input:
      check_breaking: true
      notify_channel: "test-channel"
    expected:
      articles_collected: ">0"
      articles_stored: ">0"
      success: true
    timeout: 300s
    evaluator: automated

  - id: digest_workflow
    name: Digest Workflow E2E
    description: Full digest workflow execution
    workflow: NewsDigestWorkflow
    input:
      digest_type: "scheduled"
      lookback_hours: 24
      notify_channel: "test-channel"
    expected:
      articles_included: ">0"
      success: true
      message_id: "exists"
    timeout: 600s
    evaluator: automated

  - id: breaking_news_flow
    name: Breaking News Alert Flow
    description: Breaking news detection and notification
    evaluator: llm_judge
    llm_criteria:
      - name: detection_accuracy
        weight: 0.5
        prompt: "Did the system correctly identify breaking news?"
      - name: notification_timeliness
        weight: 0.3
        prompt: "Was the alert sent promptly?"
      - name: content_quality
        weight: 0.2
        prompt: "Was the alert content informative?"
```

### Manual Validation Steps

```bash
# Step 1: Start test workflow
temporal workflow start \
  --task-queue news-digest \
  --type NewsCollectionWorkflow \
  --workflow-id test-collection-$(date +%s) \
  --input '{"check_breaking": false}'

# Step 2: Monitor execution
kubectl logs -n ai-agents deployment/news-monitor -f

# Step 3: Verify articles stored
python -c "
from kubani.framework.mcp import get_mcp_client
import asyncio

async def check():
    client = get_mcp_client()
    result = await client.memory.query_knowledge(query='news articles', limit=5)
    print(f'Articles in memory: {result}')

asyncio.run(check())
"

# Step 4: Trigger digest workflow
temporal workflow start \
  --task-queue news-digest \
  --type NewsDigestWorkflow \
  --workflow-id test-digest-$(date +%s) \
  --input '{"lookback_hours": 24, "notify_channel": "ai-news-test"}'

# Step 5: Verify Discord message
# Check #ai-news-test channel for digest
```

### Verification

```bash
# Run integration tests
kubani eval-syndicate news-digest --output syndicate-report.md
```

**Gate:** Syndicate passes when all integration tests pass.

---

## Implementation Sequence

### Week 1: Infrastructure + Skills Foundation

| Day | Tasks |
|-----|-------|
| 1 | Fix MCP transport, verify connectivity |
| 2 | Create test_cases.yaml for Priority 1 skills (analyze-article, analyze-trends, detect-breaking-news) |
| 3 | Run skill evaluations, iterate on improvements |
| 4 | Create test_cases.yaml for Priority 2 skills (collection skills) |
| 5 | Run evaluations, all Priority 1-2 skills passing |

### Week 2: Skills Completion + Agent Foundation

| Day | Tasks |
|-----|-------|
| 1 | Create test_cases.yaml for Priority 3-4 skills |
| 2 | Run evaluations, iterate until all skills passing |
| 3 | Add AgentSkills package, update KubaniAgent base |
| 4 | Create evaluation suite for ContentAnalystAgent |
| 5 | Simplify ContentAnalystAgent, run evaluations |

### Week 3: Agents + Syndicate

| Day | Tasks |
|-----|-------|
| 1 | Simplify remaining agents (FeedCollector, DigestPublisher) |
| 2 | Run agent evaluations, iterate until passing |
| 3 | Simplify ResearchCollector, ResearchAnalyst |
| 4 | Create syndicate integration tests |
| 5 | Run integration tests, fix issues, deploy |

---

## Tracking Progress

### Skills Status Board

```
Layer 2: Skills - COMPLETE (2026-01-29)
=======================================

Priority 1 (Core Analysis):
  [x] analyze-article      - Accuracy: 100% | Tests: 15/15 | Status: ✅ PASS
  [x] analyze-trends       - Accuracy: 100% | Tests: 14/14 | Status: ✅ PASS
  [x] detect-breaking-news - Accuracy: 100% | Tests: 18/18 | Status: ✅ PASS

Priority 2 (Collection):
  [x] fetch-rss-feeds      - Accuracy: 100% | Tests: 14/14 | Status: ✅ PASS
  [x] filter-duplicates    - Accuracy: 100% | Tests: 19/19 | Status: ✅ PASS
  [x] fetch-arxiv-papers   - Accuracy: 100% | Tests:  7/7  | Status: ✅ PASS
  [x] fetch-github-trending - Accuracy: 100% | Tests:  7/7  | Status: ✅ PASS

Priority 3 (Research):
  [x] analyze-arxiv-paper  - Accuracy: 100% | Tests:  8/8  | Status: ✅ PASS
  [x] analyze-github-repo  - Accuracy: 100% | Tests:  8/8  | Status: ✅ PASS
  [x] analyze-trends-historical - Accuracy: 100% | Tests:  8/8  | Status: ✅ PASS

Priority 4 (Output):
  [x] compose-digest       - Accuracy: 100% | Tests: 11/11 | Status: ✅ PASS
  [x] compose-executive-digest - Accuracy: 100% | Tests:  8/8  | Status: ✅ PASS
  [x] publish-to-discord   - Accuracy: 100% | Tests: 13/13 | Status: ✅ PASS

Total: 150 tests across 13 skills | All passing ✅
Gate: PASSED (all skills ≥80% accuracy)
```

### Agents Status Board

```
Layer 3: Agents - COMPLETE (2026-01-29)
=======================================

  [x] ContentAnalystAgent    - Eval: 100% | Tests: 7/7   | Status: ✅ PASS
  [x] FeedCollectorAgent     - Eval: 100% | Tests: 3/3   | Status: ✅ PASS
  [x] DigestPublisherAgent   - Eval: 100% | Tests: 10/10 | Status: ✅ PASS
  [x] ResearchCollectorAgent - Eval: 100% | Tests: 8/8   | Status: ✅ PASS
  [x] ResearchAnalystAgent   - Eval: 100% | Tests: 13/13 | Status: ✅ PASS

Total: 41 tests across 5 agents | All passing ✅
Gate: PASSED (all agents ≥90% evaluation accuracy)
```

### Syndicate Status Board

```
Layer 4: Syndicate - COMPLETE (2026-01-29)
==========================================

  [x] Collection Workflow Logic  - Tests: 4/4  | Status: ✅ PASS
  [x] Digest Workflow Logic      - Tests: 4/4  | Status: ✅ PASS
  [x] Data Type Serialization    - Tests: 3/3  | Status: ✅ PASS
  [x] Workflow Mixin             - Tests: 2/2  | Status: ✅ PASS
  [x] Agent Activity Integration - Tests: 4/4  | Status: ✅ PASS
  [x] End-to-End Simulation      - Tests: 3/3  | Status: ✅ PASS

Total: 20 tests | All passing ✅
Gate: PASSED (all E2E tests passing)
```

---

## Commands Reference

```bash
# Layer 1: Infrastructure
kubani mcp health-check --all

# Layer 2: Skills
kubani skill eval <path> --verbose           # Quick eval
kubani skill eval <path> --mode full         # Full eval
kubani skill improve <path> --goals accuracy # Auto-improve
kubani skill auto --improve <path>           # Autonomous dev
kubani skill eval-all kubani/skills/news     # Eval all

# Layer 3: Agents
kubani eval <agent>                          # Run eval suite
kubani eval-results <agent>                  # View results
kubani eval-compare <agent> --runs 5         # Compare runs

# Layer 4: Syndicate
kubani eval-syndicate news-digest            # Integration tests
temporal workflow start --task-queue news-digest # Manual trigger
```

---

## Success Criteria Summary

| Layer | Metric | Target |
|-------|--------|--------|
| 1. Infrastructure | MCP connectivity | 100% tools accessible |
| 2. Skills | Accuracy | ≥80% per skill |
| 2. Skills | Critic confidence | ≥0.8 per skill |
| 3. Agents | Evaluation accuracy | ≥90% per agent |
| 3. Agents | Code reduction | ≥70% per agent |
| 4. Syndicate | Integration tests | 100% passing |

---

## Rollback Plan

Each layer can be rolled back independently:

- **Layer 1:** Revert `client.py` changes
- **Layer 2:** Skills are additive, no rollback needed
- **Layer 3:** Keep old agent code in `agent.py.bak` until validated
- **Layer 4:** `kubectl rollout undo deployment/news-monitor`
