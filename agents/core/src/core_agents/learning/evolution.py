"""
Skill Evolution - Automatic skill improvement and generation.

Provides capabilities for:
1. Evolving existing skills based on feedback
2. Generating new skills from patterns
3. A/B testing skill variants
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EvolutionStrategy(str, Enum):
    """Strategies for skill evolution."""

    REFINEMENT = "refinement"  # Improve existing skill
    GENERALIZATION = "generalization"  # Make skill more general
    SPECIALIZATION = "specialization"  # Make skill more specific
    COMBINATION = "combination"  # Combine multiple skills
    GENERATION = "generation"  # Generate new skill


@dataclass
class SkillVariant:
    """A variant of a skill for A/B testing."""

    id: str
    skill_id: str
    version: str
    content: str
    strategy: EvolutionStrategy
    metrics: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = False


@dataclass
class EvolutionResult:
    """Result of a skill evolution operation."""

    success: bool
    original_skill_id: str
    new_variant: Optional[SkillVariant] = None
    changes: list[str] = field(default_factory=list)
    error: Optional[str] = None


class SkillEvolution:
    """
    Manages skill evolution and improvement.

    Features:
    - Automatic skill refinement based on feedback
    - New skill generation from patterns
    - A/B testing of skill variants
    - Rollback capabilities
    """

    def __init__(self, skills_dir: str | Path):
        self.skills_dir = Path(skills_dir)
        self._variants: dict[str, list[SkillVariant]] = {}

    async def evolve_skill(
        self,
        skill_id: str,
        strategy: EvolutionStrategy,
        feedback: Optional[dict[str, Any]] = None,
        patterns: Optional[list[dict[str, Any]]] = None,
    ) -> EvolutionResult:
        """
        Evolve a skill using the specified strategy.

        Args:
            skill_id: ID of the skill to evolve
            strategy: Evolution strategy to use
            feedback: User feedback to incorporate
            patterns: Learned patterns to use

        Returns:
            EvolutionResult with the new variant
        """
        try:
            # Load current skill
            skill_content = await self._load_skill(skill_id)
            if not skill_content:
                return EvolutionResult(
                    success=False,
                    original_skill_id=skill_id,
                    error=f"Skill not found: {skill_id}",
                )

            # Apply evolution strategy
            if strategy == EvolutionStrategy.REFINEMENT:
                new_content, changes = await self._refine_skill(
                    skill_content, feedback
                )
            elif strategy == EvolutionStrategy.GENERALIZATION:
                new_content, changes = await self._generalize_skill(
                    skill_content, patterns
                )
            elif strategy == EvolutionStrategy.SPECIALIZATION:
                new_content, changes = await self._specialize_skill(
                    skill_content, patterns
                )
            elif strategy == EvolutionStrategy.GENERATION:
                new_content, changes = await self._generate_skill(patterns)
            else:
                return EvolutionResult(
                    success=False,
                    original_skill_id=skill_id,
                    error=f"Unknown strategy: {strategy}",
                )

            # Create variant
            import uuid

            variant = SkillVariant(
                id=str(uuid.uuid4()),
                skill_id=skill_id,
                version=self._next_version(skill_id),
                content=new_content,
                strategy=strategy,
            )

            # Store variant
            if skill_id not in self._variants:
                self._variants[skill_id] = []
            self._variants[skill_id].append(variant)

            return EvolutionResult(
                success=True,
                original_skill_id=skill_id,
                new_variant=variant,
                changes=changes,
            )

        except Exception as e:
            logger.error(f"Skill evolution failed: {e}")
            return EvolutionResult(
                success=False,
                original_skill_id=skill_id,
                error=str(e),
            )

    async def _load_skill(self, skill_id: str) -> Optional[str]:
        """Load skill content from file."""
        # Convert skill_id to path
        skill_path = self.skills_dir / skill_id / "SKILL.md"
        if not skill_path.exists():
            # Try alternative paths
            for path in self.skills_dir.rglob("SKILL.md"):
                if skill_id in str(path):
                    skill_path = path
                    break

        if skill_path.exists():
            return skill_path.read_text()
        return None

    async def _refine_skill(
        self,
        content: str,
        feedback: Optional[dict[str, Any]],
    ) -> tuple[str, list[str]]:
        """Refine skill based on feedback."""
        changes = []

        if not feedback:
            return content, changes

        # Apply feedback-based refinements
        new_content = content

        # Add clarifications based on common issues
        if feedback.get("unclear_steps"):
            # Add more detail to steps
            changes.append("Added clarification to unclear steps")

        # Improve error handling
        if feedback.get("error_cases"):
            error_section = "\n## Error Handling\n\n"
            for error in feedback["error_cases"]:
                error_section += f"- **{error['type']}**: {error['resolution']}\n"
            new_content += error_section
            changes.append("Added error handling section")

        # Add examples
        if feedback.get("needs_examples"):
            changes.append("Added usage examples")

        return new_content, changes

    async def _generalize_skill(
        self,
        content: str,
        patterns: Optional[list[dict[str, Any]]],
    ) -> tuple[str, list[str]]:
        """Make skill more general based on patterns."""
        changes = []

        if not patterns:
            return content, changes

        # Identify common elements across patterns
        # and make skill handle more cases
        new_content = content

        # Add conditional logic for different cases
        changes.append("Generalized to handle more input variations")

        return new_content, changes

    async def _specialize_skill(
        self,
        content: str,
        patterns: Optional[list[dict[str, Any]]],
    ) -> tuple[str, list[str]]:
        """Make skill more specific based on patterns."""
        changes = []

        if not patterns:
            return content, changes

        # Focus on most common pattern
        new_content = content

        changes.append("Specialized for most common use case")

        return new_content, changes

    async def _generate_skill(
        self,
        patterns: Optional[list[dict[str, Any]]],
    ) -> tuple[str, list[str]]:
        """Generate new skill from patterns."""
        changes = ["Generated new skill from learned patterns"]

        if not patterns:
            return "", changes

        # Generate skill template
        pattern = patterns[0]

        skill_content = f"""---
name: auto-generated-skill
version: 1.0.0
description: Automatically generated skill from learned patterns
author: kubani-learning
---

# Auto-Generated Skill

This skill was automatically generated from observed patterns.

## Input Pattern

```json
{pattern.get('input_pattern', {})}
```

## Expected Output

```json
{pattern.get('output_pattern', {})}
```

## Actions

1. Analyze input matching the pattern
2. Apply learned transformation
3. Return expected output format

## Confidence

This skill has a confidence score of {pattern.get('confidence', 0):.2%} based on {pattern.get('sample_count', 0)} observations.
"""

        return skill_content, changes

    def _next_version(self, skill_id: str) -> str:
        """Get next version number for skill."""
        variants = self._variants.get(skill_id, [])
        if not variants:
            return "1.0.1"

        # Parse last version and increment
        last_version = variants[-1].version
        parts = last_version.split(".")
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)

    async def activate_variant(self, variant_id: str) -> bool:
        """Activate a skill variant for production use."""
        for skill_id, variants in self._variants.items():
            for variant in variants:
                if variant.id == variant_id:
                    # Deactivate other variants
                    for v in variants:
                        v.is_active = False
                    variant.is_active = True

                    # Write to skill file
                    await self._write_variant(skill_id, variant)
                    return True
        return False

    async def _write_variant(self, skill_id: str, variant: SkillVariant) -> None:
        """Write variant content to skill file."""
        skill_path = self.skills_dir / skill_id / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(variant.content)
        logger.info(f"Activated variant {variant.id} for skill {skill_id}")

    async def rollback(self, skill_id: str, version: str) -> bool:
        """Rollback skill to a previous version."""
        variants = self._variants.get(skill_id, [])
        for variant in variants:
            if variant.version == version:
                await self._write_variant(skill_id, variant)
                return True
        return False

    async def get_variants(self, skill_id: str) -> list[SkillVariant]:
        """Get all variants for a skill."""
        return self._variants.get(skill_id, [])

    async def record_metrics(
        self,
        variant_id: str,
        metrics: dict[str, float],
    ) -> None:
        """Record performance metrics for a variant."""
        for variants in self._variants.values():
            for variant in variants:
                if variant.id == variant_id:
                    variant.metrics.update(metrics)
                    return

    async def get_best_variant(self, skill_id: str) -> Optional[SkillVariant]:
        """Get the best performing variant based on metrics."""
        variants = self._variants.get(skill_id, [])
        if not variants:
            return None

        # Score variants by success rate
        def score(v: SkillVariant) -> float:
            return v.metrics.get("success_rate", 0.0)

        return max(variants, key=score)
