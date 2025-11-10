#!/bin/bash
# Backup marcotte-dev data from Oracle Cloud

ORACLE_IP="${1}"
ORACLE_USER="ubuntu"
BACKUP_DIR="${2:-$HOME/marcotte-dev-backup}"

if [ -z "$ORACLE_IP" ]; then
  echo "Usage: ./backup.sh <oracle-ip> [backup-directory]"
  echo "Example: ./backup.sh 100.x.x.x ~/marcotte-dev-backup"
  exit 1
fi

echo "💾 Backing up marcotte-dev from Oracle Cloud..."
echo "   Source: ${ORACLE_USER}@${ORACLE_IP}"
echo "   Destination: ${BACKUP_DIR}"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Backup Spot MCP Server data
echo ""
echo "📦 Spot MCP Server..."
rsync -avz --delete \
  ${ORACLE_USER}@${ORACLE_IP}:~/qdrant-data/ \
  "${BACKUP_DIR}/spot-mcp-server/qdrant-data/"

if [ $? -eq 0 ]; then
  BACKUP_SIZE=$(du -sh "${BACKUP_DIR}/spot-mcp-server/qdrant-data" 2>/dev/null | cut -f1)
  echo "✅ Spot MCP Server synced (${BACKUP_SIZE})"
else
  echo "❌ Spot MCP Server sync failed"
  exit 1
fi

# Add more service backups here as needed
# echo ""
# echo "📦 Another Service..."
# rsync -avz ...

# Log the backup
echo ""
echo "Last synced: $(date)" >> "${BACKUP_DIR}/last-sync.log"
echo "✅ All backups completed!"
echo ""
echo "To restore:"
echo "  ./restore.sh ${BACKUP_DIR} ${ORACLE_IP}"
