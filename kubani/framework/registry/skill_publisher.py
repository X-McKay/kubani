"""Skill publisher for agents to create new skills."""

import hashlib
import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import oras.client
import yaml

from kubani.framework.config import get_config

from .client import RegistryClient, get_registry_client
from .models import ResourceInfo, VersionInfo

logger = logging.getLogger(__name__)


class SkillPublisher:
    """
    Publishes new skills to the registry.

    Used by agents to propose new skills for human approval.
    """

    def __init__(
        self,
        registry_client: RegistryClient | None = None,
        oci_registry_url: str | None = None,
        agent_name: str = "unknown-agent",
    ):
        """
        Initialize the skill publisher.

        Args:
            registry_client: Registry client for metadata
            oci_registry_url: OCI registry URL
            agent_name: Name of the publishing agent
        """
        config = get_config()
        self.registry_client = registry_client or get_registry_client()
        self.oci_registry_url = oci_registry_url or "registry.almckay.io"
        self.agent_name = agent_name

        # OCI client for pushing
        self._oci_client = oras.client.OrasClient()

    async def publish_skill(
        self,
        name: str,
        description: str,
        instructions: str,
        domain: str = "general",
        category: str = "general",
        version: str = "0.1.0",
        scripts: dict[str, str] | None = None,
        references: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        changelog: str | None = None,
    ) -> tuple[ResourceInfo, VersionInfo]:
        """
        Publish a new skill to the registry.

        The skill is created in 'draft' status and requires human approval
        to be promoted to production.

        Args:
            name: Skill name
            description: Short description
            instructions: Markdown instructions (body of SKILL.md)
            domain: Skill domain (e.g., "k8s", "news")
            category: Skill category (e.g., "diagnostic", "remediation")
            version: Initial version
            scripts: Optional scripts (filename -> content)
            references: Optional references (filename -> content)
            metadata: Additional metadata
            changelog: Description of changes

        Returns:
            Tuple of (ResourceInfo, VersionInfo)
        """
        skill_id = f"{domain}/{category}/{name}"
        oci_repository = f"{self.oci_registry_url}/skills/{name}"

        # Create skill directory
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir) / name
            skill_dir.mkdir()

            # Create SKILL.md
            frontmatter = {
                "name": name,
                "description": description,
                "metadata": {
                    "domain": domain,
                    "category": category,
                    **(metadata or {}),
                },
            }

            skill_md_content = f"""---
{yaml.dump(frontmatter, default_flow_style=False)}---

{instructions}
"""
            (skill_dir / "SKILL.md").write_text(skill_md_content)

            # Create scripts directory
            if scripts:
                scripts_dir = skill_dir / "scripts"
                scripts_dir.mkdir()
                for filename, content in scripts.items():
                    (scripts_dir / filename).write_text(content)

            # Create references directory
            if references:
                refs_dir = skill_dir / "references"
                refs_dir.mkdir()
                for filename, content in references.items():
                    (refs_dir / filename).write_text(content)

            # Package as tarball
            tarball_path = Path(temp_dir) / f"{name}.tar.gz"
            with tarfile.open(tarball_path, "w:gz") as tar:
                for item in skill_dir.iterdir():
                    tar.add(item, arcname=item.name)

            # Calculate digest
            sha256 = hashlib.sha256()
            with open(tarball_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            digest = f"sha256:{sha256.hexdigest()}"

            # Push to OCI registry
            oci_tag = f"v{version}"
            target = f"{oci_repository}:{oci_tag}"

            logger.info(f"Pushing skill {name}:{version} to {target}")

            self._oci_client.push(
                files=[str(tarball_path)],
                target=target,
                manifest_annotations={
                    "org.kubani.resource.type": "skill",
                    "org.kubani.resource.name": name,
                    "org.kubani.resource.version": version,
                    "org.kubani.created.by": self.agent_name,
                },
            )

        # Register in PostgreSQL registry
        async with self.registry_client:
            # Check if skill exists
            existing = await self.registry_client.get_skill(skill_id)

            if existing:
                skill_info = existing
            else:
                # Create new skill
                skill_info = await self.registry_client.create_skill(
                    name=name,
                    description=description,
                    domain=domain,
                    category=category,
                    oci_repository=oci_repository,
                    created_by=self.agent_name,
                    metadata={"domain": domain, "category": category, **(metadata or {})},
                )

            # Create version
            version_info = await self.registry_client.create_skill_version(
                skill_id=skill_id,
                version=version,
                oci_tag=oci_tag,
                oci_digest=digest,
                created_by=self.agent_name,
                changelog=changelog,
            )

        logger.info(f"Published skill {name}:{version} (status: {version_info.status})")
        return skill_info, version_info


def get_skill_publisher(agent_name: str) -> SkillPublisher:
    """Get a skill publisher for an agent."""
    return SkillPublisher(agent_name=agent_name)
