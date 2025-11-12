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

# Allow non-interactive mode via environment variable
if [ "${RESTORE_NON_INTERACTIVE:-false}" != "true" ]; then
  read -p "This will overwrite existing data on Oracle Cloud. Continue? (y/N) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 1
  fi
else
  echo "Non-interactive mode: proceeding with restore..."
fi

# Restore Spot MCP Server
if [ -d "$BACKUP_DIR/spot-mcp-server/qdrant-data" ]; then
  echo ""
  echo "📦 Restoring Spot MCP Server..."

  # Stop container if it exists
  echo "⏸️  Stopping container (if running)..."
  ssh ${ORACLE_USER}@${ORACLE_IP} "docker stop spot-mcp-server 2>/dev/null || true"

  # Ensure data directory exists
  ssh ${ORACLE_USER}@${ORACLE_IP} "mkdir -p ~/qdrant-data && chmod 755 ~/qdrant-data"

  # Rsync to Oracle
  echo "📤 Uploading data..."
  rsync -avz --delete \
    "${BACKUP_DIR}/spot-mcp-server/qdrant-data/" \
    ${ORACLE_USER}@${ORACLE_IP}:~/qdrant-data/

  # Start container if it exists, otherwise it will be started by deploy.sh
  echo "▶️  Starting container (if exists)..."
  ssh ${ORACLE_USER}@${ORACLE_IP} << 'ENDSSH'
  if docker ps -a | grep -q spot-mcp-server; then
    docker start spot-mcp-server
    sleep 5
    if docker ps | grep -q spot-mcp-server; then
      echo "✅ Spot MCP Server started"
    else
      echo "⚠️  Spot MCP Server container exists but failed to start (will be redeployed)"
      docker logs --tail 20 spot-mcp-server 2>/dev/null || true
    fi
  else
    echo "ℹ️  Container doesn't exist yet (will be created by deploy.sh)"
  fi
ENDSSH
fi

# Add more service restores here as needed

echo ""
echo "✅ Restore complete!"
echo "   Test: curl http://${ORACLE_IP}:3856/mcp"
