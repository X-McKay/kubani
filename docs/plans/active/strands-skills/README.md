# Skills System Simplification — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ~935 lines of custom discovery code with ~120 lines of minimal custom progressive-disclosure, wire in the existing `SkillLoader` for OCI production discovery, slim the Skills MCP server to execution-only, and fix the frontmatter schema split.

**Architecture:** Skills are loaded at agent creation time from filesystem (dev) or OCI registry (prod). An XML skill catalog is injected into the system prompt for progressive disclosure. A `load_skill` Strands tool lets the agent load full instructions on demand. The Skills MCP server retains only `execute_skill` and `get_execution_outcomes`.

**Tech Stack:** Python 3.12, Strands SDK (`@tool` decorator), PyYAML, existing `kubani.framework.registry.SkillLoader` (ORAS-based OCI), FastMCP, pytest.

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `kubani/framework/skills/catalog.py` | XML catalog generation from filesystem or OCI skill metadata |
| `kubani/framework/skills/policies.py` | Policy definitions and fnmatch-based skill filtering |
| `kubani/nexus/tools/skill_tools.py` | `load_skill` Strands tool for on-demand SKILL.md loading |
| `tests/unit/framework/skills/__init__.py` | Test package init |
| `tests/unit/framework/skills/test_catalog.py` | Unit tests for catalog generation and filesystem loading |
| `tests/unit/framework/skills/test_policies.py` | Unit tests for policy filtering |
| `tests/unit/nexus/tools/__init__.py` | Test package init |
| `tests/unit/nexus/tools/test_skill_tools.py` | Unit tests for `load_skill` tool |

### Modified Files

| File | What Changes |
|------|-------------|
| `kubani/framework/skills/__init__.py` | Replace old exports with new modules |
| `kubani/nexus/orchestrator/activities.py` | Add `_build_skill_catalog()` helper, wire `load_skill` + catalog into both agent activities, update system prompt |
| `kubani/mcp/servers/skills/src/skills_mcp/server.py` | Remove 3 discovery tools, simplify lifespan, update `execute_skill` to use direct path resolution, update `health` tool |
| `kubani/skills/news/*/SKILL.md` (13 files) | Normalize `metadata.kubani.*` to flat `metadata.*` format |

### Deleted Files

| File | Lines |
|------|-------|
| `kubani/mcp/servers/skills/src/skills_mcp/discovery.py` | 256 |
| `kubani/mcp/servers/skills/src/skills_mcp/oci_discovery.py` | 237 |
| `kubani/mcp/servers/skills/tests/test_discovery.py` | 127 |
| `kubani/framework/mcp/skills.py` | 225 |
| `kubani/framework/skills/integration.py` | 218 |

---

## Chunk 1: Frontmatter Normalization + Catalog Module

### Task 1: Normalize news skill frontmatter

**Why:** 13 news skills use `metadata.kubani.domain` while all other skills use `metadata.domain`. Any new parser must handle one format consistently. We normalize to the flat format used by the majority (k8s, general domains).

**Files:**
- Modify: `kubani/skills/news/analysis/analyze-article/SKILL.md`
- Modify: `kubani/skills/news/analysis/detect-trends/SKILL.md`
- Modify: `kubani/skills/news/analysis/identify-breaking-news/SKILL.md`
- Modify: `kubani/skills/news/collection/deduplicate-articles/SKILL.md`
- Modify: `kubani/skills/news/collection/fetch-arxiv-papers/SKILL.md`
- Modify: `kubani/skills/news/collection/fetch-github-trending/SKILL.md`
- Modify: `kubani/skills/news/collection/fetch-rss-feeds/SKILL.md`
- Modify: `kubani/skills/news/collection/filter-ai-relevant/SKILL.md`
- Modify: `kubani/skills/news/diagnostic/analyze-arxiv-paper/SKILL.md`
- Modify: `kubani/skills/news/diagnostic/analyze-github-repo/SKILL.md`
- Modify: `kubani/skills/news/diagnostic/analyze-trends-historical/SKILL.md`
- Modify: `kubani/skills/news/publishing/compose-digest/SKILL.md`
- Modify: `kubani/skills/news/publishing/publish-discord/SKILL.md`

The change is identical for every file. Here is one full example — `fetch-rss-feeds/SKILL.md` frontmatter currently looks like:

```yaml
---
name: fetch-rss-feeds
version: "2.0.0"
description: >
  Fetch articles from RSS/Atom feeds and store them in memory for analysis.
  Uses the rss tool for fetching and memory MCP for storage and deduplication.
license: MIT
allowed-tools:
  - rss
  - memory/add
  - memory/check_seen
  - memory/mark_seen
metadata:
  kubani:
    domain: news
    category: collection
    requires_approval: false
    confidence: 0.95
    version: "2.0.0"
---
```

Change the `metadata:` block in each file to the flat format:

```yaml
metadata:
  domain: news
  category: collection
  requires-approval: false
  confidence: 0.95
  mcp-servers: []
```

Key transformations for every file:
1. Remove the `kubani:` nesting level under `metadata:`
2. Change `requires_approval` (underscore) to `requires-approval` (hyphen)
3. Remove `version:` from inside metadata (redundant with top-level `version`)
4. Add `mcp-servers: []` if absent (or populate from `allowed-tools` if the tools map to MCP servers)
5. Keep `license:` and `allowed-tools:` at top level (these are valid Strands fields)

- [ ] **Step 1.1: Write a validation script to check all skills parse consistently**

Create `scripts/validate_skill_frontmatter.py` (temporary, not committed):

```python
"""Validate all SKILL.md files parse with consistent flat metadata schema."""
import sys
from pathlib import Path

import yaml

SKILLS_ROOT = Path("kubani/skills")
errors = []

for skill_md in sorted(SKILLS_ROOT.rglob("SKILL.md")):
    content = skill_md.read_text()
    if not content.startswith("---"):
        errors.append(f"MISSING FRONTMATTER: {skill_md}")
        continue

    parts = content.split("---", 2)
    if len(parts) < 3:
        errors.append(f"BAD FRONTMATTER DELIMITERS: {skill_md}")
        continue

    meta = yaml.safe_load(parts[1]) or {}

    # Check required top-level fields
    for field in ("name", "description"):
        if field not in meta:
            errors.append(f"MISSING {field}: {skill_md}")

    # Check metadata is flat (no kubani nesting)
    m = meta.get("metadata", {})
    if "kubani" in m:
        errors.append(f"NESTED metadata.kubani: {skill_md}")
        continue

    # Check required metadata fields
    if "domain" not in m:
        errors.append(f"MISSING metadata.domain: {skill_md}")
    if "category" not in m:
        errors.append(f"MISSING metadata.category: {skill_md}")

    # Check hyphen convention (not underscore)
    if "requires_approval" in m:
        errors.append(f"BAD KEY requires_approval (use requires-approval): {skill_md}")

    print(f"OK: {meta.get('name', '???')} ({skill_md.relative_to(SKILLS_ROOT)})")

if errors:
    print(f"\n{'='*60}")
    print(f"ERRORS ({len(errors)}):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"\nAll {len(list(SKILLS_ROOT.rglob('SKILL.md')))} skills validated OK")
```

- [ ] **Step 1.2: Run validation script to see current failures**

Run: `cd /home/al/git/kubani && uv run python scripts/validate_skill_frontmatter.py`

Expected: 13 failures for news skills showing `NESTED metadata.kubani:`.

- [ ] **Step 1.3: Fix all 13 news skill frontmatter blocks**

For each of the 13 files listed above, apply the same transformation. Example diff for `analyze-article/SKILL.md`:

```diff
 metadata:
-  kubani:
-    domain: news
-    category: analysis
-    requires_approval: false
-    confidence: 0.90
-    version: "2.0.0"
+  domain: news
+  category: analysis
+  requires-approval: false
+  confidence: 0.90
+  mcp-servers: []
```

Apply to all 13 files. The `domain` and `category` values come from the existing nested structure. The `confidence` value is preserved. `requires_approval` → `requires-approval`. Remove the nested `version` (redundant with top-level `version`).

- [ ] **Step 1.4: Run validation script again to confirm all pass**

Run: `cd /home/al/git/kubani && uv run python scripts/validate_skill_frontmatter.py`

Expected: `All 48 skills validated OK` with zero errors.

- [ ] **Step 1.5: Run existing tests to confirm nothing broke**

Run: `cd /home/al/git/kubani && just test-unit`

Expected: All existing tests pass. The frontmatter changes are backward-compatible — `discovery.py` reads `metadata.domain` which is now present in all skills (it was already present in k8s/general skills). News skills previously had empty domain/category via discovery.py — now they have correct values.

- [ ] **Step 1.6: Delete validation script, commit**

```bash
rm scripts/validate_skill_frontmatter.py
git add kubani/skills/news/
git commit -m "fix(skills): normalize news skill frontmatter to flat metadata schema

13 news skills used metadata.kubani.* nesting while all other skills
used flat metadata.*. Normalizes to the flat format so all parsers
(current and future) can use one code path.

Changes per file:
- Remove kubani: nesting level
- requires_approval → requires-approval (hyphen convention)
- Remove redundant version from metadata block
- Add mcp-servers: [] where missing

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Create catalog module

**Why:** This module replaces all custom discovery code (`discovery.py`, `oci_discovery.py`, `framework/mcp/skills.py`, `framework/skills/integration.py`). It has two functions: (1) scan the filesystem or OCI registry for skill metadata, (2) generate an XML catalog string for system prompt injection.

**Files:**
- Create: `kubani/framework/skills/catalog.py`
- Create: `tests/unit/framework/skills/__init__.py`
- Create: `tests/unit/framework/skills/test_catalog.py`

- [ ] **Step 2.1: Create test directory**

```bash
mkdir -p tests/unit/framework/skills
touch tests/unit/framework/skills/__init__.py
```

- [ ] **Step 2.2: Write tests for `load_skills_from_filesystem`**

Create `tests/unit/framework/skills/test_catalog.py`:

```python
"""Tests for skill catalog generation."""

from pathlib import Path

import pytest

from kubani.framework.skills.catalog import (
    build_catalog_xml,
    load_skills_from_filesystem,
)


@pytest.fixture
def skills_dir(tmp_path):
    """Create a minimal skills directory with three test skills."""
    # k8s skill with full metadata
    d1 = tmp_path / "k8s" / "diagnostic" / "check-pods"
    d1.mkdir(parents=True)
    (d1 / "SKILL.md").write_text(
        "---\n"
        "name: check-pods\n"
        "description: Check pod health status\n"
        "metadata:\n"
        "  domain: k8s\n"
        "  category: diagnostic\n"
        "---\n\n"
        "# Check Pods\n\nInstructions here.\n"
    )

    # general skill
    d2 = tmp_path / "general" / "memory" / "store-context"
    d2.mkdir(parents=True)
    (d2 / "SKILL.md").write_text(
        "---\n"
        "name: store-context\n"
        "description: Store conversation context in memory\n"
        "metadata:\n"
        "  domain: general\n"
        "  category: memory\n"
        "---\n\n"
        "# Store Context\n\nInstructions here.\n"
    )

    # development skill (should be filterable)
    d3 = tmp_path / "_development" / "test-skill"
    d3.mkdir(parents=True)
    (d3 / "SKILL.md").write_text(
        "---\n"
        "name: _dev-test\n"
        "description: A development test skill\n"
        "metadata:\n"
        "  domain: _development\n"
        "  category: test\n"
        "---\n\n"
        "# Dev Test\n"
    )

    return tmp_path


class TestLoadSkillsFromFilesystem:
    def test_loads_all_skills(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        assert len(skills) == 3

    def test_skill_has_name(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        names = {s["name"] for s in skills}
        assert "check-pods" in names
        assert "store-context" in names
        assert "_dev-test" in names

    def test_skill_has_description(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        for skill in skills:
            assert skill["description"], f"{skill['name']} has empty description"

    def test_skill_has_path(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        for skill in skills:
            assert "path" in skill
            assert Path(skill["path"]).exists()

    def test_nonexistent_dir_returns_empty_list(self, tmp_path):
        skills = load_skills_from_filesystem(tmp_path / "nope")
        assert skills == []

    def test_empty_dir_returns_empty_list(self, tmp_path):
        skills = load_skills_from_filesystem(tmp_path)
        assert skills == []

    def test_malformed_frontmatter_skipped(self, tmp_path):
        """A SKILL.md with bad YAML should be skipped, not crash."""
        d = tmp_path / "bad-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\n: invalid yaml [[\n---\n\n# Bad\n")

        skills = load_skills_from_filesystem(tmp_path)
        assert skills == []

    def test_no_frontmatter_skipped(self, tmp_path):
        """A SKILL.md without --- delimiters should be skipped."""
        d = tmp_path / "plain-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# Just Markdown\n\nNo frontmatter.\n")

        skills = load_skills_from_filesystem(tmp_path)
        assert skills == []

    def test_name_falls_back_to_dirname(self, tmp_path):
        """If frontmatter has no name, use directory name."""
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\ndescription: No name field\n---\n\n# Skill\n"
        )

        skills = load_skills_from_filesystem(tmp_path)
        assert len(skills) == 1
        assert skills[0]["name"] == "my-skill"


class TestBuildCatalogXml:
    def test_produces_valid_xml_structure(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills)
        assert xml.startswith("<available_skills>")
        assert xml.endswith("</available_skills>")

    def test_contains_skill_names(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills)
        assert 'name="check-pods"' in xml
        assert 'name="store-context"' in xml

    def test_contains_descriptions(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills)
        assert "Check pod health" in xml

    def test_denied_patterns_exclude_skills(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills, denied=["_dev*"])
        assert "_dev-test" not in xml
        assert "check-pods" in xml

    def test_multiple_denied_patterns(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills, denied=["_dev*", "check*"])
        assert "_dev-test" not in xml
        assert "check-pods" not in xml
        assert "store-context" in xml

    def test_empty_skills_list(self):
        xml = build_catalog_xml([])
        assert "<available_skills>" in xml
        assert "</available_skills>" in xml
        # Should only have the two XML tags, nothing between
        lines = [l for l in xml.split("\n") if l.strip()]
        assert len(lines) == 2

    def test_description_truncated_at_120_chars(self, tmp_path):
        d = tmp_path / "long-desc"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: long-desc\ndescription: " + "A" * 200 + "\n---\n\n# X\n"
        )
        skills = load_skills_from_filesystem(tmp_path)
        xml = build_catalog_xml(skills)
        # Description in XML should be at most 120 chars
        # Find the content between > and </skill>
        import re
        match = re.search(r'name="long-desc">(.*?)</skill>', xml)
        assert match
        assert len(match.group(1)) <= 120

    def test_newlines_in_description_collapsed(self, tmp_path):
        d = tmp_path / "multiline"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: multiline\ndescription: >\n  Line one.\n  Line two.\n---\n\n# X\n"
        )
        skills = load_skills_from_filesystem(tmp_path)
        xml = build_catalog_xml(skills)
        # Should not contain literal newlines in the XML element
        assert "\n" not in xml.split('name="multiline">')[1].split("</skill>")[0]
```

- [ ] **Step 2.3: Run tests to verify they fail (module doesn't exist yet)**

Run: `cd /home/al/git/kubani && uv run pytest tests/unit/framework/skills/test_catalog.py -v`

Expected: `ModuleNotFoundError: No module named 'kubani.framework.skills.catalog'`

- [ ] **Step 2.4: Implement `kubani/framework/skills/catalog.py`**

```python
"""Skill catalog for progressive disclosure.

Generates an XML catalog of skill metadata for system prompt injection,
and provides loading functions for filesystem and OCI sources.

Two sources:
- Filesystem: scans kubani/skills/ for SKILL.md files (development)
- OCI: queries SkillLoader for published skills (production)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def build_catalog_xml(
    skills: list[dict],
    denied: list[str] | None = None,
) -> str:
    """Build XML skill catalog for system prompt injection.

    Args:
        skills: List of dicts with at minimum 'name' and 'description' keys.
        denied: Optional glob patterns for skills to exclude from the catalog.

    Returns:
        XML string suitable for embedding in a system prompt. Example::

            <available_skills>
              <skill name="check-pods">Check pod health status</skill>
            </available_skills>
    """
    from fnmatch import fnmatch

    denied = denied or []
    lines = ["<available_skills>"]

    for skill in skills:
        name = skill["name"]
        if any(fnmatch(name, p) for p in denied):
            continue
        # Collapse newlines, truncate to 120 chars
        desc = skill.get("description", "").strip().replace("\n", " ")[:120]
        lines.append(f'  <skill name="{name}">{desc}</skill>')

    lines.append("</available_skills>")
    return "\n".join(lines)


def load_skills_from_filesystem(skills_root: Path) -> list[dict]:
    """Scan a directory tree for SKILL.md files and extract metadata.

    Each SKILL.md must start with YAML frontmatter delimited by ``---``.
    Files without frontmatter or with malformed YAML are silently skipped.

    Args:
        skills_root: Root directory to scan recursively.

    Returns:
        Sorted list of dicts with keys: name, description, path.
        Empty list if directory doesn't exist or contains no valid skills.
    """
    if not skills_root.exists():
        return []

    skills: list[dict] = []

    for skill_md in sorted(skills_root.rglob("SKILL.md")):
        try:
            content = skill_md.read_text()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            meta = yaml.safe_load(parts[1]) or {}
            skills.append({
                "name": meta.get("name", skill_md.parent.name),
                "description": meta.get("description", ""),
                "path": str(skill_md.parent),
            })
        except Exception:
            logger.warning("Failed to parse %s", skill_md, exc_info=True)
            continue

    logger.info("Loaded %d skills from filesystem: %s", len(skills), skills_root)
    return skills


async def load_skills_from_oci() -> list[dict]:
    """Load skill summaries from the OCI registry via SkillLoader.

    Uses the existing ``SkillLoader.list_available_skills()`` which queries
    the Registry API for skills with PRODUCTION status. Each returned dict
    has at minimum 'name' and 'description' keys.

    Returns:
        List of skill summary dicts. Empty list on error.
    """
    from kubani.framework.registry.skill_loader import get_skill_loader

    loader = get_skill_loader()
    try:
        available = await loader.list_available_skills()
        return [
            {
                "name": s["name"],
                "description": s.get("description", ""),
                "oci_id": s.get("id"),
            }
            for s in available
        ]
    except Exception:
        logger.exception("Failed to list skills from OCI registry")
        return []


def find_skills_root() -> Path:
    """Locate the kubani/skills/ directory.

    Resolution order:
    1. SKILLS_PATH environment variable (if set)
    2. Walk up from this file to find pyproject.toml, then kubani/skills/
    3. Fallback to relative path ``kubani/skills``

    Returns:
        Path to the skills root directory.
    """
    env_path = os.environ.get("SKILLS_PATH")
    if env_path:
        return Path(env_path)

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            skills_path = parent / "kubani" / "skills"
            if skills_path.exists():
                return skills_path

    return Path("kubani/skills")
```

- [ ] **Step 2.5: Run tests to verify they pass**

Run: `cd /home/al/git/kubani && uv run pytest tests/unit/framework/skills/test_catalog.py -v`

Expected: All 15 tests pass.

- [ ] **Step 2.6: Commit**

```bash
git add kubani/framework/skills/catalog.py tests/unit/framework/skills/
git commit -m "feat(skills): add skill catalog module for progressive disclosure

New module replaces custom discovery code with two focused functions:
- load_skills_from_filesystem: scans SKILL.md frontmatter metadata
- build_catalog_xml: generates XML for system prompt injection

Also adds load_skills_from_oci for production OCI registry loading
via the existing SkillLoader, and find_skills_root for path resolution.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Create policies module

**Why:** Skills must be filtered by policy before catalog generation. The nexus-proactive policy restricts skills to k8s/general operations only. This replaces the scattered fnmatch filtering in `discovery.py` (lines 88-141) and `framework/mcp/skills.py` (lines 60-103).

**Files:**
- Create: `kubani/framework/skills/policies.py`
- Create: `tests/unit/framework/skills/test_policies.py`

- [ ] **Step 3.1: Write tests for policy filtering**

Create `tests/unit/framework/skills/test_policies.py`:

```python
"""Tests for skill policy filtering."""

import pytest

from kubani.framework.skills.policies import SKILL_POLICIES, filter_skills


def _skill(name: str) -> dict:
    """Create a minimal skill dict for testing."""
    return {"name": name, "description": f"Test: {name}"}


@pytest.fixture
def all_skills():
    """A representative set of skills spanning all domains."""
    return [
        _skill("k8s/diagnostic/check-pods"),
        _skill("k8s/remediation/restart-pod"),
        _skill("k8s/collection/get-cluster-health"),
        _skill("news/analysis/sentiment"),
        _skill("news/collection/rss-feed"),
        _skill("general/missions/run-check"),
        _skill("general/notifications/send-alert"),
        _skill("general/analytics/detect-anomaly"),
        _skill("general/memory/store-context"),
        _skill("_development/test-skill"),
    ]


class TestFilterSkills:
    def test_nexus_allows_all_except_dev(self, all_skills):
        result = filter_skills(all_skills, "nexus")
        names = {s["name"] for s in result}
        assert len(result) == 9  # all except _development
        assert "_development/test-skill" not in names

    def test_nexus_proactive_restricts_to_allowed_domains(self, all_skills):
        result = filter_skills(all_skills, "nexus-proactive")
        names = {s["name"] for s in result}

        # k8s/* allowed
        assert "k8s/diagnostic/check-pods" in names
        assert "k8s/remediation/restart-pod" in names
        assert "k8s/collection/get-cluster-health" in names
        # general/missions/*, general/notifications/*, general/analytics/* allowed
        assert "general/missions/run-check" in names
        assert "general/notifications/send-alert" in names
        assert "general/analytics/detect-anomaly" in names
        # news/* NOT allowed
        assert "news/analysis/sentiment" not in names
        assert "news/collection/rss-feed" not in names
        # general/memory/* NOT allowed
        assert "general/memory/store-context" not in names
        # _development/* denied
        assert "_development/test-skill" not in names

    def test_nexus_computer_allows_all_except_dev(self, all_skills):
        result = filter_skills(all_skills, "nexus-computer")
        assert len(result) == 9

    def test_unknown_policy_falls_back_to_nexus(self, all_skills):
        result = filter_skills(all_skills, "nonexistent-policy")
        assert len(result) == 9  # same as nexus

    def test_denied_takes_priority_over_allowed(self):
        """A skill matching both allowed and denied patterns is excluded."""
        skills = [_skill("_development/k8s/test-thing")]
        result = filter_skills(skills, "nexus")
        assert len(result) == 0

    def test_empty_input_returns_empty(self):
        result = filter_skills([], "nexus")
        assert result == []

    def test_all_expected_policies_exist(self):
        assert "nexus" in SKILL_POLICIES
        assert "nexus-proactive" in SKILL_POLICIES
        assert "nexus-computer" in SKILL_POLICIES

    def test_each_policy_has_allowed_and_denied(self):
        for name, rules in SKILL_POLICIES.items():
            assert "allowed" in rules, f"Policy '{name}' missing 'allowed'"
            assert "denied" in rules, f"Policy '{name}' missing 'denied'"
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `cd /home/al/git/kubani && uv run pytest tests/unit/framework/skills/test_policies.py -v`

Expected: `ModuleNotFoundError: No module named 'kubani.framework.skills.policies'`

- [ ] **Step 3.3: Implement `kubani/framework/skills/policies.py`**

```python
"""Policy-based skill filtering.

Skills are filtered before catalog generation, not at query time.
This means the agent literally cannot see skills outside its policy
because they never enter the system prompt.

Policy names match the MCP connection policies in
``kubani/nexus/tools/mcp_clients.py`` (lines 48-73) so that the
``mcp_policy`` parameter controls both MCP server access and skill
visibility in a single knob.
"""

from __future__ import annotations

import logging
from fnmatch import fnmatch

logger = logging.getLogger(__name__)

# Each policy defines which skill name patterns are allowed/denied.
# ``allowed`` patterns are checked with fnmatch — a skill must match
# at least one allowed pattern to be included.
# ``denied`` patterns are checked first — a matching skill is excluded
# even if it also matches an allowed pattern.
SKILL_POLICIES: dict[str, dict[str, list[str]]] = {
    "nexus": {
        "allowed": ["*"],
        "denied": ["_development/*"],
    },
    "nexus-proactive": {
        "allowed": [
            "k8s/*",
            "general/missions/*",
            "general/notifications/*",
            "general/analytics/*",
        ],
        "denied": ["_development/*"],
    },
    "nexus-computer": {
        "allowed": ["*"],
        "denied": ["_development/*"],
    },
}


def filter_skills(skills: list[dict], policy: str) -> list[dict]:
    """Filter skill dicts by a named policy.

    Args:
        skills: List of skill dicts. Each must have a ``name`` key.
        policy: Policy name (e.g. ``"nexus"``, ``"nexus-proactive"``).
                Falls back to ``"nexus"`` if the name is unknown.

    Returns:
        New list containing only skills permitted by the policy.
    """
    rules = SKILL_POLICIES.get(policy)
    if rules is None:
        logger.warning("Unknown skill policy '%s', falling back to 'nexus'", policy)
        rules = SKILL_POLICIES["nexus"]

    allowed_patterns = rules["allowed"]
    denied_patterns = rules["denied"]

    filtered = []
    for skill in skills:
        name = skill["name"]

        # Denied patterns checked first — takes priority
        if any(fnmatch(name, p) for p in denied_patterns):
            continue

        # Must match at least one allowed pattern
        if any(fnmatch(name, p) for p in allowed_patterns):
            filtered.append(skill)

    logger.info(
        "Policy '%s': %d/%d skills passed filter",
        policy, len(filtered), len(skills),
    )
    return filtered
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `cd /home/al/git/kubani && uv run pytest tests/unit/framework/skills/test_policies.py -v`

Expected: All 8 tests pass.

- [ ] **Step 3.5: Run full test suite to check for regressions**

Run: `cd /home/al/git/kubani && just test-unit`

Expected: All tests pass. These new modules are additive — nothing imports them yet.

- [ ] **Step 3.6: Commit**

```bash
git add kubani/framework/skills/policies.py tests/unit/framework/skills/test_policies.py
git commit -m "feat(skills): add policy-based skill filtering

New module defines SKILL_POLICIES matching MCP connection policies
(nexus, nexus-proactive, nexus-computer) and provides filter_skills()
using fnmatch patterns. Denied patterns take priority over allowed.

Replaces scattered filtering in discovery.py and framework/mcp/skills.py.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: load_skill Tool + Nexus Integration

### Task 4: Create the `load_skill` Strands tool

**Why:** When the agent sees a skill in the XML catalog and decides to use it, it needs a way to load the full SKILL.md content. This tool replaces the `get_skill` MCP tool. It reads from the filesystem first, with OCI cache fallback.

**Files:**
- Create: `kubani/nexus/tools/skill_tools.py`
- Create: `tests/unit/nexus/tools/__init__.py`
- Create: `tests/unit/nexus/tools/test_skill_tools.py`

- [ ] **Step 4.1: Create test directory**

```bash
mkdir -p tests/unit/nexus/tools
touch tests/unit/nexus/tools/__init__.py
```

- [ ] **Step 4.2: Write tests for `load_skill`**

Create `tests/unit/nexus/tools/test_skill_tools.py`:

```python
"""Tests for the load_skill Strands tool."""

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def skills_dir(tmp_path):
    """Create a skills directory with two test skills."""
    d1 = tmp_path / "k8s" / "diagnostic" / "check-pods"
    d1.mkdir(parents=True)
    (d1 / "SKILL.md").write_text(
        "---\n"
        "name: check-pods\n"
        "description: Check pod health\n"
        "metadata:\n"
        "  domain: k8s\n"
        "  category: diagnostic\n"
        "---\n\n"
        "# Check Pods\n\n"
        "## Steps\n"
        "1. Get pod status\n"
        "2. Check events\n"
    )

    d2 = tmp_path / "general" / "memory" / "store-context"
    d2.mkdir(parents=True)
    (d2 / "SKILL.md").write_text(
        "---\n"
        "name: store-context\n"
        "description: Store context\n"
        "---\n\n"
        "# Store Context\n\nStore stuff.\n"
    )

    return tmp_path


class TestLoadSkillFromFilesystem:
    def test_loads_existing_skill(self, skills_dir):
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=skills_dir,
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("check-pods")

        assert "# Check Pods" in result
        assert "Get pod status" in result

    def test_returns_full_content_including_frontmatter(self, skills_dir):
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=skills_dir,
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("check-pods")

        assert "name: check-pods" in result

    def test_not_found_returns_error_message(self, skills_dir):
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=skills_dir,
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("nonexistent-skill")

        assert "not found" in result.lower()

    def test_finds_skill_by_name_not_path(self, skills_dir):
        """Should match on the 'name' field in frontmatter, not directory name."""
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=skills_dir,
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("store-context")

        assert "# Store Context" in result

    def test_nonexistent_skills_root(self, tmp_path):
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=tmp_path / "nope",
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("anything")

        assert "not found" in result.lower()
```

- [ ] **Step 4.3: Run tests to verify they fail**

Run: `cd /home/al/git/kubani && uv run pytest tests/unit/nexus/tools/test_skill_tools.py -v`

Expected: `ModuleNotFoundError: No module named 'kubani.nexus.tools.skill_tools'`

- [ ] **Step 4.4: Implement `kubani/nexus/tools/skill_tools.py`**

```python
"""Skill tools for the Nexus agent.

Provides ``load_skill`` — the agent calls this to load full SKILL.md
content for a skill it selected from the XML catalog in its system prompt.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from strands import tool

from kubani.framework.skills.catalog import find_skills_root

logger = logging.getLogger(__name__)


def _load_skill_impl(skill_name: str) -> str:
    """Load a skill's full SKILL.md content by name.

    Searches the filesystem skills directory first. If OCI discovery
    is enabled and the skill isn't found locally, searches the
    SkillLoader's on-disk cache (populated by OCI pulls).

    Args:
        skill_name: Skill name from the catalog (e.g. "investigate-pod-failure").

    Returns:
        Full SKILL.md content string, or an error message if not found.
    """
    # --- Filesystem search ---
    skills_root = find_skills_root()
    if skills_root.exists():
        result = _search_directory(skills_root, skill_name)
        if result is not None:
            return result

    # --- OCI cache search (only if enabled) ---
    oci_enabled = os.environ.get("OCI_DISCOVERY_ENABLED", "false").lower() == "true"
    if oci_enabled:
        result = _search_oci_cache(skill_name)
        if result is not None:
            return result

    return f"Skill '{skill_name}' not found."


def _search_directory(root: Path, skill_name: str) -> str | None:
    """Search a directory tree for a SKILL.md matching the given name."""
    for skill_md in root.rglob("SKILL.md"):
        try:
            content = skill_md.read_text()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            meta = yaml.safe_load(parts[1]) or {}
            if meta.get("name") == skill_name:
                return content
        except Exception:
            continue
    return None


def _search_oci_cache(skill_name: str) -> str | None:
    """Search the SkillLoader's on-disk cache for a skill.

    The cache directory (default: ~/.kubani/skill-cache/) contains
    subdirectories keyed by OCI digest, each with an extracted SKILL.md.
    """
    try:
        from kubani.framework.registry.skill_loader import get_skill_loader

        loader = get_skill_loader()
        if not loader.cache_dir.exists():
            return None

        return _search_directory(loader.cache_dir, skill_name)
    except Exception:
        logger.warning("OCI cache search failed for %s", skill_name, exc_info=True)
        return None


@tool
def load_skill(skill_name: str) -> str:
    """Load full instructions for a skill by name.

    Call this when you want to activate a skill from the <available_skills>
    catalog in your system prompt. Returns the complete SKILL.md content
    including instructions, preconditions, and steps.

    After loading, follow the skill's instructions using your other tools.
    If the skill has executable scripts, use execute_skill via MCP.

    Args:
        skill_name: The skill name from the catalog (e.g. "investigate-pod-failure")
    """
    return _load_skill_impl(skill_name)
```

**Design notes:**
- The `_load_skill_impl` function is separated from the `@tool`-decorated `load_skill` so tests can call it directly without Strands tool machinery.
- The `@tool` decorator makes this a Strands tool that the Agent can call.
- Filesystem is checked first (fast, local). OCI cache is checked second (only if `OCI_DISCOVERY_ENABLED=true`).
- The OCI path uses `_search_directory` on the cache dir — same logic, different root. This avoids calling the async `SkillLoader.load_skill()` from a sync context.

- [ ] **Step 4.5: Run tests to verify they pass**

Run: `cd /home/al/git/kubani && uv run pytest tests/unit/nexus/tools/test_skill_tools.py -v`

Expected: All 5 tests pass.

- [ ] **Step 4.6: Commit**

```bash
git add kubani/nexus/tools/skill_tools.py tests/unit/nexus/tools/
git commit -m "feat(nexus): add load_skill tool for on-demand skill loading

Strands @tool that loads full SKILL.md content when the agent
activates a skill from the XML catalog. Searches filesystem first,
falls back to OCI cache when OCI_DISCOVERY_ENABLED=true.

Replaces the get_skill MCP tool with a simpler, local-first approach.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: Wire skill catalog into Nexus activities

**Why:** This is the core integration — injecting the XML catalog into the agent's system prompt and adding `load_skill` to the agent's tool list. Both `run_agent_turn` and `run_mission_agent_turn` need this.

**Files:**
- Modify: `kubani/nexus/orchestrator/activities.py:50-100` (system prompt)
- Modify: `kubani/nexus/orchestrator/activities.py:140-218` (run_agent_turn)
- Modify: `kubani/nexus/orchestrator/activities.py:414-534` (run_mission_agent_turn)

- [ ] **Step 5.1: Add the `_build_skill_catalog` helper function**

In `kubani/nexus/orchestrator/activities.py`, add the following import and helper right after the `logger = ...` line (line 41) and before the `AGENT_SYSTEM_PROMPT` definition (line 50):

```python
# --- Add after line 41 ---

async def _build_skill_catalog(policy: str) -> str:
    """Build skill catalog XML for the given policy.

    Uses filesystem in development, OCI registry in production.
    Returns empty string if no skills are found or on error.
    """
    import os

    from kubani.framework.skills import (
        build_catalog_xml,
        filter_skills,
        find_skills_root,
        load_skills_from_filesystem,
    )

    use_oci = os.environ.get("OCI_DISCOVERY_ENABLED", "false").lower() == "true"

    if use_oci:
        from kubani.framework.skills import load_skills_from_oci

        skills = await load_skills_from_oci()
    else:
        skills = load_skills_from_filesystem(find_skills_root())

    if not skills:
        return ""

    filtered = filter_skills(skills, policy)
    if not filtered:
        return ""

    return build_catalog_xml(filtered)
```

- [ ] **Step 5.2: Update the AGENT_SYSTEM_PROMPT**

In `activities.py`, find the `SKILLS (via MCP)` section of `AGENT_SYSTEM_PROMPT` (line 75-76):

```python
# Current (line 75-76):
SKILLS (via MCP): Discover and execute registered Kubani skills.
  For finding and running pre-built capabilities.
```

Replace with:

```python
SKILLS: You have specialized skills listed in <available_skills> below.
  Call load_skill(skill_name="...") to load a skill's full instructions.
  Follow the instructions using your other tools (kubernetes MCP, fetch, etc).
  For skills with executable scripts, use execute_skill via MCP to run them safely.
```

- [ ] **Step 5.3: Wire catalog + load_skill into `run_agent_turn`**

In `run_agent_turn`, find lines 203-218 and make these changes:

**Add import** at line 140 (inside the function, with the other lazy imports):

```python
    from kubani.nexus.tools.skill_tools import load_skill
```

**Insert catalog building** after line 201 (after `full_prompt` is constructed, before `system_prompt` assembly):

```python
    # Build skill catalog and inject into system prompt
    skill_catalog = await _build_skill_catalog(policy="nexus")
```

**Modify system prompt assembly** (currently lines 203-210). Replace:

```python
    system_prompt = AGENT_SYSTEM_PROMPT
    if computer_use_enabled:
        system_prompt += COMPUTER_USE_PROMPT
    if not mcp_tools:
        system_prompt += (
            "\n\nNote: MCP servers could not be reached. "
            "Memory, Skills, and Fetch tools are unavailable this session."
        )
```

With:

```python
    system_prompt = AGENT_SYSTEM_PROMPT
    if skill_catalog:
        system_prompt += "\n\n" + skill_catalog
    if computer_use_enabled:
        system_prompt += COMPUTER_USE_PROMPT
    if not mcp_tools:
        system_prompt += (
            "\n\nNote: MCP servers could not be reached. "
            "Memory, Skills, and Fetch tools are unavailable this session."
        )
```

**Add `load_skill` to tools list** (currently line 212):

```python
    # Current:
    all_tools = [*workspace_tools, *mcp_tools]
    # Change to:
    all_tools = [load_skill, *workspace_tools, *mcp_tools]
```

- [ ] **Step 5.4: Wire catalog + load_skill into `run_mission_agent_turn`**

In `run_mission_agent_turn`, make parallel changes:

**Add import** at line 417 (with the other lazy imports):

```python
    from kubani.nexus.tools.skill_tools import load_skill
```

**Insert catalog building** after line 497 (after `system_prompt` is formatted from template, before prompt_parts):

```python
    # Build skill catalog filtered by mission policy
    skill_catalog = await _build_skill_catalog(policy=mcp_policy)
    if skill_catalog:
        system_prompt += "\n\n" + skill_catalog
```

**Add `load_skill` to tools list.** At line 531, change:

```python
    # Current:
    tools=mcp_tools,
    # Change to:
    tools=[load_skill, *mcp_tools],
```

- [ ] **Step 5.5: Run existing tests**

Run: `cd /home/al/git/kubani && just test-unit`

Expected: All tests pass. The changes are additive — `_build_skill_catalog` is called at runtime only when an activity executes. Existing tests that mock the Agent constructor will still work because `load_skill` is just another tool in the list.

- [ ] **Step 5.6: Local smoke test (optional but recommended)**

```bash
cd /home/al/git/kubani/kubani/nexus/orchestrator
source .env
python -m kubani.nexus.orchestrator.worker
```

From another terminal, trigger a conversation turn and check the worker logs for:
- `Loaded N skills from filesystem` (from `load_skills_from_filesystem`)
- `Policy 'nexus': N/M skills passed filter` (from `filter_skills`)
- The system prompt should now contain `<available_skills>` XML

- [ ] **Step 5.7: Commit**

```bash
git add kubani/nexus/orchestrator/activities.py
git commit -m "feat(nexus): wire skill catalog and load_skill into agent activities

Both run_agent_turn and run_mission_agent_turn now:
- Build an XML skill catalog filtered by policy at agent creation
- Inject the catalog into the system prompt for progressive disclosure
- Include load_skill in the agent's tool list for on-demand loading

The mcp_policy parameter controls both MCP server access and skill
visibility, keeping the two in sync.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Update `kubani/framework/skills/__init__.py`

**Why:** The current `__init__.py` exports from `integration.py` which we'll delete in a later task. Update it now to export from the new modules, so all downstream imports work.

**Files:**
- Modify: `kubani/framework/skills/__init__.py`

- [ ] **Step 6.1: Replace `__init__.py` contents**

Replace the entire file at `kubani/framework/skills/__init__.py` with:

```python
"""Kubani Skills Framework.

Provides skill catalog generation, policy filtering, and loading functions
for progressive skill disclosure in Nexus agents.
"""

from kubani.framework.skills.catalog import (
    build_catalog_xml,
    find_skills_root,
    load_skills_from_filesystem,
    load_skills_from_oci,
)
from kubani.framework.skills.policies import SKILL_POLICIES, filter_skills

__all__ = [
    "build_catalog_xml",
    "find_skills_root",
    "filter_skills",
    "load_skills_from_filesystem",
    "load_skills_from_oci",
    "SKILL_POLICIES",
]
```

**Note:** This intentionally removes the old exports (`KubaniSkill`, `discover_kubani_skills`, etc.). Any code that imports those will break — that's expected and we'll fix those imports in the cleanup task.

- [ ] **Step 6.2: Check what breaks**

Run: `cd /home/al/git/kubani && uv run ruff check .`

Expected: Import errors in `kubani/agents/_base/skills_orchestrator.py` and its tests. These files import `KubaniSkill`, `discover_kubani_skills`, and `generate_skills_catalog` from the old module. We'll handle those in the cleanup phase (Task 9).

- [ ] **Step 6.3: Commit**

```bash
git add kubani/framework/skills/__init__.py
git commit -m "refactor(skills): update framework skills exports to new modules

Replace exports from integration.py (being deleted) with exports from
the new catalog.py and policies.py modules. Old imports will break —
fixed in the cleanup task.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: MCP Server Slimming + Dead Code Removal

### Task 7: Slim the Skills MCP server

**Why:** With discovery moved to the framework and `load_skill` tool, the MCP server only needs to provide `execute_skill`, `get_execution_outcomes`, `health`, and `metrics`. Remove the 3 discovery tools and their lifespan setup.

**Files:**
- Modify: `kubani/mcp/servers/skills/src/skills_mcp/server.py`

- [ ] **Step 7.1: Remove discovery imports from `server.py`**

At the top of `server.py`, delete these two import lines (lines 21 and 30):

```python
# DELETE line 21:
from skills_mcp.discovery import get_discovery

# DELETE line 30:
from skills_mcp.oci_discovery import get_oci_discovery
```

Also remove unused model imports from line 23-29. After the change, the imports should be:

```python
from skills_mcp.executor import get_executor_manager
from skills_mcp.models import (
    ExecutionStatus,
    SkillExecuteResult,
)
```

(`SkillDetailResult`, `SkillInfo`, `SkillListResult` are no longer needed since the tools that used them are being deleted.)

- [ ] **Step 7.2: Simplify the lifespan function**

Replace the entire `lifespan` function (lines 63-196) with this simplified version that only sets up the executor:

```python
@asynccontextmanager
async def lifespan(server: FastMCP):
    """Initialize execution infrastructure.

    Discovery is handled by the framework (kubani.framework.skills.catalog),
    not by this server. We only need the executor for sandboxed execution.
    """
    global _health_manager, _metrics_collector, _registry_client, _heartbeat_task

    # --- Executor setup (unchanged from before) ---
    microsandbox_enabled = os.environ.get("MICROSANDBOX_ENABLED", "true").lower() == "true"
    microsandbox_url = os.environ.get("MICROSANDBOX_URL")

    executor_manager = get_executor_manager()
    if not executor_manager._initialized:
        await executor_manager.initialize(
            microsandbox_enabled=microsandbox_enabled,
            microsandbox_url=microsandbox_url,
        )

    # --- Health checks (executor only) ---
    _health_manager = HealthCheckManager()
    _health_manager.register_check(
        "executor",
        lambda: {"status": "ok", "executor": executor_manager.get_executor_name()},
        timeout=5.0,
    )

    # --- Metrics ---
    _metrics_collector = MetricsCollector()

    # --- Registry heartbeat ---
    registry_url = os.environ.get("REGISTRY_URL")
    if registry_url:
        try:
            _registry_client = RegistryClient(registry_url)
            await _registry_client.register(
                name="skills-mcp",
                server_type="mcp",
                capabilities=["execute_skill", "get_execution_outcomes"],
                metadata={
                    "executor": executor_manager.get_executor_name(),
                },
            )
            _heartbeat_task = asyncio.create_task(
                _registry_client.heartbeat_loop(interval=30)
            )
            logger.info(f"Registered with registry at {registry_url}")
        except Exception as e:
            logger.warning(f"Failed to register with registry: {e}")

    logger.info(
        "Skills MCP Server started (execution-only mode, "
        f"executor={executor_manager.get_executor_name()})"
    )

    yield

    # --- Cleanup ---
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
    if _registry_client:
        try:
            await _registry_client.unregister()
        except Exception:
            pass

    logger.info("Skills MCP Server shutting down")
```

- [ ] **Step 7.3: Delete the 3 discovery tool definitions**

Delete these entire function blocks from `create_server()`:

1. **`list_skills`** (lines 225-274) — the `@mcp.tool()` decorator through the return statement
2. **`get_skill`** (lines 276-297) — same
3. **`refresh_skills`** (lines 299-323) — same

Also delete the comment `# Skill Discovery Tools` (line 222-223).

- [ ] **Step 7.4: Update `execute_skill` to use direct path resolution**

In the `execute_skill` tool (starts at line 329), replace the discovery lookup:

```python
# DELETE these lines (currently ~353-370):
        discovery = get_discovery()
        skill = discovery.get_skill(skill_path)

        if skill is None:
            return SkillExecuteResult(
                skill_path=skill_path,
                status=ExecutionStatus.FAILED,
                error=f"Skill not found: {skill_path}",
            )

        # Check if skill has executable scripts
        if not skill.scripts:
            return SkillExecuteResult(
                skill_path=skill_path,
                status=ExecutionStatus.SKIPPED,
                output=skill.content,
                error="Skill has no executable scripts (declarative skill)",
            )
```

Replace with direct path resolution:

```python
        # Resolve skill directory from path
        skills_root = Path(os.environ.get("SKILLS_PATH", "kubani/skills"))
        # Handle both absolute and relative paths
        if not skills_root.is_absolute():
            # Walk up to find repo root (same strategy as catalog.find_skills_root)
            current = Path(__file__).resolve()
            for parent in current.parents:
                if (parent / "pyproject.toml").exists():
                    skills_root = parent / skills_root
                    break

        skill_dir = skills_root / skill_path
        if not skill_dir.exists():
            return SkillExecuteResult(
                skill_path=skill_path,
                status=ExecutionStatus.FAILED,
                error=f"Skill directory not found: {skill_path}",
            )

        # Check for executable scripts
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.exists() or not any(scripts_dir.iterdir()):
            # Read SKILL.md content for declarative skills
            skill_md = skill_dir / "SKILL.md"
            content = skill_md.read_text() if skill_md.exists() else ""
            return SkillExecuteResult(
                skill_path=skill_path,
                status=ExecutionStatus.SKIPPED,
                output=content,
                error="Skill has no executable scripts (declarative skill)",
            )

        # Build a minimal SkillInfo for the executor.
        # Note: SkillInfo.scripts is list[str] (filenames), not dict.
        from skills_mcp.models import SkillInfo

        script_names = [f.name for f in scripts_dir.iterdir() if f.is_file()]
        skill = SkillInfo(
            path=skill_path,
            name=skill_path.split("/")[-1],
            scripts=script_names,
            skill_dir=str(skill_dir),
        )
```

Also add `from pathlib import Path` to the imports at the top of `server.py` if not already present.

- [ ] **Step 7.5: Update `health` tool to remove discovery reference**

In the `health` tool (line 427-455), replace the fallback block that calls `get_discovery()`:

```python
    @mcp.tool()
    async def health() -> dict[str, Any]:
        """Check the health of the Skills MCP server."""
        if _health_manager:
            health_response = await _health_manager.check_all()
            return health_response.to_dict()

        # Fallback if health manager not initialized
        try:
            executor = get_executor_manager()
            return {
                "status": "healthy",
                "executor": executor.get_executor_name(),
                "microsandbox_enabled": executor.microsandbox_enabled,
                "mode": "execution-only",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }
```

- [ ] **Step 7.6: Update the server description**

In `create_server()` (line 209-213), update the `instructions` string:

```python
    mcp = FastMCP(
        name="Skills MCP Server",
        instructions=(
            "Kubani Skills MCP Server (execution-only mode). Use execute_skill "
            "to run skill scripts in isolated Microsandbox environments. Use "
            "get_execution_outcomes to review recent execution results."
        ),
        lifespan=lifespan,
```

- [ ] **Step 7.7: Run MCP server tests**

Run: `cd /home/al/git/kubani && uv run pytest kubani/mcp/servers/skills/tests/test_executor.py -v`

Expected: Executor tests pass unchanged (we didn't modify executor.py).

Run: `cd /home/al/git/kubani && uv run pytest kubani/mcp/servers/skills/tests/test_integration.py -v`

Expected: May have failures if integration tests call `list_skills` or `get_skill`. If so, those tests need updating in the next step.

- [ ] **Step 7.8: Commit**

```bash
git add kubani/mcp/servers/skills/src/skills_mcp/server.py
git commit -m "refactor(skills-mcp): remove discovery tools, execution-only mode

Remove list_skills, get_skill, refresh_skills tools and all discovery
setup from the lifespan. The MCP server now only provides:
- execute_skill: sandboxed script execution
- get_execution_outcomes: execution history
- health / metrics: operational tools

Discovery is handled by kubani.framework.skills.catalog which injects
an XML skill catalog into the agent's system prompt.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 8: Delete dead files

**Why:** With the new modules in place and the MCP server slimmed, these files are no longer imported by anything.

**Files:**
- Delete: `kubani/mcp/servers/skills/src/skills_mcp/discovery.py` (256 lines)
- Delete: `kubani/mcp/servers/skills/src/skills_mcp/oci_discovery.py` (237 lines)
- Delete: `kubani/mcp/servers/skills/tests/test_discovery.py` (127 lines)
- Delete: `kubani/framework/mcp/skills.py` (225 lines)
- Delete: `kubani/framework/skills/integration.py` (218 lines)

- [ ] **Step 8.1: Verify no remaining imports of discovery modules**

```bash
cd /home/al/git/kubani
grep -r "from skills_mcp.discovery" --include="*.py" | grep -v __pycache__
grep -r "from skills_mcp.oci_discovery" --include="*.py" | grep -v __pycache__
```

Expected: No results (the only importer was `server.py`, which we already updated).

- [ ] **Step 8.2: Verify no remaining imports of framework/mcp/skills.py**

```bash
grep -r "from kubani.framework.mcp.skills" --include="*.py" | grep -v __pycache__
```

Expected: Results in `kubani/agents/_base/agent.py` (line 33) and possibly tests. These are handled in Task 9.

- [ ] **Step 8.3: Verify no remaining imports of framework/skills/integration.py**

```bash
grep -r "from kubani.framework.skills.integration" --include="*.py" | grep -v __pycache__
grep -r "from kubani.framework.skills import.*KubaniSkill\|discover_kubani\|parse_kubani\|generate_skills" --include="*.py" | grep -v __pycache__
```

Expected: Results in `kubani/agents/_base/skills_orchestrator.py` (line 14) and tests. Handled in Task 9.

- [ ] **Step 8.4: Delete the files**

```bash
rm kubani/mcp/servers/skills/src/skills_mcp/discovery.py
rm kubani/mcp/servers/skills/src/skills_mcp/oci_discovery.py
rm kubani/mcp/servers/skills/tests/test_discovery.py
rm kubani/framework/mcp/skills.py
rm kubani/framework/skills/integration.py
```

- [ ] **Step 8.5: Commit**

```bash
git add -A kubani/mcp/servers/skills/src/skills_mcp/discovery.py \
           kubani/mcp/servers/skills/src/skills_mcp/oci_discovery.py \
           kubani/mcp/servers/skills/tests/test_discovery.py \
           kubani/framework/mcp/skills.py \
           kubani/framework/skills/integration.py
git commit -m "refactor(skills): delete superseded discovery and framework wrapper code

Remove 1,063 lines of code replaced by ~120 lines in the new
catalog.py, policies.py, and skill_tools.py modules:

- discovery.py (256 LOC): filesystem skill scanning
- oci_discovery.py (237 LOC): unimplemented OCI stub
- test_discovery.py (127 LOC): tests for above
- framework/mcp/skills.py (225 LOC): broken async MCP client wrappers
- framework/skills/integration.py (218 LOC): duplicate SKILL.md parser

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 9: Fix broken imports in legacy agents

**Why:** The `SkillsOrchestrator` base class and `KubaniAgent` import from the deleted modules. These are used by 6 syndicate agents (FeedCollector, ContentAnalyst, etc.). We need to update them to not crash on import, even though Nexus is the primary user path.

**Files:**
- Modify: `kubani/agents/_base/agent.py:33`
- Modify: `kubani/agents/_base/skills_orchestrator.py:14-18`
- Modify: `kubani/agents/_base/__init__.py`
- Modify: `tests/unit/agents/test_skills_orchestrator.py`

- [ ] **Step 9.1: Update `agent.py` to remove dead import**

In `kubani/agents/_base/agent.py`, line 33, delete:

```python
from kubani.framework.mcp.skills import get_filtered_skills
```

Then find the `get_filtered_skills` call at line 174 and the `get_skill_as_tool` call at line 206. Both are inside methods of `KubaniAgent`. Replace the entire `_load_skills` and `_skill_to_tool` methods to raise `NotImplementedError` since they relied on the deleted module:

```python
    async def _load_skills(self, skills_config: dict) -> list:
        """Load skills for this agent.

        Note: Legacy skill loading via MCP has been removed. Agents should
        use the Strands AgentSkills catalog (kubani.framework.skills.catalog)
        instead. See SkillsOrchestrator for the updated pattern.
        """
        logger.warning(
            "KubaniAgent._load_skills() called but MCP skill loading has been removed. "
            "Use kubani.framework.skills.catalog for skill discovery."
        )
        return []

    @staticmethod
    def _skill_to_tool(skill):
        """Convert a skill to a callable tool.

        Note: Legacy conversion via get_skill_as_tool has been removed.
        """
        raise NotImplementedError(
            "Legacy skill-to-tool conversion removed. "
            "Use load_skill from kubani.nexus.tools.skill_tools instead."
        )
```

- [ ] **Step 9.2: Update `skills_orchestrator.py` to use new modules**

Replace the imports at the top of `kubani/agents/_base/skills_orchestrator.py` (lines 14-18):

```python
# DELETE:
from kubani.framework.skills import (
    KubaniSkill,
    discover_kubani_skills,
    generate_skills_catalog,
)

# REPLACE WITH:
from kubani.framework.skills import (
    build_catalog_xml,
    filter_skills,
    find_skills_root,
    load_skills_from_filesystem,
)
```

Then update the methods that use the old functions. Read the full file to find them:

- `_discover_skills` (line 53): currently calls `discover_kubani_skills()` — replace with `load_skills_from_filesystem(find_skills_root())`
- `_generate_skills_prompt` (line 80): currently calls `generate_skills_catalog(self._skills)` — replace with `build_catalog_xml(self._skills)`
- The `skills` property (line 76): currently returns `list[KubaniSkill]` — change to `list[dict]`
- The `_skills` field (line 50): currently `list[KubaniSkill]` — change to `list[dict]`

- [ ] **Step 9.3: Update `test_skills_orchestrator.py`**

Replace the test file to use new imports:

```python
"""Tests for SkillsOrchestrator base class."""

from pathlib import Path
from unittest.mock import patch

from kubani.agents._base.skills_orchestrator import SkillsOrchestrator


class TestSkillsOrchestrator:
    """Test the SkillsOrchestrator base class."""

    def test_orchestrator_inherits_kubani_agent(self):
        from kubani.agents._base import KubaniAgent
        assert issubclass(SkillsOrchestrator, KubaniAgent)

    def test_orchestrator_discovers_skills(self):
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_load:
            mock_load.return_value = []

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent
                async def on_skill_complete(self, skill_name, result):
                    pass

            TestOrchestrator()
            mock_load.assert_called()

    def test_orchestrator_generates_skills_prompt(self):
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_load:
            mock_load.return_value = [
                {
                    "name": "test-skill",
                    "description": "A test skill",
                    "path": "/test",
                }
            ]

            class TestOrchestrator(SkillsOrchestrator):
                AGENT_DIR = Path(__file__).parent
                async def on_skill_complete(self, skill_name, result):
                    pass

            orchestrator = TestOrchestrator()
            prompt = orchestrator._generate_skills_prompt()

            assert "test-skill" in prompt
            assert "A test skill" in prompt
```

- [ ] **Step 9.4: Run tests**

Run: `cd /home/al/git/kubani && just test-unit`

Expected: All tests pass. If other agent tests fail due to the `KubaniSkill` import, fix them with the same pattern — replace `KubaniSkill(...)` test fixtures with plain dicts.

- [ ] **Step 9.5: Run lint**

Run: `cd /home/al/git/kubani && just lint`

Expected: Clean. Fix any unused import warnings.

- [ ] **Step 9.6: Commit**

```bash
git add kubani/agents/_base/ tests/unit/agents/
git commit -m "refactor(agents): update legacy agent imports to new skills modules

Update KubaniAgent and SkillsOrchestrator to use the new
catalog/policies modules instead of deleted integration.py and
framework/mcp/skills.py. Legacy _load_skills returns empty list
with a deprecation warning.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: Verification + Final Cleanup

### Task 10: Full verification

**Why:** Confirm everything works end-to-end after all changes.

- [ ] **Step 10.1: Run full test suite**

Run: `cd /home/al/git/kubani && just test-unit`

Expected: All tests pass. Common failure modes and fixes:
- `ImportError: cannot import name 'KubaniSkill'` → find the import, replace with dict
- `ImportError: cannot import name 'get_discovery'` → missed reference in server.py
- Test assertions on tool count (e.g., "expected 7 tools, got 4") → update the assertion

- [ ] **Step 10.2: Run lint**

Run: `cd /home/al/git/kubani && just lint`

Expected: Clean.

- [ ] **Step 10.3: Run MCP server tests specifically**

Run: `cd /home/al/git/kubani && uv run pytest kubani/mcp/servers/skills/tests/ -v`

Expected: `test_executor.py` passes. `test_integration.py` may need updates if it tests discovery tools.

- [ ] **Step 10.4: Verify the XML catalog with real skills**

```bash
cd /home/al/git/kubani
uv run python -c "
from kubani.framework.skills import (
    build_catalog_xml, filter_skills,
    find_skills_root, load_skills_from_filesystem,
)

skills = load_skills_from_filesystem(find_skills_root())
print(f'Total skills loaded: {len(skills)}')

for policy in ('nexus', 'nexus-proactive', 'nexus-computer'):
    filtered = filter_skills(skills, policy)
    xml = build_catalog_xml(filtered)
    print(f'{policy}: {len(filtered)} skills, {len(xml)} chars')
"
```

Expected output like:
```
Total skills loaded: 48
nexus: 46 skills, ~7700 chars
nexus-proactive: ~12 skills, ~2000 chars
nexus-computer: 46 skills, ~7700 chars
```

- [ ] **Step 10.5: Verify load_skill finds real skills**

```bash
cd /home/al/git/kubani
uv run python -c "
from kubani.nexus.tools.skill_tools import _load_skill_impl
result = _load_skill_impl('investigate-pod-failure')
print(result[:200])
print('...')
print(f'Total length: {len(result)} chars')
"
```

Expected: Prints the first 200 chars of the investigate-pod-failure SKILL.md content.

- [ ] **Step 10.6: Search for any remaining dead references**

```bash
cd /home/al/git/kubani
grep -rn "get_discovery\|get_oci_discovery\|SkillDiscovery\|OCISkillDiscovery" \
  --include="*.py" | grep -v __pycache__ | grep -v ".pyc"

grep -rn "from kubani.framework.mcp.skills" --include="*.py" | grep -v __pycache__

grep -rn "from kubani.framework.skills.integration" --include="*.py" | grep -v __pycache__

grep -rn "list_skills\|refresh_skills" tests/ --include="*.py" | grep -v __pycache__
```

Expected: No results. If any remain, fix them.

- [ ] **Step 10.7: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix(skills): resolve remaining references to deleted modules

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 11: Update documentation

**Files:**
- Modify: `.claude/skills/skill-developer/SKILL.md` (update how skills are discovered)

- [ ] **Step 11.1: Read the current skill-developer skill**

Read `.claude/skills/skill-developer/SKILL.md` and find any references to:
- `list_skills` MCP tool
- `get_skill` MCP tool
- The Skills MCP server handling discovery
- `discovery.py` or `oci_discovery.py`

- [ ] **Step 11.2: Update references to reflect new architecture**

Replace any MCP discovery references with:
- Skills are discovered via `kubani.framework.skills.catalog.load_skills_from_filesystem()`
- XML catalog is injected into agent system prompt via `build_catalog_xml()`
- Agents call `load_skill(skill_name="...")` to load full instructions
- Execution still goes through the Skills MCP server `execute_skill` tool
- Policy filtering is defined in `kubani/framework/skills/policies.py`
- SKILL.md format is unchanged — flat `metadata.domain`/`metadata.category` schema

- [ ] **Step 11.3: Commit**

```bash
git add .claude/skills/skill-developer/SKILL.md
git commit -m "docs(skills): update skill-developer guide for new discovery system

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary

| Metric | Value |
|--------|-------|
| **Tasks** | 11 |
| **Steps** | ~55 |
| **New code** | ~120 lines (catalog.py + policies.py + skill_tools.py) |
| **New tests** | ~290 lines (test_catalog.py + test_policies.py + test_skill_tools.py) |
| **Deleted code** | ~1,063 lines |
| **Net change** | ~-653 lines |
| **Modified SKILL.md files** | 13 (frontmatter normalization) |
| **New dependencies** | 0 |
| **Commits** | ~10 |
