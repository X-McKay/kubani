# Voyager-Inspired Enhancements for Kubani Skill System

## Introduction

Our research into the NVIDIA Voyager lifelong learning agent [1] has revealed several powerful concepts that can significantly enhance the Kubani skill development workflow. By adopting key elements of Voyager's architecture, we can transform our skill system from a manual, file-based approach to a self-improving, agentic system that continuously learns and compounds capabilities over time.

This document proposes a series of enhancements inspired by Voyager, with detailed implementation plans for each. These proposals are designed to align with our existing infrastructure and user preferences for highly agentic, continuously learning systems.

## Proposed Enhancements

We propose a phased implementation of five key enhancements, prioritized by impact and effort:

| Phase | Enhancement | Description | Benefit | Effort | Dependencies |
|-------|-------------|-------------|---------|--------|--------------|
| 1 | **Self-Verification Critic** | LLM verifies if task succeeded semantically | Higher accuracy, catches edge cases | Low (1 day) | LLM client |
| 2 | **Automatic Retry with Feedback** | Auto-retry failed evaluations with feedback | Higher success rate, less manual intervention | Low (1 day) | Evaluator |
| 3 | **Embedding-Based Skill Retrieval** | Search for skills by semantic similarity | Skill discovery, reuse, and composition | Medium (3 days) | Qdrant |
| 4 | **Skill Composition** | Build complex skills from simpler ones | Hierarchical skills, reduced duplication | Medium-High (4 days) | Skill retrieval |
| 5 | **Automatic Curriculum** | LLM proposes next skills to develop | Self-driven skill discovery | Medium (3 days) | Skill retrieval |

### Phase 1: Self-Verification Critic

**Problem:** Our current evaluation relies solely on test assertions, which may miss subtle failures or edge cases. We have no semantic understanding of success.

**Voyager Solution:** After execution, an LLM acts as a critic to verify if the task objective was truly achieved. It provides a critique and suggestions if the task failed.

**Proposed Implementation:**
1. **Extend Evaluator:** After each test case, call a new `critic_evaluate` method.
2. **Critic Prompt:** Create a prompt that asks the LLM:
   - "Did the skill successfully achieve its goal?"
   - Provide the skill description, test case input, expected output, and actual output.
3. **Parse Critic Response:** Parse the critic's response (e.g., `{"success": true, "critique": "..."}`).
4. **Update Evaluation Report:** Add the critic's feedback to the JSON and Markdown reports.
5. **Factor into Accuracy:** Consider the critic's verdict when calculating overall accuracy.

**Implementation Plan (1 day):**
- **Task 1:** Create `critic_evaluate` method in `llm_client.py`.
- **Task 2:** Implement critic prompt with detailed context.
- **Task 3:** Modify `skill_evaluator_llm.py` to call critic and parse response.
- **Task 4:** Update report generation to include critic feedback.
- **Task 5:** Test with existing skills to validate critic's effectiveness.

### Phase 2: Automatic Retry with Feedback

**Problem:** Failed evaluations require manual intervention to improve. The system doesn't automatically learn from its mistakes.

**Voyager Solution:** An iterative prompting mechanism automatically retries failed tasks with feedback until success or max iterations are reached.

**Proposed Implementation:**
1. **Add Retry Loop:** In `skill_evaluator_llm.py`, wrap the test case execution in a `for` loop (max 3 attempts).
2. **Pass Feedback:** If a test fails, pass the failure reason (assertion error, critic feedback) to the next attempt's prompt.
3. **Track Attempts:** Record each attempt's result in the evaluation history.
4. **Report Final Outcome:** Report the final success or failure after all attempts.

**Implementation Plan (1 day):**
- **Task 1:** Add retry loop to `_run_test_case` in `skill_evaluator_llm.py`.
- **Task 2:** Create a feedback mechanism to pass failure reasons to the next prompt.
- **Task 3:** Update evaluation history to store all attempts.
- **Task 4:** Test with a skill that fails on the first try to validate retry logic.

### Phase 3: Embedding-Based Skill Retrieval

**Problem:** Skills are stored in directories and are not searchable by semantic similarity. This prevents skill discovery and reuse.

**Voyager Solution:** Each skill is indexed by an embedding of its description. When a new task arrives, the system embeds the task and finds the top-5 most similar skills to use as building blocks.

**Proposed Implementation:**
1. **Generate Embeddings:** When a skill is promoted, generate an embedding of its description using an open-source embedding model (e.g., `all-MiniLM-L6-v2`).
2. **Integrate Qdrant:** Use the existing Qdrant instance in the Kubani cluster.
3. **Store Embeddings:** Create a `skills` collection in Qdrant and store the embeddings along with skill metadata (name, version, category, path).
4. **Implement Semantic Search:** Create a `kubani-dev skill-llm search` command that:
   - Takes a natural language query.
   - Embeds the query.
   - Searches Qdrant for the top-k most similar skills.
   - Displays the results with similarity scores.

**Implementation Plan (3 days):**
- **Day 1: Embedding Generation:**
  - Add `sentence-transformers` to `requirements.txt`.
  - Create a utility to generate embeddings.
  - Modify `promote` command to generate and store embeddings.
- **Day 2: Qdrant Integration:**
  - Add `qdrant-client` to `requirements.txt`.
  - Create a Qdrant client to connect to the cluster.
  - Implement methods to create collection and upsert skill vectors.
- **Day 3: Semantic Search CLI:**
  - Create `search` command in `skill_llm.py`.
  - Implement query embedding and Qdrant search.
  - Format and display search results.
  - Test end-to-end with a library of skills.

### Phase 4: Skill Composition

**Problem:** Each skill executes independently. We can't build complex skills from simpler ones, leading to code duplication and limited complexity.

**Voyager Solution:** Complex skills are synthesized by composing simpler programs. This allows for hierarchical skill trees and rapid capability compounding.

**Proposed Implementation:**
1. **Skill Reference Syntax:** Define a syntax for referencing other skills within a SKILL.md file (e.g., `{{skills.core.read-file}}`).
2. **Skill Execution Engine:** Create an engine that can:
   - Parse a SKILL.md file and identify skill references.
   - Recursively execute referenced skills.
   - Pass outputs from one skill as inputs to another.
3. **Dependency Management:** Track skill dependencies in the registry database.
4. **Handle Circular Dependencies:** Implement a mechanism to detect and prevent infinite loops.

**Implementation Plan (4 days):**
- **Day 1: Syntax and Parsing:**
  - Define skill reference syntax.
  - Create a parser to extract dependencies from SKILL.md.
- **Day 2: Execution Engine:**
  - Build a recursive execution engine.
  - Implement input/output passing between skills.
- **Day 3: Dependency Management:**
  - Add `skill_dependencies` table to registry schema.
  - Update `promote` command to record dependencies.
- **Day 4: Testing and Validation:**
  - Create a complex skill that composes multiple simpler skills.
  - Test end-to-end to validate composition.

### Phase 5: Automatic Curriculum

**Problem:** Skill development is entirely manual. The system doesn't propose new skills to develop, missing opportunities for systematic capability growth.

**Voyager Solution:** An LLM analyzes the current skill library and world state to propose the next most valuable skill to learn, maximizing exploration and novelty.

**Proposed Implementation:**
1. **Capability Analysis:** Create a prompt that asks an LLM to analyze the current skill library and summarize the agent's capabilities.
2. **Gap Identification:** Create a prompt that asks the LLM to identify gaps in the agent's capabilities based on its domain (e.g., k8s-monitor, news-monitor).
3. **Skill Proposal Generation:** Create a prompt that asks the LLM to propose a new skill to fill an identified gap, including a description and test cases.
4. **CLI Command:** Create a `kubani-dev skill-llm suggest` command to trigger the automatic curriculum.

**Implementation Plan (3 days):**
- **Day 1: Capability and Gap Analysis:**
  - Create prompts for capability and gap analysis.
  - Implement methods to interact with the LLM.
- **Day 2: Skill Proposal Generation:**
  - Create prompt for skill proposal generation.
  - Implement method to generate new skill files.
- **Day 3: CLI and Testing:**
  - Create `suggest` command in `skill_llm.py`.
  - Test with a small skill library to validate suggestions.

## Conclusion

By implementing these Voyager-inspired enhancements, we can evolve the Kubani skill system into a truly agentic, self-improving, and continuously learning platform. The proposed phased approach allows us to deliver value incrementally, starting with the highest-impact, lowest-effort features. This will significantly accelerate our progress towards building generally capable embodied agents.

## References
[1] Wang, G., Xie, Y., Jiang, Y., Mandlekar, A., Xiao, C., Zhu, Y., Fan, L., & Anandkumar, A. (2023). *Voyager: An Open-Ended Embodied Agent with Large Language Models*. arXiv preprint arXiv:2305.16291. https://arxiv.org/abs/2305.16291
