FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy workspace root for installable package
COPY pyproject.toml README.md ./
COPY kubani/ kubani/

# Install the kubani package with events (redis) dependencies
RUN pip install --no-cache-dir -e ".[events]" \
    && pip install --no-cache-dir uvicorn[standard] fastapi asyncpg

# Run as non-root user
RUN useradd -m -u 1000 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "kubani.nexus.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
