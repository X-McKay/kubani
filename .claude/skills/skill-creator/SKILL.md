---
name: skill-creator
description: Create new Claude Code skills for this project. Use when adding automation, workflows, or specialized commands. Guides through skill design, templating, and registration.
---

# Skill Creator

Create new Claude Code skills tailored to this project's conventions and patterns.

## Arguments

- `skill-name`: Name for the new skill (lowercase, hyphenated)
- `--type`: Skill type: `workflow`, `command`, `reference`, `hybrid` (default: workflow)

## Instructions

### Phase 1: Understand the Request

Before creating a skill, gather requirements:

1. **What task does this skill automate?**
   - Specific operations (build, deploy, test)
   - Investigative workflows (troubleshoot, analyze, audit)
   - Information retrieval (status, list, describe)

2. **What inputs does it need?**
   - Required arguments (agent names, versions, paths)
   - Optional flags (--force, --dry-run, --verbose)
   - Environment context (current directory, git branch)

3. **What's the expected output?**
   - Actions performed (files created, commands run)
   - Information displayed (status, logs, reports)
   - State changes (deployments, configurations)

### Phase 2: Choose Skill Type

#### Workflow Skills (Most Common)
Multi-step procedures with decision points. Use for deployments, builds, troubleshooting.

```markdown
## Instructions

### Step 1: Check Prerequisites
[Commands to verify state]

### Step 2: Perform Action
[Main operation]

### Step 3: Verify Success
[Validation commands]
```

#### Command Skills
Single-purpose commands with clear inputs/outputs. Use for status checks, quick actions.

```markdown
## Instructions

### Command
\`\`\`bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents
\`\`\`

### Variations
- With labels: `--selector=app=k8s-monitor`
- Wide output: `-o wide`
```

#### Reference Skills
Documentation and guidelines loaded on-demand. Use for standards, APIs, policies.

```markdown
## Reference

### API Endpoints
- `/health` - Health check
- `/metrics` - Prometheus metrics

### Configuration Options
| Key | Type | Default | Description |
|-----|------|---------|-------------|
```

#### Hybrid Skills
Combine workflows with embedded references. Use for complex operations.

### Phase 3: Create the Skill

1. **Create the skill directory:**
   ```bash
   mkdir -p /home/al/git/kubani/.claude/skills/${SKILL_NAME}
   ```

2. **Create SKILL.md with this template:**

```markdown
---
name: ${SKILL_NAME}
description: [Concise description - this determines when Claude activates the skill. Be specific about triggers.]
---

# [Title Case Skill Name]

[One-line summary of what this skill does]

## Arguments

- \`required-arg\`: Description (required)
- \`optional-arg\`: Description (optional, default: value)
- \`--flag\`: Description of boolean flag

## Instructions

### [Step/Section Name]

[Clear instructions with code blocks]

\`\`\`bash
# Use explicit paths and environment variables
KUBECONFIG=/home/al/.kube/config kubectl [command]
\`\`\`

### [Next Step]

[Continue with logical flow]

## Examples

### Example 1: [Use Case]
\`\`\`
/skill-name arg1 --flag
\`\`\`

## Troubleshooting

### [Common Issue]
[How to resolve]
```

### Phase 4: Write Effective Descriptions

The `description` field in frontmatter is critical - it determines when Claude activates the skill.

**Good descriptions:**
- "Deploy AI agents to Kubernetes cluster. Use when deploying, updating, or checking agent versions."
- "Create a new AI agent from template. Use when adding a new agent to the cluster."

**Poor descriptions:**
- "Handles deployments" (too vague)
- "Agent stuff" (not specific)

Include:
1. Primary action (verb + noun)
2. Trigger phrases ("Use when...")
3. Key capabilities

### Phase 5: Project-Specific Conventions

Follow these patterns for this project:

**Kubernetes Commands:**
```bash
KUBECONFIG=/home/al/.kube/config kubectl [command]
```

**Git Operations:**
```bash
cd /home/al/git/kubani
git [command]
```

**Agent Operations:**
- Agents live in `agents/` directory
- GitOps manifests in `gitops/apps/ai-agents/`
- Use `just` commands when available

**Registry:**
```bash
registry.almckay.io/${AGENT_NAME}:${VERSION}
```

### Phase 6: Register the Skill

Skills are auto-discovered from `.claude/skills/*/SKILL.md`. No manual registration needed.

After creation:
1. Verify SKILL.md exists and has valid frontmatter
2. Test by asking Claude to use the skill
3. Iterate based on how well Claude understands the intent

## Skill Templates

### Template: Agent Operation Skill

```markdown
---
name: ${SKILL_NAME}
description: [Action] for AI agents. Use when [trigger conditions].
---

# [Skill Title]

[Description]

## Arguments

- \`agent-name\`: k8s-monitor, news-monitor (required)
- \`--option\`: Description

## Instructions

### 1. Validate Input

\`\`\`bash
# Check agent exists
ls /home/al/git/kubani/agents/${AGENT_NAME}/ || echo "Agent not found"
\`\`\`

### 2. Perform Operation

\`\`\`bash
cd /home/al/git/kubani
# [main operation]
\`\`\`

### 3. Verify

\`\`\`bash
KUBECONFIG=/home/al/.kube/config kubectl get pods -n ai-agents -l app=${AGENT_NAME}
\`\`\`
```

### Template: Cluster Operation Skill

```markdown
---
name: ${SKILL_NAME}
description: [Action] for Kubernetes cluster. Use when [trigger conditions].
---

# [Skill Title]

[Description]

## Instructions

### Check Current State

\`\`\`bash
KUBECONFIG=/home/al/.kube/config kubectl get [resource] -A
\`\`\`

### Perform Action

\`\`\`bash
KUBECONFIG=/home/al/.kube/config kubectl [command]
\`\`\`

### Verify

\`\`\`bash
KUBECONFIG=/home/al/.kube/config kubectl get events --sort-by='.lastTimestamp' | head -20
\`\`\`
```

### Template: GitOps Skill

```markdown
---
name: ${SKILL_NAME}
description: [Action] via GitOps. Use when [trigger conditions].
---

# [Skill Title]

[Description]

## Instructions

### 1. Modify Manifests

\`\`\`bash
cd /home/al/git/kubani
# Edit gitops/[path]/[file].yaml
\`\`\`

### 2. Commit and Push

\`\`\`bash
git add gitops/[path]/
git commit -m "chore(gitops): [description]"
git push
\`\`\`

### 3. Wait for Flux Sync

\`\`\`bash
KUBECONFIG=/home/al/.kube/config kubectl get kustomizations -n flux-system
\`\`\`
```

## Best Practices

1. **Be explicit** - Include full paths, env vars, namespaces
2. **Be defensive** - Add validation steps before destructive operations
3. **Be consistent** - Follow existing skill patterns in this project
4. **Be complete** - Include troubleshooting for common failures
5. **Be concise** - Keep instructions actionable, not verbose

## Existing Skills Reference

Review these for patterns:
- `deploy` - Multi-step GitOps workflow with immediate fallback
- `troubleshoot` - Investigative workflow with decision trees
- `new-agent` - Scaffolding with templates
- `cluster-status` - Simple command aggregation
- `build` - Earthly-based build workflow
