# Cursor IDE Integration

Guide for using Spot MCP Server with Cursor IDE.

## Configuration

Add to your `~/.cursor/mcp.json` (or wherever your Cursor config is):

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://100.x.x.x:3856/mcp",
      "autoStart": true,
      "description": "Spot MCP Server - semantic memory across all machines",
      "tags": ["spot", "memory", "codebase", "marcotte-dev"]
    }
  }
}
```

Replace `100.x.x.x` with your Oracle instance's Tailscale IP.

## Cursor Rules

Add these rules to your Cursor settings (Settings → General → Rules for AI) to guide Claude on automatic Spot tool usage:

```
# SPOT MCP INTEGRATION - Automatic Memory & Codebase Intelligence

You have access to Spot MCP tools for persistent memory and semantic codebase search. Use them proactively and liberally.

## Core Workflow (Follow This Pattern)

1. **SEARCH FIRST** - Call `spot-find` before answering ANY non-trivial request
2. **ANSWER** - Provide your response using found context
3. **STORE AFTER** - Call `spot-store` to remember important information

When in doubt, USE the tools. Over-using is better than under-using.

## Automatic `spot-find` Usage

Call `spot-find` BEFORE replying for:
- ANY question that could benefit from context (default: yes, use it)
- User asks about past work ("what did we", "last time", "previously", "you said")
- Technical questions about this or other projects
- Debugging, troubleshooting, or error investigation
- Asking about patterns, conventions, or best practices
- Following up on any previous conversation or decision
- Questions spanning multiple files, systems, or services

**Examples that trigger spot-find:**
- "How do we handle authentication?" → Search for auth patterns/decisions
- "What's the database setup?" → Search for DB config/architecture
- "Fix this bug" → Search for similar fixes and troubleshooting patterns
- "Add a feature" → Search for related code patterns and conventions
- "Why did we choose X?" → Search for architectural decisions

**Skip spot-find only for:**
- Pure formatting/style questions ("add a comment", "rename variable")
- Trivial syntax ("how do I write a for loop")
- Brand new topics with no prior context

## Automatic `spot-store` Usage

Call `spot-store` AFTER replying when your response includes:

**Always store (category="decision"):**
- Architectural decisions and rationale
- Technology/library choices and trade-offs
- Design patterns chosen for this project
- Infrastructure or deployment decisions

**Always store (category="pattern"):**
- Code patterns and conventions established
- Error handling approaches
- Testing strategies
- Performance optimization techniques
- Project-specific best practices

**Always store (category="memory", default):**
- Configuration values (API keys locations, ports, URLs)
- Environment setup steps
- Troubleshooting outcomes ("fixed X by doing Y")
- Workflow explanations
- Command sequences
- File/directory locations
- Dependency versions and compatibility notes

**Skip spot-store only for:**
- Responses that are purely explanatory (no new knowledge)
- Formatting/style-only changes
- Information already stored recently

## Memory System (No Codebase Indexing)

**Spot focuses on memory and patterns, not local code search:**
- **Memory storage**: Store decisions, patterns, and insights with `spot-store`
- **Cross-project search**: Find patterns and decisions across all your work
- **Code navigation**: Use Cursor's built-in search for local code

**During development:**
- Assistant calls `spot-find` before answering to check memory
- Assistant calls `spot-store` after providing value to build memory
- No codebase indexing - Cursor handles local code intelligence

**Examples:**
- "How do we handle async functions here?" → `spot-find("async patterns", category="pattern")`
- "Find database query patterns" → `spot-find("database queries", category="pattern")`

## Tool Reference

- `spot-find(query, category?, tags?, workspace_name?)` - Semantic search across all memories
- `spot-store(information, category?, tags?, project?, language?)` - Store important info
- `spot-list-workspaces()` - Show all workspaces with stored memories

## Tags for Better Organization

Add descriptive tags when storing:
- Technology: `"flask", "react", "docker", "aws"`
- Domain: `"auth", "database", "api", "frontend"`
- Type: `"bugfix", "optimization", "refactor", "security"`

Example: `spot-store(..., category="decision", tags="database,postgres,architecture")`

## Remember

- Spot is ALWAYS available - use it frequently
- Search semantically (meaning-based), not exact keywords
- Store information liberally - disk is cheap, context is valuable
- When unsure if something is worth storing, store it
- The more you use Spot, the more valuable it becomes
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

### 3. Memory System

Spot stores and retrieves memories, decisions, and patterns across all your projects:

```python
# Store architectural decision
spot-store(
    information="Decision: Use PostgreSQL for complex queries\nRationale: ACID compliance needed\nAlternatives: MongoDB",
    category="decision",
    tags="database,architecture"
)

# Find similar patterns later
spot-find("database decisions", category="decision")

# Returns: All stored database decisions with context
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

### Memory Building with Codeblocks

After working on code, store important patterns and examples:

```python
# Store a complete code pattern with examples
spot-store(
    information="""AuthService usage pattern:

GOOD: Centralized auth with proper error handling
```javascript
const auth = new AuthService();
try {
  const user = await auth.login(credentials);
  // Use user...
} catch (error) {
  // Handle auth errors
}
```

BAD: Direct API calls without error handling
```javascript
// Don't do this
api.post('/auth/login', credentials)
  .then(user => /* handle success */)
  .catch(err => /* handle error */);
```

Key methods:
- login(credentials) → Promise<User>
- logout() → Promise<void>
- getCurrentUser() → User | null
- refreshToken() → Promise<string>
""",
    category="pattern",
    tags="auth,security,javascript"
)

# Later, find patterns and examples
spot-find("auth service usage", category="pattern")
```

### Pure Memory-First Approach

**ONLY use memory tools** - no indexing or code search tools:
- `spot-find` for retrieving stored patterns, decisions, and examples
- `spot-store` for saving valuable code patterns and insights

**Cursor handles all code access** - file navigation, search, and immediate code intelligence.

### Workspace Isolation

Multiple projects stay separate:

```python
spot-find(
    query="authentication patterns",
    workspace_name="client-project"  # Only searches this workspace's memories
)
```

### Memory Health

Since we use pure memory-first approach, health monitoring is built into the search results. If you're not finding expected memories, check your search terms or category filters.

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
