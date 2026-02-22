FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js via mise (needed by mcp-server-fetch for Readability.js)
ENV MISE_DATA_DIR="/opt/mise"
RUN curl https://mise.run | sh \
    && /root/.local/bin/mise install node@lts \
    && /root/.local/bin/mise use --global node@lts
ENV PATH="/opt/mise/shims:$PATH"

# Copy workspace root for installable package
COPY pyproject.toml README.md ./
COPY kubani/ kubani/

# Install the kubani package with all needed optional deps:
#   events = redis, skills = qdrant-client
# Plus additional runtime deps for the orchestrator
RUN pip install --no-cache-dir -e ".[events,skills]" \
    && pip install --no-cache-dir asyncpg duckduckgo-search mcp-server-fetch

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

CMD ["python", "-m", "kubani.nexus.orchestrator.worker"]
