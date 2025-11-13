# GitHub Secrets Setup Guide

**Status:** GitHub Actions is free for both public and private repositories! ✅

## Step-by-Step Instructions

### 1. Get Your Secret Values

Run these commands on your Linux laptop to get the values you'll need:

```bash
# Get your SSH private key
cat ~/.ssh/id_rsa
# Copy the ENTIRE output including "-----BEGIN" and "-----END" lines

# Get your Tailscale IP from .env file
grep INSTANCE_TAILSCALE_IP .env | cut -d'=' -f2

# Get your public IP from .env file
grep INSTANCE_PUBLIC_IP .env | cut -d'=' -f2

# Or SSH to get Tailscale IP directly
ssh ubuntu@<PUBLIC_IP> 'tailscale ip -4'
```

### 2. Navigate to GitHub Secrets

1. Go to your GitHub repository: https://github.com/YOUR_USERNAME/marcotte-dev
2. Click **Settings** (top right)
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret**

### 3. Add Each Secret

Add these three secrets one by one:

#### Secret 1: SSH_PRIVATE_KEY
- **Name:** `SSH_PRIVATE_KEY`
- **Value:** Paste the entire contents of `~/.ssh/id_rsa`
  ```
  -----BEGIN OPENSSH PRIVATE KEY-----
  b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAA...
  ... (many lines) ...
  -----END OPENSSH PRIVATE KEY-----
  ```
- Click **Add secret**

#### Secret 2: ORACLE_TAILSCALE_IP
- **Name:** `ORACLE_TAILSCALE_IP`
- **Value:** Your instance's Tailscale IP (get from `.env` file: `INSTANCE_TAILSCALE_IP`)
- Click **Add secret**

#### Secret 3: ORACLE_PUBLIC_IP
- **Name:** `ORACLE_PUBLIC_IP`
- **Value:** Your instance's public IP (get from `.env` file: `INSTANCE_PUBLIC_IP`)
- Click **Add secret**

### 4. Verify Secrets Are Set

After adding all secrets, you should see:

```
Repository secrets (3)
- SSH_PRIVATE_KEY (Updated X seconds ago)
- ORACLE_TAILSCALE_IP (Updated X seconds ago)
- ORACLE_PUBLIC_IP (Updated X seconds ago)
```

## Test the GitHub Actions Workflow

1. Go to the **Actions** tab in your repository
2. Click **Deploy to Oracle Cloud** (left sidebar)
3. Click **Run workflow** (right side)
4. Select:
   - Branch: `main`
   - Service: `spot-mcp-server` (or `all`)
5. Click **Run workflow**
6. Watch the deployment process in real-time!

## What Happens When You Deploy

The workflow will:
1. ✅ Check out your code
2. ✅ Set up Docker for ARM64 builds
3. ✅ Connect to your instance via SSH
4. ✅ Build the Spot MCP Server Docker image
5. ✅ Transfer and deploy to your Oracle instance
6. ✅ Verify the deployment succeeded
7. ✅ Test the MCP endpoint

Expected duration: ~10-15 minutes (ARM64 cross-compilation is slow)

## Security Notes

- ✅ **Secrets are encrypted** by GitHub
- ✅ **Never displayed** in logs (automatically redacted)
- ✅ **Only accessible** to workflows in your repository
- ✅ **Free tier includes** 2000 minutes/month (you'll use ~10-20 minutes/month)

## Troubleshooting

### "Secret not found" Error
- Make sure secret names are EXACTLY as shown (case-sensitive)
- Re-add the secret if you made a typo

### "Permission denied (publickey)" Error
- Your `SSH_PRIVATE_KEY` doesn't match the public key on the instance
- Verify: `ssh -i ~/.ssh/id_rsa ubuntu@<PUBLIC_IP> 'echo success'`

### Workflow Fails on "Set up Docker Buildx"
- This is a transient GitHub Actions issue
- Simply re-run the workflow

## After Setup

Once GitHub secrets are configured:

**Option 1: Automatic deployments**
- Push changes to `main` branch
- GitHub Actions automatically deploys

**Option 2: Manual deployments**
- Go to Actions → Run workflow
- Click "Run workflow"

**Option 3: Local deployments** (still works)
```bash
./scripts/deploy.sh <TAILSCALE_IP>
```

All three methods will work! Choose what's most convenient.

## Cost

**GitHub Actions:**
- ✅ **Free tier:** 2000 minutes/month
- ✅ **Your usage:** ~10 minutes/deployment
- ✅ **Estimated:** 200 deployments/month for free
- ✅ **Cost:** $0/month

**Perfect for your use case!**
