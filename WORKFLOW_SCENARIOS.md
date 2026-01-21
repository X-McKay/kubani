# Kubani Skill Development Workflow - End-to-End Scenarios

**Author:** Manus AI  
**Date:** January 20, 2026  
**Purpose:** Detailed walkthrough of workflows after implementation

## 1. Introduction

This document provides detailed, step-by-step scenarios showing exactly how developers and agents will interact with the skill development system once it's fully implemented. Each scenario includes commands, outputs, and the system's behavior at each step.

---

## 2. Scenario 1: Developer Creates a New Skill Using Claude Code

**Context:** A developer wants to create a skill to find unused Kubernetes ConfigMaps.

### Step 1: Developer Initiates Skill Creation

**Action:**
```
Developer opens Claude Code and types:
"Create a new skill to find all unused ConfigMaps in a Kubernetes namespace"
```

**System Response:**
```
Skill Developer Agent: I'll help you create a skill to find unused ConfigMaps. Let me ask a few questions to ensure we build this correctly:

1. What should the input parameters be?
   - Namespace name (required or optional)?
   - Should we check all namespaces or just one?
   - Any filters (labels, age, etc.)?

2. What should the output format be?
   - List of ConfigMap names?
   - Include additional metadata (age, size, labels)?
   - JSON, YAML, or plain text?

3. How should we determine if a ConfigMap is "unused"?
   - Not referenced by any Pods?
   - Not referenced by any Deployments/StatefulSets?
   - Not mounted as volumes?
```

### Step 2: Developer Provides Requirements

**Action:**
```
Developer responds:
"Input: namespace (required), age_days (optional, default 30)
Output: JSON list with name, age, size, and why it's unused
Unused means: not referenced by any Pod, Deployment, StatefulSet, or DaemonSet"
```

**System Response:**
```
Skill Developer Agent: Perfect! I'm creating the skill now...

✓ Created directory: skills/development/find-unused-configmaps/
✓ Generated SKILL.md with your specifications
✓ Generated skill.py with implementation
✓ Generated test_cases.yaml with 8 test scenarios
✓ Skill is ready for review and testing

You can find the skill at: skills/development/find-unused-configmaps/

Would you like me to:
1. Run a local evaluation now?
2. Show you the generated code?
3. Make any adjustments?
```

### Step 3: Developer Reviews and Tests Locally

**Action:**
```
Developer: "Show me the generated code"
```

**System Response:**
```
Skill Developer Agent: Here's the generated skill.py:

[Shows the Python code with syntax highlighting]

The skill uses the Kubernetes Python client to:
1. List all ConfigMaps in the namespace
2. List all Pods, Deployments, StatefulSets, and DaemonSets
3. Check which ConfigMaps are referenced
4. Filter by age if specified
5. Return unused ConfigMaps with metadata

Would you like me to run a local evaluation to test this?
```

**Action:**
```
Developer: "Yes, run a local evaluation"
```

**System Response:**
```
Skill Developer Agent: Starting local evaluation using microsandbox...

⏳ Creating isolated microVM...
✓ MicroVM ready (142ms)
✓ Mounting skill directory
✓ Installing dependencies (kubernetes==28.1.0)
✓ Running test case 1/8: Empty namespace
✓ Running test case 2/8: Namespace with all ConfigMaps in use
✓ Running test case 3/8: Mixed scenario with unused ConfigMaps
✓ Running test case 4/8: ConfigMaps older than threshold
✓ Running test case 5/8: Edge case - ConfigMap referenced by multiple resources
✓ Running test case 6/8: ConfigMap with no references but recently created
✓ Running test case 7/8: Large namespace (100+ ConfigMaps)
✓ Running test case 8/8: Invalid namespace (error handling)

📊 Evaluation Results:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Accuracy:           95.0% (19/20 assertions passed)
  Avg Latency:        1,234 ms
  P95 Latency:        2,100 ms
  Avg Token Usage:    0 (no LLM calls)
  Cost per Run:       $0.0000
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ Failed Assertion:
  Test Case 7: Large namespace
  Expected: Response time < 2000ms
  Actual: 2,100ms
  
💡 Suggestion: Consider adding pagination or caching for large namespaces

Results saved to: skills/development/find-unused-configmaps/latest_eval.json

Would you like me to:
1. Optimize the code to fix the performance issue?
2. Proceed with cluster evaluation as-is?
3. Make other changes?
```

### Step 4: Developer Requests Improvement

**Action:**
```
Developer: "Optimize the code for large namespaces"
```

**System Response:**
```
Skill Developer Agent: I'll optimize the code for better performance...

✓ Added caching for resource lookups
✓ Implemented parallel processing for ConfigMap checks
✓ Added pagination support
✓ Updated code in skill.py

Re-running evaluation...

📊 New Evaluation Results:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Accuracy:           100% (20/20 assertions passed)
  Avg Latency:        856 ms (31% improvement)
  P95 Latency:        1,450 ms (31% improvement)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ All tests passed!

The skill is ready for promotion. Would you like me to:
1. Promote to production (skills/agents/k8s-monitor/)?
2. Run cluster evaluation first?
3. Make additional changes?
```

### Step 5: Developer Promotes to Production

**Action:**
```
Developer: "Run cluster evaluation first"
```

**System Response:**
```
Skill Developer Agent: Starting cluster evaluation...

⏳ Triggering Temporal workflow: skill-evaluation-find-unused-configmaps
✓ Workflow started (ID: wf_eval_20260120_193045)
✓ Evaluation job scheduled on cluster
⏳ Running in microsandbox on node: k8s-worker-02
✓ Evaluation complete

📊 Cluster Evaluation Results:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Accuracy:           100% (20/20 assertions passed)
  Avg Latency:        823 ms
  P95 Latency:        1,380 ms
  Environment:        Production-like cluster
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Cluster evaluation successful!

Ready to promote. Shall I proceed?
```

**Action:**
```
Developer: "Yes, promote to production"
```

**System Response:**
```
Skill Developer Agent: Promoting skill to production...

✓ Created version directory: skills/agents/k8s-monitor/find-unused-configmaps/v1.0.0/
✓ Copied SKILL.md, skill.py, test_cases.yaml
✓ Saved latest_eval.json
✓ Removed from skills/development/
✓ Registered in Skill Registry (ID: skill_12345)
✓ Skill is now available to k8s-monitor agent

🎉 Skill "find-unused-configmaps" v1.0.0 is now in production!

The k8s-monitor agent can now use this skill by calling:
  execute_skill("find-unused-configmaps", {"namespace": "default"})
```

---

## 3. Scenario 2: Developer Uses CLI for Quick Iteration

**Context:** A developer prefers command-line tools and wants to create a skill quickly.

### Step 1: Draft a New Skill

**Command:**
```bash
kubani-dev skill draft post-to-discord --description "Post a message to a Discord channel"
```

**Output:**
```
✓ Created skill directory: skills/development/post-to-discord/
✓ Generated SKILL.md from template
✓ Generated skill.py skeleton
✓ Generated test_cases.yaml template

Next steps:
  1. Edit the skill files in skills/development/post-to-discord/
  2. Run: kubani-dev skill eval post-to-discord --local
  3. Iterate until satisfied
  4. Run: kubani-dev skill promote post-to-discord
```

### Step 2: Developer Edits Files Manually

**Action:**
Developer opens `skills/development/post-to-discord/skill.py` in their editor and implements the logic.

### Step 3: Run Local Evaluation

**Command:**
```bash
kubani-dev skill eval post-to-discord --local
```

**Output:**
```
Starting local evaluation for: post-to-discord
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏳ Creating microsandbox...
✓ Sandbox ready (156ms)
✓ Running 5 test cases...

Test Results:
  ✓ test_simple_message (234ms)
  ✓ test_message_with_embed (312ms)
  ✓ test_message_with_file (445ms)
  ✗ test_invalid_channel (failed)
  ✓ test_rate_limit_handling (678ms)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Results: 4/5 passed (80%)
Avg Latency: 417ms
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Failed Test Details:
  test_invalid_channel:
    Expected: Raise ChannelNotFoundError
    Actual: Raised ValueError instead
    
Fix the error and run again with:
  kubani-dev skill eval post-to-discord --local
```

### Step 4: Fix and Re-evaluate

**Action:**
Developer fixes the error handling in `skill.py`.

**Command:**
```bash
kubani-dev skill eval post-to-discord --local
```

**Output:**
```
Starting local evaluation for: post-to-discord
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ All 5 test cases passed!
✓ Evaluation saved to: skills/development/post-to-discord/latest_eval.json

Ready for promotion. Run:
  kubani-dev skill promote post-to-discord --category core
```

### Step 5: Promote to Production

**Command:**
```bash
kubani-dev skill promote post-to-discord --category core
```

**Output:**
```
Promoting skill: post-to-discord
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏳ Running cluster evaluation...
✓ Cluster evaluation passed (100% accuracy)
✓ Created: skills/core/post-to-discord/v1.0.0/
✓ Registered in Skill Registry
✓ Available to all agents

🎉 Skill promoted successfully!

View details:
  kubani-dev skill info post-to-discord
```

---

## 4. Scenario 3: Cluster Agent Automatically Improves a Skill

**Context:** The k8s-monitor agent notices that the `find-unused-configmaps` skill is failing in certain edge cases and decides to improve it.

### Step 1: Agent Detects Issue

**System Behavior:**
```
[k8s-monitor agent executing find-unused-configmaps]
❌ Execution failed: KeyError: 'metadata'
Context: ConfigMap without metadata field

[Agent's internal reasoning]
This skill is failing on malformed ConfigMaps. I should improve it to handle this edge case.
```

### Step 2: Agent Creates Improved Version

**System Behavior:**
```
[k8s-monitor agent calls Skill Developer Agent]

Skill Developer Agent:
  ✓ Analyzed failure logs
  ✓ Identified root cause: Missing null checks for metadata
  ✓ Generated improved code with defensive programming
  ✓ Added new test case for malformed ConfigMaps
  ✓ Running evaluation in cluster...
  
Evaluation Results:
  ✓ All existing tests passed
  ✓ New edge case test passed
  ✓ No performance regression
  
  ✓ Creating new version: v1.1.0
  ✓ Publishing to Skill Registry
```

### Step 3: Sync Agent Creates Pull Request

**System Behavior:**
```
[Sync Agent detects new version in registry]

✓ Detected: find-unused-configmaps v1.1.0 (created by k8s-monitor)
✓ Cloning repository
✓ Creating branch: skill-sync/find-unused-configmaps-v1.1.0
✓ Copying files from registry
✓ Committing changes
✓ Pushing to GitHub
✓ Creating pull request

PR Created: https://github.com/X-McKay/kubani/pull/123
```

### Step 4: Developer Reviews Pull Request

**GitHub UI:**
```
Pull Request #123
Title: [Skill Sync] Update find-unused-configmaps to v1.1.0

Description:
This PR was automatically created by the Sync Agent.

Changes:
- Improved error handling for malformed ConfigMaps
- Added null checks for metadata fields
- Added new test case: test_malformed_configmap

Evaluation Results:
- Accuracy: 100% (21/21 tests passed)
- Avg Latency: 845ms (no regression)
- Created by: k8s-monitor agent
- Reason: Automatic improvement after production failure

Files Changed:
  skills/agents/k8s-monitor/find-unused-configmaps/v1.1.0/
    - SKILL.md (updated description)
    - skill.py (improved error handling)
    - test_cases.yaml (added new test)
    - latest_eval.json (new evaluation results)

Reviewer: Please verify the changes and merge if acceptable.
```

**Action:**
Developer reviews the code, approves, and merges the PR.

**Result:**
```
✓ PR merged to main branch
✓ Git repository now in sync with Skill Registry
✓ v1.1.0 is the new production version
```

---

## 5. Scenario 4: Viewing Skill Information and History

### Command: List All Skills

**Command:**
```bash
kubani-dev skill list
```

**Output:**
```
Skills in Development:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  (none)

Core Skills (Production):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  post-to-discord          v1.0.0    ✓ Passing
  fetch-github-issues      v2.1.3    ✓ Passing
  summarize-logs           v1.5.0    ⚠ Warning (high latency)

Agent-Specific Skills:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  k8s-monitor/
    find-unused-configmaps v1.1.0    ✓ Passing
    detect-pod-restarts    v1.0.0    ✓ Passing
  
  news-monitor/
    fetch-rss-feeds        v1.2.0    ✓ Passing
    analyze-sentiment      v1.0.1    ✓ Passing

Total: 7 skills (6 passing, 1 warning)
```

### Command: View Skill Details

**Command:**
```bash
kubani-dev skill info find-unused-configmaps
```

**Output:**
```
Skill: find-unused-configmaps
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Basic Information:
  Name:           find-unused-configmaps
  Current Version: v1.1.0
  Category:       agent-specific (k8s-monitor)
  Status:         ✓ Passing
  Created:        2026-01-20 19:30:45
  Last Updated:   2026-01-20 21:15:22

Description:
  Finds all unused ConfigMaps in a Kubernetes namespace. A ConfigMap
  is considered unused if it's not referenced by any Pod, Deployment,
  StatefulSet, or DaemonSet.

Latest Evaluation (v1.1.0):
  Accuracy:       100% (21/21 tests)
  Avg Latency:    845ms
  P95 Latency:    1,420ms
  Token Usage:    0
  Cost per Run:   $0.0000
  Evaluated:      2026-01-20 21:10:33

Version History:
  v1.1.0  2026-01-20  Improved error handling         ✓
  v1.0.0  2026-01-20  Initial release                 ✓

Usage:
  execute_skill("find-unused-configmaps", {
    "namespace": "default",
    "age_days": 30  // optional
  })

View full evaluation history:
  kubani-dev skill eval-history find-unused-configmaps
```

### Command: View Evaluation History

**Command:**
```bash
kubani-dev skill eval-history find-unused-configmaps
```

**Output:**
```
Evaluation History: find-unused-configmaps
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Version  Date                 Accuracy  Latency  Status
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v1.1.0   2026-01-20 21:10:33  100%      845ms    ✓ Pass
v1.1.0   2026-01-20 21:05:12  100%      832ms    ✓ Pass (pre-release)
v1.0.0   2026-01-20 19:45:22  100%      823ms    ✓ Pass
v1.0.0   2026-01-20 19:35:10  100%      856ms    ✓ Pass
v1.0.0   2026-01-20 19:32:45  95%       2,100ms  ⚠ Fail (perf)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Performance Trend:
  Latency: 2,100ms → 856ms → 823ms → 845ms (60% improvement)
  Accuracy: 95% → 100% (5% improvement)

View detailed report:
  kubani-dev skill eval-report find-unused-configmaps v1.1.0
```

---

## 6. Scenario 5: Agent Discovers and Uses a Skill

**Context:** The news-monitor agent needs to post a breaking news alert to Discord.

### Step 1: Agent Queries Registry

**System Behavior:**
```python
# In news-monitor agent code
from core_agents.registry import SkillRegistry

registry = SkillRegistry()
skills = registry.search(query="post discord", category="core")

# Returns:
# [
#   {
#     "name": "post-to-discord",
#     "version": "v1.0.0",
#     "description": "Post a message to a Discord channel",
#     "accuracy": 1.0,
#     "avg_latency_ms": 417
#   }
# ]
```

### Step 2: Agent Executes Skill

**System Behavior:**
```python
# Agent executes the skill
result = registry.execute_skill(
    name="post-to-discord",
    version="v1.0.0",
    inputs={
        "channel_id": "breaking-news",
        "message": "🚨 Breaking: Major security vulnerability discovered in...",
        "embed": {
            "title": "CVE-2026-12345",
            "url": "https://..."
        }
    }
)

# Skill executes successfully
# Result: {"message_id": "1234567890", "status": "posted"}
```

### Step 3: Execution Logged

**System Behavior:**
```
[Skill execution logged to database]
  Skill: post-to-discord v1.0.0
  Executed by: news-monitor
  Latency: 423ms
  Status: Success
  Timestamp: 2026-01-20 22:15:33
```

---

## 7. Key Workflow Benefits

### For Developers

1. **Fast Iteration:** Local evaluation with microsandbox provides sub-second feedback
2. **Conversational Creation:** Natural language interaction via Claude Code
3. **Automatic Testing:** Synthetic test case generation reduces manual work
4. **Clear Lifecycle:** Explicit stages from development to production
5. **Rich History:** Complete evaluation history and performance trends

### For Agents

1. **Self-Improvement:** Agents can detect failures and improve skills automatically
2. **Skill Discovery:** Easy search and discovery of available skills
3. **Reliable Execution:** All skills are thoroughly evaluated before production
4. **Shared Knowledge:** Skills can be reused across multiple agents
5. **Continuous Learning:** System learns from failures and improves over time

### For the System

1. **Security:** All code executes in hardware-isolated microsandboxes
2. **Observability:** Complete audit trail of skill creation, evaluation, and execution
3. **Quality Control:** Automated evaluation ensures skills meet quality standards
4. **Scalability:** Registry-based architecture scales to hundreds of skills
5. **Maintainability:** Git-based source control with automated sync

---

## 8. Summary

The implemented system provides a seamless, secure, and highly automated workflow for skill development that works equally well for:

- **Interactive development** via Claude Code with the Skill Developer Agent
- **Scriptable operations** via the `kubani-dev` CLI
- **Autonomous improvement** by cluster agents with automatic PR creation
- **Production execution** by any agent in the cluster

The combination of local microsandbox evaluation, cluster-based validation, hybrid storage, and automated synchronization creates a best-in-class MLOps platform specifically designed for agentic AI systems.
