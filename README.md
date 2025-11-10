# Spot Memory Server

A semantic memory and codebase intelligence server for Cursor IDE, powered by Qdrant vector search.

**Production-tested. Zero cost. Private by default.**

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

### Cross-Machine Sync
- Deploy once to Oracle Cloud Always Free ($0/month)
- Access from all your machines via Tailscale
- Automated backups to Linux laptop
- 15-minute recovery if instance fails

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
• mcp-server-qdrant: 18 files, 94 chunks (updated just now)
```

## Installation & Deployment

### Option 1: Local Development

```bash
# Clone the repo
git clone https://github.com/xmmarcotte/mcp-server-qdrant.git
cd mcp-server-qdrant

# Build and run with Docker
docker-compose up -d
```

The server runs on `http://localhost:3856/mcp` (local embedded Qdrant).

### Option 2: Oracle Cloud Always Free (Recommended)

Deploy to Oracle Cloud for **$0/month** with access from all your machines.

**Features:**
- 24GB RAM, 4 ARM cores, 200GB storage (free forever)
- Shared memory across all your machines
- Private access via Tailscale (no public exposure)
- Automated backup scripts included
- Full deployment guide: [ORACLE_CLOUD_DEPLOY.md](ORACLE_CLOUD_DEPLOY.md)

**Quick start:**

```bash
# 1. Build ARM64 image and deploy
./deploy-oracle.sh <your-oracle-public-ip>

# 2. Install Tailscale on Oracle instance and your machines (recommended)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up  # Note the 100.x.x.x IP

# 3. Set up automated backups on Linux laptop
./setup-cron-backup.sh 100.x.x.x ~/spot-backup daily

# 4. Update mcp.json on all machines (use Tailscale IP)
{
  "spot": {
    "url": "http://100.x.x.x:3856/mcp"
  }
}
```

**Backup & Recovery:**
```bash
# Set up automated daily backup to Linux laptop (use Tailscale IP)
./setup-cron-backup.sh 100.x.x.x ~/spot-backup daily

# Manual backup anytime
./backup-local.sh 100.x.x.x ~/spot-backup

# Restore if needed
./restore-from-backup.sh ~/spot-backup 100.x.x.x
```

### Configure Cursor

Add to your Cursor `mcp.json`:

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://localhost:3856/mcp",
      "autoStart": false,
      "description": "Spot memory server - semantic search and codebase intelligence",
      "tags": ["spot", "memory", "codebase", "qdrant"]
    }
  }
}
```

For Oracle Cloud with Tailscale, replace `localhost:3856` with your Tailscale IP (e.g., `100.x.x.x:3856`).

## Configuration

Set these environment variables (in `docker-compose.yml` or your deployment):

| Variable | Description | Default |
|----------|-------------|---------|
| `QDRANT_LOCAL_PATH` | Path for embedded Qdrant | `/app/qdrant-data` |
| `COLLECTION_NAME` | Default collection name | `default-collection` |
| `EMBEDDING_MODEL` | Embedding model to use | `BAAI/bge-large-en-v1.5` |
| `RERANKER_ENABLED` | Enable local reranking | `true` |
| `RERANKER_MODEL` | Reranker model | `BAAI/bge-reranker-base` |
| `FASTMCP_HOST` | Host to bind to | `0.0.0.0` |
| `FASTMCP_PORT` | Port to listen on | `3855` |

**Note:** Use `QDRANT_LOCAL_PATH` for embedded mode (recommended), or `QDRANT_URL` for remote Qdrant.

## Cursor Rules

For best results, add these rules to your Cursor settings to guide Claude on when to use Spot:

📄 [CURSOR_RULES.txt](CURSOR_RULES.txt) - Copy this into your Cursor rules

Key points:
- Call `spot-find` before replying (unless trivial)
- Call `spot-store` after replying (unless trivial)
- Use categories: `decision`, `pattern`, `memory`
- Store technical knowledge automatically

## Architecture

For implementation details, see [ARCHITECTURE.md](ARCHITECTURE.md).

**Key components:**
- **FastMCP** - MCP server framework
- **Qdrant** - Vector search engine (embedded mode)
- **FastEmbed** - Local embeddings (BAAI/bge-large-en-v1.5)
- **AST-based chunking** - Tree-sitter for code analysis

## Performance

**Search latency:** <1 second
**Indexing:** ~3-5 seconds for 20 files
**Incremental updates:** ~2 seconds for typical changes
**Memory usage:** 500-800MB (embeddings cached)
**Storage:** ~6KB per code chunk, ~300MB for 50K chunks

## Testing

Spot has been production-tested with:
- Multiple workspaces (Python, JavaScript)
- Cross-machine access via Tailscale
- Automated backups to local machine
- Real-world code search and memory queries

See the comprehensive test report in git history.

## License

Apache 2.0

## Credits

Built with:
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [Qdrant](https://qdrant.tech/) - Vector search engine
- [FastEmbed](https://github.com/qdrant/fastembed) - Fast embeddings
- [Tree-sitter](https://tree-sitter.github.io/) - Code parsing
- Named after **Spot**, Commander Data's cat 🐱
