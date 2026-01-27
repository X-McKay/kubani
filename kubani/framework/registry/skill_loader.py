"""Skill loader that fetches skills from the registry."""

import logging
import shutil
import tarfile
import tempfile
import time
from pathlib import Path

import oras.client
import yaml

from kubani.framework.config import get_config

from .client import RegistryClient, get_registry_client
from .models import ResourceInfo, ResourceStatus, SkillContent, VersionInfo

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
        self.cache_dir = (
            cache_dir
            or Path(
                config.registry.url.replace("http://", "").replace("https://", "").split(":")[0]
                if config.registry.url
                else "~/.kubani/skill-cache"
            ).expanduser()
        )

        # Use a more sensible default
        if str(self.cache_dir).startswith("localhost"):
            self.cache_dir = Path("~/.kubani/skill-cache").expanduser()

        self.oci_registry_url = oci_registry_url or "registry.almckay.io"

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
        skill_info: ResourceInfo,
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
        skill_info: ResourceInfo,
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
        domain = metadata.get("metadata", {}).get("domain") or skill_info.metadata.get(
            "domain", "general"
        )
        category = metadata.get("metadata", {}).get("category") or skill_info.metadata.get(
            "category", "general"
        )

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
