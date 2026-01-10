"""
Skills MCP Server - Expose Kubani skills as discoverable MCP tools.

This module implements Recommendation #4 from the comprehensive improvement plan:
"Expose Skills as Discoverable MCP Servers"

By exposing skills via MCP, external systems can:
1. Discover available skills dynamically
2. Invoke skills using the standard MCP protocol
3. Build skill marketplaces and sharing platforms

The server wraps skill definitions and makes them callable via MCP,
enabling interoperability with any MCP-compatible agent framework.

Usage:
    from core_agents.skills.mcp_server import SkillsMCPServer

    # Create server with skills from a directory
    server = SkillsMCPServer(skills_dir="/path/to/skills")

    # Start the server
    await server.start(host="0.0.0.0", port=8000)

    # Or get the FastAPI app for integration
    app = server.to_fastapi_app()
"""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPToolDefinition:
    """Definition of an MCP tool derived from a skill."""

    name: str
    description: str
    input_schema: dict[str, Any]
    skill_path: str
    category: str
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)


@dataclass
class MCPToolResult:
    """Result from executing an MCP tool."""

    success: bool
    content: Any
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SkillsMCPServer:
    """
    MCP Server that exposes Kubani skills as discoverable tools.

    This server implements the Model Context Protocol (MCP) to make
    skills available to external agents and systems.

    Features:
    - Automatic skill discovery from directory
    - Dynamic tool registration
    - Standard MCP protocol compliance
    - Skill execution with validation
    """

    def __init__(
        self,
        skills_dir: str | Path,
        server_name: str = "kubani-skills",
        server_version: str = "1.0.0",
    ):
        """
        Initialize the Skills MCP Server.

        Args:
            skills_dir: Directory containing skill definitions
            server_name: Name for the MCP server
            server_version: Version of the server
        """
        self.skills_dir = Path(skills_dir)
        self.server_name = server_name
        self.server_version = server_version

        self._tools: dict[str, MCPToolDefinition] = {}
        self._tool_handlers: dict[str, Callable] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the server by loading skills."""
        if self._initialized:
            return

        logger.info(f"Initializing Skills MCP Server from {self.skills_dir}")

        # Discover and load skills
        await self._discover_skills()

        self._initialized = True
        logger.info(f"Loaded {len(self._tools)} skills as MCP tools")

    async def _discover_skills(self) -> None:
        """Discover skills from the skills directory."""
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return

        # Find all SKILL.md files
        for skill_file in self.skills_dir.rglob("SKILL.md"):
            try:
                await self._load_skill(skill_file)
            except Exception as e:
                logger.warning(f"Failed to load skill from {skill_file}: {e}")

    async def _load_skill(self, skill_file: Path) -> None:
        """Load a skill definition and register it as an MCP tool."""
        content = skill_file.read_text()

        # Parse skill metadata from frontmatter
        metadata = self._parse_skill_frontmatter(content)
        if not metadata:
            return

        # Create tool definition
        skill_path = str(skill_file.parent.relative_to(self.skills_dir))
        tool_name = skill_path.replace("/", "-").replace("\\", "-")

        tool = MCPToolDefinition(
            name=tool_name,
            description=metadata.get("description", ""),
            input_schema=self._build_input_schema(metadata),
            skill_path=skill_path,
            category=metadata.get("category", "general"),
            version=metadata.get("version", "1.0.0"),
            tags=metadata.get("tags", []),
        )

        self._tools[tool_name] = tool
        self._tool_handlers[tool_name] = self._create_tool_handler(tool, skill_file)

        logger.debug(f"Registered skill as MCP tool: {tool_name}")

    def _parse_skill_frontmatter(self, content: str) -> dict[str, Any]:
        """Parse YAML frontmatter from skill markdown."""
        if not content.startswith("---"):
            return {}

        try:
            import yaml

            # Find end of frontmatter
            end_idx = content.find("---", 3)
            if end_idx == -1:
                return {}

            frontmatter = content[3:end_idx].strip()
            return yaml.safe_load(frontmatter) or {}

        except Exception as e:
            logger.warning(f"Failed to parse skill frontmatter: {e}")
            return {}

    def _build_input_schema(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Build JSON Schema for tool input from skill metadata."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        # Extract inputs from skill metadata
        inputs = metadata.get("inputs", metadata.get("input_schema", {}))
        if isinstance(inputs, dict):
            for name, spec in inputs.items():
                if isinstance(spec, dict):
                    schema["properties"][name] = {
                        "type": spec.get("type", "string"),
                        "description": spec.get("description", ""),
                    }
                    if spec.get("required", False):
                        schema["required"].append(name)
                else:
                    schema["properties"][name] = {
                        "type": "string",
                        "description": str(spec),
                    }

        return schema

    def _create_tool_handler(
        self,
        tool: MCPToolDefinition,
        skill_file: Path,
    ) -> Callable:
        """Create a handler function for executing the skill."""

        async def handler(arguments: dict[str, Any]) -> MCPToolResult:
            """Execute the skill with given arguments."""
            try:
                # Import skill runner
                from core_agents.skills import SkillRunner

                runner = SkillRunner(skills_dir=self.skills_dir)

                # Execute the skill
                result = await runner.execute_skill(
                    skill_path=tool.skill_path,
                    inputs=arguments,
                )

                return MCPToolResult(
                    success=True,
                    content=result,
                    metadata={
                        "skill_path": tool.skill_path,
                        "version": tool.version,
                    },
                )

            except Exception as e:
                logger.error(f"Skill execution failed: {e}")
                return MCPToolResult(
                    success=False,
                    content=None,
                    error=str(e),
                )

        return handler

    def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools in MCP format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:
        """
        Call a tool by name with given arguments.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            MCPToolResult with execution result
        """
        if name not in self._tool_handlers:
            return MCPToolResult(
                success=False,
                content=None,
                error=f"Unknown tool: {name}",
            )

        handler = self._tool_handlers[name]
        return await handler(arguments)

    def to_fastapi_app(self):
        """
        Create a FastAPI app implementing the MCP protocol.

        Returns:
            FastAPI application instance
        """
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel

        app = FastAPI(
            title=self.server_name,
            version=self.server_version,
            description="Kubani Skills exposed via MCP protocol",
        )

        class ToolCallRequest(BaseModel):
            name: str
            arguments: dict[str, Any] = {}

        class MCPRequest(BaseModel):
            jsonrpc: str = "2.0"
            id: int | str
            method: str
            params: dict[str, Any] = {}

        @app.on_event("startup")
        async def startup():
            await self.initialize()

        @app.get("/health")
        async def health():
            return {"status": "healthy", "tools": len(self._tools)}

        @app.get("/tools")
        async def list_tools():
            """List available tools."""
            return {"tools": self.list_tools()}

        @app.post("/tools/call")
        async def call_tool(request: ToolCallRequest):
            """Call a tool."""
            result = await self.call_tool(request.name, request.arguments)
            if not result.success:
                raise HTTPException(status_code=400, detail=result.error)
            return {"content": result.content, "metadata": result.metadata}

        @app.post("/mcp")
        async def mcp_endpoint(request: MCPRequest):
            """
            MCP JSON-RPC endpoint.

            Implements the standard MCP protocol methods:
            - tools/list: List available tools
            - tools/call: Call a tool
            """
            if request.method == "tools/list":
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": request.id,
                        "result": {"tools": self.list_tools()},
                    }
                )

            elif request.method == "tools/call":
                name = request.params.get("name")
                arguments = request.params.get("arguments", {})

                if not name:
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": request.id,
                            "error": {"code": -32602, "message": "Missing tool name"},
                        }
                    )

                result = await self.call_tool(name, arguments)

                if result.success:
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": request.id,
                            "result": {
                                "content": [{"type": "text", "text": json.dumps(result.content)}],
                                "isError": False,
                            },
                        }
                    )
                else:
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": request.id,
                            "result": {
                                "content": [{"type": "text", "text": result.error}],
                                "isError": True,
                            },
                        }
                    )

            else:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": request.id,
                        "error": {"code": -32601, "message": f"Unknown method: {request.method}"},
                    }
                )

        return app

    async def start(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
    ) -> None:
        """
        Start the MCP server.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        import uvicorn

        await self.initialize()
        app = self.to_fastapi_app()

        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()


async def run_skills_mcp_server(
    skills_dir: str = "skills",
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    """
    Run the Skills MCP Server.

    Args:
        skills_dir: Directory containing skill definitions
        host: Host to bind to
        port: Port to bind to
    """
    server = SkillsMCPServer(skills_dir=skills_dir)
    await server.start(host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Skills MCP Server")
    parser.add_argument("--skills-dir", default="skills", help="Skills directory")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")

    args = parser.parse_args()

    asyncio.run(
        run_skills_mcp_server(
            skills_dir=args.skills_dir,
            host=args.host,
            port=args.port,
        )
    )
