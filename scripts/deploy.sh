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
  scp "$REPO_ROOT/services/spot-mcp-server/docker-compose.yml" ${ORACLE_USER}@${ORACLE_IP}:/home/ubuntu/
  scp "$REPO_ROOT/services/spot-mcp-server/migrate-to-server.py" ${ORACLE_USER}@${ORACLE_IP}:/home/ubuntu/

  echo "🚀 Deploying on Oracle Cloud..."
  ssh ${ORACLE_USER}@${ORACLE_IP} << 'ENDSSH'
  # Load image
  echo "Loading Docker image..."
  gunzip -c spot-mcp-server.tar.gz | docker load
  rm spot-mcp-server.tar.gz

  # Check if we need to migrate from local storage
  if [ -d ~/qdrant-data ] && [ "$(ls -A ~/qdrant-data)" ]; then
    echo "📦 Found existing local Qdrant data, will migrate..."
    NEEDS_MIGRATION=true
  else
    NEEDS_MIGRATION=false
  fi

  # Stop existing services
  echo "Stopping existing services..."
  docker-compose down 2>/dev/null || true

  # Start Qdrant server first
  echo "Starting Qdrant server..."
  docker-compose up -d qdrant

  # Wait for Qdrant to be healthy
  echo "Waiting for Qdrant to be ready..."
  for i in {1..30}; do
    if docker exec qdrant curl -f http://localhost:6333/health > /dev/null 2>&1; then
      echo "✅ Qdrant is ready"
      break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
  done

  # Migrate data if needed
  if [ "$NEEDS_MIGRATION" = true ]; then
    echo "🔄 Migrating data from local storage to Qdrant server..."
    docker run --rm \
      --network="host" \
      -v ~/qdrant-data:/app/qdrant-data \
      -e QDRANT_LOCAL_PATH=/app/qdrant-data \
      -e QDRANT_URL=http://localhost:6333 \
      -e COLLECTION_NAME=default-collection \
      spot-mcp-server:arm64 \
      python /app/migrate-to-server.py

    echo "✅ Migration complete"
    echo "💾 Backing up old local storage..."
    mv ~/qdrant-data ~/qdrant-data.backup.$(date +%Y%m%d_%H%M%S)
  fi

  # Start Spot MCP Server
  echo "Starting Spot MCP Server..."
  docker-compose up -d spot-mcp-server

  # Wait for container to start
  sleep 5

  # Check if running
  if docker ps | grep -q spot-mcp-server; then
    echo "✅ Containers started successfully"
    docker-compose ps
    echo ""
    docker logs --tail 30 spot-mcp-server
    echo ""
    echo "🧹 Memory Janitor systemd service will be set up separately"
  else
    echo "❌ Container failed to start"
    docker logs spot-mcp-server
    exit 1
  fi
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
