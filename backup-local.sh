#!/bin/bash
# Simple rsync mirror of Spot Memory Server data from Oracle Cloud

ORACLE_IP="${1}"
ORACLE_USER="ubuntu"
BACKUP_DIR="${2:-$HOME/spot-backup}"

if [ -z "$ORACLE_IP" ]; then
  echo "Usage: ./backup-local.sh <oracle-public-ip> [backup-directory]"
  echo "Example: ./backup-local.sh 123.45.67.89 ~/spot-backup"
  exit 1
fi

echo "💾 Syncing Spot Memory Server from Oracle Cloud..."
echo "   Source: ${ORACLE_USER}@${ORACLE_IP}:~/qdrant-data"
echo "   Mirror: ${BACKUP_DIR}"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Simple rsync mirror - keeps one current copy
rsync -avz --delete \
  ${ORACLE_USER}@${ORACLE_IP}:~/qdrant-data/ \
  "${BACKUP_DIR}/qdrant-data/"

if [ $? -eq 0 ]; then
  BACKUP_SIZE=$(du -sh "${BACKUP_DIR}/qdrant-data" 2>/dev/null | cut -f1)
  echo "✅ Sync completed: ${BACKUP_DIR}/qdrant-data (${BACKUP_SIZE})"
  echo "   Last synced: $(date)" >> "${BACKUP_DIR}/last-sync.log"
else
  echo "❌ Sync failed"
  exit 1
fi

echo ""
echo "To restore this backup:"
echo "  rsync -avz ${BACKUP_DIR}/qdrant-data/ ubuntu@<oracle-ip>:~/qdrant-data/"
