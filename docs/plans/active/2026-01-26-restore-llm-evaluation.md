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

## Solution

### Architecture

```
kubani/                          # Core library - all business logic
├── framework/
│   └── llm.py                   # Single LLM client with execute_skill(), critic_evaluate()
├── workflows/skill_auto/
│   ├── capabilities/
│   │   ├── draft_skill.py       # Draft a skill from description
│   │   ├── draft_test_cases.py  # Generate test cases
│   │   ├── evaluate_skill.py    # LLM-based evaluation (quick + full modes)
│   │   ├── improve_skill.py     # Improve skill from feedback
│   │   └── promote_skill.py     # Promote to production
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

## Implementation Tasks

### Phase 1: Commit Existing Fixes

The previous session fixed two bugs that should be committed first.

- [ ] **1.1** Run tests to verify existing changes work
- [ ] **1.2** Commit FrameworkLLM changes (uses OpenAIModel for vLLM)
- [ ] **1.3** Commit activities.py fix (await on improve_skill)

### Phase 2: Enhance FrameworkLLM

Add skill execution capabilities to `kubani/framework/llm.py`.

- [ ] **2.1** Add `execute_skill()` method
  ```python
  async def execute_skill(
      self,
      skill_sop: str,
      inputs: dict[str, Any],
      timeout: int | None = None,
  ) -> dict[str, Any]:
      """Execute a skill by having the LLM follow the SOP."""
  ```

- [ ] **2.2** Add `critic_evaluate()` method
  ```python
  async def critic_evaluate(
      self,
      skill_description: str,
      test_case_description: str,
      inputs: dict[str, Any],
      expected_output: dict[str, Any],
      actual_output: dict[str, Any],
      assertion_results: list[dict[str, Any]],
  ) -> dict[str, Any]:
      """Have LLM critic evaluate skill execution quality."""
  ```

- [ ] **2.3** Add helper methods: `_strip_thinking_tags()`, JSON extraction
- [ ] **2.4** Write unit tests

### Phase 3: Create Evaluation Config

Migrate evaluation configuration to `kubani/workflows/skill_auto/`.

- [ ] **3.1** Create `kubani/workflows/skill_auto/eval_config.py`
  - `EvalConfiguration` dataclass (model, base_url, enable_thinking, timeout)
  - `EvalMode` dataclass (quick vs full)
  - `get_default_configurations()` for 4-config matrix
  - `get_quick_configuration()` for single fast eval

- [ ] **3.2** Write unit tests

### Phase 4: Create LLM-Based Skill Evaluator

Create `kubani/workflows/skill_auto/capabilities/llm_evaluator.py`.

- [ ] **4.1** Create `SkillEvaluatorLLM` class
  ```python
  class SkillEvaluatorLLM:
      """Evaluate skills by having an LLM execute them."""

      def __init__(self, llm_client: LLMClient):
          self.llm = llm_client

      async def evaluate_skill(self, skill_dir: Path, verbose: bool = False) -> dict[str, Any]:
          """Run all test cases and return evaluation results."""

      async def _run_test_case(self, skill_sop: str, test_case: dict, is_first: bool) -> dict[str, Any]:
          """Run single test case with retry and critic evaluation."""

      def _check_assertion(self, output: dict, assertion_spec: dict, error: str | None, expected: dict) -> dict[str, Any]:
          """Check an assertion against the output."""
  ```

- [ ] **4.2** Port assertion checking logic from old code
- [ ] **4.3** Write unit tests with mock LLM client

### Phase 5: Create Evaluation Orchestrator

Create `kubani/workflows/skill_auto/capabilities/eval_orchestrator.py`.

- [ ] **5.1** Create `EvalOrchestrator` class
  ```python
  class EvalOrchestrator:
      """Orchestrate multi-configuration skill evaluation."""

      async def run_quick(self, skill_path: Path) -> dict[str, Any]:
          """Run quick single-config evaluation."""

      async def run_full(self, skill_path: Path, parallel: bool = True) -> dict[str, Any]:
          """Run full 4-config matrix evaluation."""

      async def _run_single_config(self, skill_path: Path, config: EvalConfiguration) -> dict[str, Any]:
          """Run evaluation with specific configuration."""
  ```

- [ ] **5.2** Port parallel execution logic
- [ ] **5.3** Write unit tests

### Phase 6: Create Evaluation Reporter

Create `kubani/workflows/skill_auto/capabilities/eval_reporter.py`.

- [ ] **6.1** Create `EvalReporter` class
  ```python
  class EvalReporter:
      """Generate evaluation reports and comparisons."""

      def format_quick_report(self, results: dict) -> str:
          """Format single evaluation results for CLI."""

      def format_comparison_table(self, results: list[dict]) -> str:
          """Format multi-config comparison table."""

      def format_markdown_report(self, results: list[dict]) -> str:
          """Generate full markdown report."""

      async def generate_analysis_summary(self, results: list[dict], llm: LLMClient) -> str:
          """Use LLM to generate analysis summary."""
  ```

- [ ] **6.2** Port table formatting logic
- [ ] **6.3** Write unit tests

### Phase 7: Update evaluate_skill Capability

Update `kubani/workflows/skill_auto/capabilities/evaluate_skill.py`.

- [ ] **7.1** Change to use LLM evaluator
  ```python
  async def evaluate_skill(
      client: LLMClient,
      skill_path: str,
      mode: str = "quick",  # "quick" or "full"
      parallel: bool = True,
  ) -> tuple[EvalMetrics, str]:
  ```

- [ ] **7.2** Integrate with orchestrator for multi-config
- [ ] **7.3** Update unit tests

### Phase 8: Create kubani CLI Module

Create `kubani/workflows/skill_auto/cli.py` with individual commands.

- [ ] **8.1** Create CLI entry points
  ```python
  @click.group()
  def skill():
      """Skill development commands."""

  @skill.command()
  async def draft(description: str, output_dir: str, ...):
      """Draft a new skill from description."""

  @skill.command()
  async def eval(skill_path: str, mode: str = "quick", parallel: bool = True, ...):
      """Evaluate a skill against test cases."""

  @skill.command()
  async def improve(skill_path: str, feedback: str, ...):
      """Improve a skill based on feedback."""

  @skill.command()
  async def iterate(skill_path: str, max_iterations: int = 5, target_accuracy: float = 0.8, ...):
      """Run evaluation + improvement loop."""

  @skill.command()
  async def auto(description: str, ...):
      """Full autonomous skill creation workflow (Temporal-based)."""
  ```

- [ ] **8.2** Wire up to capability functions
- [ ] **8.3** Add to kubani package entry points

### Phase 9: Update kubani-dev CLI

Update `platform/cli/src/kubani_dev/commands/skill.py` to be a thin wrapper.

- [ ] **9.1** Simplify to call kubani CLI
  ```python
  @skill_group.command(name="draft")
  @click.pass_context
  def draft_skill(ctx, description, ...):
      """Draft a new skill. (Wrapper for kubani skill draft)"""
      from kubani.workflows.skill_auto.cli import draft
      return draft(description, ...)
  ```

- [ ] **9.2** Keep cluster-specific logic in kubani-dev
- [ ] **9.3** Update help text to reference kubani CLI

### Phase 10: Update Temporal Activities

Update activities to use new evaluation.

- [ ] **10.1** Update `run_evaluation_activity`
- [ ] **10.2** Ensure workflow passes correct parameters
- [ ] **10.3** Update E2E test

### Phase 11: Verification

- [ ] **11.1** Run unit tests: `pytest kubani/workflows/skill_auto/tests/`
- [ ] **11.2** Run E2E test: `RUN_E2E_TESTS=1 pytest kubani/workflows/skill_auto/tests/test_e2e.py -v`
- [ ] **11.3** Manual test individual commands:
  ```bash
  kubani skill draft -d "A skill that sums two numbers"
  kubani skill eval kubani/skills/_development/sum-two-numbers --mode quick
  kubani skill eval kubani/skills/_development/sum-two-numbers --mode full
  kubani skill improve kubani/skills/_development/sum-two-numbers --feedback "Improve error handling"
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
| `kubani/workflows/skill_auto/capabilities/llm_evaluator.py` | LLM-based skill evaluator |
| `kubani/workflows/skill_auto/capabilities/eval_orchestrator.py` | Multi-config orchestration |
| `kubani/workflows/skill_auto/capabilities/eval_reporter.py` | Report generation |
| `kubani/workflows/skill_auto/cli.py` | CLI entry points |

### Modify (Existing Files)

| File | Changes |
|------|---------|
| `kubani/framework/llm.py` | Add `execute_skill()`, `critic_evaluate()` |
| `kubani/workflows/skill_auto/capabilities/evaluate_skill.py` | Use LLM evaluator |
| `kubani/workflows/skill_auto/temporal/activities.py` | Update evaluation activity |
| `platform/cli/src/kubani_dev/commands/skill.py` | Simplify to wrapper |
| `pyproject.toml` (kubani) | Add CLI entry point |

### Keep (No Changes)

| File | Reason |
|------|--------|
| `platform/cli/src/kubani_dev/sandbox/` | Keep for future Python-executable skills |
| `kubani/workflows/skill_auto/capabilities/improve_skill.py` | Already works |
| `kubani/workflows/skill_auto/capabilities/draft_*.py` | Already works |

---

## Success Criteria

- [ ] Unit tests pass: 160+ tests
- [ ] E2E test passes with cluster LLM
- [ ] Individual CLI commands work:
  - `kubani skill draft` creates skill files
  - `kubani skill eval --mode quick` runs single-config evaluation
  - `kubani skill eval --mode full` runs 4-config matrix
  - `kubani skill improve` improves based on feedback
  - `kubani skill iterate` runs eval/improve loop
  - `kubani skill auto` runs full Temporal workflow
- [ ] `kubani-dev skill *` commands work as wrappers
- [ ] Evaluation uses LLM to execute SKILL.md prompts
- [ ] Full mode comparison table shows large/small + thinking on/off
