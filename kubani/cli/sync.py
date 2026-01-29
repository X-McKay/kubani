"""
Registry Sync Command for Kubani.

Provides unified synchronization of Git resources to the registry:
- Skills (skills/**/*.md)
- Agents (agents/*/pyproject.toml)
- MCP Servers (mcp/servers/*.json)
- MCP Policies (mcp/policies/*.json)

Usage:
    kubani-dev sync              # Sync everything
    kubani-dev sync --skills     # Just skills
    kubani-dev sync --dry-run    # Preview changes
"""

import hashlib
import json
import logging
import os
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import yaml

logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    """Status of a sync operation."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class SyncItem:
    """Result of syncing a single item."""

    resource_type: str
    resource_id: str
    status: SyncStatus
    message: str = ""


@dataclass
class SyncResult:
    """Result of a sync operation."""

    items: list[SyncItem] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @property
    def created(self) -> int:
        return sum(1 for i in self.items if i.status == SyncStatus.CREATED)

    @property
    def updated(self) -> int:
        return sum(1 for i in self.items if i.status == SyncStatus.UPDATED)

    @property
    def unchanged(self) -> int:
        return sum(1 for i in self.items if i.status == SyncStatus.UNCHANGED)

    @property
    def failed(self) -> int:
        return sum(1 for i in self.items if i.status == SyncStatus.FAILED)

    def add(self, item: SyncItem) -> None:
        self.items.append(item)

    def summary(self) -> str:
        return (
            f"Synced: {self.created} created, {self.updated} updated, "
            f"{self.unchanged} unchanged, {self.failed} failed"
        )


# -----------------------------------------------------------------------------
# Scanners
# -----------------------------------------------------------------------------


@dataclass
class SkillDefinition:
    """A skill parsed from a SKILL.md file."""

    skill_id: str
    name: str
    domain: str
    category: str
    description: str
    version: str
    source_path: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path, skills_root: Path) -> "SkillDefinition | None":
        """Parse a SKILL.md file."""
        try:
            content = path.read_text()

            # Extract YAML frontmatter
            frontmatter = {}
            body = content
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()

            # Derive domain/category from path
            # e.g., skills/k8s/remediation/restart-pod/SKILL.md
            rel_path = path.relative_to(skills_root)
            parts = rel_path.parts

            if len(parts) >= 3:
                domain = parts[0]
                category = parts[1]
                name = parts[2]
            elif len(parts) >= 2:
                domain = parts[0]
                category = "general"
                name = parts[1]
            else:
                domain = "general"
                category = "general"
                name = path.parent.name

            skill_id = f"{domain}/{category}/{name}"

            # Extract description from first paragraph or frontmatter
            description = frontmatter.get("description", "")
            if not description and body:
                # Get first non-header paragraph
                for line in body.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#"):
                        description = line[:500]
                        break

            return cls(
                skill_id=skill_id,
                name=frontmatter.get("name", name),
                domain=domain,
                category=category,
                description=description,
                version=frontmatter.get("version", "1.0.0"),
                source_path=str(path),
                content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
                metadata=frontmatter.get("metadata", {}),
            )

        except Exception as e:
            logger.warning(f"Failed to parse skill: {path}: {e}")
            return None


@dataclass
class AgentDefinition:
    """An agent parsed from pyproject.toml."""

    agent_id: str
    name: str
    description: str
    version: str
    source_path: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_pyproject(cls, path: Path) -> "AgentDefinition | None":
        """Parse a pyproject.toml file."""
        try:
            content = path.read_text()
            data = tomllib.loads(content)

            project = data.get("project", {})
            name = project.get("name", path.parent.name)

            # Skip 'core' as it's a library, not a deployable agent
            if name == "core-agents":
                return None

            return cls(
                agent_id=name,
                name=name,
                description=project.get("description", ""),
                version=project.get("version", "0.0.0"),
                source_path=str(path.parent),
                metadata=data.get("tool", {}).get("kubani", {}),
            )

        except Exception as e:
            logger.warning(f"Failed to parse agent: {path}: {e}")
            return None


@dataclass
class MCPServerDefinition:
    """An MCP server parsed from JSON."""

    server_id: str
    name: str
    description: str
    transport: str
    connection_config: dict[str, Any]
    capabilities: list[str]
    namespaces: list[str] | None
    read_only: bool
    source_path: str

    @classmethod
    def from_json(cls, path: Path) -> "MCPServerDefinition | None":
        """Parse an MCP server JSON file."""
        try:
            data = json.loads(path.read_text())
            server_id = path.stem  # filename without .json

            # Build connection config from command/args/env
            connection_config = {}
            if "command" in data:
                connection_config["command"] = data["command"]
            if "args" in data:
                connection_config["args"] = data["args"]
            if "env" in data:
                connection_config["env"] = data["env"]
            if "url" in data:
                connection_config["url"] = data["url"]

            return cls(
                server_id=server_id,
                name=data.get("name", server_id),
                description=data.get("description", ""),
                transport=data.get("transport", "stdio"),
                connection_config=connection_config,
                capabilities=data.get("capabilities", []),
                namespaces=data.get("namespaces"),
                read_only=data.get("readOnly", False),
                source_path=str(path),
            )

        except Exception as e:
            logger.warning(f"Failed to parse MCP server: {path}: {e}")
            return None


@dataclass
class MCPPolicyDefinition:
    """An MCP policy parsed from JSON."""

    policy_id: str
    agent_pattern: str
    allowed_servers: list[str]
    require_approval: list[str]
    namespace_restrictions: dict[str, Any] | None
    audit_log: bool
    source_path: str

    @classmethod
    def from_json(cls, path: Path) -> "MCPPolicyDefinition | None":
        """Parse an MCP policy JSON file."""
        try:
            data = json.loads(path.read_text())
            policy_id = path.stem  # filename without .json

            # The policy filename is the agent pattern
            # e.g., k8s-monitor.json -> pattern "k8s-monitor"
            # default.json -> pattern "*" (matches all)
            agent_pattern = "*" if policy_id == "default" else policy_id

            return cls(
                policy_id=policy_id,
                agent_pattern=agent_pattern,
                allowed_servers=data.get("allowedServers", []),
                require_approval=data.get("requireApproval", []),
                namespace_restrictions=data.get("namespaceRestrictions"),
                audit_log=data.get("auditLog", False),
                source_path=str(path),
            )

        except Exception as e:
            logger.warning(f"Failed to parse MCP policy: {path}: {e}")
            return None


class ResourceScanner:
    """Scans the repository for resources to sync."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def scan_skills(self) -> list[SkillDefinition]:
        """Scan for skills in skills/ directory."""
        skills_dir = self.project_root / "skills"
        if not skills_dir.exists():
            logger.warning(f"Skills directory not found: {skills_dir}")
            return []

        skills = []
        for skill_md in skills_dir.rglob("SKILL.md"):
            skill = SkillDefinition.from_file(skill_md, skills_dir)
            if skill:
                skills.append(skill)

        logger.info(f"Found {len(skills)} skills")
        return skills

    def scan_agents(self) -> list[AgentDefinition]:
        """Scan for agents in agents/ directory."""
        agents_dir = self.project_root / "agents"
        if not agents_dir.exists():
            logger.warning(f"Agents directory not found: {agents_dir}")
            return []

        agents = []
        for pyproject in agents_dir.glob("*/pyproject.toml"):
            agent = AgentDefinition.from_pyproject(pyproject)
            if agent:
                agents.append(agent)

        logger.info(f"Found {len(agents)} agents")
        return agents

    def scan_mcp_servers(self) -> list[MCPServerDefinition]:
        """Scan for MCP servers in mcp/servers/ directory."""
        servers_dir = self.project_root / "mcp" / "servers"
        if not servers_dir.exists():
            logger.warning(f"MCP servers directory not found: {servers_dir}")
            return []

        servers = []
        for json_file in servers_dir.glob("*.json"):
            server = MCPServerDefinition.from_json(json_file)
            if server:
                servers.append(server)

        logger.info(f"Found {len(servers)} MCP servers")
        return servers

    def scan_mcp_policies(self) -> list[MCPPolicyDefinition]:
        """Scan for MCP policies in mcp/policies/ directory."""
        policies_dir = self.project_root / "mcp" / "policies"
        if not policies_dir.exists():
            logger.warning(f"MCP policies directory not found: {policies_dir}")
            return []

        policies = []
        for json_file in policies_dir.glob("*.json"):
            policy = MCPPolicyDefinition.from_json(json_file)
            if policy:
                policies.append(policy)

        logger.info(f"Found {len(policies)} MCP policies")
        return policies


# -----------------------------------------------------------------------------
# Registry Client
# -----------------------------------------------------------------------------


class RegistrySyncClient:
    """Client for syncing resources to the registry."""

    def __init__(self, registry_url: str):
        self.registry_url = registry_url.rstrip("/")

    async def sync_skill(self, skill: SkillDefinition) -> SyncItem:
        """Sync a skill to the registry."""
        from urllib.parse import quote

        try:
            async with httpx.AsyncClient() as client:
                # Check if exists (URL-encode skill_id since it contains slashes)
                encoded_id = quote(skill.skill_id, safe="")
                response = await client.get(
                    f"{self.registry_url}/api/v1/skills/{encoded_id}",
                    timeout=10.0,
                )

                payload = {
                    "id": skill.skill_id,
                    "name": skill.name,
                    "domain": skill.domain,
                    "category": skill.category,
                    "status": "stable",
                }

                if response.status_code == 404:
                    # Create new
                    response = await client.post(
                        f"{self.registry_url}/api/v1/skills",
                        json=payload,
                        timeout=10.0,
                    )
                    if response.status_code in (200, 201):
                        return SyncItem("skill", skill.skill_id, SyncStatus.CREATED)
                    else:
                        return SyncItem(
                            "skill",
                            skill.skill_id,
                            SyncStatus.FAILED,
                            f"HTTP {response.status_code}",
                        )
                elif response.status_code == 200:
                    # Skill already exists - the POST endpoint handles upsert
                    return SyncItem("skill", skill.skill_id, SyncStatus.UNCHANGED)
                else:
                    return SyncItem(
                        "skill",
                        skill.skill_id,
                        SyncStatus.FAILED,
                        f"HTTP {response.status_code}",
                    )

        except Exception as e:
            return SyncItem("skill", skill.skill_id, SyncStatus.FAILED, str(e))

    async def sync_agent(self, agent: AgentDefinition) -> SyncItem:
        """Sync an agent to the registry."""
        try:
            async with httpx.AsyncClient() as client:
                # Check if exists
                response = await client.get(
                    f"{self.registry_url}/api/v1/agents/{agent.agent_id}",
                    timeout=10.0,
                )

                payload = {
                    "id": agent.agent_id,
                    "name": agent.name,
                    "description": agent.description,
                    "version": agent.version,
                    "metadata": {
                        **agent.metadata,
                        "source_path": agent.source_path,
                        "source": "git",
                    },
                }

                if response.status_code == 404:
                    # Create new
                    response = await client.post(
                        f"{self.registry_url}/api/v1/agents",
                        json=payload,
                        timeout=10.0,
                    )
                    if response.status_code in (200, 201):
                        return SyncItem("agent", agent.agent_id, SyncStatus.CREATED)
                    else:
                        return SyncItem(
                            "agent",
                            agent.agent_id,
                            SyncStatus.FAILED,
                            f"HTTP {response.status_code}",
                        )
                elif response.status_code == 200:
                    # Check if version changed
                    existing = response.json()
                    if existing.get("version") == agent.version:
                        return SyncItem("agent", agent.agent_id, SyncStatus.UNCHANGED)

                    # Update via POST (upsert behavior)
                    response = await client.post(
                        f"{self.registry_url}/api/v1/agents",
                        json=payload,
                        timeout=10.0,
                    )
                    if response.status_code in (200, 201):
                        return SyncItem("agent", agent.agent_id, SyncStatus.UPDATED)
                    else:
                        return SyncItem(
                            "agent",
                            agent.agent_id,
                            SyncStatus.FAILED,
                            f"HTTP {response.status_code}",
                        )
                else:
                    return SyncItem(
                        "agent",
                        agent.agent_id,
                        SyncStatus.FAILED,
                        f"HTTP {response.status_code}",
                    )

        except Exception as e:
            return SyncItem("agent", agent.agent_id, SyncStatus.FAILED, str(e))

    async def sync_mcp_server(self, server: MCPServerDefinition) -> SyncItem:
        """Sync an MCP server to the registry."""
        try:
            async with httpx.AsyncClient() as client:
                # Check if exists
                response = await client.get(
                    f"{self.registry_url}/api/v1/mcp/servers/{server.server_id}",
                    timeout=10.0,
                )

                payload = {
                    "id": server.server_id,
                    "name": server.name,
                    "description": server.description,
                    "transport": server.transport,
                    "connection_config": server.connection_config,
                    "capabilities": server.capabilities,
                    "namespaces": server.namespaces,
                    "read_only": server.read_only,
                }

                if response.status_code == 404:
                    # Create new
                    response = await client.post(
                        f"{self.registry_url}/api/v1/mcp/servers",
                        json=payload,
                        timeout=10.0,
                    )
                    if response.status_code in (200, 201):
                        return SyncItem("mcp_server", server.server_id, SyncStatus.CREATED)
                    else:
                        return SyncItem(
                            "mcp_server",
                            server.server_id,
                            SyncStatus.FAILED,
                            f"HTTP {response.status_code}: {response.text}",
                        )
                elif response.status_code == 200:
                    # MCP servers don't have a version, so just mark unchanged
                    # Could compare capabilities/config for more precise detection
                    return SyncItem("mcp_server", server.server_id, SyncStatus.UNCHANGED)
                else:
                    return SyncItem(
                        "mcp_server",
                        server.server_id,
                        SyncStatus.FAILED,
                        f"HTTP {response.status_code}",
                    )

        except Exception as e:
            return SyncItem("mcp_server", server.server_id, SyncStatus.FAILED, str(e))

    async def sync_mcp_policy(
        self, policy: MCPPolicyDefinition, server_ids: list[str]
    ) -> list[SyncItem]:
        """
        Sync an MCP policy to the registry.

        Policies are per-server, so we create one registry policy per allowed server.
        """
        results = []

        for server_id in policy.allowed_servers:
            if server_id not in server_ids:
                results.append(
                    SyncItem(
                        "mcp_policy",
                        f"{policy.policy_id}/{server_id}",
                        SyncStatus.SKIPPED,
                        f"Server {server_id} not found",
                    )
                )
                continue

            try:
                async with httpx.AsyncClient() as client:
                    payload = {
                        "agent_pattern": policy.agent_pattern,
                        "server_id": server_id,
                        "allowed_tools": None,  # All tools allowed
                        "require_approval": policy.require_approval,
                        "namespace_restrictions": policy.namespace_restrictions,
                        "priority": 0 if policy.policy_id == "default" else 10,
                    }

                    # Always try to create - the API should handle duplicates
                    response = await client.post(
                        f"{self.registry_url}/api/v1/mcp/policies",
                        json=payload,
                        timeout=10.0,
                    )

                    if response.status_code in (200, 201):
                        results.append(
                            SyncItem(
                                "mcp_policy",
                                f"{policy.agent_pattern}/{server_id}",
                                SyncStatus.CREATED,
                            )
                        )
                    elif response.status_code == 400 and "already exists" in response.text.lower():
                        results.append(
                            SyncItem(
                                "mcp_policy",
                                f"{policy.agent_pattern}/{server_id}",
                                SyncStatus.UNCHANGED,
                            )
                        )
                    else:
                        results.append(
                            SyncItem(
                                "mcp_policy",
                                f"{policy.agent_pattern}/{server_id}",
                                SyncStatus.FAILED,
                                f"HTTP {response.status_code}",
                            )
                        )

            except Exception as e:
                results.append(
                    SyncItem(
                        "mcp_policy",
                        f"{policy.agent_pattern}/{server_id}",
                        SyncStatus.FAILED,
                        str(e),
                    )
                )

        return results


# -----------------------------------------------------------------------------
# Sync Orchestrator
# -----------------------------------------------------------------------------


class RegistrySync:
    """Orchestrates syncing Git resources to the registry."""

    def __init__(
        self,
        project_root: Path,
        registry_url: str | None = None,
    ):
        self.project_root = project_root
        self.registry_url = registry_url or os.environ.get("REGISTRY_URL", "http://localhost:8000")
        self.scanner = ResourceScanner(project_root)
        self.client = RegistrySyncClient(self.registry_url)

    async def sync_skills(self, dry_run: bool = False) -> SyncResult:
        """Sync skills to the registry."""
        result = SyncResult()
        skills = self.scanner.scan_skills()

        for skill in skills:
            if dry_run:
                result.add(SyncItem("skill", skill.skill_id, SyncStatus.SKIPPED, "dry-run"))
            else:
                item = await self.client.sync_skill(skill)
                result.add(item)

        result.completed_at = datetime.now(UTC)
        return result

    async def sync_agents(self, dry_run: bool = False) -> SyncResult:
        """Sync agents to the registry."""
        result = SyncResult()
        agents = self.scanner.scan_agents()

        for agent in agents:
            if dry_run:
                result.add(SyncItem("agent", agent.agent_id, SyncStatus.SKIPPED, "dry-run"))
            else:
                item = await self.client.sync_agent(agent)
                result.add(item)

        result.completed_at = datetime.now(UTC)
        return result

    async def sync_mcp_servers(self, dry_run: bool = False) -> SyncResult:
        """Sync MCP servers to the registry."""
        result = SyncResult()
        servers = self.scanner.scan_mcp_servers()

        for server in servers:
            if dry_run:
                result.add(SyncItem("mcp_server", server.server_id, SyncStatus.SKIPPED, "dry-run"))
            else:
                item = await self.client.sync_mcp_server(server)
                result.add(item)

        result.completed_at = datetime.now(UTC)
        return result

    async def sync_mcp_policies(self, dry_run: bool = False) -> SyncResult:
        """Sync MCP policies to the registry."""
        result = SyncResult()
        policies = self.scanner.scan_mcp_policies()
        servers = self.scanner.scan_mcp_servers()
        server_ids = [s.server_id for s in servers]

        for policy in policies:
            if dry_run:
                for server_id in policy.allowed_servers:
                    result.add(
                        SyncItem(
                            "mcp_policy",
                            f"{policy.agent_pattern}/{server_id}",
                            SyncStatus.SKIPPED,
                            "dry-run",
                        )
                    )
            else:
                items = await self.client.sync_mcp_policy(policy, server_ids)
                for item in items:
                    result.add(item)

        result.completed_at = datetime.now(UTC)
        return result

    async def sync_all(
        self,
        dry_run: bool = False,
        skills: bool = True,
        agents: bool = True,
        mcp: bool = True,
    ) -> dict[str, SyncResult]:
        """Sync all resources to the registry."""
        results = {}

        if skills:
            results["skills"] = await self.sync_skills(dry_run)
        if agents:
            results["agents"] = await self.sync_agents(dry_run)
        if mcp:
            results["mcp_servers"] = await self.sync_mcp_servers(dry_run)
            results["mcp_policies"] = await self.sync_mcp_policies(dry_run)

        return results


# -----------------------------------------------------------------------------
# CLI Output Helpers
# -----------------------------------------------------------------------------


def print_sync_results(results: dict[str, SyncResult]) -> None:
    """Print sync results to console."""
    from kubani.cli.ui import (
        console,
        create_table,
        error,
        header,
        muted,
        success,
    )

    for resource_type, result in results.items():
        console.print()
        header(resource_type.upper())

        if not result.items:
            muted("  No items found")
            continue

        table = create_table(columns=["ID", "Status", "Message"])

        for item in result.items:
            status_style = {
                SyncStatus.CREATED: "green",
                SyncStatus.UPDATED: "yellow",
                SyncStatus.UNCHANGED: "dim",
                SyncStatus.FAILED: "red",
                SyncStatus.SKIPPED: "blue",
            }.get(item.status, "white")

            table.add_row(
                item.resource_id,
                f"[{status_style}]{item.status.value}[/{status_style}]",
                item.message,
            )

        console.print(table)
        muted(f"  {result.summary()}")

    # Overall summary
    console.print()
    header("Summary")
    total_created = sum(r.created for r in results.values())
    total_updated = sum(r.updated for r in results.values())
    total_unchanged = sum(r.unchanged for r in results.values())
    total_failed = sum(r.failed for r in results.values())

    console.print(
        f"  [green]{total_created} created[/green], "
        f"[yellow]{total_updated} updated[/yellow], "
        f"[dim]{total_unchanged} unchanged[/dim], "
        f"[red]{total_failed} failed[/red]"
    )

    console.print()
    if total_failed > 0:
        error("Sync completed with errors")
    else:
        success("Sync completed successfully")
