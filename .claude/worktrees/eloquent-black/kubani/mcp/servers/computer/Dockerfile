# =============================================================================
# Computer Use MCP Server
# =============================================================================
# MCP server for browser control via Playwright with Xvfb + noVNC
#
# Build from repo root:
#   docker build -f kubani/mcp/servers/computer/Dockerfile -t computer-mcp-server .
# =============================================================================

FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv system-wide
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    mv /root/.local/bin/uvx /usr/local/bin/uvx
ENV PATH="/usr/local/bin:$PATH"

# Copy workspace root files
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md

# Copy kubani package (framework)
COPY kubani/__init__.py /app/kubani/__init__.py
COPY kubani/framework /app/kubani/framework

# Create MCP servers directory structure
RUN mkdir -p /app/kubani/mcp/servers/computer

# Copy this MCP server
COPY kubani/mcp/servers/computer/pyproject.toml /app/kubani/mcp/servers/computer/pyproject.toml
COPY kubani/mcp/servers/computer/src /app/kubani/mcp/servers/computer/src

# Update workspace to include only this MCP server
RUN python3 -c "\
import re; \
f = open('/app/pyproject.toml', 'r'); content = f.read(); f.close(); \
content = re.sub( \
    r'(\[tool\.uv\.workspace\])\s*members\s*=\s*\[[^\]]*\]', \
    r'\1\nmembers = [\"kubani/mcp/servers/computer\"]', \
    content \
); \
f = open('/app/pyproject.toml', 'w'); f.write(content); f.close()"

# Install dependencies
RUN uv sync --package computer-mcp-server --no-dev

# Install Playwright Chromium with system deps
RUN /app/.venv/bin/playwright install chromium --with-deps

# Copy startup script
COPY kubani/mcp/servers/computer/start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 8086 6080

ENTRYPOINT ["/app/start.sh"]

# Labels
LABEL org.opencontainers.image.title="computer-mcp-server"
LABEL org.opencontainers.image.description="Computer Use MCP server for Kubani"
