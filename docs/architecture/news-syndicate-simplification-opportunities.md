# News Syndicate: Simplification Opportunities

**Date:** 2026-01-28
**Status:** Analysis for Discussion
**Related:** [News Syndicate Analysis](./news-syndicate-analysis.md)

---

## The Core Insight

After exploring the skills and MCP architecture, I found a significant disconnect:

**Skills exist as declarative definitions, but agents re-implement everything in Python code.**

| Skill Definition | Agent Implementation |
|------------------|---------------------|
| `news/diagnostic/analyze-article` (85 lines SKILL.md) | `ContentAnalystAgent._analyze_single_article` (70+ lines Python) |
| `news/collection/fetch-rss-feeds` (86 lines SKILL.md) | `FeedCollectorAgent._collect_from_feed` (80+ lines Python) |
| `news/action/compose-digest` (119 lines SKILL.md) | `DigestPublisherAgent._compose_digest` (200+ lines Python) |

The skills describe what to do. The agents duplicate that logic in code.

---

## The Solution: Strands AgentSkills

The Strands SDK has a pattern for this: **AgentSkills**. There's an [AWS sample implementation](https://github.com/aws-samples/sample-strands-agents-agentskills) and an [agent-skills-sdk](https://pypi.org/project/agent-skills-sdk/) package that implements the [AgentSkills.io standard](https://agentskills.io).

### How It Works

**1. Skills are discovered from SKILL.md files:**
```python
from strands_agentskills import discover_skills, create_skill_tool

skills = discover_skills("./kubani/skills/news")
```

**2. Skills can be exposed to agents in three patterns:**

| Pattern | How It Works | Best For |
|---------|--------------|----------|
| **File-based** | LLM reads SKILL.md via `file_read` tool | Maximum flexibility |
| **Tool-based** | `skill(name)` tool loads instructions on demand | Token tracking, structured control |
| **Meta-Tool** | Each skill runs in isolated sub-agent | Context separation, per-skill tool restrictions |

**3. Progressive Disclosure (token efficiency):**
- **Phase 1** (~100 tokens/skill): Load only metadata initially
- **Phase 2** (<5000 tokens): Load full SKILL.md when skill activates
- **Phase 3** (as needed): Load resource files on demand

### What This Means for Kubani

Our SKILL.md files already follow the AgentSkills.io format! We just need to:

1. Add the `strands-agentskills` package
2. Update `KubaniAgent` to use skill discovery
3. Remove hardcoded prompts from agent code

---

## Before vs After: ContentAnalystAgent

### Before (777 lines)

```python
class ContentAnalystAgent(KubaniAgent):
    # Prompt embedded in code (duplicates skill spec)
    ANALYSIS_PROMPT = """Analyze the following news article and provide:
        1. Summary: A concise 2-3 sentence summary...
        2. Category: One of: research, business...
        ..."""

    def _analyze_single_article(self, article):
        # Step 1: Prepare content (duplicates skill step 1)
        content = f"{title}\n\n{summary}"
        if len(content) > 2000:
            content = content[:2000]

        # Step 2: Call LLM (duplicates skill step 2)
        response = client.chat.completions.create(
            model=self._get_model(),
            messages=[
                {"role": "system", "content": "You are an AI news analyst..."},
                {"role": "user", "content": self.ANALYSIS_PROMPT.format(...)},
            ],
        )

        # Step 3: Parse response (duplicates skill step 3)
        # ... 50+ more lines
```

### After (~150 lines)

```python
from strands_agentskills import discover_skills, create_skill_tool

class ContentAnalystAgent(KubaniAgent):
    """Content analysis using AgentSkills pattern."""

    def __init__(self):
        super().__init__()

        # Discover skills from the news/diagnostic directory
        self.skills = discover_skills(Path(__file__).parent.parent.parent / "skills/news")
        self.skill_tool = create_skill_tool(self.skills, self.skills_dir)

    def _create_agent(self) -> Agent:
        """Create agent with skill tool."""
        from strands import Agent
        from strands_agentskills import generate_skills_prompt

        # Generate system prompt that includes skill metadata
        base_prompt = self.prompt  # From prompt.md
        skills_prompt = generate_skills_prompt(self.skills)

        return Agent(
            model=self._get_model(),
            system_prompt=f"{base_prompt}\n\n{skills_prompt}",
            tools=[self.skill_tool, file_read],  # Agent can invoke skills
        )

    async def analyze_articles(self, articles: list[dict]) -> AnalysisResult:
        """Analyze articles - agent will use analyze-article skill."""
        prompt = f"Analyze these {len(articles)} articles for insights and trends."

        # Agent naturally discovers and uses the analyze-article skill
        result = await self.agent.invoke_async(prompt)

        return self._parse_result(result)
```

**The agent doesn't implement the analysis logic - it uses the skill!**

---

## Before vs After: DigestPublisherAgent

### Before (1300 lines)

- 5 different LLM prompts hardcoded
- Multiple formatting methods
- History tracking logic
- Chunk splitting logic

### After (~200 lines)

```python
from strands_agentskills import discover_skills, create_skill_tool

class DigestPublisherAgent(KubaniAgent):
    """Digest composition using AgentSkills pattern."""

    def __init__(self):
        super().__init__()
        self.skills = discover_skills(Path(__file__).parent.parent.parent / "skills/news")
        self.skill_tool = create_skill_tool(self.skills, self.skills_dir)

    def _create_agent(self) -> Agent:
        from strands import Agent
        from strands_agentskills import generate_skills_prompt

        return Agent(
            model=self._get_model(),
            system_prompt=f"{self.prompt}\n\n{generate_skills_prompt(self.skills)}",
            tools=[
                self.skill_tool,
                file_read,
                self._discord_tool,  # Wrap Discord MCP
                self._memory_tool,   # Wrap Memory MCP for history
            ],
        )

    async def compose_and_publish(self, articles, trends, channel):
        """Agent uses compose-digest and publish-to-discord skills."""
        prompt = f"""
        Compose a digest from these {len(articles)} articles and publish to #{channel}.
        Trends: {trends}
        """
        return await self.agent.invoke_async(prompt)
```

---

## Implementation Plan

### Phase 1: Add AgentSkills Package

```bash
# Add dependency
uv add strands-agentskills
# or
uv add agent-skills-sdk
```

### Phase 2: Update KubaniAgent Base Class

```python
# kubani/agents/_base/agent.py

from strands_agentskills import discover_skills, create_skill_tool, generate_skills_prompt

class KubaniAgent(ABC):
    def __init__(self, agent_dir: Path | None = None):
        super().__init__()
        self._agent_dir = self._resolve_agent_dir(agent_dir)

        # Discover skills based on config
        skills_config = self.config.get("skills", {})
        if skills_paths := skills_config.get("paths"):
            self._skills = self._discover_skills(skills_paths)
            self._skill_tool = create_skill_tool(self._skills, self._skills_dir)
        else:
            self._skills = []
            self._skill_tool = None

    def _discover_skills(self, paths: list[str]) -> list:
        """Discover skills from configured paths."""
        all_skills = []
        for path in paths:
            skills_dir = Path(path)
            if skills_dir.exists():
                all_skills.extend(discover_skills(skills_dir))
        return all_skills

    @property
    def skills_prompt(self) -> str:
        """Generate skills metadata for system prompt."""
        if self._skills:
            return generate_skills_prompt(self._skills)
        return ""

    def _create_agent(self) -> Agent:
        """Create agent with skill tools."""
        tools = self.get_additional_tools()
        if self._skill_tool:
            tools.append(self._skill_tool)

        return Agent(
            model=self._get_model(),
            system_prompt=f"{self.prompt}\n\n{self.skills_prompt}",
            tools=tools,
        )
```

### Phase 3: Update Agent Configs

```yaml
# kubani/agents/content_analyst/config.yaml
name: content-analyst
version: "1.0.0"

skills:
  paths:
    - kubani/skills/news/diagnostic
    - kubani/skills/news/collection
  # No more allowed/denied patterns needed - skills are discovered
```

### Phase 4: Simplify Agents

Remove hardcoded prompts and logic, let agents use discovered skills.

---

## Comparison: Current vs AgentSkills Approach

| Aspect | Current | With AgentSkills |
|--------|---------|------------------|
| **Prompts** | Hardcoded in Python | In SKILL.md files |
| **Agent code** | 700-1300 lines | 150-200 lines |
| **Skill reuse** | Copy-paste | Discover and reference |
| **Token efficiency** | Load everything | Progressive disclosure |
| **Prompt updates** | Code change required | Edit SKILL.md |
| **Testing** | Mock LLM calls | Test skill definitions |

---

## Code Reduction Summary

| Component | Current | After | Reduction |
|-----------|---------|-------|-----------|
| ContentAnalystAgent | 777 lines | ~150 lines | **81%** |
| DigestPublisherAgent | 1300 lines | ~200 lines | **85%** |
| FeedCollectorAgent | 314 lines | ~100 lines | **68%** |
| ResearchAnalystAgent | ~500 lines | ~150 lines | **70%** |
| **Total** | ~2900 lines | ~600 lines | **79%** |

---

## What About MCP?

AgentSkills handles the **skill discovery and LLM orchestration** side. MCP handles the **tool execution** side.

They complement each other:

```
┌─────────────────────────────────────────────────────────────┐
│                        Agent                                 │
│                                                              │
│  ┌─────────────────┐              ┌─────────────────┐       │
│  │  AgentSkills    │              │   MCP Tools     │       │
│  │  (What to do)   │              │   (How to do)   │       │
│  │                 │              │                 │       │
│  │  - analyze-article              │  - Memory MCP   │       │
│  │  - compose-digest               │  - Discord MCP  │       │
│  │  - detect-breaking              │  - Feeds MCP    │       │
│  └─────────────────┘              └─────────────────┘       │
│         ↓                                ↓                   │
│    Skill instructs              Tool executes               │
│    "analyze this article"       "store to memory"           │
└─────────────────────────────────────────────────────────────┘
```

The agent:
1. Loads skills (prompts, instructions)
2. Decides which skill to use
3. Executes skill (LLM reasoning)
4. Calls MCP tools (actions)

---

## Next Steps

1. **Evaluate packages**: Test `strands-agentskills` vs `agent-skills-sdk` with Kubani's setup
2. **Fix MCP transport first**: The existing MCP fix is still needed
3. **Proof of concept**: Simplify ContentAnalystAgent using AgentSkills
4. **Roll out**: Apply pattern to other agents

---

## Sources

- [AWS Sample: strands-agents-agentskills](https://github.com/aws-samples/sample-strands-agents-agentskills)
- [agent-skills-sdk on PyPI](https://pypi.org/project/agent-skills-sdk/)
- [Strands SDK Skills Feature Request](https://github.com/strands-agents/sdk-python/issues/1181)
- [AgentSkills.io Standard](https://agentskills.io)
