# Phase 2: OCI Integration & CLI

**Duration:** ~1.5 weeks
**Prerequisites:** Phase 1 (Schema Migration) complete
**Outcome:** OCI client working, CLI commands for pull/push/promote

## Overview

This phase implements the OCI registry integration using `oras-py` and updates the `kubani` CLI with new commands for the registry-first workflow.

---

## Task 2.1: Add oras-py Dependency

### 2.1.1 Update pyproject.toml

**File:** `platform/cli/pyproject.toml`

```toml
[project]
dependencies = [
    # ... existing dependencies
    "oras>=0.2.0",  # OCI Registry As Storage client
]
```

### 2.1.2 Install and Verify

```bash
cd platform/cli
uv pip install -e .

# Verify oras is importable
python -c "import oras.client; print('oras-py installed successfully')"
```

**Acceptance Criteria:**
- [ ] oras-py added to dependencies
- [ ] Package installs without errors
- [ ] Import works

---

## Task 2.2: Create OCI Client Wrapper

**File:** `platform/cli/src/kubani_dev/oci.py`

```python
"""OCI Registry client for Kubani resources."""

import hashlib
import logging
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import oras.client

logger = logging.getLogger(__name__)

ResourceType = Literal["skill", "agent", "syndicate"]


@dataclass
class OCIPushResult:
    """Result of pushing to OCI registry."""

    repository: str
    tag: str
    digest: str
    size_bytes: int


@dataclass
class OCIPullResult:
    """Result of pulling from OCI registry."""

    repository: str
    tag: str
    digest: str
    extracted_path: Path


class KubaniOCIClient:
    """Client for pushing/pulling Kubani resources to/from OCI registry."""

    # Media types for Kubani resources
    MEDIA_TYPES = {
        "skill": "application/vnd.kubani.skill.v1+tar",
        "agent": "application/vnd.kubani.agent.v1+tar",
        "syndicate": "application/vnd.kubani.syndicate.v1+tar",
    }

    def __init__(
        self,
        registry_url: str = "registry.almckay.io",
        username: str | None = None,
        password: str | None = None,
        insecure: bool = False,
    ):
        """
        Initialize the OCI client.

        Args:
            registry_url: Base URL of the OCI registry
            username: Registry username (or from KUBANI_OCI_USERNAME env)
            password: Registry password (or from KUBANI_OCI_PASSWORD env)
            insecure: Allow insecure connections (for local testing)
        """
        self.registry_url = registry_url.rstrip("/")
        self.username = username or os.environ.get("KUBANI_OCI_USERNAME")
        self.password = password or os.environ.get("KUBANI_OCI_PASSWORD")
        self.insecure = insecure

        self._client = oras.client.OrasClient(insecure=insecure)

        # Login if credentials provided
        if self.username and self.password:
            self._client.login(
                hostname=self.registry_url,
                username=self.username,
                password=self.password,
            )

    def _get_repository(self, resource_type: ResourceType, name: str) -> str:
        """Get the full repository path for a resource."""
        return f"{self.registry_url}/{resource_type}s/{name}"

    def _package_directory(self, source_dir: Path, resource_type: ResourceType) -> Path:
        """
        Package a directory as a tarball.

        Args:
            source_dir: Directory to package
            resource_type: Type of resource (for media type)

        Returns:
            Path to the created tarball
        """
        tarball_path = Path(tempfile.mktemp(suffix=".tar.gz"))

        with tarfile.open(tarball_path, "w:gz") as tar:
            # Add all files in the directory
            for item in source_dir.iterdir():
                tar.add(item, arcname=item.name)

        logger.debug(f"Packaged {source_dir} to {tarball_path}")
        return tarball_path

    def _calculate_digest(self, file_path: Path) -> str:
        """Calculate SHA256 digest of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"

    def push(
        self,
        source_dir: Path,
        resource_type: ResourceType,
        name: str,
        tag: str,
    ) -> OCIPushResult:
        """
        Push a resource directory to the OCI registry.

        Args:
            source_dir: Directory containing the resource files
            resource_type: Type of resource (skill, agent, syndicate)
            name: Name of the resource
            tag: Version tag (e.g., "v1.0.0")

        Returns:
            OCIPushResult with repository, tag, digest, and size
        """
        if not source_dir.is_dir():
            raise ValueError(f"Source must be a directory: {source_dir}")

        # Package as tarball
        tarball = self._package_directory(source_dir, resource_type)

        try:
            repository = self._get_repository(resource_type, name)
            target = f"{repository}:{tag}"

            logger.info(f"Pushing {source_dir} to {target}")

            # Push using oras
            self._client.push(
                files=[str(tarball)],
                target=target,
                manifest_annotations={
                    "org.kubani.resource.type": resource_type,
                    "org.kubani.resource.name": name,
                    "org.kubani.resource.version": tag,
                },
            )

            # Calculate digest for return
            digest = self._calculate_digest(tarball)
            size_bytes = tarball.stat().st_size

            return OCIPushResult(
                repository=repository,
                tag=tag,
                digest=digest,
                size_bytes=size_bytes,
            )

        finally:
            # Cleanup tarball
            tarball.unlink(missing_ok=True)

    def pull(
        self,
        resource_type: ResourceType,
        name: str,
        tag: str,
        dest_dir: Path,
    ) -> OCIPullResult:
        """
        Pull a resource from the OCI registry.

        Args:
            resource_type: Type of resource (skill, agent, syndicate)
            name: Name of the resource
            tag: Version tag (e.g., "v1.0.0")
            dest_dir: Directory to extract the resource to

        Returns:
            OCIPullResult with repository, tag, digest, and extracted path
        """
        repository = self._get_repository(resource_type, name)
        target = f"{repository}:{tag}"

        logger.info(f"Pulling {target} to {dest_dir}")

        # Create temp directory for download
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Pull using oras
            self._client.pull(
                target=target,
                outdir=str(temp_path),
            )

            # Find the tarball (oras downloads as individual files)
            tarballs = list(temp_path.glob("*.tar.gz")) + list(temp_path.glob("*.tar"))

            if not tarballs:
                # Files may have been extracted directly
                # Move all files to destination
                dest_dir.mkdir(parents=True, exist_ok=True)
                for item in temp_path.iterdir():
                    shutil.move(str(item), str(dest_dir / item.name))
            else:
                # Extract tarball
                tarball = tarballs[0]
                dest_dir.mkdir(parents=True, exist_ok=True)
                with tarfile.open(tarball, "r:*") as tar:
                    tar.extractall(dest_dir)

        # Get manifest to retrieve digest
        manifest = self._client.remote.get_manifest(target)
        digest = manifest.get("digest", "unknown")

        return OCIPullResult(
            repository=repository,
            tag=tag,
            digest=digest,
            extracted_path=dest_dir,
        )

    def exists(self, resource_type: ResourceType, name: str, tag: str) -> bool:
        """Check if a resource exists in the registry."""
        repository = self._get_repository(resource_type, name)
        target = f"{repository}:{tag}"

        try:
            self._client.remote.get_manifest(target)
            return True
        except Exception:
            return False

    def list_tags(self, resource_type: ResourceType, name: str) -> list[str]:
        """List all tags for a resource."""
        repository = self._get_repository(resource_type, name)

        try:
            tags = self._client.remote.get_tags(repository)
            return tags.get("tags", [])
        except Exception as e:
            logger.warning(f"Failed to list tags for {repository}: {e}")
            return []

    def delete(self, resource_type: ResourceType, name: str, tag: str) -> bool:
        """
        Delete a resource tag from the registry.

        Note: This only deletes the tag, not the underlying blob (if other tags reference it).
        """
        repository = self._get_repository(resource_type, name)
        target = f"{repository}:{tag}"

        try:
            self._client.delete(target)
            return True
        except Exception as e:
            logger.error(f"Failed to delete {target}: {e}")
            return False


# Convenience function for creating a configured client
def get_oci_client() -> KubaniOCIClient:
    """Get an OCI client configured from environment."""
    from kubani_dev.config import get_config

    config = get_config()

    return KubaniOCIClient(
        registry_url=config.get("oci_registry", "registry.almckay.io"),
        username=os.environ.get("KUBANI_OCI_USERNAME"),
        password=os.environ.get("KUBANI_OCI_PASSWORD"),
    )
```

**Acceptance Criteria:**
- [ ] OCI client wrapper created
- [ ] Push packages directory as tarball and uploads
- [ ] Pull downloads and extracts to directory
- [ ] Proper error handling
- [ ] Configurable from environment

---

## Task 2.3: Create Registry API Client

**File:** `platform/cli/src/kubani_dev/registry_client.py`

```python
"""Client for the Kubani Registry API."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

ResourceType = Literal["skill", "agent", "syndicate"]
ResourceStatus = Literal["draft", "testing", "staging", "production", "deprecated"]


@dataclass
class VersionInfo:
    """Information about a resource version."""

    version: str
    oci_tag: str | None
    oci_digest: str | None
    status: ResourceStatus
    created_at: datetime
    created_by: str | None
    promoted_at: datetime | None
    promoted_by: str | None


@dataclass
class ResourceInfo:
    """Information about a resource."""

    id: str
    name: str
    description: str | None
    current_version: str | None
    oci_repository: str | None
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any]


class RegistryClient:
    """Client for interacting with the Kubani Registry API."""

    def __init__(self, registry_url: str, timeout: float = 30.0):
        """
        Initialize the registry client.

        Args:
            registry_url: Base URL of the registry API
            timeout: Request timeout in seconds
        """
        self.registry_url = registry_url.rstrip("/")
        self.timeout = timeout

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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
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

    async def get_skill(self, skill_id: str) -> ResourceInfo | None:
        """Get skill metadata by ID."""
        try:
            encoded_id = quote(skill_id, safe="")
            data = await self._request("GET", f"/skills/{encoded_id}")
            return ResourceInfo(
                id=data["id"],
                name=data["name"],
                description=data.get("description"),
                current_version=data.get("current_version"),
                oci_repository=data.get("oci_repository"),
                status=data.get("status", "draft"),
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                metadata=data.get("metadata", {}),
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
            params["status"] = status

        data = await self._request("GET", "/skills", params=params)
        return [
            ResourceInfo(
                id=s["id"],
                name=s["name"],
                description=s.get("description"),
                current_version=s.get("current_version"),
                oci_repository=s.get("oci_repository"),
                status=s.get("status", "draft"),
                created_at=datetime.fromisoformat(s["created_at"]),
                updated_at=datetime.fromisoformat(s["updated_at"]),
                metadata=s.get("metadata", {}),
            )
            for s in data
        ]

    async def create_skill(
        self,
        skill_id: str,
        name: str,
        description: str | None = None,
        domain: str | None = None,
        category: str | None = None,
        oci_repository: str | None = None,
        created_by: str | None = None,
        metadata: dict | None = None,
    ) -> ResourceInfo:
        """Create a new skill."""
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
            description=data.get("description"),
            current_version=data.get("current_version"),
            oci_repository=data.get("oci_repository"),
            status=data.get("status", "draft"),
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
            status=data.get("status", "draft"),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
            promoted_at=datetime.fromisoformat(data["promoted_at"]) if data.get("promoted_at") else None,
            promoted_by=data.get("promoted_by"),
        )

    async def get_skill_version(
        self,
        skill_id: str,
        version: str | None = None,
        status: ResourceStatus | None = None,
    ) -> VersionInfo | None:
        """
        Get a specific skill version.

        Args:
            skill_id: Skill identifier
            version: Specific version (e.g., "1.0.0")
            status: If version not specified, get latest with this status

        Returns:
            VersionInfo or None if not found
        """
        encoded_id = quote(skill_id, safe="")
        params = {}
        if version:
            params["version"] = version
        if status:
            params["status"] = status

        try:
            data = await self._request("GET", f"/skills/{encoded_id}/versions/latest", params=params)
            return VersionInfo(
                version=data["version"],
                oci_tag=data.get("oci_tag"),
                oci_digest=data.get("oci_digest"),
                status=data.get("status", "draft"),
                created_at=datetime.fromisoformat(data["created_at"]),
                created_by=data.get("created_by"),
                promoted_at=datetime.fromisoformat(data["promoted_at"]) if data.get("promoted_at") else None,
                promoted_by=data.get("promoted_by"),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def promote_skill_version(
        self,
        skill_id: str,
        version: str,
        target_status: ResourceStatus,
        promoted_by: str | None = None,
    ) -> VersionInfo:
        """Promote a skill version to a new status."""
        encoded_id = quote(skill_id, safe="")
        payload = {
            "target_status": target_status,
            "promoted_by": promoted_by,
        }
        data = await self._request("POST", f"/skills/{encoded_id}/versions/{version}/promote", json=payload)
        return VersionInfo(
            version=data["version"],
            oci_tag=data.get("oci_tag"),
            oci_digest=data.get("oci_digest"),
            status=data.get("status"),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
            promoted_at=datetime.fromisoformat(data["promoted_at"]) if data.get("promoted_at") else None,
            promoted_by=data.get("promoted_by"),
        )

    # -------------------------------------------------------------------------
    # Agents (similar pattern)
    # -------------------------------------------------------------------------

    async def get_agent(self, agent_id: str) -> ResourceInfo | None:
        """Get agent metadata by ID."""
        try:
            data = await self._request("GET", f"/agents/{agent_id}")
            return ResourceInfo(
                id=data["id"],
                name=data["name"],
                description=data.get("description"),
                current_version=data.get("current_version"),
                oci_repository=data.get("oci_repository"),
                status=data.get("status", "unknown"),
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                metadata=data.get("metadata", {}),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def create_agent_version(
        self,
        agent_id: str,
        version: str,
        oci_tag: str,
        oci_digest: str,
        created_by: str | None = None,
        changelog: str | None = None,
    ) -> VersionInfo:
        """Create a new agent version."""
        payload = {
            "version": version,
            "oci_tag": oci_tag,
            "oci_digest": oci_digest,
            "status": "draft",
            "created_by": created_by,
            "changelog": changelog,
        }
        data = await self._request("POST", f"/agents/{agent_id}/versions", json=payload)
        return VersionInfo(
            version=data["version"],
            oci_tag=data.get("oci_tag"),
            oci_digest=data.get("oci_digest"),
            status=data.get("status", "draft"),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
            promoted_at=datetime.fromisoformat(data["promoted_at"]) if data.get("promoted_at") else None,
            promoted_by=data.get("promoted_by"),
        )

    # -------------------------------------------------------------------------
    # Syndicates (similar pattern)
    # -------------------------------------------------------------------------

    async def get_syndicate(self, syndicate_id: str) -> ResourceInfo | None:
        """Get syndicate metadata by ID."""
        try:
            data = await self._request("GET", f"/syndicates/{syndicate_id}")
            return ResourceInfo(
                id=data["id"],
                name=data["name"],
                description=data.get("description"),
                current_version=data.get("current_version"),
                oci_repository=data.get("oci_repository"),
                status=data.get("status", "draft"),
                created_at=datetime.fromisoformat(data["created_at"]),
                updated_at=datetime.fromisoformat(data["updated_at"]),
                metadata=data.get("metadata", {}),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def create_syndicate(
        self,
        syndicate_id: str,
        name: str,
        description: str | None = None,
        oci_repository: str | None = None,
        created_by: str | None = None,
        metadata: dict | None = None,
    ) -> ResourceInfo:
        """Create a new syndicate."""
        payload = {
            "id": syndicate_id,
            "name": name,
            "description": description,
            "oci_repository": oci_repository,
            "status": "draft",
            "created_by": created_by,
            "metadata": metadata or {},
        }
        data = await self._request("POST", "/syndicates", json=payload)
        return ResourceInfo(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            current_version=data.get("current_version"),
            oci_repository=data.get("oci_repository"),
            status=data.get("status", "draft"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )

    async def create_syndicate_version(
        self,
        syndicate_id: str,
        version: str,
        oci_tag: str,
        oci_digest: str,
        agent_refs: list[dict],
        created_by: str | None = None,
        changelog: str | None = None,
    ) -> VersionInfo:
        """Create a new syndicate version."""
        payload = {
            "version": version,
            "oci_tag": oci_tag,
            "oci_digest": oci_digest,
            "agent_refs": agent_refs,
            "status": "draft",
            "created_by": created_by,
            "changelog": changelog,
        }
        data = await self._request("POST", f"/syndicates/{syndicate_id}/versions", json=payload)
        return VersionInfo(
            version=data["version"],
            oci_tag=data.get("oci_tag"),
            oci_digest=data.get("oci_digest"),
            status=data.get("status", "draft"),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by"),
            promoted_at=datetime.fromisoformat(data["promoted_at"]) if data.get("promoted_at") else None,
            promoted_by=data.get("promoted_by"),
        )


# Convenience function
def get_registry_client() -> RegistryClient:
    """Get a registry client configured from environment."""
    import os

    registry_url = os.environ.get("REGISTRY_URL", "https://registry-api.almckay.io")
    return RegistryClient(registry_url)
```

**Acceptance Criteria:**
- [ ] Registry client created with all CRUD operations
- [ ] Support for skills, agents, syndicates
- [ ] Version management with promotion
- [ ] Proper error handling for 404s
- [ ] Async HTTP with httpx

---

## Task 2.4: Add Registry API Endpoints

The registry service needs new API endpoints. Add to **`platform/registry/src/kubani_registry/api/v1/`**:

### 2.4.1 Update Skills API

**File:** `platform/registry/src/kubani_registry/api/v1/skills.py`

Add these endpoints to the existing router:

```python
# New Pydantic models
class SkillVersionCreate(BaseModel):
    """Schema for creating a skill version."""

    version: str
    oci_tag: str | None = None
    oci_digest: str | None = None
    status: str = "draft"
    created_by: str | None = None
    changelog: str | None = None


class SkillVersionResponse(BaseModel):
    """Schema for skill version response."""

    id: int
    skill_id: int
    version: str
    oci_tag: str | None
    oci_digest: str | None
    status: str
    created_at: datetime
    created_by: str | None
    changelog: str | None
    promoted_at: datetime | None
    promoted_by: str | None

    model_config = {"from_attributes": True}


class PromoteRequest(BaseModel):
    """Schema for promotion request."""

    target_status: str
    promoted_by: str | None = None


# New endpoints
@router.post("/{skill_id}/versions", response_model=SkillVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_skill_version(
    skill_id: str,
    version_data: SkillVersionCreate,
    session: SessionDep,
) -> SkillVersion:
    """Create a new skill version."""
    from urllib.parse import unquote

    skill_id = unquote(skill_id)

    # Find skill by name or ID
    result = await session.execute(select(Skill).where(Skill.name == skill_id))
    skill = result.scalar_one_or_none()

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    # Check version doesn't exist
    existing = await session.execute(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill.id,
            SkillVersion.version == version_data.version,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Version {version_data.version} already exists")

    version = SkillVersion(
        skill_id=skill.id,
        version=version_data.version,
        oci_tag=version_data.oci_tag,
        oci_digest=version_data.oci_digest,
        status=version_data.status,
        created_by=version_data.created_by,
        changelog=version_data.changelog,
    )
    session.add(version)
    await session.flush()
    return version


@router.get("/{skill_id}/versions/latest", response_model=SkillVersionResponse)
async def get_latest_skill_version(
    skill_id: str,
    session: SessionDep,
    version: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
) -> SkillVersion:
    """Get the latest skill version, optionally filtered by status."""
    from urllib.parse import unquote

    skill_id = unquote(skill_id)

    # Find skill
    result = await session.execute(select(Skill).where(Skill.name == skill_id))
    skill = result.scalar_one_or_none()

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    # Build query
    query = select(SkillVersion).where(SkillVersion.skill_id == skill.id)

    if version:
        query = query.where(SkillVersion.version == version)
    if status_filter:
        query = query.where(SkillVersion.status == status_filter)

    query = query.order_by(SkillVersion.created_at.desc()).limit(1)

    result = await session.execute(query)
    skill_version = result.scalar_one_or_none()

    if not skill_version:
        raise HTTPException(status_code=404, detail="No matching version found")

    return skill_version


@router.post("/{skill_id}/versions/{version}/promote", response_model=SkillVersionResponse)
async def promote_skill_version(
    skill_id: str,
    version: str,
    promote_data: PromoteRequest,
    session: SessionDep,
) -> SkillVersion:
    """Promote a skill version to a new status."""
    from urllib.parse import unquote

    from kubani_registry.constants import ResourceStatus

    skill_id = unquote(skill_id)

    # Find skill and version
    result = await session.execute(select(Skill).where(Skill.name == skill_id))
    skill = result.scalar_one_or_none()

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    result = await session.execute(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill.id,
            SkillVersion.version == version,
        )
    )
    skill_version = result.scalar_one_or_none()

    if not skill_version:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    # Validate promotion
    current_status = ResourceStatus(skill_version.status)
    target_status = ResourceStatus(promote_data.target_status)

    if not current_status.can_promote_to(target_status):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot promote from {current_status.value} to {target_status.value}",
        )

    # Update version
    skill_version.status = target_status.value
    skill_version.promoted_at = datetime.now(UTC)
    skill_version.promoted_by = promote_data.promoted_by

    # If promoting to production, update skill's current_version
    if target_status == ResourceStatus.PRODUCTION:
        skill.current_version = version
        skill.status = "production"

    await session.flush()
    return skill_version
```

### 2.4.2 Create Syndicates API

**File:** `platform/registry/src/kubani_registry/api/v1/syndicates.py` (new file)

```python
"""Syndicate API endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from ...db import Syndicate, SyndicateVersion
from ...db.session import get_session

# ... Similar pattern to skills.py
# Include: create_syndicate, get_syndicate, list_syndicates
# create_syndicate_version, get_latest_syndicate_version, promote_syndicate_version
```

### 2.4.3 Update Agents API

**File:** `platform/registry/src/kubani_registry/api/v1/agents.py`

Add version endpoints (similar pattern to skills).

### 2.4.4 Register New Routers

**File:** `platform/registry/src/kubani_registry/api/v1/__init__.py`

```python
from .agents import router as agents_router
from .deployments import router as deployments_router
from .endpoints import router as endpoints_router
from .mcp import router as mcp_router
from .models import router as models_router
from .skills import router as skills_router
from .syndicates import router as syndicates_router  # NEW

__all__ = [
    "agents_router",
    "deployments_router",
    "endpoints_router",
    "mcp_router",
    "models_router",
    "skills_router",
    "syndicates_router",  # NEW
]
```

**File:** `platform/registry/src/kubani_registry/main.py`

```python
# Add to router registration
from .api.v1 import syndicates_router

app.include_router(syndicates_router, prefix="/api/v1/syndicates", tags=["syndicates"])
```

**Acceptance Criteria:**
- [ ] Version endpoints for skills, agents, syndicates
- [ ] Promotion endpoint with validation
- [ ] Syndicate router created and registered
- [ ] All endpoints tested manually

---

## Task 2.5: CLI Commands - Pull

**File:** `platform/cli/src/kubani_dev/commands/pull.py` (new file)

```python
"""Pull command for fetching resources from the registry."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from kubani_dev.oci import get_oci_client
from kubani_dev.registry_client import get_registry_client
from kubani_dev.ui import console, error, info, success

app = typer.Typer(help="Pull resources from the registry")


@app.command("skill")
def pull_skill(
    name: Annotated[str, typer.Argument(help="Skill name or ID")],
    version: Annotated[str | None, typer.Option("--version", "-v", help="Specific version")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output directory")] = None,
    status: Annotated[str, typer.Option("--status", "-s", help="Version status")] = "production",
):
    """Pull a skill from the registry."""
    asyncio.run(_pull_skill(name, version, output, status))


async def _pull_skill(name: str, version: str | None, output: Path | None, status: str):
    registry = get_registry_client()
    oci = get_oci_client()

    # Get skill metadata
    skill = await registry.get_skill(name)
    if not skill:
        error(f"Skill '{name}' not found in registry")
        raise typer.Exit(1)

    # Get version info
    if version:
        version_info = await registry.get_skill_version(name, version=version)
    else:
        version_info = await registry.get_skill_version(name, status=status)

    if not version_info:
        error(f"No version found for skill '{name}' with status '{status}'")
        raise typer.Exit(1)

    # Determine output path
    if output is None:
        # Default: skills/{domain}/{category}/{name}
        domain = skill.metadata.get("domain", "general")
        category = skill.metadata.get("category", "general")
        output = Path("skills") / domain / category / name

    info(f"Pulling {name}:{version_info.version} to {output}")

    # Pull from OCI
    result = oci.pull(
        resource_type="skill",
        name=name,
        tag=version_info.oci_tag or f"v{version_info.version}",
        dest_dir=output,
    )

    success(f"Pulled {name}:{version_info.version}")
    console.print(f"  Path: {result.extracted_path}")
    console.print(f"  Digest: {result.digest}")


@app.command("agent")
def pull_agent(
    name: Annotated[str, typer.Argument(help="Agent name")],
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
):
    """Pull an agent from the registry."""
    asyncio.run(_pull_agent(name, version, output))


async def _pull_agent(name: str, version: str | None, output: Path | None):
    # Similar implementation to _pull_skill
    ...


@app.command("syndicate")
def pull_syndicate(
    name: Annotated[str, typer.Argument(help="Syndicate name")],
    version: Annotated[str | None, typer.Option("--version", "-v")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
):
    """Pull a syndicate from the registry."""
    asyncio.run(_pull_syndicate(name, version, output))


async def _pull_syndicate(name: str, version: str | None, output: Path | None):
    # Similar implementation
    ...
```

**Acceptance Criteria:**
- [ ] `kubani pull skill <name>` works
- [ ] `kubani pull agent <name>` works
- [ ] `kubani pull syndicate <name>` works
- [ ] Version and status filtering works
- [ ] Custom output directory works

---

## Task 2.6: CLI Commands - Push

**File:** `platform/cli/src/kubani_dev/commands/push.py` (new file)

```python
"""Push command for uploading resources to the registry."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from kubani_dev.oci import get_oci_client
from kubani_dev.registry_client import get_registry_client
from kubani_dev.ui import console, error, info, success

app = typer.Typer(help="Push resources to the registry")


@app.command("skill")
def push_skill(
    path: Annotated[Path, typer.Argument(help="Path to skill directory")],
    version: Annotated[str, typer.Option("--version", "-v", help="Version tag")] = None,
    changelog: Annotated[str | None, typer.Option("--changelog", "-c")] = None,
):
    """Push a skill to the registry."""
    asyncio.run(_push_skill(path, version, changelog))


async def _push_skill(path: Path, version: str | None, changelog: str | None):
    if not path.is_dir():
        error(f"Path must be a directory: {path}")
        raise typer.Exit(1)

    # Parse SKILL.md for metadata
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        error(f"SKILL.md not found in {path}")
        raise typer.Exit(1)

    # Extract name and metadata from SKILL.md
    metadata = _parse_skill_md(skill_md)
    name = metadata.get("name", path.name)

    if not version:
        # Auto-increment version
        version = await _get_next_version(name)

    registry = get_registry_client()
    oci = get_oci_client()

    info(f"Pushing {name}:{version} from {path}")

    # Push to OCI
    oci_result = oci.push(
        source_dir=path,
        resource_type="skill",
        name=name,
        tag=f"v{version}",
    )

    # Ensure skill exists in registry
    skill = await registry.get_skill(name)
    if not skill:
        # Derive domain/category from path
        parts = path.parts
        domain = "general"
        category = "general"
        if "skills" in parts:
            idx = parts.index("skills")
            if len(parts) > idx + 1:
                domain = parts[idx + 1]
            if len(parts) > idx + 2:
                category = parts[idx + 2]

        await registry.create_skill(
            skill_id=name,
            name=name,
            description=metadata.get("description"),
            domain=domain,
            category=category,
            oci_repository=oci_result.repository,
            created_by="human",
            metadata=metadata,
        )

    # Create version
    version_info = await registry.create_skill_version(
        skill_id=name,
        version=version,
        oci_tag=f"v{version}",
        oci_digest=oci_result.digest,
        created_by="human",
        changelog=changelog,
    )

    success(f"Pushed {name}:{version}")
    console.print(f"  Repository: {oci_result.repository}")
    console.print(f"  Digest: {oci_result.digest}")
    console.print(f"  Status: {version_info.status}")


def _parse_skill_md(path: Path) -> dict:
    """Parse SKILL.md frontmatter."""
    import yaml

    content = path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
    return {}


async def _get_next_version(skill_name: str) -> str:
    """Get the next version number for a skill."""
    registry = get_registry_client()
    skill = await registry.get_skill(skill_name)

    if not skill or not skill.current_version:
        return "0.1.0"

    # Parse current version and increment patch
    parts = skill.current_version.split(".")
    if len(parts) == 3:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{major}.{minor}.{patch + 1}"

    return "0.1.0"


# Similar implementations for push_agent and push_syndicate
@app.command("agent")
def push_agent(...):
    ...


@app.command("syndicate")
def push_syndicate(...):
    ...
```

**Acceptance Criteria:**
- [ ] `kubani push skill <path>` works
- [ ] Auto-generates version if not specified
- [ ] Creates skill in registry if not exists
- [ ] Parses SKILL.md for metadata
- [ ] Reports success with details

---

## Task 2.7: CLI Commands - Promote

**File:** `platform/cli/src/kubani_dev/commands/promote.py` (new file)

```python
"""Promote command for advancing resource versions through lifecycle."""

import asyncio
from typing import Annotated

import typer

from kubani_dev.registry_client import get_registry_client
from kubani_dev.ui import console, error, info, success, warning

app = typer.Typer(help="Promote resources through lifecycle stages")


@app.command("skill")
def promote_skill(
    name: Annotated[str, typer.Argument(help="Skill name:version (e.g., 'my-skill:1.0.0')")],
    to: Annotated[str, typer.Option("--to", "-t", help="Target status")] = None,
):
    """Promote a skill version to a new status."""
    asyncio.run(_promote_skill(name, to))


async def _promote_skill(name_version: str, to: str | None):
    # Parse name:version
    if ":" in name_version:
        name, version = name_version.rsplit(":", 1)
    else:
        error("Please specify version: skill-name:version")
        raise typer.Exit(1)

    registry = get_registry_client()

    # Get current version info
    version_info = await registry.get_skill_version(name, version=version)
    if not version_info:
        error(f"Version {version} not found for skill '{name}'")
        raise typer.Exit(1)

    current_status = version_info.status

    # Determine target status
    if to:
        target_status = to
    else:
        # Auto-determine next status
        status_order = ["draft", "testing", "staging", "production"]
        try:
            current_idx = status_order.index(current_status)
            if current_idx >= len(status_order) - 1:
                error(f"Skill is already at {current_status}, cannot promote further")
                raise typer.Exit(1)
            target_status = status_order[current_idx + 1]
        except ValueError:
            error(f"Unknown current status: {current_status}")
            raise typer.Exit(1)

    info(f"Promoting {name}:{version} from {current_status} to {target_status}")

    # Confirm if promoting to production
    if target_status == "production":
        if not typer.confirm("Promote to production? This will make it available to all agents."):
            warning("Cancelled")
            raise typer.Exit(0)

    # Promote
    result = await registry.promote_skill_version(
        skill_id=name,
        version=version,
        target_status=target_status,
        promoted_by="human",
    )

    success(f"Promoted {name}:{version} to {result.status}")


# Similar for promote_agent and promote_syndicate
@app.command("agent")
def promote_agent(...):
    ...


@app.command("syndicate")
def promote_syndicate(...):
    ...
```

**Acceptance Criteria:**
- [ ] `kubani promote skill name:version --to staging` works
- [ ] Auto-determines next status if --to not specified
- [ ] Confirms before production promotion
- [ ] Shows clear success/error messages

---

## Task 2.8: Register CLI Commands

**File:** `platform/cli/src/kubani_dev/cli.py`

```python
# Add imports
from kubani_dev.commands import pull, push, promote

# Register subcommands
app.add_typer(pull.app, name="pull")
app.add_typer(push.app, name="push")
app.add_typer(promote.app, name="promote")
```

**Acceptance Criteria:**
- [ ] `kubani pull --help` shows subcommands
- [ ] `kubani push --help` shows subcommands
- [ ] `kubani promote --help` shows subcommands

---

## Task 2.9: Integration Tests

**File:** `platform/cli/tests/test_oci_integration.py`

```python
"""Integration tests for OCI registry operations."""

import pytest
from pathlib import Path
import tempfile

from kubani_dev.oci import KubaniOCIClient


@pytest.fixture
def oci_client():
    """Create OCI client for testing."""
    # Use local registry for tests
    return KubaniOCIClient(
        registry_url="localhost:5000",
        insecure=True,
    )


@pytest.fixture
def sample_skill(tmp_path):
    """Create a sample skill directory."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()

    (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: A test skill
---

# Test Skill

This is a test skill for integration testing.
""")

    (skill_dir / "scripts").mkdir()
    (skill_dir / "scripts" / "test.py").write_text("print('hello')")

    return skill_dir


@pytest.mark.integration
def test_push_and_pull_skill(oci_client, sample_skill, tmp_path):
    """Test pushing and pulling a skill."""
    # Push
    result = oci_client.push(
        source_dir=sample_skill,
        resource_type="skill",
        name="test-skill",
        tag="v0.1.0",
    )

    assert result.repository == "localhost:5000/skills/test-skill"
    assert result.tag == "v0.1.0"
    assert result.digest.startswith("sha256:")

    # Pull
    dest_dir = tmp_path / "pulled"
    pull_result = oci_client.pull(
        resource_type="skill",
        name="test-skill",
        tag="v0.1.0",
        dest_dir=dest_dir,
    )

    assert pull_result.extracted_path == dest_dir
    assert (dest_dir / "SKILL.md").exists()
    assert (dest_dir / "scripts" / "test.py").exists()


@pytest.mark.integration
def test_list_tags(oci_client, sample_skill):
    """Test listing tags for a resource."""
    # Push multiple versions
    for v in ["v0.1.0", "v0.2.0", "v0.3.0"]:
        oci_client.push(
            source_dir=sample_skill,
            resource_type="skill",
            name="multi-version-skill",
            tag=v,
        )

    tags = oci_client.list_tags("skill", "multi-version-skill")
    assert "v0.1.0" in tags
    assert "v0.2.0" in tags
    assert "v0.3.0" in tags
```

**Acceptance Criteria:**
- [ ] Integration tests for OCI push/pull
- [ ] Tests run against local registry (docker)
- [ ] Tests verify content integrity

---

## Commit Checkpoints

```bash
# After Task 2.1-2.2
git add platform/cli/pyproject.toml platform/cli/src/kubani_dev/oci.py
git commit -m "feat(cli): add OCI client for registry operations

- Add oras-py dependency
- Create KubaniOCIClient wrapper for push/pull
- Support for skills, agents, syndicates

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 2.3
git add platform/cli/src/kubani_dev/registry_client.py
git commit -m "feat(cli): add registry API client

- Async client for registry API
- Support for skills, agents, syndicates CRUD
- Version management and promotion

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 2.4
git add platform/registry/src/kubani_registry/api/
git commit -m "feat(registry): add version and syndicate API endpoints

- Add skill version endpoints (create, get, promote)
- Create syndicates API router
- Add agent version endpoints

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Tasks 2.5-2.8
git add platform/cli/src/kubani_dev/commands/
git commit -m "feat(cli): add pull, push, promote commands

- kubani pull skill/agent/syndicate
- kubani push skill/agent/syndicate
- kubani promote skill/agent/syndicate
- Auto version increment

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 2.9
git add platform/cli/tests/
git commit -m "test(cli): add OCI integration tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Push
git push origin elegant-chaum
```

---

## Phase 2 Completion Checklist

- [ ] oras-py dependency added and working
- [ ] OCI client wrapper implemented
- [ ] Registry API client implemented
- [ ] New API endpoints for versions and syndicates
- [ ] CLI pull command working
- [ ] CLI push command working
- [ ] CLI promote command working
- [ ] Integration tests passing
- [ ] All changes committed and pushed
- [ ] Ready for Phase 3
