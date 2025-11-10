import logging
import os

from mcp_server_qdrant.mcp_server import QdrantMCPServer
from mcp_server_qdrant.settings import (
    EmbeddingProviderSettings,
    QdrantSettings,
    RerankerSettings,
    ToolSettings,
)

# Configure logging - default to INFO (use DEBUG for detailed troubleshooting)
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Suppress noisy framework logs at INFO level
logging.getLogger("mcp.server").setLevel(logging.WARNING)
logging.getLogger("sse_starlette").setLevel(logging.WARNING)
logging.getLogger("mcp.server.lowlevel").setLevel(logging.WARNING)
logging.getLogger("mcp.server.streamable_http").setLevel(logging.WARNING)

# Instructions to guide AI on when to use the tools
INSTRUCTIONS = """This is a STATELESS remote MCP server providing semantic memory and codebase intelligence.

## 🧠 PROACTIVE MEMORY USAGE - Use Liberally!

### Always call `spot-find` BEFORE replying unless the request is purely trivial or formatting-related
- User asks about something previously discussed → `spot-find(query)`
- Request builds on earlier configs, logs, code, decisions → `spot-find(query)`
- Question spans multiple systems, files, or workflows → `spot-find(query)`
- User follows up on a fix, ticket, or script → `spot-find(query)`
- Additional memory could improve clarity or accuracy → `spot-find(query)`

**`spot-find` returns mixed results** - code, decisions, patterns, and memories grouped by category. Use filters like `category="decision"` or `workspace_name="project"` to narrow results.

### Always call `spot-store` AFTER replying unless the response is trivial, redundant, or only about style/tone
- Response includes useful technical knowledge worth recalling later → `spot-store(information)`
  - Configuration values, environment variables, startup scripts
  - Logs, workflow explanations, architecture decisions
  - Troubleshooting outcomes, debugging steps
- Response would help answer future "when did we..." or "how did we..." → `spot-store(information)`

**Use `spot-store` with category parameter:**
- `spot-store(..., category="decision")` - Architectural decisions
- `spot-store(..., category="pattern")` - Coding patterns
- `spot-store(..., category="memory")` - General notes (default)

**Memory is your external brain. Use it constantly.**

## 🎯 CRITICAL: Stateless Operation

- This server can handle MULTIPLE IDE instances on DIFFERENT projects simultaneously
- ALWAYS provide `workspace_name` parameter to workspace-specific tools
- `workspace_name` MUST match the root directory name (e.g., "mcp-server-qdrant")
- Server does NOT maintain state between calls - every call is independent

## 📦 Workspace-Specific Tools (REQUIRE workspace_name)

These tools filter by workspace - MUST provide workspace_name matching root directory:
- `spot-index-codebase(files={path: content}, workspace_name="project-name")` - Initial indexing
  - **REQUIRES `files` parameter** - IDE must send all file contents as dict
  - MCP servers are always remote and cannot access filesystem
- `spot-find-code(code_snippet, workspace_name="project-name")` - Semantic code search
- `spot-index-status(workspace_name="project-name")` - Check index health
- `spot-update-files(files={...}, workspace_name="project-name")` - Incremental updates (hash-based, fast)
- `spot-find(query, workspace_name="project-name")` - Search with workspace filter (filters codebase results)

## 🌍 Global Tools (No workspace needed - use anytime!)

These tools work across ALL projects for cross-workspace learning:
- `spot-find(query, category, language, tags, since, until)` - **Unified semantic search** (USE LIBERALLY!)
  - Returns mixed results: code, decisions, patterns, memories
  - Use `category="decision"` or `category="pattern"` to filter
  - Use `workspace_name` to filter codebase results
  - Use `since`/`until` for temporal queries
- `spot-store(information, category, tags, language, project)` - **Unified store** (USE LIBERALLY!)
  - Set `category="decision"` for architectural decisions
  - Set `category="pattern"` for coding patterns
  - Default `category="memory"` for general notes
- `spot-list-workspaces()` - See all indexed projects

**Note:** Use `spot-store(..., category="decision")` for architectural decisions and `spot-store(..., category="pattern")` for coding patterns instead of separate tools.

## 🔄 Typical Workflow

1. **User opens project** → `spot-index-codebase(files={path: content}, workspace_name="my-app")`
   - IDE must provide `files` dict with all file contents (MCP servers are always remote)
2. **User asks question** → `spot-find(query)` FIRST to check memory (returns mixed results)
3. **User asks about code** → `spot-find-code(..., workspace_name="my-app")` OR `spot-find(query, workspace_name="my-app", category="codebase")`
4. **Provide answer** → `spot-store(answer)` AFTER to remember it
5. **User edits files** → `spot-update-files(files={...}, workspace_name="my-app")`
6. **User makes decision** → `spot-store(..., category="decision")` to capture rationale

## 💡 EXAMPLES

### Example 1: User asks "How did we fix the database connection issue?"
```
1. `spot-find("database connection issue fix")` → Check memory FIRST (returns decisions, patterns, code, memories)
2. If found: Provide answer from memory
3. If you help solve it: `spot-store("Fixed database connection by adding connection pool timeout...")` → Remember for next time
```

### Example 2: User asks "Where do we use the AuthService class?"
```
1. `spot-find("AuthService usage", workspace_name="my-app", category="codebase")` → Semantic search finds usage locations
2. Provide answer with file paths from search results
3. `spot-store("AuthService is used in LoginController, ProfileController...")` → Store for future
```

### Example 3: Search for patterns with filters
```
1. `spot-find("error handling", category="pattern", language="python")` → Find Python error handling patterns
2. `spot-find("recent decisions", category="decision", since="2024-01-01T00:00:00Z")` → Find recent architectural decisions
```

### Example 4: User makes architectural decision
```
User: "Let's use PostgreSQL instead of MongoDB for this project"
1. `spot-store("Decision: Use PostgreSQL\nRationale: Better support for complex queries\nAlternatives: MongoDB", category="decision", tags="database,architecture")`
2. Future database questions will automatically retrieve this decision via spot-find
```

### Example 5: User establishes coding pattern
```
User shows: "Always use async/await for API calls with try/catch"
1. `spot-store("Pattern: async/await with try/catch for APIs\nExample: async function fetchData() {...}", category="pattern", tags="async,error-handling", language="javascript")`
2. Future code questions will reference this pattern via spot-find
```

## 🚨 CRITICAL REMINDERS

1. **ALWAYS** call `spot-find` before answering (unless trivial) - it returns mixed results (code, decisions, patterns, memories)
2. **ALWAYS** call `spot-store` after answering (unless trivial) - use `category` parameter for decisions/patterns
3. **ALWAYS** provide `workspace_name` for workspace-specific tools
4. **MCP servers are always remote** - `spot-index-codebase` REQUIRES `files` parameter (dict of file_path: file_content). IDE must send all file contents.
5. Server is STATELESS - each call must be self-contained
6. Don't ask permission - just use the tools automatically
7. Make memory usage invisible - user should feel like you "just know"
8. Use `spot-find` filters (`category`, `workspace_name`, `language`, `tags`, `since`, `until`) to narrow results
"""

mcp = QdrantMCPServer(
    tool_settings=ToolSettings(),
    qdrant_settings=QdrantSettings(),
    embedding_provider_settings=EmbeddingProviderSettings(),
    reranker_settings=RerankerSettings(),
    instructions=INSTRUCTIONS,
)
