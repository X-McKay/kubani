# Restore LLM-Based Skill Evaluation

## Problem Summary

The recent skill-auto refactor accidentally replaced LLM-based skill evaluation with sandbox-based evaluation. This broke the workflow because:

1. **Skills are prompt-based** (SKILL.md files), not Python executables
2. The sandbox evaluator expects `skill.py` with an `execute()` function
3. Key files were deleted without proper migration:
   - `kubani_dev.llm_client.LLMClient` - had `execute_skill()` method
   - `kubani_dev.skill_evaluator_llm.SkillEvaluatorLLM` - had LLM-based evaluation
   - `kubani_dev.eval_config.py` - multi-config evaluation (large/small, thinking on/off)
   - `kubani_dev.eval_orchestrator.py` - parallel evaluation orchestration
   - `kubani_dev.eval_reporter.py` - comparison reports

## Solution: Strands AgentSkills Pattern

Use the **Strands sub-agent pattern** for skill execution instead of custom `execute_skill()` methods. This simplifies the implementation by leveraging Strands SDK's native capabilities.

### Key Insight

Skill execution is essentially creating a sub-agent with:
- SKILL.md content as system prompt
- Test inputs as the request
- JSON output validation

The Strands SDK handles this cleanly with isolated sub-agents.

### Architecture

```
kubani/                          # Core library - all business logic
├── framework/
│   └── llm.py                   # FrameworkLLM with helper methods (completed)
├── workflows/skill_auto/
│   ├── capabilities/
│   │   ├── draft_skill.py       # Draft a skill from description
│   │   ├── draft_test_cases.py  # Generate test cases
│   │   ├── evaluate_skill.py    # Strands sub-agent evaluation
│   │   ├── improve_skill.py     # Improve skill from feedback
│   │   └── promote_skill.py     # Promote to production
│   ├── eval_config.py           # Multi-config evaluation settings
│   └── cli.py                   # CLI entry points (kubani skill ...)

kubani_dev/                      # Lightweight CLI wrapper
├── commands/
│   └── skill.py                 # Thin wrapper calling kubani.workflows.skill_auto.cli
```

### CLI Commands

**kubani CLI** (in `kubani/`):
```bash
kubani skill draft -d "A skill that..."      # Draft skill
kubani skill eval <path> [--mode quick|full] # Evaluate skill
kubani skill improve <path> --feedback "..." # Improve skill
kubani skill iterate <path> [--max-iter 5]   # Eval + improve loop
kubani skill auto -d "..." [--max-iter 5]    # Full end-to-end workflow
```

**kubani-dev CLI** (wrapper + cluster commands):
```bash
kubani-dev skill draft ...    # Calls kubani skill draft
kubani-dev skill eval ...     # Calls kubani skill eval
kubani-dev deploy ...         # Cluster operations (stays in kubani-dev)
kubani-dev sync ...           # Cluster operations (stays in kubani-dev)
```

---

## Progress

### Completed

- [x] **Phase 1**: Commit existing fixes (FrameworkLLM OpenAI model, activities.py await fix)
- [x] **Phase 2**: Enhance FrameworkLLM with helper methods
  - `_strip_thinking_tags()` - Remove <think>, <reasoning>, <thought> tags
  - `_extract_json()` - Parse JSON from raw text or markdown code blocks
  - `execute_skill()` - Execute SKILL.md prompts with inputs (for backwards compat)
  - `critic_evaluate()` - Semantic verification of skill results (Voyager-inspired)
- [x] **Phase 3**: Create `kubani/workflows/skill_auto/eval_config.py`
  - EvalConfiguration, ConfigurationResult, ComparisonReport dataclasses
  - get_default_configurations() - 4-config matrix
  - get_quick_configuration() - Single config for fast evaluation
  - 21 tests passing
- [x] **Phase 4**: Create `kubani/workflows/skill_auto/capabilities/llm_evaluator.py`
  - SkillEvaluator using Strands sub-agent pattern
  - Assertion checking (exists, type, equals, contains, range)
  - Optional critic evaluation for semantic verification
  - 42 tests passing
- [x] **Phase 5**: Create `kubani/workflows/skill_auto/capabilities/eval_orchestrator.py`
  - run_quick() for single config evaluation
  - run_full() for 4-config matrix (parallel by default)
  - 16 tests passing
- [x] **Phase 6**: Create `kubani/workflows/skill_auto/capabilities/eval_reporter.py`
  - CLI formatted quick reports and comparison tables
  - Markdown and JSON export
  - LLM-powered analysis summary
  - 18 tests passing
- [x] **Phase 7**: Update `kubani/workflows/skill_auto/capabilities/evaluate_skill.py`
  - Use LLM-based evaluation instead of sandbox
  - Support mode="quick" and mode="full"
- [x] **Phase 10**: Update Temporal activities
  - run_evaluation_activity now uses async evaluate_skill
- [x] **Centralization**: Extract shared utilities to framework
  - `kubani/framework/utils/` with DefaultFileSystem, LLM parsing, iteration persistence
  - `kubani/framework/protocols.py` with FileSystemProtocol, DiscordClientProtocol, RegistryClientProtocol
  - `kubani/framework/testing/mocks.py` with MockFileSystem, MockDiscordClient
  - Refactored skill_auto and agent_auto to import from framework
  - 260 tests passing

### Remaining (Deferred)

- [ ] **Phase 8**: Create kubani CLI module (lower priority)
- [ ] **Phase 9**: Update kubani-dev CLI to wrapper (lower priority)
- [ ] **Phase 11**: Full verification with E2E tests (requires Temporal workers)

---

## Implementation Tasks (Simplified with Strands Pattern)

### Phase 3: Create Evaluation Config (COMPLETED)

Create `kubani/workflows/skill_auto/eval_config.py` for multi-configuration evaluation.

- [x] **3.1** Create config dataclasses
  ```python
  @dataclass
  class EvalConfiguration:
      name: str               # e.g., "large-thinking"
      display_name: str       # e.g., "Large + Thinking"
      model: str              # Model name
      base_url: str           # LLM endpoint
      enable_thinking: bool   # Whether to use thinking mode
      timeout: int = 300

  def get_default_configurations() -> list[EvalConfiguration]:
      """Return 4-config matrix: large/small x thinking on/off"""

  def get_quick_configuration() -> EvalConfiguration:
      """Return fast single config for quick evaluation"""
  ```

- [ ] **3.2** Write unit tests

### Phase 4: Create LLM Skill Evaluator (Strands Sub-Agent)

Create `kubani/workflows/skill_auto/capabilities/llm_evaluator.py` using Strands sub-agent pattern.

- [ ] **4.1** Create `SkillEvaluator` class
  ```python
  class SkillEvaluator:
      """Evaluate skills using Strands sub-agents."""

      async def evaluate_skill(self, skill_dir: Path, config: EvalConfiguration) -> dict:
          """Run all test cases and return evaluation results."""

      async def _run_test_case(self, skill_sop: str, test_case: dict) -> dict:
          """Run single test case with Strands sub-agent."""
          # Create isolated sub-agent with skill prompt
          model = OpenAIModel(client_args={"base_url": config.base_url}, model_id=config.model)
          agent = Agent(model=model, system_prompt=skill_sop)

          # Execute with test inputs
          result = await agent.invoke_async(json.dumps(test_case["inputs"]))
          # Parse and validate output...

      async def _critic_evaluate(self, ...) -> dict:
          """Semantic verification using critic sub-agent."""
  ```

- [ ] **4.2** Port assertion checking logic (exists, type, equals, contains)
- [ ] **4.3** Write unit tests with mock agent

### Phase 5: Create Evaluation Orchestrator

Create `kubani/workflows/skill_auto/capabilities/eval_orchestrator.py`.

- [ ] **5.1** Create `EvalOrchestrator` class
  ```python
  class EvalOrchestrator:
      """Orchestrate multi-configuration skill evaluation."""

      async def run_quick(self, skill_path: Path) -> dict:
          """Run quick single-config evaluation."""
          config = get_quick_configuration()
          return await self._run_with_config(skill_path, config)

      async def run_full(self, skill_path: Path, parallel: bool = True) -> dict:
          """Run full 4-config matrix evaluation."""
          configs = get_default_configurations()
          if parallel:
              results = await asyncio.gather(*[
                  self._run_with_config(skill_path, c) for c in configs
              ])
          else:
              results = [await self._run_with_config(skill_path, c) for c in configs]
          return {"configurations": results}
  ```

- [ ] **5.2** Write unit tests

### Phase 6: Create Evaluation Reporter

Create `kubani/workflows/skill_auto/capabilities/eval_reporter.py`.

- [ ] **6.1** Create `EvalReporter` class
  ```python
  class EvalReporter:
      def format_quick_report(self, results: dict) -> str:
          """Format single evaluation for CLI output."""

      def format_comparison_table(self, results: dict) -> str:
          """Format multi-config comparison table (rich/tabulate)."""

      async def generate_analysis_summary(self, results: dict) -> str:
          """Use LLM to generate analysis summary."""
  ```

- [ ] **6.2** Write unit tests

### Phase 7: Update evaluate_skill Capability

Update `kubani/workflows/skill_auto/capabilities/evaluate_skill.py`.

- [ ] **7.1** Replace sandbox evaluator with LLM evaluator
  ```python
  async def evaluate_skill(
      skill_path: str,
      mode: str = "quick",  # "quick" or "full"
      parallel: bool = True,
  ) -> tuple[EvalMetrics, str]:
      """Evaluate skill using Strands sub-agent pattern."""
      orchestrator = EvalOrchestrator()
      reporter = EvalReporter()

      if mode == "quick":
          results = await orchestrator.run_quick(Path(skill_path))
          feedback = reporter.format_quick_report(results)
      else:
          results = await orchestrator.run_full(Path(skill_path), parallel)
          feedback = reporter.format_comparison_table(results)

      metrics = results_to_metrics(results)
      return metrics, feedback
  ```

- [ ] **7.2** Update unit tests

### Phase 8: Create kubani CLI Module

Create `kubani/workflows/skill_auto/cli.py` with individual commands.

- [ ] **8.1** Create CLI entry points
  ```python
  import click
  import asyncio

  @click.group()
  def skill():
      """Skill development commands."""

  @skill.command()
  @click.option("--description", "-d", required=True)
  def draft(description: str):
      """Draft a new skill from description."""
      asyncio.run(_draft(description))

  @skill.command()
  @click.argument("skill_path")
  @click.option("--mode", default="quick", type=click.Choice(["quick", "full"]))
  @click.option("--parallel/--no-parallel", default=True)
  def eval(skill_path: str, mode: str, parallel: bool):
      """Evaluate a skill against test cases."""
      asyncio.run(_eval(skill_path, mode, parallel))

  @skill.command()
  @click.argument("skill_path")
  @click.option("--max-iterations", default=5)
  @click.option("--target-accuracy", default=0.8)
  def iterate(skill_path: str, max_iterations: int, target_accuracy: float):
      """Run evaluation + improvement loop."""
      asyncio.run(_iterate(skill_path, max_iterations, target_accuracy))

  @skill.command()
  @click.option("--description", "-d", required=True)
  @click.option("--max-iterations", default=5)
  def auto(description: str, max_iterations: int):
      """Full autonomous skill creation (Temporal workflow)."""
      asyncio.run(_auto(description, max_iterations))
  ```

- [ ] **8.2** Add to kubani package entry points in pyproject.toml
- [ ] **8.3** Test commands work

### Phase 9: Update kubani-dev CLI

Update `platform/cli/src/kubani_dev/commands/skill.py` to be a thin wrapper.

- [ ] **9.1** Simplify to call kubani CLI
- [ ] **9.2** Keep `auto` command for Temporal workflow (cluster-specific)
- [ ] **9.3** Update help text

### Phase 10: Update Temporal Activities

Update activities to use new evaluation.

- [ ] **10.1** Update `run_evaluation_activity` to use new `evaluate_skill`
- [ ] **10.2** Remove sandbox_type parameter (now always LLM-based)
- [ ] **10.3** Update E2E test

### Phase 11: Verification

- [ ] **11.1** Run unit tests: `pytest kubani/workflows/skill_auto/tests/`
- [ ] **11.2** Run E2E test: `RUN_E2E_TESTS=1 pytest kubani/workflows/skill_auto/tests/test_e2e.py -v`
- [ ] **11.3** Manual test individual commands:
  ```bash
  kubani skill draft -d "A skill that sums two numbers"
  kubani skill eval kubani/skills/_development/sum-two-numbers --mode quick
  kubani skill eval kubani/skills/_development/sum-two-numbers --mode full
  kubani skill iterate kubani/skills/_development/sum-two-numbers --max-iter 3
  kubani skill auto -d "A skill that calculates factorial"
  ```
- [ ] **11.4** Test kubani-dev wrappers work identically

---

## Files Summary

### Create (New Files)

| File | Purpose |
|------|---------|
| `kubani/workflows/skill_auto/eval_config.py` | Multi-config evaluation settings |
| `kubani/workflows/skill_auto/capabilities/llm_evaluator.py` | Strands sub-agent skill evaluator |
| `kubani/workflows/skill_auto/capabilities/eval_orchestrator.py` | Multi-config orchestration |
| `kubani/workflows/skill_auto/capabilities/eval_reporter.py` | Report generation |
| `kubani/workflows/skill_auto/cli.py` | CLI entry points |

### Modify (Existing Files)

| File | Changes |
|------|---------|
| `kubani/workflows/skill_auto/capabilities/evaluate_skill.py` | Use Strands evaluator |
| `kubani/workflows/skill_auto/temporal/activities.py` | Update evaluation activity |
| `platform/cli/src/kubani_dev/commands/skill.py` | Simplify to wrapper |
| `kubani/pyproject.toml` | Add CLI entry point |

### Keep (No Changes)

| File | Reason |
|------|--------|
| `kubani/framework/llm.py` | Helper methods already added |
| `platform/cli/src/kubani_dev/sandbox/` | Keep for future Python-executable skills |
| `kubani/workflows/skill_auto/capabilities/improve_skill.py` | Already works |
| `kubani/workflows/skill_auto/capabilities/draft_*.py` | Already works |

---

## Key Simplification: Strands Sub-Agent Pattern

Instead of our custom `execute_skill()` method that manually builds prompts and parses responses, we use Strands SDK's Agent directly:

**Before (complex custom code):**
```python
system_prompt = f"SKILL SOP:\n{skill_sop}\n\nCRITICAL INSTRUCTIONS:..."
user_prompt = f"Execute with inputs:\n{json.dumps(inputs)}"
response = await self.chat([{"role": "system", ...}, {"role": "user", ...}])
output = self._extract_json(response)
```

**After (Strands sub-agent):**
```python
from strands import Agent
from strands.models.openai import OpenAIModel

model = OpenAIModel(client_args={"base_url": config.base_url}, model_id=config.model)
agent = Agent(model=model, system_prompt=skill_sop)
result = await agent.invoke_async(request)
```

Benefits:
- Cleaner code
- Isolated context per skill execution
- Native streaming support
- Consistent with rest of Kubani (uses Strands everywhere)
- The `execute_skill()` and `critic_evaluate()` methods we added can remain for backwards compatibility but the evaluator uses Strands directly

---

## Success Criteria

- [ ] Unit tests pass: 170+ tests
- [ ] E2E test passes with cluster LLM
- [ ] Individual CLI commands work:
  - `kubani skill draft` creates skill files
  - `kubani skill eval --mode quick` runs single-config evaluation
  - `kubani skill eval --mode full` runs 4-config matrix
  - `kubani skill iterate` runs eval/improve loop
  - `kubani skill auto` runs full Temporal workflow
- [ ] `kubani-dev skill *` commands work as wrappers
- [ ] Evaluation uses Strands sub-agents to execute SKILL.md prompts
- [ ] Full mode comparison table shows large/small + thinking on/off
