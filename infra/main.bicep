@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Environment name used as a prefix for resource names.')
param environmentName string

@secure()
@description('GroupMe Bot ID for the travel bot.')
param groupmeBotId string

@secure()
@description('Secret token for webhook URL path.')
param webhookSecret string

@secure()
@description('Access key for web UI authentication.')
param webAccessKey string

@description('GHCR container image reference (set by CI/CD). Public GHCR image — no credentials needed.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Custom domain hostname (e.g. sensei.dotheneedful.dev). Leave empty to skip.')
param customDomainName string = 'sensei.dotheneedful.dev'

var resourceToken = uniqueString(resourceGroup().id)

// ─── Managed Identity ────────────────────────────────────────────────
module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    location: location
    managedIdentityName: '${environmentName}-identity-${resourceToken}'
  }
}

// ─── Azure OpenAI ────────────────────────────────────────────────────
module openai 'modules/openai.bicep' = {
  name: 'openai'
  params: {
    location: location
    openaiAccountName: '${environmentName}-openai-${resourceToken}'
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

// ─── Storage ─────────────────────────────────────────────────────────
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    storageAccountName: '${environmentName}st${resourceToken}'
    managedIdentityPrincipalId: identity.outputs.managedIdentityPrincipalId
  }
}

// ─── Container Apps ──────────────────────────────────────────────────
module containerApps 'modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    location: location
    containerAppName: '${environmentName}-app-${resourceToken}'
    environmentName: '${environmentName}-env-${resourceToken}'
    containerImage: containerImage
    managedIdentityId: identity.outputs.managedIdentityId
    managedIdentityClientId: identity.outputs.managedIdentityClientId
    openaiEndpoint: openai.outputs.openaiEndpoint
    storageAccountName: storage.outputs.storageAccountName
    groupmeBotId: groupmeBotId
    webhookSecret: webhookSecret
    webAccessKey: webAccessKey
    customDomainName: customDomainName
  }
}

// ─── Outputs ─────────────────────────────────────────────────────────
@description('FQDN of the deployed Container App.')
output containerAppFqdn string = containerApps.outputs.containerAppFqdn

@description('Name of the deployed Container App.')
output containerAppName string = '${environmentName}-app-${resourceToken}'

@description('Name of the resource group-scoped Bicep deployment (used by CI/CD to query outputs).')
output deploymentName string = deployment().name

@description('Azure OpenAI account endpoint.')
output openaiEndpoint string = openai.outputs.openaiEndpoint
