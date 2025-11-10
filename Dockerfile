# Spot Memory Server - High-Quality Semantic Search
# Features:
# - Python 3.11 with uv package manager
# - Qdrant (local vector database) - embedded mode
# - FastEmbed (BAAI/bge-large-en-v1.5) - pre-downloaded
# - Local reranking for improved precision
# - Enhanced metadata extraction
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    pip install --no-cache-dir uv && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy source code and install the package locally
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv pip install --system --no-cache-dir -e .

# Create non-root user for security
# Create data directory for local Qdrant storage
# Create FastEmbed cache directory with proper permissions
RUN useradd -m -u 1000 mcpuser && \
    mkdir -p /app/qdrant-data && \
    mkdir -p /tmp/fastembed_cache && \
    chown -R mcpuser:mcpuser /app/qdrant-data && \
    chown -R mcpuser:mcpuser /tmp/fastembed_cache

# Pre-download the embedding model for faster startup
# BAAI/bge-large-en-v1.5: 1024 dimensions, ~15-20% better retrieval vs bge-base
# FastEmbed caches models in ~/.cache/fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-large-en-v1.5')" && \
    mkdir -p /home/mcpuser/.cache && \
    cp -r /root/.cache/fastembed /home/mcpuser/.cache/ 2>/dev/null || true && \
    chown -R mcpuser:mcpuser /home/mcpuser/.cache && \
    chown -R mcpuser:mcpuser /app && \
    chown -R mcpuser:mcpuser /tmp/fastembed_cache 2>/dev/null || true

# Switch to non-root user
USER mcpuser

# Add system bin to PATH
ENV PATH="/usr/local/bin:$PATH"
# Set HOME to ensure FastEmbed uses user's cache directory
ENV HOME="/home/mcpuser"
# Set XDG_CACHE_HOME to use user's cache directory (FastEmbed respects this)
ENV XDG_CACHE_HOME="/home/mcpuser/.cache"
# Set TMPDIR to writable location for FastEmbed
ENV TMPDIR="/tmp"

# Expose the default port for SSE transport
EXPOSE 3855

# Set environment variables with defaults that can be overridden at runtime
# Use local Qdrant mode by default for "just works" experience
ENV QDRANT_LOCAL_PATH="/app/qdrant-data"
ENV COLLECTION_NAME="default-collection"
ENV EMBEDDING_MODEL="BAAI/bge-large-en-v1.5"
ENV FASTMCP_HOST="0.0.0.0"
ENV FASTMCP_PORT="3855"

# Run the MCP server
CMD ["mcp-server-qdrant", "--transport", "streamable-http"]
