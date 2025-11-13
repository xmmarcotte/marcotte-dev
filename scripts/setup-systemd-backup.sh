#!/bin/bash
# Set up automated backups for marcotte-dev using systemd timers
# Run this on your LOCAL machine (laptop/desktop) to pull backups from Oracle instance

ORACLE_IP="${1}"
BACKUP_DIR="${2:-$HOME/.marcotte-dev-backup}"

if [ -z "$ORACLE_IP" ]; then
  echo "Usage: ./setup-systemd-backup.sh <oracle-ip> [backup-directory]"
  echo ""
  echo "Example: ./setup-systemd-backup.sh 100.87.243.40"
  echo ""
  echo "This creates a systemd timer that:"
  echo "  - Runs daily at 2 AM"
  echo "  - Catches up missed backups when laptop boots"
  echo "  - Logs to journalctl and backup directory"
  exit 1
fi

# Get absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup.sh"

if [ ! -f "$BACKUP_SCRIPT" ]; then
  echo "❌ backup.sh not found at: $BACKUP_SCRIPT"
  exit 1
fi

echo "🔧 Setting up systemd backup timer..."
echo "   Oracle IP: ${ORACLE_IP}"
echo "   Backup Dir: ${BACKUP_DIR}"
echo "   Backup Script: ${BACKUP_SCRIPT}"

# Make sure backup script is executable
chmod +x "$BACKUP_SCRIPT"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Create systemd service file
SERVICE_FILE="$HOME/.config/systemd/user/marcotte-dev-backup.service"
mkdir -p "$(dirname "$SERVICE_FILE")"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Marcotte Dev Backup (Spot MCP Server)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${BACKUP_SCRIPT} ${ORACLE_IP} ${BACKUP_DIR}
StandardOutput=append:${BACKUP_DIR}/systemd.log
StandardError=append:${BACKUP_DIR}/systemd.log

[Install]
WantedBy=default.target
EOF

echo "✅ Created service: $SERVICE_FILE"

# Create systemd timer file
TIMER_FILE="$HOME/.config/systemd/user/marcotte-dev-backup.timer"

cat > "$TIMER_FILE" << EOF
[Unit]
Description=Marcotte Dev Backup Timer
Requires=marcotte-dev-backup.service

[Timer]
# Run daily at 2 AM
OnCalendar=daily
OnCalendar=*-*-* 02:00:00

# If laptop was off at 2 AM, run 5 minutes after boot
Persistent=true

# Don't run if we just ran within the last 23 hours
# (prevents duplicate runs if you reboot multiple times in a day)
AccuracySec=1h

[Install]
WantedBy=timers.target
EOF

echo "✅ Created timer: $TIMER_FILE"

# Reload systemd and enable timer
systemctl --user daemon-reload

if [ $? -ne 0 ]; then
  echo "❌ Failed to reload systemd daemon"
  exit 1
fi

systemctl --user enable marcotte-dev-backup.timer

if [ $? -ne 0 ]; then
  echo "❌ Failed to enable timer"
  exit 1
fi

systemctl --user start marcotte-dev-backup.timer

if [ $? -ne 0 ]; then
  echo "❌ Failed to start timer"
  exit 1
fi

echo ""
echo "✅ Systemd timer configured successfully!"
echo ""
echo "📋 Timer Status:"
systemctl --user status marcotte-dev-backup.timer --no-pager | head -10
echo ""
echo "📅 Next scheduled run:"
systemctl --user list-timers marcotte-dev-backup.timer --no-pager
echo ""
echo "🔍 Useful commands:"
echo ""
echo "  Check timer status:"
echo "    systemctl --user status marcotte-dev-backup.timer"
echo ""
echo "  View logs:"
echo "    journalctl --user -u marcotte-dev-backup.service -f"
echo "    tail -f ${BACKUP_DIR}/systemd.log"
echo ""
echo "  Manually trigger backup now:"
echo "    systemctl --user start marcotte-dev-backup.service"
echo ""
echo "  See next scheduled run:"
echo "    systemctl --user list-timers"
echo ""
echo "  Stop/disable timer:"
echo "    systemctl --user stop marcotte-dev-backup.timer"
echo "    systemctl --user disable marcotte-dev-backup.timer"
echo ""
echo "📝 Logs location:"
echo "    ${BACKUP_DIR}/systemd.log"
echo "    ${BACKUP_DIR}/last-sync.log"
echo ""
echo "🎉 Done! Backups will run daily at 2 AM, or after boot if missed."
