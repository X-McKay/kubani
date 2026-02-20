"""Tests for the Nexus skill creation pipeline (OpenClaw-style).

Tests the full flow: Synthesizer → Safety Analysis → Registry → Approval.
Uses mock DB pool and mock LLM to test locally without infrastructure.

Run with:
    python -m pytest tests/nexus/test_skill_pipeline.py -v --no-cov
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kubani.nexus.sandbox.executor import analyze_skill_safety

# Pre-create a mock for kubani.framework.llm so the synthesizer's
# lazy import doesn't fail due to missing 'strands' dependency.
_mock_llm_module = MagicMock()
sys.modules.setdefault("kubani.framework.llm", _mock_llm_module)


# =========================================================================
# Helpers
# =========================================================================


class MockDBPool:
    """Mock asyncpg pool that stores data in memory."""

    def __init__(self) -> None:
        self._skills: dict[int, dict[str, Any]] = {}
        self._approvals: dict[int, dict[str, Any]] = {}
        self._next_skill_id = 1
        self._next_approval_id = 1

    async def fetchval(self, query: str, *args: Any) -> Any:
        if "INSERT INTO skills" in query:
            # Check for conflict (name, version)
            for sid, skill in self._skills.items():
                if skill["name"] == args[0] and skill["version"] == args[1]:
                    # Upsert: update existing
                    skill.update({
                        "oci_url": args[2] or skill.get("oci_url"),
                        "description": args[3],
                        "content_hash": args[8] or skill.get("content_hash"),
                        "status": args[9],
                        "risk_score": args[10],
                        "updated_at": "now",
                    })
                    return sid
            # Insert new
            skill_id = self._next_skill_id
            self._next_skill_id += 1
            self._skills[skill_id] = {
                "id": skill_id,
                "name": args[0],
                "version": args[1],
                "oci_url": args[2],
                "description": args[3],
                "category": args[4],
                "author": args[5],
                "requires_network": args[6],
                "requires_filesystem": args[7],
                "content_hash": args[8],
                "status": args[9],
                "risk_score": args[10],
                "created_at": "now",
                "updated_at": "now",
            }
            return skill_id
        if "INSERT INTO approval_requests" in query:
            req_id = self._next_approval_id
            self._next_approval_id += 1
            self._approvals[req_id] = {
                "id": req_id,
                "request_type": args[0],
                "reference_id": args[1],
                "title": args[2],
                "description": args[3],
                "risk_score": args[4],
                "status": "pending",
            }
            return req_id
        return None

    async def fetchrow(self, query: str, *args: Any) -> Any:
        if "WHERE content_hash" in query:
            for skill in self._skills.values():
                if skill.get("content_hash") == args[0]:
                    return _DictRow(skill)
            return None
        if "WHERE name = $1 AND version = $2" in query:
            for skill in self._skills.values():
                if skill["name"] == args[0] and skill["version"] == args[1]:
                    return _DictRow(skill)
            return None
        if "WHERE name = $1 AND status = 'approved'" in query:
            matches = [
                s for s in self._skills.values()
                if s["name"] == args[0] and s["status"] == "approved"
            ]
            if matches:
                return _DictRow(matches[-1])
            return None
        return None

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        results = list(self._skills.values())
        if "status =" in query and args:
            results = [s for s in results if s["status"] == args[0]]
        return [_DictRow(r) for r in results]

    async def execute(self, query: str, *args: Any) -> str:
        if "UPDATE skills SET status" in query:
            for skill in self._skills.values():
                if skill["id"] == args[-1]:
                    skill["status"] = args[0]
                    break
        return "UPDATE 1"


class _DictRow(dict):
    """Dict that also supports attribute-style access like asyncpg Record."""

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(key)


def make_safe_skill_code() -> str:
    """Generate a safe skill that does simple computation."""
    return '''
import json
import math

def main(inputs: dict) -> dict:
    """Calculate the area of a circle."""
    radius = inputs.get("radius", 1.0)
    area = math.pi * radius ** 2
    return {"area": round(area, 4), "radius": radius}

if __name__ == "__main__":
    import sys
    inputs = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
    result = main(inputs)
    print(json.dumps(result))
'''


def make_dangerous_skill_code() -> str:
    """Generate a skill that uses dangerous patterns."""
    return '''
import subprocess
import os

def main(inputs: dict) -> dict:
    """Run a shell command."""
    cmd = inputs.get("command", "ls")
    result = subprocess.run(cmd, shell=True, capture_output=True)
    return {"stdout": result.stdout.decode()}
'''


def make_medium_risk_skill_code() -> str:
    """Generate a skill with medium-risk patterns (os.remove = 4.0 risk)."""
    return '''
import os

def main(inputs: dict) -> dict:
    """Delete a temporary file."""
    path = inputs.get("path", "/tmp/test.txt")
    if os.path.exists(path):
        os.remove(path)
        return {"deleted": True}
    return {"deleted": False, "error": "File not found"}
'''


# =========================================================================
# Tests: Safety Analysis
# =========================================================================


class TestSafetyAnalysisPipeline:
    """Test the AST-based safety analysis as a gate for skill registration."""

    def test_safe_skill_passes(self):
        result = analyze_skill_safety(make_safe_skill_code())
        assert result["safe"] is True
        assert result["risk_score"] < 3.0

    def test_dangerous_skill_blocked(self):
        result = analyze_skill_safety(make_dangerous_skill_code())
        assert result["safe"] is False
        assert result["risk_score"] >= 8.0
        assert any("subprocess" in f for f in result["findings"])

    def test_medium_risk_detected(self):
        result = analyze_skill_safety(make_medium_risk_skill_code())
        # os module alone isn't blocked but raises risk
        assert result["risk_score"] > 0.0
        assert len(result["findings"]) > 0


# =========================================================================
# Tests: Registry (with mock DB)
# =========================================================================


class TestSkillRegistry:
    """Test the SkillRegistry class with a mock database pool."""

    @pytest.fixture
    def pool(self) -> MockDBPool:
        return MockDBPool()

    @pytest.fixture
    def registry(self, pool: MockDBPool):
        from kubani.nexus.skills.registry import SkillRegistry
        return SkillRegistry(pool)

    @pytest.mark.asyncio
    async def test_register_safe_skill_auto_approves(self, registry, pool):
        """A low-risk skill should be automatically approved."""
        skill_id = await registry.register(
            name="math/circle-area",
            version="0.1.0",
            description="Calculate circle area",
            source_code=make_safe_skill_code(),
        )
        assert skill_id == 1
        skill = pool._skills[skill_id]
        assert skill["status"] == "approved"
        assert skill["risk_score"] < 3.0
        assert skill["content_hash"] is not None
        # No approval request should be created
        assert len(pool._approvals) == 0

    @pytest.mark.asyncio
    async def test_register_medium_risk_creates_approval(self, registry, pool):
        """A medium-risk skill should create an approval request."""
        skill_id = await registry.register(
            name="fs/read-file",
            version="0.1.0",
            description="Read a file",
            source_code=make_medium_risk_skill_code(),
        )
        assert skill_id == 1
        skill = pool._skills[skill_id]
        assert skill["status"] == "pending_approval"
        # An approval request should have been created
        assert len(pool._approvals) == 1
        approval = pool._approvals[1]
        assert approval["reference_id"] == skill_id
        assert "requires approval" in approval["description"]

    @pytest.mark.asyncio
    async def test_duplicate_skill_returns_existing(self, registry, pool):
        """Registering the same source code twice returns the existing ID."""
        code = make_safe_skill_code()
        id1 = await registry.register(
            name="math/circle-area",
            version="0.1.0",
            description="v1",
            source_code=code,
        )
        id2 = await registry.register(
            name="math/circle-area",
            version="0.2.0",
            description="v2",
            source_code=code,  # Same code
        )
        assert id1 == id2  # Dedup by content hash

    @pytest.mark.asyncio
    async def test_approve_skill(self, registry, pool):
        """Approving a skill updates its status."""
        skill_id = await registry.register(
            name="fs/read-file",
            version="0.1.0",
            description="Read a file",
            source_code=make_medium_risk_skill_code(),
        )
        assert pool._skills[skill_id]["status"] == "pending_approval"

        await registry.approve(skill_id, approved_by="admin")
        assert pool._skills[skill_id]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_reject_skill(self, registry, pool):
        """Rejecting a skill updates its status."""
        skill_id = await registry.register(
            name="fs/read-file",
            version="0.1.0",
            description="Read a file",
            source_code=make_medium_risk_skill_code(),
        )
        await registry.reject(skill_id, reason="Too risky", rejected_by="admin")
        assert pool._skills[skill_id]["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_get_approved_skill(self, registry, pool):
        """Can retrieve an approved skill by name."""
        await registry.register(
            name="math/circle-area",
            version="0.1.0",
            description="Calculate circle area",
            source_code=make_safe_skill_code(),
        )
        skill = await registry.get("math/circle-area")
        assert skill is not None
        assert skill["name"] == "math/circle-area"
        assert skill["status"] == "approved"

    @pytest.mark.asyncio
    async def test_list_approved_skills(self, registry, pool):
        """List only approved skills."""
        await registry.register(
            name="math/circle-area",
            version="0.1.0",
            description="Safe skill",
            source_code=make_safe_skill_code(),
        )
        await registry.register(
            name="fs/read-file",
            version="0.1.0",
            description="Risky skill",
            source_code=make_medium_risk_skill_code(),
        )
        approved = await registry.list_approved()
        assert len(approved) == 1
        assert approved[0]["name"] == "math/circle-area"

    @pytest.mark.asyncio
    async def test_content_hash_computed(self, registry, pool):
        """Content hash is correctly computed and stored."""
        code = make_safe_skill_code()
        expected_hash = hashlib.sha256(code.encode()).hexdigest()
        skill_id = await registry.register(
            name="math/circle-area",
            version="0.1.0",
            description="Test",
            source_code=code,
        )
        assert pool._skills[skill_id]["content_hash"] == expected_hash


# =========================================================================
# Tests: Synthesizer (with mock LLM)
# =========================================================================


class TestSkillSynthesizer:
    """Test the SkillSynthesizer with a mock LLM and mock DB."""

    @pytest.fixture
    def pool(self) -> MockDBPool:
        return MockDBPool()

    @pytest.fixture
    def registry(self, pool: MockDBPool):
        from kubani.nexus.skills.registry import SkillRegistry
        return SkillRegistry(pool)

    @pytest.fixture
    def synthesizer(self, registry):
        from kubani.nexus.skills.synthesizer import SkillSynthesizer
        return SkillSynthesizer(registry)

    def _mock_llm_response(self, name: str, code: str) -> MagicMock:
        """Create a mock LLM response with the given skill data."""
        response = MagicMock()
        response.content = json.dumps({
            "name": name,
            "version": "0.1.0",
            "description": f"Auto-generated skill: {name}",
            "code": code,
        })
        return response

    @pytest.mark.asyncio
    async def test_synthesize_safe_skill(self, synthesizer, pool):
        """Synthesizer creates and auto-approves a safe skill."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value=self._mock_llm_response(
                "math/circle-area",
                make_safe_skill_code(),
            )
        )

        with patch.dict(sys.modules, {"kubani.framework.llm": MagicMock(get_llm=MagicMock(return_value=mock_llm))}):
            result = await synthesizer.create_skill(
                task_description="Calculate the area of a circle given a radius",
            )

        assert result["success"] is True
        assert result["skill_name"] == "math/circle-area"
        assert result["version"] == "0.1.0"
        assert result["status"] == "approved"
        assert result["skill_id"] == 1
        # Verify it was stored in DB
        assert pool._skills[1]["name"] == "math/circle-area"
        assert pool._skills[1]["status"] == "approved"

    @pytest.mark.asyncio
    async def test_synthesize_risky_skill_creates_approval(self, synthesizer, pool):
        """Synthesizer creates an approval request for medium-risk skills."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value=self._mock_llm_response(
                "fs/read-file",
                make_medium_risk_skill_code(),
            )
        )

        with patch.dict(sys.modules, {"kubani.framework.llm": MagicMock(get_llm=MagicMock(return_value=mock_llm))}):
            result = await synthesizer.create_skill(
                task_description="Read a file from the filesystem",
            )

        assert result["success"] is True
        assert result["status"] == "pending_approval"
        assert len(pool._approvals) == 1

    @pytest.mark.asyncio
    async def test_synthesize_retries_on_bad_json(self, synthesizer, pool):
        """Synthesizer retries when LLM returns invalid JSON."""
        bad_response = MagicMock()
        bad_response.content = "This is not JSON"

        good_response = self._mock_llm_response(
            "math/add", make_safe_skill_code()
        )

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=[bad_response, good_response])

        with patch.dict(sys.modules, {"kubani.framework.llm": MagicMock(get_llm=MagicMock(return_value=mock_llm))}):
            result = await synthesizer.create_skill(
                task_description="Add two numbers",
                max_attempts=3,
            )

        assert result["success"] is True
        assert mock_llm.chat.call_count == 2  # Failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_synthesize_fails_after_max_attempts(self, synthesizer, pool):
        """Synthesizer fails gracefully after exhausting retries."""
        bad_response = MagicMock()
        bad_response.content = "Not valid JSON at all"

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=bad_response)

        with patch.dict(sys.modules, {"kubani.framework.llm": MagicMock(get_llm=MagicMock(return_value=mock_llm))}):
            result = await synthesizer.create_skill(
                task_description="Impossible task",
                max_attempts=2,
            )

        assert result["success"] is False
        assert "Failed to synthesize" in result["error"]
        assert mock_llm.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_synthesize_handles_markdown_wrapped_json(self, synthesizer, pool):
        """Synthesizer handles LLM responses wrapped in markdown code blocks."""
        response = MagicMock()
        response.content = '```json\n' + json.dumps({
            "name": "text/uppercase",
            "version": "0.1.0",
            "description": "Convert text to uppercase",
            "code": make_safe_skill_code(),
        }) + '\n```'

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=response)

        with patch.dict(sys.modules, {"kubani.framework.llm": MagicMock(get_llm=MagicMock(return_value=mock_llm))}):
            result = await synthesizer.create_skill(
                task_description="Convert text to uppercase",
            )

        assert result["success"] is True


# =========================================================================
# Tests: Full Pipeline (Sandbox Execution)
# =========================================================================


class TestFullPipeline:
    """Test the complete flow: synthesize → register → execute."""

    @pytest.fixture
    def pool(self) -> MockDBPool:
        return MockDBPool()

    @pytest.fixture
    def registry(self, pool: MockDBPool):
        from kubani.nexus.skills.registry import SkillRegistry
        return SkillRegistry(pool)

    @pytest.mark.asyncio
    async def test_register_then_execute(self, registry):
        """Register a skill then execute it in the sandbox."""
        from kubani.nexus.sandbox.executor import execute_skill_in_sandbox

        code = make_safe_skill_code()

        # Register
        skill_id = await registry.register(
            name="math/circle-area",
            version="0.1.0",
            description="Calculate circle area",
            source_code=code,
        )
        assert skill_id == 1

        # Execute directly (pass code since we don't have a real DB for lookup)
        result = await execute_skill_in_sandbox(
            skill_name="math/circle-area",
            inputs={"radius": 5.0},
            skill_content=code,
            timeout_seconds=10,
        )

        assert result.success is True
        output = json.loads(result.output)
        assert abs(output["area"] - 78.5398) < 0.001
        assert output["radius"] == 5.0

    @pytest.mark.asyncio
    async def test_dangerous_skill_blocked_at_registration(self, registry, pool):
        """A dangerous skill still gets registered but the sandbox blocks execution."""
        from kubani.nexus.sandbox.executor import execute_skill_in_sandbox

        code = make_dangerous_skill_code()

        # Safety analysis runs during registration
        skill_id = await registry.register(
            name="system/shell-exec",
            version="0.1.0",
            description="Execute shell commands",
            source_code=code,
        )

        # It's registered but pending approval due to high risk
        assert pool._skills[skill_id]["status"] == "pending_approval"
        assert pool._skills[skill_id]["risk_score"] >= 8.0

        # Even if we try to execute it, the sandbox blocks it
        result = await execute_skill_in_sandbox(
            skill_name="system/shell-exec",
            inputs={"command": "whoami"},
            skill_content=code,
            timeout_seconds=10,
        )
        assert result.success is False
        assert "blocked by static analysis" in result.error.lower()
