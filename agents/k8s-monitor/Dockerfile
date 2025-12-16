# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared platform library
COPY agent_platform/ /app/agent_platform/

# Copy agent source
COPY agents/k8s-monitor/pyproject.toml /app/
COPY agents/k8s-monitor/src/ /app/src/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Set Python path to include agent_platform
ENV PYTHONPATH=/app:$PYTHONPATH

# Run as non-root user
RUN useradd -m -u 1000 agent
USER agent

# Default command runs the worker
ENTRYPOINT ["python", "-m", "k8s_monitor.worker"]
CMD ["worker"]
