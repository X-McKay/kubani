# Developer Experience Enhancements

> Opportunities identified from reviewing [claude.com/blog](https://claude.com/blog) articles on skills, MCP servers, hooks, and enterprise agent patterns. Analysis performed January 2026.

## Sources

- [Extending Claude's capabilities with skills and MCP servers](https://claude.com/blog/extending-claude-capabilities-with-skills-mcp-servers) (Dec 2025)
- [How enterprises are building AI agents in 2026](https://claude.com/blog/how-enterprises-are-building-ai-agents-in-2026) (Dec 2025)
- [Building Skills for Claude Code](https://claude.com/blog/building-skills-for-claude-code) (Dec 2025)
- [How to create Skills: Key steps, limitations, and examples](https://claude.com/blog/how-to-create-skills-key-steps-limitations-and-examples) (Nov 2025)
- [Skills explained: How Skills compares to prompts, Projects, MCP, and subagents](https://claude.com/blog/skills-explained) (Nov 2025)
- [Claude Code power user customization: How to configure hooks](https://claude.com/blog/how-to-configure-hooks) (Dec 2025)
- [Using CLAUDE.md files](https://claude.com/blog/using-claude-md-files) (Nov 2025)

---

## Priority Summary

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| 1 | Add hooks configuration for auto-formatting and safety guards | Low | High |
| 2 | Improve skill descriptions with verbs, use cases, boundaries | Low | Medium |
| 3 | Integrate MCP tools explicitly into skill instructions | Medium | High |
| 4 | Add references/ directories to skills for progressive disclosure | Medium | Medium |
| 5 | Make ContextManager mandatory in federated agents | Medium | High |
| 6 | Clean up duplicate commands/ vs skills/ | Low | Low |

---

## 1. Hooks Configuration

**Current State:** No hooks configured in `.claude/settings.json` (only `.claude/settings.local.json` with permissions).

**Blog Recommendation:** The hooks article describes 8 hook types that eliminate repetitive tasks and enforce project rules automatically.

**Specific Improvements:**

| Hook Type | Opportunity |
|-----------|-------------|
| **PostToolUse** | Auto-run `ruff format` after Write/Edit on Python files |
| **SessionStart** | Inject git status, current agent versions, cluster health summary |
| **PreToolUse** | Block dangerous kubectl commands (delete namespace, scale to 0) without confirmation |
| **UserPromptSubmit** | Auto-inject current sprint/issue context when working on agents |

**Example implementation for `.claude/settings.json`:**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "if [[ \"$CLAUDE_TOOL_INPUT_FILE_PATH\" == *.py ]]; then ruff format \"$CLAUDE_TOOL_INPUT_FILE_PATH\" 2>/dev/null; fi"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo '## Current Status'; git -C /home/al/git/kubani status --short; echo '## Agent Versions'; grep -h 'version =' agents/*/pyproject.toml 2>/dev/null | head -5"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash(kubectl delete namespace*)",
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"decision\": \"block\", \"reason\": \"Namespace deletion requires explicit user confirmation\"}'"
          }
        ]
      }
    ]
  }
}
```

---

## 2. Skill Description Quality

**Current State:** Skills have functional but minimal descriptions (e.g., "Diagnose and fix cluster issues").

**Blog Recommendation:** The skill creation article emphasizes that **descriptions determine when skills activate** and should include "verbs, use cases, and boundaries."

**Specific Improvements for existing skills:**

| Skill | Current | Improved |
|-------|---------|----------|
| troubleshoot | "Diagnose and fix cluster issues" | "Diagnose pod failures, CrashLoopBackOff, ImagePullBackOff, pending pods, and service connectivity issues. Use when pods won't start, deployments fail, or services are unreachable. Includes log analysis and resource investigation. Not for network policy or storage troubleshooting." |
| deploy | "Deploy AI agents to Kubernetes" | "Deploy AI agents via GitOps commit or immediate kubectl. Use when updating agent versions, rolling out new features, or recovering from failed deployments. Supports k8s-monitor and news-monitor. Not for initial cluster setup." |
| cluster-status | "Check cluster health" | "Check Kubernetes cluster health including node status, pod states, resource utilization, and Flux reconciliation status. Use when verifying cluster readiness, investigating slowdowns, or before deployments. Covers nodes, pods, deployments, and GitOps sync state." |
| bump-version | "Bump agent version" | "Increment semantic version (patch/minor/major) in agent pyproject.toml. Use when preparing releases, after feature completion, or before builds. Updates version string and triggers rebuild workflow. Not for hotfixes that bypass version bump." |

---

## 3. Progressive Disclosure in Skills

**Current State:** Skills in `.claude/skills/` are self-contained SKILL.md files.

**Blog Recommendation:** Use a `references/` directory for detailed schemas, patterns, and edge cases - keeping SKILL.md lean while loading details on-demand.

**Suggested Structure:**

```
.claude/skills/troubleshoot/
├── SKILL.md              # Lean workflow guidance (~50 lines)
└── references/
    ├── common-errors.md   # CrashLoopBackOff, ImagePullBackOff patterns
    ├── temporal-issues.md # Workflow debugging
    └── gitops-issues.md   # Flux reconciliation problems
```

**Example SKILL.md (lean version):**

```markdown
---
name: troubleshoot
description: Diagnose pod failures, CrashLoopBackOff, ImagePullBackOff, pending pods, and service connectivity issues. Use when pods won't start, deployments fail, or services are unreachable. Not for network policy or storage troubleshooting.
---

# Troubleshoot Cluster Issues

## Quick Diagnosis Flow

1. Identify problem pods: `kubectl get pods -A | grep -v Running`
2. Check events: `kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'`
3. Review logs: `kubectl logs $POD -n $NAMESPACE --tail=50`

## Common Issues

See references for detailed patterns:
- [Common Errors](references/common-errors.md) - CrashLoopBackOff, ImagePullBackOff, Pending
- [Temporal Issues](references/temporal-issues.md) - Workflow debugging
- [GitOps Issues](references/gitops-issues.md) - Flux reconciliation
```

---

## 4. MCP + Skills Integration

**Current State:** MCP servers (kubernetes-mcp-server, discord-mcp) and skills exist separately, but aren't tightly integrated.

**Blog Recommendation:** "MCP is like having access to the aisles. Skills are like an employee's expertise." Skills should explicitly orchestrate MCP tools.

**Specific Improvement:** Update skills to reference specific MCP tools they use:

```markdown
# In .claude/skills/troubleshoot/SKILL.md

## MCP Tools Used

This skill orchestrates the following MCP tools:

| Tool | Purpose |
|------|---------|
| `mcp__kubernetes-mcp-server__pods_list` | List pods across namespaces |
| `mcp__kubernetes-mcp-server__pods_log` | Get container logs |
| `mcp__kubernetes-mcp-server__events_list` | Check cluster events |
| `mcp__kubernetes-mcp-server__resources_get` | Get resource details |
| `mcp__discord-mcp__send_message_to_channel_name` | Notify on resolution |

## Workflow

1. Use `pods_list` to identify unhealthy pods
2. Use `events_list` to understand recent cluster activity
3. Use `pods_log` to examine container output
4. Use `resources_get` for detailed resource inspection
5. After resolution, use `send_message_to_channel_name` to notify #kubani-alerts
```

---

## 5. Agent Skills Library

**Current State:** Skills exist for Claude Code (developer workflow), but agents in `agents/` don't have their own skills library.

**Blog Recommendation:** The agents article mentions agents should have "domain expertise you want to capture and share."

**Opportunity:** Create agent-consumable skills in `skills/` that k8s-monitor and news-monitor agents can load dynamically via the `core_agents.skills` module:

```
skills/
├── TEMPLATE.md
├── kubernetes/
│   ├── restart-deployment.md     # Healer skill
│   ├── scale-resources.md        # Remediation skill
│   ├── diagnose-crashloop.md     # Diagnostic skill
│   └── evict-pod.md              # Cleanup skill
└── news/
    ├── summarize-article.md
    ├── categorize-relevance.md
    └── extract-entities.md
```

**Integration with core_agents:**

```python
from core_agents.skills import SkillsManager

skills = SkillsManager(skills_dir="/home/al/git/kubani/skills")
healer_skills = skills.load_domain("kubernetes")

# Use in agent creation
agent = factory.create_agent(AgentConfig(
    name="healer",
    system_prompt=healer_skills.get_prompt_addition(),
    ...
))
```

---

## 6. Duplicate Commands/Skills Cleanup

**Current State:** Both `.claude/commands/` (12 files) and `.claude/skills/` (14 skills) exist with overlapping names.

**Blog Recommendation:** Skills supersede commands - they load dynamically and support progressive disclosure.

**Current overlap:**

| commands/ | skills/ | Action |
|-----------|---------|--------|
| add-node.md | add-node/ | Remove command |
| bootstrap-node.md | bootstrap-node/ | Remove command |
| cluster-status.md | cluster-status/ | Remove command |
| troubleshoot.md | troubleshoot/ | Remove command |
| validate.md | validate/ | Remove command |
| new-agent.md | new-agent/ | Remove command |
| build.md | build/ | Remove command |
| deploy.md | deploy/ | Remove command |
| agents.md | agents/ | Remove command |
| rollback.md | rollback/ | Remove command |
| bump-version.md | bump-version/ | Remove command |
| minecraft-wl-user.md | (none) | Create skill or remove |

**Recommendation:** Delete `.claude/commands/` directory after verifying all functionality is in skills.

---

## 7. Context Engineering in Agent Prompts

**Current State:** The `core_agents.context` module exists with `ContextManager`, but it's optional.

**Blog Recommendation:** The enterprise agents article emphasizes "purpose-built models optimized for enterprise workflows" with explicit context management.

**Specific Improvements:**

### a) Make context manager mandatory in federated agents

```python
# In agents/k8s-monitor/src/k8s_monitor/federated/sentinel.py
from core_agents.context import ContextManager

class SentinelAgent:
    def __init__(self):
        self.ctx = ContextManager(session_id="sentinel-patrol")

    async def patrol(self):
        self.ctx.add_todo("Check pod health across namespaces")
        self.ctx.add_todo("Verify node resource utilization")

        try:
            result = await self._check_pods()
            self.ctx.complete_todo("Check pod health across namespaces")
        except TimeoutError as e:
            self.ctx.record_error(
                "API timeout during pod check",
                resolution="Retry with exponential backoff"
            )
```

### b) Add error memory to prevent repeated mistakes

```python
# Before executing remediation in Healer
async def remediate(self, issue: Issue):
    action_key = f"restart_pod:{issue.pod_name}"

    if self.ctx.has_failed_before(action_key):
        self.ctx.add_todo("Try alternative remediation - restart failed previously")
        return await self._alternative_remediation(issue)

    try:
        await self._restart_pod(issue.pod_name)
    except Exception as e:
        self.ctx.record_failure(action_key, str(e))
        raise
```

### c) Compress context for long-running sessions

```python
# In triage graph before complex analysis
if len(self.message_history) > 50:
    self.message_history = self.ctx.compress_history(
        self.message_history,
        max_tokens=4000,
        preserve_errors=True
    )
```

---

## 8. Evaluation Framework Enhancement

**Current State:** `kubani-dev eval` exists with multi-layer evaluation (automated, LLM-judge, simulation).

**Blog Recommendation:** The enterprise article mentions "80% of AI agent investments already delivering measurable economic returns" - suggesting ROI tracking.

**Opportunity:** Add economic impact metrics to evaluation:

```python
# In tools/kubani-dev/src/kubani_dev/evaluation.py

@dataclass
class EvaluationResult:
    # Existing fields
    layer: str
    passed: bool
    score: float
    details: dict

    # Add economic impact metrics
    estimated_manual_time_saved_minutes: float = 0.0
    resolution_success_rate: float = 0.0
    false_positive_rate: float = 0.0
    mean_time_to_resolution_seconds: float = 0.0

    @property
    def monthly_time_saved_hours(self) -> float:
        """Estimate monthly time savings assuming 100 incidents/month."""
        return (self.estimated_manual_time_saved_minutes * 100) / 60


@dataclass
class EvaluationSummary:
    results: list[EvaluationResult]

    def economic_summary(self) -> dict:
        return {
            "total_time_saved_minutes": sum(r.estimated_manual_time_saved_minutes for r in self.results),
            "average_success_rate": sum(r.resolution_success_rate for r in self.results) / len(self.results),
            "average_mttr_seconds": sum(r.mean_time_to_resolution_seconds for r in self.results) / len(self.results),
        }
```

---

## 9. Subagent Tool Isolation

**Current State:** Federated agent architecture exists (Sentinel, Healer, Explorer, Triage Graph) but tool access isn't explicitly restricted.

**Blog Recommendation:** Subagents should have "isolated contexts and tool restrictions" for specialized tasks.

**Opportunity:** Document and enforce tool isolation per agent:

| Agent | Tools Allowed | Tools Blocked | Rationale |
|-------|--------------|---------------|-----------|
| Sentinel | pods_list, events_list, pods_log, nodes_top, pods_top | pods_delete, resources_scale, pods_exec | Read-only monitoring |
| Healer | pods_delete, resources_scale, helm_uninstall, send_message | pods_exec | Remediation only, no shell access |
| Explorer | All read operations | All write operations | Investigation only |
| Triage | (delegates to specialists) | Direct tool access | Orchestration only |

**Implementation:**

```python
# In agents/k8s-monitor/src/k8s_monitor/federated/healer.py

HEALER_ALLOWED_TOOLS = [
    "mcp__kubernetes-mcp-server__pods_delete",
    "mcp__kubernetes-mcp-server__resources_scale",
    "mcp__kubernetes-mcp-server__resources_create_or_update",
    "mcp__discord-mcp__send_message_to_channel_name",
]

HEALER_BLOCKED_TOOLS = [
    "mcp__kubernetes-mcp-server__pods_exec",  # No shell access
]

def create_healer_agent(factory: AgentFactory) -> Agent:
    # Filter tools to only allowed ones
    allowed_tools = [t for t in all_tools if t.name in HEALER_ALLOWED_TOOLS]

    return factory.create_agent(AgentConfig(
        name="healer",
        tools=allowed_tools,
        ...
    ))
```

---

## 10. CLAUDE.md Optimization

**Current State:** CLAUDE.md is comprehensive (500+ lines).

**Blog Recommendation:** "Keep it concise" since it loads with every conversation. Use references for detailed content.

**Specific Improvements:**

### Move to reference files:

| Section | Current Location | Move To |
|---------|-----------------|---------|
| External Services table | CLAUDE.md | docs/EXTERNAL_SERVICES.md |
| Skill template explanation | CLAUDE.md | .claude/skills/README.md |
| Detailed architecture diagram | CLAUDE.md | docs/ARCHITECTURE.md |
| Model management details | CLAUDE.md | docs/MODEL_MANAGEMENT.md |
| Rollback procedures | CLAUDE.md | .claude/skills/rollback/SKILL.md |

### Target CLAUDE.md structure (~150 lines):

```markdown
# CLAUDE.md

## Project Overview
[2-3 sentences]

## Quick Commands
[Essential just commands only]

## Key Patterns
[AgentFactory, GraphFactory - brief examples]

## Skills
Check .claude/skills/ for task-specific guidance.

## Testing
just ci before commits.

## Important Paths
- .claude/skills/ - Claude Code skills
- agents/ - AI agents
- gitops/ - Kubernetes manifests
```

---

## Implementation Checklist

- [ ] Create `.claude/settings.json` with hooks configuration
- [ ] Update skill descriptions with verbs, use cases, boundaries
- [ ] Add `references/` directories to top 5 most-used skills
- [ ] Add MCP tool documentation to relevant skills
- [ ] Create agent skills in `skills/kubernetes/` and `skills/news/`
- [ ] Remove `.claude/commands/` after skill migration
- [ ] Add ContextManager to federated agents
- [ ] Add economic metrics to evaluation framework
- [ ] Document and enforce tool isolation per agent
- [ ] Refactor CLAUDE.md to ~150 lines with references

---

## Notes

- These recommendations are based on Anthropic's published best practices as of January 2026
- Implementation should be incremental - start with high-impact, low-effort items
- Test each change in isolation before combining
- Monitor Claude Code behavior after each change to verify improvement
