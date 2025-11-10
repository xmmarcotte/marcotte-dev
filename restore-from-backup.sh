#!/bin/bash
# Restore Spot Memory Server data to Oracle Cloud from local mirror

BACKUP_DIR="${1:-$HOME/spot-backup}"
ORACLE_IP="${2}"
ORACLE_USER="ubuntu"

if [ -z "$ORACLE_IP" ]; then
  echo "Usage: ./restore-from-backup.sh [backup-directory] <oracle-public-ip>"
  echo "Example: ./restore-from-backup.sh ~/spot-backup 123.45.67.89"
  exit 1
fi

if [ ! -d "$BACKUP_DIR/qdrant-data" ]; then
  echo "❌ Backup directory not found: $BACKUP_DIR/qdrant-data"
  echo "   Run backup-local.sh first to create a backup"
  exit 1
fi

echo "🔄 Restoring Spot Memory Server backup..."
echo "   Backup: ${BACKUP_DIR}/qdrant-data"
echo "   Target: ${ORACLE_USER}@${ORACLE_IP}"
echo ""
read -p "This will overwrite existing data on Oracle Cloud. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled"
  exit 1
fi

# Stop container on remote
echo "⏸️  Stopping container..."
ssh ${ORACLE_USER}@${ORACLE_IP} "docker stop spot-memory-server 2>/dev/null || true"

# Rsync to Oracle
echo "📤 Uploading to Oracle Cloud..."
rsync -avz --delete \
  "${BACKUP_DIR}/qdrant-data/" \
  ${ORACLE_USER}@${ORACLE_IP}:~/qdrant-data/

# Start container
echo "▶️  Starting container..."
ssh ${ORACLE_USER}@${ORACLE_IP} << 'ENDSSH'
docker start spot-memory-server

# Wait for startup
sleep 5

# Check if running
if docker ps | grep -q spot-memory-server; then
  echo "✅ Container started successfully"
else
  echo "❌ Container failed to start"
  docker logs --tail 50 spot-memory-server
  exit 1
fi
ENDSSH

echo ""
echo "✅ Restore complete!"
echo "   Test: curl http://${ORACLE_IP}:3856/mcp"
