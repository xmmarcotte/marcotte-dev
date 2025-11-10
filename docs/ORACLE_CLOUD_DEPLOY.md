# Oracle Cloud Always Free Deployment Guide

Deploy Spot Memory Server on Oracle Cloud's Always Free tier ($0/month forever).

## 📋 Prerequisites

- Oracle Cloud account (sign up at cloud.oracle.com)
- Docker installed locally (for building ARM64 image)
- SSH key pair

## 🚀 Step 1: Create Oracle Cloud VM

### 1.1 Sign Up / Log In
- Go to https://cloud.oracle.com
- Sign up for Always Free tier (requires credit card but won't charge)
- Verify email and complete setup

### 1.2 Create Compute Instance

**Note:** Free tier ARM instances can be hard to get in popular regions. Try multiple regions if one is out of capacity.

1. **Navigate:** Compute → Instances → Create Instance

2. **Configure:**
   ```
   Name: spot-memory-server

   Placement:
   - Availability Domain: Any (try AD-1, AD-2, AD-3)

   Image:
   - Change Image → Ubuntu 22.04 (Minimal)

   Shape:
   - Change Shape → Ampere (ARM-based)
   - VM.Standard.A1.Flex
   - OCPUs: 2 (use 2 of your 4 free OCPUs)
   - Memory: 12GB (use 12 of your 24GB free)

   Networking:
   - Create new VCN: spot-vcn
   - Create new subnet: spot-subnet
   - Assign public IPv4: YES

   SSH Keys:
   - Upload your public SSH key (.ssh/id_rsa.pub)

   Boot Volume:
   - 50GB (default, plenty)
   ```

3. **Click "Create"** - Takes 2-3 minutes

4. **Note the Public IP** - You'll need this

### 1.3 Configure Firewall (SSH Only)

**VCN Security List:**
1. Networking → Virtual Cloud Networks → spot-vcn
2. Security Lists → Default Security List
3. Ingress Rules should have:
   ```
   SSH (port 22) - Already configured by default
   ```

**No need to open port 3856 publicly** - Tailscale handles private networking!

## 🐳 Step 2: Build ARM64 Docker Image

**On your local machine:**

```bash
cd mcp-server-qdrant

# Create multi-platform builder
docker buildx create --name arm-builder --use
docker buildx inspect --bootstrap

# Build for ARM64
docker buildx build \
  --platform linux/arm64 \
  -t spot-memory-server:arm64 \
  --load \
  .

# Save image to file
docker save spot-memory-server:arm64 | gzip > spot-arm64.tar.gz

# Transfer to Oracle Cloud
scp spot-arm64.tar.gz ubuntu@<oracle-public-ip>:/home/ubuntu/
```

## 📦 Step 3: Deploy on Oracle Cloud

**SSH into Oracle instance:**

```bash
ssh ubuntu@<oracle-public-ip>
```

**Install Docker:**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Log out and back in for group to take effect
exit
ssh ubuntu@<oracle-public-ip>
```

**Load and run container:**

```bash
# Load Docker image
gunzip -c spot-arm64.tar.gz | docker load

# Create data directory
mkdir -p ~/qdrant-data
chmod 755 ~/qdrant-data

# Run container
docker run -d \
  --name spot-memory-server \
  --restart unless-stopped \
  -p 3856:3855 \
  -v ~/qdrant-data:/app/qdrant-data \
  -e QDRANT_LOCAL_PATH=/app/qdrant-data \
  -e EMBEDDING_MODEL=BAAI/bge-large-en-v1.5 \
  -e FASTMCP_HOST=0.0.0.0 \
  -e FASTMCP_PORT=3855 \
  spot-memory-server:arm64

# Check logs
docker logs -f spot-memory-server
```

**Verify it's running:**

```bash
# Should return JSON with server info
curl http://localhost:3856/mcp
```

## 🔧 Step 4: Configure Your Machines (After Tailscale Setup)

**Update mcp.json on ALL your machines with the Tailscale IP:**

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://100.x.x.x:3856/mcp",
      "autoStart": false,
      "description": "Centralized Spot memory on Oracle Cloud via Tailscale - private mesh network",
      "tags": ["spot", "oracle-cloud", "tailscale", "private", "free"],
      "notes": "Oracle Cloud Always Free ARM instance (24GB RAM, 200GB storage) on Tailscale mesh. Shared memory hub accessible from any Tailscale device - encrypted, no public exposure."
    }
  }
}
```

**Test from any machine:**
```bash
# Test connectivity
curl http://100.x.x.x:3856/mcp

# Should return JSON with server info
```

**In Cursor:**
- Restart Cursor
- Run any spot- command
- Should connect through Tailscale!

## 💾 Step 5: Backup Strategy (IMPORTANT!)

Since Oracle *could* theoretically reclaim free instances, set up automated rsync backups to your Linux laptop:

### Automated Backup (One Command Setup)

**On your Linux laptop:**

```bash
# Clone the repo if you haven't already
git clone https://github.com/your-username/mcp-server-qdrant.git
cd mcp-server-qdrant

# Set up daily automated backup (use Tailscale IP for SSH)
./setup-cron-backup.sh 100.x.x.x ~/spot-backup daily

# Or hourly backups
./setup-cron-backup.sh 100.x.x.x ~/spot-backup hourly
```

**Note:** Backups use SSH over Tailscale - fast and secure!

This creates a simple rsync mirror that:
- Keeps one current copy (not 7 versions - simple!)
- Runs automatically via cron
- Logs to `~/spot-backup/cron.log`
- Takes ~10-30 seconds depending on data size

### Manual Backup Anytime

```bash
# Run backup manually (use Tailscale IP)
./backup-local.sh 100.x.x.x ~/spot-backup
```

### What Gets Backed Up

```
~/spot-backup/
├── qdrant-data/           # Complete mirror of Oracle data
├── last-sync.log          # Timestamp of last sync
└── cron.log               # Automated backup logs
```

## 🔒 Step 6: Tailscale Setup (Recommended)

Use Tailscale for secure private access without public exposure.

### Install on Oracle Instance

**SSH into Oracle:**

```bash
ssh ubuntu@<oracle-public-ip>
```

**Install and configure Tailscale:**

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Authenticate and join your network
sudo tailscale up

# Note the Tailscale IP (100.x.x.x)
tailscale ip -4
```

**Note this IP** - It will be the same from all your machines!

### Install on All Your Machines

1. **Install Tailscale** on each machine (laptop, desktop, etc.)
   - Visit: https://tailscale.com/download
   - Sign in with same account

2. **Verify connectivity:**
   ```bash
   # From any machine
   ping <tailscale-ip-of-oracle>
   ```

### Update mcp.json

**Use the Tailscale IP (100.x.x.x) instead of public IP:**

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://100.x.x.x:3856/mcp",
      "autoStart": false,
      "description": "Spot memory on Oracle Cloud via Tailscale - private mesh network",
      "tags": ["spot", "oracle-cloud", "tailscale", "private"]
    }
  }
}
```

### Benefits

✅ **No public exposure** - Port 3856 never exposed to internet
✅ **Encrypted** - All traffic encrypted via WireGuard
✅ **Same IP everywhere** - Works from any Tailscale device
✅ **Works behind NAT** - No port forwarding needed
✅ **Free** - Personal use up to 100 devices
✅ **Mobile access** - Works from phone with Tailscale app

## 🛠️ Maintenance Commands

```bash
# View logs
docker logs -f spot-memory-server

# Restart container
docker restart spot-memory-server

# Update container (after rebuilding)
docker stop spot-memory-server
docker rm spot-memory-server
docker load < spot-arm64-new.tar.gz
# Run docker run command again

# Check disk usage
df -h
du -sh ~/qdrant-data

# Check memory usage
free -h
docker stats spot-memory-server
```

## 🆘 Recovery (If Instance Gets Reclaimed)

If Oracle ever reclaims your instance:

1. **Create new instance** (same steps as above, ~10 min)

2. **Deploy container** (one command):
   ```bash
   ./deploy-oracle.sh <new-oracle-ip>
   ```

3. **Restore from your Linux laptop backup**:
   ```bash
   ./restore-from-backup.sh ~/spot-backup <new-oracle-ip>
   ```

4. **Update mcp.json** on all machines with new IP

**Total recovery time: ~15 minutes**

Your Linux laptop has the complete mirror in `~/spot-backup/qdrant-data/` - all your memories, indexed codebases, and decisions are safe!

## 📊 Resource Usage (Expected)

```
RAM: 2-4GB used (12GB allocated, plenty of headroom)
CPU: <5% idle, ~20% during indexing
Disk: 5-10GB for typical usage
Network: Minimal (<1GB/month)
```

## ✅ You're Done!

All your machines now share the same Spot memory through Oracle Cloud for **$0/month forever**.

Test by:
1. Running `spot-store` on Machine A
2. Running `spot-find` on Machine B
3. Should see the same data everywhere!
