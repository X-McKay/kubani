"""
OCI-based skill discovery module.

Discovers skills from an OCI registry instead of the filesystem.
Provides caching with TTL and refresh mechanisms.
"""

import logging
import os
import time
from pathlib import Path

from skills_mcp.discovery import SkillDiscovery
from skills_mcp.models import SkillInfo

logger = logging.getLogger(__name__)


class OCISkillDiscovery:
    """
    Discovers skills from an OCI registry.

    Pulls skills from an OCI registry, caches them locally with TTL,
    and provides refresh mechanisms.

    Configuration via environment variables:
    - OCI_REGISTRY_URL: URL of the OCI registry (e.g., registry.almckay.io)
    - OCI_REGISTRY_USERNAME: Username for authentication (optional)
    - OCI_REGISTRY_PASSWORD: Password for authentication (optional)
    - OCI_SKILLS_CACHE_DIR: Local cache directory (default: /tmp/skills-cache)
    - OCI_SKILLS_CACHE_TTL: Cache TTL in seconds (default: 3600)
    """

    def __init__(
        self,
        registry_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        cache_dir: str | Path | None = None,
        cache_ttl: int = 3600,
    ):
        """
        Initialize OCI skill discovery.

        Args:
            registry_url: OCI registry URL (defaults to OCI_REGISTRY_URL env var)
            username: Registry username (defaults to OCI_REGISTRY_USERNAME env var)
            password: Registry password (defaults to OCI_REGISTRY_PASSWORD env var)
            cache_dir: Local cache directory (defaults to OCI_SKILLS_CACHE_DIR or /tmp/skills-cache)
            cache_ttl: Cache TTL in seconds (default: 3600)
        """
        self.registry_url = registry_url or os.environ.get("OCI_REGISTRY_URL")
        self.username = username or os.environ.get("OCI_REGISTRY_USERNAME")
        self.password = password or os.environ.get("OCI_REGISTRY_PASSWORD")

        if not self.registry_url:
            raise ValueError("OCI registry URL not configured")

        # Setup cache directory
        default_cache = os.environ.get("OCI_SKILLS_CACHE_DIR", "/tmp/skills-cache")
        self.cache_dir = Path(cache_dir or default_cache)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.cache_ttl = cache_ttl
        self._last_pull_time: float | None = None
        self._filesystem_discovery: SkillDiscovery | None = None

        logger.info(f"OCI skill discovery initialized: {self.registry_url}")
        logger.info(f"Cache directory: {self.cache_dir}, TTL: {self.cache_ttl}s")

    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid based on TTL."""
        if self._last_pull_time is None:
            return False

        elapsed = time.time() - self._last_pull_time
        return elapsed < self.cache_ttl

    async def _pull_skills_from_registry(self) -> None:
        """
        Pull skills from the OCI registry.

        This is a placeholder implementation. In a real implementation,
        you would use an OCI client library like oras-py to pull artifacts.
        """
        logger.info(f"Pulling skills from OCI registry: {self.registry_url}")

        try:
            # TODO: Implement actual OCI pull using oras-py or similar
            # For now, this is a placeholder that logs the intent

            # Example of what the implementation would look like:
            # import oras.client
            #
            # client = oras.client.OrasClient(hostname=self.registry_url)
            # if self.username and self.password:
            #     client.login(username=self.username, password=self.password)
            #
            # # Pull skills artifact
            # artifact_ref = f"{self.registry_url}/kubani/skills:latest"
            # client.pull(target=artifact_ref, outdir=str(self.cache_dir))

            logger.warning(
                "OCI pull not yet implemented - using filesystem fallback. "
                "To implement: add oras-py client and pull logic here."
            )

            self._last_pull_time = time.time()

        except Exception as e:
            logger.error(f"Failed to pull skills from OCI registry: {e}")
            raise

    def discover_all(self, force_refresh: bool = False) -> list[SkillInfo]:
        """
        Discover all skills from OCI registry (with caching).

        Args:
            force_refresh: Force refresh from registry even if cache is valid

        Returns:
            List of discovered skills
        """
        # Check if we need to refresh from registry
        if force_refresh or not self._is_cache_valid():
            import asyncio

            # Pull from registry
            try:
                asyncio.run(self._pull_skills_from_registry())
            except Exception as e:
                logger.error(f"Failed to refresh from OCI registry: {e}")
                # Continue with cached data if available

        # Use filesystem discovery on the cached directory
        if self._filesystem_discovery is None:
            self._filesystem_discovery = SkillDiscovery(self.cache_dir)

        return self._filesystem_discovery.discover_all(force_refresh=force_refresh)

    def get_skill(self, skill_path: str) -> SkillInfo | None:
        """
        Get a specific skill by path.

        Args:
            skill_path: Skill path (e.g., "k8s/diagnostic/check-pod-health")

        Returns:
            SkillInfo if found, None otherwise
        """
        # Ensure we have skills cached
        if self._filesystem_discovery is None:
            self.discover_all()

        return (
            self._filesystem_discovery.get_skill(skill_path)
            if self._filesystem_discovery
            else None
        )

    def filter_skills(
        self,
        skills: list[SkillInfo] | None = None,
        domain: str | None = None,
        category: str | None = None,
        allowed: list[str] | None = None,
        denied: list[str] | None = None,
    ) -> list[SkillInfo]:
        """
        Filter skills based on criteria.

        Args:
            skills: Skills to filter (defaults to all discovered)
            domain: Filter by domain (e.g., "k8s")
            category: Filter by category (e.g., "diagnostic")
            allowed: Glob patterns for allowed skills
            denied: Glob patterns for denied skills

        Returns:
            Filtered list of skills
        """
        if self._filesystem_discovery is None:
            self.discover_all()

        if self._filesystem_discovery:
            return self._filesystem_discovery.filter_skills(
                skills=skills,
                domain=domain,
                category=category,
                allowed=allowed,
                denied=denied,
            )

        return []

    def refresh(self) -> list[SkillInfo]:
        """Force refresh from OCI registry."""
        return self.discover_all(force_refresh=True)


# Global OCI discovery instance
_oci_discovery: OCISkillDiscovery | None = None


def get_oci_discovery(
    registry_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    cache_dir: str | Path | None = None,
    cache_ttl: int = 3600,
) -> OCISkillDiscovery:
    """
    Get the global OCI skill discovery instance.

    Args:
        registry_url: OCI registry URL
        username: Registry username
        password: Registry password
        cache_dir: Local cache directory
        cache_ttl: Cache TTL in seconds

    Returns:
        OCISkillDiscovery instance
    """
    global _oci_discovery

    if _oci_discovery is None:
        _oci_discovery = OCISkillDiscovery(
            registry_url=registry_url,
            username=username,
            password=password,
            cache_dir=cache_dir,
            cache_ttl=cache_ttl,
        )

    return _oci_discovery
