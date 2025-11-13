# What to Do When Your Instance is Created! 🎉

Congratulations! You got through the capacity lottery. Here's your step-by-step guide to get everything running.

---

## 📝 Information You Have

From the Oracle Console or Terraform output:
```
Public IP: 129.146.x.x (for initial SSH access)
Instance Name: marcotte-dev
Region: us-ashburn-1
```

---

## ⏱️ Step 1: Wait for Cloud-Init (5-10 minutes)

Your instance is running, but cloud-init is still installing Docker and Tailscale in the background.

**Check if it's ready:**

```bash
# SSH to the instance (use Git Bash on Windows)
ssh ubuntu@<public-ip>

# Check if cloud-init is complete
ls ~/.cloud-init-complete

# If that file exists, you're good to go!
# If not, watch the progress:
tail -f /var/log/cloud-init-output.log
# Press Ctrl+C when you see "Cloud-init v.X.X.X finished"
```

**What cloud-init installs:**
- ✅ System updates
- ✅ Docker
- ✅ Tailscale
- ✅ Creates `/home/ubuntu/qdrant-data/` directory

---

## 🔐 Step 2: Set Up Tailscale (2 minutes)

**On the Oracle instance:**

```bash
# Start Tailscale
sudo tailscale up

# You'll see output like:
#
# To authenticate, visit:
#   https://login.tailscale.com/a/xxxxxxxxxxxxx
#
```

**Copy that URL and open it in your browser:**
1. It will ask you to authenticate
2. Approve the device
3. Done!

**Get your Tailscale IP:**

```bash
tailscale ip -4
# Example output: 100.101.102.103

# SAVE THIS IP - you'll need it for everything!
```

**Verify from your Windows machine:**

```bash
# In Git Bash
ping 100.101.102.103
# Should get replies!
```

---

## 🐳 Step 3: Deploy Spot MCP Server (3-5 minutes)

**On your Windows machine:**

```bash
cd ~/vscode_projects/marcotte-dev

# Deploy using Tailscale IP
./scripts/deploy.sh 100.x.x.x
```

**What this does:**
1. Builds the ARM64 Docker image (if not already built)
2. Transfers it to the Oracle instance
3. Loads and runs the container
4. Sets up auto-restart

**You'll see:**
```
🚀 Deploying marcotte-dev services
Building ARM64 image...
Transferring image...
Starting services...
✅ Deployment complete!
```

**Verify it's running:**

```bash
# SSH to the instance
ssh ubuntu@100.x.x.x

# Check container status
docker ps

# Should show:
# CONTAINER ID   IMAGE                       STATUS
# xxxxx          spot-memory-server:arm64    Up 2 minutes

# Check logs
docker logs spot-memory-server

# Should see:
# "MCP server starting on 0.0.0.0:3855"
```

---

## 🖥️ Step 4: Configure Cursor IDE (2 minutes)

**On your Windows machine:**

**Update your Cursor `mcp.json`:**

Location: `%APPDATA%\Cursor\User\globalStorage\mcp.json`

Add or update the spot server:

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://100.x.x.x:3856/mcp",
      "autoStart": false,
      "description": "Spot memory on Oracle Cloud via Tailscale",
      "tags": ["spot", "oracle-cloud", "tailscale", "private", "free"]
    }
  }
}
```

**Replace `100.x.x.x` with your actual Tailscale IP!**

**Restart Cursor:**
1. Close Cursor completely
2. Reopen it
3. Test the connection

**Test from command line:**

```bash
# In Git Bash
curl http://100.x.x.x:3856/mcp

# Should return JSON with server info
```

---

## 💾 Step 5: Set Up Automated Backups (Optional, 2 minutes)

**On your Linux laptop (or Windows with WSL):**

```bash
cd ~/marcotte-dev

# Set up daily automated backups via Tailscale
./scripts/setup-cron-backup.sh 100.x.x.x ~/marcotte-dev-backup daily
```

**This creates:**
- Daily rsync backups over Tailscale (secure, no public exposure)
- Backup location: `~/marcotte-dev-backup/`
- Cron job that runs automatically
- Logs: `~/marcotte-dev-backup/cron.log`

**Test the backup manually:**

```bash
./scripts/backup.sh 100.x.x.x ~/marcotte-dev-backup

# Check the backup
ls -lh ~/marcotte-dev-backup/qdrant-data/
```

---

## ✅ Step 6: Test Everything Works!

### Test 1: Store Something

**In Cursor (or any IDE with MCP):**

Say to Claude/AI:
```
Remember that I successfully deployed my Oracle Cloud instance today!
```

### Test 2: Retrieve It

**From a different machine with Cursor configured:**

Say to Claude/AI:
```
What did I deploy today?
```

You should get back your stored memory about the Oracle Cloud instance!

### Test 3: Index a Codebase (Optional)

```
Can you index this codebase for semantic search?
```

The AI should use the `spot-index-codebase` tool to analyze your code.

---

## 📊 Monitoring Your Instance

### Check Container Status

```bash
ssh ubuntu@100.x.x.x
docker ps
docker logs -f spot-memory-server
```

### Check Resource Usage

```bash
ssh ubuntu@100.x.x.x

# Memory usage
free -h

# Disk usage
df -h
du -sh ~/qdrant-data

# Container stats
docker stats spot-memory-server
```

**Expected usage:**
- RAM: ~2-4GB used (out of 24GB)
- Disk: ~1-5GB (depending on indexed data)
- CPU: <5% idle, ~20% during indexing

---

## 🔧 Maintenance Commands

### Restart the Service

```bash
ssh ubuntu@100.x.x.x
docker restart spot-memory-server
```

### View Logs

```bash
ssh ubuntu@100.x.x.x
docker logs -f spot-memory-server
```

### Update the Service

```bash
# On your Windows machine
cd ~/vscode_projects/marcotte-dev
git pull
./scripts/deploy.sh 100.x.x.x
```

### Check Backup Status

```bash
# On your Linux laptop
cat ~/marcotte-dev-backup/cron.log
ls -lh ~/marcotte-dev-backup/qdrant-data/
```

---

## 🎓 What You've Achieved

You now have:

✅ **Free ARM instance** (4 cores, 24GB RAM, $0/month forever)
✅ **Private network** via Tailscale (encrypted mesh)
✅ **Spot MCP Server** running 24/7
✅ **Shared memory** accessible from all your machines
✅ **Semantic codebase search** with workspace isolation
✅ **Automated backups** (if configured)

---

## 🚨 Troubleshooting

### Can't SSH with Tailscale IP

**Try:**
```bash
# Check Tailscale is running on your machine
tailscale status

# Ping the instance
ping 100.x.x.x

# If ping fails, use public IP temporarily
ssh ubuntu@<public-ip>

# On the instance, check Tailscale
sudo tailscale status
```

### Cursor Can't Connect to MCP Server

**Check:**
1. Verify Tailscale IP is correct in `mcp.json`
2. Test with curl first: `curl http://100.x.x.x:3856/mcp`
3. Check container is running: `ssh ubuntu@100.x.x.x docker ps`
4. Check container logs: `docker logs spot-memory-server`
5. Restart Cursor completely

### Docker Container Not Running

```bash
ssh ubuntu@100.x.x.x

# Check container status
docker ps -a

# If stopped, check logs
docker logs spot-memory-server

# Restart it
docker start spot-memory-server

# If that doesn't work, redeploy
# (from Windows machine)
./scripts/deploy.sh 100.x.x.x
```

### Out of Disk Space

```bash
ssh ubuntu@100.x.x.x

# Check disk usage
df -h

# Clean up Docker
docker system prune -a

# Clean up old logs
sudo journalctl --vacuum-time=7d
```

---

## 📚 Next Steps

Now that everything is running:

1. **Read:** `docs/LAPTOP_SETUP.md` - Set up your Linux laptop
2. **Read:** `services/spot-mcp-server/README.md` - Learn about all the MCP tools
3. **Explore:** Try indexing different codebases
4. **Share:** Access your memories from multiple machines
5. **Expand:** Add more services to your Oracle instance

---

## 🎉 Congratulations!

You fought through the capacity lottery and won!

Your instance will run **forever for $0/month** as long as you:
- ✅ Keep it active (MCP server does this automatically)
- ✅ Stay within Always Free limits (you are)
- ✅ Have backups (in case Oracle ever reclaims it)

**Enjoy your new cloud infrastructure!** 🚀
