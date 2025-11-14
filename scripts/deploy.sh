#!/bin/bash
# Deploy marcotte-dev services to Oracle Cloud (ARM64)

set -e

ORACLE_IP="${1}"
SERVICE="${2:-all}"
ORACLE_USER="ubuntu"

if [ -z "$ORACLE_IP" ]; then
  echo "Usage: ./deploy.sh <oracle-ip> [service-name|all]"
  echo "Example: ./deploy.sh 100.x.x.x spot-mcp-server"
  echo "         ./deploy.sh 100.x.x.x all"
  exit 1
fi

# Get script directory (so we can run from anywhere)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

deploy_spot_mcp() {
  echo "🏗️  Building Spot MCP Server (ARM64)..."

  cd "$REPO_ROOT/services/spot-mcp-server"

  # Create buildx builder if doesn't exist
  if ! docker buildx ls | grep -q arm-builder; then
    docker buildx create --name arm-builder --use
    docker buildx inspect --bootstrap
  else
    docker buildx use arm-builder
  fi

  # Build for ARM64
  docker buildx build \
    --platform linux/arm64 \
    -t spot-mcp-server:arm64 \
    --load \
    .

  echo "✅ ARM64 image built"

  echo "📦 Saving image..."
  docker save spot-mcp-server:arm64 | gzip > /tmp/spot-mcp-server.tar.gz

  echo "📤 Transferring to Oracle Cloud ($ORACLE_IP)..."
  scp /tmp/spot-mcp-server.tar.gz ${ORACLE_USER}@${ORACLE_IP}:/home/ubuntu/

  echo "🚀 Deploying on Oracle Cloud..."
  ssh ${ORACLE_USER}@${ORACLE_IP} << 'ENDSSH'
  # Load image
  echo "Loading Docker image..."
  gunzip -c spot-mcp-server.tar.gz | docker load
  rm spot-mcp-server.tar.gz

  # Stop existing container if running
  if docker ps -a | grep -q spot-mcp-server; then
    echo "Stopping existing container..."
    docker stop spot-mcp-server 2>/dev/null || true
    docker rm spot-mcp-server 2>/dev/null || true
  fi

  # Create data directory
  mkdir -p ~/qdrant-data
  chmod 755 ~/qdrant-data

  # Run container
  echo "Starting container..."
  docker run -d \
    --name spot-mcp-server \
    --restart unless-stopped \
    -p 3856:3855 \
    -v ~/qdrant-data:/app/qdrant-data \
    -e QDRANT_LOCAL_PATH=/app/qdrant-data \
    -e COLLECTION_NAME=default-collection \
    -e EMBEDDING_MODEL=BAAI/bge-large-en-v1.5 \
    -e RERANKER_ENABLED=true \
    -e FASTMCP_HOST=0.0.0.0 \
    -e FASTMCP_PORT=3855 \
    spot-mcp-server:arm64

  # Wait for container to start
  sleep 5

  # Check if running
  if docker ps | grep -q spot-mcp-server; then
    echo "✅ Container started successfully"
    docker logs --tail 20 spot-mcp-server
  else
    echo "❌ Container failed to start"
    docker logs spot-mcp-server
    exit 1
  fi

  # Test Memory Janitor
  echo ""
  echo "🧹 Testing Memory Janitor..."
  docker exec spot-mcp-server python -m memory_janitor

  echo ""
  echo "📊 Memory Janitor test complete! Check logs above for results."
ENDSSH

  # Clean up local tar
  rm /tmp/spot-mcp-server.tar.gz

  echo ""
  echo "🎉 Spot MCP Server deployed!"
  echo "   Test: curl http://${ORACLE_IP}:3856/mcp"
}

# Main deployment logic
case "$SERVICE" in
  "spot-mcp-server")
    deploy_spot_mcp
    ;;
  "all")
    echo "Deploying all services..."
    deploy_spot_mcp
    # Add more services here as needed
    ;;
  *)
    echo "Unknown service: $SERVICE"
    echo "Available services: spot-mcp-server, all"
    exit 1
    ;;
esac

echo ""
echo "✅ Deployment complete!"
