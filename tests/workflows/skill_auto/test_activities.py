"""Tests for skill auto workflow activities."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = MagicMock()
    client.chat = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_detect_overlap_finds_similar_skill(mock_llm_client):
    """detect_skill_overlap should identify overlapping skills."""
    from kubani.workflows.skill_auto.activities import detect_skill_overlap
    from kubani.workflows.skill_auto.models import OverlapResult

    # Mock LLM response indicating overlap
    mock_llm_client.chat.return_value = {
        "content": """```json
{
    "has_overlap": true,
    "confidence": 0.82,
    "overlapping_skills": ["memory-troubleshooting"],
    "reasoning": "Both skills diagnose memory-related pod failures",
    "recommendation": "merge"
}
```""",
        "tokens": {"prompt": 100, "completion": 50, "total": 150},
    }

    result = await detect_skill_overlap(
        description="A skill that helps diagnose OOMKilled pods",
        existing_skills=[
            {"name": "memory-troubleshooting", "description": "Diagnose memory issues in pods"},
            {"name": "cpu-throttling", "description": "Diagnose CPU throttling issues"},
        ],
        llm_client=mock_llm_client,
    )

    assert isinstance(result, OverlapResult)
    assert result.has_overlap is True
    assert result.confidence > 0.8
    assert "memory-troubleshooting" in result.overlapping_skills


@pytest.mark.asyncio
async def test_detect_overlap_no_overlap(mock_llm_client):
    """detect_skill_overlap should return no overlap when skills are distinct."""
    from kubani.workflows.skill_auto.activities import detect_skill_overlap

    mock_llm_client.chat.return_value = {
        "content": """```json
{
    "has_overlap": false,
    "confidence": 0.95,
    "overlapping_skills": [],
    "reasoning": "This skill addresses a unique use case",
    "recommendation": "proceed"
}
```""",
        "tokens": {"prompt": 100, "completion": 50, "total": 150},
    }

    result = await detect_skill_overlap(
        description="A skill that manages Kubernetes RBAC policies",
        existing_skills=[
            {"name": "memory-troubleshooting", "description": "Diagnose memory issues"},
        ],
        llm_client=mock_llm_client,
    )

    assert result.has_overlap is False
    assert result.recommendation == "proceed"


@pytest.mark.asyncio
async def test_load_existing_skills_from_directory(tmp_path):
    """load_existing_skills should read skills from the skills directory."""
    from kubani.workflows.skill_auto.activities import load_existing_skills

    # Create test skill structure
    skill_dir = tmp_path / "skills" / "general" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill for testing
triggers:
  - test_trigger
---

# Test Skill

This is a test skill.
""")

    skills = await load_existing_skills(tmp_path / "skills")

    assert len(skills) == 1
    assert skills[0]["name"] == "test-skill"
    assert "test skill" in skills[0]["description"].lower()


@pytest.mark.asyncio
async def test_load_existing_skills_excludes_development(tmp_path):
    """load_existing_skills should exclude _development skills by default."""
    from kubani.workflows.skill_auto.activities import load_existing_skills

    # Production skill
    prod_dir = tmp_path / "skills" / "general" / "prod-skill"
    prod_dir.mkdir(parents=True)
    (prod_dir / "SKILL.md").write_text("""---
name: prod-skill
description: Production skill
---
# Prod Skill
""")

    # Development skill
    dev_dir = tmp_path / "skills" / "_development" / "dev-skill"
    dev_dir.mkdir(parents=True)
    (dev_dir / "SKILL.md").write_text("""---
name: dev-skill
description: Development skill
---
# Dev Skill
""")

    skills = await load_existing_skills(tmp_path / "skills", include_development=False)

    assert len(skills) == 1
    assert skills[0]["name"] == "prod-skill"


@pytest.mark.asyncio
async def test_infer_skill_structure_generates_spec(mock_llm_client):
    """infer_skill_structure should generate skill spec from description."""
    from kubani.workflows.skill_auto.activities import infer_skill_structure

    mock_llm_client.chat.return_value = {
        "content": """```json
{
    "name": "oom-diagnostics",
    "description": "Diagnose OOMKilled pod failures",
    "inputs": {
        "pod_name": {"type": "string", "description": "Name of the pod", "required": true},
        "namespace": {"type": "string", "description": "Kubernetes namespace", "required": true}
    },
    "outputs": {
        "diagnosis": {"type": "string", "description": "Root cause analysis"},
        "recommendations": {"type": "array", "description": "Suggested fixes"}
    },
    "steps": [
        "Get pod events and logs",
        "Check container memory limits",
        "Analyze memory usage patterns",
        "Provide recommendations"
    ],
    "examples": [
        {
            "name": "Basic OOM diagnosis",
            "description": "Diagnose a pod killed due to OOM",
            "input": {"pod_name": "api-server-1", "namespace": "production"},
            "expected_output": {"diagnosis": "Container exceeded memory limit"}
        }
    ]
}
```""",
        "tokens": {"prompt": 200, "completion": 300, "total": 500},
    }

    spec = await infer_skill_structure(
        description="A skill that helps diagnose OOMKilled pods",
        llm_client=mock_llm_client,
    )

    assert spec["name"] == "oom-diagnostics"
    assert "pod_name" in spec["inputs"]
    assert len(spec["steps"]) > 0
    assert len(spec["examples"]) > 0


@pytest.mark.asyncio
async def test_generate_test_cases_from_spec(mock_llm_client):
    """generate_test_cases should create test cases with assertions."""
    from kubani.workflows.skill_auto.activities import generate_test_cases

    mock_llm_client.chat.return_value = {
        "content": """```yaml
test_cases:
  - name: basic_oom_diagnosis
    description: Diagnose a pod killed due to OOM
    inputs:
      pod_name: api-server-1
      namespace: production
    expected:
      diagnosis: Contains analysis of memory issue
    assertions:
      - type: exists
        field: diagnosis
        description: Should provide a diagnosis
      - type: not_empty
        field: recommendations
        description: Should provide recommendations
```""",
        "tokens": {"prompt": 200, "completion": 200, "total": 400},
    }

    spec = {
        "name": "oom-diagnostics",
        "description": "Diagnose OOMKilled pods",
        "inputs": {"pod_name": {"type": "string"}, "namespace": {"type": "string"}},
        "examples": [{"name": "basic", "input": {"pod_name": "test"}}],
    }

    test_cases_yaml = await generate_test_cases(spec, mock_llm_client)

    assert "test_cases:" in test_cases_yaml
    assert "basic_oom_diagnosis" in test_cases_yaml
    assert "assertions:" in test_cases_yaml


@pytest.mark.asyncio
async def test_write_skill_files_creates_directory_structure(tmp_path):
    """write_skill_files should create skill directory with all files."""
    from pathlib import Path

    from kubani.workflows.skill_auto.activities import write_skill_files

    spec = {
        "name": "test-skill",
        "description": "A test skill",
        "inputs": {"query": {"type": "string", "required": True}},
        "outputs": {"result": {"type": "string"}},
        "steps": ["Step 1", "Step 2"],
    }
    test_cases = "test_cases:\n  - name: test1\n    inputs: {}"

    skill_path = await write_skill_files(
        spec=spec,
        test_cases=test_cases,
        output_dir=tmp_path / "skills" / "_development",
    )

    assert Path(skill_path).exists()
    assert (Path(skill_path) / "SKILL.md").exists()
    assert (Path(skill_path) / "test_cases.yaml").exists()
    assert (Path(skill_path) / "metadata.json").exists()

    # Verify SKILL.md has frontmatter
    skill_content = (Path(skill_path) / "SKILL.md").read_text()
    assert "---" in skill_content
    assert "name: test-skill" in skill_content
