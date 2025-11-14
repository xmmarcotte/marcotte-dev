# Spot MCP Server

A semantic memory MCP server for Cursor IDE, powered by Qdrant vector search.

**Part of the [marcotte-dev](../../) infrastructure.**

## What Is This?

Spot is an MCP (Model Context Protocol) server that gives Claude in Cursor IDE:
- **Persistent memory** across all your machines
- **Semantic memory search** across all projects
- **Architectural decision tracking** with structured categories
- **Code pattern recognition** for consistent development

All data is stored in your own Qdrant instance - no external APIs, no data leaves your control.

## Features

### High-Quality Semantic Search
- **BAAI/bge-large-en-v1.5** embeddings (1024 dimensions)
- 15-20% better retrieval than baseline models
- Local reranking for improved precision
- Optimized for code and technical content

### Memory System
- Semantic search across all stored memories
- Category-based organization (decisions, patterns, notes)
- Tag-based filtering for precise retrieval
- Cross-project pattern recognition

### Memory Building
- Organic memory growth as you work
- Store insights, decisions, and patterns with `spot-store`
- No mass indexing - just capture valuable moments
- Workspace isolation for multi-project support

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

### 3. `spot-list-workspaces` - List workspaces
List all workspaces with stored memories.

**Memory-first approach:** Focus on storing insights, code patterns, and usage examples with `spot-store` rather than indexing entire files.

**Example:** Store important codeblocks as you discover them:

```python
spot-store(
    information="""Database connection pattern with retry logic:

```python
async def get_db_connection(retries=3):
    for attempt in range(retries):
        try:
            conn = await create_connection()
            await conn.ping()  # Test connection
            return conn
        except ConnectionError as e:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    raise RuntimeError("Failed to connect after retries")
```

Use this pattern for all database operations to handle connection failures gracefully.""",
    category="pattern",
    tags="database,retry,async"
)
```

### 4. `spot-list-workspaces` - List all workspaces
See all workspaces with stored memories.

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
