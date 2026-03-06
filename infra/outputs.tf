# ── Outputs ────────────────────────────────────────────────────────────

output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "backend_url" {
  description = "Public URL of the backend Container App"
  value       = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}

output "frontend_url" {
  description = "Public URL of the Static Web App"
  value       = "https://${azurerm_static_web_app.frontend.default_host_name}"
}

output "swa_api_key" {
  description = "API key for deploying to Static Web App"
  value       = azurerm_static_web_app.frontend.api_key
  sensitive   = true
}

output "acr_login_server" {
  description = "ACR login server for pushing backend images"
  value       = azurerm_container_registry.acr.login_server
}

output "acr_name" {
  description = "ACR name"
  value       = azurerm_container_registry.acr.name
}

output "cosmos_endpoint" {
  description = "Cosmos DB endpoint"
  value       = azurerm_cosmosdb_account.db.endpoint
}

output "container_app_name" {
  description = "Name of the backend Container App"
  value       = azurerm_container_app.backend.name
}

output "container_app_env_name" {
  description = "Name of the Container App Environment"
  value       = azurerm_container_app_environment.env.name
}
