terraform {
  required_version = ">= 1.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# Get availability domains
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# Get the third availability domain (AD-3)
locals {
  ad_name = data.oci_identity_availability_domains.ads.availability_domains[2].name
}

# VCN
resource "oci_core_vcn" "marcotte_dev_vcn" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "marcotte-dev-vcn"
  dns_label      = "marcottedev"

  freeform_tags = {
    Project = "marcotte-dev"
    Managed = "terraform"
  }
}

# Internet Gateway
resource "oci_core_internet_gateway" "marcotte_dev_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.marcotte_dev_vcn.id
  display_name   = "marcotte-dev-igw"
  enabled        = true
}

# Default Route Table
resource "oci_core_default_route_table" "marcotte_dev_route_table" {
  manage_default_resource_id = oci_core_vcn.marcotte_dev_vcn.default_route_table_id

  route_rules {
    network_entity_id = oci_core_internet_gateway.marcotte_dev_igw.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }
}

# Subnet
resource "oci_core_subnet" "marcotte_dev_subnet" {
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.marcotte_dev_vcn.id
  cidr_block        = "10.0.1.0/24"
  display_name      = "marcotte-dev-subnet"
  dns_label         = "marcottesubnet"
  security_list_ids = [oci_core_security_list.marcotte_dev_security_list.id]
  route_table_id    = oci_core_vcn.marcotte_dev_vcn.default_route_table_id

  freeform_tags = {
    Project = "marcotte-dev"
  }
}

# Security List (SSH only for initial setup, Tailscale handles the rest)
resource "oci_core_security_list" "marcotte_dev_security_list" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.marcotte_dev_vcn.id
  display_name   = "marcotte-dev-security-list"

  # Allow SSH from anywhere (for initial setup)
  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"

    tcp_options {
      min = 22
      max = 22
    }
  }

  # Allow all outbound traffic
  egress_security_rules {
    protocol         = "all"
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
  }

  freeform_tags = {
    Project = "marcotte-dev"
  }
}

# Get Ubuntu 22.04 image (ARM64)
data "oci_core_images" "ubuntu_arm64" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

# Get the latest Ubuntu 22.04 ARM64 image
locals {
  ubuntu_image_id = data.oci_core_images.ubuntu_arm64.images[0].id
}

# Read cloud-init script and optionally inject Tailscale auth key
locals {
  cloud_init_base = file("${path.module}/cloud-init.yaml")
  # If TAILSCALE_AUTH_KEY is provided, inject Tailscale setup command into runcmd
  cloud_init = var.tailscale_auth_key != "" ? replace(
    local.cloud_init_base,
    "  # Tailscale auth key will be injected here if provided via Terraform variable",
    "  # Tailscale auth key will be injected here if provided via Terraform variable\n  - sudo tailscale up --authkey=${var.tailscale_auth_key} --accept-routes || true"
  ) : local.cloud_init_base
}

# Compute Instance
resource "oci_core_instance" "marcotte_dev" {
  compartment_id      = var.compartment_ocid
  availability_domain = local.ad_name
  display_name        = "marcotte-dev"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 4
    memory_in_gbs = 24
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.marcotte_dev_subnet.id
    assign_public_ip = true
    display_name     = "marcotte-dev-vnic"
  }

  source_details {
    source_type = "image"
    source_id   = local.ubuntu_image_id
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data          = base64encode(local.cloud_init)
  }

  freeform_tags = {
    Project = "marcotte-dev"
    Managed = "terraform"
  }
}

# Outputs
output "instance_public_ip" {
  description = "Public IP address of the instance"
  value       = oci_core_instance.marcotte_dev.public_ip
}

output "instance_ocid" {
  description = "OCID of the instance"
  value       = oci_core_instance.marcotte_dev.id
}

output "instance_display_name" {
  description = "Display name of the instance"
  value       = oci_core_instance.marcotte_dev.display_name
}
