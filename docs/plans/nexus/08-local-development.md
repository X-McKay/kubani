# ADR: Nexus Local Development & Iterative Testing

**Date:** 2026-02-23
**Status:** Implemented
**Branch:** `feature/nexus-loop`
**Author:** Nexus implementation

---

## Context

Iterating on the Nexus Agent — especially prompts, activity logic, and mission configuration — was slow and required a full container build, push, and cluster deployment for every change. This created a significant barrier to rapid development and experimentation. We need a way to run the agent locally against live cluster services to test changes in seconds, not minutes.

## Decision

Establish a complete local iterative testing workflow for the Nexus Agent that connects to live cluster services via the existing `*.almckay.io` ingress URLs. This workflow is composed of three parts:

1.  **`.env.nexus-local` Environment Template**: A committed `.env` file that pre-configures all service URLs (LLM, Temporal, MCP servers, databases) to point at their `*.almckay.io` ingress endpoints. Developers copy this to `.env.nexus-local.override` (which is gitignored) and fill in the secrets.

2.  **`scripts/nexus_local_runner.py`**: A command-line test runner that directly invokes the `run_agent_turn` and `run_mission_agent_turn` Temporal activity functions as plain async functions. This bypasses the need for a local Temporal worker and allows for immediate execution of agent logic against the live cluster backend.

3.  **Comprehensive Documentation**: This ADR and an updated `local-development` Claude skill that guides developers through the setup and usage of the new workflow.

## Local Development Workflow

### 1. One-Time Setup

First, a developer copies the environment template and fills in the required secrets.

```bash
# 1. Copy the environment template
cp .env.nexus-local .env.nexus-local.override

# 2. Get secrets from the cluster and edit .env.nexus-local.override
# For NEXUS_DATABASE_URL:
kubectl get secret nexus-config -n nexus -o jsonpath=\'{.data.nexus-database-url}\' | base64 -d

# For REDIS_URL:
kubectl get secret nexus-config -n nexus -o jsonpath=\'{.data.redis-url}\' | base64 -d

# For QDRANT_API_KEY, NEO4J_PASSWORD, etc., get from 1Password or cluster secrets
```

### 2. Validate Setup

The developer runs the `health` and `check` commands to validate their connection and configuration.

```bash
# Check connectivity to all *.almckay.io services
python scripts/nexus_local_runner.py health

# Check that all required .env variables are set correctly
python scripts/nexus_local_runner.py check
```

### 3. Iterative Testing

With the setup validated, the developer can now test changes to prompts, activities, or missions instantly.

#### Testing a Reactive Turn

To test a change to `AGENT_SYSTEM_PROMPT` or the `run_agent_turn` activity:

```bash
# Make a change to the prompt in kubani/nexus/orchestrator/activities.py

# Run a reactive turn directly from the command line
python scripts/nexus_local_runner.py turn "What is the health of the kubernetes cluster?"
```

The runner directly calls the `run_agent_turn` async function, hitting the live `llm.almckay.io` and `mcp-gateway.almckay.io` services, and prints the final response.

#### Testing a Proactive Mission

To test a change to `MISSION_SYSTEM_PROMPT` or the `run_mission_agent_turn` activity:

```bash
# Make a change to the mission prompt in kubani/nexus/orchestrator/activities.py

# Run a proactive mission turn with the nexus-proactive policy
python scripts/nexus_local_runner.py mission \
    --goal "Check all pods in the nexus namespace and report any that are not Running"
    --policy nexus-proactive \
    --max-tool-calls 15
```

This allows for rapid testing of complex, multi-tool missions that interact with live cluster state via the MCP servers.

### 4. Watch Mode for Hot-Reload

For even faster iteration, `watch` mode re-runs a mission automatically whenever a specified file is saved. This is ideal for fine-tuning prompts.

```bash
# This command will re-run the mission every time you save the activities.py file
python scripts/nexus_local_runner.py watch \
    --goal "Summarise the top 3 stories from Hacker News"
    --watch-path kubani/nexus/orchestrator/activities.py
```

The runner automatically reloads the `activities.py` module on each change, so prompt and code modifications are picked up instantly.

## Implementation Details

### `nexus_local_runner.py`

-   **Argument Parsing**: Uses `argparse` to provide a clean CLI interface for the `turn`, `mission`, `health`, `check`, and `watch` commands.
-   **Environment Loading**: `load_env` function loads `.env.nexus-local` and `.env.nexus-local.override` without overwriting existing shell environment variables.
-   **Direct Activity Invocation**: The runner imports the `run_agent_turn` and `run_mission_agent_turn` functions and `await`s them directly. This works because the activities were written as pure async functions that accept and return serializable data.
-   **Temporal Heartbeat Patch**: The `_patch_temporal_activity` function monkey-patches `temporalio.activity.heartbeat` to be a no-op logging call. This allows the activity code to run outside a Temporal worker context without raising a `RuntimeError`.
-   **Module Reloading**: In `watch` mode, `importlib.reload()` is used to reload the `activities.py` module, ensuring that any code or prompt changes are immediately reflected in the next run.

### `.env.nexus-local`

This file centralizes all cluster service URLs, mapping the environment variables used by `kubani/framework/config.py` (e.g., `LLM_API_URL`, `MCP_MEMORY_URL`) to their corresponding `*.almckay.io` ingress endpoints. This decouples the local runner from the production container environment.

## Files Changed

| File | Purpose |
|---|---|
| `scripts/nexus_local_runner.py` | The main test runner script. |
| `.env.nexus-local` | Environment variable template for connecting to cluster services. |
| `tests/test_nexus_local_runner.py` | Unit tests for the runner script itself (16 tests, all passing). |
| `.gitignore` | Added `.env.nexus-local.override` to prevent committing secrets. |
| `docs/plans/nexus/08-local-development.md` | This ADR. |
| `.claude/skills/local-development/SKILL.md` | Updated with the new Nexus workflow. |
