"""
Registry Synchronization Module.

Provides automated synchronization between:
- Git repository (skills/, agents/)
- Registry service
- Deployed agents

Features:
- Bidirectional sync (Git <-> Registry)
- Automatic skill discovery and registration
- Agent heartbeat and status tracking
- Model registration from vLLM endpoints
- GitOps-driven updates
"""

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)


class SyncDirection(Enum):
    """Direction of synchronization."""

    GIT_TO_REGISTRY = "git_to_registry"
    REGISTRY_TO_GIT = "registry_to_git"
    BIDIRECTIONAL = "bidirectional"


class SyncStatus(Enum):
    """Status of a sync operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CONFLICT = "conflict"


@dataclass
class SyncResult:
    """Result of a sync operation."""

    status: SyncStatus
    direction: SyncDirection
    items_synced: int = 0
    items_failed: int = 0
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "direction": self.direction.value,
            "items_synced": self.items_synced,
            "items_failed": self.items_failed,
            "conflicts": self.conflicts,
            "errors": self.errors,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SkillManifest:
    """Manifest for a skill from Git."""

    skill_id: str
    name: str
    domain: str
    category: str
    description: str
    version: str
    path: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_skill_md(cls, path: Path) -> "SkillManifest | None":
        """Parse a SKILL.md file into a manifest."""
        try:
            content = path.read_text()

            # Extract frontmatter if present
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    description = parts[2].strip()
                else:
                    frontmatter = {}
                    description = content
            else:
                frontmatter = {}
                description = content

            # Extract path components for domain/category
            # e.g., skills/k8s/diagnostic/investigate-pod-failure/SKILL.md
            parts = path.parts
            if "skills" in parts:
                skills_idx = parts.index("skills")
                if len(parts) > skills_idx + 3:
                    domain = parts[skills_idx + 1]
                    category = parts[skills_idx + 2]
                    name = parts[skills_idx + 3]
                else:
                    domain = "general"
                    category = "action"
                    name = path.parent.name
            else:
                domain = "general"
                category = "action"
                name = path.parent.name

            skill_id = f"{domain}/{category}/{name}"

            return cls(
                skill_id=skill_id,
                name=frontmatter.get("name", name),
                domain=domain,
                category=category,
                description=description[:500],
                version=frontmatter.get("version", "1.0.0"),
                path=str(path),
                content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
                metadata=frontmatter,
            )

        except Exception as e:
            logger.warning(f"Failed to parse skill manifest: {path}: {e}")
            return None


@dataclass
class AgentManifest:
    """Manifest for an agent from Git."""

    agent_id: str
    name: str
    description: str
    version: str
    path: str
    skills: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_pyproject(cls, path: Path) -> "AgentManifest | None":
        """Parse a pyproject.toml into an agent manifest."""
        try:
            import tomllib

            content = path.read_text()
            data = tomllib.loads(content)

            project = data.get("project", {})
            name = project.get("name", path.parent.name)

            # Look for agent info file
            agent_info_path = path.parent / "src" / name.replace("-", "_") / "agent_info.py"
            skills = []
            if agent_info_path.exists():
                # Simple extraction of skills list
                info_content = agent_info_path.read_text()
                if "skills" in info_content:
                    # Would need proper parsing, simplified here
                    pass

            return cls(
                agent_id=name,
                name=project.get("name", name),
                description=project.get("description", ""),
                version=project.get("version", "0.0.0"),
                path=str(path.parent),
                skills=skills,
                metadata=data.get("tool", {}).get("kubani", {}),
            )

        except Exception as e:
            logger.warning(f"Failed to parse agent manifest: {path}: {e}")
            return None


class SkillScanner:
    """Scans Git repository for skills."""

    def __init__(self, repo_root: str | Path):
        """Initialize the scanner."""
        self.repo_root = Path(repo_root)
        self.skills_dir = self.repo_root / "skills"

    def scan_skills(self) -> list[SkillManifest]:
        """Scan for all skills in the repository."""
        skills = []

        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return skills

        for skill_md in self.skills_dir.rglob("SKILL.md"):
            manifest = SkillManifest.from_skill_md(skill_md)
            if manifest:
                skills.append(manifest)

        logger.info(f"Found {len(skills)} skills in repository")
        return skills

    def scan_agents(self) -> list[AgentManifest]:
        """Scan for all agents in the repository."""
        agents = []
        agents_dir = self.repo_root / "agents"

        if not agents_dir.exists():
            logger.warning(f"Agents directory not found: {agents_dir}")
            return agents

        for pyproject in agents_dir.rglob("pyproject.toml"):
            manifest = AgentManifest.from_pyproject(pyproject)
            if manifest:
                agents.append(manifest)

        logger.info(f"Found {len(agents)} agents in repository")
        return agents


class RegistryClient:
    """Client for the registry service."""

    def __init__(self, registry_url: str):
        """Initialize the client."""
        self.registry_url = registry_url.rstrip("/")

    async def get_skills(self) -> list[dict[str, Any]]:
        """Get all skills from registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.registry_url}/api/v1/skills",
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Failed to get skills from registry: {e}")
        return []

    async def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Get a specific skill from registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.registry_url}/api/v1/skills/{skill_id}",
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.warning(f"Failed to get skill {skill_id}: {e}")
        return None

    async def register_skill(self, manifest: SkillManifest) -> bool:
        """Register a skill in the registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.registry_url}/api/v1/skills",
                    json={
                        "skill_id": manifest.skill_id,
                        "name": manifest.name,
                        "domain": manifest.domain,
                        "category": manifest.category,
                        "description": manifest.description,
                        "version": manifest.version,
                        "metadata": manifest.metadata,
                    },
                    timeout=30.0,
                )
                return response.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Failed to register skill {manifest.skill_id}: {e}")
        return False

    async def update_skill(self, manifest: SkillManifest) -> bool:
        """Update a skill in the registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.registry_url}/api/v1/skills/{manifest.skill_id}",
                    json={
                        "name": manifest.name,
                        "description": manifest.description,
                        "version": manifest.version,
                        "metadata": manifest.metadata,
                    },
                    timeout=30.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to update skill {manifest.skill_id}: {e}")
        return False

    async def get_agents(self) -> list[dict[str, Any]]:
        """Get all agents from registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.registry_url}/api/v1/agents",
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Failed to get agents from registry: {e}")
        return []

    async def register_agent(self, manifest: AgentManifest) -> bool:
        """Register an agent in the registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.registry_url}/api/v1/agents",
                    json={
                        "agent_id": manifest.agent_id,
                        "name": manifest.name,
                        "description": manifest.description,
                        "version": manifest.version,
                        "skills": manifest.skills,
                        "metadata": manifest.metadata,
                    },
                    timeout=30.0,
                )
                return response.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Failed to register agent {manifest.agent_id}: {e}")
        return False

    async def get_models(self) -> list[dict[str, Any]]:
        """Get all models from registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.registry_url}/api/v1/models",
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Failed to get models from registry: {e}")
        return []

    async def register_model(self, model_data: dict[str, Any]) -> bool:
        """Register a model in the registry."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.registry_url}/api/v1/models",
                    json=model_data,
                    timeout=30.0,
                )
                return response.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Failed to register model: {e}")
        return False


class ModelDiscovery:
    """Discovers models from vLLM endpoints."""

    def __init__(self, vllm_urls: list[str] | None = None):
        """Initialize model discovery."""
        self.vllm_urls = vllm_urls or [
            os.environ.get("VLLM_API_URL", "http://localhost:8000/v1"),
        ]

    async def discover_models(self) -> list[dict[str, Any]]:
        """Discover models from vLLM endpoints."""
        models = []

        for url in self.vllm_urls:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{url}/models",
                        timeout=30.0,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        for model in data.get("data", []):
                            models.append({
                                "model_id": model.get("id"),
                                "name": model.get("id"),
                                "endpoint": url,
                                "type": "vllm",
                                "metadata": model,
                            })
            except Exception as e:
                logger.warning(f"Failed to discover models from {url}: {e}")

        return models


class RegistrySynchronizer:
    """
    Synchronizes Git repository with registry.

    Supports:
    - Git -> Registry (push local changes)
    - Registry -> Git (pull approved changes)
    - Bidirectional (merge both)
    """

    def __init__(
        self,
        repo_root: str | Path,
        registry_url: str,
        vllm_urls: list[str] | None = None,
    ):
        """Initialize the synchronizer."""
        self.scanner = SkillScanner(repo_root)
        self.registry = RegistryClient(registry_url)
        self.model_discovery = ModelDiscovery(vllm_urls)
        self.repo_root = Path(repo_root)

    async def sync_skills_to_registry(self) -> SyncResult:
        """Sync skills from Git to registry."""
        result = SyncResult(
            status=SyncStatus.IN_PROGRESS,
            direction=SyncDirection.GIT_TO_REGISTRY,
        )

        try:
            # Scan local skills
            local_skills = self.scanner.scan_skills()

            # Get registry skills
            registry_skills = await self.registry.get_skills()
            registry_ids = {s.get("skill_id") for s in registry_skills}

            for skill in local_skills:
                if skill.skill_id in registry_ids:
                    # Update existing
                    if await self.registry.update_skill(skill):
                        result.items_synced += 1
                    else:
                        result.items_failed += 1
                        result.errors.append(f"Failed to update: {skill.skill_id}")
                else:
                    # Register new
                    if await self.registry.register_skill(skill):
                        result.items_synced += 1
                    else:
                        result.items_failed += 1
                        result.errors.append(f"Failed to register: {skill.skill_id}")

            result.status = SyncStatus.SUCCESS if result.items_failed == 0 else SyncStatus.FAILED

        except Exception as e:
            result.status = SyncStatus.FAILED
            result.errors.append(str(e))

        return result

    async def sync_agents_to_registry(self) -> SyncResult:
        """Sync agents from Git to registry."""
        result = SyncResult(
            status=SyncStatus.IN_PROGRESS,
            direction=SyncDirection.GIT_TO_REGISTRY,
        )

        try:
            local_agents = self.scanner.scan_agents()
            registry_agents = await self.registry.get_agents()
            registry_ids = {a.get("agent_id") for a in registry_agents}

            for agent in local_agents:
                if agent.agent_id not in registry_ids:
                    if await self.registry.register_agent(agent):
                        result.items_synced += 1
                    else:
                        result.items_failed += 1
                        result.errors.append(f"Failed to register: {agent.agent_id}")

            result.status = SyncStatus.SUCCESS if result.items_failed == 0 else SyncStatus.FAILED

        except Exception as e:
            result.status = SyncStatus.FAILED
            result.errors.append(str(e))

        return result

    async def sync_models_to_registry(self) -> SyncResult:
        """Discover and sync models to registry."""
        result = SyncResult(
            status=SyncStatus.IN_PROGRESS,
            direction=SyncDirection.GIT_TO_REGISTRY,
        )

        try:
            models = await self.model_discovery.discover_models()
            registry_models = await self.registry.get_models()
            registry_ids = {m.get("model_id") for m in registry_models}

            for model in models:
                if model["model_id"] not in registry_ids:
                    if await self.registry.register_model(model):
                        result.items_synced += 1
                    else:
                        result.items_failed += 1

            result.status = SyncStatus.SUCCESS if result.items_failed == 0 else SyncStatus.FAILED

        except Exception as e:
            result.status = SyncStatus.FAILED
            result.errors.append(str(e))

        return result

    async def sync_from_registry(self) -> SyncResult:
        """
        Sync approved changes from registry back to Git.

        This handles skills/agents that were approved via UI and need
        to be committed back to the repository.
        """
        result = SyncResult(
            status=SyncStatus.IN_PROGRESS,
            direction=SyncDirection.REGISTRY_TO_GIT,
        )

        try:
            # Get skills marked for sync
            registry_skills = await self.registry.get_skills()

            for skill in registry_skills:
                if skill.get("metadata", {}).get("pending_git_sync"):
                    # Write skill to Git
                    skill_path = self._get_skill_path(skill)
                    if await self._write_skill_to_git(skill, skill_path):
                        result.items_synced += 1
                    else:
                        result.items_failed += 1

            result.status = SyncStatus.SUCCESS if result.items_failed == 0 else SyncStatus.FAILED

        except Exception as e:
            result.status = SyncStatus.FAILED
            result.errors.append(str(e))

        return result

    def _get_skill_path(self, skill: dict[str, Any]) -> Path:
        """Get the path for a skill in the repository."""
        domain = skill.get("domain", "general")
        category = skill.get("category", "action")
        name = skill.get("skill_id", "").split("/")[-1]
        return self.repo_root / "skills" / domain / category / name / "SKILL.md"

    async def _write_skill_to_git(self, skill: dict[str, Any], path: Path) -> bool:
        """Write a skill to the Git repository."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            # Format as SKILL.md
            content = f"""---
name: {skill.get('name', '')}
version: {skill.get('version', '1.0.0')}
---

# {skill.get('name', '')}

{skill.get('description', '')}
"""
            path.write_text(content)
            return True

        except Exception as e:
            logger.error(f"Failed to write skill to Git: {e}")
            return False

    async def full_sync(self) -> dict[str, SyncResult]:
        """Run a full bidirectional sync."""
        results = {}

        # Git -> Registry
        results["skills_to_registry"] = await self.sync_skills_to_registry()
        results["agents_to_registry"] = await self.sync_agents_to_registry()
        results["models_to_registry"] = await self.sync_models_to_registry()

        # Registry -> Git
        results["from_registry"] = await self.sync_from_registry()

        return results
