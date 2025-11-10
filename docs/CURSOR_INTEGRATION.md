# Cursor IDE Integration

Guide for using Spot MCP Server with Cursor IDE.

## Configuration

Add to your `~/.cursor/mcp.json` (or wherever your Cursor config is):

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://100.x.x.x:3856/mcp",
      "autoStart": false,
      "description": "Spot MCP Server - semantic memory across all machines",
      "tags": ["spot", "memory", "codebase", "marcotte-dev"]
    }
  }
}
```

Replace `100.x.x.x` with your Oracle instance's Tailscale IP.

## Cursor Rules

Add these rules to your Cursor settings to guide Claude on when to use Spot tools:

```
Always call `spot-find` before replying unless the user request is purely trivial or formatting-related

Always call `spot-store` after replying unless the response is trivial, redundant, or only about style or tone

Use `spot-find` when:
- The user asks about something previously discussed (e.g. "you said", "last time", "remind me", "what did we do")
- The request builds on earlier configs, logs, code, or decisions
- The question spans multiple systems, files, or workflows
- The user is following up on a fix, ticket, or script
- Additional memory could improve the clarity or accuracy of the answer

Use `spot-store` when:
- The response includes useful technical knowledge worth recalling later:
  - Configuration values
  - Environment variables
  - Startup scripts
  - Logs
  - Workflow explanations
  - Architecture decisions
  - Troubleshooting outcomes
- The response would help answer future "when did we..." or "how did we..." questions

Use categories with `spot-store` for better organization:
- `category="decision"` - Architectural decisions, technology choices, trade-offs
- `category="pattern"` - Coding patterns, best practices, conventions
- `category="memory"` - General notes, observations (default)

Additional Spot tools:
- `spot-find-code` - Find similar code patterns in indexed workspaces
- `spot-index-codebase` - Index a codebase for semantic search
- `spot-update-files` - Incrementally update changed files
- `spot-list-workspaces` - See all indexed projects
- `spot-index-status` - Check index health and file counts
```

## How It Works

### 1. Persistent Memory Across Machines

When you use Cursor on any machine (laptop, desktop, work machine), all of them connect to the same Spot MCP Server on your Oracle Cloud instance via Tailscale. This means:

- **Shared context**: Claude remembers conversations and decisions from any machine
- **No data loss**: Everything persists even if you restart Cursor or switch devices
- **Private by default**: Data stays on your infrastructure (never sent to external APIs)

### 2. Semantic Search

Spot uses high-quality embeddings (BAAI/bge-large-en-v1.5) to understand the meaning of your queries:

```python
# Instead of exact text matching
spot-find(query="database connection issue")

# Finds semantically similar content like:
# - "Fixed connection pooling timeout"
# - "Resolved DB auth errors"
# - "Connection retry logic added"
```

### 3. Codebase Intelligence

Spot indexes your code with AST-based chunking, preserving function/class context:

```python
# Index your workspace (Cursor does this automatically)
spot-index-codebase(
    files={...},  # All project files
    workspace_name="my-app"
)

# Find similar code patterns
spot-find-code(
    code_snippet="async def fetch_data",
    workspace_name="my-app"
)

# Returns: All functions that follow this pattern with context
```

### 4. Categories for Organization

Store information with categories for structured retrieval:

```python
# Architectural decision
spot-store(
    information="Decision: Use PostgreSQL over MongoDB for ACID compliance",
    category="decision",
    project="my-app",
    tags="database,architecture"
)

# Coding pattern
spot-store(
    information="Always use try/catch for API calls with exponential backoff",
    category="pattern",
    language="javascript",
    tags="async,error-handling"
)

# General note
spot-store(
    information="Production deploy checklist: run migrations, clear cache, restart workers"
)

# Later, search by category
spot-find(query="database decisions", category="decision")
```

## Typical Workflow

### Morning: Start on Desktop

```
You: "What did we decide about the auth system yesterday?"
Claude: [calls spot-find(query="auth system decision")]
        "We decided to use JWT with refresh tokens stored in httpOnly cookies..."
```

### Afternoon: Switch to Laptop

```
You: "Continue implementing that auth system"
Claude: [calls spot-find(query="auth JWT implementation")]
        "Based on yesterday's decision, here's the implementation..."
        [provides code]
        [calls spot-store to remember the implementation]
```

### Evening: Back to Desktop

```
You: "Did we finish the auth system?"
Claude: [calls spot-find(query="auth system implementation today")]
        "Yes, we completed it on your laptop this afternoon. Here's what was done..."
```

## Advanced Features

### Incremental Updates

After editing files:

```python
# Spot automatically detects changes and only re-indexes modified files
spot-update-files(
    files={"src/main.py": "...", "src/api.py": "..."},
    workspace_name="my-app"
)
# Output: Updated 2 changed files (12 chunks) in 1847ms
```

### Workspace Isolation

Multiple projects stay separate:

```python
spot-find-code(
    code_snippet="authentication",
    workspace_name="client-project"  # Only searches this workspace
)
```

### Health Monitoring

```python
spot-index-status(workspace_name="my-app")
# Shows: files tracked, last update, index health
```

## Troubleshooting

### "Connection refused" Error

```bash
# Check Tailscale is running
tailscale status

# Verify server is up
curl http://100.x.x.x:3856/mcp

# Check Cursor mcp.json has correct IP
cat ~/.cursor/mcp.json
```

### Tools Not Showing Up

1. Restart Cursor
2. Check MCP server is listed in Cursor settings
3. Manually connect to server in Cursor's MCP panel

### Slow Search

- Large workspaces (1000+ files) may take a few seconds
- Incremental updates are much faster than full re-index
- Reranking adds ~50ms but improves quality significantly

## Best Practices

1. **Let Claude manage the tools** - Don't manually call them, let Claude decide when based on the rules
2. **Use categories consistently** - Helps with retrieval later
3. **Add descriptive tags** - Makes filtering easier
4. **Trust semantic search** - Don't worry about exact keywords, Spot understands meaning
5. **Keep backups running** - See [../README.md](../README.md) for backup setup

## Privacy & Security

- ✅ All data stays on your infrastructure
- ✅ Private Tailscale network (not exposed publicly)
- ✅ No external API calls
- ✅ You own and control all embeddings and vectors
- ✅ Open source (Apache 2.0)

## Performance

**Typical latencies:**
- Search: 300-800ms
- Store: 100-300ms
- Index (20 files): 3-5 seconds
- Incremental update: 2 seconds

**Storage:**
- ~6KB per code chunk
- ~2KB per memory/decision
- ~300MB for 50,000 chunks

## Further Reading

- [../services/spot-mcp-server/README.md](../services/spot-mcp-server/README.md) - Detailed tool documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical implementation
- [SETUP.md](SETUP.md) - Infrastructure setup guide
