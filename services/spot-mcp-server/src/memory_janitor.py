#!/usr/bin/env python3
"""
Memory Janitor - Self-maintaining memory system for Spot MCP Server

Runs as a background service to:
- Deduplicate similar memories
- Resolve conflicting memories (FIFO - newest wins)
- Archive stale/unused memories
- Update health scores
- Generate maintenance reports
"""

import asyncio
import datetime
import logging
from collections import defaultdict
from typing import Any, Dict, List

from mcp_server_qdrant.embeddings.factory import create_embedding_provider
from mcp_server_qdrant.qdrant import Entry, QdrantConnector
from mcp_server_qdrant.settings import EmbeddingProviderSettings, QdrantSettings
from qdrant_client import models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class MemoryJanitor:
    """Autonomous memory maintenance service"""

    def __init__(
        self,
        qdrant_connector: QdrantConnector,
        similarity_threshold: float = 0.90,
        stale_threshold_days: int = 365,
        min_access_count: int = 1,
    ):
        self.qdrant = qdrant_connector
        self.similarity_threshold = similarity_threshold
        self.stale_threshold_days = stale_threshold_days
        self.min_access_count = min_access_count

        # Stats for reporting
        self.stats = {
            "duplicates_merged": 0,
            "conflicts_resolved": 0,
            "stale_archived": 0,
            "health_updated": 0,
            "workspace_fixed": 0,
        }

    async def run_maintenance(self) -> Dict[str, Any]:
        """Run all maintenance tasks and return report"""
        logger.info("🧹 Starting memory maintenance cycle...")

        try:
            # Phase 0: Workspace cleanup (run first, fixes metadata)
            logger.info("Phase 0: Workspace cleanup")
            await self.fix_workspace_metadata()

            # Phase 0.5: Category cleanup and invalid memory deletion
            logger.info("Phase 0.5: Category cleanup")
            await self.fix_category_metadata()

            # Phase 1: Deduplication
            logger.info("Phase 1: Deduplication")
            await self.deduplicate_memories()

            # Phase 2: Conflict resolution
            logger.info("Phase 2: Conflict resolution")
            await self.resolve_conflicts()

            # Phase 3: Stale memory archiving
            logger.info("Phase 3: Stale memory archiving")
            await self.archive_stale_memories()

            # Phase 4: Health scoring
            logger.info("Phase 4: Health scoring")
            await self.update_health_scores()

            # Generate report
            report = self.generate_report()
            logger.info(f"✅ Maintenance complete: {report}")

            return report

        except Exception as e:
            logger.error(f"❌ Maintenance failed: {e}")
            raise

    async def fix_workspace_metadata(self):
        """Fix workspace metadata: migrate 'project' to 'workspace_name' and normalize"""
        logger.info("🔧 Fixing workspace metadata...")

        all_memories = await self._get_all_memories()

        for memory in all_memories:
            meta = memory.metadata or {}
            needs_update = False
            updated_meta = dict(meta)

            # Case 1: Has 'project' but not 'workspace_name' - migrate it
            if "project" in meta and "workspace_name" not in meta:
                workspace = self._normalize_workspace_name(meta["project"])
                updated_meta["workspace_name"] = workspace
                needs_update = True
                logger.info(
                    f"Migrating project '{meta['project']}' -> workspace_name '{workspace}'"
                )

            # Case 2: Has 'workspace_name' but not normalized - normalize it
            elif "workspace_name" in meta:
                original = meta["workspace_name"]
                normalized = self._normalize_workspace_name(original)
                if original != normalized:
                    updated_meta["workspace_name"] = normalized
                    needs_update = True
                    logger.info(
                        f"Normalizing workspace_name '{original}' -> '{normalized}'"
                    )

            # Case 3: Try to infer workspace from content/tags for important memories
            elif "workspace_name" not in meta and meta.get("category") in [
                "decision",
                "pattern",
            ]:
                # Try to infer from tags or content
                inferred = self._infer_workspace(memory.content, meta)
                if inferred:
                    updated_meta["workspace_name"] = inferred
                    needs_update = True
                    logger.info(f"Inferred workspace_name '{inferred}' from content")

            # Update if needed
            if needs_update:
                await self._update_memory_metadata(memory.id, updated_meta)
                self.stats["workspace_fixed"] += 1

        logger.info(
            f"✅ Fixed {self.stats['workspace_fixed']} workspace metadata entries"
        )

    async def fix_category_metadata(self):
        """Fix category metadata and clean up invalid memories"""
        logger.info("🔧 Fixing category metadata and cleaning invalid memories...")

        all_memories = await self._get_all_memories()

        for memory in all_memories:
            meta = memory.metadata or {}
            category = meta.get("category", "memory")

            # Check 1: Delete memories with empty or whitespace-only content
            if not memory.content or memory.content.strip() == "":
                logger.info(f"Deleting empty memory (id: {memory.id[:8]}...)")
                await self._delete_memory(memory.id, "empty content")
                self.stats["empty_deleted"] = self.stats.get("empty_deleted", 0) + 1
                continue

            # Check 2: Delete memories with suspiciously short content (< 10 chars)
            if len(memory.content.strip()) < 10:
                logger.info(
                    f"Deleting suspiciously short memory (id: {memory.id[:8]}..., "
                    f"content: '{memory.content[:50]}')"
                )
                await self._delete_memory(memory.id, "suspiciously short content")
                self.stats["short_deleted"] = self.stats.get("short_deleted", 0) + 1
                continue

            # Check 3: Validate category values
            valid_categories = [
                "decision",
                "pattern",
                "memory",
                "architecture",
                "error",
                "lesson",
                "codebase",
                "other",
            ]
            if category not in valid_categories:
                logger.info(
                    f"Recategorizing invalid category '{category}' -> 'memory' "
                    f"(id: {memory.id[:8]}...)"
                )
                updated_meta = dict(meta)
                updated_meta["category"] = "memory"
                await self._update_memory_metadata(memory.id, updated_meta)
                self.stats["category_fixed"] = self.stats.get("category_fixed", 0) + 1

        logger.info(
            f"✅ Category cleanup complete: "
            f"{self.stats.get('category_fixed', 0)} fixed, "
            f"{self.stats.get('empty_deleted', 0)} empty deleted, "
            f"{self.stats.get('short_deleted', 0)} short deleted"
        )

    def _normalize_workspace_name(self, name: str) -> str:
        """Normalize workspace name to be consistent"""
        import re

        normalized = name.lower()
        normalized = re.sub(r"[^\w\-]", "-", normalized)  # Replace non-alphanumeric
        normalized = re.sub(r"-+", "-", normalized)  # Collapse multiple hyphens
        normalized = normalized.strip("-")  # Remove leading/trailing hyphens
        return normalized

    def _infer_workspace(self, content: str, metadata: dict) -> str | None:
        """Try to infer workspace from content and metadata"""
        # Common project names to look for
        known_projects = [
            "eboot-app-code",
            "eboot-webapp-backend",
            "eboot-webapp-frontend",
            "eboot-mortician",
            "meta-granitenet",
            "marcotte-dev",
            "spot-mcp-server",
        ]

        content_lower = content.lower()

        # Check tags first
        tags = metadata.get("tags", "")
        if isinstance(tags, str):
            for project in known_projects:
                if project in tags.lower():
                    return project

        # Check content
        for project in known_projects:
            if project in content_lower:
                return project

        return None

    def _extract_vector(self, vector_data):
        """Extract vector array from Qdrant vector data (handles named vectors)"""
        if isinstance(vector_data, dict):
            # Qdrant returns named vectors as {"vector_name": [values]}
            # Get the first (and likely only) vector
            return list(vector_data.values())[0] if vector_data else None
        return vector_data

    def _wrap_vector(self, vector_array):
        """Wrap vector array in named vector dict for Qdrant upsert"""
        if vector_array is None:
            return None
        # Use the FastEmbed vector name format: fast-{model_name}
        # For BAAI/bge-large-en-v1.5, this is "fast-bge-large-en-v1.5"
        vector_name = "fast-bge-large-en-v1.5"
        return {vector_name: vector_array}

    async def _update_memory_metadata(self, memory_id: str, metadata: dict):
        """Update memory metadata in Qdrant"""
        try:
            # Get the memory point to preserve its vector
            points = await self.qdrant._client.retrieve(
                collection_name=self.qdrant.collection_name,
                ids=[memory_id],
                with_vectors=True,
                with_payload=True,
            )

            if not points:
                logger.warning(f"Memory {memory_id} not found for metadata update")
                return

            point = points[0]

            # Extract vector (handle named vectors)
            vector = self._extract_vector(point.vector)

            # Update with new metadata
            await self.qdrant._client.upsert(
                collection_name=self.qdrant.collection_name,
                points=[
                    models.PointStruct(
                        id=memory_id,
                        vector=self._wrap_vector(vector),
                        payload={
                            "document": point.payload.get("document", ""),
                            "metadata": metadata,
                        },
                    )
                ],
            )
        except Exception as e:
            logger.error(f"Failed to update metadata for {memory_id}: {e}")

    async def deduplicate_memories(self):
        """Find and merge near-duplicate memories using semantic similarity"""
        logger.info("🔍 Scanning for duplicate memories...")

        # Get all memories
        all_memories = await self._get_all_memories()

        # Group by category and workspace for efficient comparison
        grouped = defaultdict(list)
        for memory in all_memories:
            meta = memory.metadata or {}
            key = (meta.get("category", "memory"), meta.get("workspace_name", ""))
            grouped[key].append(memory)

        # Check for duplicates within each group
        for group_key, memories in grouped.items():
            if len(memories) < 2:
                continue

            logger.info(f"Checking {len(memories)} memories in group {group_key}")

            # Compare each pair for similarity
            for i, mem1 in enumerate(memories):
                for mem2 in memories[i + 1 :]:
                    similarity = await self._calculate_similarity(mem1, mem2)

                    if similarity >= self.similarity_threshold:
                        logger.info(
                            f"Found duplicate (similarity={similarity:.2f}): "
                            f"{mem1.content[:50]}... vs {mem2.content[:50]}..."
                        )
                        await self._merge_memories(mem1, mem2)
                        self.stats["duplicates_merged"] += 1

    async def resolve_conflicts(self):
        """Resolve conflicting memories using FIFO (newest wins)"""
        logger.info("⚔️  Resolving conflicting memories...")

        # Get all memories
        all_memories = await self._get_all_memories()

        # Group by semantic topic (using embeddings)
        topic_groups = await self._group_by_topic(all_memories)

        for topic, memories in topic_groups.items():
            if len(memories) < 2:
                continue

            # Check for conflicts (contradictory information)
            conflicts = await self._detect_conflicts(memories)

            for conflict_group in conflicts:
                # Sort by timestamp (newest first)
                sorted_memories = sorted(
                    conflict_group,
                    key=lambda m: (m.metadata or {}).get("timestamp", 0),
                    reverse=True,
                )

                # Keep newest, archive older conflicting memories
                to_archive = sorted_memories[1:]

                logger.info(
                    f"Conflict detected: Keeping newest memory, archiving {len(to_archive)} older versions"
                )

                for old_memory in to_archive:
                    await self._delete_memory(
                        old_memory.id, reason="superseded_by_newer"
                    )
                    self.stats["conflicts_resolved"] += 1

    async def archive_stale_memories(self):
        """Delete memories that haven't been accessed in a long time (1 year)"""
        logger.info("🗑️  Deleting stale memories...")

        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
            days=self.stale_threshold_days
        )
        cutoff_timestamp = cutoff_date.timestamp()

        # Get all memories
        all_memories = await self._get_all_memories()

        for memory in all_memories:
            meta = memory.metadata or {}
            last_accessed = meta.get("last_accessed", meta.get("timestamp", 0))
            access_count = meta.get("access_count", 0)

            # Convert timestamp to float if it's a string
            try:
                last_accessed = float(last_accessed) if last_accessed else 0
            except (ValueError, TypeError):
                last_accessed = 0

            # Delete if old and rarely accessed
            if (
                last_accessed < cutoff_timestamp
                and access_count < self.min_access_count
            ):
                logger.info(
                    f"Deleting stale memory: {memory.content[:50]}... "
                    f"(last accessed: {datetime.datetime.fromtimestamp(last_accessed)})"
                )
                await self._delete_memory(memory.id, reason="stale")
                self.stats["stale_archived"] += 1

    async def update_health_scores(self):
        """Update health scores for all memories based on usage and freshness"""
        logger.info("💚 Updating health scores...")

        all_memories = await self._get_all_memories()

        for memory in all_memories:
            # Calculate health score (0-100)
            health = await self._calculate_health_score(memory)

            # Update metadata with health score
            if hasattr(memory, "id") and memory.metadata:
                memory.metadata["health_score"] = health
                memory.metadata["health_updated_at"] = datetime.datetime.now(
                    datetime.timezone.utc
                ).timestamp()

                # Update in Qdrant
                if hasattr(memory, "vector"):
                    await self.qdrant._client.upsert(
                        collection_name=self.qdrant.collection_name,
                        points=[
                            models.PointStruct(
                                id=memory.id,
                                vector=self._wrap_vector(memory.vector),
                                payload={
                                    "document": memory.content,
                                    "metadata": memory.metadata,
                                },
                            )
                        ],
                    )

                self.stats["health_updated"] += 1

        logger.info(f"Updated health scores for {len(all_memories)} memories")

    async def _get_all_memories(self) -> List[Entry]:
        """Retrieve all memories from Qdrant with pagination"""
        # Check if collection exists first
        try:
            await self.qdrant._client.get_collection(self.qdrant.collection_name)
        except Exception as e:
            logger.warning(
                f"Collection {self.qdrant.collection_name} doesn't exist yet: {e}"
            )
            return []

        all_memories = []
        offset = 0
        batch_size = 1000

        while True:
            # Use scroll API for efficient pagination
            batch = await self.qdrant._client.scroll(
                collection_name=self.qdrant.collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            if not batch[0]:  # No more results
                break

            # Convert to Entry objects
            for point in batch[0]:
                entry = Entry(
                    content=point.payload.get("document", ""),
                    metadata=point.payload.get("metadata", {}),
                )
                entry.id = point.id
                # Extract vector (handle named vectors)
                entry.vector = self._extract_vector(point.vector)
                all_memories.append(entry)

            offset += len(batch[0])
            logger.info(f"Loaded {offset} memories...")

            if len(batch[0]) < batch_size:
                break

        logger.info(f"Total memories loaded: {len(all_memories)}")
        return all_memories

    async def _calculate_similarity(self, mem1: Entry, mem2: Entry) -> float:
        """Calculate semantic similarity between two memories using cosine similarity"""
        import numpy as np

        # Get vectors (should be stored in Entry objects)
        vec1 = mem1.vector if hasattr(mem1, "vector") else None
        vec2 = mem2.vector if hasattr(mem2, "vector") else None

        if vec1 is None or vec2 is None:
            logger.warning("Missing vectors for similarity calculation")
            return 0.0

        # Convert to numpy arrays
        v1 = np.array(vec1)
        v2 = np.array(vec2)

        # Cosine similarity: dot(v1, v2) / (norm(v1) * norm(v2))
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)
        return float(similarity)

    async def _merge_memories(self, mem1: Entry, mem2: Entry):
        """Merge two similar memories, keeping the more recent one"""
        # Determine which is newer
        ts1 = mem1.metadata.get("timestamp", 0) if mem1.metadata else 0
        ts2 = mem2.metadata.get("timestamp", 0) if mem2.metadata else 0

        keeper = mem1 if ts1 >= ts2 else mem2
        to_remove = mem2 if ts1 >= ts2 else mem1

        logger.info(
            f"Merging: Keeping '{keeper.content[:50]}...' (ts={ts1 if ts1 >= ts2 else ts2}), "
            f"removing '{to_remove.content[:50]}...' (ts={ts2 if ts1 >= ts2 else ts1})"
        )

        # Update keeper's metadata to note it absorbed a duplicate
        if keeper.metadata:
            keeper.metadata["merged_count"] = keeper.metadata.get("merged_count", 0) + 1
            keeper.metadata["last_merge"] = datetime.datetime.now(
                datetime.timezone.utc
            ).timestamp()

        # Delete the older one
        await self._delete_memory(to_remove.id, reason="duplicate")

    async def _group_by_topic(self, memories: List[Entry]) -> Dict[str, List[Entry]]:
        """Group memories by semantic topic using simple clustering"""
        if not memories:
            return {}

        # Simple approach: group by category + workspace first
        # Then within each group, cluster by similarity
        groups = defaultdict(list)

        for memory in memories:
            meta = memory.metadata or {}
            # Create a topic key based on category and workspace
            topic_key = f"{meta.get('category', 'memory')}:{meta.get('workspace_name', 'global')}"
            groups[topic_key].append(memory)

        return dict(groups)

    async def _detect_conflicts(self, memories: List[Entry]) -> List[List[Entry]]:
        """Detect conflicting information within a group of memories"""
        if len(memories) < 2:
            return []

        conflicts = []

        # Strategy: Find memories with high similarity (same topic)
        # but different timestamps (potential updates/conflicts)
        for i, mem1 in enumerate(memories):
            conflict_group = [mem1]

            for mem2 in memories[i + 1 :]:
                # Check if they're about the same thing (high similarity)
                similarity = await self._calculate_similarity(mem1, mem2)

                if similarity >= 0.75:  # Same topic threshold
                    # Check if timestamps are different (potential conflict)
                    ts1 = mem1.metadata.get("timestamp", 0) if mem1.metadata else 0
                    ts2 = mem2.metadata.get("timestamp", 0) if mem2.metadata else 0

                    # Convert timestamps to float if they're strings
                    try:
                        ts1 = float(ts1) if ts1 else 0
                        ts2 = float(ts2) if ts2 else 0
                    except (ValueError, TypeError):
                        ts1 = 0
                        ts2 = 0

                    # If timestamps differ by more than 1 day, might be an update
                    if abs(ts1 - ts2) > 86400:  # 1 day in seconds
                        conflict_group.append(mem2)

            if len(conflict_group) > 1:
                conflicts.append(conflict_group)

        return conflicts

    async def _delete_memory(self, memory_id: str, reason: str = ""):
        """Delete memory from collection by ID"""
        logger.info(f"Deleting memory {memory_id[:8]}... (reason: {reason})")

        await self.qdrant._client.delete(
            collection_name=self.qdrant.collection_name,
            points_selector=models.PointIdsList(points=[memory_id]),
        )
        logger.info(f"Deleted memory {memory_id[:8]}...")

    async def _calculate_health_score(self, memory: Entry) -> float:
        """Calculate health score (0-100) based on various factors"""
        meta = memory.metadata or {}

        # Factors:
        # - Freshness (newer = better)
        # - Access count (more = better)
        # - Last accessed (recent = better)
        # - Content quality (length, structure)

        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        created = meta.get("timestamp", now)
        last_accessed = meta.get("last_accessed", created)
        access_count = meta.get("access_count", 0)

        # Age factor (0-100, newer = higher)
        age_days = (now - created) / 86400
        age_score = max(0, 100 - (age_days / 365 * 50))  # Decay over 2 years

        # Recency factor (0-100, recent access = higher)
        recency_days = (now - last_accessed) / 86400
        recency_score = max(0, 100 - (recency_days / 180 * 100))  # Decay over 6 months

        # Usage factor (0-100, more access = higher)
        usage_score = min(100, access_count * 10)  # Cap at 100

        # Weighted average
        health = (age_score * 0.3) + (recency_score * 0.4) + (usage_score * 0.3)

        return health

    def generate_report(self) -> Dict[str, Any]:
        """Generate maintenance report"""
        return {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "workspace_fixed": self.stats["workspace_fixed"],
            "category_fixed": self.stats.get("category_fixed", 0),
            "empty_deleted": self.stats.get("empty_deleted", 0),
            "short_deleted": self.stats.get("short_deleted", 0),
            "duplicates_merged": self.stats["duplicates_merged"],
            "conflicts_resolved": self.stats["conflicts_resolved"],
            "stale_archived": self.stats["stale_archived"],
            "health_updated": self.stats["health_updated"],
            "total_actions": sum(self.stats.values()),
        }


async def main():
    """Main entry point for running as a standalone service"""
    logger.info("🚀 Memory Janitor starting...")

    # Initialize settings
    qdrant_settings = QdrantSettings()
    embedding_settings = EmbeddingProviderSettings()

    # Create embedding provider
    embedding_provider = create_embedding_provider(embedding_settings)

    # Initialize Qdrant connection (using server mode, not local path)
    qdrant = QdrantConnector(
        qdrant_settings.location,  # Should be http://qdrant:6333 or http://localhost:6333
        qdrant_settings.api_key,
        qdrant_settings.collection_name,
        embedding_provider,
        None,  # No local path - using server mode
        {},  # No custom indexes needed
        reranker=None,
    )

    # Create janitor
    janitor = MemoryJanitor(qdrant)

    # Run maintenance
    report = await janitor.run_maintenance()

    logger.info(f"📊 Maintenance Report: {report}")
    logger.info("✅ Memory Janitor complete")


if __name__ == "__main__":
    asyncio.run(main())
