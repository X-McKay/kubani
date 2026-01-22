#!/usr/bin/env python3
"""
Changelog Generation Script for Kubani Agents.

Parses conventional commits and generates a changelog in Keep a Changelog format.
https://keepachangelog.com/

Usage:
    python scripts/generate-changelog.py [--output CHANGELOG.md] [--since v0.1.0]

Output format:
    ## [0.2.0] - 2026-01-07

    ### Added
    - feat(k8s-monitor): Add node diagnostician agent (#123)

    ### Fixed
    - fix(core): Correct skill confidence scoring (#124)

    ### Changed
    - refactor(k8s-monitor): Improve agent communication patterns

    ### Breaking Changes
    - feat!: Rename Event Bus API methods
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


def get_git_tags() -> list[str]:
    """Get all git tags sorted by version."""
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [tag.strip() for tag in result.stdout.split("\n") if tag.strip()]
    except subprocess.CalledProcessError:
        return []


def get_commits_between(from_ref: str | None, to_ref: str = "HEAD") -> list[dict]:
    """Get commits between two refs."""
    cmd = ["git", "log", "--pretty=format:%H|%s|%b|%ae|%ad", "--date=short"]
    if from_ref:
        cmd.append(f"{from_ref}..{to_ref}")
    else:
        cmd.append(to_ref)

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    commits = []
    for line in result.stdout.split("\n"):
        if not line.strip():
            continue

        parts = line.split("|", 4)
        if len(parts) >= 4:
            commits.append(
                {
                    "hash": parts[0][:7],
                    "subject": parts[1],
                    "body": parts[2] if len(parts) > 2 else "",
                    "author": parts[3] if len(parts) > 3 else "",
                    "date": parts[4] if len(parts) > 4 else "",
                }
            )

    return commits


def parse_conventional_commit(subject: str, body: str = "") -> dict | None:
    """Parse a conventional commit message."""
    # Pattern: type(scope)!: description or type!: description
    pattern = re.compile(r"^(\w+)(?:\(([^)]+)\))?(!)?:\s*(.+)$")
    match = pattern.match(subject)

    if not match:
        return None

    commit_type = match.group(1)
    scope = match.group(2)
    is_breaking = match.group(3) == "!" or "BREAKING CHANGE" in body.upper()
    description = match.group(4)

    # Extract PR/issue references
    refs = re.findall(r"#(\d+)", subject + " " + body)

    return {
        "type": commit_type,
        "scope": scope,
        "breaking": is_breaking,
        "description": description,
        "refs": refs,
    }


# Type mapping to changelog sections
TYPE_TO_SECTION = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Performance",
    "refactor": "Changed",
    "docs": "Documentation",
    "test": "Testing",
    "style": "Style",
    "chore": "Maintenance",
    "ci": "CI/CD",
    "build": "Build",
    "revert": "Reverted",
}


def group_commits_by_section(commits: list[dict]) -> dict[str, list[dict]]:
    """Group parsed commits by changelog section."""
    sections = defaultdict(list)

    for commit in commits:
        parsed = parse_conventional_commit(commit["subject"], commit.get("body", ""))
        if not parsed:
            continue

        if parsed["breaking"]:
            sections["Breaking Changes"].append({**parsed, "hash": commit["hash"]})

        section = TYPE_TO_SECTION.get(parsed["type"], "Other")
        sections[section].append({**parsed, "hash": commit["hash"]})

    return dict(sections)


def format_commit_entry(commit: dict) -> str:
    """Format a single commit as a changelog entry."""
    scope = f"**{commit['scope']}**: " if commit.get("scope") else ""
    refs = " ".join(f"(#{ref})" for ref in commit.get("refs", []))
    refs_str = f" {refs}" if refs else ""

    return f"- {scope}{commit['description']}{refs_str}"


def generate_changelog_section(
    version: str,
    release_date: str,
    sections: dict[str, list[dict]],
) -> str:
    """Generate a changelog section for a version."""
    lines = [f"## [{version}] - {release_date}", ""]

    # Section ordering
    section_order = [
        "Breaking Changes",
        "Added",
        "Fixed",
        "Performance",
        "Changed",
        "Documentation",
        "Maintenance",
        "CI/CD",
    ]

    for section_name in section_order:
        if section_name not in sections:
            continue

        commits = sections[section_name]
        if not commits:
            continue

        lines.append(f"### {section_name}")
        for commit in commits:
            lines.append(format_commit_entry(commit))
        lines.append("")

    return "\n".join(lines)


def read_existing_changelog(path: Path) -> str:
    """Read existing changelog if it exists."""
    if path.exists():
        return path.read_text()
    return ""


def merge_changelog(existing: str, new_section: str) -> str:
    """Merge new section into existing changelog."""
    header = """# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

"""

    if not existing.strip():
        return header + new_section

    # Find where to insert (after header, before first version)
    lines = existing.split("\n")
    insert_index = 0

    for i, line in enumerate(lines):
        if line.startswith("## ["):
            insert_index = i
            break
        insert_index = i + 1

    # Insert new section
    lines.insert(insert_index, new_section)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate changelog from commits")
    parser.add_argument(
        "--output",
        "-o",
        default="CHANGELOG.md",
        help="Output file path (default: CHANGELOG.md)",
    )
    parser.add_argument(
        "--since",
        help="Generate changelog since this tag (default: last tag)",
    )
    parser.add_argument(
        "--version",
        help="Version for this release (default: Unreleased)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print changelog without writing to file",
    )

    args = parser.parse_args()

    # Determine starting point
    since_tag = args.since
    if not since_tag:
        tags = get_git_tags()
        since_tag = tags[0] if tags else None

    # Get commits
    commits = get_commits_between(since_tag)
    if not commits:
        print("No commits found since last tag")
        return 0

    # Group by section
    sections = group_commits_by_section(commits)
    if not sections:
        print("No conventional commits found")
        return 0

    # Generate changelog section
    version = args.version or "Unreleased"
    release_date = date.today().isoformat()
    new_section = generate_changelog_section(version, release_date, sections)

    if args.dry_run:
        print(new_section)
        return 0

    # Read and merge with existing
    output_path = Path(args.output)
    existing = read_existing_changelog(output_path)
    final = merge_changelog(existing, new_section)

    # Write
    output_path.write_text(final)
    print(f"Changelog updated: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
