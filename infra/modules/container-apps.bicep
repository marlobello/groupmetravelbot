@description('Azure region for Container Apps resources.')
param location string

@description('Name of the Container App.')
param containerAppName string

@description('Name of the Container Apps Environment.')
param environmentName string

@description('Public GHCR image reference (e.g., ghcr.io/owner/repo:tag). No credentials needed.')
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Resource ID of the user-assigned managed identity.')
param managedIdentityId string

@description('Client ID of the user-assigned managed identity.')
param managedIdentityClientId string

@description('Cosmos DB account endpoint.')
param cosmosEndpoint string

@description('Azure OpenAI account endpoint.')
param openaiEndpoint string

@description('Storage account name.')
param storageAccountName string

@secure()
@description('GroupMe Bot ID secret.')
param groupmeBotId string

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'groupme-bot-id'
          value: groupmeBotId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'travelbot'
          image: containerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'AZURE_CLIENT_ID'
              value: managedIdentityClientId
            }
            {
              name: 'COSMOS_ENDPOINT'
              value: cosmosEndpoint
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: openaiEndpoint
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: 'gpt-4o'
            }
            {
              name: 'STORAGE_ACCOUNT_NAME'
              value: storageAccountName
            }
            {
              name: 'STORAGE_CONTAINER_NAME'
              value: 'itineraries'
            }
            {
              name: 'GROUPME_BOT_ID'
              secretRef: 'groupme-bot-id'
            }
            {
              name: 'BOT_TRIGGER_KEYWORD'
              value: '@sensei'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

@description('FQDN of the Container App.')
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
