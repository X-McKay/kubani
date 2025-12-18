# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including kubectl for remediation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/ \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user first
RUN useradd -m -u 1000 agent

# Copy agent source
COPY --chown=agent:agent agents/k8s-monitor/pyproject.toml /app/
COPY --chown=agent:agent agents/k8s-monitor/README.md /app/
COPY --chown=agent:agent agents/k8s-monitor/src/ /app/src/

# Install dependencies (includes core-agents from PyPI or wheel)
RUN pip install --no-cache-dir .

# Set Python path
ENV PYTHONPATH=/app

# Switch to non-root user
USER agent

# Default command runs the worker
ENTRYPOINT ["python", "-m", "k8s_monitor.worker"]
CMD ["worker"]
