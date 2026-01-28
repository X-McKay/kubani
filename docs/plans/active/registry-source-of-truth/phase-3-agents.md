# Phase 3: Agent Integration

**Duration:** ~1 week
**Prerequisites:** Phase 2 (OCI Integration & CLI) complete
**Outcome:** Agents can load skills from registry, create new skills, and participate in approval workflow

## Overview

This phase integrates the registry-first architecture into the Kubani framework so that running agents can:
1. Load skills dynamically from the registry
2. Create and propose new skills
3. Participate in the human approval workflow via Discord

---

## Task 3.1: Create Framework Registry Client

**File:** `kubani/framework/registry/__init__.py` (new directory and file)

```python
"""Registry client for the Kubani framework."""

from .client import RegistryClient, get_registry_client
from .models import ResourceInfo, VersionInfo, ResourceStatus
from .skill_loader import SkillLoader, get_skill_loader

__all__ = [
    "RegistryClient",
    "get_registry_client",
    "ResourceInfo",
    "VersionInfo",
    "ResourceStatus",
    "SkillLoader",
    "get_skill_loader",
]
```

**File:** `kubani/framework/registry/models.py`

```python
"""Data models for registry resources."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ResourceStatus(str, Enum):
    """Lifecycle status for resources."""

    DRAFT = "draft"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"


@dataclass
class VersionInfo:
    """Information about a resource version."""

    version: str
    oci_tag: str | None
    oci_digest: str | None
    status: ResourceStatus
    created_at: datetime
    created_by: str | None
    promoted_at: datetime | None = None
    promoted_by: str | None = None


@dataclass
class ResourceInfo:
    """Information about a resource."""

    id: str
    name: str
    resource_type: str  # skill, agent, syndicate
    description: str | None
    current_version: str | None
    oci_repository: str | None
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillContent:
    """Loaded skill content."""

    name: str
    version: str
    description: str
    instructions: str  # The markdown body
    domain: str
    category: str
    scripts: dict[str, str]  # filename -> content
    references: dict[str, str]  # filename -> content
    metadata: dict[str, Any]

    @property
    def skill_id(self) -> str:
        """Get the skill ID."""
        return f"{self.domain}/{self.category}/{self.name}"
```

**File:** `kubani/framework/registry/client.py`

```python
"""Async registry client for agents."""

import logging
from datetime import datetime
from typing import Literal

import httpx

from kubani.framework.config import get_config

from .models import ResourceInfo, ResourceStatus, VersionInfo

logger = logging.getLogger(__name__)

ResourceType = Literal["skill", "agent", "syndicate"]


class RegistryClient:
    """Async client for the Kubani Registry API."""

    def __init__(self, registry_url: str | None = None, timeout: float = 30.0):
        """
        Initialize the registry client.

        Args:
            registry_url: Base URL of the registry API (default from config)
            timeout: Request timeout in seconds
        """
        config = get_config()
        self.registry_url = (registry_url or config.registry.api_url).rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _url(self, path: str) -> str:
        """Build full URL for an API path."""
        return f"{self.registry_url}/api/v1{path}"

    async def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Make an HTTP request to the registry."""
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        response = await self._client.request(
            method,
            self._url(path),
            json=json,
            params=params,
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    # -------------------------------------------------------------------------
    # Skills
    # -------------------------------------------------------------------------

    async def get_skill(
        self,
        skill_id: str,
        version: str | None = None,
        status: ResourceStatus | None = None,
    ) -> ResourceInfo | None:
        """
        Get skill metadata.

        Args:
            skill_id: Skill identifier
            version: Specific version to get
            status: Filter by status (default: production)

        Returns:
            ResourceInfo or None if not found
        """
        from urllib.parse import quote

        encoded_id = quote(skill_id, safe="")

        try:
            data = await self._request("GET", f"/skills/{encoded_id}")
            return ResourceInfo(
                id=data["id"],
                name=data["name"],
                resource_type="skill",
                description=data.get("description"),
                current_version=data.get("current_version"),
                oci_repository=data.get("oci_repository"),
                status=ResourceStatus(data.get("status", "draft")),
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                metadata=data.get("metadata", {}),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_skill_version(
        self,
        skill_id: str,
        version: str | None = None,
        status: ResourceStatus = ResourceStatus.PRODUCTION,
    ) -> VersionInfo | None:
        """Get a specific skill version."""
        from urllib.parse import quote

        encoded_id = quote(skill_id, safe="")
        params = {}
        if version:
            params["version"] = version
        else:
            params["status"] = status.value

        try:
            data = await self._request(
                "GET", f"/skills/{encoded_id}/versions/latest", params=params
            )
            return VersionInfo(
                version=data["version"],
                oci_tag=data.get("oci_tag"),
                oci_digest=data.get("oci_digest"),
                status=ResourceStatus(data.get("status", "draft")),
                created_at=datetime.fromisoformat(data["created_at"]),
                created_by=data.get("created_by"),
                promoted_at=(
                    datetime.fromisoformat(data["promoted_at"])
                    if data.get("promoted_at")
                    else None
                ),
                promoted_by=data.get("promoted_by"),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def list_skills(
        self,
        domain: str | None = None,
        category: str | None = None,
        status: ResourceStatus | None = None,
    ) -> list[ResourceInfo]:
        """List skills with optional filters."""
        params = {}
        if domain:
            params["domain"] = domain
        if category:
            params["category"] = category
        if status:
            params["status"] = status.value

        data = await self._request("GET", "/skills", params=params)
        return [
            ResourceInfo(
                id=s["id"],
                name=s["name"],
                resource_type="skill",
                description=s.get("description"),
                current_version=s.get("current_version"),
                oci_repository=s.get("oci_repository"),
                status=ResourceStatus(s.get("status", "draft")),
                created_at=datetime.fromisoformat(s["created_at"]),
                updated_at=datetime.fromisoformat(s["updated_at"]),
                metadata=s.get("metadata", {}),
            )
            for s in data
        ]

    async def create_skill(
        self,
        name: str,
        description: str | None = None,
        domain: str = "general",
        category: str = "general",
        oci_repository: str | None = None,
        created_by: str | None = None,
        metadata: dict | None = None,
    ) -> ResourceInfo:
        """Create a new skill in the registry."""
        skill_id = f"{domain}/{category}/{name}"
        payload = {
            "id": skill_id,
            "name": name,
            "description": description,
            "domain": domain,
            "category": category,
            "oci_repository": oci_repository,
            "status": "draft",
            "created_by": created_by,
            "metadata": metadata or {},
        }
        data = await self._request("POST", "/skills", json=payload)
        return ResourceInfo(
            id=data["id"],
            name=data["name"],
            resource_type="skill",
            description=data.get("description"),
            current_version=data.get("current_version"),
            oci_repository=data.get("oci_repository"),
            status=ResourceStatus(data.get("status", "draft")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )

    async def create_skill_version(
        self,
        skill_id: str,
        version: str,
        oci_tag: str,
        oci_digest: str,
        created_by: str | None = None,
        changelog: str | None = None,
    ) -> VersionInfo:
        """Create a new skill version."""
        from urllib.parse import quote

        encoded_id = quote(skill_id, safe="")
        payload = {
            "version": version,
            "oci_tag": oci_tag,
            "oci_digest": oci_digest,
            "status": "draft",
            "created_by": created_by,
            "changelog": changelog,
        }
        data = await self._request("POST", f"/skills/{encoded_id}/versions", json=payload)
        return VersionInfo(
            version=data["version"],
            oci_tag=data.get("oci_tag"),
            oci_digest=data.get("oci_digest"),
            status=ResourceStatus(data.get("status", "draft")),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
            promoted_at=None,
            promoted_by=None,
        )

    async def record_skill_outcome(
        self,
        skill_id: str,
        success: bool,
        context: dict | None = None,
    ) -> dict:
        """Record a skill execution outcome."""
        from urllib.parse import quote

        encoded_id = quote(skill_id, safe="")
        payload = {"success": success, "context": context}
        return await self._request("PUT", f"/skills/{encoded_id}/outcome", json=payload)


# Singleton instance
_registry_client: RegistryClient | None = None


def get_registry_client() -> RegistryClient:
    """Get the global registry client instance."""
    global _registry_client
    if _registry_client is None:
        _registry_client = RegistryClient()
    return _registry_client
```

**Acceptance Criteria:**
- [ ] Registry client module created
- [ ] Async HTTP client with proper context management
- [ ] All skill CRUD operations
- [ ] Proper error handling for 404s
- [ ] Configuration from unified config

---

## Task 3.2: Create Skill Loader

**File:** `kubani/framework/registry/skill_loader.py`

```python
"""Skill loader that fetches skills from the registry."""

import hashlib
import logging
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import oras.client
import yaml

from kubani.framework.config import get_config

from .client import RegistryClient, get_registry_client
from .models import ResourceStatus, SkillContent, VersionInfo

logger = logging.getLogger(__name__)


class SkillLoader:
    """
    Loads skills from the OCI registry with caching.

    Skills are cached locally to avoid repeated downloads. The cache is
    keyed by OCI digest for immutability.
    """

    def __init__(
        self,
        registry_client: RegistryClient | None = None,
        cache_dir: Path | None = None,
        oci_registry_url: str | None = None,
    ):
        """
        Initialize the skill loader.

        Args:
            registry_client: Registry client for metadata
            cache_dir: Local cache directory
            oci_registry_url: OCI registry URL
        """
        config = get_config()
        self.registry_client = registry_client or get_registry_client()
        self.cache_dir = cache_dir or Path(config.get("skill_cache_dir", "~/.kubani/skill-cache")).expanduser()
        self.oci_registry_url = oci_registry_url or config.get("oci_registry", "registry.almckay.io")

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # OCI client for pulling
        self._oci_client = oras.client.OrasClient()

    def _get_cache_path(self, digest: str) -> Path:
        """Get the cache path for a digest."""
        # Use first 12 chars of digest for directory name
        digest_short = digest.replace("sha256:", "")[:12]
        return self.cache_dir / digest_short

    def _is_cached(self, digest: str) -> bool:
        """Check if a skill is cached."""
        cache_path = self._get_cache_path(digest)
        return cache_path.exists() and (cache_path / "SKILL.md").exists()

    async def load_skill(
        self,
        skill_id: str,
        version: str | None = None,
        status: ResourceStatus = ResourceStatus.PRODUCTION,
    ) -> SkillContent | None:
        """
        Load a skill from the registry.

        Args:
            skill_id: Skill identifier (e.g., "k8s/diagnostic/investigate-pod-failure")
            version: Specific version to load
            status: If version not specified, load latest with this status

        Returns:
            SkillContent or None if not found
        """
        async with self.registry_client:
            # Get skill metadata
            skill_info = await self.registry_client.get_skill(skill_id)
            if not skill_info:
                logger.warning(f"Skill not found: {skill_id}")
                return None

            # Get version info
            version_info = await self.registry_client.get_skill_version(
                skill_id, version=version, status=status
            )
            if not version_info:
                logger.warning(f"No version found for skill {skill_id} with status {status}")
                return None

            # Check cache
            if version_info.oci_digest and self._is_cached(version_info.oci_digest):
                logger.debug(f"Loading {skill_id}:{version_info.version} from cache")
                cache_path = self._get_cache_path(version_info.oci_digest)
                return self._parse_skill_directory(cache_path, skill_info, version_info)

            # Pull from OCI registry
            logger.info(f"Pulling {skill_id}:{version_info.version} from OCI registry")
            skill_path = await self._pull_skill(skill_info, version_info)

            if skill_path is None:
                return None

            return self._parse_skill_directory(skill_path, skill_info, version_info)

    async def _pull_skill(
        self,
        skill_info: Any,
        version_info: VersionInfo,
    ) -> Path | None:
        """Pull a skill from the OCI registry."""
        if not version_info.oci_tag:
            logger.error(f"No OCI tag for skill version {version_info.version}")
            return None

        # Determine target
        repository = f"{self.oci_registry_url}/skills/{skill_info.name}"
        target = f"{repository}:{version_info.oci_tag}"

        # Create cache directory
        if version_info.oci_digest:
            cache_path = self._get_cache_path(version_info.oci_digest)
        else:
            # Fallback to version-based cache
            cache_path = self.cache_dir / skill_info.name / version_info.version

        cache_path.mkdir(parents=True, exist_ok=True)

        try:
            # Pull to temp directory first
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                self._oci_client.pull(
                    target=target,
                    outdir=str(temp_path),
                )

                # Find and extract tarball if present
                tarballs = list(temp_path.glob("*.tar.gz")) + list(temp_path.glob("*.tar"))

                if tarballs:
                    with tarfile.open(tarballs[0], "r:*") as tar:
                        tar.extractall(cache_path)
                else:
                    # Files extracted directly - move to cache
                    for item in temp_path.iterdir():
                        dest = cache_path / item.name
                        if dest.exists():
                            if dest.is_dir():
                                shutil.rmtree(dest)
                            else:
                                dest.unlink()
                        shutil.move(str(item), str(dest))

            logger.debug(f"Cached skill at {cache_path}")
            return cache_path

        except Exception as e:
            logger.error(f"Failed to pull skill from OCI: {e}")
            # Cleanup failed cache
            if cache_path.exists():
                shutil.rmtree(cache_path)
            return None

    def _parse_skill_directory(
        self,
        skill_path: Path,
        skill_info: Any,
        version_info: VersionInfo,
    ) -> SkillContent:
        """Parse a skill directory into SkillContent."""
        skill_md = skill_path / "SKILL.md"

        if not skill_md.exists():
            raise ValueError(f"SKILL.md not found in {skill_path}")

        content = skill_md.read_text()

        # Parse frontmatter
        metadata = {}
        instructions = content

        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                metadata = yaml.safe_load(parts[1]) or {}
                instructions = parts[2].strip()

        # Load scripts
        scripts = {}
        scripts_dir = skill_path / "scripts"
        if scripts_dir.exists():
            for script_file in scripts_dir.iterdir():
                if script_file.is_file():
                    scripts[script_file.name] = script_file.read_text()

        # Load references
        references = {}
        refs_dir = skill_path / "references"
        if refs_dir.exists():
            for ref_file in refs_dir.iterdir():
                if ref_file.is_file():
                    references[ref_file.name] = ref_file.read_text()

        # Extract domain/category from metadata or skill_info
        domain = metadata.get("metadata", {}).get("domain") or skill_info.metadata.get("domain", "general")
        category = metadata.get("metadata", {}).get("category") or skill_info.metadata.get("category", "general")

        return SkillContent(
            name=metadata.get("name", skill_info.name),
            version=version_info.version,
            description=metadata.get("description", skill_info.description or ""),
            instructions=instructions,
            domain=domain,
            category=category,
            scripts=scripts,
            references=references,
            metadata=metadata,
        )

    async def list_available_skills(
        self,
        domain: str | None = None,
        category: str | None = None,
        status: ResourceStatus = ResourceStatus.PRODUCTION,
    ) -> list[dict]:
        """
        List available skills from the registry.

        Returns a list of skill summaries (not full content).
        """
        async with self.registry_client:
            skills = await self.registry_client.list_skills(
                domain=domain,
                category=category,
                status=status,
            )

            return [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "current_version": s.current_version,
                    "domain": s.metadata.get("domain", "general"),
                    "category": s.metadata.get("category", "general"),
                }
                for s in skills
            ]

    def clear_cache(self, older_than_days: int | None = None):
        """
        Clear the skill cache.

        Args:
            older_than_days: Only clear items older than this many days
        """
        import time

        if older_than_days is None:
            # Clear everything
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Cleared entire skill cache")
        else:
            # Clear old items
            cutoff = time.time() - (older_than_days * 24 * 60 * 60)
            cleared = 0

            for item in self.cache_dir.iterdir():
                if item.is_dir() and item.stat().st_mtime < cutoff:
                    shutil.rmtree(item)
                    cleared += 1

            logger.info(f"Cleared {cleared} cached skills older than {older_than_days} days")


# Singleton instance
_skill_loader: SkillLoader | None = None


def get_skill_loader() -> SkillLoader:
    """Get the global skill loader instance."""
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader()
    return _skill_loader
```

**Acceptance Criteria:**
- [ ] SkillLoader class created
- [ ] Pulls from OCI registry
- [ ] Caches by digest for immutability
- [ ] Parses SKILL.md with frontmatter
- [ ] Loads scripts and references directories
- [ ] Cache management (clear old items)

---

## Task 3.3: Create Skill Publisher (for agents)

**File:** `kubani/framework/registry/skill_publisher.py`

```python
"""Skill publisher for agents to create new skills."""

import hashlib
import logging
import tarfile
import tempfile
from datetime import datetime
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
        self.oci_registry_url = oci_registry_url or config.get("oci_registry", "registry.almckay.io")
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
```

**Acceptance Criteria:**
- [ ] SkillPublisher class created
- [ ] Creates skill directory structure
- [ ] Packages as tarball
- [ ] Pushes to OCI registry
- [ ] Registers in PostgreSQL
- [ ] Returns in draft status

---

## Task 3.4: Discord Approval Workflow

**File:** `kubani/framework/registry/approval.py`

```python
"""Human approval workflow for skill promotion via Discord."""

import logging
from typing import Any

from kubani.framework.config import get_config

logger = logging.getLogger(__name__)


class ApprovalWorkflow:
    """
    Manages human approval workflow for skill promotions.

    Posts approval requests to Discord and waits for reactions.
    """

    APPROVE_EMOJI = "✅"
    REJECT_EMOJI = "❌"
    REVISION_EMOJI = "🔄"

    def __init__(self, discord_mcp_client: Any = None):
        """
        Initialize the approval workflow.

        Args:
            discord_mcp_client: MCP client for Discord operations
        """
        self.config = get_config()
        self.discord = discord_mcp_client
        self.approval_channel = self.config.get("discord.skill_approval_channel", "skill-approvals")

    async def request_approval(
        self,
        skill_name: str,
        version: str,
        created_by: str,
        description: str,
        changelog: str | None = None,
        evaluation_results: dict | None = None,
    ) -> str:
        """
        Post an approval request to Discord.

        Args:
            skill_name: Name of the skill
            version: Version to approve
            created_by: Agent or user that created it
            description: Skill description
            changelog: What changed in this version
            evaluation_results: Optional evaluation summary

        Returns:
            Message ID for tracking
        """
        if self.discord is None:
            logger.warning("Discord MCP client not configured, skipping approval request")
            return "no-discord"

        # Build embed
        embed = {
            "title": f"🆕 Skill Approval: {skill_name}:{version}",
            "description": description,
            "color": 0x5865F2,  # Discord blurple
            "fields": [
                {"name": "Created By", "value": created_by, "inline": True},
                {"name": "Version", "value": version, "inline": True},
                {"name": "Status", "value": "Pending Approval", "inline": True},
            ],
            "footer": {"text": f"React with {self.APPROVE_EMOJI} to approve, {self.REJECT_EMOJI} to reject, {self.REVISION_EMOJI} for revisions"},
        }

        if changelog:
            embed["fields"].append({"name": "Changelog", "value": changelog, "inline": False})

        if evaluation_results:
            eval_summary = f"Accuracy: {evaluation_results.get('accuracy', 'N/A')}\n"
            eval_summary += f"Tests: {evaluation_results.get('passed', 0)}/{evaluation_results.get('total', 0)}"
            embed["fields"].append({"name": "Evaluation", "value": eval_summary, "inline": False})

        # Send to Discord
        result = await self.discord.send_message_to_channel_name(
            channel_name=self.approval_channel,
            embed=embed,
        )

        message_id = result.get("id", "unknown")

        # Add reaction options
        await self.discord.add_reaction(
            channel_id=result.get("channel_id"),
            message_id=message_id,
            emoji=self.APPROVE_EMOJI,
        )
        await self.discord.add_reaction(
            channel_id=result.get("channel_id"),
            message_id=message_id,
            emoji=self.REJECT_EMOJI,
        )
        await self.discord.add_reaction(
            channel_id=result.get("channel_id"),
            message_id=message_id,
            emoji=self.REVISION_EMOJI,
        )

        logger.info(f"Posted approval request for {skill_name}:{version} (message_id: {message_id})")
        return message_id

    async def wait_for_decision(
        self,
        channel_id: str,
        message_id: str,
        timeout_seconds: int = 86400,  # 24 hours
    ) -> str:
        """
        Wait for a human decision on an approval request.

        Args:
            channel_id: Discord channel ID
            message_id: Message ID of the approval request
            timeout_seconds: How long to wait

        Returns:
            Decision: "approved", "rejected", "revision", or "timeout"
        """
        if self.discord is None:
            return "no-discord"

        result = await self.discord.await_reaction(
            channel_id=channel_id,
            message_id=message_id,
            valid_emojis=[self.APPROVE_EMOJI, self.REJECT_EMOJI, self.REVISION_EMOJI],
            timeout_seconds=timeout_seconds,
        )

        if result is None:
            return "timeout"

        emoji = result.get("emoji", {}).get("name")

        if emoji == self.APPROVE_EMOJI:
            return "approved"
        elif emoji == self.REJECT_EMOJI:
            return "rejected"
        elif emoji == self.REVISION_EMOJI:
            return "revision"
        else:
            return "unknown"

    async def update_status(
        self,
        channel_id: str,
        message_id: str,
        new_status: str,
        by_user: str | None = None,
    ):
        """Update the approval request with a new status."""
        if self.discord is None:
            return

        status_text = {
            "approved": "✅ Approved",
            "rejected": "❌ Rejected",
            "revision": "🔄 Revision Requested",
            "promoted": "🚀 Promoted to Production",
        }.get(new_status, new_status)

        reply_content = f"**Status Update:** {status_text}"
        if by_user:
            reply_content += f" by {by_user}"

        # Note: Discord MCP doesn't have edit_message, so we send a reply
        await self.discord.send_message(
            channel_id=channel_id,
            content=reply_content,
        )
```

**Acceptance Criteria:**
- [ ] ApprovalWorkflow class created
- [ ] Posts approval requests to Discord
- [ ] Adds reaction emojis
- [ ] Waits for human decision
- [ ] Updates status on decision

---

## Task 3.5: Update Skill Learner Agent

Update the existing skill learner agent to use the new registry system.

**File:** `kubani/agents/skill_learner/agent.py` (update existing)

Add new method for publishing via registry:

```python
async def propose_skill(
    self,
    name: str,
    description: str,
    instructions: str,
    domain: str,
    category: str,
    source_context: dict,
) -> dict:
    """
    Propose a new skill based on learned patterns.

    This creates the skill in draft status and optionally
    requests human approval via Discord.
    """
    from kubani.framework.registry import get_skill_loader
    from kubani.framework.registry.skill_publisher import get_skill_publisher
    from kubani.framework.registry.approval import ApprovalWorkflow

    publisher = get_skill_publisher(agent_name=self.name)

    # Publish to registry (draft status)
    skill_info, version_info = await publisher.publish_skill(
        name=name,
        description=description,
        instructions=instructions,
        domain=domain,
        category=category,
        version="0.1.0",
        metadata={
            "source": "skill-learner",
            "learned_from": source_context,
        },
        changelog="Initial version - auto-generated from learned patterns",
    )

    # Run evaluation if available
    eval_results = await self._evaluate_skill(skill_info.id, version_info.version)

    # Request human approval if evaluation passes threshold
    if eval_results and eval_results.get("accuracy", 0) >= 0.7:
        approval = ApprovalWorkflow(discord_mcp_client=self.mcp.discord)

        await approval.request_approval(
            skill_name=name,
            version=version_info.version,
            created_by=self.name,
            description=description,
            changelog="Auto-generated skill from learned patterns",
            evaluation_results=eval_results,
        )

    return {
        "skill_id": skill_info.id,
        "version": version_info.version,
        "status": version_info.status.value,
        "evaluation": eval_results,
    }
```

**Acceptance Criteria:**
- [ ] Skill learner uses new registry system
- [ ] Publishes skills in draft status
- [ ] Runs evaluation before approval request
- [ ] Requests human approval via Discord

---

## Task 3.6: Add Configuration for Registry

**File:** `config/default.yaml` (update)

```yaml
# Add registry configuration
registry:
  api_url: "https://registry-api.almckay.io"
  oci_url: "registry.almckay.io"

oci:
  registry: "registry.almckay.io"
  # Credentials via environment: KUBANI_OCI_USERNAME, KUBANI_OCI_PASSWORD

skill_cache_dir: "~/.kubani/skill-cache"

discord:
  skill_approval_channel: "skill-approvals"
```

**File:** `kubani/framework/config/config_unified.py` (update)

Add registry section to config schema:

```python
@dataclass
class RegistryConfig:
    """Registry configuration."""

    api_url: str = "https://registry-api.almckay.io"
    oci_url: str = "registry.almckay.io"


@dataclass
class KubaniConfig:
    # ... existing fields ...
    registry: RegistryConfig = field(default_factory=RegistryConfig)
```

**Acceptance Criteria:**
- [ ] Registry URLs configurable
- [ ] OCI credentials from environment
- [ ] Cache directory configurable
- [ ] Discord channel configurable

---

## Task 3.7: Integration Tests

**File:** `kubani/framework/registry/tests/test_skill_loader.py`

```python
"""Tests for the skill loader."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from kubani.framework.registry.skill_loader import SkillLoader
from kubani.framework.registry.models import ResourceInfo, ResourceStatus, VersionInfo


@pytest.fixture
def mock_registry_client():
    """Create a mock registry client."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_oci_client():
    """Create a mock OCI client."""
    return MagicMock()


@pytest.fixture
def skill_loader(mock_registry_client, mock_oci_client, tmp_path):
    """Create a skill loader with mocks."""
    loader = SkillLoader(
        registry_client=mock_registry_client,
        cache_dir=tmp_path / "cache",
        oci_registry_url="localhost:5000",
    )
    loader._oci_client = mock_oci_client
    return loader


@pytest.mark.asyncio
async def test_load_skill_from_cache(skill_loader, mock_registry_client, tmp_path):
    """Test loading a skill that's already cached."""
    # Setup cache
    cache_path = tmp_path / "cache" / "abc123def456"
    cache_path.mkdir(parents=True)
    (cache_path / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Test Skill Instructions
""")

    # Setup mock responses
    mock_registry_client.get_skill.return_value = ResourceInfo(
        id="general/general/test-skill",
        name="test-skill",
        resource_type="skill",
        description="A test skill",
        current_version="1.0.0",
        oci_repository="localhost:5000/skills/test-skill",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={"domain": "general", "category": "general"},
    )

    mock_registry_client.get_skill_version.return_value = VersionInfo(
        version="1.0.0",
        oci_tag="v1.0.0",
        oci_digest="sha256:abc123def456",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        created_by="human",
        promoted_at=datetime.now(),
        promoted_by="human",
    )

    # Load skill
    skill = await skill_loader.load_skill("test-skill")

    assert skill is not None
    assert skill.name == "test-skill"
    assert skill.description == "A test skill"
    assert "Test Skill Instructions" in skill.instructions


@pytest.mark.asyncio
async def test_load_skill_pulls_from_oci(skill_loader, mock_registry_client, mock_oci_client, tmp_path):
    """Test loading a skill that needs to be pulled."""
    # Setup mock responses
    mock_registry_client.get_skill.return_value = ResourceInfo(
        id="k8s/diagnostic/test-skill",
        name="test-skill",
        resource_type="skill",
        description="A test skill",
        current_version="1.0.0",
        oci_repository="localhost:5000/skills/test-skill",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={"domain": "k8s", "category": "diagnostic"},
    )

    mock_registry_client.get_skill_version.return_value = VersionInfo(
        version="1.0.0",
        oci_tag="v1.0.0",
        oci_digest="sha256:newdigest123",
        status=ResourceStatus.PRODUCTION,
        created_at=datetime.now(),
        created_by="human",
        promoted_at=datetime.now(),
        promoted_by="human",
    )

    # Mock OCI pull to create files
    def mock_pull(target, outdir):
        out_path = Path(outdir)
        (out_path / "SKILL.md").write_text("""---
name: test-skill
description: Pulled skill
---

# Pulled Instructions
""")

    mock_oci_client.pull.side_effect = mock_pull

    # Load skill
    skill = await skill_loader.load_skill("test-skill")

    assert skill is not None
    assert skill.name == "test-skill"
    mock_oci_client.pull.assert_called_once()


@pytest.mark.asyncio
async def test_load_skill_not_found(skill_loader, mock_registry_client):
    """Test loading a skill that doesn't exist."""
    mock_registry_client.get_skill.return_value = None

    skill = await skill_loader.load_skill("nonexistent-skill")

    assert skill is None
```

**Acceptance Criteria:**
- [ ] Unit tests for SkillLoader
- [ ] Tests for cache hits and misses
- [ ] Tests for skill not found
- [ ] Tests for SkillPublisher
- [ ] Integration tests with mock OCI

---

## Commit Checkpoints

```bash
# After Task 3.1-3.2
git add kubani/framework/registry/
git commit -m "feat(framework): add registry client and skill loader

- Add RegistryClient for async registry API access
- Add SkillLoader with OCI pull and caching
- Add data models for resources and versions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 3.3
git add kubani/framework/registry/skill_publisher.py
git commit -m "feat(framework): add skill publisher for agents

- Agents can publish new skills to registry
- Creates skill directory, packages, pushes to OCI
- Registers in PostgreSQL with draft status

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 3.4
git add kubani/framework/registry/approval.py
git commit -m "feat(framework): add Discord approval workflow

- Post approval requests to Discord
- Wait for human reaction (approve/reject/revision)
- Update status on decision

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 3.5
git add kubani/agents/skill_learner/
git commit -m "feat(agents): update skill learner to use registry

- Publish skills via new registry system
- Run evaluation before approval request
- Request human approval via Discord

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 3.6
git add config/ kubani/framework/config/
git commit -m "feat(config): add registry configuration

- Registry API and OCI URLs
- Skill cache directory
- Discord approval channel

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 3.7
git add kubani/framework/registry/tests/
git commit -m "test(framework): add registry integration tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Push
git push origin elegant-chaum
```

---

## Phase 3 Completion Checklist

- [ ] Framework registry client implemented
- [ ] Skill loader with caching working
- [ ] Skill publisher for agents working
- [ ] Discord approval workflow implemented
- [ ] Skill learner agent updated
- [ ] Configuration added
- [ ] Integration tests passing
- [ ] All changes committed and pushed
- [ ] Ready for Phase 4
