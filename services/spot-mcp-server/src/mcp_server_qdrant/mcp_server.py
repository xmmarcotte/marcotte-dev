import json
import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from mcp_server_qdrant.common.filters import make_indexes
from mcp_server_qdrant.common.func_tools import make_partial_function
from mcp_server_qdrant.embeddings.factory import create_embedding_provider
from mcp_server_qdrant.qdrant import ArbitraryFilter, Entry, QdrantConnector
from mcp_server_qdrant.reranker import LocalReranker
from mcp_server_qdrant.settings import (
    EmbeddingProviderSettings,
    QdrantSettings,
    RerankerSettings,
    ToolSettings,
)
from pydantic import Field
from qdrant_client import models

logger = logging.getLogger(__name__)


# Add normalization function at the top-level (after imports)
def normalize_metadata(metadata):
    import ast
    import datetime

    def add_timestamp(md):
        md = dict(md) if md is not None else {}
        now = datetime.datetime.now(datetime.timezone.utc)
        md["timestamp"] = now.timestamp()  # Unix timestamp (numeric for range queries)
        return md

    if metadata is None:
        return add_timestamp({})
    if isinstance(metadata, dict):
        return add_timestamp(metadata)
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                return add_timestamp(parsed)
            else:
                return add_timestamp({"value": parsed})
        except Exception:
            # Try ast.literal_eval for single-quoted dict/list
            try:
                parsed = ast.literal_eval(metadata)
                if isinstance(parsed, dict) or isinstance(parsed, list):
                    return add_timestamp(parsed)
                else:
                    return add_timestamp({"value": parsed})
            except Exception:
                return add_timestamp({"value": metadata})
    return add_timestamp({"value": metadata})


# FastMCP is an alternative interface for declaring the capabilities
# of the server. Its API is based on FastAPI.
class QdrantMCPServer(FastMCP):
    """
    A MCP server for Qdrant.
    """

    def __init__(
        self,
        tool_settings: ToolSettings,
        qdrant_settings: QdrantSettings,
        embedding_provider_settings: EmbeddingProviderSettings,
        reranker_settings: RerankerSettings | None = None,
        name: str = "mcp-server-qdrant",
        instructions: str | None = None,
        **settings: Any,
    ):
        self.tool_settings = tool_settings
        self.qdrant_settings = qdrant_settings
        self.embedding_provider_settings = embedding_provider_settings
        self.reranker_settings = reranker_settings or RerankerSettings()

        self.embedding_provider = create_embedding_provider(embedding_provider_settings)

        # Initialize reranker for improved precision
        self.reranker = LocalReranker(
            model_name=self.reranker_settings.model,
            enabled=self.reranker_settings.enabled,
        )

        self.qdrant_connector = QdrantConnector(
            qdrant_settings.location,
            qdrant_settings.api_key,
            qdrant_settings.collection_name,
            self.embedding_provider,
            qdrant_settings.local_path,
            make_indexes(qdrant_settings.filterable_fields_dict()),
            reranker=self.reranker,
        )

        logger.info("📊 Spot memory server: bge-large-en-v1.5 + reranking")
        self.auto_index_enabled = True

        super().__init__(name=name, instructions=instructions, **settings)

        self.setup_tools()

    def _normalize_workspace_name(self, name: str) -> str:
        """
        Normalize workspace name for consistency.
        - Convert to lowercase
        - Replace spaces and special chars with hyphens
        - Remove leading/trailing hyphens
        """
        import re

        normalized = name.lower()
        normalized = re.sub(
            r"[^\w\-]", "-", normalized
        )  # Replace non-alphanumeric with -
        normalized = re.sub(r"-+", "-", normalized)  # Collapse multiple hyphens
        normalized = normalized.strip("-")  # Remove leading/trailing hyphens

        if normalized != name:
            logger.info(f"Normalized workspace name: '{name}' -> '{normalized}'")

        return normalized

    def _format_response_with_guidance(self, result: str, guidance: str = None) -> str:
        """
        Include optional agent instructions in responses.

        Args:
            result: The main result to return
            guidance: Optional guidance hint for the AI agent

        Returns:
            Formatted response with guidance if provided
        """
        if guidance:
            return f"{result}\n\n[Agent Guidance: {guidance}]"
        return result

    def _add_workspace_filter(
        self, existing_filter: models.Filter | None = None
    ) -> models.Filter:
        """Add workspace filter to existing filter conditions."""
        if not self.current_workspace:
            # No workspace set, return existing filter or no filter
            return existing_filter or models.Filter(must=[])

        workspace_condition = models.FieldCondition(
            key="metadata.workspace",
            match=models.MatchValue(value=self.current_workspace),
        )

        if existing_filter is None:
            return models.Filter(must=[workspace_condition])

        # Merge with existing filter
        must_conditions = list(existing_filter.must or [])
        must_conditions.append(workspace_condition)
        return models.Filter(
            must=must_conditions,
            should=existing_filter.should,
            must_not=existing_filter.must_not,
        )

    def format_entry(self, entry: Entry) -> str:
        """
        Feel free to override this method in your subclass to customize the format of the entry.
        """
        entry_metadata = json.dumps(entry.metadata) if entry.metadata else ""
        return f"<entry><content>{entry.content}</content><metadata>{entry_metadata}</metadata></entry>"

    def setup_tools(self):
        """
        Register the tools in the server.
        """

        async def store(
            ctx: Context,
            information: Annotated[str, Field(description="Text to store")],
            category: Annotated[
                str | None,
                Field(
                    description="Category: 'decision', 'pattern', 'memory' (default). Use 'decision' for architectural decisions, 'pattern' for coding patterns, 'memory' for general notes."
                ),
            ] = None,
            tags: Annotated[
                str | None,
                Field(
                    description="Comma-separated tags (e.g., 'auth,security,database')"
                ),
            ] = None,
            language: Annotated[
                str | None,
                Field(
                    description="Programming language (for patterns, e.g., 'python', 'javascript')"
                ),
            ] = None,
            project: Annotated[
                str | None, Field(description="Project name (for decisions/patterns)")
            ] = None,
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to store in (defaults to main collection)"
                ),
            ] = None,
            metadata: Annotated[
                dict | str | None,
                Field(
                    description="Additional metadata (object or stringified JSON). Category, tags, language, and project will be merged into this."
                ),
            ] = None,
        ) -> str:
            """
            Unified store for any type of content (decisions, patterns, memories).
            Automatically sets appropriate metadata based on category.
            """
            target_collection = collection_name or self.qdrant_settings.collection_name

            # Determine category (default to 'memory' if not specified)
            cat = category or "memory"

            # Build metadata
            store_metadata = {}
            if isinstance(metadata, dict):
                store_metadata.update(metadata)
            elif isinstance(metadata, str):
                try:
                    import json

                    store_metadata.update(json.loads(metadata))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

            # Set category-specific metadata
            store_metadata["category"] = cat
            store_metadata["type"] = {
                "decision": "architectural_decision",
                "pattern": "coding_pattern",
                "memory": "memory",
            }.get(cat, "memory")

            if tags:
                store_metadata["tags"] = tags
                store_metadata["tag_list"] = [t.strip() for t in tags.split(",")]

            if language:
                store_metadata["language"] = language

            if project:
                store_metadata["project"] = project

            # For decisions, extract decision text if it's structured
            if cat == "decision" and "decision:" in information.lower():
                # Try to extract decision from structured text
                lines = information.split("\n")
                for line in lines:
                    if line.lower().startswith("decision:"):
                        store_metadata["decision"] = line[10:].strip()
                        break

            # For patterns, extract pattern text if it's structured
            if cat == "pattern" and "pattern:" in information.lower():
                lines = information.split("\n")
                for line in lines:
                    if line.lower().startswith("pattern:"):
                        store_metadata["pattern"] = line[9:].strip()
                        break

            await ctx.debug(
                f"Storing {cat}: {information[:100]}... (tags: {tags}, language: {language})"
            )

            entry = Entry(
                content=information, metadata=normalize_metadata(store_metadata)
            )

            await self.qdrant_connector.store(entry, collection_name=target_collection)

            result = f"Stored {cat}: {information[:100]}"
            if tags:
                result += f" (tags: {tags})"
            return result

        async def search(
            ctx: Context,
            query: Annotated[
                str,
                Field(
                    description="What to search for - returns code, decisions, patterns, and memories"
                ),
            ],
            workspace_name: Annotated[
                str | None,
                Field(
                    description="Workspace/project name to filter codebase results. Omit for global search across all workspaces."
                ),
            ] = None,
            category: Annotated[
                str | None,
                Field(
                    description="Filter by category: 'codebase', 'decision', 'pattern', 'memory'. Omit to search all categories."
                ),
            ] = None,
            language: Annotated[
                str | None,
                Field(
                    description="Filter by programming language (e.g., 'python', 'javascript')"
                ),
            ] = None,
            tags: Annotated[
                str | None,
                Field(
                    description="Filter by tags (comma-separated, e.g., 'async,api')"
                ),
            ] = None,
            since: Annotated[
                str | None,
                Field(
                    description="ISO timestamp to search from (e.g., '2024-01-01T00:00:00Z')"
                ),
            ] = None,
            until: Annotated[
                str | None, Field(description="ISO timestamp to search until")
            ] = None,
            collection_name: Annotated[
                str | None,
                Field(description="Collection to search (defaults to main collection)"),
            ] = None,
            query_filter: ArbitraryFilter | None = None,
        ) -> list[str]:
            """
            Unified semantic search across all content types (code, decisions, patterns, memories).
            Returns mixed results with optional filters for workspace, category, language, tags, and time.
            """
            target_collection = collection_name or self.qdrant_settings.collection_name

            # Build filter conditions
            conditions = []

            # Category filter
            if category:
                conditions.append(
                    models.FieldCondition(
                        key="metadata.category", match=models.MatchValue(value=category)
                    )
                )
                # If filtering codebase, add workspace filter
                if category == "codebase" and workspace_name:
                    target_workspace = self._normalize_workspace_name(workspace_name)
                    conditions.append(
                        models.FieldCondition(
                            key="metadata.workspace",
                            match=models.MatchValue(value=target_workspace),
                        )
                    )
            elif workspace_name:
                # If no category but workspace specified, filter codebase results by workspace
                # We'll do this in post-processing for mixed results
                target_workspace = self._normalize_workspace_name(workspace_name)

            # Language filter
            if language:
                conditions.append(
                    models.FieldCondition(
                        key="metadata.language", match=models.MatchValue(value=language)
                    )
                )

            # Tags filter
            if tags:
                tag_list = [t.strip() for t in tags.split(",")]
                for tag in tag_list:
                    conditions.append(
                        models.FieldCondition(
                            key="metadata.tags", match=models.MatchText(text=tag)
                        )
                    )

            # Time filters
            if since or until:
                import datetime

                if since:
                    try:
                        since_dt = datetime.datetime.fromisoformat(
                            since.replace("Z", "+00:00")
                        )
                        since_unix = since_dt.timestamp()
                        conditions.append(
                            models.FieldCondition(
                                key="metadata.timestamp",
                                range=models.Range(gte=since_unix),
                            )
                        )
                    except ValueError:
                        pass
                if until:
                    try:
                        until_dt = datetime.datetime.fromisoformat(
                            until.replace("Z", "+00:00")
                        )
                        until_unix = until_dt.timestamp()
                        conditions.append(
                            models.FieldCondition(
                                key="metadata.timestamp",
                                range=models.Range(lte=until_unix),
                            )
                        )
                    except ValueError:
                        pass

            # Merge with arbitrary filter if provided
            if query_filter:
                query_filter_obj = models.Filter(**query_filter)
                if conditions:
                    # Merge conditions
                    must_conditions = list(query_filter_obj.must or []) + conditions
                    query_filter_obj = models.Filter(
                        must=must_conditions,
                        should=query_filter_obj.should,
                        must_not=query_filter_obj.must_not,
                    )
                else:
                    query_filter_obj = query_filter_obj
            else:
                query_filter_obj = (
                    models.Filter(must=conditions) if conditions else None
                )

            await ctx.debug(
                f"Searching for: {query} (filters: category={category}, workspace={workspace_name})"
            )

            entries = await self.qdrant_connector.search(
                query,
                collection_name=target_collection,
                limit=self.qdrant_settings.search_limit,
                query_filter=query_filter_obj,
            )

            # Post-process: if workspace specified but no category, filter codebase results
            if workspace_name and not category:
                target_workspace = self._normalize_workspace_name(workspace_name)
                filtered_entries = []
                for entry in entries:
                    meta = entry.metadata or {}
                    entry_category = meta.get("category", "other")
                    if entry_category == "codebase":
                        entry_workspace = meta.get("workspace", "")
                        if entry_workspace == target_workspace:
                            filtered_entries.append(entry)
                    else:
                        # Non-codebase entries are global, include them
                        filtered_entries.append(entry)
                entries = filtered_entries

            if not entries:
                filter_desc = []
                if category:
                    filter_desc.append(f"category={category}")
                if workspace_name:
                    filter_desc.append(f"workspace={workspace_name}")
                filter_str = f" ({', '.join(filter_desc)})" if filter_desc else ""
                return [f"No results found for '{query}'{filter_str}"]

            # Group results by category for better presentation
            by_category = {
                "codebase": [],
                "decision": [],
                "pattern": [],
                "memory": [],
                "other": [],
            }
            for entry in entries:
                meta = entry.metadata or {}
                cat = meta.get("category", "other")
                by_category.get(cat, by_category["other"]).append(entry)

            content = [f"Found {len(entries)} results for '{query}':\n"]

            # Show decisions first
            if by_category["decision"]:
                content.append(f"\n📋 Decisions ({len(by_category['decision'])}):")
                for entry in by_category["decision"][:5]:
                    meta = entry.metadata or {}
                    decision = meta.get("decision", entry.content[:100])
                    content.append(f"  • {decision}")

            # Then patterns
            if by_category["pattern"]:
                content.append(f"\n🎨 Patterns ({len(by_category['pattern'])}):")
                for entry in by_category["pattern"][:5]:
                    meta = entry.metadata or {}
                    pattern = meta.get("pattern", entry.content[:100])
                    content.append(f"  • {pattern}")

            # Then codebase
            if by_category["codebase"]:
                content.append(f"\n💻 Code ({len(by_category['codebase'])}):")
                for entry in by_category["codebase"][:10]:
                    meta = entry.metadata or {}
                    file_path = meta.get("file_path", "unknown")
                    name = meta.get("name", "")
                    start_line = meta.get("start_line", "")
                    ref = file_path
                    if start_line:
                        ref += f":{start_line}"
                    if name:
                        ref += f" - {name}"
                    content.append(f"  • {ref}")

            # Then memories/other
            if by_category["memory"] or by_category["other"]:
                content.append(
                    f"\n📝 Other ({len(by_category['memory']) + len(by_category['other'])}):"
                )
                for entry in (by_category["memory"] + by_category["other"])[:5]:
                    content.append(f"  • {entry.content[:150]}...")

            return content

        search_foo = search
        store_foo = store

        # Note: search and store don't use wrap_filters since they have their own filter logic
        if self.qdrant_settings.collection_name:
            search_foo = make_partial_function(
                search_foo, {"collection_name": self.qdrant_settings.collection_name}
            )
            store_foo = make_partial_function(
                store_foo, {"collection_name": self.qdrant_settings.collection_name}
            )

        self.tool(
            search_foo,
            name="spot-find",
            description="Unified semantic search across all content (code, decisions, patterns, memories). Returns mixed results grouped by category. Use liberally before answering questions. Supports filters: workspace_name, category, language, tags, since, until.",
        )

        if not self.qdrant_settings.read_only:
            # Those methods can modify the database
            self.tool(
                store_foo,
                name="spot-store",
                description="Unified store for any content type. Use liberally after answering. Set category='decision' for architectural decisions, 'pattern' for coding patterns, 'memory' for general notes. Supports tags, language, project metadata.",
            )

        # Memory and decision tools
        self.setup_memory_tools()

    def setup_memory_tools(self):
        """Register memory, decision, and pattern tools."""

        async def list_workspaces(ctx: Context) -> str:
            """List all workspaces that have stored memories."""
            try:
                # Query for all unique workspace names in memories
                entries = await self.qdrant_connector.search(
                    "any content",  # Broad search to find all entries
                    limit=1000,  # Get many results to find all workspaces
                    collection_name=self.qdrant_settings.collection_name,
                )

                workspaces = set()
                for entry in entries:
                    meta = entry.metadata or {}
                    workspace = meta.get("workspace_name")
                    if workspace:
                        workspaces.add(workspace)

                if not workspaces:
                    return "No workspaces with stored memories found."

                result = (
                    f"📁 **Workspaces with memories:** ({len(workspaces)} total)\n\n"
                )
                for workspace in sorted(workspaces):
                    result += f"• {workspace}\n"

                return result

            except Exception as e:
                logger.error(f"Failed to list workspaces: {e}")
                return f"Error listing workspaces: {str(e)}"

        # Register analysis tools

        self.tool(
            list_workspaces,
            name="spot-list-workspaces",
            description="List all workspaces with stored memories. Use when: user asks 'what projects do you know about?' or to verify workspace isolation.",
        )

        # Advanced query tools
        async def get_smart_context(
            ctx: Context,
            topic: Annotated[
                str,
                Field(description="The topic or question to get context for"),
            ],
            workspace_name: Annotated[
                str | None,
                Field(
                    description="Workspace/project name for codebase context. MUST match root directory name. IDE should provide this. If not provided, only global decisions/patterns are returned."
                ),
            ] = None,
            max_results: Annotated[
                int,
                Field(description="Maximum number of context items to retrieve"),
            ] = 15,
            include_code: Annotated[
                bool,
                Field(
                    description="Include actual code snippets in results (default: true)"
                ),
            ] = True,
            collection_name: Annotated[
                str | None,
                Field(description="Collection to search (defaults to main collection)"),
            ] = None,
        ) -> str:
            """
            Get smart context by retrieving relevant decisions, patterns, and code together.
            This provides a comprehensive view combining multiple data types.

            Special queries:
            - "project overview" or "project summary" - Get high-level project structure
            - "list classes" or "list functions" - Get component inventory
            """
            target_collection = collection_name or self.qdrant_settings.collection_name

            # Check for special queries
            topic_lower = topic.lower()
            if any(
                x in topic_lower
                for x in ["project overview", "project summary", "project structure"]
            ):
                return await self._get_project_overview(target_collection)
            elif any(
                x in topic_lower
                for x in ["list classes", "list functions", "list components"]
            ):
                return await self._get_component_inventory(
                    target_collection, topic_lower
                )

            # Search across all types, but filter codebase by workspace at query time
            # Build filter that allows decisions/patterns globally but filters codebase by workspace
            # We'll do two searches: one for codebase (with workspace filter) and one for others

            # Search for codebase with workspace filter
            codebase_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value="codebase"),
                    )
                ]
            )
            codebase_filter = self._add_workspace_filter(codebase_filter)

            codebase_entries = (
                await self.qdrant_connector.search(
                    topic,
                    collection_name=target_collection,
                    limit=max_results,
                    query_filter=codebase_filter,
                )
                if include_code
                else []
            )

            # Search for decisions and patterns (no workspace filter needed)
            other_filter = models.Filter(
                should=[
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value="decision"),
                    ),
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value="pattern"),
                    ),
                ]
            )

            other_entries = await self.qdrant_connector.search(
                topic,
                collection_name=target_collection,
                limit=max_results,
                query_filter=other_filter,
            )

            if not codebase_entries and not other_entries:
                return f"No context found for: {topic}"

            # Group by category
            decisions = []
            patterns = []
            codebase = []
            other = []

            for entry in other_entries:
                meta = entry.metadata or {}
                category = meta.get("category", "other")
                if category == "decision":
                    decisions.append(entry)
                elif category == "pattern":
                    patterns.append(entry)
                else:
                    other.append(entry)

            # Add codebase entries (already filtered by workspace)
            codebase.extend(codebase_entries)

            # Build comprehensive context
            result = [f"Smart Context for: {topic}\n"]

            if decisions:
                result.append(f"\n📋 Related Decisions ({len(decisions)}):")
                for entry in decisions[:5]:
                    meta = entry.metadata or {}
                    decision = meta.get("decision", "")
                    if decision:
                        result.append(f"- {decision}")
                    else:
                        result.append(f"- {entry.content[:200]}...")

            if patterns:
                result.append(f"\n🎨 Related Patterns ({len(patterns)}):")
                for entry in patterns[:5]:
                    meta = entry.metadata or {}
                    pattern = meta.get("pattern", "")
                    if pattern:
                        result.append(f"- {pattern}")
                    else:
                        result.append(f"- {entry.content[:200]}...")

            if codebase:
                result.append(f"\n💻 Related Code ({len(codebase)}):")
                for entry in codebase[:10]:
                    meta = entry.metadata or {}
                    file_path = meta.get("file_path", "unknown")
                    name = meta.get("name", "")
                    chunk_type = meta.get("chunk_type", "")
                    start_line = meta.get("start_line", "")

                    # Build code reference
                    ref = file_path
                    if start_line:
                        ref += f":{start_line}"
                    if name and chunk_type:
                        ref += f" - {chunk_type}: {name}"
                    result.append(f"- {ref}")

                    # Include code snippet if requested
                    if include_code and name:
                        code_lines = entry.content.split("\n")
                        # Show first 5 lines of actual code
                        code_preview = []
                        for line in code_lines:
                            if line.strip() and not line.startswith("#"):
                                code_preview.append(line)
                                if len(code_preview) >= 5:
                                    break
                        if code_preview:
                            result.append(
                                f"  ```\n  {chr(10).join(code_preview[:3])}\n  ...```"
                            )

            if other:
                result.append(f"\n📝 Other Context ({len(other)}):")
                for entry in other[:5]:
                    result.append(f"- {entry.content[:200]}...")

            return "\n".join(result)

        # Temporal search tool
        async def search_by_time(
            ctx: Context,
            query: Annotated[
                str,
                Field(description="Natural language query to search for"),
            ],
            since: Annotated[
                str | None,
                Field(
                    description="ISO timestamp to search from (e.g., '2024-01-01T00:00:00Z')"
                ),
            ] = None,
            until: Annotated[
                str | None,
                Field(description="ISO timestamp to search until"),
            ] = None,
            category: Annotated[
                str | None,
                Field(
                    description="Filter by category (decision, pattern, codebase, memory)"
                ),
            ] = None,
            collection_name: Annotated[
                str | None,
                Field(description="Collection to search (defaults to main collection)"),
            ] = None,
        ) -> list[str]:
            """
            Search with temporal filters to find entries from specific time periods.
            Useful for tracking changes, recent decisions, or evolution over time.
            """
            target_collection = collection_name or self.qdrant_settings.collection_name

            # Build filter conditions
            from qdrant_client import models

            conditions = []

            # Convert ISO timestamps to Unix timestamps for range queries
            import datetime

            if since:
                try:
                    since_dt = datetime.datetime.fromisoformat(
                        since.replace("Z", "+00:00")
                    )
                    since_unix = since_dt.timestamp()
                    conditions.append(
                        models.FieldCondition(
                            key="metadata.timestamp", range=models.Range(gte=since_unix)
                        )
                    )
                except ValueError:
                    # If not valid ISO, skip this filter
                    pass

            if until:
                try:
                    until_dt = datetime.datetime.fromisoformat(
                        until.replace("Z", "+00:00")
                    )
                    until_unix = until_dt.timestamp()
                    conditions.append(
                        models.FieldCondition(
                            key="metadata.timestamp", range=models.Range(lte=until_unix)
                        )
                    )
                except ValueError:
                    # If not valid ISO, skip this filter
                    pass

            if category:
                conditions.append(
                    models.FieldCondition(
                        key="metadata.category", match=models.MatchValue(value=category)
                    )
                )
                # If filtering by codebase category, add workspace filter
                if category == "codebase":
                    workspace_filter = self._add_workspace_filter()
                    if workspace_filter and workspace_filter.must:
                        conditions.extend(workspace_filter.must)

            query_filter = models.Filter(must=conditions) if conditions else None

            entries = await self.qdrant_connector.search(
                query,
                collection_name=target_collection,
                limit=self.qdrant_settings.search_limit,
                query_filter=query_filter,
            )

            # If no category specified, filter codebase results by workspace in post-processing
            if not category:
                filtered_entries = []
                for entry in entries:
                    meta = entry.metadata or {}
                    entry_category = meta.get("category", "other")
                    if entry_category == "codebase":
                        entry_workspace = meta.get("workspace")
                        if (
                            self.current_workspace
                            and entry_workspace != self.current_workspace
                        ):
                            continue  # Skip codebase entries from other workspaces
                    filtered_entries.append(entry)
                entries = filtered_entries

            if not entries:
                time_desc = ""
                if since and until:
                    time_desc = f" between {since} and {until}"
                elif since:
                    time_desc = f" since {since}"
                elif until:
                    time_desc = f" until {until}"

                return [f"No results found for '{query}'{time_desc}"]

            content = [f"Results for '{query}'"]
            if since or until or category:
                filters = []
                if since:
                    filters.append(f"since {since}")
                if until:
                    filters.append(f"until {until}")
                if category:
                    filters.append(f"category={category}")
                content[0] += f" ({', '.join(filters)})"

            for entry in entries:
                meta = entry.metadata or {}
                # Convert Unix timestamp to ISO for display
                timestamp_display = "unknown"
                if "timestamp" in meta:
                    try:
                        timestamp_unix = meta["timestamp"]
                        dt = datetime.datetime.fromtimestamp(
                            timestamp_unix, tz=datetime.timezone.utc
                        )
                        timestamp_display = dt.isoformat()
                    except Exception:
                        timestamp_display = "unknown"

                content.append(f"[{timestamp_display}] {self.format_entry(entry)}")

            return content

        # Register smart context tool

        async def search_patterns(
            ctx: Context,
            query: Annotated[
                str,
                Field(
                    description="What to search for (e.g., 'error handling', 'authentication')"
                ),
            ],
            language: Annotated[
                str | None,
                Field(
                    description="Filter by programming language (e.g., 'python', 'javascript')"
                ),
            ] = None,
            tags: Annotated[
                str | None,
                Field(
                    description="Filter by tags (comma-separated, e.g., 'async,api')"
                ),
            ] = None,
            project: Annotated[
                str | None,
                Field(description="Filter by project name"),
            ] = None,
            collection_name: Annotated[
                str | None,
                Field(description="Collection to search (defaults to main collection)"),
            ] = None,
        ) -> list[str]:
            """
            Search for patterns with advanced filtering by language, tags, and project.
            Great for cross-project learning and finding reusable patterns.
            """
            target_collection = collection_name or self.qdrant_settings.collection_name

            # Build filter conditions
            conditions = [
                models.FieldCondition(
                    key="metadata.category", match=models.MatchValue(value="pattern")
                )
            ]

            if language:
                conditions.append(
                    models.FieldCondition(
                        key="metadata.language", match=models.MatchValue(value=language)
                    )
                )

            if tags:
                # Search for any of the provided tags
                tag_list = [t.strip() for t in tags.split(",")]
                for tag in tag_list:
                    conditions.append(
                        models.FieldCondition(
                            key="metadata.tags", match=models.MatchText(text=tag)
                        )
                    )

            if project:
                conditions.append(
                    models.FieldCondition(
                        key="metadata.project", match=models.MatchValue(value=project)
                    )
                )

            query_filter = models.Filter(must=conditions)

            entries = await self.qdrant_connector.search(
                query,
                collection_name=target_collection,
                limit=20,
                query_filter=query_filter,
            )

            if not entries:
                filters = []
                if language:
                    filters.append(f"language={language}")
                if tags:
                    filters.append(f"tags={tags}")
                if project:
                    filters.append(f"project={project}")

                filter_str = f" ({', '.join(filters)})" if filters else ""
                return [f"No patterns found for '{query}'{filter_str}"]

            results = [f"Found {len(entries)} patterns for '{query}':\n"]

            for entry in entries:
                meta = entry.metadata or {}
                pattern = meta.get("pattern", "Unknown")
                lang = meta.get("language", "")
                pattern_tags = meta.get("tags", "")
                proj = meta.get("project", "")
                use_case = meta.get("use_case", "")

                result_line = f"\n• {pattern}"
                details = []
                if lang:
                    details.append(f"[{lang}]")
                if pattern_tags:
                    details.append(f"tags: {pattern_tags}")
                if proj:
                    details.append(f"project: {proj}")

                if details:
                    result_line += f" ({', '.join(details)})"

                results.append(result_line)

                if use_case:
                    results.append(f"  Use Case: {use_case}")

                # Show example if present
                example = meta.get("example", "")
                if example:
                    example_lines = example.split("\n")[:3]  # First 3 lines only
                    results.append(f"  Example: {example_lines[0]}")
                    if len(example_lines) > 1:
                        for line in example_lines[1:]:
                            results.append(f"           {line}")

                results.append("")  # Blank line

            return results

    async def _get_project_overview(self, collection_name: str) -> str:
        """Get a high-level project overview."""
        # Add workspace filter
        workspace_filter = self._add_workspace_filter()

        entries = await self.qdrant_connector.search(
            "file imports classes functions",
            collection_name=collection_name,
            limit=100,
            query_filter=workspace_filter,
        )

        if not entries:
            return "No code patterns stored yet. Use spot-store() to save code patterns and examples as memories."

        # Aggregate project stats
        languages = {}
        files = set()
        classes = []
        functions = []

        for entry in entries:
            meta = entry.metadata or {}
            if meta.get("category") != "codebase":
                continue

            lang = meta.get("language", "unknown")
            languages[lang] = languages.get(lang, 0) + 1

            file_path = meta.get("file_path")
            if file_path:
                files.add(file_path)

            chunk_type = meta.get("chunk_type", "")
            name = meta.get("name", "")
            if chunk_type == "class" and name:
                classes.append(f"{file_path}::{name}")
            elif chunk_type in ["function", "method"] and name:
                functions.append(name)

        result = ["📊 Project Overview\n"]
        result.append(f"Total Files: {len(files)}")
        result.append(
            f"Languages: {', '.join(f'{k} ({v})' for k, v in sorted(languages.items(), key=lambda x: -x[1]))}"
        )
        result.append(f"Classes: {len(classes)}")
        result.append(f"Functions/Methods: {len(functions)}")

        if classes:
            result.append(f"\nKey Classes ({min(10, len(classes))}):")
            for cls in sorted(classes)[:10]:
                result.append(f"- {cls}")

        return "\n".join(result)

    async def _get_component_inventory(self, collection_name: str, query: str) -> str:
        """Get a filtered list of components."""
        # Determine what to list
        list_classes = "class" in query
        list_functions = "function" in query
        list_all = "component" in query or (not list_classes and not list_functions)

        # Add workspace filter
        workspace_filter = self._add_workspace_filter()

        entries = await self.qdrant_connector.search(
            "classes functions methods",
            collection_name=collection_name,
            limit=200,
            query_filter=workspace_filter,
        )

        if not entries:
            return "No codebase indexed yet."

        classes = []
        functions = []

        for entry in entries:
            meta = entry.metadata or {}
            if meta.get("category") != "codebase":
                continue

            chunk_type = meta.get("chunk_type", "")
            name = meta.get("name", "")
            file_path = meta.get("file_path", "")

            if chunk_type == "class" and name:
                classes.append(f"{file_path}::{name}")
            elif chunk_type in ["function", "method"] and name:
                parent = meta.get("parent_class", "")
                if parent:
                    functions.append(f"{file_path}::{parent}.{name}")
                else:
                    functions.append(f"{file_path}::{name}")

        result = []

        if list_all or list_classes:
            result.append(f"Classes ({len(classes)}):")
            for cls in sorted(set(classes))[:50]:
                result.append(f"- {cls}")

        if list_all or list_functions:
            if result:
                result.append("")
            result.append(f"Functions/Methods ({len(functions)}):")
            for func in sorted(set(functions))[:50]:
                result.append(f"- {func}")

        return "\n".join(result)
