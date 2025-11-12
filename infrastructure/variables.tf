variable "tenancy_ocid" {
  description = "OCID of your tenancy"
  type        = string
}

variable "user_ocid" {
  description = "OCID of the user calling the API"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the API key"
  type        = string
}

variable "private_key_path" {
  description = "Path to the private key file"
  type        = string
}

variable "compartment_ocid" {
  description = "OCID of the compartment where resources will be created"
  type        = string
}

variable "region" {
  description = "Oracle Cloud region (e.g., us-ashburn-1, us-phoenix-1)"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key for instance access"
  type        = string
}

variable "tailscale_auth_key" {
  description = "Tailscale auth key for automatic setup (optional, leave empty for manual setup)"
  type        = string
  default     = ""
  sensitive   = true
}

