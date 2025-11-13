# GitHub Secrets Configuration

To enable automated deployments via GitHub Actions, configure these secrets in your repository.

## Required Secrets

Go to: **Repository → Settings → Secrets and variables → Actions → New repository secret**

### SSH Access

| Secret Name | Value | Notes |
|------------|-------|-------|
| `SSH_PRIVATE_KEY` | Contents of `~/.ssh/id_rsa` | Used to SSH into the instance |
| `ORACLE_TAILSCALE_IP` | Your instance's Tailscale IP | Run `ssh ubuntu@<PUBLIC_IP> 'tailscale ip -4'` |
| `ORACLE_PUBLIC_IP` | Your instance's public IP | From Oracle Cloud Console |

### How to Get SSH Private Key

```bash
# On your Linux laptop
cat ~/.ssh/id_rsa
```

Copy the entire output (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`)

## Testing the Workflow

Once secrets are configured:

1. Go to **Actions** tab in GitHub
2. Select **Deploy to Oracle Cloud** workflow
3. Click **Run workflow**
4. Choose service: `all` or `spot-mcp-server`
5. Click **Run workflow** button
6. Monitor the deployment logs

## Deployment Process

The workflow will:
1. ✅ Checkout code
2. ✅ Set up Docker Buildx for ARM64 cross-compilation
3. ✅ Configure SSH access
4. ✅ Test connection to instance
5. ✅ Build and deploy services
6. ✅ Verify deployment
7. ✅ Test MCP endpoint

## Security Notes

- ✅ **Never commit secrets** to the repository
- ✅ **Use GitHub Secrets** for all sensitive values
- ✅ **Tailscale IP is private** - only accessible via your mesh network
- ✅ **SSH keys are encrypted** in GitHub Secrets
- ✅ **Workflow logs** automatically redact secret values

## Troubleshooting

### SSH Connection Fails

**Check:**
- `SSH_PRIVATE_KEY` matches the public key on the instance
- `ORACLE_TAILSCALE_IP` is correct (run `tailscale status` on laptop)
- Instance is running: `ssh ubuntu@<TAILSCALE_IP> 'uptime'`

### Docker Build Fails

**Solution:**
- ARM64 cross-compilation can be slow (10-15 minutes)
- GitHub Actions has 6 hour timeout (plenty of time)
- Check Dockerfile syntax if it fails quickly

### MCP Server Not Responding

**Check:**
```bash
ssh ubuntu@<TAILSCALE_IP> 'docker logs spot-mcp-server'
```

Look for startup errors or missing dependencies.

## Using GitHub Actions

Once secrets are configured, you can deploy via:
1. **GitHub Actions** - Push to trigger automatic deployment
2. **Manual workflow** - Actions tab → Run workflow
3. **Local deployment** - `./scripts/deploy.sh <TAILSCALE_IP>`

All three methods are supported and will keep your instance up-to-date.
