"""
Skills Integration Module

Integrates the agentskills package with Kubani's registry and metadata system.
Provides discovery, loading, and enrichment of skills in Agent Skills standard format.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class KubaniSkill:
    """
    Kubani skill with Agent Skills standard metadata + kubani extensions.
    
    This wraps the agentskills.SkillProperties with additional Kubani-specific
    metadata from the metadata.kubani namespace.
    """
    
    # Agent Skills standard fields
    name: str
    description: str
    skill_path: Path
    license: str
    compatibility: str
    
    # Kubani-specific metadata (from metadata.kubani)
    domain: str | None = None
    category: str | None = None
    requires_approval: bool = False
    confidence: float = 1.0
    mcp_servers: list[str] | None = None
    version: str = "1.0.0"
    
    def to_agentskills_properties(self):
        """Convert to agentskills.SkillProperties for use with agentskills package."""
        try:
            from agentskills import SkillProperties
            return SkillProperties(
                name=self.name,
                description=self.description,
                skill_path=str(self.skill_path),
                license=self.license,
                compatibility=self.compatibility,
            )
        except ImportError:
            logger.warning("agentskills package not installed")
            return None


def discover_kubani_skills(
    skills_root: Path,
    domain: str | None = None,
    category: str | None = None,
) -> list[KubaniSkill]:
    """
    Discover skills in Kubani skills directory.
    
    Scans for SKILL.md files and parses metadata.
    
    Args:
        skills_root: Root directory containing skills
        domain: Optional domain filter (e.g., "news", "k8s")
        category: Optional category filter (e.g., "collection", "analysis")
    
    Returns:
        List of discovered KubaniSkill objects
    """
    skills = []
    
    # Find all SKILL.md files
    skill_files = list(skills_root.rglob("SKILL.md"))
    
    for skill_file in skill_files:
        try:
            skill = parse_kubani_skill(skill_file)
            
            # Apply filters
            if domain and skill.domain != domain:
                continue
            if category and skill.category != category:
                continue
            
            skills.append(skill)
        except Exception as e:
            logger.warning(f"Failed to parse skill {skill_file}: {e}")
    
    logger.info(f"Discovered {len(skills)} skills in {skills_root}")
    return skills


def parse_kubani_skill(skill_file: Path) -> KubaniSkill:
    """
    Parse a SKILL.md file to extract metadata.
    
    Expects Agent Skills standard format with YAML frontmatter.
    
    Args:
        skill_file: Path to SKILL.md file
    
    Returns:
        KubaniSkill object
    """
    with open(skill_file, "r") as f:
        content = f.read()
    
    # Extract YAML frontmatter
    if not content.startswith("---"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    
    # Find end of frontmatter
    end_idx = content.find("---", 3)
    if end_idx == -1:
        raise ValueError("SKILL.md frontmatter not properly closed")
    
    frontmatter = content[3:end_idx].strip()
    metadata = yaml.safe_load(frontmatter)
    
    # Extract standard fields
    name = metadata.get("name")
    description = metadata.get("description", "")
    license = metadata.get("license", "MIT")
    compatibility = metadata.get("compatibility", "No dependencies")
    
    if not name:
        raise ValueError("SKILL.md must have 'name' field")
    
    # Extract Kubani-specific metadata
    kubani_meta = metadata.get("metadata", {}).get("kubani", {})
    
    skill = KubaniSkill(
        name=name,
        description=description.strip(),
        skill_path=skill_file.parent,
        license=license,
        compatibility=compatibility,
        domain=kubani_meta.get("domain"),
        category=kubani_meta.get("category"),
        requires_approval=kubani_meta.get("requires_approval", False),
        confidence=kubani_meta.get("confidence", 1.0),
        mcp_servers=kubani_meta.get("mcp_servers", []),
        version=kubani_meta.get("version", "1.0.0"),
    )
    
    return skill


def parse_kubani_metadata(skill_file: Path) -> dict[str, Any]:
    """
    Parse only the kubani metadata from a skill file.
    
    Useful for registry integration.
    
    Args:
        skill_file: Path to SKILL.md file
    
    Returns:
        Dictionary of kubani metadata
    """
    skill = parse_kubani_skill(skill_file)
    
    return {
        "domain": skill.domain,
        "category": skill.category,
        "requires_approval": skill.requires_approval,
        "confidence": skill.confidence,
        "mcp_servers": skill.mcp_servers,
        "version": skill.version,
    }


def generate_skills_catalog(skills: list[KubaniSkill]) -> str:
    """
    Generate a catalog of skills for display.
    
    Args:
        skills: List of skills
    
    Returns:
        Formatted catalog string
    """
    catalog = "# Available Skills\n\n"
    
    # Group by domain
    by_domain = {}
    for skill in skills:
        domain = skill.domain or "general"
        if domain not in by_domain:
            by_domain[domain] = []
        by_domain[domain].append(skill)
    
    for domain, domain_skills in sorted(by_domain.items()):
        catalog += f"## {domain.title()}\n\n"
        
        # Group by category within domain
        by_category = {}
        for skill in domain_skills:
            category = skill.category or "general"
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(skill)
        
        for category, cat_skills in sorted(by_category.items()):
            catalog += f"### {category.title()}\n\n"
            
            for skill in sorted(cat_skills, key=lambda s: s.name):
                catalog += f"- **{skill.name}**: {skill.description}\n"
            
            catalog += "\n"
    
    return catalog
