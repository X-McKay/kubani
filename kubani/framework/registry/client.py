"""Async registry client for agents."""

import logging
from datetime import datetime
from typing import Literal
from urllib.parse import quote

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
        self.registry_url = (registry_url or config.registry.url).rstrip("/")
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
                    datetime.fromisoformat(data["promoted_at"]) if data.get("promoted_at") else None
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
