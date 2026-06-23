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

@description('Name of existing managed certificate in the environment.')
param managedCertificateName string = 'mc-travelbot-env--sensei-dotheneed-9347'

@description('Microsoft Foundry project endpoint (Agent Service) — the bot\'s chat backend. Provided by the platform/CoE team that owns the Foundry project.')
param foundryProjectEndpoint string = 'https://sensei-resource.services.ai.azure.com/api/projects/sensei'

@description('Azure OpenAI endpoint on the Foundry account (used for attachment OCR). Provided by the platform/CoE team.')
param foundryOpenAiEndpoint string = 'https://sensei-resource.openai.azure.com/'

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
// NOTE: This app deployment is intentionally scoped to its own resource group.
// It does NOT create or modify the Foundry account/project or its role
// assignments — that boundary is owned by the platform/CoE team and granted
// out-of-band (see infra/platform/). The app only consumes the project
// endpoints passed in as parameters.
module containerApps 'modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    location: location
    containerAppName: '${environmentName}-app-${resourceToken}'
    environmentName: '${environmentName}-env-${resourceToken}'
    containerImage: containerImage
    managedIdentityId: identity.outputs.managedIdentityId
    managedIdentityClientId: identity.outputs.managedIdentityClientId
    openaiEndpoint: foundryOpenAiEndpoint
    foundryProjectEndpoint: foundryProjectEndpoint
    storageAccountName: storage.outputs.storageAccountName
    groupmeBotId: groupmeBotId
    webhookSecret: webhookSecret
    webAccessKey: webAccessKey
    customDomainName: customDomainName
    managedCertificateName: managedCertificateName
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

@description('Principal ID of the app managed identity. Hand this to the platform/CoE team so they can grant it access to the Foundry project (see infra/platform/).')
output managedIdentityPrincipalId string = identity.outputs.managedIdentityPrincipalId

