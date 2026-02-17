
># Nexus Implementation Plan: 01 - Temporal-Native Orchestrator

**Author:** Manus AI
**Date:** February 6, 2026

## 1. Overview

This document provides a detailed implementation plan for the **Nexus Syndicate**, the core orchestrator of the Kubani Nexus agent. As decided in the architectural review, this component will be implemented as a long-running, durable Temporal workflow.

This orchestrator is the "brain" of the agent. It is responsible for maintaining the conversational state, managing the agent's lifecycle, planning tasks, and delegating execution to specialized agents and skills. Its implementation as a Temporal workflow ensures that the agent is "always-on," resilient to failures, and fully observable.

## 2. Core Workflow: `NexusSyndicateWorkflow`

The central component is the `NexusSyndicateWorkflow`. This workflow will be designed to run indefinitely until explicitly terminated.

### 2.1. Workflow Interface

-   **Name:** `NexusSyndicateWorkflow`
-   **Task Queue:** `nexus-syndicate`
-   **Start Arguments:**
    -   `user_id: str`: The primary user this agent instance is associated with.
    -   `conversation_id: str`: A unique ID for the initial conversation session.
-   **Signals:**
    -   `receive_message(message: UserMessage)`: Sends a new user message to the workflow.
    -   `update_goal(goal: str)`: Allows the user to change the agent's high-level goal.
-   **Queries:**
    -   `get_state() -> NexusWorkflowState`: Returns the current state of the workflow, including conversation history and current status.
    -   `get_status() -> str`: Returns a simple human-readable status (e.g., "Idle," "Planning," "Executing Skill: web_search").

### 2.2. Data Models

We will use Pydantic models for all data structures to ensure type safety and clear contracts.

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal

class UserMessage(BaseModel):
    """A message received from a user via the Conversational Gateway."""
    source: Literal["discord", "kubani-ui"]
    user_id: str
    conversation_id: str
    text: str
    timestamp: str

class AgentMessage(BaseModel):
    """A message sent from the agent back to the user."""
    conversation_id: str
    text: str
    timestamp: str

class NexusWorkflowState(BaseModel):
    """The complete, queryable state of the Nexus workflow."""
    user_id: str
    current_goal: str | None = None
    status: str = "Idle"
    conversation_history: List[UserMessage | AgentMessage] = Field(default_factory=list)
    current_plan: List[str] = Field(default_factory=list)
    last_error: str | None = None
```

## 3. Workflow Logic

The workflow will operate as a continuous loop, waiting for signals and processing them.

### 3.1. Main Loop

The core logic will be within a `workflow.run` method:

```python
@workflow.run
async def run(self, user_id: str, conversation_id: str) -> None:
    self.state = NexusWorkflowState(user_id=user_id)

    while True:
        # Wait for a new message to arrive. This will block until a signal is received.
        await workflow.wait_condition(
            lambda: self.incoming_messages.qsize() > 0
        )

        message = await self.incoming_messages.get()
        self.state.status = "Processing"
        self.state.conversation_history.append(message)

        # Defer the core logic to a child workflow for better isolation and observability
        try:
            response_text = await workflow.execute_child_workflow(
                "ProcessMessageWorkflow",
                args=[self.state, message],
                id=f"process-{message.timestamp}"
            )
            response = AgentMessage(
                conversation_id=conversation_id,
                text=response_text,
                timestamp=datetime.now().isoformat()
            )
            self.state.conversation_history.append(response)

            # Signal the Conversational Gateway to send the response
            await workflow.execute_activity(
                "send_agent_response_activity",
                args=[response],
                start_to_close_timeout=timedelta(seconds=10)
            )

        except Exception as e:
            self.state.last_error = str(e)
            # Handle error, potentially send an error message to the user

        self.state.status = "Idle"
```

### 3.2. Child Workflow: `ProcessMessageWorkflow`

To keep the main loop clean, the complex logic of planning and execution will be in a separate child workflow. This allows each message processing cycle to be observed and debugged independently in the Temporal UI.

-   **Name:** `ProcessMessageWorkflow`
-   **Task Queue:** `nexus-syndicate`
-   **Arguments:**
    -   `current_state: NexusWorkflowState`
    -   `message: UserMessage`
-   **Returns:** `str` (the agent's response)

**Logic:**

1.  **Intent Analysis:** Use an LLM (via an activity) to classify the user's intent (e.g., question, command, chit-chat).
2.  **Planning:** If the intent requires action, execute a `PlanningActivity` to break the request down into a series of steps (skills to be executed).
3.  **Execution:** Iterate through the plan, executing each step using a generic `ExecuteSkillActivity`.
4.  **Response Generation:** Once the plan is complete, use an `LLMActivity` to synthesize the results into a natural language response.

### 3.3. Core Activities

The workflow will rely on a set of well-defined activities:

-   `send_agent_response_activity`: Publishes the agent's response to a Redis Pub/Sub channel that the Conversational Gateway is listening on.
-   `classify_intent_activity`: Calls the LLM to determine the user's intent.
-   `planning_activity`: Calls the LLM with the user's request and available skills to generate a step-by-step plan.
-   `execute_skill_activity`: The most critical activity. It is responsible for:
    1.  Looking up the skill's OCI artifact URL in the `Skill Registry`.
    2.  Provisioning an ephemeral, secure sandbox (as per Decision #3).
    3.  Running the skill within the sandbox.
    4.  Capturing the output and returning it to the workflow.
-   `summarize_results_activity`: Calls the LLM to generate the final user-facing response.

## 4. Testing Strategy

-   **Unit Tests:** Each activity will be unit-tested in isolation, with its dependencies (like LLM clients or database clients) mocked.
-   **Workflow Replay:** We will use Temporal's workflow replay testing feature to ensure that any changes to the workflow code are deterministic and do not break existing executions. A suite of workflow histories will be maintained for this purpose.
-   **Integration Tests:** An end-to-end test will be created that starts the `NexusSyndicateWorkflow`, sends it a message via a test utility that simulates the Conversational Gateway, and verifies that a response is generated and sent correctly.
