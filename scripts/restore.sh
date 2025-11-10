#!/bin/bash
# Restore marcotte-dev data to Oracle Cloud from local backup

BACKUP_DIR="${1:-$HOME/marcotte-dev-backup}"
ORACLE_IP="${2}"
ORACLE_USER="ubuntu"

if [ -z "$ORACLE_IP" ]; then
  echo "Usage: ./restore.sh [backup-directory] <oracle-ip>"
  echo "Example: ./restore.sh ~/marcotte-dev-backup 100.x.x.x"
  exit 1
fi

if [ ! -d "$BACKUP_DIR" ]; then
  echo "❌ Backup directory not found: $BACKUP_DIR"
  echo "   Run backup.sh first to create a backup"
  exit 1
fi

echo "🔄 Restoring marcotte-dev backup..."
echo "   Backup: ${BACKUP_DIR}"
echo "   Target: ${ORACLE_USER}@${ORACLE_IP}"
echo ""
read -p "This will overwrite existing data on Oracle Cloud. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled"
  exit 1
fi

# Restore Spot MCP Server
if [ -d "$BACKUP_DIR/spot-mcp-server/qdrant-data" ]; then
  echo ""
  echo "📦 Restoring Spot MCP Server..."

  # Stop container
  echo "⏸️  Stopping container..."
  ssh ${ORACLE_USER}@${ORACLE_IP} "docker stop spot-mcp-server 2>/dev/null || true"

  # Rsync to Oracle
  echo "📤 Uploading data..."
  rsync -avz --delete \
    "${BACKUP_DIR}/spot-mcp-server/qdrant-data/" \
    ${ORACLE_USER}@${ORACLE_IP}:~/qdrant-data/

  # Start container
  echo "▶️  Starting container..."
  ssh ${ORACLE_USER}@${ORACLE_IP} << 'ENDSSH'
  docker start spot-mcp-server
  sleep 5
  if docker ps | grep -q spot-mcp-server; then
    echo "✅ Spot MCP Server started"
  else
    echo "❌ Spot MCP Server failed to start"
    docker logs --tail 50 spot-mcp-server
    exit 1
  fi
ENDSSH
fi

# Add more service restores here as needed

echo ""
echo "✅ Restore complete!"
echo "   Test: curl http://${ORACLE_IP}:3856/mcp"
