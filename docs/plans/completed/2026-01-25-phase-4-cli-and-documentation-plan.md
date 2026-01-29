# Detailed Implementation Plan: Phase 4 - CLI & Documentation

**Date:** 2026-01-25
**Status:** Completed
**Author:** Manus AI

## 1. Objective

This document provides a prescriptive guide for the final phase of the workflow refactor: exposing the new `agent_auto` workflow to users via the `kubani` CLI and creating comprehensive documentation for the new architecture. This phase ensures the powerful new capabilities are usable, understandable, and maintainable.

## 2. Epic 7: Update CLI

**Goal:** To provide a seamless user experience for developers by integrating the new `AgentAutoWorkflow` with the `kubani` command-line interface.

---

### **Task 7.1: Modify `agent draft` Command**

**Action:** Refactor the `kubani agent draft` command to act as the primary entry point for starting the `AgentAutoWorkflow`.

-   **File:** `platform/cli/src/kubani_dev/commands/agent.py`
-   **Purpose:** To connect the user-facing command to the backend Temporal workflow, allowing developers to trigger agent creation from their terminal.

**Implementation:**

```python
# platform/cli/src/kubani_dev/commands/agent.py

import typer
from temporalio.client import Client
from kubani.workflows.agent_auto.workflow import AgentAutoWorkflow
from kubani.workflows.agent_auto.domain.models import AgentAutoInput

app = typer.Typer()

@app.command("draft")
def draft_agent(
    description: str = typer.Option(..., "--description", "-d", help="A high-level description of the agent to create."),
    agent_name: str = typer.Option(..., "--name", "-n", help="The name of the agent to create."),
    target_accuracy: float = typer.Option(0.9, help="The target evaluation accuracy to reach."),
    max_iterations: int = typer.Option(10, help="The maximum number of improvement iterations."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Run without asking for user confirmation."),
):
    """Drafts a new agent by running the automated agent creation workflow."""
    typer.echo(f"🚀 Starting agent creation workflow for [1m{agent_name}[0m...")

    # In a real app, the client would be created from a shared context
    client = await Client.connect("localhost:7233")

    workflow_input = AgentAutoInput(
        agent_name=agent_name,
        description=description,
        target_accuracy=target_accuracy,
        max_iterations=max_iterations,
        # ... other options ...
    )

    handle = await client.start_workflow(
        AgentAutoWorkflow.run,
        args=[workflow_input],
        id=f"agent-auto-{agent_name}",
        task_queue="agent-auto-task-queue",
    )

    typer.echo(f"Workflow started with ID: {handle.id}")
    typer.echo("You can monitor its progress using the Temporal UI or `kubani agent status`.")

    if not non_interactive:
        # This would be a more complex implementation to stream logs/status
        typer.echo("Waiting for workflow to complete... (This is a simplified example)")
        result = await handle.result()
        typer.echo(f"Workflow finished with status: {result["status"]}")

```

**Verification:** Running `kubani agent draft --name my-agent --description 
"An agent to monitor kubernetes pods"` should successfully start a new `AgentAutoWorkflow` instance in Temporal.

---

### **Task 7.2: Implement `agent status` and `agent interact` Commands**

**Action:** Create new CLI commands to query the status of a running workflow and send signals to it (e.g., to pause, resume, or cancel).

-   **File:** `platform/cli/src/kubani_dev/commands/agent.py`
-   **Purpose:** To provide users with the means to observe and control the agent creation process after it has been started.

**Implementation:**

```python
# platform/cli/src/kubani_dev/commands/agent.py

# ... (add to the existing file)

@app.command("status")
def agent_status(agent_name: str = typer.Argument(..., help="The name of the agent.")):
    """Get the status of a running agent creation workflow."""
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle(f"agent-auto-{agent_name}")
    
    try:
        description = await handle.describe()
        typer.echo(f"Workflow ID: {description.id}")
        typer.echo(f"Status: {description.status.name}")
        
        # Use a query to get the detailed internal state
        state_result = await handle.query("get_state")
        typer.echo("Current State:")
        # Pretty print the state dictionary
        import json
        typer.echo(json.dumps(state_result, indent=2))

    except Exception as e:
        typer.echo(f"Error fetching workflow status: {e}", err=True)

@app.command("cancel")
def cancel_agent_workflow(agent_name: str = typer.Argument(..., help="The name of the agent.")):
    """Cancel a running agent creation workflow."""
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle(f"agent-auto-{agent_name}")
    await handle.cancel()
    typer.echo(f"Cancel request sent to workflow for agent [1m{agent_name}[0m.")

```

**Verification:** Running `kubani agent status my-agent` should query the running workflow and display its current state. Running `kubani agent cancel my-agent` should gracefully terminate the workflow.

## 3. Epic 8: Update Documentation

**Goal:** To create clear, comprehensive documentation that enables developers to understand, use, and extend the new functional workflow architecture.

---

### **Task 8.1: Create Architecture Documentation**

**Action:** Write a new, detailed document explaining the layered architecture, the separation of concerns, and the testing strategy.

-   **File:** `docs/architecture/functional-workflow-design.md`
-   **Purpose:** To serve as the canonical reference for the new design pattern, ensuring future development adheres to these principles.

**Content Outline:**

1.  **Overview:** High-level goal of the architecture (testability, maintainability).
2.  **The Four Layers:**
    -   Domain Layer (Pure Functions, Models)
    -   Service Layer (Dependency Injection, Composition)
    -   Activity Layer (Thin Wrappers, Instantiation)
    -   Workflow Layer (Orchestration, State Management)
3.  **Data Flow:** A diagram showing how a request flows from the workflow down to the domain layer and back up.
4.  **Testing Strategy:**
    -   Unit Testing the Domain Layer (no mocks).
    -   Integration Testing the Service Layer (with mocks).
    -   End-to-End Testing the Workflow Layer (Temporal test harness).
5.  **Example:** Walk through the refactoring of a single activity (`detect_skill_overlap`) to illustrate the pattern in practice.

**Verification:** The document must be clear, well-structured, and provide enough detail for a new developer to understand the architecture.

---

### **Task 8.2: Update Developer Guides**

**Action:** Update the existing guides for developing agents and skills to reflect the new automated workflows.

-   **Files:** `docs/kubani/agents/development.md`, `docs/kubani/skills/development.md`
-   **Purpose:** To ensure developers are using the new, streamlined process instead of manual methods.

**Content Changes:**

-   The primary method for creating a new agent should now be `kubani agent draft`.
-   The manual steps should be moved to an "Advanced" or "Manual Creation" section.
-   The skill development guide should be updated to mention that skills can be auto-generated by the `agent_auto` workflow.

**Verification:** The developer guides must prioritize the new automated workflow as the primary path for creation.

---

### **Task 8.3: Create New CLI Tutorial**

**Action:** Write a new, hands-on tutorial for using the `kubani agent` commands.

-   **File:** `docs/platform/cli/guides/creating-agents-automatically.md`
-   **Purpose:** To provide a step-by-step guide that walks a developer through creating their first agent using the new automated process.

**Content Outline:**

1.  **Introduction:** What the `agent_auto` workflow does.
2.  **Step 1: Drafting the Agent:**
    -   Run `kubani agent draft --name ... --description ...`
    -   Explain the output and what's happening in the background (workflow started).
3.  **Step 2: Monitoring the Process:**
    -   Use `kubani agent status ...` to check the progress.
    -   Explain how to look at the Temporal UI for more detail.
4.  **Step 3: The Eval-Improve Loop:**
    -   Explain how the workflow is automatically testing and refining the agent.
5.  **Step 4: The Final Result:**
    -   Show the final directory structure of the published agent.
6.  **Next Steps:** How to further customize or manually improve the generated agent.

**Verification:** A developer following the tutorial must be able to successfully create a new agent from scratch using only the CLI commands.
