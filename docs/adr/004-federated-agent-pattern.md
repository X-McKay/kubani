# ADR-004: Federated Agent Pattern

## Status
Accepted

## Context

Complex AI agent tasks often require multiple distinct capabilities: investigation, decision-making, execution, and monitoring. A monolithic agent that handles all these responsibilities becomes difficult to test, maintain, and evolve. Different aspects of a task may require different prompts, tools, and evaluation criteria.

We needed an architecture that allows specialization while maintaining coordination between components. The pattern should support independent development and testing of each capability while enabling seamless collaboration at runtime.

## Decision

We adopted a federated agent pattern where complex agents are composed of specialized sub-agents, each responsible for a specific aspect of the overall task. The main agent orchestrates these sub-agents through Temporal workflows, ensuring durability and visibility into the execution flow.

A typical federated agent structure includes an Explorer agent for investigation and information gathering, an Executor agent for taking actions based on decisions, and a Monitor agent for observing outcomes and triggering learning. Each sub-agent has its own system prompt, tool set, and evaluation criteria optimized for its specific responsibility.

The k8s-monitor agent demonstrates this pattern with three sub-agents. The Explorer investigates pod failures by gathering logs, events, and metrics. The Executor applies remediations such as scaling, restarting, or configuration changes. The Monitor tracks the outcome and logs results for the learning system.

Communication between sub-agents happens through Temporal workflow state and activities. The workflow orchestrates the sequence of sub-agent invocations and handles failures, retries, and timeouts at each step.

## Consequences

### Positive

Each sub-agent can be developed, tested, and optimized independently. The Explorer can be improved without affecting the Executor, and vice versa. This separation enables parallel development and reduces the blast radius of changes.

Testing becomes more focused because each sub-agent has a clear responsibility and interface. Unit tests can verify sub-agent behavior in isolation, while integration tests verify the coordination through workflows.

The pattern naturally supports different tool sets for different phases. Investigation tools are available to the Explorer, while execution tools are restricted to the Executor. This principle of least privilege reduces the risk of unintended actions.

Temporal workflows provide visibility into the execution flow, making debugging easier. Each sub-agent invocation is recorded with inputs, outputs, and timing, enabling detailed analysis of agent behavior.

### Negative

The federated pattern adds complexity compared to a single monolithic agent. Developers must understand the coordination model and workflow patterns in addition to individual agent behavior.

Communication overhead between sub-agents through Temporal adds latency. For simple tasks, a monolithic agent would be faster. The pattern is most beneficial for complex, multi-step tasks where the benefits of specialization outweigh the coordination cost.

State management between sub-agents requires careful design. Information gathered by the Explorer must be passed to the Executor in a structured format, and the workflow must handle partial failures gracefully.

### Neutral

The pattern requires Temporal for orchestration, which is already a core dependency of Kubani. Teams familiar with Temporal will find the pattern natural, while those new to Temporal will need to learn its concepts alongside the agent patterns.

## Alternatives Considered

### Monolithic Agent

A single agent handling all responsibilities would be simpler to implement initially but would become unwieldy as capabilities grow. Testing would require mocking all tools, and changes to one capability could affect others unexpectedly.

### Microservices Architecture

Separate services for each capability would provide strong isolation but would add significant operational overhead. The federated pattern achieves similar benefits within a single deployable unit, reducing complexity.

### Pipeline Architecture

A fixed pipeline of stages would be simpler than dynamic orchestration but would not handle the iterative nature of agent tasks. Agents often need to loop back to investigation after execution reveals new information.

### Event-Driven Architecture

Event-based communication between agents would provide loose coupling but would make the execution flow harder to follow and debug. Temporal workflows provide a clear execution history that events alone cannot match.
