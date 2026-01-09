"""
Skill format validation tests.

These tests validate that all SKILL.md files follow the Agent Skills format
specification. They run quickly (no Qdrant/network required) and should be
part of CI for any changes to skills/.
"""

from pathlib import Path

import frontmatter
import pytest
import yaml

# Path to skills directory (relative to repo root)
SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"

# Required frontmatter metadata fields
REQUIRED_METADATA = {"name", "description"}

# Optional but recommended metadata
RECOMMENDED_METADATA = {"domain", "category", "requires-approval", "confidence"}

# Required markdown sections (## headers)
REQUIRED_SECTIONS = {"Preconditions", "Actions", "Success Criteria"}

# Optional but recommended sections
RECOMMENDED_SECTIONS = {"Failure Handling", "Examples"}


def get_all_skill_paths() -> list[Path]:
    """Get all SKILL.md files in the skills directory."""
    if not SKILLS_DIR.exists():
        return []
    return [
        p
        for p in SKILLS_DIR.rglob("SKILL.md")
        if "proposed" not in p.parts  # Exclude proposed skills from strict validation
    ]


def skill_path_id(path: Path) -> str:
    """Generate test ID from skill path."""
    return str(path.relative_to(SKILLS_DIR.parent))


# Skip all tests if no skills directory
pytestmark = pytest.mark.skipif(
    not SKILLS_DIR.exists() or not get_all_skill_paths(),
    reason="No skills directory or skills found",
)


@pytest.mark.parametrize("skill_path", get_all_skill_paths(), ids=skill_path_id)
def test_skill_is_valid_markdown(skill_path: Path) -> None:
    """Each skill must be valid markdown with YAML frontmatter."""
    content = skill_path.read_text()
    assert content.strip(), f"Empty skill file: {skill_path}"

    # Should start with YAML frontmatter
    assert content.startswith("---"), f"Missing YAML frontmatter: {skill_path}"


@pytest.mark.parametrize("skill_path", get_all_skill_paths(), ids=skill_path_id)
def test_skill_has_valid_frontmatter(skill_path: Path) -> None:
    """Each skill must have valid YAML frontmatter."""
    try:
        post = frontmatter.load(skill_path)
    except Exception as e:
        pytest.fail(f"Invalid frontmatter in {skill_path}: {e}")

    assert post.metadata, f"Empty frontmatter in {skill_path}"


@pytest.mark.parametrize("skill_path", get_all_skill_paths(), ids=skill_path_id)
def test_skill_has_required_metadata(skill_path: Path) -> None:
    """Each skill must have required frontmatter fields."""
    post = frontmatter.load(skill_path)

    for field in REQUIRED_METADATA:
        assert field in post.metadata, f"Missing required field '{field}' in {skill_path}"

    # Validate types
    assert isinstance(post.metadata.get("name"), str), f"'name' must be string in {skill_path}"
    assert isinstance(
        post.metadata.get("description"), str
    ), f"'description' must be string in {skill_path}"


@pytest.mark.parametrize("skill_path", get_all_skill_paths(), ids=skill_path_id)
def test_skill_has_recommended_metadata(skill_path: Path) -> None:
    """Warn if skills are missing recommended metadata (non-failing)."""
    post = frontmatter.load(skill_path)

    missing = []
    metadata = post.metadata.get("metadata", post.metadata)

    for field in RECOMMENDED_METADATA:
        if field not in metadata and field not in post.metadata:
            missing.append(field)

    if missing:
        pytest.skip(f"Missing recommended metadata: {missing} in {skill_path}")


@pytest.mark.parametrize("skill_path", get_all_skill_paths(), ids=skill_path_id)
def test_skill_has_required_sections(skill_path: Path) -> None:
    """Each skill must have required markdown sections."""
    content = skill_path.read_text()

    for section in REQUIRED_SECTIONS:
        # Check for ## Section or ## Section (different heading levels ok)
        section_pattern = f"## {section}"
        assert section_pattern in content, f"Missing section '## {section}' in {skill_path}"


@pytest.mark.parametrize("skill_path", get_all_skill_paths(), ids=skill_path_id)
def test_skill_has_test_yaml(skill_path: Path) -> None:
    """Each skill should have accompanying test scenarios."""
    test_file = skill_path.parent / "test.yaml"
    assert test_file.exists(), f"Missing test.yaml for {skill_path.parent.name}"


@pytest.mark.parametrize("skill_path", get_all_skill_paths(), ids=skill_path_id)
def test_skill_test_yaml_is_valid(skill_path: Path) -> None:
    """Test YAML files must be valid YAML with scenarios."""
    test_file = skill_path.parent / "test.yaml"
    if not test_file.exists():
        pytest.skip("No test.yaml file")

    try:
        with open(test_file) as f:
            test_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        pytest.fail(f"Invalid YAML in {test_file}: {e}")

    assert "scenarios" in test_config, f"Missing 'scenarios' in {test_file}"
    assert isinstance(test_config["scenarios"], list), f"'scenarios' must be a list in {test_file}"
    assert len(test_config["scenarios"]) > 0, f"No scenarios defined in {test_file}"


def test_skill_ids_unique() -> None:
    """All skill IDs (directory names) must be unique."""
    skill_paths = get_all_skill_paths()
    if not skill_paths:
        pytest.skip("No skills found")

    ids = [p.parent.name for p in skill_paths]
    duplicates = [id for id in ids if ids.count(id) > 1]

    assert len(ids) == len(set(ids)), f"Duplicate skill IDs found: {set(duplicates)}"


def test_skill_domains_valid() -> None:
    """All skill domains must be from the allowed list."""
    valid_domains = {"k8s", "news", "general"}

    for skill_path in get_all_skill_paths():
        post = frontmatter.load(skill_path)
        metadata = post.metadata.get("metadata", post.metadata)
        domain = metadata.get("domain")

        if domain:
            assert (
                domain in valid_domains
            ), f"Invalid domain '{domain}' in {skill_path}. Must be one of: {valid_domains}"


def test_skill_categories_valid() -> None:
    """All skill categories must be from the allowed list."""
    valid_categories = {
        # Domain-specific categories
        "remediation",
        "diagnostic",
        "collection",
        "action",
        "analysis",
        "optimization",
        "monitoring",
        "curation",
        "discovery",
        # Cross-cutting general categories
        "memory",
        "notifications",
        "analytics",
        "gitops",
    }

    for skill_path in get_all_skill_paths():
        post = frontmatter.load(skill_path)
        metadata = post.metadata.get("metadata", post.metadata)
        category = metadata.get("category")

        if category:
            assert (
                category in valid_categories
            ), f"Invalid category '{category}' in {skill_path}. Must be one of: {valid_categories}"


def test_skill_confidence_in_range() -> None:
    """Skill confidence must be between 0 and 1."""
    for skill_path in get_all_skill_paths():
        post = frontmatter.load(skill_path)
        metadata = post.metadata.get("metadata", post.metadata)
        confidence = metadata.get("confidence")

        if confidence is not None:
            assert 0 <= confidence <= 1, f"Confidence must be 0-1, got {confidence} in {skill_path}"


def test_skill_mcp_servers_are_list() -> None:
    """MCP servers must be a list if specified."""
    for skill_path in get_all_skill_paths():
        post = frontmatter.load(skill_path)
        metadata = post.metadata.get("metadata", post.metadata)
        servers = metadata.get("mcp-servers")

        if servers is not None:
            assert isinstance(servers, list), f"mcp-servers must be a list in {skill_path}"
