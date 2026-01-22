"""Migrate existing .claude/skills to new skill system."""

import logging
import shutil
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Skills that should remain in .claude/skills as documentation/guidance
DOCUMENTATION_SKILLS = {
    "architecture",
    "code-patterns",
    "local-development",
    "mcp-servers",
    "testing",
}

# Skills that are meta (help create other skills) - keep in .claude/skills
META_SKILLS = {
    "skill-developer",
    "mcp-builder",
}

# Skills to migrate to new system
EXECUTABLE_SKILLS = {
    "add-node",
    "agent-evaluation",
    "agents",
    "bootstrap-node",
    "bump-version",
    "cluster-status",
    "continuous-learning",
    "deployment",
    "new-agent",
    "rollback",
    "troubleshoot",
    "validate",
}


def should_migrate_skill(skill_name: str) -> bool:
    """Determine if a skill should be migrated to the new system."""
    return skill_name in EXECUTABLE_SKILLS


def should_keep_skill(skill_name: str) -> bool:
    """Determine if a skill should remain in .claude/skills."""
    return skill_name in DOCUMENTATION_SKILLS or skill_name in META_SKILLS


def migrate_skill(skill_path: Path, target_dir: Path, dry_run: bool = False) -> Tuple[bool, str]:
    """
    Migrate a skill from .claude/skills to the new system.

    Args:
        skill_path: Path to the skill in .claude/skills
        target_dir: Target directory (skills/core or skills/agents/...)
        dry_run: If True, don't actually move files

    Returns:
        (success, message)
    """
    skill_name = skill_path.name

    # Check if skill has required files
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "Missing SKILL.md"

    # Create target directory
    target_skill_dir = target_dir / skill_name / "v1.0.0"

    if target_skill_dir.exists():
        return False, f"Already exists at {target_skill_dir}"

    if dry_run:
        return True, f"Would migrate to {target_skill_dir}"

    try:
        target_skill_dir.mkdir(parents=True, exist_ok=True)

        # Copy SKILL.md
        shutil.copy2(skill_md, target_skill_dir / "SKILL.md")

        # Create stub skill.py if it doesn't exist
        skill_py = skill_path / "skill.py"
        if skill_py.exists():
            shutil.copy2(skill_py, target_skill_dir / "skill.py")
        else:
            # Create a stub
            stub_content = '''"""Skill implementation."""

def execute(inputs: dict) -> dict:
    """
    Execute the skill.
    
    Args:
        inputs: Input parameters
    
    Returns:
        Output results
    """
    # TODO: Implement skill logic
    return {
        "status": "not_implemented",
        "message": "This skill needs to be implemented"
    }
'''
            (target_skill_dir / "skill.py").write_text(stub_content)

        # Create stub test_cases.yaml
        test_cases_yaml = skill_path / "test_cases.yaml"
        if test_cases_yaml.exists():
            shutil.copy2(test_cases_yaml, target_skill_dir / "test_cases.yaml")
        else:
            # Create a stub
            stub_test = """# Test cases for this skill
# Add test cases as you implement the skill

test_cases:
  - name: basic_test
    description: Basic functionality test
    inputs:
      # Add inputs here
    expected_outputs:
      status: success
    assertions:
      - field: status
        type: equals
        value: success
"""
            (target_skill_dir / "test_cases.yaml").write_text(stub_test)

        return True, f"Migrated to {target_skill_dir}"

    except Exception as e:
        logger.exception(f"Failed to migrate {skill_name}")
        return False, f"Error: {e}"


def migrate_all_skills(project_root: Path, dry_run: bool = False) -> List[Tuple[str, bool, str]]:
    """
    Migrate all eligible skills.

    Args:
        project_root: Project root directory
        dry_run: If True, don't actually move files

    Returns:
        List of (skill_name, success, message) tuples
    """
    claude_skills_dir = project_root / ".claude" / "skills"
    results = []

    if not claude_skills_dir.exists():
        return results

    for skill_path in claude_skills_dir.iterdir():
        if not skill_path.is_dir():
            continue

        skill_name = skill_path.name

        # Skip development directory (it's a symlink)
        if skill_name == "development":
            continue

        # Skip skills that should stay
        if should_keep_skill(skill_name):
            results.append((skill_name, True, "Kept as documentation/meta skill"))
            continue

        # Skip skills not in migration list
        if not should_migrate_skill(skill_name):
            results.append((skill_name, False, "Not in migration list - manual review needed"))
            continue

        # Migrate to core skills
        target_dir = project_root / "skills" / "core"
        success, message = migrate_skill(skill_path, target_dir, dry_run)
        results.append((skill_name, success, message))

    return results


def main():
    """CLI entry point for migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate .claude/skills to new system")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without doing it"
    )
    parser.add_argument(
        "--project-root", type=Path, default=Path.cwd(), help="Project root directory"
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    logger.info("Skill Migration Tool")
    logger.info("=" * 60)
    logger.info("")

    if args.dry_run:
        logger.info("DRY RUN MODE - No files will be moved")
        logger.info("")

    results = migrate_all_skills(args.project_root, args.dry_run)

    logger.info("Migration Results:")
    logger.info("-" * 60)

    for skill_name, success, message in results:
        status = "✓" if success else "✗"
        logger.info(f"{status} {skill_name:30s} {message}")

    logger.info("")
    logger.info(f"Total: {len(results)} skills processed")
    success_count = sum(1 for _, success, _ in results if success)
    logger.info(f"Success: {success_count}")
    logger.info(f"Failed: {len(results) - success_count}")


if __name__ == "__main__":
    main()
