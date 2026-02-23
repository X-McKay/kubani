FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js via mise (needed by mcp-server-fetch for Readability.js)
# Note: mise's npm/npx wrappers use relative paths that break when symlinked,
# so we create small shell scripts that invoke npm-cli.js/npx-cli.js directly.
ENV MISE_DATA_DIR="/opt/mise"
RUN curl https://mise.run | sh \
    && /root/.local/bin/mise install node@lts \
    && ln -s /opt/mise/installs/node/lts/bin/node /usr/local/bin/node \
    && printf '#!/bin/sh\nexec /usr/local/bin/node /opt/mise/installs/node/lts/lib/node_modules/npm/bin/npm-cli.js "$@"\n' > /usr/local/bin/npm \
    && chmod +x /usr/local/bin/npm \
    && printf '#!/bin/sh\nexec /usr/local/bin/node /opt/mise/installs/node/lts/lib/node_modules/npm/bin/npx-cli.js "$@"\n' > /usr/local/bin/npx \
    && chmod +x /usr/local/bin/npx

# Copy workspace root for installable package
COPY pyproject.toml README.md ./
COPY kubani/ kubani/

# Install the kubani package with all needed optional deps:
#   events = redis, skills = qdrant-client
# Plus additional runtime deps for the orchestrator
RUN pip install --no-cache-dir -e ".[events,skills]" \
    && pip install --no-cache-dir asyncpg duckduckgo-search mcp-server-fetch

# Pre-install readabilipy's Node.js dependencies (Readability.js) so the
# non-root appuser doesn't need write access at runtime.
RUN cd /usr/local/lib/python3.12/site-packages/readabilipy/javascript \
    && npm install

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

CMD ["python", "-m", "kubani.nexus.orchestrator.worker"]
