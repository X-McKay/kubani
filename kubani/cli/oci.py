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
        try:
            manifest = self._client.remote.get_manifest(target)
            digest = manifest.get("digest", "unknown")
        except Exception:
            digest = "unknown"

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


def get_oci_client() -> KubaniOCIClient:
    """Get an OCI client configured from environment."""
    registry_url = os.environ.get("KUBANI_OCI_REGISTRY", "registry.almckay.io")

    return KubaniOCIClient(
        registry_url=registry_url,
        username=os.environ.get("KUBANI_OCI_USERNAME"),
        password=os.environ.get("KUBANI_OCI_PASSWORD"),
    )
