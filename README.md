# marcotte-dev

Infrastructure and services for my Oracle Cloud Always Free instance.

**Tailscale IP:** `<TAILSCALE_IP>` (private mesh network - see GitHub Secrets)
**Public IP:** `<PUBLIC_IP>` (Oracle Cloud - see GitHub Secrets)
**Domain:** `marcotte.dev` (future)

## Services

### [Spot MCP Server](services/spot-mcp-server/)
Semantic memory and codebase intelligence MCP server for Cursor IDE.

**Status:** ✅ Production (deployed and running)
**Endpoint:** `http://<TAILSCALE_IP>:3856/mcp`
**Tech:** Python, FastMCP, Qdrant, FastEmbed

**Features:**
- Persistent memory across all machines
- Semantic codebase search with workspace isolation
- Architectural decision tracking
- Code pattern recognition
- AST-based code chunking
- Incremental indexing with hash-based change detection

See [services/spot-mcp-server/README.md](services/spot-mcp-server/README.md) for details.

## Infrastructure

### Oracle Cloud Always Free
- **Instance:** VM.Standard.A1.Flex
- **CPU:** 4 ARM cores (Ampere Altra)
- **RAM:** 24GB
- **Storage:** 200GB boot volume
- **Cost:** $0/month (free forever)

### Networking
- **Tailscale:** Private mesh VPN for secure access
- **Public IP:** Only for initial setup, then Tailscale-only
- **Firewall:** iptables + Oracle Cloud security lists

### Backups
- **Primary:** Automated daily rsync to local machine via Tailscale
- **Location:** `~/.marcotte-dev-backup/` on your laptop/desktop
- **Schedule:** Daily at 2:00 AM (with catch-up on boot if missed)
- **Method:** Systemd timer (runs on your local machine)
- **Retention:** Single current mirror (fast recovery)
- **Scripts:** See [scripts/](scripts/)

## Quick Start

### 🎯 Option 1: GitHub Actions CI/CD (Manual Trigger)

**Deploy from GitHub Actions:**
1. Set up GitHub Secrets (see [GitHub Actions Setup](docs/GITHUB_ACTIONS_SETUP.md))
2. Go to **Actions** → **Deploy to Oracle Cloud** → **Run workflow**
3. Choose action and click **Run workflow**
4. GitHub Actions handles everything automatically!

**Benefits:**
- ✅ No local setup required
- ✅ Data preservation during redeploys
- ✅ Full infrastructure automation
- ✅ Run on-demand when you're ready

See [GitHub Actions Setup Guide](docs/GITHUB_ACTIONS_SETUP.md) for details.

### 🚀 Option 2: Local Automated Provisioning

**First time setup:**
1. Configure Terraform (see [Terraform Setup Guide](docs/TERRAFORM_SETUP.md))
2. Run full provisioning:
   ```bash
   ./scripts/provision.sh
   ```
   This automatically:
   - Provisions infrastructure (VM, networking, security)
   - Installs Docker, Tailscale, and system updates
   - Restores data from backup (if exists)
   - Deploys all services

**Redeploy after updates:**
```bash
# Just run the same command - it handles everything including data preservation!
./scripts/provision.sh
```

### Manual Deployment (If Instance Already Exists)

```bash
# Deploy all services
./scripts/deploy.sh <oracle-tailscale-ip>

# Deploy specific service
./scripts/deploy.sh <oracle-tailscale-ip> spot-mcp-server
```

### Set Up Backups

**Run on your local machine (laptop/desktop):**
```bash
# Systemd timer - runs daily at 2 AM, catches up on boot if missed
./scripts/setup-systemd-backup.sh <TAILSCALE_IP> ~/.marcotte-dev-backup
```

**Why this works:**
- ✅ Runs missed backups when you boot up (laptop was off at 2 AM? No problem!)
- ✅ Prevents duplicate runs if you reboot multiple times
- ✅ Pulls data from Oracle instance via Tailscale (secure)
- ✅ Easy to monitor with `systemctl --user list-timers`

## Monitoring

```bash
# SSH to instance (via Tailscale - recommended)
ssh ubuntu@<TAILSCALE_IP>

# Or via public IP
ssh ubuntu@<PUBLIC_IP>

# Check all services
docker ps

# Check specific service
docker logs -f spot-mcp-server

# Check resources
htop
df -h
```

## Documentation

- **[Cursor Integration](docs/CURSOR_INTEGRATION.md)** - How to use Spot with Cursor IDE
- **[GitHub Actions Deployment](docs/GITHUB_ACTIONS_SETUP.md)** - Automated deployments from GitHub
- **[GitHub Secrets Setup](docs/GITHUB_SECRETS.md)** - Quick guide to configure CI/CD secrets
- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [Terraform Setup](docs/TERRAFORM_SETUP.md) - Infrastructure as Code

## Adding a New Service

1. Create `services/your-service/` directory
2. Add Dockerfile and service code
3. Add to `services/docker-compose.yml` if it should orchestrate with others
4. Update this README
5. Test locally, then deploy with `./scripts/deploy.sh`

## Current Status

**Instance:** ✅ Deployed and running
**Services:** ✅ Spot MCP Server operational
**Backups:** ✅ Automated daily backups configured
**Cost:** $0/month (Always Free tier)

Oracle Cloud Always Free includes:
- 2 VM.Standard.A1.Flex instances (4 OCPUs, 24GB RAM total)
- 200GB boot volumes
- 10TB/month outbound data transfer
- Permanent (not trial-based)

## Future Plans

- [ ] Host at `marcotte.dev` domain
- [ ] Add monitoring dashboard (Grafana?)
- [ ] Add more services as needed
- [ ] Consider multi-region backup

## License

Apache 2.0
