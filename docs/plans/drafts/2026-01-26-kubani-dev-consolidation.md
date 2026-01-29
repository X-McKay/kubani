# kubani Consolidation Plan (Simplified)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate redundant code by using Strands SDK, pydantic-settings, and Protocol-based abstractions. Delete ~2,000+ lines of duplicate implementations.

**Architecture:**
- **Strands SDK** for ALL LLM interactions (delete custom clients)
- **pydantic-settings** for ALL configuration (single source of truth)
- **Protocol + DI** for testability (mockable abstractions)
- **httpx** as the only HTTP client (delete requests)

**Tech Stack:** Python 3.11+, Strands Agent SDK, pydantic-settings, httpx, typer

---

## Executive Summary

### What Gets DELETED

| Package | File(s) | Lines | Reason |
|---------|---------|-------|--------|
| kubani_dev | `llm_client.py` | ~500 | Use Strands SDK |
| kubani_dev | `commands/config.py` internals | ~150 | Use framework config |
| skill-dev-tools | `llm/client.py` | ~150 | Use Strands SDK |
| skill-dev-tools | `config.py` | ~60 | Use framework config |
| Both | `requests` dependency | - | Standardize on httpx |
| Both | `deep_merge()` duplicates | ~20 | pydantic handles this |

**Total: ~900+ lines deleted, plus simplified dependencies**

### What Gets MERGED

`skill-dev-tools` useful components → `kubani/framework/`:
- `evaluation/` → `kubani/framework/evaluation/`
- `trace.py` → `kubani/framework/observability/trace.py`
- `mixins/` → `kubani/framework/mixins/`

### New Abstractions for Testability

```python
# kubani/framework/protocols.py
from typing import Protocol

class LLMProtocol(Protocol):
    """Protocol for LLM interactions - mockable in tests."""
    async def chat(self, messages: list[dict], **kwargs) -> str: ...
    async def run(self, prompt: str) -> str: ...

class SkillExecutorProtocol(Protocol):
    """Protocol for skill execution - mockable in tests."""
    async def execute(self, skill_path: str, context: dict) -> dict: ...
```

---

## Task 1: Add Dependencies and Remove Duplicates

**Files:**
- Modify: `platform/cli/pyproject.toml`
- Reference: `kubani/framework/`

**Step 1: Update CLI dependencies**

```toml
[project]
dependencies = [
    "typer>=0.12.0",
    "watchfiles>=0.21.0",
    "watchdog>=3.0.0",
    "httpx>=0.27.0",        # Keep - standardized HTTP client
    "rich>=13.0.0",
    "pyyaml>=6.0",
    "questionary>=2.0.0",
    # "requests>=2.32.5",   # REMOVE - use httpx
    "temporalio>=1.7.0",
    "kubani",               # ADD - framework dependency
    "strands-agents",       # ADD - for LLM interactions
]
```

**Step 2: Verify import works**

```bash
cd platform/cli && uv pip install -e . && python -c "
from kubani.framework import get_config
from strands import Agent
print('Imports OK')
"
```

**Step 3: Commit**

```bash
git add platform/cli/pyproject.toml
git commit -m "build(cli): add kubani framework and strands-agents dependencies

Remove requests (use httpx). Add kubani and strands-agents for
consolidated LLM and config access.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create Protocol Abstractions for Testability

**Purpose:** Define mockable interfaces before deleting implementations

**Files:**
- Create: `kubani/framework/protocols.py`
- Create: `kubani/framework/testing/mocks.py`

**Step 1: Create Protocol definitions**

```python
# kubani/framework/protocols.py
"""Protocol definitions for dependency injection and testing.

Usage:
    from kubani.framework.protocols import LLMProtocol

    def my_function(llm: LLMProtocol):
        result = await llm.chat([{"role": "user", "content": "Hello"}])
        return result

    # In tests:
    from kubani.framework.testing.mocks import MockLLM
    result = await my_function(MockLLM(responses=["Hi there!"]))
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProtocol(Protocol):
    """Protocol for LLM chat interactions."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Send chat completion request, return content string."""
        ...


@runtime_checkable
class SkillExecutorProtocol(Protocol):
    """Protocol for skill execution."""

    async def execute(
        self,
        skill_path: str,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute a skill and return results."""
        ...


@runtime_checkable
class ConfigProtocol(Protocol):
    """Protocol for configuration access."""

    @property
    def llm_api_url(self) -> str: ...

    @property
    def llm_model(self) -> str: ...

    @property
    def llm_temperature(self) -> float: ...
```

**Step 2: Create mock implementations**

```python
# kubani/framework/testing/mocks.py
"""Mock implementations for testing.

Usage:
    from kubani.framework.testing.mocks import MockLLM, MockSkillExecutor

    @pytest.fixture
    def mock_llm():
        return MockLLM(responses=["Expected response"])

    async def test_my_function(mock_llm):
        result = await my_function(mock_llm)
        assert result == "Expected response"
        assert mock_llm.call_count == 1
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockLLM:
    """Mock LLM for testing."""

    responses: list[str] = field(default_factory=lambda: ["Mock response"])
    call_count: int = 0
    calls: list[dict] = field(default_factory=list)

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Return next response from queue."""
        self.calls.append({
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return response


@dataclass
class MockSkillExecutor:
    """Mock skill executor for testing."""

    results: dict[str, dict] = field(default_factory=dict)
    call_count: int = 0
    calls: list[dict] = field(default_factory=list)

    async def execute(
        self,
        skill_path: str,
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Return mock result for skill."""
        self.calls.append({
            "skill_path": skill_path,
            "context": context,
            "timeout": timeout,
        })
        self.call_count += 1
        return self.results.get(skill_path, {"success": True, "output": "mock"})


@dataclass
class MockConfig:
    """Mock configuration for testing."""

    llm_api_url: str = "http://localhost:8000/v1"
    llm_model: str = "test-model"
    llm_temperature: float = 0.0
```

**Step 3: Update framework __init__.py**

```python
# Add to kubani/framework/__init__.py
from .protocols import LLMProtocol, SkillExecutorProtocol, ConfigProtocol
```

**Step 4: Commit**

```bash
git add kubani/framework/protocols.py kubani/framework/testing/mocks.py kubani/framework/__init__.py
git commit -m "feat(framework): add Protocol abstractions for testability

- LLMProtocol: mockable interface for LLM interactions
- SkillExecutorProtocol: mockable interface for skill execution
- MockLLM, MockSkillExecutor: test fixtures

Enables dependency injection and easy mocking in tests.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create Strands-Based LLM Wrapper

**Purpose:** Single LLM implementation using Strands SDK

**Files:**
- Create: `kubani/framework/llm.py`

**Step 1: Create Strands-based LLM wrapper**

```python
# kubani/framework/llm.py
"""LLM utilities using Strands Agent SDK.

This module provides a simple interface for LLM interactions that:
1. Uses Strands SDK internally (not raw HTTP)
2. Implements LLMProtocol for testability
3. Gets configuration from kubani.framework.config

Usage:
    from kubani.framework.llm import get_llm, FrameworkLLM

    # Simple usage
    llm = get_llm()
    response = await llm.chat([{"role": "user", "content": "Hello"}])

    # With dependency injection
    async def my_function(llm: LLMProtocol):
        return await llm.chat(messages)

    # In production
    await my_function(get_llm())

    # In tests
    await my_function(MockLLM(responses=["test"]))
"""

import logging
from dataclasses import dataclass
from typing import Any

from strands import Agent

from kubani.framework.config import get_config, get_llm_config
from kubani.framework.protocols import LLMProtocol

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    """Response from chat completion."""

    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class FrameworkLLM:
    """
    LLM wrapper using Strands SDK.

    Implements LLMProtocol for dependency injection and testing.
    """

    def __init__(
        self,
        model: str | None = None,
        api_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """
        Initialize LLM wrapper.

        If parameters not provided, uses kubani.framework.config.
        """
        config = get_llm_config()

        self.model = model or config.model
        self.api_url = api_url or config.api_url
        self.temperature = temperature if temperature is not None else config.temperature
        self.max_tokens = max_tokens or config.max_tokens

        self._agent: Agent | None = None

    def _get_agent(self) -> Agent:
        """Get or create Strands Agent."""
        if self._agent is None:
            self._agent = Agent(
                model_id=self.model,
                # Strands handles API URL via environment or model provider
            )
        return self._agent

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Send chat completion and return content.

        Implements LLMProtocol interface.
        """
        agent = self._get_agent()

        # Convert messages to prompt for Strands
        # For simple cases, use the last user message
        user_messages = [m for m in messages if m["role"] == "user"]
        if not user_messages:
            raise ValueError("No user message in messages list")

        prompt = user_messages[-1]["content"]

        # Add system message context if present
        system_messages = [m for m in messages if m["role"] == "system"]
        if system_messages:
            # Strands handles system prompts differently
            agent.system_prompt = system_messages[-1]["content"]

        # Run the agent
        result = await agent.run(prompt)
        return result

    async def chat_with_metadata(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Chat with full response metadata."""
        content = await self.chat(messages, temperature, max_tokens)
        return ChatResponse(
            content=content,
            model=self.model,
            # Token counts would come from Strands internals
        )


# Global instance
_llm: FrameworkLLM | None = None


def get_llm() -> FrameworkLLM:
    """Get global LLM instance configured from framework."""
    global _llm
    if _llm is None:
        _llm = FrameworkLLM()
    return _llm


def reset_llm() -> None:
    """Reset global LLM (useful after config changes)."""
    global _llm
    _llm = None
```

**Step 2: Add tests**

```python
# kubani/framework/tests/test_llm.py
"""Tests for LLM wrapper."""

import pytest
from kubani.framework.llm import FrameworkLLM, get_llm
from kubani.framework.testing.mocks import MockLLM
from kubani.framework.protocols import LLMProtocol


def test_framework_llm_implements_protocol():
    """Verify FrameworkLLM implements LLMProtocol."""
    llm = FrameworkLLM()
    assert isinstance(llm, LLMProtocol)


def test_mock_llm_implements_protocol():
    """Verify MockLLM implements LLMProtocol."""
    mock = MockLLM()
    assert isinstance(mock, LLMProtocol)


@pytest.mark.asyncio
async def test_mock_llm_returns_responses():
    """Test MockLLM returns configured responses."""
    mock = MockLLM(responses=["Hello!", "World!"])

    r1 = await mock.chat([{"role": "user", "content": "Hi"}])
    r2 = await mock.chat([{"role": "user", "content": "Hey"}])

    assert r1 == "Hello!"
    assert r2 == "World!"
    assert mock.call_count == 2


@pytest.mark.asyncio
async def test_mock_llm_records_calls():
    """Test MockLLM records call arguments."""
    mock = MockLLM()
    messages = [{"role": "user", "content": "Test"}]

    await mock.chat(messages, temperature=0.5)

    assert len(mock.calls) == 1
    assert mock.calls[0]["messages"] == messages
    assert mock.calls[0]["temperature"] == 0.5
```

**Step 3: Commit**

```bash
git add kubani/framework/llm.py kubani/framework/tests/test_llm.py
git commit -m "feat(framework): add Strands-based LLM wrapper

- FrameworkLLM: uses Strands SDK, implements LLMProtocol
- get_llm(): factory function with framework config
- Full test coverage with MockLLM

This replaces all custom HTTP-based LLM clients.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: DELETE kubani_dev/llm_client.py

**Purpose:** Remove 500+ lines of redundant code

**Files:**
- Delete: `platform/cli/src/kubani_dev/llm_client.py`
- Modify: All files that import from it

**Step 1: Update skill_drafter.py**

```python
# platform/cli/src/kubani_dev/skill_drafter.py
# Change:
# from kubani_dev.llm_client import LLMClient
# To:
from kubani.framework.llm import get_llm
from kubani.framework.protocols import LLMProtocol

class SkillDrafter:
    def __init__(self, llm: LLMProtocol | None = None):
        self.llm = llm or get_llm()
```

**Step 2: Update skill_evaluator_llm.py**

```python
# platform/cli/src/kubani_dev/skill_evaluator_llm.py
from kubani.framework.llm import get_llm
from kubani.framework.protocols import LLMProtocol

class SkillEvaluatorLLM:
    def __init__(self, llm: LLMProtocol | None = None):
        self.llm = llm or get_llm()
```

**Step 3: Update skill_improver.py**

```python
# platform/cli/src/kubani_dev/skill_improver.py
from kubani.framework.llm import get_llm
from kubani.framework.protocols import LLMProtocol

class SkillImprover:
    def __init__(self, llm: LLMProtocol | None = None):
        self.llm = llm or get_llm()
```

**Step 4: Update commands/skill.py**

Replace all `LLMClient` usage with `get_llm()`.

**Step 5: Delete the file**

```bash
rm platform/cli/src/kubani_dev/llm_client.py
```

**Step 6: Run tests**

```bash
cd platform/cli && pytest -v
```

**Step 7: Commit**

```bash
git add -A
git commit -m "refactor(cli): delete llm_client.py, use framework LLM

- Remove 500+ lines of duplicate LLM client code
- All skill tools now use kubani.framework.llm
- Dependency injection via LLMProtocol for testability
- Update all imports in skill_drafter, skill_evaluator, skill_improver

BREAKING: LLMClient class no longer exists. Use get_llm() instead.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Merge skill-dev-tools Into Framework

**Purpose:** Consolidate useful components, delete duplicates

**Files:**
- Move: `skill-dev-tools/src/skill_dev_tools/evaluation/` → `kubani/framework/evaluation/`
- Move: `skill-dev-tools/src/skill_dev_tools/trace.py` → `kubani/framework/observability/trace.py`
- Delete: `skill-dev-tools/src/skill_dev_tools/config.py`
- Delete: `skill-dev-tools/src/skill_dev_tools/llm/`

**Step 1: Move evaluation module**

```bash
cp -r platform/skill-dev-tools/src/skill_dev_tools/evaluation kubani/framework/
```

**Step 2: Move trace module**

```bash
cp platform/skill-dev-tools/src/skill_dev_tools/trace.py kubani/framework/observability/
```

**Step 3: Update imports in moved files**

Replace:
- `from skill_dev_tools.config import` → `from kubani.framework.config import`
- `from skill_dev_tools.llm import` → `from kubani.framework.llm import`

**Step 4: Delete redundant files from skill-dev-tools**

```bash
rm platform/skill-dev-tools/src/skill_dev_tools/config.py
rm -rf platform/skill-dev-tools/src/skill_dev_tools/llm/
```

**Step 5: Update skill-dev-tools to depend on framework**

```toml
# platform/skill-dev-tools/pyproject.toml
dependencies = [
    "kubani",  # Use framework for config, LLM, etc.
    "structlog>=24.0",
    "httpx>=0.27",
    "python-frontmatter>=1.0",
    "pyyaml>=6.0",
    "duckdb>=0.10.0",
]
```

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor: merge skill-dev-tools components into framework

- Move evaluation/ to kubani/framework/evaluation/
- Move trace.py to kubani/framework/observability/
- Delete duplicate config.py and llm/ from skill-dev-tools
- skill-dev-tools now depends on kubani for shared code

Reduces duplication, single source of truth for LLM and config.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Simplify Config Commands

**Purpose:** Use pydantic-settings directly, delete manual loading

**Files:**
- Modify: `platform/cli/src/kubani_dev/commands/config.py`

**Step 1: Rewrite config.py to use framework**

```python
"""Configuration management commands.

Uses kubani.framework.config (pydantic-settings) for all config access.
"""

import os
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from kubani.framework.config import get_config, reload_config

app = typer.Typer(name="config", help="Configuration management", no_args_is_help=True)
console = Console()


@app.command()
def get(key: str = typer.Argument(..., help="Config key (dot notation)")):
    """Get a configuration value."""
    config = get_config()

    # Navigate nested config using pydantic model
    value = config
    for part in key.split("."):
        if hasattr(value, part):
            value = getattr(value, part)
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            console.print(f"[yellow]Key not found: {key}[/yellow]")
            raise typer.Exit(1)

    # Format output
    if hasattr(value, "model_dump"):
        console.print(yaml.dump(value.model_dump(), default_flow_style=False))
    elif isinstance(value, dict):
        console.print(yaml.dump(value, default_flow_style=False))
    else:
        console.print(str(value))


@app.command()
def show(section: str = typer.Option(None, "--section", "-s")):
    """Show effective configuration."""
    config = get_config()
    data = config.model_dump()

    if section:
        for part in section.split("."):
            data = data.get(part, {})

    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)
    console.print(Panel(
        Syntax(yaml_str, "yaml", theme="monokai"),
        title=f"Config ({config.environment})"
    ))


@app.command()
def validate():
    """Validate configuration."""
    try:
        config = get_config()
        console.print(f"[green]✓ Valid ({config.environment})[/green]")
    except Exception as e:
        console.print(f"[red]✗ Invalid: {e}[/red]")
        raise typer.Exit(1)
```

**Step 2: Commit**

```bash
git add platform/cli/src/kubani_dev/commands/config.py
git commit -m "refactor(cli): simplify config commands with pydantic

- Delete _load_config(), _deep_merge(), _get_nested()
- Use kubani.framework.config.get_config() directly
- Pydantic handles all validation and merging
- ~100 lines removed

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Remove requests, Standardize on httpx

**Purpose:** Single HTTP client library

**Files:**
- Modify: `platform/cli/pyproject.toml`
- Modify: Any files using `import requests`

**Step 1: Find requests usage**

```bash
grep -r "import requests" platform/cli/src/
```

**Step 2: Replace with httpx**

For sync code that used requests:
```python
# Before
import requests
response = requests.post(url, json=data, timeout=30)

# After
import httpx
response = httpx.post(url, json=data, timeout=30)
```

**Step 3: Remove from dependencies**

```toml
# platform/cli/pyproject.toml - remove this line:
# "requests>=2.32.5",
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(cli): standardize on httpx, remove requests

httpx supports both sync and async, one less dependency.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Final Cleanup and Tests

**Step 1: Run full test suite**

```bash
just test
```

**Step 2: Run linting**

```bash
just lint
```

**Step 3: Verify no import errors**

```bash
python -c "from kubani_dev.cli import app; print('CLI OK')"
python -c "from kubani.framework import get_config, get_llm; print('Framework OK')"
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup after consolidation

- All tests passing
- No linting errors
- Imports verified

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

### Code Deleted

| Component | Lines Removed |
|-----------|---------------|
| `kubani_dev/llm_client.py` | ~500 |
| `skill-dev-tools/llm/client.py` | ~150 |
| `skill-dev-tools/config.py` | ~60 |
| `commands/config.py` internals | ~100 |
| Duplicate utilities | ~50 |
| **Total** | **~860 lines** |

### Dependencies Removed

- `requests` (use httpx)
- Duplicate pydantic models

### New Abstractions

| File | Purpose |
|------|---------|
| `framework/protocols.py` | LLMProtocol, SkillExecutorProtocol |
| `framework/testing/mocks.py` | MockLLM, MockSkillExecutor |
| `framework/llm.py` | Strands-based LLM wrapper |

### Architecture After

```
kubani_dev (CLI)
    └── kubani.framework
            ├── config.py         # pydantic-settings (single config)
            ├── llm.py            # Strands SDK wrapper
            ├── protocols.py      # Mockable interfaces
            ├── testing/mocks.py  # Test fixtures
            ├── evaluation/       # (merged from skill-dev-tools)
            └── observability/    # (includes trace.py)
```

### Benefits

1. **~860 lines deleted** - less code to maintain
2. **Single LLM implementation** - Strands SDK
3. **Single config system** - pydantic-settings
4. **Testable via DI** - Protocol + Mock pattern
5. **One HTTP library** - httpx only
6. **Type-safe** - pydantic models everywhere
