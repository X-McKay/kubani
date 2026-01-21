---
name: mcp-builder
description: Build MCP (Model Context Protocol) servers for Claude Code integration. Use when creating tools, resources, or prompts that extend Claude's capabilities. Supports Python FastMCP and TypeScript implementations.
---

# MCP Server Builder

Create MCP servers that extend Claude Code's capabilities with custom tools, resources, and prompts.

## Arguments

- `server-name`: Name for the MCP server (lowercase, hyphenated)
- `--lang`: Implementation language: `python` (default), `typescript`
- `--type`: Server type: `tools`, `resources`, `hybrid` (default: tools)

## Instructions

### Phase 1: Design the MCP Server

Before writing code, answer these questions:

1. **What capabilities does this server provide?**
   - Tools (actions Claude can perform)
   - Resources (data Claude can read)
   - Prompts (templates Claude can use)

2. **What external services does it integrate with?**
   - APIs (REST, GraphQL)
   - Databases
   - File systems
   - Other services

3. **What inputs/outputs does each tool need?**
   - Required parameters
   - Optional parameters with defaults
   - Return value structure

### Phase 2: Project Setup

#### Python (FastMCP - Recommended)

```bash
cd /home/al/git/kubani
mkdir -p mcp-servers/${SERVER_NAME}
cd mcp-servers/${SERVER_NAME}

# Create pyproject.toml
cat > pyproject.toml << 'EOF'
[project]
name = "${SERVER_NAME}"
version = "0.1.0"
description = "MCP server for [description]"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.9.0",
    "httpx>=0.27.0",
    "pydantic>=2.5.0",
]

[project.scripts]
${SERVER_NAME} = "${SERVER_NAME//-/_}.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
EOF

# Create package structure
mkdir -p src/${SERVER_NAME//-/_}
touch src/${SERVER_NAME//-/_}/__init__.py
```

#### TypeScript

```bash
cd /home/al/git/kubani
mkdir -p mcp-servers/${SERVER_NAME}
cd mcp-servers/${SERVER_NAME}

npm init -y
npm install @modelcontextprotocol/sdk zod

# Create tsconfig.json
cat > tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "esModuleInterop": true,
    "outDir": "./dist",
    "rootDir": "./src"
  },
  "include": ["src/**/*"]
}
EOF

mkdir -p src
```

### Phase 3: Implement the Server

#### Python FastMCP Template

Create `src/${SERVER_NAME//-/_}/server.py`:

```python
"""${SERVER_NAME} MCP Server."""

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# Initialize server
mcp = FastMCP(
    "${SERVER_NAME}",
    description="Description of what this server provides",
)


# Define input/output models with Pydantic
class ToolInput(BaseModel):
    """Input schema for the tool."""

    required_param: str = Field(description="Description of this parameter")
    optional_param: int = Field(default=10, description="Optional with default")


class ToolOutput(BaseModel):
    """Output schema for the tool."""

    result: str
    success: bool


# Define tools with the @mcp.tool() decorator
@mcp.tool()
async def example_tool(
    required_param: str,
    optional_param: int = 10,
) -> str:
    """
    Description of what this tool does.

    This docstring becomes the tool description that Claude sees.
    Be specific about:
    - What the tool does
    - When to use it
    - What it returns

    Args:
        required_param: Description of required parameter
        optional_param: Description of optional parameter

    Returns:
        Description of the return value
    """
    # Implementation
    result = f"Processed {required_param} with {optional_param}"
    return result


# Tool with annotations for behavior hints
@mcp.tool(
    annotations={
        "readOnlyHint": True,      # Doesn't modify state
        "idempotentHint": True,    # Safe to retry
        "openWorldHint": False,    # Doesn't access external services
    }
)
async def read_only_tool(query: str) -> str:
    """A read-only tool that doesn't modify any state."""
    return f"Results for: {query}"


@mcp.tool(
    annotations={
        "destructiveHint": True,   # Modifies/deletes data
    }
)
async def destructive_tool(item_id: str) -> str:
    """A tool that modifies or deletes data. Use with caution."""
    return f"Deleted: {item_id}"


# Define resources for data Claude can read
@mcp.resource("config://settings")
async def get_settings() -> str:
    """Return current configuration settings."""
    return "key=value\nother=setting"


# Dynamic resources with URI templates
@mcp.resource("file://{path}")
async def read_file(path: str) -> str:
    """Read a file by path."""
    # Implementation with proper error handling
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found: {path}"


# Define prompts (templates)
@mcp.prompt()
async def analyze_prompt(topic: str) -> str:
    """Generate an analysis prompt for a topic."""
    return f"""Please analyze the following topic thoroughly:

Topic: {topic}

Consider:
1. Key concepts
2. Relationships
3. Implications
"""


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
```

#### TypeScript Template

Create `src/index.ts`:

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

// Define input schemas with Zod
const ExampleInputSchema = z.object({
  requiredParam: z.string().describe("Description of required parameter"),
  optionalParam: z.number().default(10).describe("Optional with default"),
});

// Create server
const server = new McpServer({
  name: "${SERVER_NAME}",
  version: "0.1.0",
});

// Register tools
server.tool(
  "example_tool",
  "Description of what this tool does",
  ExampleInputSchema.shape,
  async ({ requiredParam, optionalParam }) => {
    const result = `Processed ${requiredParam} with ${optionalParam}`;
    return {
      content: [{ type: "text", text: result }],
    };
  }
);

// Register resources
server.resource(
  "config://settings",
  "Current configuration settings",
  async () => ({
    contents: [
      {
        uri: "config://settings",
        mimeType: "text/plain",
        text: "key=value\nother=setting",
      },
    ],
  })
);

// Start server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch(console.error);
```

### Phase 4: Tool Design Best Practices

#### Agent-Centric Design

```python
# BAD: Thin API wrapper
@mcp.tool()
async def get_user(user_id: str) -> str:
    """Get user by ID."""
    return api.get_user(user_id)

# GOOD: Workflow-oriented tool
@mcp.tool()
async def get_user_with_context(
    user_id: str,
    include_recent_activity: bool = True,
    include_permissions: bool = False,
) -> str:
    """
    Get comprehensive user information for decision-making.

    Returns user profile along with relevant context like
    recent activity and permissions when needed for
    access decisions or troubleshooting.
    """
    user = api.get_user(user_id)
    result = {"user": user}

    if include_recent_activity:
        result["recent_activity"] = api.get_activity(user_id, limit=5)

    if include_permissions:
        result["permissions"] = api.get_permissions(user_id)

    return json.dumps(result, indent=2)
```

#### Error Handling

```python
@mcp.tool()
async def safe_tool(param: str) -> str:
    """Tool with proper error handling."""
    try:
        result = await external_api_call(param)
        return json.dumps({"success": True, "data": result})
    except ConnectionError:
        return json.dumps({
            "success": False,
            "error": "Cannot connect to service. Check network or try again.",
            "suggestion": "Verify the service is running with /cluster-health"
        })
    except ValueError as e:
        return json.dumps({
            "success": False,
            "error": f"Invalid input: {e}",
            "suggestion": "Check parameter format and try again"
        })
```

#### Return Actionable Information

```python
# BAD: Raw data dump
@mcp.tool()
async def check_status() -> str:
    return json.dumps(api.get_all_data())

# GOOD: Curated, actionable response
@mcp.tool()
async def check_status() -> str:
    """Check system status and highlight issues needing attention."""
    data = api.get_all_data()

    issues = [item for item in data if item["status"] != "healthy"]

    if not issues:
        return "All systems healthy. No action needed."

    return json.dumps({
        "summary": f"{len(issues)} issues found",
        "issues": issues,
        "suggested_actions": [
            f"Investigate {i['name']}: {i['error']}"
            for i in issues[:3]
        ]
    })
```

### Phase 5: Register with Claude Code

Add to `/home/al/git/kubani/.mcp.json`:

```json
{
  "mcpServers": {
    "${SERVER_NAME}": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/home/al/git/kubani/mcp-servers/${SERVER_NAME}",
        "${SERVER_NAME}"
      ]
    }
  }
}
```

For TypeScript:
```json
{
  "mcpServers": {
    "${SERVER_NAME}": {
      "command": "node",
      "args": [
        "/home/al/git/kubani/mcp-servers/${SERVER_NAME}/dist/index.js"
      ]
    }
  }
}
```

### Phase 6: Test the Server

#### Manual Testing

```bash
cd /home/al/git/kubani/mcp-servers/${SERVER_NAME}

# Python: Run directly
uv run python -m ${SERVER_NAME//-/_}.server

# TypeScript: Build and run
npm run build
node dist/index.js
```

#### Test with Claude Code

After adding to `.mcp.json`:
1. Restart Claude Code or run `/mcp`
2. Ask Claude to use the new tools
3. Verify tool discovery with `/tools`

### Phase 7: Kubernetes Deployment (Optional)

For MCP servers that need to run as cluster services:

Create `gitops/apps/mcp-servers/${SERVER_NAME}/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${SERVER_NAME}
  namespace: mcp-servers
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${SERVER_NAME}
  template:
    metadata:
      labels:
        app: ${SERVER_NAME}
    spec:
      containers:
        - name: server
          image: registry.almckay.io/${SERVER_NAME}:0.1.0
          ports:
            - containerPort: 8080
          env:
            - name: FASTMCP_HOST
              value: "0.0.0.0"
            - name: FASTMCP_PORT
              value: "8080"
```

## Tool Annotation Reference

| Annotation | Type | Description |
|------------|------|-------------|
| `readOnlyHint` | bool | Tool only reads data, no side effects |
| `destructiveHint` | bool | Tool may delete or modify data irreversibly |
| `idempotentHint` | bool | Safe to call multiple times with same result |
| `openWorldHint` | bool | Tool interacts with external/untrusted services |

## Common Patterns

### Kubernetes Integration Tool

```python
@mcp.tool(annotations={"readOnlyHint": True})
async def kubectl_get(
    resource: str,
    namespace: str = "default",
    label_selector: str | None = None,
) -> str:
    """
    Get Kubernetes resources.

    Args:
        resource: Resource type (pods, deployments, services)
        namespace: Kubernetes namespace
        label_selector: Filter by labels (e.g., "app=nginx")
    """
    cmd = ["kubectl", "get", resource, "-n", namespace, "-o", "json"]
    if label_selector:
        cmd.extend(["-l", label_selector])

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout
```

### API Integration Tool

```python
import httpx

@mcp.tool()
async def api_request(
    endpoint: str,
    method: str = "GET",
    body: str | None = None,
) -> str:
    """Make an API request to the configured service."""
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=f"{API_BASE_URL}{endpoint}",
            json=json.loads(body) if body else None,
            headers={"Authorization": f"Bearer {API_TOKEN}"}
        )
        return response.text
```

### Database Query Tool

```python
@mcp.tool(annotations={"readOnlyHint": True})
async def query_database(
    query: str,
    limit: int = 100,
) -> str:
    """
    Execute a read-only SQL query.

    Only SELECT queries are allowed. Results limited for safety.
    """
    if not query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries allowed"

    # Add LIMIT if not present
    if "LIMIT" not in query.upper():
        query = f"{query} LIMIT {limit}"

    # Execute and return results
    results = await db.execute(query)
    return json.dumps(results, indent=2)
```

## Troubleshooting

### Server won't start
- Check Python/Node version compatibility
- Verify all dependencies installed: `uv sync` or `npm install`
- Check for syntax errors: `python -m py_compile server.py`

### Tools not appearing in Claude
- Verify `.mcp.json` syntax is valid JSON
- Check server path is absolute
- Restart Claude Code after config changes
- Check server logs for errors

### Tool calls failing
- Add logging to tool functions
- Check input validation matches schema
- Verify external service connectivity
- Test tool in isolation first
