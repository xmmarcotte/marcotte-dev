# marcotte-dev

Infrastructure and services for my Oracle Cloud Always Free instance.

**Tailscale IP:** `100.x.x.x` (private mesh network)
**Domain:** `marcotte.dev` (future)

## Services

### [Spot MCP Server](services/spot-mcp-server/)
Semantic memory and codebase intelligence MCP server for Cursor IDE.

**Status:** ✅ Production (tested and deployed)
**Endpoint:** `http://100.x.x.x:3856/mcp`
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
- **Primary:** Automated daily rsync to Linux laptop via Tailscale
- **Location:** `~/marcotte-dev-backup/` on laptop
- **Retention:** Single current mirror (fast recovery)
- **Scripts:** See [scripts/](scripts/)

## Quick Start

### Deploy All Services

```bash
# From your local machine (must have SSH access to Oracle instance)
./scripts/deploy.sh <oracle-tailscale-ip>
```

### Deploy Specific Service

```bash
cd services/spot-mcp-server
docker-compose up -d
```

### Set Up Backups

```bash
# On your Linux laptop
./scripts/setup-cron-backup.sh 100.x.x.x ~/marcotte-dev-backup daily
```

## Monitoring

```bash
# SSH to instance
ssh ubuntu@100.x.x.x

# Check all services
docker ps

# Check specific service
docker logs -f spot-mcp-server

# Check resources
htop
df -h
```

## Documentation

- [Oracle Cloud Setup](docs/SETUP.md) - VM provisioning, Tailscale, security
- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [Cursor Integration](docs/CURSOR_INTEGRATION.md) - How to use with Cursor IDE

## Adding a New Service

1. Create `services/your-service/` directory
2. Add Dockerfile and service code
3. Add to `services/docker-compose.yml` if it should orchestrate with others
4. Update this README
5. Test locally, then deploy with `./scripts/deploy.sh`

## Costs

**Current:** $0/month
**Projection:** $0/month (Always Free tier)

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
