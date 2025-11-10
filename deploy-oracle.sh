#!/bin/bash
# Deploy Spot Memory Server to Oracle Cloud (ARM64)

set -e

ORACLE_IP="${1}"
ORACLE_USER="ubuntu"

if [ -z "$ORACLE_IP" ]; then
  echo "Usage: ./deploy-oracle.sh <oracle-public-ip>"
  exit 1
fi

echo "🏗️  Building ARM64 Docker image..."

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
  -t spot-memory-server:arm64 \
  --load \
  .

echo "✅ ARM64 image built successfully"

echo "📦 Saving image to file..."
docker save spot-memory-server:arm64 | gzip > spot-arm64.tar.gz

echo "📤 Transferring to Oracle Cloud ($ORACLE_IP)..."
scp spot-arm64.tar.gz ${ORACLE_USER}@${ORACLE_IP}:/home/ubuntu/

echo "🚀 Deploying on Oracle Cloud..."
ssh ${ORACLE_USER}@${ORACLE_IP} << 'ENDSSH'
# Load image
echo "Loading Docker image..."
gunzip -c spot-arm64.tar.gz | docker load
rm spot-arm64.tar.gz

# Stop existing container if running
if docker ps -a | grep -q spot-memory-server; then
  echo "Stopping existing container..."
  docker stop spot-memory-server 2>/dev/null || true
  docker rm spot-memory-server 2>/dev/null || true
fi

# Create data directory
mkdir -p ~/qdrant-data
chmod 755 ~/qdrant-data

# Run container
echo "Starting container..."
docker run -d \
  --name spot-memory-server \
  --restart unless-stopped \
  -p 3856:3855 \
  -v ~/qdrant-data:/app/qdrant-data \
  -e QDRANT_LOCAL_PATH=/app/qdrant-data \
  -e EMBEDDING_MODEL=BAAI/bge-large-en-v1.5 \
  -e RERANKER_ENABLED=true \
  -e FASTMCP_HOST=0.0.0.0 \
  -e FASTMCP_PORT=3855 \
  spot-memory-server:arm64

# Wait for container to start
sleep 5

# Check if running
if docker ps | grep -q spot-memory-server; then
  echo "✅ Container started successfully"
  docker logs --tail 20 spot-memory-server
else
  echo "❌ Container failed to start"
  docker logs spot-memory-server
  exit 1
fi
ENDSSH

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "1. Test: curl http://${ORACLE_IP}:3856/mcp"
echo "2. Update mcp.json on all machines with:"
echo "   \"url\": \"http://${ORACLE_IP}:3856/mcp\""
echo ""
echo "💾 Set up backups (see ORACLE_CLOUD_DEPLOY.md)"

# Clean up local tar
rm spot-arm64.tar.gz
