# Kubani Restructuring Implementation Plan

> **Status**: Draft
> **Design Doc**: [2026-01-22-kubani-restructuring-design.md](./2026-01-22-kubani-restructuring-design.md)
> **Date**: 2026-01-22

---

## Overview

This plan outlines the incremental migration from the current `agents/` structure to the new `kubani/` structure with clear separation of Skills, Agents, and Syndicates.

**Key Decisions:**
- SOPs move under `kubani/syndicates/`
- Skills are versioned (mechanism TBD in Phase 1)
- Only syndicates are deployed (not standalone agents)
- Hot-reload for skills: research during Phase 1, implement if feasible

---

## Phase 0: Preparation

**Goal**: Set up the new structure without breaking existing functionality.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 0.1 | Create `kubani/` directory structure | No |
| 0.2 | Set up Python package structure (`pyproject.toml`, `__init__.py`) | No |
| 0.3 | Decide on skill versioning strategy | **Yes** - Git tags? Semantic versioning in SKILL.md? Registry-based? |
| 0.4 | Research hot-reload patterns for MCP tools | **Yes** - Need to investigate MCP spec for tool refresh |
| 0.5 | Update `.gitignore` and CI/CD for new paths | No |

### Deliverables
- Empty directory structure in place
- Decision document on skill versioning
- Research notes on hot-reload feasibility

---

## Phase 1: Framework

**Goal**: Build the shared framework that agents and syndicates depend on.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 1.1 | Create `kubani/framework/config.py` | No - port from `config_unified.py` |
| 1.2 | Create `kubani/framework/mcp/client.py` | No |
| 1.3 | Create `kubani/framework/mcp/skills.py` (skill filtering) | No |
| 1.4 | Create `kubani/framework/events/bus.py` | No - port from existing |
| 1.5 | Create `kubani/framework/a2a/` module | **Yes** - Confirm A2A spec version to target |
| 1.6 | Create `kubani/framework/testing/mocks.py` | No |
| 1.7 | Port `memory/`, `learning/`, `observability/` from core | No - mostly copy with minor refactoring |
| 1.8 | Create `kubani/agents/_base/agent.py` (KubaniAgent) | No |
| 1.9 | Create `kubani/syndicates/_base/syndicate.py` | No |
| 1.10 | Write framework tests | No |

### Dependencies
- Phase 0 complete

### Deliverables
- Working `kubani/framework/` package
- Base classes for agents and syndicates
- Tests passing

---

## Phase 2: Skills MCP Server

**Goal**: Build the MCP server that exposes skills as tools.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 2.1 | Create `tools/skills-mcp/` directory structure | No |
| 2.2 | Implement skill discovery (load SKILL.md files) | No |
| 2.3 | Implement `tools/list` with agent filtering | No |
| 2.4 | Implement `tools/call` with script execution | **Yes** - Sandboxing approach: subprocess? Container? |
| 2.5 | Implement outcome recording for learning | No |
| 2.6 | Add skill versioning metadata | Depends on Phase 0.3 decision |
| 2.7 | Write MCP server tests | No |
| 2.8 | Create Dockerfile and Earthfile | No |
| 2.9 | Add GitOps manifests for deployment | No |

### Dependencies
- Phase 1 complete (for skill filtering logic)

### Deliverables
- Working Skills MCP Server
- Can list and execute skills
- Deployed to cluster (shadow mode initially)

---

## Phase 3: Migrate Skills

**Goal**: Move existing skills to new structure and format.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 3.1 | Move `agents/skills/` to `kubani/skills/` | No |
| 3.2 | Audit skills: which need `scripts/` directories? | **Yes** - Review each skill's execution model |
| 3.3 | Update SKILL.md files to AgentSkills.io format | No |
| 3.4 | Add version metadata to each skill | Depends on versioning decision |
| 3.5 | Migrate skill tests to new location | No |
| 3.6 | Verify skills work via Skills MCP Server | No |

### Dependencies
- Phase 2 complete

### Deliverables
- All skills in `kubani/skills/`
- Skills executable via Skills MCP Server
- Skill tests passing

---

## Phase 4: Extract Agents

**Goal**: Extract federated agents into standalone agent definitions.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 4.1 | Create `kubani/agents/sentinel/` | No |
| 4.2 | Extract Sentinel prompt to `prompt.md` | No |
| 4.3 | Extract Sentinel config to `config.yaml` | No |
| 4.4 | Create minimal `agent.py` for Sentinel | No |
| 4.5 | Write Sentinel tests | No |
| 4.6 | Create Sentinel eval suite | **Yes** - What scenarios to prioritize? |
| 4.7 | Repeat 4.1-4.6 for Healer | No |
| 4.8 | Repeat 4.1-4.6 for Explorer | No |
| 4.9 | Create Analyst agent (from news-monitor) | **Yes** - Confirm this is the right abstraction |
| 4.10 | Create Composer agent (from news-monitor) | **Yes** - Confirm this is the right abstraction |

### Dependencies
- Phase 1 complete (base classes)
- Phase 3 complete (skills available)

### Deliverables
- 5 agents extracted: Sentinel, Healer, Explorer, Analyst, Composer
- Each has tests and eval suite
- Agents work with Skills MCP Server

---

## Phase 5: Create Syndicates

**Goal**: Build syndicates that orchestrate the extracted agents.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 5.1 | Create `kubani/syndicates/k8s-monitor/` | No |
| 5.2 | Implement k8s-monitor `syndicate.py` | No |
| 5.3 | Port Temporal workflows to `workflows/` | No |
| 5.4 | Create k8s-monitor config.yaml | No |
| 5.5 | Write k8s-monitor syndicate tests | No |
| 5.6 | Create k8s-monitor eval suite | **Yes** - End-to-end scenarios needed |
| 5.7 | Verify k8s-monitor behavior matches current | No |
| 5.8 | Create `kubani/syndicates/news-digest/` | No |
| 5.9 | Implement news-digest syndicate | No |
| 5.10 | Verify news-digest behavior matches current | No |

### Dependencies
- Phase 4 complete (agents available)

### Deliverables
- k8s-monitor syndicate working
- news-digest syndicate working
- Behavior verified against current implementation

---

## Phase 6: Migrate SOPs

**Goal**: Move SOPs under syndicates.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 6.1 | Create `kubani/syndicates/_sops/` or integrate into syndicates | **Yes** - Shared SOPs vs syndicate-specific? |
| 6.2 | Move `infrastructure/sops/k8s/` content | No |
| 6.3 | Update SOP references to use new skill paths | No |
| 6.4 | Update SOPExecutor to work with new structure | No |

### Dependencies
- Phase 5 complete

### Deliverables
- SOPs in new location
- SOPs execute correctly with new skills

---

## Phase 7: Deployment & Cutover

**Goal**: Deploy new structure and deprecate old.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 7.1 | Update GitOps manifests for new structure | No |
| 7.2 | Deploy k8s-monitor syndicate (shadow mode) | No |
| 7.3 | Run both old and new in parallel, compare behavior | No |
| 7.4 | Deploy news-digest syndicate (shadow mode) | No |
| 7.5 | Cutover: route traffic to new syndicates | **Yes** - Rollback plan if issues? |
| 7.6 | Deprecate old `agents/k8s-monitor/` | No |
| 7.7 | Deprecate old `agents/news-monitor/` | No |
| 7.8 | Remove deprecated code after stabilization | No |
| 7.9 | Update kubani CLI for new structure | No |
| 7.10 | Update documentation | No |

### Dependencies
- Phase 6 complete

### Deliverables
- New structure deployed and stable
- Old structure deprecated/removed
- Documentation updated

---

## Phase 8: Polish & Enhancement

**Goal**: Address deferred items and improvements.

### Tasks

| Task | Description | Needs Clarification |
|------|-------------|---------------------|
| 8.1 | Implement skill hot-reload (if feasible) | Based on Phase 0.4 research |
| 8.2 | Add skill performance metrics dashboard | No |
| 8.3 | Implement skill A/B testing capability | **Yes** - Scope and approach |
| 8.4 | Add agent performance comparison tooling | No |
| 8.5 | Create agent templates for `kubani new` | No |
| 8.6 | Create syndicate templates | No |

### Dependencies
- Phase 7 complete

### Deliverables
- Enhanced tooling
- Better observability
- Templates for new development

---

## Clarification Points Summary

Items where I'll need to ask for more details during implementation:

| Phase | Item | Question |
|-------|------|----------|
| 0 | Skill versioning | Git tags? Semantic version in SKILL.md? Registry metadata? |
| 0 | Hot-reload research | How important is this? Should it block deployment? |
| 1 | A2A spec | Which version of A2A protocol to target? |
| 2 | Sandboxing | Subprocess isolation? Container per skill execution? |
| 3 | Skill scripts | Which existing skills need executable scripts vs declarative-only? |
| 4 | Agent eval | Priority scenarios for each agent's eval suite? |
| 4 | News agents | Is Analyst/Composer the right abstraction, or different roles? |
| 5 | Syndicate eval | What end-to-end scenarios should we test? |
| 6 | SOP location | Shared SOPs directory or integrated into each syndicate? |
| 7 | Rollback | What's the rollback plan if new syndicates have issues? |
| 8 | A/B testing | How sophisticated should skill A/B testing be? |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing functionality | Shadow deployment, parallel running, behavior comparison |
| Skills MCP Server performance | Load testing before cutover |
| Agent behavior differs from federated | Comprehensive eval suites, side-by-side comparison |
| Migration takes too long | Each phase delivers value independently |
| Hot-reload not feasible | Graceful degradation to restart-based reload |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| All existing tests pass | 100% |
| Skill execution latency | < 100ms overhead vs current |
| Agent eval scores | >= current baseline |
| Syndicate behavior | Matches current implementation |
| Zero production incidents during cutover | Yes |

---

## Notes

- Each phase can be merged to main independently
- Phases 1-3 can potentially run in parallel with careful coordination
- Phase 4 and 5 are the most complex and may need subdivision
- Consider creating feature flags for gradual rollout
