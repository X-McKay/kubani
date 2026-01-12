"""
Skills CLI - sync skills from filesystem to Qdrant and metadata registry.

This CLI is used during deployment to register skills in both:
1. Qdrant - for semantic search at runtime
2. Metadata Registry - for UI visibility, tracking, and confidence scores

Usage:
    skills-sync [skills_dir]  # Sync all skills to Qdrant + registry
    skills-sync --list        # List skills in Qdrant
    skills-sync --qdrant-only # Sync only to Qdrant (skip registry)

Environment variables:
    SKILLS_DIR: Default skills directory (default: ./skills)
    QDRANT_HOST: Qdrant host (default: localhost)
    QDRANT_PORT: Qdrant port (default: 6333)
    EMBEDDINGS_API_URL: Embeddings API URL (default: http://localhost:8001/v1)
    KUBANI_REGISTRY_URL: Metadata registry URL (default: http://localhost:8000)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def register_skill_in_registry(
    client: httpx.AsyncClient,
    registry_url: str,
    skill_id: str,
    name: str,
    domain: str,
    category: str,
    confidence: float,
    requires_approval: bool,
) -> bool:
    """Register a single skill in the metadata registry."""
    try:
        response = await client.post(
            f"{registry_url}/api/v1/skills",
            json={
                "id": skill_id,
                "name": name,
                "domain": domain,
                "category": category,
                "status": "stable",  # Synced skills are considered stable
                "confidence": confidence,
                "requires_approval": requires_approval,
            },
            timeout=10.0,
        )
        if response.status_code in (200, 201):
            return True
        logger.warning(f"Failed to register {skill_id} in registry: {response.status_code}")
        return False
    except Exception as e:
        logger.warning(f"Failed to register {skill_id} in registry: {e}")
        return False


async def sync_skills(skills_dir: Path, skip_registry: bool = False) -> list[str]:
    """Sync skills from filesystem to Qdrant and optionally to metadata registry."""
    from core_agents.skills.unified import UnifiedSkillLibrary

    library = UnifiedSkillLibrary(skills_dir=skills_dir)
    synced = await library.sync()

    logger.info(f"Synced {len(synced)} skills to Qdrant")
    for skill_id in synced:
        logger.info(f"  - {skill_id}")

    # Also register in metadata registry for UI visibility
    if not skip_registry:
        registry_url = os.getenv("KUBANI_REGISTRY_URL", "http://localhost:8000")
        logger.info(f"Registering skills in metadata registry at {registry_url}")

        registered = 0
        async with httpx.AsyncClient() as client:
            # Check if registry is available
            try:
                health = await client.get(f"{registry_url}/health", timeout=5.0)
                if health.status_code != 200:
                    logger.warning("Registry not healthy, skipping registration")
                    return synced
            except Exception as e:
                logger.warning(f"Registry not available at {registry_url}: {e}")
                logger.info("Skipping registry registration (Qdrant sync completed)")
                return synced

            # Register each synced skill
            for skill_id in synced:
                skill = await library.get(skill_id)
                if skill:
                    success = await register_skill_in_registry(
                        client=client,
                        registry_url=registry_url,
                        skill_id=skill_id,
                        name=skill.name,
                        domain=skill.domain,
                        category=skill.category,
                        confidence=skill.confidence,
                        requires_approval=skill.requires_approval,
                    )
                    if success:
                        registered += 1

        logger.info(f"Registered {registered}/{len(synced)} skills in metadata registry")

    return synced


async def list_skills() -> None:
    """List skills currently in Qdrant."""
    from core_agents.skills.unified import UnifiedSkillLibrary

    library = UnifiedSkillLibrary()
    await library._ensure_initialized()

    # Query all skills

    response = await library._qdrant_client.scroll(
        collection_name=library.collection_name,
        limit=1000,
        with_payload=True,
    )

    points, _ = response
    logger.info(f"Found {len(points)} skills in Qdrant:")
    for point in points:
        skill_id = point.payload.get("id", "unknown")
        name = point.payload.get("name", "unknown")
        domain = point.payload.get("domain", "unknown")
        logger.info(f"  - {skill_id}: {name} (domain: {domain})")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sync skills from filesystem to Qdrant and metadata registry",
    )
    parser.add_argument(
        "skills_dir",
        nargs="?",
        default="skills",
        help="Skills directory to sync (default: ./skills)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List skills in Qdrant instead of syncing",
    )
    parser.add_argument(
        "--qdrant-only",
        action="store_true",
        help="Sync only to Qdrant, skip metadata registry",
    )

    args = parser.parse_args()

    if args.list:
        asyncio.run(list_skills())
    else:
        skills_dir = Path(args.skills_dir)
        if not skills_dir.exists():
            logger.error(f"Skills directory does not exist: {skills_dir}")
            sys.exit(1)

        synced = asyncio.run(sync_skills(skills_dir, skip_registry=args.qdrant_only))
        if not synced:
            logger.warning("No skills were synced")
            sys.exit(1)


if __name__ == "__main__":
    main()
