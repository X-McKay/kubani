# Build stage
FROM rust:1.92-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy manifests
COPY Cargo.toml Cargo.lock ./

# Create a dummy main.rs to build dependencies
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo build --release && \
    rm -rf src

# Copy source code
COPY src ./src

# Build the application
RUN touch src/main.rs && \
    cargo build --release

# Runtime stage
FROM debian:bookworm-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy the binary from builder
COPY --from=builder /app/target/release/kubani-ui-backend /app/kubani-ui-backend

# Set environment variables
ENV RUST_LOG=info
ENV K8S_MCP_URL=http://kubernetes-mcp-server.ai-agents.svc.cluster.local:8080
ENV REGISTRY_URL=http://metadata-registry.ai-agents.svc.cluster.local:8000
ENV VLLM_URL=http://llm-api.vllm.svc.cluster.local:8000/v1
ENV MODEL_NAME=Qwen/Qwen3-14B

# Expose port
EXPOSE 3001

# Run the binary
CMD ["/app/kubani-ui-backend"]
