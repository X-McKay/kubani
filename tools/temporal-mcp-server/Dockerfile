FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir -e .

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

# Default to SSE mode for cluster deployment
ENTRYPOINT ["temporal-mcp"]
CMD ["--mode", "sse", "--port", "8081"]
