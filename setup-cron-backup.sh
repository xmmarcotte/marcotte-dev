#!/bin/bash
# Set up automated rsync backup on Linux laptop

ORACLE_IP="${1}"
BACKUP_DIR="${2:-$HOME/spot-backup}"
SCHEDULE="${3:-daily}"  # daily, hourly, or custom cron

if [ -z "$ORACLE_IP" ]; then
  echo "Usage: ./setup-cron-backup.sh <oracle-ip> [backup-directory] [schedule]"
  echo ""
  echo "Schedule options:"
  echo "  daily   - Run at 3 AM every day (default)"
  echo "  hourly  - Run every hour"
  echo "  custom  - You'll edit crontab manually"
  echo ""
  echo "Example: ./setup-cron-backup.sh 123.45.67.89 ~/spot-backup daily"
  exit 1
fi

# Get absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup-local.sh"

if [ ! -f "$BACKUP_SCRIPT" ]; then
  echo "❌ backup-local.sh not found at: $BACKUP_SCRIPT"
  exit 1
fi

echo "🔧 Setting up automated backup..."
echo "   Oracle IP: ${ORACLE_IP}"
echo "   Backup Dir: ${BACKUP_DIR}"
echo "   Schedule: ${SCHEDULE}"

# Make sure backup script is executable
chmod +x "$BACKUP_SCRIPT"

# Build cron command
CRON_CMD="${BACKUP_SCRIPT} ${ORACLE_IP} ${BACKUP_DIR} >> ${BACKUP_DIR}/cron.log 2>&1"

# Set schedule
case $SCHEDULE in
  daily)
    CRON_SCHEDULE="0 3 * * *"  # 3 AM every day
    DESCRIPTION="daily at 3 AM"
    ;;
  hourly)
    CRON_SCHEDULE="0 * * * *"  # Top of every hour
    DESCRIPTION="every hour"
    ;;
  custom)
    echo ""
    echo "Add this line to your crontab (crontab -e):"
    echo ""
    echo "# Spot Memory Server backup"
    echo "0 3 * * * ${CRON_CMD}"
    echo ""
    echo "Schedule format: MIN HOUR DAY MONTH WEEKDAY"
    echo "Examples:"
    echo "  0 3 * * *     - Daily at 3 AM"
    echo "  0 */6 * * *   - Every 6 hours"
    echo "  0 3 * * 0     - Weekly on Sunday at 3 AM"
    exit 0
    ;;
  *)
    echo "❌ Invalid schedule: $SCHEDULE"
    echo "   Use: daily, hourly, or custom"
    exit 1
    ;;
esac

# Add to crontab
(crontab -l 2>/dev/null | grep -v "backup-local.sh"; echo "# Spot Memory Server backup ($DESCRIPTION)"; echo "${CRON_SCHEDULE} ${CRON_CMD}") | crontab -

if [ $? -eq 0 ]; then
  echo "✅ Cron job added successfully!"
  echo ""
  echo "Schedule: ${DESCRIPTION}"
  echo "Command: ${CRON_CMD}"
  echo ""
  echo "To view your crontab:"
  echo "  crontab -l"
  echo ""
  echo "To edit manually:"
  echo "  crontab -e"
  echo ""
  echo "To test the backup now:"
  echo "  ${BACKUP_SCRIPT} ${ORACLE_IP} ${BACKUP_DIR}"
  echo ""
  echo "Logs will be written to:"
  echo "  ${BACKUP_DIR}/cron.log"
  echo "  ${BACKUP_DIR}/last-sync.log"
else
  echo "❌ Failed to add cron job"
  exit 1
fi
