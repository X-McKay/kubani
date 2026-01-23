FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for microsandbox
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir -e .

# Create skills directory mount point
RUN mkdir -p /skills

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

# Default to SSE mode for cluster deployment
ENTRYPOINT ["skills-mcp-server"]
CMD ["--mode", "sse", "--port", "8080"]
