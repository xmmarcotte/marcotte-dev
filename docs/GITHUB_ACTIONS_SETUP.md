# GitHub Actions CI/CD Setup

This guide explains how to set up automated deployments from GitHub to Oracle Cloud.

## Overview

The GitHub Actions workflow (`/.github/workflows/deploy.yml`) provides:
- **Automated deployments** on push to `main` branch
- **Manual deployments** via workflow dispatch
- **Full infrastructure provisioning** with Terraform
- **Service deployment** with Docker
- **Data preservation** during redeploys

## Prerequisites

1. **GitHub Repository** with this codebase
2. **Oracle Cloud Account** with API keys configured
3. **Tailscale Account** (optional, for auth key)
4. **SSH Key Pair** for instance access

## Step 1: Configure GitHub Secrets

Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add the following secrets:

### Oracle Cloud Infrastructure (OCI) Secrets

| Secret Name | Description | How to Get |
|------------|-------------|------------|
| `OCI_TENANCY_OCID` | Your tenancy OCID | Identity → Tenancy → Tenancy Details |
| `OCI_USER_OCID` | Your user OCID | Identity → Users → Your User |
| `OCI_FINGERPRINT` | API key fingerprint | Identity → Users → Your User → API Keys |
| `OCI_PRIVATE_KEY` | Contents of your OCI API private key | The `.pem` file you downloaded |
| `OCI_COMPARTMENT_OCID` | Compartment OCID | Identity → Compartments → Your Compartment |
| `OCI_REGION` | Region code | e.g., `us-ashburn-1`, `us-phoenix-1` |

### SSH Secrets

| Secret Name | Description | How to Get |
|------------|-------------|------------|
| `SSH_PRIVATE_KEY` | Your SSH private key | Contents of `~/.ssh/id_rsa` |
| `SSH_PUBLIC_KEY` | Your SSH public key | Contents of `~/.ssh/id_rsa.pub` |
| `ORACLE_PUBLIC_IP` | Current instance public IP (optional) | From Oracle Cloud Console or Terraform output |

### Tailscale (Optional)

| Secret Name | Description | How to Get |
|------------|-------------|------------|
| `TAILSCALE_AUTH_KEY` | Tailscale auth key for automatic setup | Tailscale Admin Console → Settings → Keys → Generate auth key |

**Note**: If you don't provide `TAILSCALE_AUTH_KEY`, you'll need to manually authenticate Tailscale after provisioning.

### Backup (Optional)

| Secret Name | Description | How to Get |
|------------|-------------|------------|
| `BACKUP_SSH_KEY` | SSH key for backup server access | Your backup server SSH private key |

## Step 2: Generate Tailscale Auth Key (Recommended)

For fully automated deployments, generate a Tailscale auth key:

1. Go to [Tailscale Admin Console](https://login.tailscale.com/admin/settings/keys)
2. Click **Generate auth key**
3. Set expiration (or use reusable key)
4. Copy the key
5. Add as `TAILSCALE_AUTH_KEY` secret in GitHub

**Important**: Use a reusable key if you want to redeploy without regenerating.

## Step 3: Running the Workflow

The workflow runs **manually only** (no automatic triggers):

### Manual (Workflow Dispatch)
- Go to **Actions** → **Deploy to Oracle Cloud** → **Run workflow**
- Choose action:
  - **deploy**: Deploy services only (infrastructure must exist)
  - **provision**: Full infrastructure provisioning + deploy
- Optional: Skip backup checkbox
- Click **Run workflow** to start

## Step 4: First Deployment

1. **Go to Actions tab** in GitHub
2. **Select "Deploy to Oracle Cloud"** workflow
3. **Click "Run workflow"** button
4. **Choose action** (deploy or provision)
5. **Click "Run workflow"** to start
6. **Watch the workflow run**
7. **Check the summary** at the end for deployment info

## How It Works

### Workflow Steps

1. **Checkout Code** - Gets the latest code
2. **Setup Terraform** - Installs Terraform
3. **Configure SSH** - Sets up SSH keys for instance access
4. **Configure Terraform** - Creates `terraform.tfvars` from secrets
5. **Setup OCI API Key** - Configures Oracle Cloud authentication
6. **Terraform Init/Plan/Apply** - Provisions or updates infrastructure
7. **Wait for Instance** - Waits for cloud-init to complete
8. **Setup Tailscale** - Authenticates Tailscale (if auth key provided)
9. **Backup/Restore** - Handles data preservation
10. **Build & Deploy** - Builds Docker images and deploys services
11. **Verify** - Checks that services are running

### Data Preservation

The workflow handles data preservation:
- **Before destroy**: Backs up data (if backup server configured)
- **After create**: Restores data from backup
- **Your MCP memory bank is preserved!**

**Note**: The backup/restore steps are placeholders. Implement based on your backup strategy:
- Option 1: Use your existing backup server
- Option 2: Use Oracle Cloud Object Storage
- Option 3: Use GitHub Actions artifacts (for small datasets)

## Terraform State Management

By default, Terraform state is stored locally in the GitHub Actions runner. This means:
- ✅ State is lost between runs (but Terraform can recreate)
- ⚠️ For production, consider using a remote backend

### Option 1: OCI Object Storage Backend (Recommended)

Update `infrastructure/main.tf`:

```hcl
terraform {
  backend "s3" {
    endpoint   = "https://<namespace>.compat.objectstorage.<region>.oraclecloud.com"
    bucket     = "terraform-state"
    key        = "marcotte-dev/terraform.tfstate"
    region     = "<region>"
    access_key = "<access-key>"
    secret_key = "<secret-key>"
    # ... other S3-compatible settings
  }
}
```

### Option 2: GitHub Actions Cache

The workflow can cache Terraform state (add to workflow):

```yaml
- name: Cache Terraform State
  uses: actions/cache@v3
  with:
    path: infrastructure/.terraform
    key: terraform-${{ runner.os }}-${{ hashFiles('infrastructure/**/*.tf') }}
```

## Troubleshooting

### Workflow Fails at Terraform Apply

**Error**: `Out of host capacity`

**Solution**: 
- Try a different region
- Wait and retry (free tier instances can be limited)

### Tailscale Not Working

**Error**: `tailscale status` shows disconnected

**Solution**:
- Check `TAILSCALE_AUTH_KEY` secret is set correctly
- Verify auth key hasn't expired
- Manually authenticate: SSH to instance and run `sudo tailscale up`

### SSH Connection Fails

**Error**: `Permission denied (publickey)`

**Solution**:
- Verify `SSH_PRIVATE_KEY` and `SSH_PUBLIC_KEY` secrets are correct
- Ensure public key matches the one in Terraform
- Check instance is running: `terraform output instance_public_ip`

### Container Build Fails

**Error**: Docker buildx issues

**Solution**:
- The workflow sets up QEMU for ARM64 emulation
- This can be slow - consider using GitHub-hosted ARM runners (if available)
- Or build images locally and push to a registry

## Security Best Practices

1. ✅ **Never commit secrets** - Use GitHub Secrets only
2. ✅ **Rotate keys regularly** - Update OCI API keys and SSH keys periodically
3. ✅ **Use Tailscale auth keys with expiration** - Set reasonable expiration times
4. ✅ **Limit workflow permissions** - Use least privilege
5. ✅ **Review workflow logs** - Check for exposed secrets in logs

## Advanced: Custom Deployment Strategies

### Deploy Only on Tags

Update workflow trigger:

```yaml
on:
  push:
    tags:
      - 'v*'
```

### Deploy to Different Environments

Use workflow inputs or environment variables:

```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        type: choice
        options: [staging, production]
```

Then use in Terraform:

```yaml
- name: Configure Terraform
  run: |
    echo "environment = \"${{ github.event.inputs.environment }}\"" >> terraform.tfvars
```

## Monitoring Deployments

- **GitHub Actions tab** - View all workflow runs
- **Workflow summary** - See deployment info at end of run
- **Instance logs** - SSH to instance and check `docker logs`

## Next Steps

1. Set up all GitHub Secrets
2. Generate Tailscale auth key
3. Push to `main` or trigger manually
4. Monitor the deployment
5. Update your Cursor `mcp.json` with the Tailscale IP

## See Also

- [Terraform Setup](TERRAFORM_SETUP.md) - Manual Terraform setup
- [Oracle Cloud Setup](SETUP.md) - Manual deployment guide
- [GitHub Actions Documentation](https://docs.github.com/en/actions)


