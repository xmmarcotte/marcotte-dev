#!/usr/bin/env python3
"""
Migrate data from local Qdrant storage to Qdrant server.
Run this script after starting Qdrant server but before starting Spot MCP Server.
"""

import asyncio
import logging
import os
from pathlib import Path

from qdrant_client import AsyncQdrantClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    """Migrate data from local storage to Qdrant server"""
    local_path = os.getenv("QDRANT_LOCAL_PATH", "./qdrant-data")
    server_url = os.getenv("QDRANT_URL", "http://localhost:6333")

    logger.info(f"🔄 Starting migration from {local_path} to {server_url}")

    # Check if local storage exists
    if not Path(local_path).exists():
        logger.warning(
            f"⚠️  Local storage not found at {local_path}, nothing to migrate"
        )
        return

    # Connect to local storage
    logger.info("📂 Connecting to local storage...")
    local_client = AsyncQdrantClient(path=local_path)

    # Connect to server
    logger.info("🌐 Connecting to Qdrant server...")
    server_client = AsyncQdrantClient(url=server_url)

    try:
        # Get all collections from local storage
        collections = await local_client.get_collections()
        logger.info(f"Found {len(collections.collections)} collections to migrate")

        for collection in collections.collections:
            coll_name = collection.name
            logger.info(f"📦 Migrating collection: {coll_name}")

            # Get collection info
            coll_info = await local_client.get_collection(coll_name)

            # Create collection on server with same config
            try:
                await server_client.create_collection(
                    collection_name=coll_name,
                    vectors_config=coll_info.config.params.vectors,
                )
                logger.info(f"✅ Created collection {coll_name} on server")
            except Exception:
                logger.info(
                    f"Collection {coll_name} already exists on server, continuing..."
                )

            # Scroll through all points and migrate
            offset = None
            total_migrated = 0
            batch_size = 100

            while True:
                # Get batch of points
                points, offset = await local_client.scroll(
                    collection_name=coll_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )

                if not points:
                    break

                # Upload to server
                await server_client.upsert(
                    collection_name=coll_name,
                    points=points,
                )

                total_migrated += len(points)
                logger.info(f"  Migrated {total_migrated} points...")

                if offset is None:
                    break

            logger.info(f"✅ Migrated {total_migrated} points from {coll_name}")

        logger.info("🎉 Migration complete!")
        logger.info(f"💡 You can now delete the local storage: rm -rf {local_path}")

    finally:
        await local_client.close()
        await server_client.close()


if __name__ == "__main__":
    asyncio.run(migrate())
