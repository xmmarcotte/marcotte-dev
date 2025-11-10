# Spot MCP Server

A semantic memory and codebase intelligence MCP server for Cursor IDE, powered by Qdrant vector search.

**Part of the [marcotte-dev](../../) infrastructure.**

## What Is This?

Spot is an MCP (Model Context Protocol) server that gives Claude in Cursor IDE:
- **Persistent memory** across all your machines
- **Semantic codebase search** with workspace isolation
- **Architectural decision tracking** with structured categories
- **Code pattern recognition** for consistent development

All data is stored in your own Qdrant instance - no external APIs, no data leaves your control.

## Features

### High-Quality Semantic Search
- **BAAI/bge-large-en-v1.5** embeddings (1024 dimensions)
- 15-20% better retrieval than baseline models
- Local reranking for improved precision
- Optimized for code and technical content

### Smart Codebase Intelligence
- AST-based code chunking (preserves context)
- Function/class signature extraction
- Framework and pattern detection
- Quality signals (docstrings, type hints, tests)

### Incremental Indexing
- Hash-based change detection (only re-index what changed)
- ~2 second updates for typical changes
- Workspace isolation for multi-project support
- Health monitoring and status checks

## The 7 Tools

All tools use the `spot-` prefix:

### 1. `spot-store` - Store anything
Store information with optional categories and metadata.

```python
# Store a general note
spot-store(information="Fixed database connection pooling issue with timeout=30")

# Store an architectural decision
spot-store(
    information="Decision: Use PostgreSQL over MongoDB. Rationale: Better support for complex queries and ACID compliance.",
    category="decision",
    project="my-app",
    tags="database,architecture"
)

# Store a coding pattern
spot-store(
    information="Pattern: Always use async/await for API calls with try/catch for error handling",
    category="pattern",
    language="javascript",
    tags="async,error-handling"
)
```

### 2. `spot-find` - Search everything
Unified semantic search across all stored content with flexible filtering.

```python
# Search everything
spot-find(query="database connection issue")

# Search specific category
spot-find(query="authentication patterns", category="decision")

# Search with workspace filter
spot-find(query="error handling", workspace_name="my-app", category="codebase")

# Search with time range
spot-find(query="recent decisions", category="decision", since="2024-11-01T00:00:00Z")

# Search by tags
spot-find(query="database", tags="architecture")
```

Returns results grouped by category: Decisions, Patterns, Code, Memories.

### 3. `spot-index-codebase` - Index your code
Full codebase indexing with AST-based chunking.

```python
# Index a workspace (IDE sends file contents)
spot-index-codebase(
    files={
        "src/main.py": "# file content here...",
        "src/utils.py": "# file content here...",
        # ... all files
    },
    workspace_name="my-app"
)
# Output: Indexed 24 files (156 code chunks) from 24 total files. Languages: python, markdown
```

**Note:** MCP servers are remote - the IDE must send file contents as a dictionary.

### 4. `spot-find-code` - Search code semantically
Find similar code patterns across your codebase.

```python
# Find similar functions
spot-find-code(
    code_snippet="async def fetch_data",
    workspace_name="my-app"
)

# Find where a pattern is used
spot-find-code(
    code_snippet="class UserAuthentication",
    workspace_name="my-app"
)
```

Returns code chunks with file paths, line numbers, and context (class/function names).

### 5. `spot-update-files` - Incremental updates
Fast updates for changed files only.

```python
# Update specific files after editing
spot-update-files(
    files={
        "src/main.py": "# updated content...",
        "src/api.py": "# updated content..."
    },
    workspace_name="my-app"
)
# Output: Updated 2 changed files (12 code chunks) in 1847ms
```

Uses MD5 hash comparison - only re-indexes files that actually changed.

### 6. `spot-index-status` - Check health
Monitor your workspace index health.

```python
spot-index-status(workspace_name="my-app")
```

```
📊 Index Status

Workspace: my-app
Files Tracked: 24
Last Update: 2 hours ago
Auto-Index: ✅ Enabled

✅ Index is healthy and current
```

### 7. `spot-list-workspaces` - List all workspaces
See all indexed projects.

```python
spot-list-workspaces()
```

```
📋 Indexed Workspaces (3)

• my-app: 24 files, 156 chunks (updated 2 hours ago)
• client-project: 45 files, 289 chunks (updated yesterday)
• spot-mcp-server: 18 files, 94 chunks (updated just now)
```

## Local Development

```bash
# Install dependencies
uv sync

# Run locally (development mode)
uv run fastmcp dev src/mcp_server_qdrant/mcp_server.py

# Or via Docker
docker-compose up -d

# Check logs
docker logs -f spot-mcp-server
```

## Deployment

### Via marcotte-dev Scripts

From the repository root:

```bash
./scripts/deploy.sh <oracle-tailscale-ip>
```

This builds the ARM64 image, transfers it, and deploys the container.

### Manual Deployment

```bash
# Build for ARM64
docker buildx build --platform linux/arm64 -t spot-mcp-server:latest -f Dockerfile .

# Save and transfer
docker save spot-mcp-server:latest | gzip > spot-mcp-server.tar.gz
scp spot-mcp-server.tar.gz ubuntu@<oracle-ip>:~/

# On Oracle instance
ssh ubuntu@<oracle-ip>
docker load < spot-mcp-server.tar.gz
cd ~/spot-mcp-server
docker-compose up -d
```

## Configuration

Edit `docker-compose.yml` or set environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `QDRANT_LOCAL_PATH` | Path for embedded Qdrant | `/app/qdrant-data` |
| `COLLECTION_NAME` | Default collection name | `default-collection` |
| `EMBEDDING_MODEL` | Embedding model to use | `BAAI/bge-large-en-v1.5` |
| `RERANKER_ENABLED` | Enable local reranking | `true` |
| `RERANKER_MODEL` | Reranker model | `BAAI/bge-reranker-base` |
| `FASTMCP_HOST` | Host to bind to | `0.0.0.0` |
| `FASTMCP_PORT` | Port to listen on | `3855` |

## Cursor Integration

Add to your Cursor `mcp.json` on each machine:

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://100.x.x.x:3856/mcp",
      "autoStart": false,
      "description": "Spot memory server - semantic search and codebase intelligence",
      "tags": ["spot", "memory", "codebase", "qdrant"]
    }
  }
}
```

Replace `100.x.x.x` with your Oracle instance's Tailscale IP.

### Cursor Rules

For best results, add these rules to your Cursor settings:

📄 [docs/CURSOR_INTEGRATION.md](../../docs/CURSOR_INTEGRATION.md)

Key points:
- Call `spot-find` before replying (unless trivial)
- Call `spot-store` after replying (unless trivial)
- Use categories: `decision`, `pattern`, `memory`

## Performance

**Search latency:** <1 second
**Indexing:** ~3-5 seconds for 20 files
**Incremental updates:** ~2 seconds for typical changes
**Memory usage:** 500-800MB (embeddings cached)
**Storage:** ~6KB per code chunk, ~300MB for 50K chunks

## Architecture

See [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) for implementation details.

**Key components:**
- **FastMCP** - MCP server framework
- **Qdrant** - Vector search engine (embedded mode)
- **FastEmbed** - Local embeddings (BAAI/bge-large-en-v1.5)
- **Tree-sitter** - AST-based code parsing

## Testing

Production-tested with:
- Multiple workspaces (Python, JavaScript)
- Cross-machine access via Tailscale
- Automated backups to local machine
- Real-world code search and memory queries

## License

Apache 2.0

## Credits

- Named after **Spot**, Commander Data's cat 🐱
- Built with [FastMCP](https://github.com/jlowin/fastmcp), [Qdrant](https://qdrant.tech/), [FastEmbed](https://github.com/qdrant/fastembed)
