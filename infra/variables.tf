# ── Variables ──────────────────────────────────────────────────────────

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "westeurope"
}

variable "environment" {
  description = "Environment name (used in resource naming)"
  type        = string
  default     = "dev"
}

variable "admin_token" {
  description = "Admin token for protected API endpoints"
  type        = string
  sensitive   = true
}

variable "backend_image" {
  description = "Full container image reference for the backend (e.g. myacr.azurecr.io/beerpong-api:latest)"
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
}
