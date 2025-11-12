#!/bin/bash
# Full infrastructure provisioning script for marcotte-dev
# Handles: backup, terraform apply, restore, and deploy
#
# Usage: ./scripts/provision.sh [backup-dir]
#
# This script:
# 1. Backs up existing data (if instance exists)
# 2. Provisions infrastructure with Terraform
# 3. Waits for cloud-init to complete
# 4. Restores data from backup
# 5. Deploys all services

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
INFRA_DIR="${REPO_ROOT}/infrastructure"
BACKUP_DIR="${1:-$HOME/marcotte-dev-backup}"
ORACLE_USER="ubuntu"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 marcotte-dev Full Provisioning${NC}"
echo ""

# Check if terraform.tfvars exists
if [ ! -f "${INFRA_DIR}/terraform.tfvars" ]; then
  echo -e "${RED}❌ terraform.tfvars not found!${NC}"
  echo ""
  echo "Please create ${INFRA_DIR}/terraform.tfvars from terraform.tfvars.example"
  echo "See docs/TERRAFORM_SETUP.md for instructions"
  exit 1
fi

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
  echo -e "${RED}❌ Terraform not found!${NC}"
  echo ""
  echo "Install Terraform: https://www.terraform.io/downloads"
  exit 1
fi

# Step 1: Check if instance exists and backup data
echo -e "${YELLOW}📋 Step 1: Checking for existing instance...${NC}"

cd "${INFRA_DIR}"

# Initialize Terraform if needed
if [ ! -d ".terraform" ]; then
  echo "Initializing Terraform..."
  terraform init
fi

# Get current instance IP (if it exists)
CURRENT_IP=""
if terraform state show oci_core_instance.marcotte_dev &>/dev/null; then
  CURRENT_IP=$(terraform output -raw instance_public_ip 2>/dev/null || echo "")

  if [ -n "$CURRENT_IP" ]; then
    echo "Found existing instance at ${CURRENT_IP}"
    echo ""
    read -p "Backup existing data before redeploy? (Y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
      echo -e "${YELLOW}💾 Backing up data from existing instance...${NC}"
      "${SCRIPT_DIR}/backup.sh" "${CURRENT_IP}" "${BACKUP_DIR}" || {
        echo -e "${YELLOW}⚠️  Backup failed or no data to backup, continuing...${NC}"
      }
      echo ""
    fi
  fi
fi

# Step 2: Provision infrastructure
echo -e "${YELLOW}🏗️  Step 2: Provisioning infrastructure with Terraform...${NC}"
echo ""

terraform plan -out=tfplan
echo ""
read -p "Apply this plan? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled"
  exit 0
fi

terraform apply tfplan
rm -f tfplan

# Get new instance IP
NEW_IP=$(terraform output -raw instance_public_ip)
echo ""
echo -e "${GREEN}✅ Instance created: ${NEW_IP}${NC}"
echo ""

# Step 3: Wait for cloud-init to complete
echo -e "${YELLOW}⏳ Step 3: Waiting for cloud-init to complete...${NC}"
echo "This may take 2-3 minutes..."

# Add SSH options for first-time connection
SSH_OPTS="-o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null"

MAX_WAIT=300  # 5 minutes
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
  if ssh $SSH_OPTS ${ORACLE_USER}@${NEW_IP} "test -f ~/.cloud-init-complete" 2>/dev/null; then
    echo -e "${GREEN}✅ cloud-init completed!${NC}"
    break
  fi

  echo -n "."
  sleep 10
  ELAPSED=$((ELAPSED + 10))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
  echo ""
  echo -e "${RED}❌ cloud-init timeout. Please check the instance manually.${NC}"
  exit 1
fi

echo ""

# Step 4: Setup Tailscale (interactive)
echo -e "${YELLOW}🔐 Step 4: Tailscale setup${NC}"
echo ""
echo "You need to authenticate Tailscale on the instance."
echo "This requires interactive login."
echo ""
read -p "SSH to instance and run 'sudo tailscale up' now? (Y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
  echo ""
  echo "Opening SSH session. After authenticating Tailscale:"
  echo "1. Run: sudo tailscale up"
  echo "2. Note the Tailscale IP (run: tailscale ip -4)"
  echo "3. Exit SSH (Ctrl+D)"
  echo ""
  read -p "Press Enter to continue..."
  ssh $SSH_OPTS ${ORACLE_USER}@${NEW_IP}
fi

# Get Tailscale IP
echo ""
echo "Getting Tailscale IP..."
TAILSCALE_IP=$(ssh $SSH_OPTS ${ORACLE_USER}@${NEW_IP} "tailscale ip -4" 2>/dev/null || echo "")

if [ -z "$TAILSCALE_IP" ]; then
  echo -e "${YELLOW}⚠️  Could not get Tailscale IP. You may need to set it up manually.${NC}"
  echo "Please provide the Tailscale IP, or press Enter to use public IP for now:"
  read -p "Tailscale IP: " TAILSCALE_IP
  if [ -z "$TAILSCALE_IP" ]; then
    TAILSCALE_IP="${NEW_IP}"
  fi
else
  echo -e "${GREEN}✅ Tailscale IP: ${TAILSCALE_IP}${NC}"
fi

# Step 5: Restore data (if backup exists)
if [ -d "${BACKUP_DIR}/spot-mcp-server/qdrant-data" ]; then
  echo ""
  echo -e "${YELLOW}🔄 Step 5: Restoring data from backup...${NC}"
  RESTORE_NON_INTERACTIVE=true "${SCRIPT_DIR}/restore.sh" "${BACKUP_DIR}" "${TAILSCALE_IP}" || {
    echo -e "${YELLOW}⚠️  Restore failed or skipped, continuing...${NC}"
  }
else
  echo ""
  echo -e "${YELLOW}ℹ️  Step 5: No backup found, skipping restore${NC}"
fi

# Step 6: Deploy services
echo ""
echo -e "${YELLOW}🚀 Step 6: Deploying services...${NC}"
"${SCRIPT_DIR}/deploy.sh" "${TAILSCALE_IP}" "all"

echo ""
echo -e "${GREEN}✅ Provisioning complete!${NC}"
echo ""
echo "Instance details:"
echo "  Public IP: ${NEW_IP}"
echo "  Tailscale IP: ${TAILSCALE_IP}"
echo ""
echo "Test the deployment:"
echo "  curl http://${TAILSCALE_IP}:3856/mcp"
echo ""
echo "Update your Cursor mcp.json with:"
echo "  http://${TAILSCALE_IP}:3856/mcp"
