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

# Backup Spot MCP Server data (from Docker volume)
echo ""
echo "📦 Spot MCP Server..."

# Create local backup directory
mkdir -p "${BACKUP_DIR}/spot-mcp-server/qdrant-data"

# First, create a temporary backup on the remote server from the Docker volume
ssh ${ORACLE_USER}@${ORACLE_IP} "sudo docker run --rm -v ubuntu_qdrant-storage:/source -v /home/ubuntu/qdrant-data-temp:/backup alpine sh -c 'cp -a /source/. /backup/' && sudo chown -R ubuntu:ubuntu /home/ubuntu/qdrant-data-temp"

# Then rsync it locally
rsync -avz --delete \
  ${ORACLE_USER}@${ORACLE_IP}:~/qdrant-data-temp/ \
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
