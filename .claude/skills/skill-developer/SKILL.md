# Skill Developer

## Description
Assist users in developing, evaluating, and improving Kubani skills using the LLM-integrated skill development workflow.

## When to Use
- User wants to create a new skill
- User wants to evaluate an existing skill
- User wants to improve a skill based on evaluation results
- User wants to promote a skill to production
- User wants to view skill evaluation history

## Prerequisites
- Kubani development environment set up
- `kubani-dev` CLI tool installed
- LLM endpoint available (defaults to Kubani LLM at https://llm.almckay.io)
- Skills directory structure exists (`skills/development`, `skills/core`, `skills/agents`)

## Workflow

### 1. Creating a New Skill

When the user wants to create a new skill:

1. **Understand the requirement**: Ask clarifying questions about:
   - What the skill should do
   - What inputs it needs
   - What outputs it should produce
   - What test cases would validate it

2. **Draft the skill**: Use the `kubani-dev skill draft` command:
   ```bash
   kubani-dev skill draft "<description>" [--llm-url <url>] [--llm-model <model>]
   ```

3. **Review the generated skill**: Check the created files:
   - `SKILL.md` - Natural language instructions
   - `test_cases.yaml` - Test cases with expected outputs
   - `metadata.json` - Skill metadata

4. **Iterate if needed**: If the user wants changes, edit the files or re-draft

### 2. Evaluating a Skill

When the user wants to evaluate a skill:

1. **Run evaluation**: Use the `kubani-dev skill eval` command:
   ```bash
   kubani-dev skill eval skills/development/<skill-name> [--verbose]
   ```

2. **Review results**: Check the evaluation output:
   - Accuracy percentage
   - Tests passed/failed
   - Average latency
   - Token usage
   - Critic feedback (semantic validation)

3. **Explain results**: Help the user understand:
   - Why tests passed or failed
   - What the critic feedback means
   - What improvements could be made

### 3. Improving a Skill

When evaluation shows issues or user wants to improve:

1. **Analyze evaluation**: Review the `latest_eval.json` file

2. **Run improvement**: Use the `kubani-dev skill improve` command:
   ```bash
   kubani-dev skill improve skills/development/<skill-name> --goals accuracy [--goals latency] [--goals tokens]
   ```

3. **Review suggestions**: The system will:
   - Extract critic feedback
   - Analyze patterns in failures
   - Generate improvement suggestions
   - Propose an improved SKILL.md

4. **Apply improvements**: If user approves, the skill will be updated

5. **Re-evaluate**: Run evaluation again to validate improvements

### 4. Promoting a Skill

When a skill is ready for production:

1. **Verify readiness**: Check:
   - Evaluation accuracy is acceptable (>80% recommended)
   - All critical test cases pass
   - Critic feedback is positive

2. **Promote the skill**: Use the `kubani-dev skill promote` command:
   ```bash
   kubani-dev skill promote skills/development/<skill-name> --category core [--bump major|minor|patch]
   ```

3. **Verify promotion**: Check that the skill appears in `skills/core/` or `skills/agents/`

### 5. Viewing Evaluation History

To review past evaluations:

```bash
kubani-dev skill eval-history skills/development/<skill-name>
```

This shows:
- Timestamp of evaluation
- Accuracy and metrics
- Test results
- Critic feedback

## Tips for Success

### Writing Good Skills
- Use clear, step-by-step instructions
- Specify exact output format with examples
- Include error handling instructions
- Test edge cases

### Interpreting Critic Feedback
- **High confidence (>0.8)**: Skill is working as intended
- **Low confidence (<0.8)**: Semantic issues, needs improvement
- **Suggestions**: Actionable recommendations from the critic

### Iteration Strategy
1. Start simple - get basic functionality working
2. Add edge cases - handle errors and special inputs
3. Optimize - improve latency and token usage
4. Polish - standardize output format and wording

### Common Issues

**Low Accuracy**
- Check if SKILL.md instructions are clear
- Verify test cases have correct expected outputs
- Look at critic feedback for semantic issues

**High Latency**
- Simplify instructions
- Reduce number of steps
- Use more efficient LLM model

**Inconsistent Outputs**
- Add explicit output format requirements
- Include multiple examples
- Use critic feedback to identify variations

## Example Workflow

```bash
# 1. Create a new skill
kubani-dev skill draft "Calculate the factorial of a number"

# 2. Evaluate it
kubani-dev skill eval skills/development/calculate-factorial --verbose

# 3. If accuracy is low, improve it
kubani-dev skill improve skills/development/calculate-factorial --goals accuracy

# 4. Re-evaluate
kubani-dev skill eval skills/development/calculate-factorial

# 5. When ready, promote to production
kubani-dev skill promote skills/development/calculate-factorial --category core

# 6. View history anytime
kubani-dev skill eval-history skills/core/calculate-factorial
```

## Integration with Claude Code

This skill is designed to work seamlessly with Claude Code:
- The `development` symlink allows Claude Code to access skills
- Skills can be edited directly in Claude Code
- Evaluation can be run from Claude Code terminal
- Results are visible in the same workspace

## Advanced Features

### Self-Verification Critic
Every evaluation includes a critic that:
- Validates semantic correctness beyond assertions
- Provides confidence scores
- Offers improvement suggestions
- Catches subtle issues assertions might miss

### Automatic Retry with Feedback
When a test fails:
- System automatically retries (up to 3 attempts)
- Failed assertions and critic feedback are passed to next attempt
- Full attempt history is tracked

### Voyager-Inspired Learning
The system is designed for continuous learning:
- Critic feedback drives improvement
- Skills can be composed hierarchically (future)
- Automatic curriculum learning (future)
- Embedding-based skill retrieval (future)

## Troubleshooting

**LLM Connection Issues**
- Default endpoint: `https://llm.almckay.io` with `nvidia/Qwen3-14B-FP4`
- Verify endpoint: `curl https://llm.almckay.io/v1/models`
- Set custom endpoint: `--llm-url http://your-endpoint --llm-model your-model`
- For local Ollama: `--llm-url http://localhost:11434 --llm-model qwen2.5:3b`

**Evaluation Timeouts**
- First test has 180s timeout (with retry)
- Subsequent tests have 120s timeout
- Use faster/smaller model for development
- Simplify skill instructions

**Skill Not Found**
- Check skill path is correct
- Verify skill has required files (SKILL.md, test_cases.yaml, metadata.json)
- Use `kubani-dev skill list` to see all skills

## Related Skills
- `skill-creator` - Original skill creation (non-LLM)
- `agent-evaluation` - Agent evaluation framework
- `continuous-learning` - Continuous learning strategies

## References
- [SKILL_DEVELOPMENT_GUIDE.md](../../docs/SKILL_DEVELOPMENT_GUIDE.md)
- [VOYAGER_ENHANCEMENT_PROPOSALS.md](../../VOYAGER_ENHANCEMENT_PROPOSALS.md)
- [CRITIC_IMPROVEMENT_INTEGRATION.md](../../CRITIC_IMPROVEMENT_INTEGRATION.md)
