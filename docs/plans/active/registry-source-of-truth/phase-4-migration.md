# Phase 4: Migration & Cutover

**Duration:** ~1 week
**Prerequisites:** Phases 1-3 complete
**Outcome:** All existing resources migrated, old system deprecated, Git export running

## Overview

This phase migrates existing filesystem-based resources to the registry, validates the migration, and cuts over to the new system. It also sets up the Git export job for audit trail.

---

## Task 4.1: Create Migration Script

**File:** `platform/cli/src/kubani_dev/commands/migrate.py`

```python
"""Migration command for moving resources to the registry."""

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
import yaml

from kubani_dev.oci import KubaniOCIClient, get_oci_client
from kubani_dev.registry_client import RegistryClient, get_registry_client
from kubani_dev.ui import console, error, info, muted, success, warning

logger = logging.getLogger(__name__)

app = typer.Typer(help="Migrate resources to the registry")


@app.command("to-registry")
def migrate_to_registry(
    project_root: Annotated[Path, typer.Option("--root", "-r", help="Project root")] = Path("."),
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview changes")] = False,
    skills: Annotated[bool, typer.Option("--skills/--no-skills", help="Migrate skills")] = True,
    agents: Annotated[bool, typer.Option("--agents/--no-agents", help="Migrate agents")] = True,
    syndicates: Annotated[bool, typer.Option("--syndicates/--no-syndicates", help="Migrate syndicates")] = True,
):
    """
    Migrate existing filesystem resources to the registry.

    This is a one-time migration that:
    1. Scans the filesystem for existing skills, agents, and syndicates
    2. Packages each as a tarball
    3. Pushes to the OCI registry
    4. Registers metadata in PostgreSQL with status=production
    """
    asyncio.run(_migrate_to_registry(project_root, dry_run, skills, agents, syndicates))


async def _migrate_to_registry(
    project_root: Path,
    dry_run: bool,
    migrate_skills: bool,
    migrate_agents: bool,
    migrate_syndicates: bool,
):
    """Run the migration."""
    project_root = project_root.resolve()

    if not (project_root / "kubani").exists():
        error(f"Not a Kubani project root: {project_root}")
        raise typer.Exit(1)

    results = {
        "skills": {"migrated": 0, "skipped": 0, "failed": 0},
        "agents": {"migrated": 0, "skipped": 0, "failed": 0},
        "syndicates": {"migrated": 0, "skipped": 0, "failed": 0},
    }

    registry = get_registry_client()
    oci = get_oci_client()

    # Migrate skills
    if migrate_skills:
        info("Migrating skills...")
        skills_dir = project_root / "kubani" / "skills"
        if skills_dir.exists():
            results["skills"] = await _migrate_skills(skills_dir, registry, oci, dry_run)
        else:
            warning(f"Skills directory not found: {skills_dir}")

    # Migrate agents
    if migrate_agents:
        info("Migrating agents...")
        agents_dir = project_root / "kubani" / "agents"
        if agents_dir.exists():
            results["agents"] = await _migrate_agents(agents_dir, registry, oci, dry_run)
        else:
            warning(f"Agents directory not found: {agents_dir}")

    # Migrate syndicates
    if migrate_syndicates:
        info("Migrating syndicates...")
        syndicates_dir = project_root / "kubani" / "syndicates"
        if syndicates_dir.exists():
            results["syndicates"] = await _migrate_syndicates(syndicates_dir, registry, oci, dry_run)
        else:
            warning(f"Syndicates directory not found: {syndicates_dir}")

    # Print summary
    console.print()
    console.print("[bold]Migration Summary[/bold]")
    console.print()

    for resource_type, counts in results.items():
        status = "✅" if counts["failed"] == 0 else "⚠️"
        console.print(
            f"  {status} {resource_type}: "
            f"[green]{counts['migrated']} migrated[/green], "
            f"[yellow]{counts['skipped']} skipped[/yellow], "
            f"[red]{counts['failed']} failed[/red]"
        )

    if dry_run:
        console.print()
        warning("Dry run - no changes made")


async def _migrate_skills(
    skills_dir: Path,
    registry: RegistryClient,
    oci: KubaniOCIClient,
    dry_run: bool,
) -> dict:
    """Migrate all skills from the filesystem."""
    counts = {"migrated": 0, "skipped": 0, "failed": 0}

    # Find all SKILL.md files
    skill_files = list(skills_dir.rglob("SKILL.md"))
    info(f"Found {len(skill_files)} skills")

    for skill_md in skill_files:
        skill_dir = skill_md.parent

        try:
            # Parse skill metadata
            metadata = _parse_skill_md(skill_md)
            name = metadata.get("name", skill_dir.name)

            # Derive domain/category from path
            rel_path = skill_dir.relative_to(skills_dir)
            parts = rel_path.parts

            if len(parts) >= 2:
                domain = parts[0]
                category = parts[1]
            elif len(parts) >= 1:
                domain = parts[0]
                category = "general"
            else:
                domain = "general"
                category = "general"

            skill_id = f"{domain}/{category}/{name}"

            # Check if already migrated
            existing = await registry.get_skill(skill_id)
            if existing and existing.current_version:
                muted(f"  Skipping {skill_id} (already in registry)")
                counts["skipped"] += 1
                continue

            if dry_run:
                info(f"  Would migrate: {skill_id}")
                counts["migrated"] += 1
                continue

            # Push to OCI
            version = metadata.get("version", "1.0.0")
            oci_result = oci.push(
                source_dir=skill_dir,
                resource_type="skill",
                name=name,
                tag=f"v{version}",
            )

            # Register in PostgreSQL
            if not existing:
                await registry.create_skill(
                    skill_id=skill_id,
                    name=name,
                    description=metadata.get("description"),
                    domain=domain,
                    category=category,
                    oci_repository=oci_result.repository,
                    created_by="migration",
                    metadata={"domain": domain, "category": category, **metadata.get("metadata", {})},
                )

            # Create version with production status
            await registry.create_skill_version(
                skill_id=skill_id,
                version=version,
                oci_tag=f"v{version}",
                oci_digest=oci_result.digest,
                created_by="migration",
                changelog="Migrated from filesystem",
            )

            # Promote directly to production
            await registry.promote_skill_version(
                skill_id=skill_id,
                version=version,
                target_status="testing",
                promoted_by="migration",
            )
            await registry.promote_skill_version(
                skill_id=skill_id,
                version=version,
                target_status="staging",
                promoted_by="migration",
            )
            await registry.promote_skill_version(
                skill_id=skill_id,
                version=version,
                target_status="production",
                promoted_by="migration",
            )

            success(f"  Migrated: {skill_id}:{version}")
            counts["migrated"] += 1

        except Exception as e:
            error(f"  Failed to migrate {skill_dir}: {e}")
            logger.exception(f"Migration failed for {skill_dir}")
            counts["failed"] += 1

    return counts


async def _migrate_agents(
    agents_dir: Path,
    registry: RegistryClient,
    oci: KubaniOCIClient,
    dry_run: bool,
) -> dict:
    """Migrate all agents from the filesystem."""
    counts = {"migrated": 0, "skipped": 0, "failed": 0}

    # Find all agent directories (have config.yaml or pyproject.toml)
    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue

        config_file = agent_dir / "config.yaml"
        pyproject_file = agent_dir / "pyproject.toml"

        if not config_file.exists() and not pyproject_file.exists():
            continue

        try:
            # Parse agent metadata
            if config_file.exists():
                config = yaml.safe_load(config_file.read_text())
                name = config.get("name", agent_dir.name)
                version = config.get("version", "1.0.0")
                description = config.get("description", "")
            else:
                import tomllib
                pyproject = tomllib.loads(pyproject_file.read_text())
                project = pyproject.get("project", {})
                name = project.get("name", agent_dir.name)
                version = project.get("version", "1.0.0")
                description = project.get("description", "")

            # Skip core-agents (it's a library)
            if name == "core-agents":
                muted(f"  Skipping {name} (library)")
                counts["skipped"] += 1
                continue

            # Check if already migrated
            existing = await registry.get_agent(name)
            if existing and existing.current_version:
                muted(f"  Skipping {name} (already in registry)")
                counts["skipped"] += 1
                continue

            if dry_run:
                info(f"  Would migrate: {name}")
                counts["migrated"] += 1
                continue

            # Push to OCI
            oci_result = oci.push(
                source_dir=agent_dir,
                resource_type="agent",
                name=name,
                tag=f"v{version}",
            )

            # Register in PostgreSQL (agents table already exists)
            # We need to add/update with OCI info
            await registry._request(
                "POST",
                "/agents",
                json={
                    "id": name,
                    "name": name,
                    "description": description,
                    "version": version,
                    "current_version": version,
                    "oci_repository": oci_result.repository,
                    "status": "production",
                    "metadata": {"source": "migration"},
                },
            )

            # Create agent version
            await registry.create_agent_version(
                agent_id=name,
                version=version,
                oci_tag=f"v{version}",
                oci_digest=oci_result.digest,
                created_by="migration",
                changelog="Migrated from filesystem",
            )

            success(f"  Migrated: {name}:{version}")
            counts["migrated"] += 1

        except Exception as e:
            error(f"  Failed to migrate {agent_dir.name}: {e}")
            logger.exception(f"Migration failed for {agent_dir}")
            counts["failed"] += 1

    return counts


async def _migrate_syndicates(
    syndicates_dir: Path,
    registry: RegistryClient,
    oci: KubaniOCIClient,
    dry_run: bool,
) -> dict:
    """Migrate all syndicates from the filesystem."""
    counts = {"migrated": 0, "skipped": 0, "failed": 0}

    # Find all syndicate directories
    for syndicate_dir in syndicates_dir.iterdir():
        if not syndicate_dir.is_dir():
            continue

        config_file = syndicate_dir / "config.yaml"
        if not config_file.exists():
            continue

        try:
            # Parse syndicate metadata
            config = yaml.safe_load(config_file.read_text())
            name = config.get("name", syndicate_dir.name)
            version = config.get("version", "1.0.0")
            description = config.get("description", "")
            agent_refs = [
                {"agent": a, "version": "latest"}
                for a in config.get("agents", [])
            ]

            # Check if already migrated
            existing = await registry.get_syndicate(name)
            if existing and existing.current_version:
                muted(f"  Skipping {name} (already in registry)")
                counts["skipped"] += 1
                continue

            if dry_run:
                info(f"  Would migrate: {name}")
                counts["migrated"] += 1
                continue

            # Push to OCI
            oci_result = oci.push(
                source_dir=syndicate_dir,
                resource_type="syndicate",
                name=name,
                tag=f"v{version}",
            )

            # Register in PostgreSQL
            await registry.create_syndicate(
                syndicate_id=name,
                name=name,
                description=description,
                oci_repository=oci_result.repository,
                created_by="migration",
                metadata={"source": "migration"},
            )

            # Create syndicate version
            await registry.create_syndicate_version(
                syndicate_id=name,
                version=version,
                oci_tag=f"v{version}",
                oci_digest=oci_result.digest,
                agent_refs=agent_refs,
                created_by="migration",
                changelog="Migrated from filesystem",
            )

            success(f"  Migrated: {name}:{version}")
            counts["migrated"] += 1

        except Exception as e:
            error(f"  Failed to migrate {syndicate_dir.name}: {e}")
            logger.exception(f"Migration failed for {syndicate_dir}")
            counts["failed"] += 1

    return counts


def _parse_skill_md(path: Path) -> dict:
    """Parse SKILL.md frontmatter."""
    content = path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
    return {}
```

**Acceptance Criteria:**
- [ ] Migration script created
- [ ] Scans skills, agents, syndicates directories
- [ ] Pushes each to OCI registry
- [ ] Registers in PostgreSQL with production status
- [ ] Dry run mode for preview
- [ ] Proper error handling and reporting

---

## Task 4.2: Create Git Export Job

**File:** `platform/cli/src/kubani_dev/commands/export.py`

```python
"""Export command for syncing registry to Git."""

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from kubani_dev.oci import get_oci_client
from kubani_dev.registry_client import get_registry_client
from kubani_dev.ui import console, error, info, muted, success, warning

logger = logging.getLogger(__name__)

app = typer.Typer(help="Export resources from registry to Git")


@app.command("to-git")
def export_to_git(
    project_root: Annotated[Path, typer.Option("--root", "-r", help="Project root")] = Path("."),
    commit: Annotated[bool, typer.Option("--commit/--no-commit", help="Create Git commit")] = True,
    push: Annotated[bool, typer.Option("--push/--no-push", help="Push to remote")] = False,
    skills: Annotated[bool, typer.Option("--skills/--no-skills", help="Export skills")] = True,
    agents: Annotated[bool, typer.Option("--agents/--no-agents", help="Export agents")] = True,
    syndicates: Annotated[bool, typer.Option("--syndicates/--no-syndicates", help="Export syndicates")] = True,
):
    """
    Export production resources from the registry to Git.

    This creates a snapshot of all production resources for version control
    and disaster recovery.
    """
    asyncio.run(_export_to_git(project_root, commit, push, skills, agents, syndicates))


async def _export_to_git(
    project_root: Path,
    do_commit: bool,
    do_push: bool,
    export_skills: bool,
    export_agents: bool,
    export_syndicates: bool,
):
    """Run the export."""
    project_root = project_root.resolve()

    registry = get_registry_client()
    oci = get_oci_client()

    changes = []

    # Export skills
    if export_skills:
        info("Exporting skills...")
        skills_dir = project_root / "kubani" / "skills"
        skill_changes = await _export_skills(skills_dir, registry, oci)
        changes.extend(skill_changes)

    # Export agents
    if export_agents:
        info("Exporting agents...")
        agents_dir = project_root / "kubani" / "agents"
        agent_changes = await _export_agents(agents_dir, registry, oci)
        changes.extend(agent_changes)

    # Export syndicates
    if export_syndicates:
        info("Exporting syndicates...")
        syndicates_dir = project_root / "kubani" / "syndicates"
        syndicate_changes = await _export_syndicates(syndicates_dir, registry, oci)
        changes.extend(syndicate_changes)

    if not changes:
        info("No changes to export")
        return

    console.print()
    info(f"Exported {len(changes)} resources")

    # Git operations
    if do_commit:
        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=project_root, check=True)

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=project_root,
            capture_output=True,
        )

        if result.returncode != 0:
            # There are changes
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            commit_msg = f"sync: export from registry ({timestamp})\n\n"
            commit_msg += "Exported resources:\n"
            for change in changes[:20]:  # Limit to 20 in commit message
                commit_msg += f"  - {change}\n"
            if len(changes) > 20:
                commit_msg += f"  ... and {len(changes) - 20} more\n"

            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=project_root,
                check=True,
            )
            success("Created Git commit")

            if do_push:
                subprocess.run(["git", "push"], cwd=project_root, check=True)
                success("Pushed to remote")
        else:
            muted("No changes to commit")


async def _export_skills(
    skills_dir: Path,
    registry,
    oci,
) -> list[str]:
    """Export all production skills."""
    changes = []

    # Get all production skills
    skills = await registry.list_skills(status="production")

    for skill in skills:
        if not skill.current_version:
            continue

        version_info = await registry.get_skill_version(
            skill.id,
            version=skill.current_version,
        )

        if not version_info or not version_info.oci_tag:
            continue

        # Determine output path
        domain = skill.metadata.get("domain", "general")
        category = skill.metadata.get("category", "general")
        output_dir = skills_dir / domain / category / skill.name

        # Pull from OCI
        try:
            oci.pull(
                resource_type="skill",
                name=skill.name,
                tag=version_info.oci_tag,
                dest_dir=output_dir,
            )
            changes.append(f"skill:{skill.id}:{skill.current_version}")
            muted(f"  Exported {skill.id}:{skill.current_version}")
        except Exception as e:
            error(f"  Failed to export {skill.id}: {e}")

    return changes


async def _export_agents(agents_dir: Path, registry, oci) -> list[str]:
    """Export all production agents."""
    changes = []

    # Get all agents with current_version
    agents = await registry._request("GET", "/agents")

    for agent in agents:
        if not agent.get("current_version"):
            continue

        name = agent["name"]
        version = agent["current_version"]
        output_dir = agents_dir / name

        try:
            oci.pull(
                resource_type="agent",
                name=name,
                tag=f"v{version}",
                dest_dir=output_dir,
            )
            changes.append(f"agent:{name}:{version}")
            muted(f"  Exported {name}:{version}")
        except Exception as e:
            error(f"  Failed to export {name}: {e}")

    return changes


async def _export_syndicates(syndicates_dir: Path, registry, oci) -> list[str]:
    """Export all production syndicates."""
    changes = []

    # Get all syndicates
    syndicates = await registry._request("GET", "/syndicates")

    for syndicate in syndicates:
        if not syndicate.get("current_version"):
            continue

        name = syndicate["name"]
        version = syndicate["current_version"]
        output_dir = syndicates_dir / name

        try:
            oci.pull(
                resource_type="syndicate",
                name=name,
                tag=f"v{version}",
                dest_dir=output_dir,
            )
            changes.append(f"syndicate:{name}:{version}")
            muted(f"  Exported {name}:{version}")
        except Exception as e:
            error(f"  Failed to export {name}: {e}")

    return changes


# Scheduled job entry point
def run_scheduled_export():
    """Entry point for scheduled export job."""
    import os

    project_root = Path(os.environ.get("KUBANI_PROJECT_ROOT", "/app/kubani"))

    asyncio.run(_export_to_git(
        project_root=project_root,
        do_commit=True,
        do_push=True,
        export_skills=True,
        export_agents=True,
        export_syndicates=True,
    ))
```

**Acceptance Criteria:**
- [ ] Export command created
- [ ] Pulls production resources from OCI
- [ ] Writes to filesystem
- [ ] Creates Git commit
- [ ] Optional push to remote
- [ ] Entry point for scheduled job

---

## Task 4.3: Create Kubernetes CronJob for Export

**File:** `infrastructure/gitops/kubani-system/registry-export-cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: registry-export
  namespace: kubani-system
spec:
  schedule: "0 * * * *"  # Every hour
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: export
              image: ghcr.io/almckay/kubani-cli:latest
              command:
                - python
                - -m
                - kubani_dev.commands.export
              env:
                - name: KUBANI_PROJECT_ROOT
                  value: /workspace
                - name: REGISTRY_URL
                  value: https://registry-api.almckay.io
                - name: KUBANI_OCI_USERNAME
                  valueFrom:
                    secretKeyRef:
                      name: oci-credentials
                      key: username
                - name: KUBANI_OCI_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: oci-credentials
                      key: password
                - name: GIT_AUTHOR_NAME
                  value: "Registry Export Bot"
                - name: GIT_AUTHOR_EMAIL
                  value: "registry-export@kubani.local"
              volumeMounts:
                - name: workspace
                  mountPath: /workspace
                - name: ssh-key
                  mountPath: /root/.ssh
                  readOnly: true
          volumes:
            - name: workspace
              persistentVolumeClaim:
                claimName: kubani-workspace
            - name: ssh-key
              secret:
                secretName: git-deploy-key
                defaultMode: 0600
          restartPolicy: OnFailure
```

**Acceptance Criteria:**
- [ ] CronJob manifest created
- [ ] Runs hourly
- [ ] Proper credentials mounting
- [ ] Git SSH key for push

---

## Task 4.4: Deprecate Old Sync Command

**File:** `platform/cli/src/kubani_dev/commands/sync.py` (update)

Add deprecation warning and redirect:

```python
"""Legacy sync command - deprecated in favor of push/pull."""

import typer

from kubani_dev.ui import warning

app = typer.Typer(help="[DEPRECATED] Use push/pull instead")


@app.callback(invoke_without_command=True)
def deprecation_warning(ctx: typer.Context):
    """Show deprecation warning."""
    warning(
        "The 'sync' command is deprecated.\n"
        "\n"
        "Use the new registry-first commands instead:\n"
        "  kubani-dev pull skill <name>     # Pull from registry\n"
        "  kubani-dev push skill <path>     # Push to registry\n"
        "  kubani-dev promote skill <name>  # Promote version\n"
        "  kubani-dev export to-git         # Export to Git\n"
        "\n"
        "For one-time migration from filesystem:\n"
        "  kubani-dev migrate to-registry\n"
    )

    if ctx.invoked_subcommand is None:
        raise typer.Exit(1)


# Keep old commands working temporarily for backwards compatibility
@app.command()
def skills(dry_run: bool = False):
    """[DEPRECATED] Sync skills to registry."""
    warning("This command is deprecated. Use 'kubani-dev push skill' instead.")
    # ... old implementation for backwards compatibility ...
```

**Acceptance Criteria:**
- [ ] Deprecation warning shown
- [ ] Points to new commands
- [ ] Old commands still work (temporarily)

---

## Task 4.5: Validation and Testing

### 4.5.1 Pre-Migration Validation

```bash
# Verify registry is accessible
curl -s https://registry-api.almckay.io/health | jq

# Verify OCI registry is accessible
oras version
oras login registry.almckay.io

# Verify database schema is up to date
cd platform/registry
alembic current
alembic heads

# List existing resources
kubani-dev sync --dry-run
```

### 4.5.2 Migration Dry Run

```bash
# Preview migration
kubani-dev migrate to-registry --dry-run

# Check output for:
# - Number of skills found
# - Number of agents found
# - Number of syndicates found
# - Any errors or warnings
```

### 4.5.3 Staged Migration

```bash
# Migrate skills first (lowest risk)
kubani-dev migrate to-registry --no-agents --no-syndicates

# Verify skills are in registry
curl -s https://registry-api.almckay.io/api/v1/skills | jq '.[] | {name, current_version, status}'

# Verify OCI artifacts exist
oras repo tags registry.almckay.io/skills/investigate-pod-failure

# Test pull
kubani-dev pull skill investigate-pod-failure --output /tmp/test-skill
ls -la /tmp/test-skill/

# If all good, migrate agents
kubani-dev migrate to-registry --no-skills --no-syndicates

# Then syndicates
kubani-dev migrate to-registry --no-skills --no-agents
```

### 4.5.4 Post-Migration Validation

```bash
# Verify all resources migrated
echo "=== Skills ==="
curl -s https://registry-api.almckay.io/api/v1/skills | jq 'length'

echo "=== Agents ==="
curl -s https://registry-api.almckay.io/api/v1/agents | jq 'length'

echo "=== Syndicates ==="
curl -s https://registry-api.almckay.io/api/v1/syndicates | jq 'length'

# Test skill loading from agent perspective
python -c "
import asyncio
from kubani.framework.registry import get_skill_loader

async def test():
    loader = get_skill_loader()
    skill = await loader.load_skill('k8s/diagnostic/investigate-pod-failure')
    print(f'Loaded: {skill.name} v{skill.version}')
    print(f'Instructions: {skill.instructions[:100]}...')

asyncio.run(test())
"

# Test Git export
kubani-dev export to-git --no-commit
git status
git diff
```

### 4.5.5 Integration Tests

**File:** `platform/cli/tests/test_migration_integration.py`

```python
"""Integration tests for migration."""

import pytest
from pathlib import Path


@pytest.mark.integration
def test_migrate_and_pull_skill(tmp_path, registry_client, oci_client):
    """Test full migration and pull cycle for a skill."""
    # Create test skill
    skill_dir = tmp_path / "skills" / "test" / "diagnostic" / "test-migrate"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: test-migrate
description: Test migration skill
version: "1.0.0"
---

# Test Migration Skill

This skill tests the migration process.
""")

    # Run migration
    # ... (call migration function)

    # Verify in registry
    skill = await registry_client.get_skill("test/diagnostic/test-migrate")
    assert skill is not None
    assert skill.current_version == "1.0.0"

    # Verify can pull
    pull_dir = tmp_path / "pulled"
    oci_client.pull(
        resource_type="skill",
        name="test-migrate",
        tag="v1.0.0",
        dest_dir=pull_dir,
    )

    assert (pull_dir / "SKILL.md").exists()
```

**Acceptance Criteria:**
- [ ] Pre-migration validation checklist
- [ ] Dry run tested
- [ ] Staged migration tested
- [ ] Post-migration validation passed
- [ ] Integration tests passing

---

## Task 4.6: Cleanup Deprecated Code

After validation period (1-2 weeks), remove deprecated code:

### 4.6.1 Remove skill_metadata Table Usage

**Files to update:**
- `platform/registry/src/kubani_registry/api/v1/skills.py` - Remove SkillMetadata references
- `platform/cli/src/kubani_dev/sync.py` - Mark for removal

### 4.6.2 Remove skill_sync_status Table

```python
# In a new migration
op.drop_table('skill_sync_status')
op.drop_table('skill_metadata')  # After data verified in new tables
```

### 4.6.3 Update Documentation

- Update CLAUDE.md to reflect new workflow
- Update README files
- Archive old sync documentation

**Acceptance Criteria:**
- [ ] Deprecated code identified
- [ ] Removal planned for after validation period
- [ ] Documentation updated

---

## Task 4.7: Register CLI Commands

**File:** `platform/cli/src/kubani_dev/cli.py` (update)

```python
# Add imports
from kubani_dev.commands import migrate, export

# Register subcommands
app.add_typer(migrate.app, name="migrate")
app.add_typer(export.app, name="export")
```

**Acceptance Criteria:**
- [ ] `kubani-dev migrate --help` works
- [ ] `kubani-dev export --help` works

---

## Commit Checkpoints

```bash
# After Task 4.1
git add platform/cli/src/kubani_dev/commands/migrate.py
git commit -m "feat(cli): add migration command for registry cutover

- Migrate skills, agents, syndicates from filesystem
- Push to OCI registry
- Register in PostgreSQL with production status
- Dry run mode for preview

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 4.2
git add platform/cli/src/kubani_dev/commands/export.py
git commit -m "feat(cli): add Git export command

- Export production resources from registry to Git
- Create Git commit with changelog
- Optional push to remote
- Entry point for scheduled job

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 4.3
git add infrastructure/gitops/kubani-system/registry-export-cronjob.yaml
git commit -m "feat(infra): add registry export CronJob

- Hourly export of production resources
- Git commit and push
- Proper credentials mounting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 4.4
git add platform/cli/src/kubani_dev/commands/sync.py
git commit -m "chore(cli): deprecate sync command

- Add deprecation warning
- Point to new push/pull commands
- Keep backwards compatibility temporarily

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 4.5
git add platform/cli/tests/
git commit -m "test(cli): add migration integration tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# After Task 4.7
git add platform/cli/src/kubani_dev/cli.py
git commit -m "feat(cli): register migrate and export commands

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Push
git push origin elegant-chaum
```

---

## Phase 4 Completion Checklist

- [ ] Migration script created and tested
- [ ] Git export command created
- [ ] Kubernetes CronJob manifest created
- [ ] Old sync command deprecated
- [ ] Pre-migration validation passed
- [ ] Dry run tested successfully
- [ ] Staged migration completed
- [ ] Post-migration validation passed
- [ ] Integration tests passing
- [ ] CLI commands registered
- [ ] All changes committed and pushed

---

## Post-Migration Monitoring

After cutover, monitor for:

1. **Registry API health** - Check latency and error rates
2. **OCI registry usage** - Storage and bandwidth
3. **Skill loading times** - Cache hit rates
4. **Agent failures** - Any skill loading errors
5. **Git export job** - Successful runs

Set up alerts for:
- Registry API 5xx errors
- OCI pull failures
- Git export job failures
- Skill cache misses > threshold
