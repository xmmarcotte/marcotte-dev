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
INSTRUCTIONS = r"""This is a STATELESS remote MCP server providing semantic memory and codebase intelligence.

## 🧠 PROACTIVE MEMORY USAGE - Use Liberally!

### Always call `spot-find` BEFORE replying unless the request is purely trivial or formatting-related
- User asks about something previously discussed → `spot-find(query)`
- Request builds on earlier configs, logs, code, decisions → `spot-find(query)`
- Question spans multiple systems, files, or workflows → `spot-find(query)`
- User follows up on a fix, ticket, or script → `spot-find(query)`
- Additional memory could improve clarity or accuracy → `spot-find(query)`
- Include relevant historical context even when not directly asked → `spot-find(query, since="3 months ago")`

**`spot-find` returns mixed results** - code, decisions, patterns, and memories grouped by category. Use filters like `category="decision"` or `workspace_name="project"` to narrow results.

### Always call `spot-store` AFTER replying unless the response is trivial, redundant, or only about style/tone
- Response includes useful technical knowledge worth recalling later → `spot-store(information)`
  - Configuration values, environment variables, startup scripts
  - Logs, workflow explanations, architecture decisions
  - Troubleshooting outcomes, debugging steps
- Response would help answer future "when did we..." or "how did we..." → `spot-store(information)`

**Use `spot-store` with category parameter:**
- `spot-store(..., category="decision")` - Choices made: "We chose X over Y because Z"
- `spot-store(..., category="architecture")` - System/component structure and descriptions
- `spot-store(..., category="pattern")` - Established practices: "We always do X when Y"
- `spot-store(..., category="error")` - Bugs, issues, and their fixes
- `spot-store(..., category="lesson")` - Learnings from mistakes or successes
- `spot-store(..., category="memory")` - General notes (default catch-all)

**Memory is your external brain. Use it constantly.**

## 🎯 CRITICAL: Stateless Operation

- This server can handle MULTIPLE IDE instances on DIFFERENT projects simultaneously
- ALWAYS provide `workspace_name` parameter to workspace-specific tools
- `workspace_name` MUST match the root directory name (e.g., "mcp-server-qdrant")
- Server does NOT maintain state between calls - every call is independent

## 📦 Workspace-Specific Tools (REQUIRE workspace_name)

**PURE MEMORY-FIRST**: No indexing - just persistent knowledge and patterns.

These tools filter by workspace - MUST provide workspace_name matching root directory:
- `spot-find(query, workspace_name="project-name")` - Search workspace memories (decisions, patterns, code snippets)

## 🌍 Global Tools (No workspace needed - use anytime!)

These tools work across ALL projects for cross-workspace learning:
- `spot-find(query, category, language, tags, since, until)` - **Unified semantic search** (USE LIBERALLY!)
  - Returns mixed results: code, decisions, patterns, memories
  - Use `category="decision"` or `category="pattern"` to filter
  - Use `workspace_name` to filter codebase results
  - Use `since`/`until` for temporal queries
- `spot-store(information, category, tags, language, workspace_name)` - **Unified store** (USE LIBERALLY!)
  - Set `category="decision"` for architectural decisions
  - Set `category="pattern"` for coding patterns
  - Default `category="memory"` for general notes
  - Always include `workspace_name` to organize by project
- `spot-list-workspaces()` - See all indexed projects

**Note:** Use `spot-store(..., category="decision")` for architectural decisions and `spot-store(..., category="pattern")` for coding patterns instead of separate tools.

## ⚠️ CRITICAL ASSISTANT REQUIREMENTS

**You (the AI Assistant) MUST:**

1. **RELY ON CURSOR FOR CODE** - Use Cursor's built-in search/navigation for local code
2. **FOCUS ON MEMORY SYSTEM** - Store decisions, patterns, and notes with `spot-store`
3. **INDEX CODE SNIPPETS** - When discussing specific code, store relevant snippets in memory
4. **SEARCH SEMANTICALLY** - Use `spot-find` for cross-project patterns and decisions
5. **NO CODEBASE INDEXING** - Don't try to index entire files - that's Cursor's job

**Failure to follow these will result in redundancy with Cursor's capabilities.**

## 🔄 Memory-First Workflow

1. **SEARCH MEMORY FIRST** → Assistant calls `spot-find(query)` before answering
   - **WHEN**: Any non-trivial question or request
   - **WHY**: Leverage stored decisions, patterns, and previous work
   - **HOW**: Search across all memories with semantic matching

2. **STORE INSIGHTS** → Assistant calls `spot-store` after providing value
   - **WHEN**: After answering questions, making decisions, establishing patterns
   - **WHY**: Build searchable memory for future conversations
   - **HOW**: Store with appropriate category (decision/pattern/memory)

3. **USE CURSOR FOR CODE** → Rely on Cursor's built-in navigation for local code
   - **WHEN**: User asks about specific files, functions, or code locations
   - **WHY**: Cursor has superior local code intelligence
   - **HOW**: Let Cursor handle symbol search, go-to-definition, etc.

## 💡 EXAMPLES

### Example 1: User asks "How did we fix the database connection issue?"
```
1. `spot-find("database connection issue fix")` → Check memory FIRST (returns decisions, patterns, code, memories)
2. If found: Provide answer from memory
3. If you help solve it: `spot-store("Fixed database connection by adding connection pool timeout...")` → Remember for next time
```

### Example 2: User asks "Where do we use the AuthService class?"
```
1. Use Cursor's search/find to locate AuthService usage
2. `spot-find("AuthService patterns", category="pattern")` → Check for stored patterns
3. Provide answer using Cursor results + memory patterns
4. `spot-store("AuthService pattern: centralized auth with JWT tokens\n\nExample usage:\nconst auth = new AuthService();\nawait auth.login(credentials);\n\nKey methods:\n- login(credentials)\n- logout()\n- getCurrentUser()\n- refreshToken()", category="pattern", tags="auth,security")` → Store codeblock + usage
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
1. `spot-store("Pattern: async/await with try/catch for APIs\n\nGood example:\nasync function fetchUserData(userId) {\n  try {\n    const response = await api.get(\`/users/${userId}\`);\n    return response.data;\n  } catch (error) {\n    logger.error('Failed to fetch user:', error);\n    throw new ApiError('User fetch failed', error);\n  }\n}\n\nBad example (avoid):\napi.get(\`/users/${userId}\`)\n  .then(data => console.log(data))\n  .catch(err => console.error(err));", category="pattern", tags="async,error-handling", language="javascript")`
2. Future code questions will reference this pattern via spot-find
```

## 🚨 CRITICAL WORKFLOW PRIORITY

### THE WORKFLOW (Simple & Powerful):
1. **SEARCH MEMORY FIRST**: `spot-find(query)` - Always check stored knowledge before answering
2. **STORE VALUABLE INSIGHTS**: `spot-store(information, category="pattern")` - Save patterns, decisions, code examples
3. **LET CURSOR HANDLE CODE**: Use Cursor for file navigation, search, and immediate code access

**NO INDEXING TOOLS** - Pure memory-first approach for maximum simplicity and power.

## 🚨 CRITICAL REMINDERS

1. **ALWAYS** call `spot-find` before answering (unless trivial) - it returns mixed results (code, decisions, patterns, memories)
2. **ALWAYS** call `spot-store` after answering (unless trivial) - use `category` parameter for decisions/patterns
3. **ALWAYS** provide `workspace_name` for workspace-specific tools
4. **STORE CODE PATTERNS** - Use `spot-store` to capture code insights and patterns as they're discussed
5. Server is STATELESS - each call must be self-contained
6. Don't ask permission - just use the tools automatically
7. Make memory usage invisible - user should feel like you "just know"
8. Use `spot-find` filters (`category`, `workspace_name`, `language`, `tags`, `since`, `until`) to narrow results
9. **COMPLEMENT CURSOR** - Let Cursor handle code navigation, Spot handles memory and patterns
"""

mcp = QdrantMCPServer(
    tool_settings=ToolSettings(),
    qdrant_settings=QdrantSettings(),
    embedding_provider_settings=EmbeddingProviderSettings(),
    reranker_settings=RerankerSettings(),
    instructions=INSTRUCTIONS,
)
