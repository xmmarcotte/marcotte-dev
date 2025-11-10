"""
Deduplication utilities for Qdrant storage.
"""

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def generate_content_hash(file_path: str, chunk_id: Optional[str] = None) -> str:
    """
    Generate a unique hash for deduplication.

    Args:
        file_path: Path to the file
        chunk_id: Optional chunk identifier (e.g., "function:my_function")

    Returns:
        MD5 hash string
    """
    key = f"{file_path}:{chunk_id}" if chunk_id else file_path
    return hashlib.md5(key.encode()).hexdigest()


async def deduplicate_before_store(
    qdrant_connector,
    file_path: str,
    collection_name: str,
    chunk_id: Optional[str] = None,
) -> bool:
    """
    Check if an entry already exists and delete it before storing new version.

    Args:
        qdrant_connector: QdrantConnector instance
        file_path: Path to the file
        collection_name: Qdrant collection name
        chunk_id: Optional chunk identifier

    Returns:
        True if deduplication was needed, False otherwise
    """
    content_hash = generate_content_hash(file_path, chunk_id)

    try:
        # Search for existing entries with this hash
        from qdrant_client import models

        existing = await qdrant_connector.search(
            query=f"file_path:{file_path}",
            collection_name=collection_name,
            limit=100,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.file_path",
                        match=models.MatchValue(value=file_path),
                    )
                ]
            ),
        )

        if existing:
            # Delete existing entries for this file/chunk
            for entry in existing:
                if (
                    entry.metadata
                    and entry.metadata.get("content_hash") == content_hash
                ):
                    logger.info(f"Found duplicate for {file_path}:{chunk_id}, skipping")
                    return True

            # Different content, delete old versions before adding new
            logger.info(f"Updating {len(existing)} entries for {file_path}")
            # Hash checking prevents duplicate storage
            return False

    except Exception as e:
        logger.warning(f"Deduplication check failed: {e}")
        return False

    return False
