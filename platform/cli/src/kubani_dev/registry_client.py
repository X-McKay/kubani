"""Client for the Kubani Registry API."""

import logging
import os
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

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse ISO datetime string, handling None."""
        if value is None:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    # -------------------------------------------------------------------------
    # Skills
    # -------------------------------------------------------------------------

    async def get_skill(self, skill_id: str) -> ResourceInfo | None:
        """Get skill metadata by ID."""
        try:
            encoded_id = quote(skill_id, safe="")
            data = await self._request("GET", f"/skills/{encoded_id}")
            return ResourceInfo(
                id=str(data.get("id", skill_id)),
                name=data["name"],
                description=data.get("description"),
                current_version=data.get("current_version"),
                oci_repository=data.get("oci_repository"),
                status=data.get("status", "draft"),
                created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
                updated_at=self._parse_datetime(data.get("updated_at")) or datetime.now(),
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
                id=str(s.get("id", s["name"])),
                name=s["name"],
                description=s.get("description"),
                current_version=s.get("current_version"),
                oci_repository=s.get("oci_repository"),
                status=s.get("status", "draft"),
                created_at=self._parse_datetime(s.get("created_at")) or datetime.now(),
                updated_at=self._parse_datetime(s.get("updated_at")) or datetime.now(),
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
            "name": name,
            "description": description,
            "domain": domain,
            "category": category or "general",
            "oci_repository": oci_repository,
            "status": "draft",
            "created_by": created_by,
            "metadata": metadata or {},
        }
        data = await self._request("POST", "/skills", json=payload)
        return ResourceInfo(
            id=str(data.get("id", skill_id)),
            name=data["name"],
            description=data.get("description"),
            current_version=data.get("current_version"),
            oci_repository=data.get("oci_repository"),
            status=data.get("status", "draft"),
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            updated_at=self._parse_datetime(data.get("updated_at")) or datetime.now(),
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
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            created_by=data.get("created_by"),
            promoted_at=self._parse_datetime(data.get("promoted_at")),
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
            data = await self._request(
                "GET", f"/skills/{encoded_id}/versions/latest", params=params
            )
            return VersionInfo(
                version=data["version"],
                oci_tag=data.get("oci_tag"),
                oci_digest=data.get("oci_digest"),
                status=data.get("status", "draft"),
                created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
                created_by=data.get("created_by"),
                promoted_at=self._parse_datetime(data.get("promoted_at")),
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
        data = await self._request(
            "POST", f"/skills/{encoded_id}/versions/{version}/promote", json=payload
        )
        return VersionInfo(
            version=data["version"],
            oci_tag=data.get("oci_tag"),
            oci_digest=data.get("oci_digest"),
            status=data.get("status"),
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            created_by=data.get("created_by"),
            promoted_at=self._parse_datetime(data.get("promoted_at")),
            promoted_by=data.get("promoted_by"),
        )

    # -------------------------------------------------------------------------
    # Agents
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
                created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
                updated_at=self._parse_datetime(data.get("updated_at")) or datetime.now(),
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
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            created_by=data.get("created_by"),
            promoted_at=self._parse_datetime(data.get("promoted_at")),
            promoted_by=data.get("promoted_by"),
        )

    async def get_agent_version(
        self,
        agent_id: str,
        version: str | None = None,
        status: ResourceStatus | None = None,
    ) -> VersionInfo | None:
        """Get a specific agent version."""
        params = {}
        if version:
            params["version"] = version
        if status:
            params["status"] = status

        try:
            data = await self._request("GET", f"/agents/{agent_id}/versions/latest", params=params)
            return VersionInfo(
                version=data["version"],
                oci_tag=data.get("oci_tag"),
                oci_digest=data.get("oci_digest"),
                status=data.get("status", "draft"),
                created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
                created_by=data.get("created_by"),
                promoted_at=self._parse_datetime(data.get("promoted_at")),
                promoted_by=data.get("promoted_by"),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def promote_agent_version(
        self,
        agent_id: str,
        version: str,
        target_status: ResourceStatus,
        promoted_by: str | None = None,
    ) -> VersionInfo:
        """Promote an agent version to a new status."""
        payload = {
            "target_status": target_status,
            "promoted_by": promoted_by,
        }
        data = await self._request(
            "POST", f"/agents/{agent_id}/versions/{version}/promote", json=payload
        )
        return VersionInfo(
            version=data["version"],
            oci_tag=data.get("oci_tag"),
            oci_digest=data.get("oci_digest"),
            status=data.get("status"),
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            created_by=data.get("created_by"),
            promoted_at=self._parse_datetime(data.get("promoted_at")),
            promoted_by=data.get("promoted_by"),
        )

    # -------------------------------------------------------------------------
    # Syndicates
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
                created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
                updated_at=self._parse_datetime(data.get("updated_at")) or datetime.now(),
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
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            updated_at=self._parse_datetime(data.get("updated_at")) or datetime.now(),
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
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            created_by=data.get("created_by"),
            promoted_at=self._parse_datetime(data.get("promoted_at")),
            promoted_by=data.get("promoted_by"),
        )

    async def get_syndicate_version(
        self,
        syndicate_id: str,
        version: str | None = None,
        status: ResourceStatus | None = None,
    ) -> VersionInfo | None:
        """Get a specific syndicate version."""
        params = {}
        if version:
            params["version"] = version
        if status:
            params["status"] = status

        try:
            data = await self._request(
                "GET", f"/syndicates/{syndicate_id}/versions/latest", params=params
            )
            return VersionInfo(
                version=data["version"],
                oci_tag=data.get("oci_tag"),
                oci_digest=data.get("oci_digest"),
                status=data.get("status", "draft"),
                created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
                created_by=data.get("created_by"),
                promoted_at=self._parse_datetime(data.get("promoted_at")),
                promoted_by=data.get("promoted_by"),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def promote_syndicate_version(
        self,
        syndicate_id: str,
        version: str,
        target_status: ResourceStatus,
        promoted_by: str | None = None,
    ) -> VersionInfo:
        """Promote a syndicate version to a new status."""
        payload = {
            "target_status": target_status,
            "promoted_by": promoted_by,
        }
        data = await self._request(
            "POST", f"/syndicates/{syndicate_id}/versions/{version}/promote", json=payload
        )
        return VersionInfo(
            version=data["version"],
            oci_tag=data.get("oci_tag"),
            oci_digest=data.get("oci_digest"),
            status=data.get("status"),
            created_at=self._parse_datetime(data.get("created_at")) or datetime.now(),
            created_by=data.get("created_by"),
            promoted_at=self._parse_datetime(data.get("promoted_at")),
            promoted_by=data.get("promoted_by"),
        )


def get_registry_client() -> RegistryClient:
    """Get a registry client configured from environment."""
    registry_url = os.environ.get("REGISTRY_URL", "https://metadata.almckay.io")
    return RegistryClient(registry_url)
