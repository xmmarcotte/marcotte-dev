#!/bin/bash
set -e

echo "🚀 Starting Spot Memory Server..."
echo "   📊 BAAI/bge-large-en-v1.5 embeddings"
echo "   🎯 Local reranking enabled"
echo "   🔍 Enhanced metadata extraction"

# Run the MCP server
exec mcp-server-qdrant --transport streamable-http
