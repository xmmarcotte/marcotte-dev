# Linux Laptop Setup Guide

Once your Oracle Cloud instance is running, here's how to set up your Linux laptop to access it.

## Files to Transfer from Windows

### 1. Oracle Cloud API Keys (Optional - only if managing infrastructure from laptop)

```bash
# On Windows, copy the .oci directory
scp -r ~/.oci your-linux-user@your-linux-laptop:/home/your-linux-user/

# Or manually copy:
#   ~/.oci/oci_api_key.pem (private key)
```

**Note:** Only needed if you want to run Terraform from your laptop. Not needed for just using the MCP server.

### 2. SSH Keys (for accessing Oracle instance)

**Option A: Use the same key** (simpler)
```bash
# On Windows, copy your SSH key
scp ~/.ssh/id_rsa your-linux-user@your-linux-laptop:/home/your-linux-user/.ssh/
scp ~/.ssh/id_rsa.pub your-linux-user@your-linux-laptop:/home/your-linux-user/.ssh/

# On Linux laptop, set permissions
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_rsa.pub
```

**Option B: Use a different key** (more secure)
```bash
# On Linux laptop, generate new key
ssh-keygen -t rsa -b 4096 -C "laptop-oracle-cloud"

# Add the new public key to Oracle instance
ssh ubuntu@<oracle-public-ip>  # Using Windows key
echo "$(cat ~/.ssh/id_rsa.pub)" | ssh ubuntu@<oracle-public-ip> "cat >> ~/.ssh/authorized_keys"
```

## Install Tailscale on Linux Laptop

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate (use same account as your other devices)
sudo tailscale up

# Verify connectivity
tailscale status
ping <oracle-tailscale-ip>
```

## Configure Cursor IDE on Linux

Update your Cursor `mcp.json`:

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://<oracle-tailscale-ip>:3856/mcp",
      "autoStart": false,
      "description": "Spot memory on Oracle Cloud via Tailscale"
    }
  }
}
```

**Location:** Usually `~/.config/Cursor/User/globalStorage/mcp.json` on Linux

## Set Up Automated Backups

From your Linux laptop, back up the Oracle instance data:

```bash
# Clone this repo (if not already)
git clone <your-repo-url>
cd marcotte-dev

# Set up daily backups (uses Tailscale IP)
./scripts/setup-cron-backup.sh <oracle-tailscale-ip> ~/marcotte-dev-backup daily
```

This will:
- Create `~/marcotte-dev-backup/` directory
- Set up a daily cron job
- Back up all Qdrant data via rsync over Tailscale

## Optional: Install Terraform on Linux (if you want to manage infrastructure)

```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y gnupg software-properties-common
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install terraform

# Verify
terraform version
```

Then copy terraform.tfvars (if you want to run Terraform from laptop):

```bash
# From Windows, securely copy your terraform config
scp infrastructure/terraform.tfvars your-linux-user@your-linux-laptop:~/marcotte-dev/infrastructure/

# Update the private_key_path in terraform.tfvars on Linux
# Change from: C:/Users/mmarcotte/.oci/oci_api_key.pem
# To: /home/your-linux-user/.oci/oci_api_key.pem
```

## What You'll Have

After setup:
- ✅ SSH access to Oracle instance
- ✅ Tailscale private network access
- ✅ Cursor IDE configured with MCP server
- ✅ Automated daily backups
- ✅ (Optional) Terraform for infrastructure management

## Quick Reference

**SSH to Oracle instance:**
```bash
ssh ubuntu@<oracle-tailscale-ip>
# Or using public IP initially:
ssh ubuntu@<oracle-public-ip>
```

**Check Spot MCP Server status:**
```bash
ssh ubuntu@<oracle-tailscale-ip>
docker logs -f spot-memory-server
```

**Test MCP Server from laptop:**
```bash
curl http://<oracle-tailscale-ip>:3856/mcp
```

**Check backup status:**
```bash
ls -lh ~/marcotte-dev-backup/
cat ~/marcotte-dev-backup/cron.log
```

## Differences from Windows Setup

| Task | Windows | Linux |
|------|---------|-------|
| SSH key path | `~/.ssh/id_rsa` (Git Bash) | `~/.ssh/id_rsa` |
| OCI key path | `C:/Users/.../.oci/` | `/home/.../.oci/` |
| Cursor config | `%APPDATA%\Cursor\...` | `~/.config/Cursor/...` |
| Terraform path | `C:/Users/.../marcotte-dev/` | `~/marcotte-dev/` |

## Troubleshooting

**Can't SSH to instance:**
- Verify Tailscale is running: `tailscale status`
- Try public IP first to verify SSH key works
- Check instance is running in Oracle Console

**Cursor can't connect to MCP server:**
- Verify Tailscale IP is correct
- Test with curl first: `curl http://<tailscale-ip>:3856/mcp`
- Restart Cursor after updating mcp.json

**Backups not working:**
- Check cron logs: `cat ~/marcotte-dev-backup/cron.log`
- Verify SSH key allows passwordless access
- Test rsync manually: `./scripts/backup.sh <oracle-tailscale-ip> ~/marcotte-dev-backup`
