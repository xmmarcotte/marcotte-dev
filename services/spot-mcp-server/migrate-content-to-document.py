#!/usr/bin/env python3
"""
One-time migration script to fix payload keys from 'content' to 'document'
This fixes memories that were stored by the janitor with the wrong key.
"""

import asyncio
import logging
import os

from qdrant_client import AsyncQdrantClient, models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Migrate all 'content' keys to 'document' keys in Qdrant"""
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_name = os.getenv("COLLECTION_NAME", "default-collection")

    logger.info(f"🔄 Starting migration for collection: {collection_name}")
    logger.info(f"   Qdrant URL: {qdrant_url}")

    # Initialize Qdrant client
    client = AsyncQdrantClient(url=qdrant_url)

    # Check if collection exists
    try:
        await client.get_collection(collection_name)
    except Exception as e:
        logger.error(f"Collection {collection_name} doesn't exist: {e}")
        return

    # Scroll through all points
    offset = None
    batch_size = 100
    total_migrated = 0
    total_checked = 0

    while True:
        points, next_offset = await client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        if not points:
            break

        # Check each point
        points_to_update = []
        for point in points:
            total_checked += 1

            # Check if it has 'content' but not 'document'
            if "content" in point.payload and "document" not in point.payload:
                logger.info(f"   Migrating point {point.id}: content -> document")

                # Create updated payload
                new_payload = dict(point.payload)
                new_payload["document"] = new_payload.pop("content")

                # Prepare for upsert
                points_to_update.append(
                    models.PointStruct(
                        id=point.id,
                        vector=point.vector,
                        payload=new_payload,
                    )
                )

        # Batch update all points that need migration
        if points_to_update:
            await client.upsert(
                collection_name=collection_name,
                points=points_to_update,
                wait=True,
            )
            total_migrated += len(points_to_update)
            logger.info(f"   ✅ Migrated {len(points_to_update)} points in this batch")

        offset = next_offset
        if next_offset is None:
            break

    logger.info("🎉 Migration complete!")
    logger.info(f"   Total points checked: {total_checked}")
    logger.info(f"   Total points migrated: {total_migrated}")
    logger.info(f"   Points already correct: {total_checked - total_migrated}")


if __name__ == "__main__":
    asyncio.run(migrate())
