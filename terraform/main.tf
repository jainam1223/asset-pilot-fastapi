terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }

  backend "azurerm" {
    resource_group_name  = "prodessy"
    storage_account_name = "tfstateprod178967"
    container_name       = "tfstate"
    key                  = "app-assest-pilot-fastapi"
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_resource_group" "rg" {
  name = "prodessy"
}

data "azurerm_service_plan" "asp" {
  name                = "asp-asset-pilot"
  resource_group_name = data.azurerm_resource_group.rg.name
}

data "azurerm_container_registry" "acr" {
  name                = "assetpilotacr2026"
  resource_group_name = data.azurerm_resource_group.rg.name
}

resource "azurerm_linux_web_app" "app" {
  name                = "asset-pilot-fastapi-app-prod"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = data.azurerm_resource_group.rg.location
  service_plan_id     = data.azurerm_service_plan.asp.id

  site_config {
    container_registry_use_managed_identity = true
    application_stack {
      docker_image_name   = "asset-pilot-fastapi:latest"
      docker_registry_url = "https://${data.azurerm_container_registry.acr.login_server}"
    }
  }

  identity {
    type = "SystemAssigned"
  }

  app_settings = {
    "WEBSITES_PORT"                    = "8000"
    "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = "false"
  }
}

resource "azurerm_role_assignment" "acr_pull" {
  principal_id                     = azurerm_linux_web_app.app.identity[0].principal_id
  role_definition_name             = "AcrPull"
  scope                            = data.azurerm_container_registry.acr.id
  skip_service_principal_aad_check = true
}
