import json
import logging
import time
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field
from qdrant_client import models

from mcp_server_qdrant.common.filters import make_indexes
from mcp_server_qdrant.common.func_tools import make_partial_function
from mcp_server_qdrant.common.wrap_filters import wrap_filters
from mcp_server_qdrant.embeddings.factory import create_embedding_provider
from mcp_server_qdrant.qdrant import ArbitraryFilter, Entry, QdrantConnector
import hashlib
from mcp_server_qdrant.analysis import (
    CodeAnalyzer,
    CodeChunker,
    FileHashTracker,
    RelationshipMapper,
)
from mcp_server_qdrant.settings import (
    EmbeddingProviderSettings,
    QdrantSettings,
    RerankerSettings,
    ToolSettings,
)
from mcp_server_qdrant.reranker import LocalReranker

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

        # Initialize analysis components
        self.code_analyzer = CodeAnalyzer()
        self.relationship_mapper = RelationshipMapper()
        self.code_chunker = CodeChunker(max_chunk_size=500)
        # Note: UsageExtractor removed - language-specific feature
        self.file_tracker = FileHashTracker()

        # Track current workspace for isolation
        self.current_workspace = None
        self.last_index_time = None
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

    def _analyze_file_in_memory(self, file_path: str, file_content: str) -> "FileInfo":
        """
        Analyze a file in-memory (no filesystem access).
        Creates basic file info without language-specific parsing.

        Args:
            file_path: Path to the file (relative or absolute)
            file_content: Content of the file as string

        Returns:
            FileInfo object with basic information
        """
        from pathlib import Path
        from mcp_server_qdrant.analysis.codebase_scanner import FileInfo

        # Simple language detection from extension
        path_obj = Path(file_path)
        ext = path_obj.suffix.lower()

        # Minimal language map - just common extensions
        # Language-specific features removed per plan
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".sh": "shell",
            ".sql": "sql",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".md": "markdown",
        }
        language = language_map.get(ext, "text")

        # Create basic file info - no AST parsing, no structure extraction
        # Semantic search via embeddings will handle code understanding
        return FileInfo(
            path=file_path,
            language=language,
            size=len(file_content.encode("utf-8")),
            line_count=len(file_content.split("\n")),
            functions=[],  # No structure extraction
            classes=[],  # No structure extraction
            imports=[],  # No structure extraction
            exports=[],  # No structure extraction
        )

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
                except:
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
                    chunk_type = meta.get("chunk_type", "")
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

        filterable_conditions = (
            self.qdrant_settings.filterable_fields_dict_with_conditions()
        )

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

        async def index_codebase(
            ctx: Context,
            files: Annotated[
                dict[str, str],
                Field(
                    description="Dict of file_path: file_content to index. REQUIRED - IDE must send all file contents as dict. MCP servers are always remote and cannot access filesystem."
                ),
            ],
            workspace_name: Annotated[
                str,
                Field(
                    description="Workspace/project name for isolation. REQUIRED. MUST match the root directory name of the workspace (e.g., if workspace is 'my-project', use 'my-project'). IDE should extract this from the workspace root folder name."
                ),
            ],
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to store indexed code (defaults to 'codebase' collection)"
                ),
            ] = None,
        ) -> str:
            """
            Scan and index an entire codebase. Uses semantic chunking and embeddings for code understanding.
            Stores this information in Qdrant for semantic search and retrieval.

            MCP servers are always remote - IDE must provide all file contents via files parameter.
            No filesystem access is available.
            """
            if not files:
                return "Error: files parameter is REQUIRED. IDE must send all file contents as {path: content} dict."

            if not workspace_name:
                return "Error: workspace_name is REQUIRED. Provide workspace_name matching the root directory name."

            # Validate files dict
            if len(files) == 0:
                return "Error: files dict is empty. Provide at least one file to index."

            # Set workspace
            target_workspace = self._normalize_workspace_name(workspace_name)
            logger.info(f"Using provided workspace name: {target_workspace}")

            await ctx.debug(f"Workspace set to: {target_workspace}")

            # Use codebase collection by default
            codebase_collection = (
                collection_name or self.qdrant_settings.collection_name
            )

            # Analyze files in-memory
            logger.info(f"📂 Indexing {len(files)} files from IDE (remote server mode)")

            from mcp_server_qdrant.analysis.codebase_scanner import (
                FileInfo,
                ProjectStructure,
            )

            structure_files = []
            languages = {}

            for file_path, file_content in files.items():
                # Analyze file in-memory (no filesystem access)
                file_info = self._analyze_file_in_memory(file_path, file_content)
                structure_files.append(file_info)
                languages[file_info.language] = languages.get(file_info.language, 0) + 1

            # Create structure object
            structure = ProjectStructure(
                root_path="",  # Not used for remote servers
                files=structure_files,
                languages=languages,
                total_files=len(structure_files),
                entry_points=[],
                main_modules=[],
            )
            logger.info(
                f"📊 Found {len(structure.files)} files in {len(structure.languages)} languages: {', '.join(structure.languages.keys())}"
            )

            # Index each file with smart chunking
            indexed_count = 0
            chunk_count = 0
            seen_hashes = set()  # Deduplicate within this indexing run
            import asyncio

            # Process files - hash checking will skip unchanged files
            total_files = len(structure.files)
            logger.info(
                f"📦 Processing {total_files} files (hash checking enabled - unchanged files will be skipped)"
            )

            # Process files in parallel batches for better performance
            async def process_file(file_info, file_idx):
                """Process a single file and return chunks and file content."""
                logger.info(
                    f"📄 [{file_idx}/{total_files}] Processing: {file_info.path} ({file_info.language})"
                )

                # Get file content from provided files dict (always remote server)
                file_content = files.get(file_info.path)
                if file_content is None:
                    logger.warning(
                        f"⚠️  File not found in provided files: {file_info.path}"
                    )
                    return None, None

                file_size = len(file_content)
                logger.info(f"   ✓ Using provided content ({file_size:,} bytes)")

                # Check if file has changed using hash tracker
                if not self.file_tracker.has_changed(file_info.path, file_content):
                    logger.info(
                        f"   ⏭️  Skipping {file_info.path} (unchanged, hash matches)"
                    )
                    # Still mark as indexed to update timestamp
                    self.file_tracker.mark_indexed(file_info.path, file_content)
                    return None, file_content

                # Chunk the file into semantic units
                logger.info(
                    f"   🔪 Chunking {file_info.path} ({file_info.language})..."
                )

                # Use AST-based intelligent chunking
                chunks = self.code_chunker.chunk_file(
                    file_content, file_info.path, file_info.language
                )

                logger.info(
                    f"   ✓ Generated {len(chunks)} chunks from {file_info.path}"
                )

                # Note: Usage extraction removed - language-specific feature
                # Semantic search via embeddings handles code understanding

                return chunks, file_content

            # Process files in parallel batches (10 at a time for good performance)
            batch_size = 10
            for batch_start in range(0, total_files, batch_size):
                batch = structure.files[batch_start : batch_start + batch_size]
                batch_num = (batch_start // batch_size) + 1
                total_batches = (total_files + batch_size - 1) // batch_size

                logger.info(
                    f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} files in parallel)..."
                )

                # Process batch in parallel
                tasks = [
                    process_file(file_info, batch_start + idx + 1)
                    for idx, file_info in enumerate(batch)
                ]
                results = await asyncio.gather(*tasks)

                # Store results sequentially (to avoid race conditions with seen_hashes)
                for (chunks, file_content), file_info in zip(results, batch):
                    if chunks is None:
                        # File was skipped - already marked as indexed in process_file
                        indexed_count += 1
                        continue

                    # Store each chunk
                    logger.info(f"   💾 Storing {len(chunks)} chunks to Qdrant...")
                    for chunk_idx, chunk in enumerate(chunks, 1):
                        # Deduplicate using content hash
                        if chunk.hash in seen_hashes:
                            logger.info(
                                f"      [{chunk_idx}/{len(chunks)}] Skipping duplicate chunk: {chunk.name or 'unnamed'}"
                            )
                            continue
                        seen_hashes.add(chunk.hash)

                        chunk_name = (
                            chunk.name or f"{chunk.chunk_type}@{chunk.start_line}"
                        )
                        logger.info(
                            f"      [{chunk_idx}/{len(chunks)}] Storing chunk: {chunk_name} (lines {chunk.start_line}-{chunk.end_line})"
                        )

                        # Build metadata
                        metadata = {
                            "type": f"code_{chunk.chunk_type}",  # code_function, code_class, etc.
                            "category": "codebase",
                            "workspace": target_workspace,  # Workspace isolation
                            "file_path": chunk.file_path,
                            "language": chunk.language,
                            "chunk_type": chunk.chunk_type,
                            "start_line": chunk.start_line,
                            "end_line": chunk.end_line,
                            "content_hash": chunk.hash,
                        }

                        # Add optional fields
                        if chunk.name:
                            metadata["name"] = chunk.name
                        if chunk.parent_class:
                            metadata["parent_class"] = chunk.parent_class
                        if chunk.docstring:
                            metadata["docstring"] = chunk.docstring

                        # Create searchable content with context
                        content_parts = [f"# File: {chunk.file_path}"]
                        if chunk.name:
                            content_parts.append(
                                f"# {chunk.chunk_type.title()}: {chunk.name}"
                            )
                        if chunk.parent_class:
                            content_parts.append(f"# Class: {chunk.parent_class}")
                        if chunk.docstring:
                            content_parts.append(f'"""{chunk.docstring}"""')

                        content_parts.append("")  # Blank line
                        content_parts.append(chunk.content)

                        content = "\n".join(content_parts)

                        # Store in Qdrant
                        logger.info("         → Generating embedding and storing...")
                        entry = Entry(
                            content=content, metadata=normalize_metadata(metadata)
                        )
                        await self.qdrant_connector.store(
                            entry, collection_name=codebase_collection
                        )
                        chunk_count += 1
                        logger.info(
                            f"         ✓ Stored chunk {chunk_name} (total: {chunk_count})"
                        )

                        # Log every 50 chunks to show progress
                        if chunk_count % 50 == 0:
                            logger.info(
                                f"💾 Progress: {chunk_count} chunks stored so far..."
                            )

                if chunks:
                    logger.info(
                        f"   ✓ Completed {file_info.path}: {len(chunks)} chunks stored"
                    )

                # Note: Usage examples removed - language-specific feature
                # Semantic search via embeddings handles code understanding

                # Update relationship mapper (simplified - no structure extraction)
                self.relationship_mapper.add_file(
                    file_info.path,
                    [],  # No imports extracted
                    [],  # No exports extracted
                    [],  # No classes extracted
                    [],  # No functions extracted
                )

                # Mark file as indexed in tracker
                self.file_tracker.mark_indexed(file_info.path, file_content)

                indexed_count += 1

            # Update last index time
            self.last_index_time = time.time()

            logger.info(
                f"✅ Indexing complete: {indexed_count} files, {chunk_count} chunks, workspace={target_workspace}"
            )

            return f"Indexed {indexed_count} files ({chunk_count} code chunks) from {structure.total_files} total files. Languages: {', '.join(structure.languages.keys())}"

        async def index_file(
            ctx: Context,
            file_path: Annotated[str, Field(description="Path to the file to index")],
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to store indexed file (defaults to 'codebase' collection)"
                ),
            ] = None,
        ) -> str:
            """
            Index a single file with semantic understanding. Extracts functions, classes, imports, and purpose.
            """
            from pathlib import Path

            file_path_obj = Path(file_path).resolve()
            if not file_path_obj.exists():
                return f"Error: File {file_path} does not exist"

            await ctx.debug(f"Indexing file: {file_path}")

            # Detect language
            scanner = CodebaseScanner(str(file_path_obj.parent))
            language = scanner.detect_language(file_path_obj)
            if not language:
                return f"Error: Could not detect language for {file_path}"

            # Analyze file
            file_info = scanner.analyze_file(file_path_obj)
            if not file_info:
                return f"Error: Could not analyze file {file_path}"

            # Extract additional info
            try:
                with open(file_path_obj, "r", encoding="utf-8") as f:
                    content = f.read()
                purpose = self.code_analyzer.extract_purpose(content, language)
                api_endpoints = self.code_analyzer.extract_api_endpoints(
                    content, language
                )
                data_structures = self.code_analyzer.extract_data_structures(
                    content, language
                )
            except Exception as e:
                return f"Error reading file: {e}"

            # Create content
            file_dict = {
                "path": str(file_path_obj.relative_to(Path.cwd())),
                "language": language,
                "functions": file_info.functions,
                "classes": file_info.classes,
                "imports": file_info.imports,
                "exports": file_info.exports,
            }
            if purpose:
                file_dict["purpose"] = purpose
            if api_endpoints:
                file_dict["api_endpoints"] = api_endpoints
            if data_structures:
                file_dict["data_structures"] = data_structures

            summary = self.code_analyzer.generate_file_summary(file_dict)
            content = f"File: {file_dict['path']}\n{summary}"

            # Store
            # Use default collection for unified semantic search
            codebase_collection = (
                collection_name or self.qdrant_settings.collection_name
            )
            metadata = {
                "type": "codebase_file",
                "category": "codebase",
                "file_path": file_dict["path"],
                "language": language,
                "line_count": file_info.line_count,
                "functions": json.dumps(file_info.functions),
                "classes": json.dumps(file_info.classes),
                "imports": json.dumps(file_info.imports),
            }
            if purpose:
                metadata["purpose"] = purpose
            if api_endpoints:
                metadata["api_endpoints"] = json.dumps(api_endpoints)
            if data_structures:
                metadata["data_structures"] = json.dumps(data_structures)

            entry = Entry(content=content, metadata=normalize_metadata(metadata))
            await self.qdrant_connector.store(
                entry, collection_name=codebase_collection
            )

            return f"Indexed file: {file_dict['path']} ({language}, {len(file_info.functions)} functions, {len(file_info.classes)} classes)"

        async def get_project_summary(
            ctx: Context,
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to search (defaults to 'codebase' collection)"
                ),
            ] = None,
        ) -> str:
            """
            Get a high-level summary of the project structure, including languages, entry points, and main components.
            """
            # Use default collection for unified semantic search
            codebase_collection = (
                collection_name or self.qdrant_settings.collection_name
            )

            # Search for project structure info with workspace filter
            codebase_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value="codebase"),
                    )
                ]
            )
            codebase_filter = self._add_workspace_filter(codebase_filter)

            entries = await self.qdrant_connector.search(
                "project structure overview main entry points",
                collection_name=codebase_collection,
                limit=50,
                query_filter=codebase_filter,
            )

            if not entries:
                return "No codebase indexed yet. Use index-codebase to scan your project first."

            # Group by language
            languages = {}
            components = []
            entry_points = []

            for entry in entries:
                meta = entry.metadata or {}
                lang = meta.get("language", "unknown")
                languages[lang] = languages.get(lang, 0) + 1

                file_path = meta.get("file_path", "")
                if "main" in file_path.lower() or "index" in file_path.lower():
                    entry_points.append(file_path)

                if meta.get("classes") or meta.get("functions"):
                    components.append(
                        {
                            "path": file_path,
                            "classes": len(json.loads(meta.get("classes", "[]"))),
                            "functions": len(json.loads(meta.get("functions", "[]"))),
                        }
                    )

            summary = "Project Summary:\n"
            summary += f"- Languages: {', '.join(f'{k} ({v} files)' for k, v in languages.items())}\n"
            summary += f"- Total files indexed: {len(entries)}\n"
            if entry_points:
                summary += f"- Entry points: {', '.join(entry_points[:5])}\n"
            if components:
                summary += f"- Key components: {', '.join([c['path'] for c in components[:10]])}\n"

            return summary

        async def get_component_list(
            ctx: Context,
            component_type: Annotated[
                str,
                Field(
                    description="Type of component: 'classes', 'functions', 'files', or 'all'"
                ),
            ] = "all",
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to search (defaults to 'codebase' collection)"
                ),
            ] = None,
        ) -> list[str]:
            """
            Get a list of components in the codebase: classes, functions, or files.
            """
            # Use default collection for unified semantic search
            codebase_collection = (
                collection_name or self.qdrant_settings.collection_name
            )

            # Filter to codebase category and current workspace
            codebase_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value="codebase"),
                    )
                ]
            )
            codebase_filter = self._add_workspace_filter(codebase_filter)

            entries = await self.qdrant_connector.search(
                "codebase components classes functions",
                collection_name=codebase_collection,
                limit=100,
                query_filter=codebase_filter,
            )

            if not entries:
                return [
                    "No codebase indexed yet. Use index-codebase to scan your project first."
                ]

            results = []
            if component_type in ["classes", "all"]:
                classes = []
                for entry in entries:
                    meta = entry.metadata or {}
                    if meta.get("classes"):
                        file_classes = json.loads(meta.get("classes", "[]"))
                        for cls in file_classes:
                            classes.append(f"{meta.get('file_path')}::{cls['name']}")
                if classes:
                    results.append("Classes:")
                    results.extend(classes[:50])

            if component_type in ["functions", "all"]:
                functions = []
                for entry in entries:
                    meta = entry.metadata or {}
                    if meta.get("functions"):
                        file_funcs = json.loads(meta.get("functions", "[]"))
                        for func in file_funcs:
                            functions.append(f"{meta.get('file_path')}::{func['name']}")
                if functions:
                    results.append("\nFunctions:")
                    results.extend(functions[:50])

            if component_type in ["files", "all"]:
                files = [
                    entry.metadata.get("file_path", "unknown")
                    for entry in entries
                    if entry.metadata
                ]
                if files:
                    results.append("\nFiles:")
                    results.extend(files[:50])

            return results if results else ["No components found"]

        async def find_similar_code(
            ctx: Context,
            code_snippet: Annotated[
                str, Field(description="Code snippet to find similar code for")
            ],
            workspace_name: Annotated[
                str | None,
                Field(
                    description="Workspace/project name. MUST match the root directory name. IDE should provide this automatically. If not provided, searches current workspace or shows error."
                ),
            ] = None,
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to search (defaults to 'codebase' collection)"
                ),
            ] = None,
        ) -> list[str]:
            """
            Find code patterns similar to the provided snippet using semantic search.
            Searches only code chunks (functions, classes, methods) not decisions/patterns.
            """
            logger.info(f"🔍 Searching for similar code: {code_snippet[:50]}...")

            # Get workspace from parameter (required for stateless operation)
            if not workspace_name:
                return [
                    "Error: No workspace specified. Provide workspace_name parameter (should match root directory name)."
                ]

            target_workspace = self._normalize_workspace_name(workspace_name)
            logger.info(f"Using workspace: {target_workspace}")

            # Use default collection for unified semantic search
            codebase_collection = (
                collection_name or self.qdrant_settings.collection_name
            )

            # Filter to only code chunks in specified workspace
            code_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value="codebase"),
                    ),
                    models.FieldCondition(
                        key="metadata.workspace",
                        match=models.MatchValue(value=target_workspace),
                    ),
                ]
            )

            entries = await self.qdrant_connector.search(
                code_snippet,
                collection_name=codebase_collection,
                limit=self.qdrant_settings.search_limit,
                query_filter=code_filter,
            )

            logger.info(f"   → Found {len(entries)} similar code patterns")

            if not entries:
                # Add guidance if no results found
                guidance = None
                if self.file_tracker.get_stats()["total_files"] == 0:
                    guidance = "This workspace has 0 files indexed. Run index-codebase first to enable code search."
                elif (
                    not self.last_index_time
                    or (time.time() - self.last_index_time) > 3600
                ):
                    guidance = (
                        "Index may be stale. Consider running update-files to refresh."
                    )

                result = f"No similar code found for: {code_snippet[:50]}... (workspace: {target_workspace})"
                return [self._format_response_with_guidance(result, guidance)]

            results = [
                f"Found {len(entries)} similar code patterns in workspace '{target_workspace}':\n"
            ]
            for entry in entries:
                meta = entry.metadata or {}
                file_path = meta.get("file_path", "unknown")
                chunk_type = meta.get("chunk_type", "code")
                name = meta.get("name", "")
                start_line = meta.get("start_line", "")

                # Build result header
                header = f"\n{file_path}"
                if start_line:
                    header += f":{start_line}"
                if name:
                    header += f" - {chunk_type}: {name}"
                results.append(header)

                # Show actual code (limit to 15 lines for readability)
                code_lines = entry.content.split("\n")
                if len(code_lines) > 15:
                    results.append("\n".join(code_lines[:15]))
                    results.append(f"... ({len(code_lines) - 15} more lines)")
                else:
                    results.append(entry.content)
                results.append("")  # Blank line between results

            return results

        async def find_usage(
            ctx: Context,
            component_name: Annotated[
                str,
                Field(
                    description="Name of component (class/function) to find usage for"
                ),
            ],
            workspace_name: Annotated[
                str | None,
                Field(
                    description="Workspace/project name. MUST match the root directory name. IDE should provide this automatically. If not provided, searches current workspace or shows error."
                ),
            ] = None,
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to search (defaults to 'codebase' collection)"
                ),
            ] = None,
        ) -> list[str]:
            """
            Find where a component (class or function) is used in the codebase.
            """
            logger.info(f"🔍 Finding usage of: {component_name}")

            # Get workspace from parameter (required for stateless operation)
            if not workspace_name:
                return [
                    "Error: No workspace specified. Provide workspace_name parameter (should match root directory name)."
                ]

            target_workspace = self._normalize_workspace_name(workspace_name)
            logger.info(f"Using workspace: {target_workspace}")

            # Use default collection for unified semantic search
            codebase_collection = (
                collection_name or self.qdrant_settings.collection_name
            )

            # Query for usage examples with metadata filter (workspace-specific)
            usage_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.chunk_type",
                        match=models.MatchValue(value="usage_example"),
                    ),
                    models.FieldCondition(
                        key="metadata.target_name",
                        match=models.MatchValue(value=component_name),
                    ),
                    models.FieldCondition(
                        key="metadata.workspace",
                        match=models.MatchValue(value=target_workspace),
                    ),
                ]
            )

            # Search for usage examples
            entries = await self.qdrant_connector.search(
                f"usage of {component_name}",
                collection_name=codebase_collection,
                limit=50,
                query_filter=usage_filter,
            )

            logger.info(f"   → Found {len(entries)} usage locations")

            if not entries:
                # Add guidance if no results found
                guidance = None
                if self.file_tracker.get_stats()["total_files"] == 0:
                    guidance = "This workspace has 0 files indexed. Run index-codebase first to enable usage tracking."
                else:
                    guidance = f"'{component_name}' may not exist or may not be imported anywhere. Try: 1) Check spelling, 2) Search for the definition with find-similar-code, 3) Re-index with index-codebase."

                result = f"No usage found for {component_name} (workspace: {target_workspace})"
                return [self._format_response_with_guidance(result, guidance)]

            results = [
                f"Found {len(entries)} usage examples for '{component_name}' in workspace '{target_workspace}':\n"
            ]
            for entry in entries:
                meta = entry.metadata or {}
                file_path = meta.get("file_path", "unknown")
                line_number = meta.get("line_number", "?")
                context = meta.get("context", "unknown context")
                results.append(f"- {file_path}:{line_number} ({context})")

            # Also check relationship mapper
            usage = self.relationship_mapper.get_component_usage(component_name)
            if usage:
                results.append("\nAlso found in relationship map:")
                results.extend([f"- {u}" for u in usage[:10]])

            return results

        async def remember_decision(
            ctx: Context,
            decision: Annotated[
                str, Field(description="The architectural or design decision made")
            ],
            rationale: Annotated[
                str | None,
                Field(description="Why this decision was made"),
            ] = None,
            alternatives: Annotated[
                str | None,
                Field(description="Alternatives that were considered"),
            ] = None,
            tags: Annotated[
                str | None,
                Field(
                    description="Comma-separated tags (e.g., 'auth,security,database')"
                ),
            ] = None,
            project: Annotated[
                str | None,
                Field(description="Project name this decision applies to"),
            ] = None,
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to store in (defaults to main collection for unified search)"
                ),
            ] = None,
        ) -> str:
            """
            Store an architectural or design decision with rationale, alternatives, and tags.
            Enhanced with rich metadata for better search and cross-project learning.
            """
            # Use default collection for unified semantic search
            target_collection = collection_name or self.qdrant_settings.collection_name

            # Build rich content
            content_parts = [f"Decision: {decision}"]
            if rationale:
                content_parts.append(f"Rationale: {rationale}")
            if alternatives:
                content_parts.append(f"Alternatives Considered: {alternatives}")
            if tags:
                content_parts.append(f"Tags: {tags}")

            content = "\n".join(content_parts)

            # Build enhanced metadata
            metadata = {
                "type": "architectural_decision",
                "category": "decision",
                "decision": decision,
                "workspace": "global",  # Decisions are global by default
            }

            if rationale:
                metadata["rationale"] = rationale
            if alternatives:
                metadata["alternatives"] = alternatives
            if tags:
                # Store as both string and list for flexible querying
                metadata["tags"] = tags
                metadata["tag_list"] = [t.strip() for t in tags.split(",")]
            if project:
                metadata["project"] = project

            entry = Entry(content=content, metadata=normalize_metadata(metadata))
            await self.qdrant_connector.store(entry, collection_name=target_collection)

            result = f"Remembered decision: {decision}"
            if tags:
                result += f" (tags: {tags})"

            return result

        async def remember_pattern(
            ctx: Context,
            pattern: Annotated[
                str,
                Field(description="Coding pattern or convention used in this project"),
            ],
            example: Annotated[
                str | None,
                Field(description="Example code showing this pattern"),
            ] = None,
            use_case: Annotated[
                str | None,
                Field(description="When to use this pattern"),
            ] = None,
            tags: Annotated[
                str | None,
                Field(
                    description="Comma-separated tags (e.g., 'error-handling,async,api')"
                ),
            ] = None,
            language: Annotated[
                str | None,
                Field(
                    description="Programming language (e.g., 'python', 'javascript')"
                ),
            ] = None,
            project: Annotated[
                str | None,
                Field(description="Project name this pattern is from"),
            ] = None,
            collection_name: Annotated[
                str | None,
                Field(
                    description="Collection to store in (defaults to main collection for unified search)"
                ),
            ] = None,
        ) -> str:
            """
            Store a coding pattern or convention with rich metadata.
            Enhanced with use cases, tags, and language for better cross-project learning.
            """
            # Use default collection for unified semantic search
            target_collection = collection_name or self.qdrant_settings.collection_name

            # Build rich content
            content_parts = [f"Pattern: {pattern}"]
            if use_case:
                content_parts.append(f"Use Case: {use_case}")
            if example:
                content_parts.append(f"Example:\n{example}")
            if tags:
                content_parts.append(f"Tags: {tags}")

            content = "\n".join(content_parts)

            # Build enhanced metadata
            metadata = {
                "type": "coding_pattern",
                "category": "pattern",
                "pattern": pattern,
                "workspace": "global",  # Decisions are global by default
            }

            if example:
                metadata["example"] = example
            if use_case:
                metadata["use_case"] = use_case
            if tags:
                metadata["tags"] = tags
                metadata["tag_list"] = [t.strip() for t in tags.split(",")]
            if language:
                metadata["language"] = language
            if project:
                metadata["project"] = project

            entry = Entry(content=content, metadata=normalize_metadata(metadata))
            await self.qdrant_connector.store(entry, collection_name=target_collection)

            result = f"Remembered pattern: {pattern}"
            if tags:
                result += f" (tags: {tags})"
            if language:
                result += f" [{language}]"

            return result

        async def update_files(
            ctx: Context,
            files: Annotated[
                dict[str, str],
                Field(
                    description="Dict of file_path: file_content to incrementally update in index"
                ),
            ],
            workspace_name: Annotated[
                str | None,
                Field(
                    description="Workspace/project name. MUST match the root directory name of the workspace. Required for remote MCP servers. If not provided, uses the last indexed workspace."
                ),
            ] = None,
        ) -> str:
            """
            Incrementally update specific files in the index.
            Only re-indexes files that have changed based on content hash.
            Much faster than full codebase scan.
            """
            import time
            from pathlib import Path

            start_time = time.time()

            logger.info(f"🔄 Starting incremental update for {len(files)} files")

            # Get workspace from parameter (required for stateless operation)
            if not workspace_name:
                return "Error: No workspace specified. Provide workspace_name parameter (should match root directory name)."

            workspace_name = self._normalize_workspace_name(workspace_name)
            logger.info(f"Using workspace: {workspace_name}")

            # Detect changed files
            changed_paths = self.file_tracker.get_changed_files(files)
            logger.info(
                f"🔍 Hash check: {len(changed_paths)} files changed out of {len(files)}"
            )

            if not changed_paths:
                logger.info("✅ No changes detected, index is current")
                return "No changes detected. Index is current."

            # Limit to prevent slowdown (configurable via environment if needed)
            max_files = 50
            if len(changed_paths) > max_files:
                logger.warning(
                    f"⚠️  Truncating to {max_files} files (received {len(changed_paths)})"
                )
                changed_paths = changed_paths[:max_files]
                truncated = True
            else:
                truncated = False

            # Index changed files
            indexed_count = 0
            chunk_count = 0

            logger.info(f"📝 Processing {len(changed_paths)} changed files...")

            for file_path in changed_paths:
                logger.info(f"   → Updating {file_path}")
                content = files[file_path]

                # Analyze file in-memory (no filesystem access)
                file_info = self._analyze_file_in_memory(file_path, content)
                language = file_info.language

                if language == "text":
                    # Skip non-code files
                    continue

                # Chunk the file
                chunks = self.code_chunker.chunk_file(content, file_path, language)

                # Store chunks with workspace metadata
                for chunk in chunks:
                    metadata = {
                        "type": f"code_{chunk.chunk_type}",
                        "category": "codebase",
                        "workspace": workspace_name,  # Use provided workspace
                        "file_path": chunk.file_path,
                        "language": chunk.language,
                        "chunk_type": chunk.chunk_type,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "content_hash": chunk.hash,
                    }

                    if chunk.name:
                        metadata["name"] = chunk.name
                    if chunk.parent_class:
                        metadata["parent_class"] = chunk.parent_class
                    if chunk.docstring:
                        metadata["docstring"] = chunk.docstring

                    # Build content
                    content_parts = [f"# File: {chunk.file_path}"]
                    if chunk.name:
                        content_parts.append(
                            f"# {chunk.chunk_type.title()}: {chunk.name}"
                        )
                    if chunk.parent_class:
                        content_parts.append(f"# Class: {chunk.parent_class}")
                    if chunk.docstring:
                        content_parts.append(f'"""{chunk.docstring}"""')
                    content_parts.append("")
                    content_parts.append(chunk.content)

                    entry_content = "\n".join(content_parts)
                    entry = Entry(
                        content=entry_content, metadata=normalize_metadata(metadata)
                    )

                    await self.qdrant_connector.store(
                        entry, collection_name=self.qdrant_settings.collection_name
                    )
                    chunk_count += 1

                indexed_count += 1

            elapsed = int((time.time() - start_time) * 1000)
            self.last_index_time = time.time()

            logger.info(
                f"✅ Incremental update complete: {indexed_count} files, {chunk_count} chunks in {elapsed}ms"
            )

            result = f"Updated {indexed_count} changed files ({chunk_count} code chunks) in {elapsed}ms"
            if truncated:
                result += f"\n[Agent Guidance: {len(files) - max_files} additional changed files detected but not indexed to prevent slowdown. Run index-codebase for full re-index.]"

            return result

        async def get_index_status(
            ctx: Context,
            workspace_name: Annotated[
                str | None,
                Field(
                    description="Workspace/project name to check status for. MUST match the root directory name of the workspace. If not provided, uses the last indexed workspace."
                ),
            ] = None,
        ) -> str:
            """
            Get current indexing status and health metrics for a specific workspace.
            Shows workspace, tracked files, last update, and index health.
            """
            import datetime

            # Determine which workspace to check
            if not workspace_name:
                return "Error: workspace_name parameter is required for this tool. Provide the root directory name of your workspace."

            target_workspace = self._normalize_workspace_name(workspace_name)

            if not target_workspace:
                return "📊 Index Status\n\nWorkspace: Not set (run index-codebase first or provide workspace_name parameter)"

            # Query Qdrant to get actual stats for this workspace
            codebase_collection = self.qdrant_settings.collection_name

            # Build filter for this workspace
            workspace_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.workspace",
                        match=models.MatchValue(value=target_workspace),
                    ),
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value="codebase"),
                    ),
                ]
            )

            # Get file count by querying for unique file_paths
            # We'll do a search to get sample entries and count unique files
            entries = await self.qdrant_connector.search(
                "codebase files",
                collection_name=codebase_collection,
                limit=1000,  # Get enough to count files
                query_filter=workspace_filter,
            )

            # Count unique files
            unique_files = set()
            latest_timestamp = 0
            for entry in entries:
                meta = entry.metadata or {}
                file_path = meta.get("file_path")
                if file_path:
                    unique_files.add(file_path)
                timestamp = meta.get("timestamp", 0)
                if timestamp and timestamp > latest_timestamp:
                    latest_timestamp = timestamp

            # Build status report
            lines = ["📊 Index Status\n"]
            lines.append(f"Workspace: {target_workspace}")

            # File tracking
            lines.append(f"Files Tracked: {len(unique_files)}")

            # Last update from Qdrant data
            if latest_timestamp:
                last_update = datetime.datetime.fromtimestamp(latest_timestamp)
                time_ago = datetime.datetime.now() - last_update
                minutes_ago = int(time_ago.total_seconds() / 60)

                if minutes_ago < 1:
                    time_str = "just now"
                elif minutes_ago < 60:
                    time_str = f"{minutes_ago} minutes ago"
                else:
                    hours_ago = int(minutes_ago / 60)
                    time_str = f"{hours_ago} hours ago"

                lines.append(f"Last Update: {time_str}")
            else:
                lines.append("Last Update: Never")

            # Auto-index status
            if self.auto_index_enabled:
                lines.append("Auto-Index: ✅ Enabled")
            else:
                lines.append("Auto-Index: ❌ Disabled")

            # Health check
            if len(unique_files) == 0:
                lines.append(
                    "\n⚠️  Warning: No files indexed. Run index-codebase to get started."
                )
            elif not latest_timestamp:
                lines.append(
                    "\n⚠️  Warning: Index may be stale. Consider running index-codebase."
                )
            elif latest_timestamp and (time.time() - latest_timestamp) > 3600:
                lines.append(
                    "\n💡 Tip: Index is over 1 hour old. Use update-files to refresh changed files."
                )
            else:
                lines.append("\n✅ Index is healthy and current")

            return "\n".join(lines)

        async def list_workspaces(ctx: Context) -> str:
            """
            List all workspaces that have been indexed.
            Shows workspace names and file counts for each.
            """
            logger.info("📋 Listing all indexed workspaces...")

            # Query all codebase entries
            codebase_collection = self.qdrant_settings.collection_name
            codebase_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.category",
                        match=models.MatchValue(value="codebase"),
                    )
                ]
            )

            entries = await self.qdrant_connector.search(
                "codebase files",
                collection_name=codebase_collection,
                limit=1000,  # Get enough to analyze all workspaces
                query_filter=codebase_filter,
            )

            if not entries:
                return "No workspaces indexed yet. Use index-codebase to get started."

            # Group by workspace
            workspaces = {}
            for entry in entries:
                meta = entry.metadata or {}
                workspace = meta.get("workspace", "unknown")
                file_path = meta.get("file_path")
                timestamp = meta.get("timestamp", 0)

                if workspace not in workspaces:
                    workspaces[workspace] = {
                        "files": set(),
                        "chunks": 0,
                        "latest_timestamp": 0,
                    }

                if file_path:
                    workspaces[workspace]["files"].add(file_path)
                workspaces[workspace]["chunks"] += 1
                if timestamp > workspaces[workspace]["latest_timestamp"]:
                    workspaces[workspace]["latest_timestamp"] = timestamp

            # Build response
            lines = [f"📋 Indexed Workspaces ({len(workspaces)})\n"]

            for workspace, data in sorted(workspaces.items()):
                file_count = len(data["files"])
                chunk_count = data["chunks"]
                timestamp = data["latest_timestamp"]

                # Format timestamp
                if timestamp:
                    import datetime

                    last_update = datetime.datetime.fromtimestamp(timestamp)
                    time_ago = datetime.datetime.now() - last_update
                    minutes_ago = int(time_ago.total_seconds() / 60)

                    if minutes_ago < 1:
                        time_str = "just now"
                    elif minutes_ago < 60:
                        time_str = f"{minutes_ago}m ago"
                    else:
                        hours_ago = int(minutes_ago / 60)
                        time_str = f"{hours_ago}h ago"
                else:
                    time_str = "unknown"

                current_marker = ""  # No "current" workspace in stateless server
                lines.append(
                    f"• {workspace}{current_marker}: {file_count} files, {chunk_count} chunks (updated {time_str})"
                )

            return "\n".join(lines)

        async def clear_workspace(
            ctx: Context,
            workspace_name: Annotated[
                str,
                Field(description="Name of workspace to clear from index"),
            ],
            confirm: Annotated[
                bool,
                Field(description="Confirmation flag (must be true to proceed)"),
            ] = False,
        ) -> str:
            """
            Remove all indexed data for a specific workspace.
            This is useful for cleaning up old projects or resetting a workspace index.
            """
            if not confirm:
                return f"⚠️  Workspace deletion requires confirmation. Call again with confirm=True to proceed.\n\nThis will remove all indexed data for workspace '{workspace_name}'."

            logger.info(f"🗑️  Clearing workspace: {workspace_name}")

            return (
                f"⚠️  Clear workspace not fully implemented yet.\n\n"
                f"To reset workspace '{workspace_name}':\n"
                "1. Re-run index-codebase to overwrite with fresh data\n"
                "2. Or manually clear Qdrant collection and re-index all workspaces"
            )

        async def get_current_context(
            ctx: Context,
            workspace_name: Annotated[
                str | None,
                Field(
                    description="Workspace/project name. MUST match the root directory name. IDE should provide this. Required to get workspace-specific context."
                ),
            ] = None,
        ) -> str:
            """
            Get quick overview of workspace and index status.
            Fast status check for the AI to understand current context.
            """
            if not workspace_name:
                return "Error: No workspace specified. Provide workspace_name parameter (should match root directory name)."

            target_workspace = self._normalize_workspace_name(workspace_name)
            lines = []

            # Current workspace
            lines.append(f"🎯 Workspace: {target_workspace}")

            # Quick stats for this workspace (query Qdrant)
            try:
                result = await self.qdrant_connector._client.scroll(
                    collection_name=self.qdrant_settings.collection_name,
                    scroll_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="metadata.workspace",
                                match=models.MatchValue(value=target_workspace),
                            ),
                            models.FieldCondition(
                                key="metadata.category",
                                match=models.MatchValue(value="codebase"),
                            ),
                        ]
                    ),
                    limit=1,
                    with_payload=False,
                )
                points = result[0]  # (points, next_page_offset)
                if points:
                    count_result = await self.qdrant_connector._client.count(
                        collection_name=self.qdrant_settings.collection_name,
                        count_filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="metadata.workspace",
                                    match=models.MatchValue(value=target_workspace),
                                ),
                                models.FieldCondition(
                                    key="metadata.category",
                                    match=models.MatchValue(value="codebase"),
                                ),
                            ]
                        ),
                    )
                    lines.append(f"📁 Indexed Code Chunks: {count_result.count}")
                else:
                    lines.append("📁 Indexed Code Chunks: 0 (not indexed yet)")
            except Exception as e:
                logger.error(f"Failed to query workspace stats: {e}")
                lines.append("📁 Indexed Code Chunks: unknown (query failed)")

            lines.append(
                f"\n💡 Use get-index-status(workspace_name='{target_workspace}') for detailed status"
            )

            return "\n".join(lines)

        # Register all analysis tools
        self.tool(
            index_codebase,
            name="spot-index-codebase",
            description="Use when: starting work on a new project, user says 'analyze this codebase', or when you need to understand project structure. Indexes entire codebase for semantic search. Run this FIRST before other code tools. REQUIRES files parameter (dict of file_path: file_content) and workspace_name. MCP servers are always remote - IDE must send all file contents.",
        )

        # Use get-smart-context with "project overview" or "list classes" queries instead

        self.tool(
            find_similar_code,
            name="spot-find-code",
            description="Use when: user asks 'how do we handle X?', shows you code and asks for similar patterns, or you need examples. Finds semantically similar code automatically. Example: spot-find-code(code_snippet='async def fetch_data')",
        )

        # Note: find-python-usage removed - language-specific feature
        # Use spot-find() with workspace_name filter instead for finding code usage

        self.tool(
            list_workspaces,
            name="spot-list-workspaces",
            description="List all indexed workspaces with file counts and last update times. Use when: user asks 'what projects do you know about?', before clearing a workspace, or to verify workspace isolation.",
        )

        # Removed clear-workspace - too dangerous for IDE to call. Users can manually delete Qdrant data if needed.

        if not self.qdrant_settings.read_only:
            # Removed remember-decision and remember-pattern - use spot-store(category="decision") or spot-store(category="pattern") instead
            # This reduces tool count and eliminates redundancy

            self.tool(
                update_files,
                name="spot-update-files",
                description="Use when: user edits/saves files, you detect stale index, or need fast refresh after changes. Incrementally updates only changed files via hash comparison (< 100ms). Pass files as {path: content} dict. Much faster than full re-index.",
            )

            self.tool(
                get_index_status,
                name="spot-index-status",
                description="Use when: debugging why searches return no results, verifying index is current, or checking what's indexed. Shows workspace, tracked files, last update time, and health warnings. For remote MCP servers, provide workspace_name parameter matching the root directory name. Run this if spot-find-code or spot-find return unexpected results.",
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
            return "No codebase indexed yet. Use index-codebase to scan your project first."

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
