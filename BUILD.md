# Build Documentation

This document describes how to build and deploy `mcp-server-qdrant` from scratch on any instance.

## 🚀 Key Features

This MCP server includes **incremental indexing** with automatic change detection:

- **Hash-Based Change Detection**: Only re-indexes files that have actually changed (MD5 comparison)
- **Incremental Updates**: Fast, targeted updates instead of full rescans (<100ms for changed files)
- **Workspace Isolation**: Separate indexes for different projects automatically
- **Agent Guidance**: Intelligent hints when index is stale or empty
- **Health Monitoring**: Check index status and freshness at any time

### Core Tools

**Indexing:**
- `index-codebase(files={path: content}, workspace_name="project")` - Full initial scan (run once per workspace)
  - **REQUIRES `files` parameter** - IDE must send all file contents as dict
  - MCP servers are always remote and cannot access filesystem
- `update-files(files={path: content, ...}, workspace_name="project")` - Fast incremental update (only changed files)
- `get-index-status(workspace_name="project")` - Check index health and freshness

**Code Intelligence:**
- `find-similar-code(code_snippet, workspace_name="project")` - Semantic code search with workspace isolation
- `search(query, workspace_name="project", category="codebase")` - Unified semantic search for code

**Memory:**
- `qdrant-store(information)` - Store any information
- `qdrant-find(query)` - Search stored memories
- `remember-decision(decision, rationale)` - Store architectural decisions
- `remember-pattern(pattern, example)` - Store coding patterns
- `search-by-time(query, since, until)` - Temporal queries

### Usage Example

```python
# 1. Index your codebase (first time)
# IDE sends all file contents as dict
index-codebase(
    files={
        "src/main.py": "# file content...",
        "src/utils.py": "# file content...",
        # ... all files
    },
    workspace_name="my-project"
)
# Output: Indexed 24 files (800 code chunks) from 24 total files. Languages: python, markdown, toml

# 2. Make some changes to your code...
# 3. Quick refresh (only changed files)
update-files(
    files={"src/main.py": "...new content..."},
    workspace_name="my-project"
)
# Output: Updated 1 changed file (5 code chunks) in 45ms

# 4. Check health
get-index-status(workspace_name="my-project")
# Output:
# 📊 Index Status
# Workspace: my-project
# Files Tracked: 24
# Last Update: just now
# Auto-Index: ✅ Enabled
# ✅ Index is healthy and current
```

## Quick Start

### Linux/macOS
```bash
./build.sh --test --docker
```

### Windows
```powershell
.\build.ps1 -Test -Docker
```

## Build Scripts

### `build.sh` (Linux/macOS/Unix)

A comprehensive build script that handles the entire build process:

```bash
# Basic build (just package)
./build.sh

# Build with tests
./build.sh --test

# Build with Docker image
./build.sh --docker

# Build everything
./build.sh --test --docker

# Publish to PyPI (requires UV_PUBLISH_TOKEN)
./build.sh --publish
```

**What it does:**
1. Checks Python version (requires >= 3.10)
2. Installs `uv` if not present
3. Syncs dependencies from `uv.lock`
4. Optionally runs tests
5. Builds the Python package
6. Optionally builds Docker image
7. Optionally publishes to PyPI

### `build.ps1` (Windows)

PowerShell equivalent with the same functionality:

```powershell
# Basic build
.\build.ps1

# Build with tests
.\build.ps1 -Test

# Build with Docker
.\build.ps1 -Docker

# Build everything
.\build.ps1 -Test -Docker

# Publish to PyPI
.\build.ps1 -Publish
```

## Manual Build Steps

If you prefer to build manually:

### 1. Prerequisites
- Python 3.10 or higher
- `uv` package manager (install via: `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### 2. Install Dependencies
```bash
uv sync
```

### 3. Run Tests (Optional)
```bash
uv run pytest
```

### 4. Build Package
```bash
uv build
```

The built package will be in the `dist/` directory.

### 5. Build Docker Image (Optional)
```bash
docker build -t mcp-server-qdrant:latest .
```

### 6. Run Docker Container
```bash
docker run -p 3855:3855 \
  -e FASTMCP_HOST="0.0.0.0" \
  -e QDRANT_URL="http://your-qdrant-server:6333" \
  -e QDRANT_API_KEY="your-api-key" \
  -e COLLECTION_NAME="your-collection" \
  mcp-server-qdrant:latest
```

## Cloud Deployment

The build scripts are designed to work on any cloud instance. For cloud deployments:

1. **SSH into your instance**
2. **Clone the repository**
   ```bash
   git clone https://github.com/xmmarcotte/mcp-server-qdrant.git
   cd mcp-server-qdrant
   ```
3. **Run the build script**
   ```bash
   ./build.sh --test --docker
   ```
4. **Deploy the Docker container** using your cloud provider's container service

### Environment Variables for Cloud

Set these environment variables in your cloud deployment:

- `QDRANT_URL` - Your Qdrant server URL
- `QDRANT_API_KEY` - Your Qdrant API key (if required)
- `COLLECTION_NAME` - Default collection name
- `EMBEDDING_MODEL` - Embedding model to use (default: `BAAI/bge-base-en-v1.5`)
- `FASTMCP_HOST` - Host to bind to (use `0.0.0.0` for cloud)
- `FASTMCP_PORT` - Port to listen on (default: `3855`)

## Branch Strategy

This project uses a simple two-branch strategy:

- **`main`** - Production-ready code
- **`dev`** - Development branch

All changes should be made in `dev` and merged to `main` when ready.

## CI/CD

GitHub Actions workflows are configured to:
- Run tests on push to `main` or `dev`
- Run pre-commit checks
- Publish to PyPI when a version tag (v*) is pushed
