# Skill Development Workflow - Next Steps

This document outlines the remaining implementation work for the complete skill development workflow system.

## ✅ Completed (MVP)

### Phase 1: Foundation & Infrastructure
- [x] Created `skills/` directory structure (development, core, agents)
- [x] Established symlink: `.claude/skills/development` → `skills/development`
- [x] Implemented `kubani-dev skill` CLI command group:
  - `draft`: Create skills from templates
  - `list`: List all skills by category
  - `info`: Show detailed skill information
  - `promote`: Move skills from development to production
  - `eval`: Evaluate skills locally
  - `eval-history`: Placeholder for viewing history

### Phase 2: Evaluation System
- [x] Built `SkillEvaluator` with subprocess-based execution
- [x] Implemented test case parsing from `test_cases.yaml`
- [x] Created assertion validation system (equals, exists, performance)
- [x] Generated evaluation reports (JSON + Markdown)
- [x] Integrated with CLI for local evaluation

### Phase 3: Database Models
- [x] Extended registry database models:
  - `Skill`: Core skill metadata
  - `SkillVersion`: Version history
  - `SkillEvaluation`: Evaluation results
  - `SkillSyncStatus`: Git sync tracking
- [x] Created Alembic migration for new tables

## 🚧 Remaining Work

### Phase 4: Registry API Endpoints

**Priority: High**  
**Estimated Effort: 2-3 days**

Create REST API endpoints in the registry service for skill management:

```python
# registry/src/kubani_registry/api/v1/skills.py

POST   /api/v1/skills                  # Register a new skill
GET    /api/v1/skills                  # List all skills
GET    /api/v1/skills/{id}             # Get skill by ID
PUT    /api/v1/skills/{id}             # Update skill metadata
DELETE /api/v1/skills/{id}             # Delete skill

POST   /api/v1/skills/{id}/versions    # Create new version
GET    /api/v1/skills/{id}/versions    # List versions

POST   /api/v1/skills/{id}/evaluations # Submit evaluation result
GET    /api/v1/skills/{id}/evaluations # Get evaluation history
```

**Implementation Steps:**
1. Create `registry/src/kubani_registry/api/v1/skills.py`
2. Define Pydantic request/response models
3. Implement CRUD operations using SQLAlchemy
4. Add to FastAPI router in `endpoints.py`
5. Write unit tests for each endpoint

### Phase 5: CLI Database Integration

**Priority: High**  
**Estimated Effort: 1-2 days**

Update `kubani-dev skill` commands to interact with the registry:

**Changes Needed:**
- `eval` command: Submit results to registry after local evaluation
- `eval-history` command: Query registry for historical evaluations
- `promote` command: Register skill in database when promoting
- `list` command: Option to query registry instead of filesystem

**Implementation:**
```python
# tools/kubani-dev/src/kubani_dev/registry_client.py

class RegistryClient:
    def __init__(self, registry_url: str):
        self.base_url = registry_url
    
    def register_skill(self, skill_data: dict) -> dict:
        """Register a skill in the registry."""
        pass
    
    def submit_evaluation(self, skill_id: int, eval_data: dict) -> dict:
        """Submit evaluation results."""
        pass
    
    def get_evaluation_history(self, skill_id: int) -> list:
        """Get evaluation history for a skill."""
        pass
```

### Phase 6: Microsandbox Integration

**Priority: Medium**  
**Estimated Effort: 2-3 days**

Replace subprocess execution with actual microsandbox:

1. **Install microsandbox:**
   ```bash
   pip install microsandbox
   ```

2. **Update `MicrosandboxRunner`:**
   ```python
   from microsandbox import Sandbox
   
   def _execute_in_sandbox(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
       with Sandbox() as sandbox:
           # Copy skill files into sandbox
           sandbox.copy_file(self.skill_dir / "skill.py", "/skill.py")
           
           # Execute skill
           result = sandbox.run_python(f"""
           from skill import execute
           import json
           result = execute({json.dumps(inputs)})
           print(json.dumps(result))
           """)
           
           return json.loads(result.stdout)
   ```

3. **Add Docker fallback** for when microsandbox is unavailable

### Phase 7: Temporal Workflow for Cluster Evaluation

**Priority: Medium**  
**Estimated Effort: 3-4 days**

Create Temporal workflow for running evaluations in the cluster:

```python
# agents/core/src/core_agents/workflows/skill_evaluation.py

@workflow.defn
class SkillEvaluationWorkflow:
    @workflow.run
    async def run(self, skill_name: str, version: str) -> dict:
        # 1. Fetch skill from registry
        skill = await workflow.execute_activity(
            fetch_skill_activity,
            skill_name,
            start_to_close_timeout=timedelta(seconds=30)
        )
        
        # 2. Create microsandbox in cluster
        sandbox_id = await workflow.execute_activity(
            create_sandbox_activity,
            start_to_close_timeout=timedelta(seconds=60)
        )
        
        # 3. Run evaluation
        results = await workflow.execute_activity(
            run_evaluation_activity,
            sandbox_id,
            skill,
            start_to_close_timeout=timedelta(minutes=10)
        )
        
        # 4. Submit results to registry
        await workflow.execute_activity(
            submit_results_activity,
            results,
            start_to_close_timeout=timedelta(seconds=30)
        )
        
        return results
```

**Update CLI:**
```python
# When --local is NOT specified, trigger Temporal workflow
if not local:
    workflow_client = TemporalClient(config.temporal_url)
    workflow_id = f"skill-eval-{name}-{int(time.time())}"
    
    handle = await workflow_client.start_workflow(
        SkillEvaluationWorkflow.run,
        name,
        id=workflow_id,
        task_queue="kubani-tasks"
    )
    
    click.echo(f"Started workflow: {workflow_id}")
    click.echo(f"Track at: {config.temporal_ui_url}/workflows/{workflow_id}")
```

### Phase 8: Skill Developer Agent

**Priority: Medium**  
**Estimated Effort: 3-5 days**

Create a conversational agent for skill development:

```markdown
# .claude/skills/skill-developer/SKILL.md

# Skill Developer Agent

## Description

An interactive agent that helps developers create, test, and refine skills through natural language conversation.

## Capabilities

1. **Skill Creation**
   - Ask clarifying questions about the skill's purpose
   - Generate SKILL.md with proper structure
   - Create skill.py implementation
   - Generate comprehensive test cases

2. **Iterative Improvement**
   - Run evaluations automatically
   - Analyze failures and suggest fixes
   - Apply improvements and re-evaluate
   - Continue until all tests pass

3. **Best Practices**
   - Suggest error handling patterns
   - Recommend input validation
   - Propose additional test cases
   - Ensure documentation completeness

## Workflow

1. User: "Create a skill to find unused ConfigMaps in Kubernetes"
2. Agent: Asks clarifying questions (namespace scope, age threshold, etc.)
3. Agent: Generates skill files
4. Agent: Runs evaluation
5. Agent: If failures, proposes fixes
6. User: Approves or requests changes
7. Agent: Applies fixes and re-evaluates
8. Agent: When passing, suggests promotion

## Implementation

```python
from strands import Agent, skill

@skill
async def develop_skill(
    description: str,
    requirements: dict = None
) -> dict:
    # 1. Clarify requirements
    requirements = await clarify_requirements(description)
    
    # 2. Generate skill files
    skill_name = await generate_skill_name(description)
    await execute_command(f"kubani-dev skill draft {skill_name} -d '{description}'")
    
    # 3. Generate implementation
    implementation = await generate_implementation(requirements)
    await write_file(f"skills/development/{skill_name}/skill.py", implementation)
    
    # 4. Generate test cases
    test_cases = await generate_test_cases(requirements)
    await write_file(f"skills/development/{skill_name}/test_cases.yaml", test_cases)
    
    # 5. Evaluate
    eval_result = await execute_command(f"kubani-dev skill eval {skill_name} --local")
    
    # 6. Iterate on failures
    while eval_result["accuracy"] < 1.0:
        fixes = await propose_fixes(eval_result)
        await apply_fixes(skill_name, fixes)
        eval_result = await execute_command(f"kubani-dev skill eval {skill_name} --local")
    
    return {
        "skill_name": skill_name,
        "status": "ready_for_promotion",
        "evaluation": eval_result
    }
```
```

### Phase 9: Automated PR Creation

**Priority: Low**  
**Estimated Effort: 2-3 days**

Implement automatic PR creation when cluster improves a skill:

```python
# agents/core/src/core_agents/skills/create_skill_pr.py

async def create_skill_improvement_pr(
    skill_name: str,
    improvements: dict,
    evaluation_results: dict
) -> dict:
    # 1. Create branch
    branch_name = f"skill-improvement/{skill_name}-{int(time.time())}"
    await execute_command(f"git checkout -b {branch_name}")
    
    # 2. Apply improvements
    skill_path = f"skills/core/{skill_name}/v{improvements['version']}"
    await write_files(skill_path, improvements['files'])
    
    # 3. Commit changes
    commit_msg = f"""Improve skill: {skill_name}

Automated improvement by cluster evaluation.

Changes:
{improvements['changelog']}

Evaluation Results:
- Accuracy: {evaluation_results['accuracy']:.1%}
- Avg Latency: {evaluation_results['avg_latency_ms']:.0f}ms
- Tests Passed: {evaluation_results['tests_passed']}/{evaluation_results['tests_total']}
"""
    await execute_command(f"git add {skill_path}")
    await execute_command(f"git commit -m '{commit_msg}'")
    
    # 4. Push and create PR
    await execute_command(f"git push origin {branch_name}")
    
    pr_body = f"""## Skill Improvement: {skill_name}

This PR contains automated improvements to the `{skill_name}` skill based on cluster evaluation.

### Evaluation Results
- **Accuracy:** {evaluation_results['accuracy']:.1%}
- **Avg Latency:** {evaluation_results['avg_latency_ms']:.0f}ms
- **Tests Passed:** {evaluation_results['tests_passed']}/{evaluation_results['tests_total']}

### Changes
{improvements['changelog']}

### Review Checklist
- [ ] Review code changes
- [ ] Verify evaluation results
- [ ] Test manually if needed
- [ ] Approve and merge

---
*Generated by Kubani Skill Workflow*
"""
    
    pr_result = await execute_command(f"""
    gh pr create \
        --title "Improve skill: {skill_name}" \
        --body "{pr_body}" \
        --label "skill-improvement,automated"
    """)
    
    # 5. Update sync status in registry
    await registry_client.update_sync_status(
        skill_name=skill_name,
        pr_number=pr_result['number'],
        pr_status='open',
        sync_direction='cluster_to_git'
    )
    
    return pr_result
```

### Phase 10: Periodic Sync Job

**Priority: Low**  
**Estimated Effort: 1-2 days**

Create a CronJob to sync skills between cluster and Git:

```yaml
# gitops/apps/ai-agents/skill-sync-job/cronjob.yaml

apiVersion: batch/v1
kind: CronJob
metadata:
  name: skill-sync-job
  namespace: ai-agents
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: skill-sync
            image: registry.almckay.io/kubani-core:latest
            command:
            - python
            - -m
            - core_agents.jobs.skill_sync
            env:
            - name: REGISTRY_URL
              value: "http://kubani-registry:8000"
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: github-token
                  key: token
```

## Testing Strategy

### Unit Tests
- Test each CLI command independently
- Test evaluation logic with mock skills
- Test database models and migrations
- Test registry API endpoints

### Integration Tests
- Test full workflow: draft → eval → promote
- Test registry integration
- Test Temporal workflow execution
- Test PR creation flow

### End-to-End Tests
- Create skill via CLI
- Evaluate locally
- Promote to production
- Trigger cluster evaluation
- Verify results in registry
- Test automatic PR creation

## Deployment Checklist

- [ ] Run database migrations on cluster
- [ ] Deploy updated registry service
- [ ] Deploy Skill Developer Agent
- [ ] Configure GitHub token for PR creation
- [ ] Set up skill-sync CronJob
- [ ] Update documentation
- [ ] Train team on new workflow

## Success Metrics

- **Developer Velocity:** Time to create and deploy a new skill
- **Evaluation Coverage:** % of skills with comprehensive test cases
- **Automation Rate:** % of skill improvements created automatically
- **Merge Rate:** % of automated PRs that get merged without changes
- **Skill Quality:** Average evaluation accuracy across all skills

## Future Enhancements

1. **LLM-as-Judge Evaluation:** Use LLM to evaluate skill quality beyond test cases
2. **Skill Composition:** Allow skills to call other skills
3. **Performance Benchmarking:** Track performance trends over time
4. **A/B Testing:** Compare skill versions in production
5. **Skill Marketplace:** Share skills across teams/organizations
6. **Visual Skill Builder:** Web UI for creating skills without code
7. **Skill Analytics:** Dashboard showing usage, performance, errors
8. **Automatic Test Generation:** LLM generates test cases from SKILL.md

## Resources

- [Anthropic: Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Anthropic: Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [Strands Agent SOPs](https://strandsagents.com/latest/documentation/docs/user-guide/evals-sdk/eval-sop/)
- [Microsandbox](https://github.com/zerocore-ai/microsandbox)
- [Voyager (Minecraft Agent)](https://voyager.minedojo.org/)
