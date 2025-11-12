# Terraform Infrastructure Setup

This guide explains how to set up automated infrastructure provisioning for marcotte-dev using Terraform and cloud-init.

## Overview

The infrastructure automation provides:
- **Terraform** for Oracle Cloud infrastructure provisioning (VM, networking, security)
- **cloud-init** for automatic instance setup (Docker, Tailscale, system updates)
- **Full redeploy** capability that preserves your MCP memory bank data

## Prerequisites

1. **Oracle Cloud Account** (free tier activated)
2. **Terraform** installed ([download](https://www.terraform.io/downloads))
3. **OCI API Key** configured
4. **SSH key pair** for instance access

## Step 1: Create OCI API Key

1. Log in to [Oracle Cloud Console](https://cloud.oracle.com/)
2. Navigate to **Identity** → **Users** → Your User
3. Click **API Keys** → **Add API Key**
4. Click **Download Private Key** (save it securely, e.g., `~/.oci/oci_api_key.pem`)
5. Click **Copy** to copy the configuration snippet
6. Note the **Fingerprint** shown

## Step 2: Get Required OCIDs

You'll need these OCIDs (Oracle Cloud Identifiers):

### Tenancy OCID
- **Identity** → **Tenancy** → **Tenancy Details** → Copy OCID

### User OCID
- **Identity** → **Users** → Your User → Copy OCID

### Compartment OCID
- **Identity** → **Compartments** → Your Compartment → Copy OCID
- If you don't have a compartment, create one or use the root compartment

### Region
- Use the region code from the top-right of the console (e.g., `us-ashburn-1`, `us-phoenix-1`)

## Step 3: Configure Terraform

1. Copy the example variables file:
   ```bash
   cd infrastructure
   cp terraform.tfvars.example terraform.tfvars
   ```

2. Edit `terraform.tfvars` with your values:
   ```hcl
   tenancy_ocid     = "ocid1.tenancy.oc1..xxxxx"
   user_ocid        = "ocid1.user.oc1..xxxxx"
   fingerprint      = "xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx"
   private_key_path = "~/.oci/oci_api_key.pem"
   compartment_ocid = "ocid1.compartment.oc1..xxxxx"
   region           = "us-ashburn-1"
   
   # Your SSH public key (contents of ~/.ssh/id_rsa.pub)
   ssh_public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC... user@host"
   ```

3. **Important**: `terraform.tfvars` is in `.gitignore` - never commit it!

## Step 4: Initialize Terraform

```bash
cd infrastructure
terraform init
```

This downloads the Oracle Cloud provider.

## Step 5: Provision Infrastructure

### Full Automated Provisioning (Recommended)

From the repository root:

```bash
./scripts/provision.sh
```

This script:
1. ✅ Backs up existing data (if instance exists)
2. ✅ Provisions infrastructure with Terraform
3. ✅ Waits for cloud-init to complete
4. ✅ Prompts for Tailscale authentication
5. ✅ Restores data from backup
6. ✅ Deploys all services

### Manual Terraform Commands

If you prefer to run Terraform manually:

```bash
cd infrastructure

# Preview changes
terraform plan

# Apply changes
terraform apply

# Get instance IP
terraform output instance_public_ip
```

## How It Works

### Infrastructure (Terraform)

The Terraform configuration (`infrastructure/main.tf`) creates:
- **VCN** (Virtual Cloud Network) with CIDR `10.0.0.0/16`
- **Subnet** with CIDR `10.0.1.0/24`
- **Internet Gateway** for public internet access
- **Security List** allowing SSH (port 22) only
- **Compute Instance**:
  - Shape: `VM.Standard.A1.Flex` (ARM64)
  - OCPUs: 4
  - Memory: 24GB
  - Image: Ubuntu 22.04 (ARM64)
  - Boot Volume: 200GB (default)

### Instance Setup (cloud-init)

The cloud-init script (`infrastructure/cloud-init.yaml`) automatically:
- Updates system packages
- Installs Docker
- Installs Tailscale
- Creates data directories
- Sets up permissions

### Data Preservation

When you redeploy:
1. **Backup**: Existing data is backed up to `~/marcotte-dev-backup/` (if instance exists)
2. **Destroy**: Old instance is destroyed (or updated)
3. **Create**: New instance is created with fresh setup
4. **Restore**: Data is restored from backup
5. **Deploy**: Services are deployed with restored data

**Your MCP memory bank is preserved!** 🎉

## Redeploying After Updates

When you make changes to the repository and want to redeploy:

```bash
# From repository root
./scripts/provision.sh
```

The script handles everything automatically, including data backup and restore.

## Terraform State

Terraform stores state in `infrastructure/terraform.tfstate`. This file:
- ✅ **Should be committed** to git (contains no sensitive data, just resource IDs)
- Tracks which resources Terraform manages
- Allows Terraform to update/destroy resources correctly

**Note**: If you delete the state file, Terraform will think resources don't exist and try to create duplicates. Keep it safe!

## Troubleshooting

### Terraform Authentication Errors

```
Error: unauthorized
```

**Solution**: Check your `terraform.tfvars`:
- Verify all OCIDs are correct
- Ensure `private_key_path` points to the correct file
- Verify the fingerprint matches your API key

### Instance Creation Fails (No Capacity)

```
Error: Out of host capacity
```

**Solution**: 
- Try a different availability domain
- Try a different region
- Wait and try again (free tier instances can be limited)

### cloud-init Not Completing

If the instance is created but cloud-init hangs:

```bash
# SSH to instance
ssh ubuntu@<public-ip>

# Check cloud-init logs
sudo tail -f /var/log/cloud-init-output.log
sudo tail -f /var/log/cloud-init.log
```

### Tailscale Not Working

After provisioning, you need to authenticate Tailscale:

```bash
ssh ubuntu@<public-ip>
sudo tailscale up
# Follow the prompts to authenticate
tailscale ip -4  # Get your Tailscale IP
```

## Manual Cleanup

To destroy all infrastructure:

```bash
cd infrastructure
terraform destroy
```

**Warning**: This will destroy the instance and all data on it. Make sure you have backups!

## Cost

All resources created are within Oracle Cloud Always Free tier:
- ✅ VM.Standard.A1.Flex (4 OCPUs, 24GB RAM)
- ✅ 200GB boot volume
- ✅ VCN, subnet, internet gateway (all free)
- ✅ Security lists (free)

**Total cost: $0/month** 🎉

## Next Steps

After provisioning:
1. Update your Cursor `mcp.json` with the Tailscale IP
2. Set up automated backups: `./scripts/setup-cron-backup.sh <tailscale-ip> ~/marcotte-dev-backup daily`
3. Test the deployment: `curl http://<tailscale-ip>:3856/mcp`

## See Also

- [SETUP.md](SETUP.md) - Manual setup guide (for reference)
- [ORACLE_CLOUD_DEPLOY.md](ORACLE_CLOUD_DEPLOY.md) - Original deployment guide
- [README.md](../README.md) - Project overview

