# marcotte-dev Setup Guide

Complete guide to deploying and managing the marcotte-dev Oracle Cloud infrastructure.

## Prerequisites

- **Oracle Cloud Account** (free tier)
- **Local machine** with Docker and SSH
- **Linux laptop** for backups (optional but recommended)
- **Tailscale account** (free)

## 1. Oracle Cloud VM Setup

### Provision the Instance

1. Log in to [Oracle Cloud Console](https://cloud.oracle.com/)
2. Navigate to **Compute** → **Instances** → **Create Instance**
3. Configure:
   - **Name:** `marcotte-dev`
   - **Image:** Ubuntu 22.04 (Always Free eligible)
   - **Shape:** VM.Standard.A1.Flex (ARM)
   - **OCPUs:** 4
   - **Memory:** 24GB
   - **Boot Volume:** 200GB
   - **Network:** Create new VCN or use existing
   - **SSH Keys:** Upload your public key

4. **Security List Rules** (Oracle Cloud Firewall):
   - Keep SSH (port 22) for initial setup
   - We'll use Tailscale after setup (no other ports needed)

### Initial SSH Connection

```bash
# Connect via public IP (initial setup only)
ssh ubuntu@<public-ip>

# Update system
sudo apt update && sudo apt upgrade -y
```

## 2. Install Docker

```bash
# Install Docker on ARM64
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in for group changes
exit
ssh ubuntu@<public-ip>

# Verify
docker run hello-world
```

## 3. Install and Configure Tailscale

Tailscale provides secure, private access to your instance from all your machines.

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Connect to your network
sudo tailscale up

# Note your Tailscale IP (100.x.x.x)
tailscale ip -4
```

**On all your other machines** (laptop, desktop, etc):
```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Connect
sudo tailscale up
```

Now all your machines can access the Oracle instance via its Tailscale IP (`100.x.x.x`) without exposing ports publicly.

### Lock Down Oracle Firewall (Recommended)

Once Tailscale is working, you can remove public access:

```bash
# On Oracle instance - configure iptables to only allow Tailscale
sudo iptables -A INPUT -i tailscale0 -j ACCEPT
sudo iptables -A INPUT -i lo -j ACCEPT
sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 22 -s $(tailscale ip -4)/32 -j ACCEPT
sudo iptables -A INPUT -j DROP

# Save rules
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

In **Oracle Cloud Console**, you can also modify the Security List to only allow SSH from your IP or remove the rules entirely (iptables will handle it).

## 4. Deploy Services

### Clone Repository (on local machine)

```bash
git clone https://github.com/xmmarcotte/marcotte-dev.git
cd marcotte-dev
```

### Deploy All Services

```bash
# Use Tailscale IP for deployment
./scripts/deploy.sh 100.x.x.x all
```

Or deploy specific service:
```bash
./scripts/deploy.sh 100.x.x.x spot-mcp-server
```

The script will:
1. Build ARM64 Docker image locally
2. Transfer image to Oracle instance
3. Deploy and start container
4. Verify it's running

### Verify Deployment

```bash
# From any Tailscale-connected machine
curl http://100.x.x.x:3856/mcp

# Should return MCP server info
```

## 5. Set Up Backups

On your **Linux laptop** (or any machine that stays online):

```bash
# One-time setup for daily backups at 3 AM
./scripts/setup-cron-backup.sh 100.x.x.x ~/marcotte-dev-backup daily

# Or manual backup anytime
./scripts/backup.sh 100.x.x.x ~/marcotte-dev-backup
```

### Restore from Backup

If your Oracle instance fails or you need to restore:

```bash
./scripts/restore.sh ~/marcotte-dev-backup 100.x.x.x
```

Recovery time: ~15 minutes

## 6. Configure Cursor IDE

On **each machine** where you use Cursor, update `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "spot": {
      "url": "http://100.x.x.x:3856/mcp",
      "autoStart": false,
      "description": "Spot MCP Server - semantic memory across all machines",
      "tags": ["spot", "memory", "codebase"]
    }
  }
}
```

Replace `100.x.x.x` with your Oracle instance's Tailscale IP.

### Cursor Rules

Add these rules to Cursor settings for best results:

📄 See [CURSOR_INTEGRATION.md](CURSOR_INTEGRATION.md) for detailed rules.

**Quick version:**
- Call `spot-find` before replying (unless trivial)
- Call `spot-store` after replying (unless trivial)
- Use categories: `decision`, `pattern`, `memory`

## 7. Monitoring

### Check Service Status

```bash
# SSH to instance
ssh ubuntu@100.x.x.x

# List running containers
docker ps

# Check specific service
docker logs -f spot-mcp-server

# Resource usage
htop
df -h
```

### Health Checks

```bash
# From any machine
curl http://100.x.x.x:3856/mcp

# Or use Spot tools in Cursor
spot-index-status()
spot-list-workspaces()
```

## 8. Adding New Services

1. Create `services/your-service/` directory
2. Add Dockerfile and code
3. Update `services/docker-compose.yml` to include it
4. Update `scripts/deploy.sh` with deploy function
5. Update root `README.md`
6. Deploy: `./scripts/deploy.sh 100.x.x.x your-service`

## Troubleshooting

### Can't Connect to Oracle Instance

```bash
# Verify Tailscale is running
tailscale status

# Check you can ping the instance
ping 100.x.x.x

# If SSH fails, connect via Oracle Cloud Console (serial console)
```

### Container Won't Start

```bash
# SSH to instance
ssh ubuntu@100.x.x.x

# Check logs
docker logs spot-mcp-server

# Restart container
docker restart spot-mcp-server

# Check disk space
df -h

# Check memory
free -h
```

### Backup Failed

```bash
# Verify SSH works via Tailscale
ssh ubuntu@100.x.x.x

# Check backup script permissions
ls -la scripts/backup.sh
chmod +x scripts/backup.sh

# Run manually to see error
./scripts/backup.sh 100.x.x.x ~/marcotte-dev-backup
```

## Cost Monitoring

Oracle Cloud Always Free includes:
- 2 VM.Standard.A1.Flex instances (4 OCPUs, 24GB RAM each)
- 200GB boot volumes (2 volumes)
- 10TB/month outbound data transfer

**Current usage:** 1 VM, 1 boot volume = $0/month

Check your billing in Oracle Cloud Console to ensure you stay in free tier.

## Security Best Practices

1. ✅ Use Tailscale for all access (not public IPs)
2. ✅ Keep Oracle firewall locked down
3. ✅ Automated backups to separate machine
4. ✅ Regular system updates: `sudo apt update && sudo apt upgrade`
5. ✅ Monitor Docker logs for anomalies
6. ✅ Use SSH keys (not passwords)

## Future Enhancements

- [ ] Custom domain (marcotte.dev) pointing to Tailscale IP
- [ ] Monitoring dashboard (Grafana + Prometheus)
- [ ] CI/CD for automated deployments
- [ ] Multi-region backup strategy

## Support

For issues:
1. Check service logs: `docker logs spot-mcp-server`
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
3. Test individual tools: see [services/spot-mcp-server/README.md](../services/spot-mcp-server/README.md)
