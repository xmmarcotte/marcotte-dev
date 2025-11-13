# Spot MCP Server - ARM64/AMD64 multi-arch image
FROM python:3.12-slim

WORKDIR /app

# Install uv (fast Python package installer)
RUN pip install --no-cache-dir uv

# Copy all files needed for installation
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install dependencies (creates .venv)
RUN uv sync --frozen --no-dev

# Add uv's virtualenv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Create data directory
RUN mkdir -p /app/qdrant-data && chmod 755 /app/qdrant-data

# Expose MCP server port
EXPOSE 3855

# Set default environment variables
ENV QDRANT_LOCAL_PATH=/app/qdrant-data \
    COLLECTION_NAME=default-collection \
    EMBEDDING_MODEL=BAAI/bge-large-en-v1.5 \
    RERANKER_ENABLED=true \
    FASTMCP_HOST=0.0.0.0 \
    FASTMCP_PORT=3855

# Run the MCP server directly
CMD ["mcp-server-qdrant", "--transport", "streamable-http"]
