# Manual Oracle Cloud Instance Creation Guide

When to use this: If automated retry isn't working, try manual creation during off-peak hours.

## 🕐 Best Times to Try

**Highest Success Rates:**
- **Late Night:** 11pm - 3am Eastern (lowest usage)
- **Early Morning:** 5am - 8am Eastern (before business hours)
- **Monday Mornings:** 6am - 9am (weekend instances released)
- **End of Month:** Last few days (companies cleaning up)
- **Weekends:** Saturday/Sunday mornings

**Worst Times:**
- 9am - 5pm Eastern (peak business hours)
- Tuesday - Thursday midday (highest enterprise usage)

---

## 📋 Step-by-Step Manual Creation (Exact Web Console Order)

### 1. Navigate to Instance Creation

1. Log in to [Oracle Cloud Console](https://cloud.oracle.com)
2. Click **☰ menu** → **Compute** → **Instances**
3. Click **Create Instance**

---

## SECTION 1: Basic Information

### Name and Compartment

```
Name: marcotte-dev
Compartment: xmmarcotte (root)
```

---

### Placement

**Try in this order:**

**First Attempt:**
```
Availability Domain: AD-1 (qWrp:US-ASHBURN-AD-1)
Capacity type: On-demand capacity
Fault domain: Let Oracle choose the best fault domain
```

**If AD-1 fails with "Out of capacity", try:**
```
Availability Domain: AD-2 (qWrp:US-ASHBURN-AD-2)
(keep other settings same)
```

**If AD-2 fails, try:**
```
Availability Domain: AD-3 (qWrp:US-ASHBURN-AD-3)
(keep other settings same)
```

---

### Image

1. Click **Change Image**
2. Click **Browse All Images**
3. Select: **Canonical Ubuntu 24.04**
   - NOT "Minimal"
   - NOT "aarch64" suffix
   - Just regular "Canonical Ubuntu 24.04"

**Verify it shows:**
```
Publisher: Oracle
Price: Free
```

---

### Shape

**CRITICAL - Must be exact:**

1. Click **Change Shape**
2. Select **Ampere** (third box - ARM-based processor)
3. Click **VM.Standard.A1.Flex**
4. Click **"Advanced options"** or look for the sliders:

```
Number of OCPUs: 4
Amount of memory (GB): 24
Network bandwidth (Gbps): 4 (auto-sets)
```

**Verify the "Shape build" shows:**
```
Virtual machine, 4 core OCPU, 24 GB memory, 4 Gbps network bandwidth
```

---

### Management

**Scroll down to the Management subsection**

**Instance metadata service:**
```
☐ Require an authorization header (leave UNCHECKED)
```

**Initialization script:**
```
☑ Choose cloud-init script file (SELECT THIS!)

Click "Drop a file or select one"
Upload: C:\Users\mmarcotte\vscode_projects\marcotte-dev\infrastructure\cloud-init.yaml
```

This installs Docker and Tailscale automatically!

---

### Availability Configuration

```
Live migration: Let Oracle choose the best migration option
☑ Restore instance lifecycle state after infrastructure maintenance (CHECKED)
```

---

### Oracle Cloud Agent

**Keep these 4 enabled (already checked by default):**
```
☑ Compute Instance Monitoring
☑ Cloud Guard Workload Protection
☑ Custom Logs Monitoring
☑ Compute Instance Run Command
```

**Leave others disabled:**
```
☐ WebLogic Management Service
☐ Vulnerability Scanning
☐ Oracle Java Management Service
☐ OS Management Hub Agent
☐ Management Agent
☐ Fleet Application Management Service
☐ Compute RDMA GPU Monitoring
☐ Compute HPC RDMA Auto-Configuration
☐ Compute HPC RDMA Authentication
☐ Block Volume Management
☐ Bastion
```

---

## SECTION 2: Security

Click **Next** or scroll down to the Security section.

**Leave all defaults (all disabled):**
```
☐ Secure Boot
☐ Measured Boot
☐ Trusted Platform Module
☐ Confidential computing
```

---

## SECTION 3: Networking

Click **Next** or scroll down to the Networking section.

### Primary VNIC

**Option A: Create New VCN (if first time or destroyed old ones):**
```
Primary network:
  ☑ Create new virtual cloud network
  VCN Name: marcotte-dev-vcn
  Compartment: xmmarcotte (root)

Subnet:
  ☑ Create new public subnet
  Subnet Name: marcotte-dev-subnet
  Compartment: xmmarcotte (root)
```

**Option B: Use Existing (if you see them in the dropdowns):**
```
Primary network:
  ☑ Select existing virtual cloud network
  Virtual cloud network: marcotte-dev-vcn

Subnet:
  ☑ Select existing subnet
  Subnet: marcotte-dev-subnet (regional)
```

**PUBLIC IP (CRITICAL!):**
```
Public IPv4 address: ☑ Assign a public IPv4 address (MUST BE CHECKED!)
```

**Other networking settings (leave defaults):**
```
Private IPv4 address: Automatically assigned
Use network security groups: No
Hostname: (leave empty or auto-generated)
```

---

### Add SSH Keys

**Scroll down in the Networking section:**

```
Add SSH keys:
  ☑ Upload public key file (.pub)

  Click "Choose Files"
  Navigate to: C:\Users\mmarcotte\.ssh\id_rsa.pub
  Select and upload it
```

**Verify you see your key displayed:**
```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCpBDE0vOomwVP6w... oracle-cloud-marcotte-dev
```

---

## SECTION 4: Storage

Click **Next** or scroll down to the Storage section.

### Boot Volume

**Leave ALL defaults:**
```
☐ Specify a custom boot volume size and performance setting
   (LEAVE UNCHECKED - default 46.6 GB is perfect and FREE)

☑ Use in-transit encryption
   (LEAVE CHECKED - good for security)

☐ Encrypt this volume with a key that you manage
   (LEAVE UNCHECKED - Oracle manages it)
```

---

### Block Volumes

**Don't attach any:**
```
Block volumes: (leave empty - you don't need additional volumes)
```

---

## Review and Create

### Double-Check These Critical Settings:

✅ **Name:** marcotte-dev
✅ **Shape:** VM.Standard.A1.Flex with **4 OCPUs, 24 GB RAM**
✅ **Image:** Canonical Ubuntu 24.04
✅ **Cloud-init script:** Uploaded ✓
✅ **Public IP:** Assigned
✅ **SSH Key:** Uploaded ✓
✅ **Boot volume:** Default (46.6 GB)

**Estimated Cost:**
```
May show $2.00/month - This is MISLEADING!
It doesn't account for Always Free credits.
Your actual cost will be $0.00/month
```

---

### Click "Create"!

Click the big blue **"Create"** button at the bottom

---

## 🎯 What Happens Next

### If It Succeeds: 🎉

You'll see:
```
Creating instance...
Status: Provisioning
```

Wait 2-3 minutes, it will change to:
```
Status: Running
Public IP: 129.146.x.x
```

**Next steps:** See `WHEN_INSTANCE_SUCCEEDS.md`

### If It Fails: 😞

You'll see one of these errors:

**"Out of host capacity"**
```
Try the next availability domain (AD-2, then AD-3)
OR
Wait and try again during off-peak hours
```

**"Authorization failed"**
```
The VCN/subnet doesn't exist anymore
Go back to Networking section and choose "Create new"
```

**"Invalid parameter"**
```
Usually the shape configuration is wrong
Go back and verify: 4 OCPUs, 24 GB exactly
```

---

## 💡 Pro Tips

### Tip 1: Have Multiple Browser Tabs Ready
- Pre-fill 3 tabs with AD-1, AD-2, AD-3
- Try them rapid-fire during off-peak hours
- Capacity can appear and disappear in minutes

### Tip 2: Try Immediately After Midnight
- 12:00am - 12:30am Eastern
- Many automated cleanup scripts run at midnight
- Fresh capacity often appears

### Tip 3: Keep Retrying the Same AD
- If you get "Out of capacity" on AD-1
- Wait 2-3 minutes
- Try AD-1 again before moving to AD-2
- Capacity fluctuates constantly

### Tip 4: Use Browser Auto-Refresh
- Set up form with all settings
- Use browser extension to auto-refresh and click Create
- (Advanced users only)

---

## 🆘 If Nothing Works

### Option 1: Try Phoenix Region (New Account)
1. Create new Oracle account with different email
2. Choose **Phoenix (us-phoenix-1)** as home region during signup
3. Try same settings there

### Option 2: Contact Oracle Support
Even free tier users can open tickets:
- **Community Forum:** forums.oracle.com
- **Support:** Explain you're on Always Free and can't get capacity
- Some users report Oracle helping with this

### Option 3: Wait for Capacity Expansion
Oracle announced doubling capacity in 2025. Ashburn should improve in coming weeks.

---

## 📝 Quick Reference Card

**Copy this for quick manual attempts:**

```
Name: marcotte-dev
AD: Try 1, 2, 3 in order
Image: Canonical Ubuntu 24.04
Shape: VM.Standard.A1.Flex
OCPUs: 4
RAM: 24 GB
VCN: Create new or use marcotte-dev-vcn
Public IP: ✅ YES
SSH: C:\Users\mmarcotte\.ssh\id_rsa.pub
Cloud-init: C:\Users\mmarcotte\vscode_projects\marcotte-dev\infrastructure\cloud-init.yaml
```

---

## ✅ Success Checklist

After instance is created:

- [ ] Note the Public IP
- [ ] Wait 5-10 minutes for cloud-init
- [ ] SSH in: `ssh ubuntu@<public-ip>`
- [ ] Set up Tailscale: `sudo tailscale up`
- [ ] Note Tailscale IP: `tailscale ip -4`
- [ ] Deploy services: `./scripts/deploy.sh <tailscale-ip>`
- [ ] Configure Cursor mcp.json
- [ ] Set up backups
- [ ] **Celebrate!** 🎉

---

## Good Luck! 🍀

**Remember:** Persistence pays off. Most people succeed within 1-3 days of strategic attempts during off-peak hours.

**Best single attempt:** Monday morning 6:30am Eastern
