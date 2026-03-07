# ── Beer Pong Tournament – Azure Infrastructure ──────────────────────
#
# Resources:
#   - Resource Group
#   - Cosmos DB (serverless, NoSQL API) + database + container
#   - Container Registry (Basic)
#   - Log Analytics Workspace
#   - Container App Environment + Container App (backend API)
#   - Static Web App (frontend)
# ─────────────────────────────────────────────────────────────────────

locals {
  prefix = "bp${var.environment}"
}

# Random suffix to avoid name collisions
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

# ── Resource Group ────────────────────────────────────────────────────

resource "azurerm_resource_group" "main" {
  name     = "${local.prefix}-rg-${random_string.suffix.result}"
  location = var.location

  tags = {
    project     = "beerpong"
    environment = var.environment
  }
}

# ── Cosmos DB (Serverless, NoSQL) ─────────────────────────────────────

resource "azurerm_cosmosdb_account" "db" {
  name                = "${local.prefix}-cosmos-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  tags = azurerm_resource_group.main.tags
}

resource "azurerm_cosmosdb_sql_database" "beerpong" {
  name                = "beerpong"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.db.name
}

resource "azurerm_cosmosdb_sql_container" "matches" {
  name                = "matches"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.db.name
  database_name       = azurerm_cosmosdb_sql_database.beerpong.name
  partition_key_paths  = ["/tournamentId"]
}

resource "azurerm_cosmosdb_sql_container" "teams" {
  name                = "teams"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.db.name
  database_name       = azurerm_cosmosdb_sql_database.beerpong.name
  partition_key_paths  = ["/tournamentId"]
}

# ── Container Registry ────────────────────────────────────────────────

resource "azurerm_container_registry" "acr" {
  name                = "${local.prefix}acr${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true

  tags = azurerm_resource_group.main.tags
}

# ── Log Analytics (required by Container App Environment) ─────────────

resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${local.prefix}-logs-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = azurerm_resource_group.main.tags
}

# ── Container App Environment ─────────────────────────────────────────

resource "azurerm_container_app_environment" "env" {
  name                       = "${local.prefix}-cae-${random_string.suffix.result}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
    minimum_count         = 0
    maximum_count         = 0
  }

  tags = azurerm_resource_group.main.tags
}

# ── Container App (Backend API) ───────────────────────────────────────

resource "azurerm_container_app" "backend" {
  name                         = "${local.prefix}-api-${random_string.suffix.result}"
  container_app_environment_id = azurerm_container_app_environment.env.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name   = "beerpong-api"
      image  = var.backend_image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.db.endpoint
      }
      env {
        name        = "COSMOS_KEY"
        secret_name = "cosmos-key"
      }
      env {
        name  = "COSMOS_DATABASE"
        value = "beerpong"
      }
      env {
        name  = "COSMOS_CONTAINER"
        value = "matches"
      }
      env {
        name        = "ADMIN_TOKEN"
        secret_name = "admin-token"
      }
      env {
        name  = "CORS_ORIGINS"
        value = "*"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  secret {
    name  = "cosmos-key"
    value = azurerm_cosmosdb_account.db.primary_key
  }

  secret {
    name  = "admin-token"
    value = var.admin_token
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  tags = azurerm_resource_group.main.tags

  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
    ]
  }
}

# ── Static Web App (Frontend) ────────────────────────────────────────

resource "azurerm_static_web_app" "frontend" {
  name                = "${local.prefix}-swa-${random_string.suffix.result}"
  location            = "westeurope"
  resource_group_name = azurerm_resource_group.main.name
  sku_tier            = "Free"
  sku_size            = "Free"

  tags = azurerm_resource_group.main.tags
}
