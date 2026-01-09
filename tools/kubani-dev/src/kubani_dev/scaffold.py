"""
Agent Scaffolding for Kubani.

Creates new agents from templates with proper structure and configuration.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


BASIC_TEMPLATE = {
    "pyproject.toml": '''[project]
name = "{name}"
version = "0.1.0"
description = "{description}"
requires-python = ">=3.11"
dependencies = [
    "core-agents",
    "strands-agents>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
''',
    "src/{module}/__init__.py": '''"""
{name} Agent

{description}
"""

__version__ = "0.1.0"
''',
    "src/{module}/agent.py": '''"""
{name} Agent Implementation.

This is the main agent module.
"""

import logging
from strands import Agent
from core_agents.factory import AgentFactory, AgentConfig

logger = logging.getLogger(__name__)


def create_agent() -> Agent:
    """Create and configure the {name} agent."""
    factory = AgentFactory()

    config = AgentConfig(
        name="{name}",
        description="{description}",
        system_prompt="""You are the {name} agent.

Your responsibilities:
- TODO: Define agent responsibilities

Always be helpful and precise in your responses.
""",
        tools=[],
    )

    return factory.create_agent(config)


async def run() -> None:
    """Run the agent."""
    agent = create_agent()
    logger.info("{name} agent started")

    # TODO: Implement agent logic


if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
''',
    "tests/__init__.py": "",
    "tests/test_agent.py": '''"""Tests for {name} agent."""

import pytest


def test_agent_creation():
    """Test that agent can be created."""
    from {module}.agent import create_agent

    agent = create_agent()
    assert agent is not None
''',
    "README.md": '''# {name}

{description}

## Installation

```bash
pip install -e .
```

## Usage

```bash
kubani-dev run {name}
```

## Development

```bash
kubani-dev test {name}
```
''',
}


FEDERATED_TEMPLATE = {
    **BASIC_TEMPLATE,
    "src/{module}/federated/__init__.py": '''"""
Federated agent components.

Implements the Sentinel/Healer/Explorer pattern.
"""
''',
    "src/{module}/federated/sentinel.py": '''"""
Sentinel Agent - Watches for events and classifies them.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """An event detected by the sentinel."""
    type: str
    source: str
    data: dict[str, Any]


class SentinelAgent:
    """Watches for events and publishes actionable issues."""

    def __init__(self):
        self._running = False

    async def start(self) -> None:
        """Start watching for events."""
        self._running = True
        logger.info("Sentinel started")

        while self._running:
            # TODO: Implement event watching
            pass

    def stop(self) -> None:
        """Stop the sentinel."""
        self._running = False
''',
    "src/{module}/federated/healer.py": '''"""
Healer Agent - Diagnoses and remediates issues.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class HealerAgent:
    """Diagnoses issues and executes remediation."""

    async def handle_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        """Handle an issue detected by the sentinel."""
        logger.info(f"Handling issue: {{issue}}")

        # TODO: Implement diagnosis and remediation

        return {{"status": "handled", "issue": issue}}
''',
    "src/{module}/federated/explorer.py": '''"""
Explorer Agent - Investigates and gathers context.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ExplorerAgent:
    """Investigates issues and gathers context."""

    async def investigate(self, context: dict[str, Any]) -> dict[str, Any]:
        """Investigate an issue and gather context."""
        logger.info(f"Investigating: {{context}}")

        # TODO: Implement investigation logic

        return {{"findings": [], "context": context}}
''',
}


WORKFLOW_TEMPLATE = {
    **BASIC_TEMPLATE,
    "src/{module}/workflows/__init__.py": '''"""
Hybrid workflow-agent components.

Implements deterministic workflows with agent decision points.
"""
''',
    "src/{module}/workflows/graph.py": '''"""
Workflow Graph Definition.

Uses Strands Graph for hybrid workflow-agent orchestration.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Placeholder for Strands Graph workflow
# When strands-graphs is available, this would use:
# from strands_graphs import Graph, Node, Edge

class WorkflowGraph:
    """Defines the workflow graph for this agent."""

    def __init__(self):
        self.nodes = []
        self.edges = []

    def add_node(self, name: str, handler: callable) -> None:
        """Add a node to the graph."""
        self.nodes.append({{"name": name, "handler": handler}})

    def add_edge(self, source: str, target: str, condition: callable = None) -> None:
        """Add an edge between nodes."""
        self.edges.append({{"source": source, "target": target, "condition": condition}})

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the workflow graph."""
        # TODO: Implement graph execution
        return {{"status": "completed", "input": input_data}}
''',
}


TEMPLATES = {
    "basic": BASIC_TEMPLATE,
    "federated": FEDERATED_TEMPLATE,
    "workflow": WORKFLOW_TEMPLATE,
}


def create_agent(
    name: str,
    template: str,
    target_dir: Path,
    project_root: Path,
    description: str = "",
) -> None:
    """
    Create a new agent from a template.

    Args:
        name: Agent name (e.g., "my-agent")
        template: Template name ("basic", "federated", "workflow")
        target_dir: Directory to create the agent in
        project_root: Root of the kubani project
        description: Agent description
    """
    if template not in TEMPLATES:
        raise ValueError(f"Unknown template: {template}. Available: {list(TEMPLATES.keys())}")

    template_files = TEMPLATES[template]
    module_name = name.replace("-", "_")

    if not description:
        description = f"A Kubani agent for {name}"

    # Create directory structure
    target_dir.mkdir(parents=True, exist_ok=True)

    # Create files from template
    for file_path, content in template_files.items():
        # Replace placeholders in path
        file_path = file_path.format(module=module_name)

        # Replace placeholders in content
        content = content.format(
            name=name,
            module=module_name,
            description=description,
        )

        # Create file
        full_path = target_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

        logger.debug(f"Created: {full_path}")

    logger.info(f"Created agent '{name}' from template '{template}' at {target_dir}")
