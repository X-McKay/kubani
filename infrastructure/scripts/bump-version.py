#!/usr/bin/env python3
"""
Semantic Version Bumping Script for Kubani Agents.

This script parses conventional commit messages and bumps version numbers
in agent pyproject.toml files.

Usage:
    python scripts/bump-version.py <agent-name> [--type patch|minor|major]
    python scripts/bump-version.py k8s-monitor --type minor
    python scripts/bump-version.py all --from-commits  # Auto-detect from git log

Commit Type to Version Bump:
    - feat: minor (0.1.0 -> 0.2.0)
    - fix, perf, refactor: patch (0.1.0 -> 0.1.1)
    - feat! or BREAKING CHANGE: major (0.1.0 -> 1.0.0)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def get_agent_pyproject(agent_name: str) -> Path:
    """Get the pyproject.toml path for an agent."""
    path = Path(f"agents/{agent_name}/pyproject.toml")
    if not path.exists():
        raise FileNotFoundError(f"Agent {agent_name} not found at {path}")
    return path


def read_version(pyproject_path: Path) -> str:
    """Read current version from pyproject.toml."""
    content = pyproject_path.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError(f"No version found in {pyproject_path}")
    return match.group(1)


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse version string into (major, minor, patch) tuple."""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_version(version: str, bump_type: str) -> str:
    """Bump version based on type."""
    major, minor, patch = parse_version(version)

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")

    return f"{major}.{minor}.{patch}"


def write_version(pyproject_path: Path, new_version: str) -> None:
    """Write new version to pyproject.toml."""
    content = pyproject_path.read_text()
    new_content = re.sub(
        r'^(version\s*=\s*")[^"]+(")',
        f"\\g<1>{new_version}\\g<2>",
        content,
        flags=re.MULTILINE,
    )
    pyproject_path.write_text(new_content)


def get_commit_messages(since_tag: str | None = None) -> list[str]:
    """Get commit messages since last tag or all commits."""
    cmd = ["git", "log", "--pretty=format:%s"]
    if since_tag:
        cmd.append(f"{since_tag}..HEAD")
    else:
        # Get commits since last version tag
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True,
                text=True,
                check=True,
            )
            last_tag = result.stdout.strip()
            cmd.append(f"{last_tag}..HEAD")
        except subprocess.CalledProcessError:
            # No tags, get all commits
            pass

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return [line.strip() for line in result.stdout.split("\n") if line.strip()]


def determine_bump_type(messages: list[str], agent_scope: str | None = None) -> str:
    """Determine bump type from conventional commit messages."""
    has_breaking = False
    has_feature = False
    has_fix = False

    # Regex for conventional commits: type(scope): description
    pattern = re.compile(r"^(\w+)(?:\(([^)]+)\))?(!)?:\s*(.+)$")

    for msg in messages:
        match = pattern.match(msg)
        if not match:
            continue

        commit_type = match.group(1)
        scope = match.group(2)
        is_breaking = match.group(3) == "!"

        # If filtering by agent scope, skip non-matching commits
        if agent_scope and scope and scope != agent_scope:
            continue

        # Check for BREAKING CHANGE in commit
        if is_breaking or "BREAKING CHANGE" in msg.upper():
            has_breaking = True

        if commit_type == "feat":
            has_feature = True
        elif commit_type in ("fix", "perf", "refactor"):
            has_fix = True

    if has_breaking:
        return "major"
    elif has_feature:
        return "minor"
    elif has_fix:
        return "patch"
    else:
        return "none"


def list_agents() -> list[str]:
    """List all available agents."""
    agents_dir = Path("agents")
    agents = []
    for path in agents_dir.iterdir():
        if path.is_dir() and (path / "pyproject.toml").exists():
            agents.append(path.name)
    return sorted(agents)


def main():
    parser = argparse.ArgumentParser(description="Bump agent versions")
    parser.add_argument(
        "agent",
        nargs="?",  # Optional when using --list
        help="Agent name to bump (or 'all' for all agents)",
    )
    parser.add_argument(
        "--type",
        choices=["patch", "minor", "major"],
        help="Version bump type (default: auto-detect from commits)",
    )
    parser.add_argument(
        "--from-commits",
        action="store_true",
        help="Auto-detect bump type from conventional commits",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_agents",
        help="List available agents and their current versions",
    )

    args = parser.parse_args()

    if args.list_agents:
        print("Available agents:")
        for agent in list_agents():
            pyproject = get_agent_pyproject(agent)
            version = read_version(pyproject)
            print(f"  {agent}: {version}")
        return 0

    # Require agent argument for non-list operations
    if not args.agent:
        parser.error(
            "agent argument is required (use 'all' for all agents, or --list to see available agents)"
        )

    # Determine which agents to bump
    if args.agent == "all":  # noqa: SIM108
        agents = list_agents()
    else:
        agents = [args.agent]

    # Get commit messages if auto-detecting
    commits = []
    if args.from_commits or not args.type:
        commits = get_commit_messages()

    results = []
    for agent in agents:
        try:
            pyproject = get_agent_pyproject(agent)
            current_version = read_version(pyproject)

            # Determine bump type
            if args.type:
                bump_type = args.type
            elif args.from_commits:
                bump_type = determine_bump_type(commits, agent_scope=agent)
            else:
                bump_type = "patch"  # Default to patch

            if bump_type == "none":
                print(f"{agent}: No relevant commits found, skipping")
                continue

            new_version = bump_version(current_version, bump_type)

            if args.dry_run:
                print(f"{agent}: {current_version} -> {new_version} ({bump_type}) [DRY RUN]")
            else:
                write_version(pyproject, new_version)
                print(f"{agent}: {current_version} -> {new_version} ({bump_type})")

            results.append((agent, current_version, new_version, bump_type))

        except Exception as e:
            print(f"Error processing {agent}: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
