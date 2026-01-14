"""
Skills loader for cluster-monitor.

Loads diagnostic and remediation skills from the skills directory.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_skills_directory() -> Path:
    """Get the skills directory path."""
    # Assume skills are in the repository root
    repo_root = Path(__file__).parents[5]  # Go up from src/cluster_monitor/
    skills_dir = repo_root / "skills" / "k8s"
    
    if not skills_dir.exists():
        logger.warning(f"Skills directory not found at {skills_dir}")
        # Try alternative path
        skills_dir = Path("/home/ubuntu/kubani/skills/k8s")
    
    return skills_dir


def load_diagnostic_skills() -> list[dict[str, Any]]:
    """
    Load diagnostic skills.
    
    Returns:
        List of skill metadata dictionaries
    """
    skills = []
    skills_dir = get_skills_directory() / "diagnostic"
    
    if not skills_dir.exists():
        logger.warning(f"Diagnostic skills directory not found: {skills_dir}")
        return skills
    
    # Find all SKILL.md files
    for skill_file in skills_dir.rglob("SKILL.md"):
        try:
            skill_name = skill_file.parent.name
            skills.append({
                "name": skill_name,
                "path": str(skill_file),
                "category": "diagnostic",
            })
            logger.debug(f"Loaded diagnostic skill: {skill_name}")
        except Exception as e:
            logger.warning(f"Failed to load skill from {skill_file}: {e}")
    
    logger.info(f"Loaded {len(skills)} diagnostic skills")
    return skills


def load_remediation_skills() -> list[dict[str, Any]]:
    """
    Load remediation skills.
    
    Returns:
        List of skill metadata dictionaries
    """
    skills = []
    skills_dir = get_skills_directory() / "remediation"
    
    if not skills_dir.exists():
        logger.warning(f"Remediation skills directory not found: {skills_dir}")
        return skills
    
    # Find all SKILL.md files
    for skill_file in skills_dir.rglob("SKILL.md"):
        try:
            skill_name = skill_file.parent.name
            skills.append({
                "name": skill_name,
                "path": str(skill_file),
                "category": "remediation",
            })
            logger.debug(f"Loaded remediation skill: {skill_name}")
        except Exception as e:
            logger.warning(f"Failed to load skill from {skill_file}: {e}")
    
    logger.info(f"Loaded {len(skills)} remediation skills")
    return skills


def get_skill_for_pattern(pattern: str) -> dict[str, Any] | None:
    """
    Get the most appropriate skill for a given pattern.
    
    Args:
        pattern: Issue pattern (e.g., "timeout", "oom", "network")
        
    Returns:
        Skill metadata or None
    """
    diagnostic_skills = load_diagnostic_skills()
    
    # Map patterns to skills
    pattern_skill_map = {
        "timeout": "diagnose-network-issue",
        "connection_error": "diagnose-network-issue",
        "network": "diagnose-network-issue",
        "oom": "check-pod-resources",
        "memory": "check-pod-resources",
        "cpu": "check-pod-resources",
        "disk": "diagnose-storage-issue",
        "storage": "diagnose-storage-issue",
    }
    
    skill_name = pattern_skill_map.get(pattern)
    if skill_name:
        for skill in diagnostic_skills:
            if skill["name"] == skill_name:
                return skill
    
    # Return first available skill as fallback
    return diagnostic_skills[0] if diagnostic_skills else None
